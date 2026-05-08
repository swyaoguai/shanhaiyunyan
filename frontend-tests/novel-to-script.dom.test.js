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

function createShell() {
  document.body.innerHTML = `
    <div id="nav-list-container"></div>
    <div id="main-view"></div>
  `;

  window.ui = {
    workspace: document.getElementById('main-view')
  };
}

function resetNovelToScriptGlobals() {
  window.store = { currentProject: 'proj-script', currentProjectId: 'proj-script' };
  window.showToast = vi.fn();
  window.switchModule = vi.fn();
  window.loadSettingsTab = vi.fn();
  window.updateBreadcrumbs = vi.fn();
  window.navigator.clipboard = { writeText: vi.fn().mockResolvedValue(undefined) };
  window.apiCall = vi.fn(async (url) => {
    if (url === '/api/novel-to-script/state') {
      return { data: null };
    }
    if (url === '/api/novel-to-script/capabilities') {
      return {
        data: {
          defaults: {
            script_style: 'scene_block_webnovel_script',
            convert_mode: 'auto',
            scene_density: 'medium',
            dialogue_ratio: 'medium',
            keep_voice_style: true,
            human_name_strategy: 'keep_original'
          },
          options: {
            script_styles: [{ value: 'scene_block_webnovel_script', label: '网文场景台本' }],
            convert_modes: [
              { value: 'auto', label: '自动识别（推荐）' },
              { value: 'chapterwise', label: '按章节转换' }
            ],
            scene_densities: [{ value: 'medium', label: '中' }],
            dialogue_ratios: [{ value: 'medium', label: '中' }],
            human_name_strategies: [{ value: 'keep_original', label: '保留原名' }]
          },
          strategy: {
            single_pass_max_words: 15000,
            chapterwise_max_words: 80000,
            batch_target_words: 12000,
            chapter_split_words: 18000
          }
        }
      };
    }
    if (url === '/api/api-configs') {
      return {
        configs: [{ id: 'cfg-script', name: 'Script Config', models: ['model-script-1'] }],
        active_config_id: 'cfg-script'
      };
    }
    if (url === '/api/global-config') {
      return {
        model: 'global-model-script',
        is_configured: true
      };
    }
    throw new Error(`Unexpected URL: ${url}`);
  });
  window.apiFormCall = vi.fn();
}

beforeAll(() => {
  loadBrowserScript('novel_agent/web/static/app-utils.js');
  loadBrowserScript('novel_agent/web/static/novel-to-script/novel-to-script-state.js');
  loadBrowserScript('novel_agent/web/static/novel-to-script/novel-to-script-api.js');
  loadBrowserScript('novel_agent/web/static/novel-to-script/novel-to-script-render.js');
  loadBrowserScript('novel_agent/web/static/novel-to-script/novel-to-script-events.js');
  loadBrowserScript('novel_agent/web/static/app-novel-to-script.js');
});

beforeEach(() => {
  localStorage.clear();
  vi.restoreAllMocks();
  createShell();
  resetNovelToScriptGlobals();
});

describe('novel-to-script DOM regressions', () => {
  it('renders the workbench with import, convert, and disabled export actions before conversion', async () => {
    await window.renderNovelToScriptInterface();

    expect(document.getElementById('novel-to-script-source-text')).not.toBeNull();
    expect(document.getElementById('novel-to-script-import-trigger')).not.toBeNull();
    expect(document.getElementById('novel-to-script-convert')).not.toBeNull();
    expect(document.getElementById('novel-to-script-export-txt').disabled).toBe(true);
    expect(document.getElementById('novel-to-script-open-result').disabled).toBe(true);
    expect(document.body.textContent).toContain('自动识别');
  });

  it('renders the result view with scene navigation when persisted result exists', async () => {
    localStorage.setItem('novel_to_script_data_proj-script', JSON.stringify({
      sourceText: '测试小说正文',
      activeView: 'result',
      result: {
        formatted_text: '【场景一：古桥 - 夜】\n人物：江临\n环境：夜雾压桥。\n动作/旁白：江临停在桥心。',
        character_index: [{ name: '江临', description: '', scene_numbers: [1], scene_count: 1 }],
        scene_outline: [{ scene_number: 1, scene_label: '场景一', heading: '古桥 - 夜', beat_count: 1, characters_text: '江临' }],
        batch_summaries: [
          { batch_number: 1, title: '第1章 - 第2章', word_count: 12000, scene_count: 3, chapter_range: [1, 2] },
          { batch_number: 2, title: '第3章 - 第4章', word_count: 11800, scene_count: 2, chapter_range: [3, 4] }
        ],
        scenes: [
          {
            scene_label: '场景一',
            heading: '古桥 - 夜',
            characters_text: '江临',
            environment_text: '夜雾压桥。',
            beats: [{ type: 'action_narration', label: '动作/旁白', text: '江临停在桥心。' }]
          }
        ]
      }
    }));

    await window.renderNovelToScriptInterface();

    const backButton = document.getElementById('novel-to-script-back-workbench');
    expect(backButton).not.toBeNull();
    expect(backButton.classList.contains('app-back-button')).toBe(true);
    expect(document.querySelector('[data-scene-index="0"]')).not.toBeNull();
    expect(document.getElementById('novel-to-script-result-editor').value).toContain('【场景一：古桥 - 夜】');
    expect(document.body.textContent).toContain('批次摘要');
    expect(document.querySelector('[data-retry-batch="1"]')).not.toBeNull();
  });

  it('switches result tabs and keeps structured views available', async () => {
    localStorage.setItem('novel_to_script_data_proj-script', JSON.stringify({
      sourceText: '测试小说正文',
      activeView: 'result',
      resultTab: 'characters',
      result: {
        formatted_text: '【场景一：古桥 - 夜】\n人物：江临\n环境：夜雾压桥。\n动作/旁白：江临停在桥心。',
        character_index: [{ name: '江临', description: '主角', scene_numbers: [1], scene_count: 1 }],
        scene_outline: [{ scene_number: 1, scene_label: '场景一', heading: '古桥 - 夜', beat_count: 1, characters_text: '江临' }],
        scenes: [
          {
            scene_label: '场景一',
            heading: '古桥 - 夜',
            characters_text: '江临',
            environment_text: '夜雾压桥。',
            beats: [{ type: 'action_narration', label: '动作/旁白', text: '江临停在桥心。' }]
          }
        ]
      }
    }));

    await window.renderNovelToScriptInterface();

    const characterTab = document.querySelector('[data-result-tab="characters"]');
    characterTab.dispatchEvent(new Event('click', { bubbles: true }));
    await new Promise((resolve) => setTimeout(resolve, 0));
    const characterTitle = document.querySelector('.novel-to-script-info-title');
    expect(characterTitle).not.toBeNull();
    expect(characterTitle.textContent).toContain('江临');
    const sceneTab = document.querySelector('[data-result-tab="scenes"]');
    sceneTab.dispatchEvent(new Event('click', { bubbles: true }));
    await new Promise((resolve) => setTimeout(resolve, 0));
    const sceneCopy = document.querySelector('.novel-to-script-info-copy');
    expect(sceneCopy).not.toBeNull();
    expect(sceneCopy.textContent).toContain('古桥 - 夜');
  });
});
