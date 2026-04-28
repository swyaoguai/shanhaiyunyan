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

function resetContinuousWriteGlobals() {
  window.store = { currentProjectId: 'proj-test', currentProject: 'proj-test' };
  window.apiCall = vi.fn();
  window.showToast = vi.fn();
  window.renderTrendsPanel = vi.fn();
  window.loadTrendsConfig = vi.fn().mockResolvedValue(undefined);
  window.checkTrendsService = vi.fn().mockResolvedValue(undefined);
  window.makeElementActivatable = vi.fn();
  window.confirmLeaveInfiniteWriteEditor = vi.fn(() => true);
}

beforeAll(() => {
  loadBrowserScript('novel_agent/web/static/app-utils.js');
  loadBrowserScript('novel_agent/web/static/continuous_write.js');
});

beforeEach(() => {
  document.body.innerHTML = '';
  localStorage.clear();
  vi.restoreAllMocks();
  resetContinuousWriteGlobals();
});

describe('continuous-write DOM regressions', () => {
  it('renders the global model as fallback when the selected config has no models', async () => {
    window.apiCall.mockImplementation(async (url) => {
      if (url === '/api/api-configs') {
        return {
          configs: [
            { id: 'cfg-empty', name: 'Empty Config', api_base: 'https://example.com/v1', models: [] }
          ],
          active_config_id: 'cfg-empty',
          active_model: ''
        };
      }

      if (url === '/api/global-config') {
        return {
          model: 'global-model-x',
          is_configured: true,
          api_base: 'https://example.com/v1'
        };
      }

      throw new Error(`Unexpected URL: ${url}`);
    });

    await window.loadGlobalApiConfigForInfiniteWrite();

    const html = window.renderInfiniteWriteModelOptions('cfg-empty', '');

    expect(html).toContain('global-model-x');
    expect(html).toContain('全局模型');
    expect(html).not.toContain('请先在该配置中添加模型');
  });

  it('switching API config keeps the model select usable via global fallback', async () => {
    window.apiCall.mockImplementation(async (url) => {
      if (url === '/api/api-configs') {
        return {
          configs: [
            { id: 'cfg-a', name: 'Config A', api_base: 'https://example.com/v1', models: [] },
            { id: 'cfg-b', name: 'Config B', api_base: 'https://example.org/v1', models: ['model-b1'] }
          ],
          active_config_id: 'cfg-a',
          active_model: ''
        };
      }

      if (url === '/api/global-config') {
        return {
          model: 'global-model-y',
          is_configured: true,
          api_base: 'https://example.com/v1'
        };
      }

      throw new Error(`Unexpected URL: ${url}`);
    });

    await window.loadGlobalApiConfigForInfiniteWrite();

    document.body.innerHTML = `
      <select id="iw-api-config-select">
        <option value="cfg-a" selected>cfg-a</option>
        <option value="cfg-b">cfg-b</option>
      </select>
      <select id="iw-model-input">${window.renderInfiniteWriteModelOptions('cfg-a', '')}</select>
    `;

    window.bindInfiniteWriteEvents();

    const apiSelect = document.getElementById('iw-api-config-select');
    const modelSelect = document.getElementById('iw-model-input');

    apiSelect.value = 'cfg-a';
    apiSelect.dispatchEvent(new Event('change', { bubbles: true }));

    expect(Array.from(modelSelect.options).map((option) => option.value)).toEqual(['global-model-y']);
    expect(modelSelect.options[0].textContent).toContain('全局模型');
    expect(window.getSelectedModelForInfiniteWrite()).toBe('global-model-y');
  });

  it('falls back to the active config when a saved API config id is no longer valid', async () => {
    localStorage.setItem('infinite_write_data_proj-test', JSON.stringify({
      selectedApiConfigId: 'cfg-missing',
      selectedModel: 'global-model-z'
    }));

    window.apiCall.mockImplementation(async (url) => {
      if (url === '/api/api-configs') {
        return {
          configs: [
            { id: 'cfg-valid', name: 'Valid Config', api_base: 'https://example.com/v1', models: ['model-a1', 'model-a2'] }
          ],
          active_config_id: 'cfg-valid',
          active_model: 'global-model-z'
        };
      }

      if (url === '/api/global-config') {
        return {
          model: 'global-model-z',
          is_configured: true,
          api_base: 'https://example.com/v1'
        };
      }

      throw new Error(`Unexpected URL: ${url}`);
    });

    document.body.innerHTML = '<div id="main-view"></div>';

    await window.renderInfiniteWriteInterface();

    const apiSelect = document.getElementById('iw-api-config-select');
    const modelSelect = document.getElementById('iw-model-input');

    expect(apiSelect.value).toBe('cfg-valid');
    expect(Array.from(modelSelect.options).map((option) => option.value)).toEqual(['model-a1', 'model-a2']);
    expect(Array.from(modelSelect.options).map((option) => option.textContent)).not.toContain('global-model-z（全局模型）');
    expect(window.getSelectedApiConfigIdForInfiniteWrite()).toBe('cfg-valid');
    expect(window.getSelectedModelForInfiniteWrite()).toBe('model-a1');
  });

  it('renders visible character anchors from the continuation context', async () => {
    localStorage.setItem('infinite_write_data_proj-test', JSON.stringify({
      sessionId: 'sess-1',
      chapters: [
        { chapter_number: 1, title: '雨夜', content: '第一章正文', word_count: 1200 }
      ],
      currentChapter: 1,
      totalWords: 1200
    }));

    window.apiCall.mockImplementation(async (url) => {
      if (url === '/api/api-configs') {
        return { configs: [], active_config_id: '', active_model: '' };
      }
      if (url === '/api/global-config') {
        return { model: '', is_configured: false, api_base: '' };
      }
      if (url === '/api/continuous-write/session/sess-1/context') {
        return {
          success: true,
          context: {
            context_summary: '[角色状态]\n周岚；最近出现在第1章；状态：警惕',
            character_states: {
              '周岚': {
                name: '周岚',
                status: '警惕',
                location: '旧城',
                last_chapter: 1,
                notes: ['周岚站在旧城桥头，怀疑顾原另有隐情。']
              }
            }
          }
        };
      }
      throw new Error(`Unexpected URL: ${url}`);
    });

    document.body.innerHTML = '<div id="main-view"></div>';

    await window.renderInfiniteWriteInterface();

    expect(document.body.textContent).toContain('人物和设定锚点');
    expect(document.body.textContent).toContain('周岚');
    expect(document.body.textContent).toContain('当前状态：警惕');
    expect(document.body.textContent).toContain('当前位置：旧城');
    expect(document.body.textContent).toContain('最近表现：周岚站在旧城桥头');
  });

  it('toggles the nearby memory preview drawer from the continue controls', async () => {
    localStorage.setItem('infinite_write_data_proj-test', JSON.stringify({
      sessionId: 'sess-2',
      chapters: [
        { chapter_number: 1, title: '雨夜', content: '第一章正文', word_count: 1200 }
      ],
      currentChapter: 1,
      totalWords: 1200
    }));

    window.apiCall.mockImplementation(async (url) => {
      if (url === '/api/api-configs') {
        return { configs: [], active_config_id: '', active_model: '' };
      }
      if (url === '/api/global-config') {
        return { model: '', is_configured: false, api_base: '' };
      }
      if (url === '/api/continuous-write/session/sess-2/context') {
        return {
          success: true,
          context: {
            context_summary: '[角色状态]\n周岚；最近出现在第1章；状态：警惕',
            character_states: {
              '周岚': {
                name: '周岚',
                status: '警惕',
                location: '旧城',
                last_chapter: 1,
                notes: ['周岚站在旧城桥头，怀疑顾原另有隐情。']
              }
            }
          }
        };
      }
      throw new Error(`Unexpected URL: ${url}`);
    });

    document.body.innerHTML = '<div id="main-view"></div>';

    await window.renderInfiniteWriteInterface();

    const toggleBtn = document.getElementById('iw-memory-preview-toggle');
    const panel = document.getElementById('iw-memory-preview-panel');

    expect(toggleBtn?.textContent).toContain('先看系统记忆');
    expect(panel?.style.display).toBe('none');

    toggleBtn.click();

    expect(toggleBtn?.textContent).toContain('收起系统记忆');
    expect(panel?.style.display).toBe('');
    expect(document.body.textContent).toContain('人物和设定锚点');
  });
});
