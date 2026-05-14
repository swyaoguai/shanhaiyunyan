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

function resetGlobals() {
  window.apiCall = vi.fn();
  window.showToast = vi.fn();
  window.loadProjects = vi.fn().mockResolvedValue(undefined);
  window.loadCurrentProjectData = vi.fn().mockResolvedValue(undefined);
  window.renderNavPanel = vi.fn();
  window.renderMultiAgentWriteNavPanel = vi.fn();
  window.loadSavedSettings = vi.fn().mockResolvedValue(undefined);
  window.restoreSidebarState = vi.fn();
  window.checkGlobalAPIConfig = vi.fn().mockResolvedValue(undefined);
  window.switchModule = vi.fn();
  window.loadKnowledgeCategories = vi.fn();
  window.openChapterEditor = vi.fn();
}

beforeAll(() => {
  loadBrowserScript('novel_agent/web/static/app-utils.js');
  loadBrowserScript('novel_agent/web/static/app-core.js');
  loadBrowserScript('novel_agent/web/static/app-copilot.js');
});

beforeEach(() => {
  document.body.innerHTML = `
    <div id="copilot-messages"></div>
    <div id="copilot-workflow-panel" class="hidden"></div>
    <div id="modal-container" class="hidden"></div>
    <span id="copilot-session-mode"></span>
    <span id="copilot-session-agent"></span>
    <button id="copilot-session-list-btn"></button>
    <div id="copilot-session-menu" class="hidden"></div>
    <div class="copilot-input">
      <div id="mention-popup" class="mention-popup hidden"></div>
      <div class="copilot-input-wrapper">
        <textarea id="copilot-input-text"></textarea>
        <button id="copilot-send-btn"></button>
      </div>
    </div>
  `;
  localStorage.clear();
  vi.restoreAllMocks();
  resetGlobals();
  window.initUIReferences();
  window.store.projectData = {
    characters: [],
    outline: [],
    worldbuilding: [],
    items: [],
    eventlines: [],
    outline_settings: [],
    detail_settings: [],
    chapter_settings: [],
    custom_knowledge: []
  };
  window.store.currentProjectId = '';
  window.store.copilotCreativeMode = 'auto';
  window.store.copilotAutoSave = { enabled: false, loaded: false, projectId: null };
  window.initCopilotEnhancements();
});

describe('copilot slash command prompts', () => {
  it('keeps auto-save rate-limit failures quiet and retries the preference save', async () => {
    vi.useFakeTimers();
    const rateLimitError = new Error('HTTP 429: 请求过于频繁');
    rateLimitError.status = 429;
    rateLimitError.retryAfter = 12;
    window.apiCall
      .mockRejectedValueOnce(rateLimitError)
      .mockResolvedValueOnce({ success: true });
    window.store.currentProjectId = 'project-1';

    await window.saveCopilotAutoSavePreference(true);
    await Promise.resolve();
    await Promise.resolve();

    expect(window.apiCall).toHaveBeenCalledTimes(1);
    expect(window.showToast).not.toHaveBeenCalled();
    expect(window.store.copilotAutoSave.enabled).toBe(true);
    expect(localStorage.getItem('copilot_chat_auto_save_enabled:project-1')).toBe('true');

    await vi.advanceTimersByTimeAsync(12000);

    expect(window.apiCall).toHaveBeenCalledTimes(2);
    expect(window.apiCall).toHaveBeenLastCalledWith('/api/project-state/copilot_chat_auto_save', 'POST', {
      data: { enabled: true }
    });
    expect(window.showToast).not.toHaveBeenCalled();
    vi.useRealTimers();
  });

  it('renders the auto-save preference in the Copilot input area', () => {
    expect(document.querySelector('.copilot-auto-save-row')).not.toBeNull();
    expect(document.getElementById('copilot-auto-save-toggle')).not.toBeNull();
    expect(document.getElementById('copilot-auto-save-status')?.textContent).toBe('未选择项目');

    window.store.currentProjectId = 'project-1';
    window.store.copilotAutoSave = { enabled: true, loaded: true, projectId: 'project-1' };
    window.renderCopilotAutoSaveToggle();

    expect(document.getElementById('copilot-auto-save-toggle')?.checked).toBe(true);
    expect(document.getElementById('copilot-auto-save-status')?.textContent).toBe('已开启');
  });

  it('restores auto-save from local memory when project state has no saved preference', async () => {
    localStorage.setItem('copilot_chat_auto_save_enabled:project-1', 'true');
    window.store.currentProjectId = 'project-1';
    window.store.copilotAutoSave = { enabled: false, loaded: false, projectId: null };
    window.apiCall
      .mockResolvedValueOnce({ success: true, data: null })
      .mockResolvedValueOnce({ success: true });

    await window.loadCopilotAutoSavePreference();

    expect(window.store.copilotAutoSave.enabled).toBe(true);
    expect(document.getElementById('copilot-auto-save-toggle')?.checked).toBe(true);
    expect(document.getElementById('copilot-auto-save-status')?.textContent).toBe('已开启');
    expect(window.apiCall).toHaveBeenLastCalledWith('/api/project-state/copilot_chat_auto_save', 'POST', {
      data: { enabled: true }
    });
  });

  it('does not render a manual creative mode selector in the Copilot input area', () => {
    window.bindCopilotCreativeModeSelector();

    expect(document.querySelector('.copilot-creative-mode-row')).toBeNull();
    expect(document.getElementById('copilot-creative-mode-select')).toBeNull();
    expect(window.store.copilotCreativeMode).toBe('auto');
  });

  it('keeps command prompts hidden by default and reveals them only after slash input', () => {
    const input = document.getElementById('copilot-input-text');
    const promptBar = document.querySelector('.copilot-command-prompts');
    expect(promptBar?.classList.contains('hidden')).toBe(true);

    input.value = '/';
    input.setSelectionRange(1, 1);
    input.dispatchEvent(new Event('input', { bubbles: true }));

    expect(promptBar?.classList.contains('hidden')).toBe(false);
    expect(document.querySelectorAll('.mention-item').length).toBeLessThanOrEqual(3);
    const commandLinks = Array.from(document.querySelectorAll('.copilot-command-text'));
    expect(commandLinks.length).toBeGreaterThan(0);
    expect(commandLinks.some((item) => item.textContent?.includes('续写章节'))).toBe(true);
    commandLinks.find((item) => item.textContent?.includes('续写章节'))?.dispatchEvent(new MouseEvent('click', { bubbles: true }));

    expect(input?.value).toBe('/chapter 1 ');
    expect(input?.selectionStart).toBe('/chapter '.length);
    expect(input?.selectionEnd).toBe('/chapter 1'.length);
  });

  it('shows slash autocomplete results and renders plain-text helper for the active command', () => {
    const input = document.getElementById('copilot-input-text');
    input.value = '/wo';
    input.setSelectionRange(3, 3);
    input.dispatchEvent(new Event('input', { bubbles: true }));

    const popup = document.getElementById('mention-popup');
    expect(popup?.classList.contains('hidden')).toBe(false);
    expect(popup?.textContent).toContain('生成世界观');
    expect(popup?.textContent).toContain('世界观');
    expect(popup?.textContent).not.toContain('/worldbuild');

    const helper = document.querySelector('.copilot-command-helper');
    expect(document.querySelector('.copilot-command-prompts')?.classList.contains('hidden')).toBe(false);
    expect(helper?.classList.contains('hidden')).toBe(false);
    expect(helper?.textContent).toContain('生成世界观');
    expect(helper?.textContent).not.toContain('/worldbuild');
    expect(helper?.textContent).not.toContain('快速填写');
  });

  it('offers chapter commands, accepts keyboard selection, and shows parameter guidance', () => {
    window.store.projectData.chapters = [
      { title: '雾港来信' },
      { title: '铁雨将至' }
    ];
    window.updateMentionData();

    const input = document.getElementById('copilot-input-text');
    input.value = '/ch';
    input.setSelectionRange(3, 3);
    input.dispatchEvent(new Event('input', { bubbles: true }));

    const popup = document.getElementById('mention-popup');
    expect(popup?.textContent).toContain('续写第1章');
    expect(document.querySelector('.copilot-command-helper')?.textContent).toContain('参数：章节号');

    input.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true }));
    expect(input.value).toBe('/chapter 1 ');
    expect(input.selectionStart).toBe('/chapter '.length);
    expect(input.selectionEnd).toBe('/chapter 1'.length);
    expect(popup?.classList.contains('hidden')).toBe(true);
  });

  it('confirms creation contract and appends task pool summary card', async () => {
    window.apiCall.mockResolvedValueOnce({
      creation_contract: {
        contract_id: 'contract-2',
        user_confirmed: true,
        scope: { novel_type: '玄幻' }
      },
      task_pool: {
        tasks: [
          { title: '上下文规划', status: 'pending', candidate_agents: ['ContextStrategy'] }
        ],
        metadata: {
          contract_id: 'contract-2',
          source: 'contract_confirmation'
        }
      }
    });

    const html = window.renderCreationContractCard({
      contract_id: 'contract-2',
      user_confirmed: false,
      scope: { novel_type: '玄幻' },
      constraints: {},
      deliverables: [],
      task_graph: []
    });
    window.appendMessage(html, 'ai');

    const button = document.querySelector('.copilot-contract-confirm-btn');
    expect(button).not.toBeNull();

    button.dispatchEvent(new MouseEvent('click', { bubbles: true }));
    for (let i = 0; i < 6; i += 1) {
      await Promise.resolve();
    }

    expect(window.apiCall).toHaveBeenCalledWith('/api/v1/contract/confirm', 'POST', expect.objectContaining({
      contract_id: 'contract-2',
      approved: true
    }));
    expect(window.loadCurrentProjectData).toHaveBeenCalled();
    expect(window.renderNavPanel).toHaveBeenCalled();
    expect(window.store.currentTaskPool?.metadata?.contract_id).toBe('contract-2');
    expect(document.body.textContent).toContain('任务池摘要');
  });

  it('resumes instead of re-confirming an already confirmed creation contract', async () => {
    window.apiCall.mockResolvedValueOnce({
      creation_contract: {
        contract_id: 'contract-confirmed',
        user_confirmed: true,
        scope: { novel_type: '玄幻' }
      },
      task_pool: {
        tasks: [
          { title: '生成世界观', status: 'completed', candidate_agents: ['Worldbuilder'] },
          { title: '创作第1章', status: 'completed', candidate_agents: ['ChapterWriter'] }
        ],
        metadata: {
          contract_id: 'contract-confirmed',
          source: 'contract_confirmation'
        }
      },
      project_ready_execution: {
        executed_task_count: 1,
        stop_reason: ''
      }
    });

    const html = window.renderCreationContractCard({
      contract_id: 'contract-confirmed',
      user_confirmed: true,
      scope: { novel_type: '玄幻' },
      constraints: {},
      deliverables: [],
      task_graph: []
    });
    window.appendMessage(html, 'ai');

    const button = document.querySelector('.copilot-contract-confirm-btn');
    expect(button?.textContent).toContain('继续执行任务池');

    button.dispatchEvent(new MouseEvent('click', { bubbles: true }));
    for (let i = 0; i < 6; i += 1) {
      await Promise.resolve();
    }

    expect(window.apiCall).toHaveBeenCalledTimes(1);
    expect(window.apiCall).toHaveBeenCalledWith('/api/v1/contract/resume', 'POST', expect.objectContaining({
      session_id: 'copilot',
      max_tasks: 7,
      max_chapter_tasks: 2,
      approve_chapter_settings: true
    }));
    expect(window.store.currentTaskPool?.metadata?.contract_id).toBe('contract-confirmed');
    expect(document.body.textContent).toContain('已继续执行任务池');
    expect(document.body.textContent).toContain('任务池摘要');
  });
});
