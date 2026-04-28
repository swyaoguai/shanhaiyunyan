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

function loadShortStoryStateHelpers() {
  const absolutePath = path.join(ROOT, 'novel_agent/web/static/short-story/short-story-state.js');
  const source = readFileSync(absolutePath, 'utf8');
  const factory = new Function('window', 'store', 'localStorage', 'apiCall', `${source}; return { parseShortStoryBlueprintsFromOutline, repairShortStoryWorkflowBlueprints };`);
  return factory({}, {}, { getItem: () => null, setItem: () => {}, removeItem: () => {} }, async () => ({ data: null }));
}

function resetSharedGlobals() {
  const shortStoryHelpers = loadShortStoryStateHelpers();
  window.ui = { workspace: document.body };
  window.store = { settings: {} };
  window.currentApiConfigs = [];
  window.currentActiveConfigId = '';
  window.currentActiveModel = '';
  window.editingConfigId = null;
  window.agentPageApiConfigs = [];
  window.agentPageActiveConfigId = '';

  window.bindThemeSettingsEvents = window.bindThemeSettingsEvents || vi.fn();
  window.bindAgentSettingsEvents = window.bindAgentSettingsEvents || vi.fn();
  window.bindKnowledgeBaseEvents = window.bindKnowledgeBaseEvents || vi.fn();
  window.bindRegexRuleEvents = window.bindRegexRuleEvents || vi.fn();
  window.bindSkillsSettingsEvents = window.bindSkillsSettingsEvents || vi.fn();

  window.shortStoryState = {
    apiConfigs: [],
    globalModel: '',
    selectedApiConfigId: '',
    activeConfigId: '',
    selectedModel: '',
    globalConfigured: false,
    workflow: null,
    synopsisRawOutput: '',
    outlineRawOutput: '',
    qualityReportDraft: '',
    qualityPassedDraft: false,
    qualitySimpleFixes: [],
    coherenceReportDraft: '',
    coherencePassedDraft: false,
    titleRawOutput: '',
    titleFeedback: '',
    synopsisFeedback: '',
    outlineRevisionFeedback: '',
    qualitySuggestedChapters: [],
    coherenceSuggestedChapters: [],
    partialChapterGeneration: null,
    collapsedSections: {},
    loadingAction: '',
    loadingStartedAt: 0,
    batchGenerationProgress: null,
    highlightSection: ''
  };
  window.isShortStorySectionCollapsed = vi.fn(() => false);

  window.bindShortStoryDraftAutosave = vi.fn();
  window.saveShortStoryData = vi.fn();
  window.persistShortStoryProjectStateNow = vi.fn().mockResolvedValue(undefined);
  window.hydrateShortStoryProjectState = vi.fn().mockResolvedValue(undefined);
  window.loadGlobalApiConfigForShortStory = vi.fn().mockResolvedValue(undefined);
  window.resetShortStoryReviewArtifacts = vi.fn(() => {
    window.shortStoryState.qualityReportDraft = '';
    window.shortStoryState.qualityPassedDraft = false;
    window.shortStoryState.qualitySimpleFixes = [];
    window.shortStoryState.coherenceReportDraft = '';
    window.shortStoryState.coherencePassedDraft = false;
    window.shortStoryState.titleRawOutput = '';
    window.shortStoryState.qualitySuggestedChapters = [];
    window.shortStoryState.coherenceSuggestedChapters = [];
  });
  window.switchModule = vi.fn();
  window.loadSettingsTab = vi.fn();
  window.updateBreadcrumbs = vi.fn();
  window.apiCall = vi.fn();
  window.showToast = vi.fn();
  window.parseShortStoryBlueprintsFromOutline = shortStoryHelpers.parseShortStoryBlueprintsFromOutline;
}

beforeAll(() => {
  loadBrowserScript('novel_agent/web/static/app-utils.js');
  loadBrowserScript('novel_agent/web/static/settings/app-settings-helpers.js');
  loadBrowserScript('novel_agent/web/static/settings/app-settings-renderers.js');
  loadBrowserScript('novel_agent/web/static/settings/app-settings-api.js');
  loadBrowserScript('novel_agent/web/static/settings/app-settings-events.js');
  loadBrowserScript('novel_agent/web/static/short-story/short-story-formatters.js');
  loadBrowserScript('novel_agent/web/static/short-story/short-story-api.js');
  loadBrowserScript('novel_agent/web/static/short-story/short-story-render.js');
  loadBrowserScript('novel_agent/web/static/short-story/short-story-events.js');
});

beforeEach(() => {
  document.body.innerHTML = '';
  vi.restoreAllMocks();
  resetSharedGlobals();
});

describe('settings DOM regressions', () => {
  it('uses semantic buttons for primary shell controls in the main template', () => {
    const html = readFileSync(path.join(ROOT, 'novel_agent/web/templates/index.html'), 'utf8');

    expect(html).toMatch(/<button type="button" class="res-item active" data-module="dashboard"/);
    expect(html).toContain('title="项目概览"');
    expect(html).toContain('aria-label="打开项目概览"');
    expect(html).toContain('title="多Agent创作"');
    expect(html).toContain('aria-label="打开多Agent创作"');
    const writePos = html.indexOf('data-module="write"');
    const infiniteWritePos = html.indexOf('data-module="infinite-write"');
    expect(writePos).toBeGreaterThan(-1);
    expect(infiniteWritePos).toBeGreaterThan(-1);
    expect(writePos).toBeLessThan(infiniteWritePos);
    expect(html).toMatch(/<button type="button" class="project-current" id="project-current"/);
    expect(html).toMatch(/<button type="button" class="icon-btn nav-action-btn" id="nav-action-add"/);
    expect(html).toMatch(/role="status" aria-live="polite"/);
  });

  it('renders API settings with invalid URLs without throwing', () => {
    window.currentActiveModel = 'stale-model';

    const render = () => window.renderGlobalApiSettingsView({
      configs: [
        {
          id: 'broken',
          name: 'Bad Config',
          api_base: '::::not-a-valid-url',
          models: ['demo-model'],
          api_key_set: false
        }
      ],
      activeConfig: {
        id: 'broken',
        name: 'Bad Config',
        api_base: '::::not-a-valid-url',
        models: ['demo-model']
      },
      activeConfigId: 'broken',
      activeModel: 'demo-model',
      hasConfigs: true,
      llmTimeouts: {},
      shortStoryTimeouts: {},
      llmRanges: {},
      shortStoryRange: { min: 30, max: 600 }
    });

    expect(render).not.toThrow();

    document.body.innerHTML = render();

    expect(document.querySelector('#active-config-select')).not.toBeNull();
    expect(document.body.textContent).toContain('::::not-a-valid-url');
    expect(document.querySelector('#active-model-select').value).toBe('demo-model');
  });

  it('renders colloquial test-result entry in API settings', () => {
    document.body.innerHTML = window.renderGlobalApiSettingsView({
      configs: [
        {
          id: 'cfg-1',
          name: '可用配置',
          api_base: 'https://api.example.com/v1',
          models: ['gpt-5.4'],
          api_key_set: true
        }
      ],
      activeConfig: {
        id: 'cfg-1',
        name: '可用配置',
        api_base: 'https://api.example.com/v1',
        models: ['gpt-5.4']
      },
      activeConfigId: 'cfg-1',
      activeModel: 'gpt-5.4',
      hasConfigs: true,
      llmTimeouts: {},
      shortStoryTimeouts: {},
      llmRanges: {},
      shortStoryRange: { min: 30, max: 600 }
    });

    expect(document.body.textContent).toContain('测试结果');
    expect(document.body.textContent).toContain('点一下上面的「测试连接」就行');
    expect(document.getElementById('test-active-config')?.textContent).toContain('测试连接');
    expect(document.querySelector('.settings-test-card--idle')).not.toBeNull();
  });

  it('calls test connection api and renders colloquial result copy', async () => {
    window.currentApiConfigs = [
      { id: 'cfg-1', name: '可用配置', api_base: 'https://api.example.com/v1', models: ['gpt-5.4'], api_key_set: true }
    ];
    window.eval(`currentApiConfigs = ${JSON.stringify(window.currentApiConfigs)};`);
    document.body.innerHTML = window.renderGlobalApiSettingsView({
      configs: window.currentApiConfigs,
      activeConfig: window.currentApiConfigs[0],
      activeConfigId: 'cfg-1',
      activeModel: 'gpt-5.4',
      hasConfigs: true,
      llmTimeouts: {},
      shortStoryTimeouts: {},
      llmRanges: {},
      shortStoryRange: { min: 30, max: 600 }
    });

    window.apiCall = vi.fn().mockResolvedValue({
      success: true,
      model_tested: 'gpt-5.4',
      response_time: 123,
      error_code: '',
      title: '可以正常用',
      solution: '这套配置已经通过测试，可以直接拿来创作。',
      detail: ''
    });
    window.showToast = vi.fn();

    window.bindGlobalAPISettingsEvents({});
    document.getElementById('test-active-config').dispatchEvent(new MouseEvent('click', { bubbles: true }));

    expect(window.apiCall).toHaveBeenCalledWith('/api/test-connection', 'POST', {
      api_base: 'https://api.example.com/v1',
      config_id: 'cfg-1',
      model: 'gpt-5.4'
    });
    await vi.waitFor(() => {
      expect(document.querySelector('.settings-test-card--success')).not.toBeNull();
    });
    expect(document.querySelector('.settings-test-label')?.textContent).toContain('结果判断');
    expect(document.getElementById('active-config-test-result')?.textContent).toContain('这次测试通过了，这套配置现在能正常用');
    expect(window.showToast).toHaveBeenCalledWith('连通了，gpt-5.4 可以用，响应 123ms。', 'success');
  });

  it('escapes malicious skill text instead of injecting DOM nodes', () => {
    const maliciousText = '<img src=x onerror="window.__xss = 1">';

    document.body.innerHTML = window.renderSkillsSettingsView([
      {
        name: 'evil-skill',
        display_name: maliciousText,
        description: maliciousText,
        path: maliciousText,
        trigger_hint: maliciousText,
        enabled: false,
        available: true
      }
    ]);

    expect(document.querySelector('img')).toBeNull();
    expect(document.querySelector('script')).toBeNull();
    expect(document.body.textContent).toContain(maliciousText);
    expect(window.__xss).toBeUndefined();
    expect(document.body.textContent).toContain('技能管理');
  });
});

describe('short-story DOM regressions', () => {
  it('supports keyboard activation through the shared activatable helper', () => {
    const handler = vi.fn();
    const element = document.createElement('div');

    window.makeElementActivatable(element, handler, { bindClick: false });
    element.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true }));
    element.dispatchEvent(new KeyboardEvent('keydown', { key: ' ', bubbles: true }));

    expect(handler).toHaveBeenCalledTimes(2);
    expect(element.getAttribute('role')).toBe('button');
    expect(element.tabIndex).toBe(0);
  });

  it('renders short-story navigation entries as buttons', () => {
    window.getCurrentShortStoryWorkflow = vi.fn(() => ({
      state: 'writing_content',
      synopsis_candidates: [{ index: 1 }],
      chapters: [{ chapter_number: 1, title: '雨夜站台' }],
      planned_chapters: 1,
      title_candidates: [{ index: 1 }],
      chapter_blueprints: [{ chapter_number: 1, title: '雨夜站台' }],
      final_output: 'final text',
      selected_title: '雨夜站台'
    }));
    window.getShortStoryStageLabel = vi.fn((value) => value || 'draft');
    window.renderShortStoryInterface = vi.fn();

    document.body.innerHTML = '<div id="nav-list-container"></div>';
    window.renderShortStoryNavPanel();

    expect(document.querySelector('.short-story-nav-entry')).toBeInstanceOf(HTMLButtonElement);
    expect(document.querySelector('.short-story-nav-entry--secondary')).toBeInstanceOf(HTMLButtonElement);
    expect(document.querySelector('.short-story-nav-chapter')).toBeInstanceOf(HTMLButtonElement);
  });

  it('keeps chapter blueprint metadata visible in the final view', () => {
    const html = window.renderShortStoryFinalChapters({
      chapters: [
        { chapter_number: 1, title: '雨夜站台', content: '正文内容。' }
      ],
      chapter_blueprints: [
        {
          chapter_number: 1,
          title: '雨夜站台',
          summary: '周岚回到旧地。',
          characters: '周岚',
          core_event: '她在站台重启调查。',
          narrative_function: '铺垫',
          emotion_point: '【虐点】她意识到对方再次失约。'
        }
      ]
    });

    document.body.innerHTML = html;

    expect(document.body.textContent).toContain('摘要：周岚回到旧地。');
    expect(document.body.textContent).toContain('出场角色：周岚');
    expect(document.body.textContent).toContain('核心事件：她在站台重启调查。');
    expect(document.body.textContent).toContain('叙事功能：铺垫');
    expect(document.body.textContent).toContain('情绪节点：【虐点】她意识到对方再次失约。');
  });

  it('renders visible short-story scroll shortcut buttons', () => {
    document.body.innerHTML = window.renderShortStoryScrollTools();

    expect(document.getElementById('short-story-scroll-top')?.textContent).toContain('回顶');
    expect(document.getElementById('short-story-scroll-bottom')?.textContent).toContain('置底');
  });

  it('renders fusion cards before synopsis flow when unified input mode is active', () => {
    window.shortStoryState.workflow = {
      state: 'awaiting_fusion_selection',
      raw_input: '旧相机、失约、雨夜',
      input_confidence: 0.86,
      detected_material_types: ['keywords', 'inspiration'],
      keywords: ['旧相机', '失约', '雨夜'],
      input_analysis: {
        summary: '输入包含词条与悬疑灵感。',
        warnings: []
      },
      fusion_candidates: [
        { index: 1, title: '暗房追索', route: '悬疑追查', hook: '失约的人藏进最后一张照片里。', premise: '方案一梗概。' },
        { index: 2, title: '迟来赴约', route: '情感反转', hook: '她等来的人没出现。', premise: '方案二梗概。' },
        { index: 3, title: '雨夜旧案', route: '暗黑揭秘', hook: '每按一次快门都更接近真相。', premise: '方案三梗概。' }
      ],
      synopsis_candidates: [],
      chapters: [],
      planned_chapters: 0,
      chapter_blueprints: []
    };
    window.getCurrentShortStoryWorkflow = vi.fn(() => window.shortStoryState.workflow);
    window.isShortStoryActionLoading = vi.fn(() => false);
    window.getShortStoryButtonLabel = vi.fn((action, idle) => idle);

    document.body.innerHTML = '<div id="short-story-sections"></div>';
    window.renderShortStorySections({
      hasWorkflow: true,
      canGenerateFusion: true,
      canGenerateSynopsis: false,
      canGenerateOutline: false,
      canConfirmOutline: false,
      canWriteContent: false,
      canQualityCheck: false,
      canCoherenceReview: false,
      canGenerateTitles: false,
      canAssemble: false,
      hasPlaceholderBlueprints: false
    });

    expect(document.body.textContent).toContain('暗房追索');
    expect(document.body.textContent).toContain('失约的人藏进最后一张照片里。');
    expect(document.body.textContent).toContain('识别把握：86%');
    expect(document.body.textContent).toContain('素材类型：keywords');
    expect(document.body.textContent).toContain('素材类型：inspiration');
    expect(document.body.textContent).toContain('抓到的重点：旧相机、失约、雨夜');
    expect(document.getElementById('short-story-generate-fusion')).not.toBeNull();
    expect(document.getElementById('short-story-generate-fusion')?.textContent).toContain('再来 3 个方案');
    expect(document.querySelector('.short-story-select-fusion')).toBeInstanceOf(HTMLButtonElement);
  });

  it('offers one-click input rewrite guidance when analysis confidence is low', () => {
    window.shortStoryState.workflow = {
      state: 'awaiting_fusion_selection',
      raw_input: '参考这个例文写，越像越好',
      input_confidence: 0.52,
      detected_material_types: ['example_text'],
      keywords: ['雨夜', '失约'],
      input_analysis: {
        summary: '输入以例文参考为主，但约束还不够清晰。',
        borrowed_highlights: ['强钩子', '快节奏反转'],
        constraints: ['人物设定换新'],
        warnings: []
      },
      fusion_candidates: [],
      synopsis_candidates: [],
      chapters: [],
      planned_chapters: 0,
      chapter_blueprints: []
    };
    window.getCurrentShortStoryWorkflow = vi.fn(() => window.shortStoryState.workflow);
    window.isShortStoryActionLoading = vi.fn(() => false);
    window.getShortStoryButtonLabel = vi.fn((action, idle) => idle);
    window.markShortStoryDraftSaved = vi.fn();
    window.showToast = vi.fn();

    document.body.innerHTML = '<div id="short-story-sections"></div><textarea id="short-story-keywords"></textarea>';
    window.renderShortStorySections({
      hasWorkflow: true,
      canGenerateFusion: true,
      canGenerateSynopsis: false,
      canGenerateOutline: false,
      canConfirmOutline: false,
      canWriteContent: false,
      canQualityCheck: false,
      canCoherenceReview: false,
      canGenerateTitles: false,
      canAssemble: false,
      hasPlaceholderBlueprints: false
    });
    window.bindShortStoryEvents();

    expect(document.body.textContent).toContain('这段输入有点混');
    expect(document.getElementById('short-story-input-suggestion')?.value).toContain('素材类型：example_text');
    expect(document.getElementById('short-story-input-suggestion')?.value).toContain('参考保留：强钩子、快节奏反转');

    document.getElementById('short-story-apply-input-suggestion').click();

    expect(document.getElementById('short-story-keywords')?.value).toContain('创作目标：输入以例文参考为主');
    expect(window.markShortStoryDraftSaved).toHaveBeenCalled();
    expect(window.showToast).toHaveBeenCalledWith('已用整理后的输入建议替换原始素材');
  });

  it('scrolls the short-story workspace to top and bottom', () => {
    document.body.innerHTML = `
      <div id="main-view"></div>
      ${window.renderShortStoryScrollTools()}
    `;

    const container = document.getElementById('main-view');
    const scrollTo = vi.fn();
    Object.defineProperty(container, 'scrollTo', { value: scrollTo, configurable: true });
    Object.defineProperty(container, 'scrollHeight', { value: 2400, configurable: true });
    Object.defineProperty(container, 'clientHeight', { value: 600, configurable: true });

    window.bindShortStoryEvents();

    document.getElementById('short-story-scroll-top').click();
    document.getElementById('short-story-scroll-bottom').click();

    expect(scrollTo).toHaveBeenNthCalledWith(1, { top: 0, behavior: 'smooth' });
    expect(scrollTo).toHaveBeenNthCalledWith(2, { top: 1800, behavior: 'smooth' });
  });

  it('shows live batch generation progress in the loading banner', () => {
    vi.spyOn(Date, 'now').mockReturnValue(15_000);
    window.shortStoryState.loadingAction = 'generate-all-chapters';
    window.shortStoryState.loadingStartedAt = 10_000;
    window.shortStoryState.batchGenerationProgress = {
      total: 5,
      completed: 2,
      currentChapter: 3
    };

    const html = window.renderShortStoryLoadingBanner();
    document.body.innerHTML = html;

    expect(document.getElementById('short-story-loading-title')?.textContent).toContain('正在生成第3章正文');
    expect(document.getElementById('short-story-loading-hint')?.textContent).toContain('当前批次 2/5');
    expect(document.getElementById('short-story-loading-hint')?.textContent).toContain('已持续 5 秒');
  });

  it('builds clean deliverable output with tags and chapter numbering only', () => {
    const clean = window.getCleanFinalOutput({
      selected_title: '她与深海',
      story_tags: {
        main_category: '婚姻家庭',
        all_tags: ['大女主', '女性互助']
      },
      selected_synopsis: '（反转向）她决定离开。',
      chapters: [
        { chapter_number: 1, title: '回家', content: '### 1. 回家\n赵琳回国。' },
        { chapter_number: 2, title: '对峙', content: '她不再退让。\n\n\\*' }
      ],
      final_output: `# 《她与深海》
**主分类**：婚姻家庭
**内容标签**：大女主、女性互助
**词条标签**：现代 | 大女主

---

## 导语
她决定离开。

---

## 正文
### 1. 回家
赵琳回国。

\\*

### 2. 对峙
她不再退让。

---

（全文完）`
    });

    expect(clean).toContain('她与深海');
    expect(clean).toContain('标签：婚姻家庭、大女主、女性互助');
    expect(clean).toContain('导语：她决定离开。');
    expect(clean).toContain('1.');
    expect(clean).toContain('2.');
    expect(clean).not.toContain('1. 回家');
    expect(clean).not.toContain('2. 对峙');
    expect(clean).not.toContain('\\*');
    expect(clean).not.toContain('\n*\n');
    expect(clean).not.toContain('《');
    expect(clean).not.toContain('词条标签');
    expect(clean).not.toContain('# ');
  });

  it('copies the clean deliverable output instead of raw markdown final output', async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(window.navigator, 'clipboard', {
      value: { writeText },
      configurable: true
    });

    window.getCurrentShortStoryWorkflow = vi.fn(() => ({
      selected_title: '她与深海',
      story_tags: {
        main_category: '婚姻家庭',
        all_tags: ['大女主', '女性互助']
      },
      selected_synopsis: '（反转向）她决定离开。',
      chapters: [
        { chapter_number: 1, title: '回家', content: '### 1. 回家\n赵琳回国。' }
      ],
      final_output: '# 《她与深海》\n**主分类**：婚姻家庭\n**内容标签**：大女主、女性互助\n\n## 导语\n她决定离开。\n\n## 正文\n### 1. 回家\n赵琳回国。'
    }));
    window.showToast = vi.fn();

    await window.copyShortStoryFinalText();

    expect(writeText).toHaveBeenCalledTimes(1);
    const copied = writeText.mock.calls[0][0];
    expect(copied).toContain('她与深海');
    expect(copied).toContain('标签：婚姻家庭、大女主、女性互助');
    expect(copied).toContain('1.');
    expect(copied).not.toContain('《');
    expect(copied).not.toContain('# ');
    expect(copied).not.toContain('1. 回家');
  });

  it('cleans legacy final output into deliverable text', () => {
    const clean = window.getCleanFinalOutput({
      final_output: `# 《婆婆说她掏出一张堕胎病历》
**主分类**：婚姻家庭
**内容标签**：大女主、女性互助、打脸逆袭
**词条标签**：大女主、贴近生活

## 导语
赵琳把婆婆告上了社区道德法庭。

## 正文
### 1. 公开的羞辱
朵朵的三岁生日宴设在小区门口的饭店包间里。

\\*

粉色的气球，卡通蛋糕，孩子的笑声本该是主角。`
    });

    expect(clean).toContain('婆婆说她掏出一张堕胎病历');
    expect(clean).toContain('标签：婚姻家庭、大女主、女性互助、打脸逆袭');
    expect(clean).toContain('导语：赵琳把婆婆告上了社区道德法庭。');
    expect(clean).toContain('1.');
    expect(clean).not.toContain('《');
    expect(clean).not.toContain('词条标签');
    expect(clean).not.toContain('正文');
    expect(clean).not.toContain('1. 公开的羞辱');
    expect(clean).not.toContain('\\*');
  });

  it('exports txt from clean deliverable text on the client side', async () => {
    const createObjectURL = vi.fn(() => 'blob:test');
    const revokeObjectURL = vi.fn();
    Object.defineProperty(window.URL, 'createObjectURL', { value: createObjectURL, configurable: true });
    Object.defineProperty(window.URL, 'revokeObjectURL', { value: revokeObjectURL, configurable: true });
    global.fetch = vi.fn();
    const capturedParts = [];
    const OriginalBlob = global.Blob;
    const BlobCtor = vi.fn((parts, options) => {
      capturedParts.push({ parts, options });
      return { size: String(parts.join('')).length, type: options?.type || '' };
    });
    global.Blob = BlobCtor;

    const click = vi.fn();
    const originalCreateElement = document.createElement.bind(document);
    const createElement = vi.spyOn(document, 'createElement').mockImplementation((tagName, options) => {
      const element = originalCreateElement(tagName, options);
      if (String(tagName).toLowerCase() === 'a') {
        element.click = click;
      }
      return element;
    });

    window.getCurrentShortStoryWorkflow = vi.fn(() => ({
      final_output: `# 《她与深海》
**主分类**：婚姻家庭
**内容标签**：大女主、女性互助

## 导语
她决定离开。

## 正文
### 1. 回家
赵琳回国。`
    }));

    await window.exportShortStoryFile('txt');

    expect(global.fetch).not.toHaveBeenCalled();
    expect(createObjectURL).toHaveBeenCalledTimes(1);
    const exportedText = capturedParts[0].parts.join('');
    expect(exportedText).toContain('标签：婚姻家庭、大女主、女性互助');
    expect(exportedText).not.toContain('《');
    expect(exportedText).not.toContain('1. 回家');
    expect(click).toHaveBeenCalledTimes(1);
    expect(revokeObjectURL).toHaveBeenCalledWith('blob:test');
    expect(window.showToast).toHaveBeenCalledWith('已导出 TXT 文件');

    createElement.mockRestore();
    global.Blob = OriginalBlob;
  });

  it('renders manuscript preview in the assembled output section', () => {
    const html = window.renderShortStoryManuscriptPreview({
      final_output: 'ready',
      selected_title: '她与深海',
      selected_synopsis: '她决定离开。',
      chapters: [
        { chapter_number: 1, title: '回家', content: '### 1. 回家\n第一章正文。\n\n***\n\n\\*\n\n* * *\n\n\\***' },
        { chapter_number: 2, title: '对峙', content: '第二章正文。' }
      ]
    }, { compact: true });

    document.body.innerHTML = html;

    expect(document.querySelector('.short-story-manuscript-preview')).not.toBeNull();
    expect(document.body.textContent).toContain('《她与深海》');
    expect(document.body.textContent).toContain('展开正文（共 2 章）');
    expect(document.body.textContent).toContain('1.');
    expect(document.body.textContent).toContain('2.');
    expect(document.body.textContent).not.toContain('1. 回家');
    expect(document.body.textContent).not.toContain('2. 对峙');
    expect(document.body.textContent).toContain('第一章正文。');
    expect(document.body.textContent).not.toContain('***');
    expect(document.body.textContent).not.toContain('\\*');
    expect(document.body.textContent).not.toContain('* * *');
    expect(document.body.textContent).not.toContain('\\***');
    expect(document.querySelector('.short-story-manuscript-toggle')?.hasAttribute('open')).toBe(false);
  });

  it('enables single-chapter regeneration during quality checking', () => {
    window.getCurrentShortStoryWorkflow = vi.fn(() => ({
      state: 'quality_checking',
      chapter_blueprints: [
        {
          chapter_number: 1,
          title: '雨夜站台',
          summary: '周岚回到旧地。',
          characters: '周岚',
          core_event: '她在站台重启调查。',
          narrative_function: '铺垫'
        }
      ],
      chapters: [
        { chapter_number: 1, title: '雨夜站台', content: '正文内容。' }
      ]
    }));
    window.isShortStoryActionLoading = vi.fn(() => false);
    window.getShortStoryButtonLabel = vi.fn((action, idle) => idle);
    window.escapeHtml = window.escapeHtml || ((value) => String(value));

    document.body.innerHTML = window.getShortStoryChapterEditors();

    expect(document.querySelector('.short-story-generate-chapter')?.hasAttribute('disabled')).toBe(false);
  });

  it('disables regeneration and saving for placeholder blueprint chapters', () => {
    window.getCurrentShortStoryWorkflow = vi.fn(() => ({
      state: 'quality_checking',
      chapter_blueprints: [
        {
          chapter_number: 9,
          title: '第9章',
          summary: '',
          characters: '',
          core_event: '',
          narrative_function: '',
          emotion_point: '',
          is_placeholder: true
        }
      ],
      chapters: [
        { chapter_number: 9, title: '第9章', content: '正文内容。' }
      ]
    }));
    window.isShortStoryActionLoading = vi.fn(() => false);
    window.getShortStoryButtonLabel = vi.fn((action, idle) => idle);
    window.escapeHtml = window.escapeHtml || ((value) => String(value));

    document.body.innerHTML = window.getShortStoryChapterEditors();

    expect(document.querySelector('.short-story-generate-chapter')?.hasAttribute('disabled')).toBe(true);
    expect(document.querySelector('.short-story-save-chapter')?.hasAttribute('disabled')).toBe(true);
    expect(document.querySelector('.short-story-chapter-content')?.hasAttribute('readonly')).toBe(true);
    expect(document.body.textContent).toContain('缺少有效章节蓝图');
  });

  it('renders a simple-fix button when quality report includes low-risk replacements', () => {
    window.shortStoryState.qualitySimpleFixes = [
      { chapter_number: 1, from_name: '陈哲', to_name: '陈浩', fix_type: 'name_consistency' },
      { chapter_number: 10, from_name: '王秀兰', to_name: '王桂芬', fix_type: 'name_consistency' }
    ];
    window.shortStoryState.qualityReportDraft = '第1章：角色一致性 - 丈夫名字“陈哲”与角色表“陈浩”不符';
    window.getCurrentShortStoryWorkflow = vi.fn(() => ({
      state: 'quality_checking',
      planned_chapters: 2,
      chapters: [
        { chapter_number: 1, title: '第1章', content: '正文1' },
        { chapter_number: 2, title: '第2章', content: '正文2' }
      ],
      chapter_blueprints: [
        { chapter_number: 1, title: '第1章', summary: '摘要1', characters: '沈青、陈浩', core_event: '事件1', narrative_function: '铺垫' },
        { chapter_number: 2, title: '第2章', summary: '摘要2', characters: '沈青、王桂芬', core_event: '事件2', narrative_function: '推进' }
      ]
    }));
    window.isShortStoryActionLoading = vi.fn(() => false);
    window.getShortStoryButtonLabel = vi.fn((action, idle) => idle);

    document.body.innerHTML = '<div id="short-story-sections"></div>';
    window.renderShortStorySections({
      hasWorkflow: true,
      canGenerateSynopsis: false,
      canGenerateOutline: false,
      canConfirmOutline: false,
      canWriteContent: true,
      canQualityCheck: true,
      canCoherenceReview: false,
      canGenerateTitles: false,
      canAssemble: false,
      hasPlaceholderBlueprints: false
    });

    expect(document.getElementById('short-story-apply-simple-quality-fixes')?.hasAttribute('disabled')).toBe(false);
    expect(document.body.textContent).toContain('检测到 2 条可自动修复的简单问题');
    expect(document.body.textContent).toContain('第1章：陈哲 → 陈浩');
  });

  it('renders a rollback button when placeholder blueprint chapters exist', async () => {
    window.shortStoryState.workflow = {
      state: 'quality_checking',
      keywords: ['旧相机', '雨夜'],
      target_total_words: 6000,
      chapter_word_target: 1000,
      category: '悬疑惊悚',
      selected_synopsis: '她回到旧地。',
      outline_confirmed: true,
      manual_intervention_required: true,
      repair_placeholder_numbers: [2],
      planned_chapters: 3,
      chapter_blueprints: [
        { chapter_number: 1, title: '第1章', summary: '摘要1', characters: '甲', core_event: '事件1', narrative_function: '铺垫' },
        { chapter_number: 2, title: '第2章', summary: '', characters: '', core_event: '', narrative_function: '', is_placeholder: true }
      ],
      chapters: [
        { chapter_number: 1, title: '第1章', content: '第一章正文。' },
        { chapter_number: 2, title: '第2章', content: '第二章正文。' },
        { chapter_number: 3, title: '第3章', content: '第三章正文。' }
      ]
    };
    window.shortStoryState.collapsedSections = {};
    window.shortStoryState.highlightSection = '';
    window.getCurrentShortStoryWorkflow = vi.fn(() => window.shortStoryState.workflow);
    window.isShortStoryActionLoading = vi.fn(() => false);
    window.getShortStoryButtonLabel = vi.fn((action, idle) => idle);
    document.body.innerHTML = '<div id="short-story-sections"></div>';
    window.renderShortStorySections({
      hasWorkflow: true,
      canGenerateSynopsis: false,
      canGenerateOutline: false,
      canConfirmOutline: false,
      canWriteContent: true,
      canQualityCheck: false,
      canCoherenceReview: false,
      canGenerateTitles: false,
      canAssemble: false,
      hasPlaceholderBlueprints: true
    });

    expect(document.getElementById('short-story-repair-outline-placeholders')).not.toBeNull();
    expect(document.getElementById('short-story-generate-quality')?.hasAttribute('disabled')).toBe(true);
    expect(document.body.textContent).toContain('已定位到异常章节：第 2 章');
    expect(document.body.textContent).toContain('请确认大纲里已经补回这些章节');
    expect(document.body.textContent).toContain('缺失章节检查清单');
    expect(document.body.textContent).toContain('已补回 0/1 章');
    expect(document.body.textContent).toContain('第 2 章');
    expect(document.body.textContent).toContain('待补回');
  });

  it('updates the outline repair checklist while editing outline text', () => {
    window.markShortStoryDraftSaved = vi.fn();
    loadBrowserScript('novel_agent/web/static/short-story/short-story-events.js');
    window.shortStoryState.workflow = {
      state: 'awaiting_outline_confirm',
      outline_text: '',
      outline_confirmed: false,
      repair_placeholder_numbers: [2, 3],
      chapter_blueprints: [
        { chapter_number: 1, title: '第1章', summary: '摘要1', characters: '甲', core_event: '事件1', narrative_function: '铺垫' }
      ],
      chapters: [{ chapter_number: 1, title: '第1章', content: '第一章正文。' }]
    };
    window.getCurrentShortStoryWorkflow = vi.fn(() => window.shortStoryState.workflow);

    document.body.innerHTML = `
      <div id="short-story-outline-repair-checklist">${window.renderShortStoryOutlineRepairChecklist(window.shortStoryState.workflow)}</div>
      <textarea id="short-story-outline-text"></textarea>
    `;

    window.bindShortStoryDraftAutosave();

    expect(document.body.textContent).toContain('已补回 0/2 章');
    expect(document.body.textContent).toContain('待补回');

    const outlineInput = document.getElementById('short-story-outline-text');
    outlineInput.value = `### 2. 新章节\n- 摘要：补回第二章\n\n### 3. 再一章\n- 摘要：补回第三章`;
    outlineInput.dispatchEvent(new Event('input', { bubbles: true }));

    expect(document.body.textContent).toContain('已补回 2/2 章');
    expect(document.body.textContent).toContain('第 2 章');
    expect(document.body.textContent).toContain('第 3 章');
    expect(document.body.textContent).toContain('已补回');
  });

  it('disables confirm outline when repaired chapters are still missing from outline text', () => {
    window.shortStoryState.workflow = {
      state: 'awaiting_outline_confirm',
      outline_text: `### 1. 第1章\n- 摘要：摘要1\n- 核心事件：事件1`,
      outline_confirmed: false,
      repair_placeholder_numbers: [2, 3],
      chapter_blueprints: [
        { chapter_number: 1, title: '第1章', summary: '摘要1', characters: '甲', core_event: '事件1', narrative_function: '铺垫' }
      ],
      chapters: [{ chapter_number: 1, title: '第1章', content: '第一章正文。' }]
    };
    window.getCurrentShortStoryWorkflow = vi.fn(() => window.shortStoryState.workflow);
    window.isShortStoryActionLoading = vi.fn(() => false);
    window.getShortStoryButtonLabel = vi.fn((action, idle) => idle);

    document.body.innerHTML = '<div id="short-story-sections"></div>';
    window.renderShortStorySections({
      hasWorkflow: true,
      canGenerateSynopsis: false,
      canGenerateOutline: false,
      canConfirmOutline: true,
      canWriteContent: false,
      canQualityCheck: false,
      canCoherenceReview: false,
      canGenerateTitles: false,
      canAssemble: false,
      hasPlaceholderBlueprints: false
    });

    expect(document.getElementById('short-story-confirm-outline')?.hasAttribute('disabled')).toBe(true);
    expect(document.body.textContent).toContain('仍有缺失章节未补回，当前不可确认大纲');
  });

  it('blocks confirming outline when repair checklist still has pending chapters', () => {
    window.shortStoryState.workflow = {
      state: 'awaiting_outline_confirm',
      outline_text: `### 1. 第1章\n- 摘要：摘要1\n- 核心事件：事件1`,
      outline_confirmed: false,
      repair_placeholder_numbers: [2, 3],
      chapter_blueprints: [
        { chapter_number: 1, title: '第1章', summary: '摘要1', characters: '甲', core_event: '事件1', narrative_function: '铺垫' }
      ],
      chapters: [{ chapter_number: 1, title: '第1章', content: '第一章正文。' }]
    };
    window.getCurrentShortStoryWorkflow = vi.fn(() => window.shortStoryState.workflow);
    window.apiCall = vi.fn();
    window.showToast = vi.fn();
    window.saveShortStoryData = vi.fn();
    window.syncShortStoryWorkflowDrafts = vi.fn(() => {
      window.shortStoryState.workflow.outline_text = document.getElementById('short-story-outline-text')?.value || '';
    });

    document.body.innerHTML = `
      <section id="short-story-section-outline"></section>
      <div id="short-story-outline-repair-checklist">${window.renderShortStoryOutlineRepairChecklist(window.shortStoryState.workflow)}</div>
      <textarea id="short-story-outline-text">${window.shortStoryState.workflow.outline_text}</textarea>
      <button id="short-story-confirm-outline">确认大纲</button>
    `;

    const scrollIntoView = vi.fn();
    Object.defineProperty(document.getElementById('short-story-section-outline'), 'scrollIntoView', {
      value: scrollIntoView,
      configurable: true
    });

    window.bindShortStoryEvents();
    document.getElementById('short-story-confirm-outline').click();

    expect(window.showToast).toHaveBeenCalledWith('请先补回第 2、3 章的大纲蓝图后再确认大纲', 'error');
    expect(window.apiCall).not.toHaveBeenCalled();
    expect(window.shortStoryState.highlightSection).toBe('outline');
    expect(scrollIntoView).toHaveBeenCalled();
  });

  it('renders a resume button when batch chapter generation stops midway', () => {
    window.shortStoryState.partialChapterGeneration = {
      failedChapter: 3,
      error: '无法连接到API服务器。',
      generatedCount: 2
    };
    window.isShortStoryActionLoading = vi.fn(() => false);
    window.getShortStoryButtonLabel = vi.fn((action, idle) => idle);

    document.body.innerHTML = window.renderShortStoryPartialChapterResume();
    const text = document.body.textContent.replace(/\s+/g, ' ').trim();

    expect(text).toMatch(/批量生成已完成前 2 章，第 3 章\s*起中断。/);
    expect(text).toContain('无法连接到API服务器。');
    expect(document.getElementById('short-story-resume-all-chapters')?.textContent).toContain('从第3章继续生成');
  });

  it('repairs chapter metadata from multi-line outline sections', () => {
    const { repairShortStoryWorkflowBlueprints } = loadShortStoryStateHelpers();
    const workflow = repairShortStoryWorkflowBlueprints({
      outline_text: `### 1. 深蓝的第一课
- **摘要**：沈青第一次走进潜水中心。
- **出场角色**：沈青、林薇、周明哲（电话中）
- **核心事件**：潜水初体验的挫败与启示，正式提出离婚。
- **叙事功能**：引入关键配角林薇，推进离婚主线。
- **情绪节点**：【转折点】“在水里，你只能靠自己”

### 2. 沉默的拉锯战
- **摘要**：沈青与周明哲进入离婚拉锯。
- **出场角色**：沈青、周明哲、律师（侧面提及）
- **核心事件**：离婚谈判拉锯，沈青以沉默和行动应对压力。
- **叙事功能**：深化婚姻冲突，强化女性自主主题。`,
      chapter_blueprints: [
        { chapter_number: 1, title: '深蓝的第一课', summary: '沈青第一次走进潜水中心。', characters: '', core_event: '', narrative_function: '', emotion_point: '' },
        { chapter_number: 2, title: '沉默的拉锯战', summary: '沈青与周明哲进入离婚拉锯。', characters: '', core_event: '', narrative_function: '', emotion_point: '' }
      ]
    });

    expect(workflow.chapter_blueprints[0].characters).toBe('沈青、林薇、周明哲（电话中）');
    expect(workflow.chapter_blueprints[0].core_event).toContain('正式提出离婚');
    expect(workflow.chapter_blueprints[0].narrative_function).toContain('推进离婚主线');
    expect(workflow.chapter_blueprints[0].emotion_point).toContain('在水里，你只能靠自己');
    expect(workflow.chapter_blueprints[1].characters).toBe('沈青、周明哲、律师（侧面提及）');
    expect(workflow.chapter_blueprints[1].narrative_function).toContain('女性自主主题');
  });

  it('backfills missing chapter blueprints from planned chapter count and written chapters', () => {
    const { repairShortStoryWorkflowBlueprints } = loadShortStoryStateHelpers();
    const workflow = repairShortStoryWorkflowBlueprints({
      planned_chapters: 11,
      chapter_blueprints: [
        { chapter_number: 1, title: '第1章', summary: '摘要1', characters: '', core_event: '', narrative_function: '', emotion_point: '' },
        { chapter_number: 2, title: '第2章', summary: '摘要2', characters: '', core_event: '', narrative_function: '', emotion_point: '' },
        { chapter_number: 3, title: '第3章', summary: '摘要3', characters: '', core_event: '', narrative_function: '', emotion_point: '' },
        { chapter_number: 4, title: '第4章', summary: '摘要4', characters: '', core_event: '', narrative_function: '', emotion_point: '' },
        { chapter_number: 5, title: '第5章', summary: '摘要5', characters: '', core_event: '', narrative_function: '', emotion_point: '' },
        { chapter_number: 6, title: '第6章', summary: '摘要6', characters: '', core_event: '', narrative_function: '', emotion_point: '' },
        { chapter_number: 7, title: '第7章', summary: '摘要7', characters: '', core_event: '', narrative_function: '', emotion_point: '' },
        { chapter_number: 8, title: '第8章', summary: '摘要8', characters: '', core_event: '', narrative_function: '', emotion_point: '' }
      ],
      chapters: [
        { chapter_number: 9, title: '第9章', content: '第九章正文。' },
        { chapter_number: 10, title: '第10章', content: '第十章正文。' },
        { chapter_number: 11, title: '第11章', content: '第十一章正文。' }
      ]
    });

    expect(workflow.chapter_blueprints).toHaveLength(11);
    expect(workflow.chapter_blueprints[8].title).toBe('第9章');
    expect(workflow.chapter_blueprints[10].title).toBe('第11章');
    expect(workflow.chapter_blueprints[8].is_placeholder).toBe(true);
    expect(workflow.warnings.some((item) => item.includes('缺少有效大纲蓝图'))).toBe(true);
  });

  it('opens settings API tab from the missing API notice link', () => {
    document.body.innerHTML = '<a href="#" id="short-story-open-api-settings">打开 API 设置</a>';

    window.bindShortStoryEvents();
    document.getElementById('short-story-open-api-settings').click();

    expect(window.switchModule).toHaveBeenCalledWith('settings');
    expect(window.loadSettingsTab).toHaveBeenCalledWith('api');
  });

  it('updates model options when switching API config', () => {
    window.shortStoryState.apiConfigs = [
      { id: 'cfg-a', models: ['model-a1', 'model-a2'] },
      { id: 'cfg-b', models: ['model-b1'] }
    ];
    window.shortStoryState.selectedApiConfigId = 'cfg-a';
    window.shortStoryState.activeConfigId = 'cfg-a';
    window.shortStoryState.selectedModel = 'model-a1';

    document.body.innerHTML = `
      <select id="short-story-api-config">
        <option value="cfg-a" selected>cfg-a</option>
        <option value="cfg-b">cfg-b</option>
      </select>
      <select id="short-story-model">${window.renderShortStoryModelOptions('cfg-a', 'model-a1')}</select>
    `;

    window.bindShortStoryEvents();

    const apiSelect = document.getElementById('short-story-api-config');
    const modelSelect = document.getElementById('short-story-model');

    apiSelect.value = 'cfg-b';
    apiSelect.dispatchEvent(new Event('change', { bubbles: true }));

    const optionValues = Array.from(modelSelect.querySelectorAll('option')).map((option) => option.value);

    expect(window.shortStoryState.selectedApiConfigId).toBe('cfg-b');
    expect(window.shortStoryState.selectedModel).toBe('model-b1');
    expect(optionValues).toEqual(['model-b1']);
    expect(window.saveShortStoryData).toHaveBeenCalled();
  });
});
