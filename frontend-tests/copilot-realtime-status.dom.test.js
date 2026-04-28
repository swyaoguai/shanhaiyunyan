// @vitest-environment jsdom

import { readFileSync } from 'node:fs';
import path from 'node:path';
import { beforeAll, beforeEach, describe, expect, it, vi } from 'vitest';

const ROOT = process.cwd();

function loadBrowserScript(relativePath) {
  const absolutePath = path.join(ROOT, relativePath);
  const source = readFileSync(absolutePath, 'utf8');
  window.eval(source);
}

function resetCoreGlobals() {
  window.apiCall = vi.fn();
  window.showToast = vi.fn();
  window.loadProjects = vi.fn().mockResolvedValue(undefined);
  window.loadSavedSettings = vi.fn().mockResolvedValue(undefined);
  window.restoreSidebarState = vi.fn();
  window.checkGlobalAPIConfig = vi.fn().mockResolvedValue(undefined);
  window.switchModule = vi.fn();
  window.initCopilotEnhancements = vi.fn();
  window.loadKnowledgeCategories = vi.fn();
}

class FakeWebSocket {
  static CONNECTING = 0;
  static OPEN = 1;
  static CLOSING = 2;
  static CLOSED = 3;
  static instances = [];

  constructor(url) {
    this.url = url;
    this.readyState = FakeWebSocket.CONNECTING;
    this.sent = [];
    this.listeners = new Map();
    FakeWebSocket.instances.push(this);
  }

  addEventListener(type, handler) {
    const bucket = this.listeners.get(type) || [];
    bucket.push(handler);
    this.listeners.set(type, bucket);
  }

  send(message) {
    this.sent.push(message);
  }

  close() {
    this.readyState = FakeWebSocket.CLOSED;
    this.emit('close', {});
  }

  emit(type, event) {
    const bucket = this.listeners.get(type) || [];
    for (const handler of bucket) {
      handler(event);
    }
  }

  open() {
    this.readyState = FakeWebSocket.OPEN;
    this.emit('open', {});
  }

  message(payload) {
    this.emit('message', { data: JSON.stringify(payload) });
  }
}

beforeAll(() => {
  loadBrowserScript('novel_agent/web/static/app-utils.js');
  loadBrowserScript('novel_agent/web/static/app-core.js');
  loadBrowserScript('novel_agent/web/static/continuous_write.js');
});

beforeEach(() => {
  document.body.innerHTML = `
    <div id="nav-list-container"></div>
    <div id="main-view"></div>
    <div id="breadcrumbs"></div>
    <div id="copilot-messages"></div>
    <div id="copilot-workflow-panel" class="hidden"></div>
    <div id="modal-container" class="hidden"></div>
    <span id="copilot-session-mode"></span>
    <span id="copilot-session-agent"></span>
    <button id="copilot-session-list-btn"></button>
    <div id="copilot-session-menu" class="hidden"></div>
    <div class="copilot-input"><textarea id="copilot-input-text"></textarea><button></button></div>
  `;
  localStorage.clear();
  vi.restoreAllMocks();
  resetCoreGlobals();
  window.initUIReferences();
  window.WebSocket = FakeWebSocket;
  FakeWebSocket.instances.length = 0;
  window.ui.workspace = document.getElementById('main-view');
  window.stopNovelCollabRuntimePolling?.();
  window.store.currentModule = 'write';
  window.store.copilotVisible = true;
  window.store.runtimeProjectStatus = null;
  window.store.currentTaskPool = null;
  window.store.collabExecutionTrace = null;
  window.store.projectReadyExecution = null;
  window.store.copilotWorkflow = null;
  window.store.collabRuntimePollingTimer = null;
  window.store.collabRuntimePollingBusy = false;
  window.store.collabRuntimeNextPollAt = 0;
  window.store.collabRuntimeLastFetchAt = 0;
  window.store.collabRuntimeRequestPromise = null;
  window.multiAgentWriteState = window.multiAgentWriteState || { activeView: 'chapters', collabTraceFilters: { stage: 'all', type: 'all' } };
  window.multiAgentWriteState.activeView = 'status';
});

describe('copilot realtime status', () => {
  it('renders runtime-derived status instead of the static ready text when workflow snapshot is idle', () => {
    window.store.runtimeProjectStatus = {
      workflow_state: 'writing',
      checkpoint: { current_chapter: 2 },
      project: { total_chapters: 10, completed_chapters: 1 }
    };
    window.store.currentTaskPool = {
      tasks: [
        {
          title: '生成世界观',
          task_type: 'build_world',
          status: 'running',
          assigned_agent: 'Worldbuilder'
        }
      ]
    };
    window.store.collabExecutionTrace = {
      status: 'running',
      events: [
        {
          type: 'task_started',
          title: '生成世界观',
          task_type: 'build_world',
          agent: 'Worldbuilder'
        }
      ]
    };

    window.updateCopilotWorkflowPanel({
      status: 'idle',
      current_agent: '',
      target_agent: '',
      stage: '',
      last_progress: '',
      created_files: [],
      updated_files: []
    });

    const panel = document.getElementById('copilot-workflow-panel');
    expect(panel?.classList.contains('hidden')).toBe(false);
    expect(panel?.textContent).toContain('世界观构建');
    expect(panel?.textContent).toContain('进行中');
    expect(panel?.textContent).not.toContain('多Agent创作模式已就绪');
  });

  it('localizes project-specific agent and stage names instead of showing raw english identifiers', () => {
    window.updateCopilotWorkflowPanel({
      status: 'completed',
      current_agent: 'SummaryOrchestrator',
      target_agent: 'SummaryOrchestrator',
      stage: 'summary_orchestrate',
      last_progress: '',
      created_files: [],
      updated_files: []
    });

    const panel = document.getElementById('copilot-workflow-panel');
    expect(panel?.textContent).toContain('摘要编排');
    expect(panel?.textContent).toContain('阶段总结');
    expect(panel?.textContent).not.toContain('SummaryOrchestrator');
    expect(panel?.textContent).not.toContain('summary_orchestrate');
  });

  it('polls workflow and runtime endpoints, then refreshes the status workspace', async () => {
    vi.useFakeTimers();
    window.renderCollabTaskPoolWorkspace = vi.fn();

    window.apiCall.mockImplementation(async (url) => {
      if (url === '/api/v1/status') {
        return {
          workflow_state: 'writing',
          checkpoint: { current_chapter: 3 },
          project: { total_chapters: 12, completed_chapters: 2 },
          task_pool: {
            tasks: [{ title: '章节写作', status: 'running', candidate_agents: ['ChapterWriter'] }],
            metadata: { contract_id: 'contract-rt' }
          },
          collab_execution_trace: {
            status: 'running',
            events: [{ type: 'task_started', title: '章节写作' }]
          },
          creation_contract: {
            contract_id: 'contract-rt',
            user_confirmed: true
          }
        };
      }

      throw new Error(`Unexpected URL: ${url}`);
    });

    window.startNovelCollabRuntimePolling();
    await vi.advanceTimersByTimeAsync(window.store.collabRuntimePollingIntervalMs);

    expect(window.apiCall).toHaveBeenCalledWith('/api/v1/status', 'GET');
    expect(window.renderCollabTaskPoolWorkspace).toHaveBeenCalledWith(
      expect.objectContaining({
        metadata: expect.objectContaining({ contract_id: 'contract-rt' })
      }),
      expect.objectContaining({
        status: 'running'
      }),
      null
    );
    expect(document.getElementById('copilot-workflow-panel')?.textContent).toContain('章节写作');

    window.stopNovelCollabRuntimePolling();
    vi.useRealTimers();
  });

  it('backs off polling after a 429 response instead of retrying every tick', async () => {
    vi.useFakeTimers();
    const rateLimitError = new Error('HTTP 429: 请求过于频繁');
    rateLimitError.status = 429;
    rateLimitError.retryAfter = 12;
    window.apiCall.mockRejectedValue(rateLimitError);

    window.startNovelCollabRuntimePolling();
    await vi.advanceTimersByTimeAsync(window.store.collabRuntimePollingIntervalMs);

    expect(window.apiCall).toHaveBeenCalledTimes(1);

    await vi.advanceTimersByTimeAsync(window.store.collabRuntimePollingIntervalMs * 2);
    expect(window.apiCall).toHaveBeenCalledTimes(1);

    await vi.advanceTimersByTimeAsync(12000);
    expect(window.apiCall).toHaveBeenCalledTimes(2);

    window.stopNovelCollabRuntimePolling();
    vi.useRealTimers();
  });

  it('deduplicates overlapping runtime refreshes and throttles rapid direct refresh calls', async () => {
    vi.useFakeTimers();
    let resolveFetch;
    const fetchPromise = new Promise((resolve) => {
      resolveFetch = resolve;
    });

    window.apiCall.mockImplementation(async (url) => {
      if (url !== '/api/v1/status') {
        throw new Error(`Unexpected URL: ${url}`);
      }
      await fetchPromise;
      return {
        workflow_state: 'writing',
        checkpoint: { current_chapter: 1 },
        project: { total_chapters: 8, completed_chapters: 0 },
        task_pool: null,
        collab_execution_trace: null
      };
    });

    const first = window.refreshNovelCollabRuntime();
    const second = window.refreshNovelCollabRuntime();
    expect(window.apiCall).toHaveBeenCalledTimes(1);

    resolveFetch();
    const [firstResult, secondResult] = await Promise.all([first, second]);
    expect(firstResult).toStrictEqual(secondResult);

    const third = await window.refreshNovelCollabRuntime();
    expect(window.apiCall).toHaveBeenCalledTimes(1);
    expect(third.runtimeProjectStatus?.workflow_state).toBe('writing');

    await vi.advanceTimersByTimeAsync(window.store.collabRuntimeMinRefreshIntervalMs + 10);
    await window.refreshNovelCollabRuntime();
    expect(window.apiCall).toHaveBeenCalledTimes(2);

    vi.useRealTimers();
  });

  it('subscribes to websocket progress and refreshes runtime after a realtime event', async () => {
    vi.useFakeTimers();
    let statusFetchCount = 0;
    window.apiCall.mockImplementation(async (url) => {
      if (url === '/api/v1/chat/workflow-status?session_id=copilot') {
        return {
          workflow: {
            status: 'idle',
            current_agent: '',
            target_agent: '',
            stage: '',
            last_progress: '',
            created_files: [],
            updated_files: []
          }
        };
      }
      if (url === '/api/v1/status') {
        statusFetchCount += 1;
        return {
          workflow_state: 'writing',
          checkpoint: { current_chapter: 1 },
          project: { total_chapters: 8, completed_chapters: 0 },
          task_pool: {
            tasks: [{ title: statusFetchCount > 1 ? '生成世界观' : '等待执行', status: 'running', assigned_agent: 'Worldbuilder' }],
            metadata: { contract_id: 'contract-ws' }
          },
          collab_execution_trace: {
            status: 'running',
            events: [{ type: 'task_started', title: '生成世界观', agent: 'Worldbuilder' }]
          }
        };
      }
      throw new Error(`Unexpected URL: ${url}`);
    });

    await window.restoreCopilotWorkflowStatus();

    expect(FakeWebSocket.instances.length).toBe(1);
    const socket = FakeWebSocket.instances[0];
    expect(socket.url).toContain('/ws');

    socket.open();
    expect(socket.sent).toContain(JSON.stringify({ action: 'subscribe', topic: 'novel_progress' }));

    socket.message({
      type: 'progress',
      payload: {
        agent: 'Worldbuilder',
        message: '正在生成世界观骨架（力量体系/地理/历史）...',
        progress: 40
      }
    });

    expect(document.getElementById('copilot-workflow-panel')?.textContent).toContain('世界观构建');
    expect(document.getElementById('copilot-workflow-panel')?.textContent).toContain('正在生成世界观骨架');

    await vi.advanceTimersByTimeAsync(1600);
    expect(statusFetchCount).toBe(1);
    expect(document.getElementById('copilot-workflow-panel')?.textContent).toContain('正在生成世界观骨架');

    window.stopNovelCollabRuntimePolling();
    vi.useRealTimers();
  });
});
