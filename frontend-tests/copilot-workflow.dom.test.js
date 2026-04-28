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

async function flushMicrotasks() {
  await Promise.resolve();
  await Promise.resolve();
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
  window.open = vi.fn();
  window.openChapterEditor = vi.fn();
  window.prompt = vi.fn();
  window.CSS = window.CSS || {};
  window.CSS.escape = vi.fn((value) => String(value));
  Object.defineProperty(window.HTMLElement.prototype, 'scrollIntoView', {
    configurable: true,
    value: vi.fn()
  });
  window.initUIReferences();
  window.ui.workspace = document.getElementById('main-view');
  window.stopNovelCollabRuntimePolling?.();
  window.store.currentModule = 'dashboard';
  window.store.runtimeProjectStatus = null;
  window.store.collabRuntimePollingTimer = null;
  window.store.collabRuntimePollingBusy = false;
  window.multiAgentWriteState = window.multiAgentWriteState || { activeView: 'chapters', collabTraceFilters: { stage: 'all', type: 'all' } };
  window.multiAgentWriteState.activeView = 'chapters';
  window.multiAgentWriteState.collabTraceFilters = { stage: 'all', type: 'all' };
});

describe('copilot workflow panel regressions', () => {
  it('stores workflow state and renders the compact execution panel when workflow data is present', () => {
    window.updateCopilotWorkflowPanel({
      run_id: 'run-123',
      status: 'running',
      command: 'create',
      current_agent: 'Worldbuilder',
      target_agent: 'Coordinator',
      stage: 'worldbuilding',
      last_progress: '### 世界观阶段\n正在生成世界观设定...',
      output_dir: 'C:/novel/project',
      created_files: [
        { path: 'C:/novel/project/worldbuilding.json', label: 'worldbuilding.json', kind: 'worldbuilding', status: 'created' }
      ],
      updated_files: []
    });

    expect(window.store.copilotWorkflow.run_id).toBe('run-123');
    expect(document.getElementById('copilot-workflow-panel')?.classList.contains('hidden')).toBe(false);
    expect(document.body.textContent).toContain('世界观构建');
    expect(document.body.textContent).toContain('进行中');
  });

  it('restoring workflow status requests backend snapshot and syncs runtime task pool', async () => {
    window.apiCall
      .mockResolvedValueOnce({ workflow: null })
      .mockResolvedValueOnce({
        task_pool: {
          tasks: [
            { title: '上下文规划', status: 'running', candidate_agents: ['ContextStrategy'] }
          ],
          metadata: { contract_id: 'contract-runtime' }
        },
        collab_execution_trace: {
          status: 'initialized',
          events: [{ type: 'task_started' }]
        },
        creation_contract: {
          contract_id: 'contract-runtime',
          user_confirmed: true
        }
      });

    await window.restoreCopilotWorkflowStatus();

    expect(window.apiCall).toHaveBeenCalledTimes(2);
    expect(window.apiCall).toHaveBeenNthCalledWith(1, '/api/v1/chat/workflow-status?session_id=copilot', 'GET');
    expect(window.apiCall).toHaveBeenNthCalledWith(2, '/api/v1/status', 'GET');
    expect(window.store.copilotWorkflow).toBeNull();
    expect(window.store.currentTaskPool?.metadata?.contract_id).toBe('contract-runtime');
    expect(window.store.pendingCreationContract?.contract_id).toBe('contract-runtime');
  });

  it('renders contract card and task pool summary from ai messages', () => {
    const contractHtml = window.renderCreationContractCard({
      contract_id: 'contract-1',
      user_confirmed: false,
      scope: {
        novel_type: '玄幻',
        theme: '复仇成长',
        protagonist: '林渊',
        plot_idea: '旧城归来',
        volume_count: 1,
        chapters_per_volume: 3,
        total_chapters: 3
      },
      constraints: {
        style: ['压抑', '递进'],
        quality_rules: ['避免AI腔']
      },
      deliverables: ['worldbuilding.json'],
      task_graph: [
        { title: '上下文规划', task_type: 'context_plan' }
      ]
    });

    const taskPoolHtml = window.renderTaskPoolSummaryCard({
      tasks: [
        { title: '上下文规划', status: 'pending', candidate_agents: ['ContextStrategy'] },
        { title: '章节写作', status: 'pending', candidate_agents: ['ChapterWriter'] }
      ],
      metadata: { contract_id: 'contract-1' }
    });

    window.appendMessage(contractHtml, 'ai');
    window.appendMessage(taskPoolHtml, 'ai');

    expect(document.body.textContent).toContain('创作合同草案');
    expect(document.body.textContent).toContain('任务池摘要');
    expect(document.querySelector('.copilot-contract-confirm-btn')).not.toBeNull();
  });

  it('derives realtime workflow text from runtime status when the workflow snapshot is idle', () => {
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

  it('opens task-pool workspace and renders preview entries, stop summary, next ready tasks, timeline filters and task detail modal', async () => {
    window.store.currentModule = 'write';
    window.store.projectData.outline = [{ title: '第一章' }];
    window.previewCollabResultFile = vi.fn().mockResolvedValue(undefined);
    const runtimeSnapshot = {
      task_pool: {
        tasks: [
          {
            task_id: 'task-world',
            title: '生成世界观',
            task_type: 'build_world',
            status: 'completed',
            candidate_agents: ['Worldbuilder'],
            assigned_agent: 'Worldbuilder',
            retry_count: 0,
            depends_on: [],
            result_ref: 'worldbuilding.json',
            metadata: {},
            inputs: {}
          },
          {
            task_id: 'task-outline',
            title: '生成大纲',
            task_type: 'build_outline',
            status: 'completed',
            candidate_agents: ['Outliner'],
            assigned_agent: 'Outliner',
            retry_count: 0,
            depends_on: ['task-world'],
            result_ref: 'outline.json',
            metadata: {},
            inputs: {}
          },
          {
            task_id: 'task-write-1',
            title: '第一章正文',
            task_type: 'write_chapter',
            status: 'completed',
            candidate_agents: ['ChapterWriter'],
            assigned_agent: 'ChapterWriter',
            retry_count: 0,
            depends_on: ['task-outline'],
            result_ref: 'chapters/001-第一章.md',
            metadata: {
              result_kind: 'chapter'
            },
            inputs: { chapter_number: 1 }
          },
          {
            task_id: 'task-summary-1-10',
            title: '阶段总结',
            task_type: 'summary_orchestrate',
            status: 'completed',
            candidate_agents: ['SummaryOrchestrator'],
            assigned_agent: 'SummaryOrchestrator',
            retry_count: 0,
            depends_on: ['task-write-10'],
            result_ref: 'stage_summaries/第1-10章-剧情总结.md',
            metadata: {
              result_kind: 'stage_summary',
              summary_range: [1, 10],
              summary_path: 'stage_summaries/第1-10章-剧情总结.md'
            },
            inputs: {}
          },
          {
            task_id: 'task-write-2',
            title: '第二章正文',
            task_type: 'write_chapter',
            status: 'pending',
            candidate_agents: ['ChapterWriter'],
            assigned_agent: '',
            retry_count: 0,
            depends_on: ['task-outline'],
            metadata: {},
            inputs: { chapter_number: 2 }
          }
        ],
        metadata: {
          contract_id: 'contract-3',
          source: 'contract_confirmation'
        }
      },
      collab_execution_trace: {
        status: 'running',
        events: [
          {
            type: 'contract_confirmation',
            title: '合同已确认',
            status: 'completed',
            timestamp: '2026-03-27T03:50:00Z'
          },
          {
            type: 'task_started',
            title: '生成世界观',
            task_type: 'build_world',
            agent: 'Worldbuilder',
            status: 'running',
            timestamp: '2026-03-27T03:55:00Z'
          },
          {
            type: 'task_completed',
            title: '阶段总结',
            task_type: 'summary_orchestrate',
            agent: 'SummaryOrchestrator',
            status: 'completed',
            timestamp: '2026-03-27T04:00:00Z'
          },
          {
            type: 'project_ready_execution_cycle',
            status: 'completed',
            timestamp: '2026-03-27T04:05:00Z'
          }
        ]
      },
      creation_contract: {
        contract_id: 'contract-3',
        user_confirmed: true
      },
      project_ready_execution: {
        stop_reason: 'max_chapter_tasks_reached',
        stopped_on_task_type: 'write_chapter',
        chapter_tasks_executed: 2,
        executed_task_count: 4,
        max_tasks: 4,
        max_chapter_tasks: 2,
        updated_at: '2026-03-27T07:00:00Z'
      }
    };
    window.apiCall.mockResolvedValueOnce(runtimeSnapshot);

    await window.openCollabTaskPoolWorkspace();

    expect(window.apiCall).toHaveBeenCalledWith('/api/v1/status', 'GET');
    expect(window.multiAgentWriteState.activeView).toBe('status');
    expect(document.getElementById('main-view')?.textContent).toContain('创作进度');
    expect(document.getElementById('main-view')?.textContent).toContain('生成世界观');
    expect(document.getElementById('main-view')?.textContent).toContain('生成大纲');
    expect(document.getElementById('main-view')?.textContent).toContain('第一章正文');
    expect(document.getElementById('main-view')?.textContent).toContain('阶段总结');
    expect(document.getElementById('main-view')?.textContent).toContain('当前卡在哪');
    expect(document.getElementById('main-view')?.textContent).toContain('这一轮连续写章先跑满了');
    expect(document.getElementById('main-view')?.textContent).toContain('下一步建议');
    expect(document.getElementById('main-view')?.textContent).toContain('第二章正文');
    expect(document.getElementById('main-view')?.textContent).toContain('进度筛选');
    expect(document.getElementById('main-view')?.textContent).toContain('全部阶段');
    expect(document.getElementById('main-view')?.textContent).toContain('全部事件');
    expect(document.getElementById('main-view')?.textContent).toContain('合同/初始化');
    expect(document.getElementById('main-view')?.textContent).toContain('项目调度');
    expect(document.getElementById('main-view')?.textContent).toContain('各执行助手最近产出');
    expect(document.getElementById('main-view')?.textContent).toContain('世界观构建师');
    expect(document.getElementById('main-view')?.textContent).toContain('产物位置：worldbuilding.json');
    expect(document.getElementById('main-view')?.textContent).toContain('最近匹配');
    expect(document.querySelector('#collab-execution-filter-breadcrumbs')?.textContent).toContain('当前筛选');
    expect(document.querySelector('#collab-execution-filter-breadcrumbs')?.textContent).toContain('全部阶段');
    expect(document.querySelector('#collab-execution-filter-breadcrumbs')?.textContent).toContain('全部事件');
    expect(document.getElementById('main-view')?.textContent).toContain('最近匹配');

    let stageFilter = document.getElementById('collab-trace-stage-filter');
    let typeFilter = document.getElementById('collab-trace-type-filter');
    expect(stageFilter).not.toBeNull();
    expect(typeFilter).not.toBeNull();

    stageFilter.value = 'summary_orchestrate';
    stageFilter.dispatchEvent(new Event('change', { bubbles: true }));
    await flushMicrotasks();

    let traceItems = Array.from(document.querySelectorAll('.collab-trace-item'));
    expect(traceItems.length).toBe(1);
    expect(traceItems[0]?.textContent).toContain('阶段总结');
    expect(traceItems[0]?.textContent).not.toContain('生成世界观');
    expect(traceItems[0]?.classList.contains('is-latest-match')).toBe(true);
    expect(document.getElementById('main-view')?.textContent).toContain('原始事件数：4');
    expect(document.getElementById('main-view')?.textContent).toContain('当前匹配数：1');
    expect(document.querySelector('#collab-execution-timeline-stats')?.textContent).toContain('阶段总结');
    expect(document.querySelector('#collab-execution-timeline-stats')?.textContent).toContain('任务完成');
    expect(document.querySelector('#collab-execution-latest-match')?.textContent).toContain('阶段总结');
    expect(document.querySelector('#collab-execution-filter-breadcrumbs')?.textContent).toContain('当前筛选');
    expect(document.querySelector('#collab-execution-filter-breadcrumbs')?.textContent).toContain('阶段');
    expect(document.querySelector('#collab-execution-filter-breadcrumbs')?.textContent).toContain('阶段总结');
    expect(document.querySelector('#collab-execution-filter-breadcrumbs')?.textContent).toContain('事件');
    expect(document.querySelector('#collab-execution-filter-breadcrumbs')?.textContent).toContain('全部事件');

    const expandButton = document.querySelector('.collab-trace-expand-btn');
    expect(expandButton).not.toBeNull();
    expect(document.querySelector('.collab-trace-item-details')).toBeNull();

    expandButton?.dispatchEvent(new MouseEvent('click', { bubbles: true }));
    await flushMicrotasks();

    expect(document.querySelector('.collab-trace-item-details')?.textContent).toContain('事件详情');
    expect(document.querySelector('.collab-trace-item-details')?.textContent).toContain('summary_orchestrate');
    expect(window.multiAgentWriteState.collabTraceExpandedEventIds.length).toBe(1);

    document.querySelector('.collab-trace-expand-btn')?.dispatchEvent(new MouseEvent('click', { bubbles: true }));
    await flushMicrotasks();

    expect(document.querySelector('.collab-trace-item-details')).toBeNull();
    expect(window.multiAgentWriteState.collabTraceExpandedEventIds).toEqual([]);

    stageFilter.value = 'all';
    stageFilter.dispatchEvent(new Event('change', { bubbles: true }));
    typeFilter.value = 'project_ready_execution_cycle';
    typeFilter.dispatchEvent(new Event('change', { bubbles: true }));
    await flushMicrotasks();

    traceItems = Array.from(document.querySelectorAll('.collab-trace-item'));
    expect(traceItems.length).toBe(1);
    expect(traceItems[0]?.textContent).toContain('项目调度批次');

    stageFilter.value = 'summary_orchestrate';
    stageFilter.dispatchEvent(new Event('change', { bubbles: true }));
    await flushMicrotasks();

    expect(document.getElementById('main-view')?.textContent).toContain('当前筛选条件下没有匹配事件');
    expect(document.querySelector('#collab-execution-latest-match')?.textContent).toContain('暂无最近匹配事件');

    stageFilter.value = 'all';
    typeFilter.value = 'all';
    stageFilter.dispatchEvent(new Event('change', { bubbles: true }));
    typeFilter.dispatchEvent(new Event('change', { bubbles: true }));
    await flushMicrotasks();

    document.querySelector('.collab-trace-expand-btn')?.dispatchEvent(new MouseEvent('click', { bubbles: true }));
    await flushMicrotasks();
    expect(window.multiAgentWriteState.collabTraceExpandedEventIds.length).toBe(1);

    stageFilter.value = 'project_dispatch';
    stageFilter.dispatchEvent(new Event('change', { bubbles: true }));
    await flushMicrotasks();
    expect(window.multiAgentWriteState.collabTraceFilters).toEqual({
      stage: 'project_dispatch',
      type: 'all'
    });

    let templateNameInput = document.getElementById('collab-trace-template-name');
    let templateSaveButton = document.getElementById('collab-trace-template-save-btn');
    expect(templateNameInput).not.toBeNull();
    expect(templateSaveButton).not.toBeNull();

    templateNameInput.value = '项目调度模板';
    templateSaveButton?.dispatchEvent(new MouseEvent('click', { bubbles: true }));
    await flushMicrotasks();

    stageFilter = document.getElementById('collab-trace-stage-filter');
    typeFilter = document.getElementById('collab-trace-type-filter');
    templateNameInput = document.getElementById('collab-trace-template-name');
    templateSaveButton = document.getElementById('collab-trace-template-save-btn');

    stageFilter.value = 'summary_orchestrate';
    stageFilter.dispatchEvent(new Event('change', { bubbles: true }));
    await flushMicrotasks();
    templateNameInput = document.getElementById('collab-trace-template-name');
    templateSaveButton = document.getElementById('collab-trace-template-save-btn');
    templateNameInput.value = '阶段总结模板';
    templateSaveButton?.dispatchEvent(new MouseEvent('click', { bubbles: true }));
    await flushMicrotasks();

    expect(document.getElementById('main-view')?.textContent).toContain('项目调度模板');
    expect(document.getElementById('main-view')?.textContent).toContain('阶段总结模板');
    expect(localStorage.getItem('collab_trace_named_filters')).toContain('项目调度模板');
    expect(localStorage.getItem('collab_trace_named_filters')).toContain('阶段总结模板');
    expect(document.querySelectorAll('.collab-trace-template-card').length).toBe(2);

    const projectTemplateCardBeforeRename = Array.from(document.querySelectorAll('.collab-trace-template-card')).find((card) =>
      card.querySelector('.collab-trace-template-name')?.textContent?.includes('项目调度模板')
    );
    expect(projectTemplateCardBeforeRename).not.toBeUndefined();

    window.prompt = vi.fn(() => '项目调度模板-已重命名');
    projectTemplateCardBeforeRename?.querySelector('.collab-trace-template-rename-btn')?.dispatchEvent(new MouseEvent('click', { bubbles: true }));
    await flushMicrotasks();

    expect(document.getElementById('main-view')?.textContent).toContain('项目调度模板-已重命名');
    expect(localStorage.getItem('collab_trace_named_filters')).toContain('项目调度模板-已重命名');

    const templateNamesBeforeMove = Array.from(document.querySelectorAll('.collab-trace-template-name')).map((node) => node.textContent?.trim());
    expect(templateNamesBeforeMove).toContain('阶段总结模板');
    expect(templateNamesBeforeMove).toContain('项目调度模板-已重命名');

    const templateNamesInitialOrder = Array.from(document.querySelectorAll('.collab-trace-template-name')).map((node) => node.textContent?.trim());
    const renamedTemplateInitialIndex = templateNamesInitialOrder.findIndex((name) => name?.includes('项目调度模板-已重命名'));
    expect(renamedTemplateInitialIndex).toBeGreaterThanOrEqual(0);

    const renamedTemplateCard = Array.from(document.querySelectorAll('.collab-trace-template-card')).find((card) =>
      card.querySelector('.collab-trace-template-name')?.textContent?.includes('项目调度模板-已重命名')
    );
    expect(renamedTemplateCard).not.toBeUndefined();

    const firstMoveSelector = renamedTemplateInitialIndex === 0
      ? '.collab-trace-template-move-down-btn'
      : '.collab-trace-template-move-up-btn';
    renamedTemplateCard?.querySelector(firstMoveSelector)?.dispatchEvent(new MouseEvent('click', { bubbles: true }));
    await flushMicrotasks();

    const templateNamesAfterFirstMove = Array.from(document.querySelectorAll('.collab-trace-template-name')).map((node) => node.textContent?.trim());
    expect(templateNamesAfterFirstMove).not.toEqual(templateNamesInitialOrder);
    expect(templateNamesAfterFirstMove).toContain('阶段总结模板');
    expect(templateNamesAfterFirstMove).toContain('项目调度模板-已重命名');

    const renamedTemplateCardAfterFirstMove = Array.from(document.querySelectorAll('.collab-trace-template-card')).find((card) =>
      card.querySelector('.collab-trace-template-name')?.textContent?.includes('项目调度模板-已重命名')
    );
    expect(renamedTemplateCardAfterFirstMove).not.toBeUndefined();

    const secondMoveSelector = renamedTemplateInitialIndex === 0
      ? '.collab-trace-template-move-up-btn'
      : '.collab-trace-template-move-down-btn';
    renamedTemplateCardAfterFirstMove?.querySelector(secondMoveSelector)?.dispatchEvent(new MouseEvent('click', { bubbles: true }));
    await flushMicrotasks();

    const templateNamesAfterSecondMove = Array.from(document.querySelectorAll('.collab-trace-template-name')).map((node) => node.textContent?.trim());
    expect(templateNamesAfterSecondMove).toEqual(templateNamesInitialOrder);

    stageFilter.value = 'all';
    stageFilter.dispatchEvent(new Event('change', { bubbles: true }));
    await flushMicrotasks();

    const renamedTemplateCardAfterMoveUp = Array.from(document.querySelectorAll('.collab-trace-template-card')).find((card) =>
      card.querySelector('.collab-trace-template-name')?.textContent?.includes('项目调度模板-已重命名')
    );
    expect(renamedTemplateCardAfterMoveUp).not.toBeUndefined();

    renamedTemplateCardAfterMoveUp?.querySelector('.collab-trace-template-apply-btn')?.dispatchEvent(new MouseEvent('click', { bubbles: true }));
    await flushMicrotasks();

    expect(document.getElementById('collab-trace-stage-filter')?.value).toBe('project_dispatch');
    expect(document.querySelector('#collab-execution-filter-breadcrumbs')?.textContent).toContain('项目调度');

    renamedTemplateCardAfterMoveUp?.querySelector('.collab-trace-template-delete-btn')?.dispatchEvent(new MouseEvent('click', { bubbles: true }));
    await flushMicrotasks();

    expect(document.getElementById('main-view')?.textContent).not.toContain('项目调度模板-已重命名');
    expect(document.getElementById('main-view')?.textContent).toContain('阶段总结模板');

    window.renderCollabTaskPoolWorkspace(
      runtimeSnapshot.task_pool,
      runtimeSnapshot.collab_execution_trace,
      runtimeSnapshot.project_ready_execution
    );
    await flushMicrotasks();

    const persistedStageFilter = document.getElementById('collab-trace-stage-filter');
    expect(persistedStageFilter?.value).toBe('project_dispatch');
    expect(document.querySelector('#collab-execution-latest-match')?.textContent).toContain('项目调度批次');

    stageFilter.value = 'all';
    typeFilter.value = 'all';
    persistedStageFilter?.dispatchEvent(new Event('change', { bubbles: true }));
    document.getElementById('collab-trace-type-filter')?.dispatchEvent(new Event('change', { bubbles: true }));
    await flushMicrotasks();

    const previewButtons = Array.from(document.querySelectorAll('.collab-task-result-preview-btn'));
    expect(previewButtons.length).toBe(4);

    previewButtons[0]?.dispatchEvent(new MouseEvent('click', { bubbles: true }));
    previewButtons[1]?.dispatchEvent(new MouseEvent('click', { bubbles: true }));
    previewButtons[2]?.dispatchEvent(new MouseEvent('click', { bubbles: true }));
    previewButtons[3]?.dispatchEvent(new MouseEvent('click', { bubbles: true }));
    await flushMicrotasks();

    expect(window.previewCollabResultFile).toHaveBeenNthCalledWith(1, 'worldbuilding.json');
    expect(window.previewCollabResultFile).toHaveBeenNthCalledWith(2, 'outline.json');
    expect(window.previewCollabResultFile).toHaveBeenNthCalledWith(3, 'chapters/001-第一章.md');
    expect(window.previewCollabResultFile).toHaveBeenNthCalledWith(4, 'stage_summaries/第1-10章-剧情总结.md');

    const detailButtons = Array.from(document.querySelectorAll('.collab-task-detail-btn'));
    expect(detailButtons.length).toBe(5);

    detailButtons[0]?.dispatchEvent(new MouseEvent('click', { bubbles: true }));
    await flushMicrotasks();

    expect(document.getElementById('modal-container')?.textContent).toContain('生成世界观');
    expect(document.getElementById('modal-container')?.textContent).toContain('这一步要做什么');
    expect(document.getElementById('modal-container')?.textContent).toContain('现在由谁来做');
    expect(document.getElementById('modal-container')?.textContent).toContain('这一步刚产出了什么');

    window.stopNovelCollabRuntimePolling();
    window.store.collabRuntimePollingTimer = null;
  });

  it('polls runtime status and re-renders task-pool workspace while task-pool view is active', async () => {
    vi.useFakeTimers();

    Object.defineProperty(document, 'hidden', {
      configurable: true,
      get: () => false
    });

    window.store.currentModule = 'write';
    window.multiAgentWriteState.activeView = 'task-pool';
    window.renderCollabTaskPoolWorkspace = vi.fn();

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
        return {
          workflow_state: 'writing',
          checkpoint: { current_chapter: 3 },
          project: { total_chapters: 12, completed_chapters: 2 },
          task_pool: {
            tasks: [{ title: '章节写作', status: 'running', candidate_agents: ['ChapterWriter'] }],
            metadata: { contract_id: 'contract-4' }
          },
          collab_execution_trace: {
            status: 'running',
            events: [{ type: 'task_started', title: '章节写作' }]
          },
          creation_contract: {
            contract_id: 'contract-4',
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
        metadata: expect.objectContaining({ contract_id: 'contract-4' })
      }),
      expect.objectContaining({
        status: 'running'
      }),
      null
    );

    window.stopNovelCollabRuntimePolling();
    vi.useRealTimers();
  });
});
