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

beforeAll(() => {
  loadBrowserScript('novel_agent/web/static/app-utils.js');
  loadBrowserScript('novel_agent/web/static/app-core.js');
});

beforeEach(() => {
  document.body.innerHTML = `
    <span id="copilot-session-mode"></span>
    <span id="copilot-session-agent"></span>
    <select id="copilot-model-select"></select>
    <span id="copilot-model-status"></span>
  `;
  vi.restoreAllMocks();
  window.apiCall = vi.fn();
  window.showToast = vi.fn();
  window.initUIReferences();
  window.store.copilotModel = {
    configs: [],
    activeConfigId: '',
    activeModel: '',
    loading: false,
    applying: false
  };
});

describe('copilot model switcher', () => {
  it('renders configured models and selects the active model from settings', async () => {
    window.apiCall.mockResolvedValue({
      configs: [
        { id: 'cfg-a', name: 'DeepSeek', models: ['deepseek-v4', 'deepseek-r1'] },
        { id: 'cfg-b', name: 'Claude', models: ['claude-opus-4-6'] }
      ],
      active_config_id: 'cfg-a',
      active_model: 'deepseek-r1'
    });

    await window.loadCopilotModelOptions();

    const select = document.getElementById('copilot-model-select');
    expect(Array.from(select.options).map((option) => option.textContent)).toEqual([
      'DeepSeek / deepseek-v4',
      'DeepSeek / deepseek-r1',
      'Claude / claude-opus-4-6'
    ]);
    expect(select.selectedOptions[0].dataset.configId).toBe('cfg-a');
    expect(select.selectedOptions[0].dataset.model).toBe('deepseek-r1');
    expect(document.getElementById('copilot-session-mode')?.textContent).toBe('模型：deepseek-r1');
  });

  it('applies a selected model through the hot-update settings endpoint', async () => {
    const receivedEvents = [];
    window.addEventListener('global-api-config-updated', (event) => {
      receivedEvents.push(event.detail);
    });
    window.store.copilotModel.configs = [
      { id: 'cfg-a', name: 'DeepSeek', models: ['deepseek-v4'] },
      { id: 'cfg-b', name: 'Claude', models: ['claude-opus-4-6'] }
    ];
    window.store.copilotModel.activeConfigId = 'cfg-a';
    window.store.copilotModel.activeModel = 'deepseek-v4';
    window.renderCopilotModelSelector();
    window.apiCall.mockImplementation(async (url, method, payload) => {
      if (url === '/api/api-configs/active' && method === 'POST') {
        expect(payload).toEqual({ config_id: 'cfg-b', model: 'claude-opus-4-6' });
        return { success: true, active_config_id: 'cfg-b', active_model: 'claude-opus-4-6' };
      }
      if (url === '/api/api-configs') {
        return {
          configs: window.store.copilotModel.configs,
          active_config_id: 'cfg-b',
          active_model: 'claude-opus-4-6'
        };
      }
      throw new Error(`Unexpected URL: ${url}`);
    });

    await window.applyCopilotModelSelection('cfg-b', 'claude-opus-4-6');

    expect(document.getElementById('copilot-session-mode')?.textContent).toBe('模型：claude-opus-4-6');
    expect(document.getElementById('copilot-model-select')?.selectedOptions[0]?.dataset.configId).toBe('cfg-b');
    expect(document.getElementById('copilot-model-status')?.textContent).toBe('已切换');
    expect(window.showToast).toHaveBeenCalledWith('聊天模型已切换为 claude-opus-4-6', 'success');
    expect(receivedEvents).toContainEqual({ activeConfigId: 'cfg-b', activeModel: 'claude-opus-4-6' });
  });
});
