/**
 * 山海·云烟 - 短篇创作状态层
 */

const SHORT_STORY_MAIN_CATEGORIES = [
    '婚姻家庭', '女生生活', '男生生活', '现言甜宠', '虐心婚恋', '青春虐恋', '男生情感',
    '脑洞', '社会伦理', '女性成长', '悬疑惊悚', '古代言情', '玄幻仙侠', '宫斗宅斗',
    '男频衍生', '女频衍生', '年代', '纯爱', '其他'
];

const SHORT_STORY_PROJECT_STATE_KEY = 'short_story_panel';
const SHORT_STORY_LEGACY_STORAGE_KEY = 'short_story_data';

let shortStoryPersistTimer = null;
let shortStoryHighlightTimer = null;

function escapeShortStoryRegex(value) {
    return String(value || '').replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

function normalizeShortStoryCategory(value, fallback = '其他') {
    const fallbackText = String(fallback || '其他').replace(/\s+/g, ' ').trim() || '其他';
    const category = String(value || '').replace(/\s+/g, ' ').trim();
    return (category || fallbackText).slice(0, 32) || '其他';
}

function coerceShortStoryChapterNumber(value, fallback) {
    const text = String(value || '').trim();
    if (/^\d+$/.test(text)) {
        return Math.max(1, parseInt(text, 10));
    }

    const mapping = {
        '一': 1, '二': 2, '三': 3, '四': 4, '五': 5,
        '六': 6, '七': 7, '八': 8, '九': 9, '十': 10
    };
    if (mapping[text]) return mapping[text];
    if (text.startsWith('十') && text.length === 2 && mapping[text[1]]) return 10 + mapping[text[1]];
    if (text.length === 2 && mapping[text[0]] && text[1] === '十') return mapping[text[0]] * 10;
    if (text.length === 3 && mapping[text[0]] && text[1] === '十' && mapping[text[2]]) {
        return mapping[text[0]] * 10 + mapping[text[2]];
    }
    return fallback;
}

function extractShortStoryOutlineField(text, labels) {
    const variants = (Array.isArray(labels) ? labels : [labels]).map((item) => String(item || '').trim()).filter(Boolean);
    if (variants.length === 0) return '';

    const labelGroup = variants.map(escapeShortStoryRegex).join('|');
    const patterns = [
        new RegExp(`^[ \\t>*-]*(?:\\d+[.、)\\-]\\s*)?(?:\\*\\*)?(?:${labelGroup})(?:\\*\\*)?\\s*[：:]\\s*(.+?)\\s*$`, 'mi'),
        new RegExp(`^[ \\t>*-]*(?:\\d+[.、)\\-]\\s*)?【(?:${labelGroup})】\\s*(.+?)\\s*$`, 'mi')
    ];

    for (const pattern of patterns) {
        const match = pattern.exec(text || '');
        if (match?.[1]) {
            return match[1].trim();
        }
    }
    return '';
}

function parseShortStoryBlueprintsFromOutline(outlineText) {
    const text = String(outlineText || '').trim();
    if (!text) return [];

    const pattern = /^\s*###\s*(?:(?:第)?([一二三四五六七八九十百零\d]+)章(?:[：: ]*)|(\d+)[.、]\s*)([^\n]*)\n([\s\S]*?)(?=^\s*###\s*(?:(?:第)?(?:[一二三四五六七八九十百零\d]+)章(?:[：: ]*)|\d+[.、]\s*)|(?![\s\S]))/gm;
    const blueprints = [];
    let match;
    let index = 0;

    while ((match = pattern.exec(text)) !== null) {
        index += 1;
        const label = (match[2] || match[1] || '').trim();
        const title = String(match[3] || '').trim() || `第${index}章`;
        const body = String(match[4] || '').trim();
        blueprints.push({
            chapter_number: coerceShortStoryChapterNumber(label, index),
            title,
            summary: extractShortStoryOutlineField(body, ['摘要', '本章摘要']),
            characters: extractShortStoryOutlineField(body, ['出场角色', '出场人物', '主要角色']),
            core_event: extractShortStoryOutlineField(body, ['核心事件', '关键事件', '主要事件']),
            narrative_function: extractShortStoryOutlineField(body, ['叙事功能', '剧情作用', '章节作用', '功能定位']),
            emotion_point: extractShortStoryOutlineField(body, ['情绪节点', '情绪重点', '情绪爆点'])
        });
    }

    return blueprints;
}

function repairShortStoryWorkflowBlueprints(workflow) {
    if (!workflow || typeof workflow !== 'object') return workflow;

    const existing = Array.isArray(workflow.chapter_blueprints) ? workflow.chapter_blueprints : [];
    const parsed = parseShortStoryBlueprintsFromOutline(workflow.outline_text || '');
    const planned = Number(workflow.planned_chapters || 0);
    const chapters = Array.isArray(workflow.chapters) ? workflow.chapters : [];
    const chapterMap = new Map(chapters.map((item) => [Number(item.chapter_number || 0), item]));
    const parsedByChapter = new Map(parsed.map((item) => [item.chapter_number, item]));
    const existingByChapter = new Map(existing.map((item) => [Number(item.chapter_number || 0), item]));
    const highestChapter = Math.max(
        planned,
        ...existing.map((item) => Number(item.chapter_number || 0)),
        ...parsed.map((item) => Number(item.chapter_number || 0)),
        ...chapters.map((item) => Number(item.chapter_number || 0)),
        0
    );

    let changed = false;
    const repaired = [];
    for (let chapterNumber = 1; chapterNumber <= highestChapter; chapterNumber += 1) {
        const fallback = parsedByChapter.get(chapterNumber) || {};
        const chapter = chapterMap.get(chapterNumber) || {};
        const current = existingByChapter.get(chapterNumber)
            ? { ...existingByChapter.get(chapterNumber) }
            : {
                chapter_number: chapterNumber,
                title: chapter.title || fallback.title || `第${chapterNumber}章`,
                summary: '',
                characters: '',
                core_event: '',
                narrative_function: '',
                emotion_point: '',
                is_placeholder: true
            };
        current.chapter_number = chapterNumber;
        current.title = String(current.title || chapter.title || fallback.title || `第${chapterNumber}章`).trim() || `第${chapterNumber}章`;
        current.is_placeholder = Boolean(current.is_placeholder);
        for (const key of ['summary', 'characters', 'core_event', 'narrative_function', 'emotion_point']) {
            if (!String(current[key] || '').trim() && String(fallback[key] || '').trim()) {
                current[key] = fallback[key];
                changed = true;
            }
        }
        if (!existingByChapter.has(chapterNumber)) {
            changed = true;
        }
        repaired.push(current);
    }

    if (changed) {
        workflow.chapter_blueprints = repaired;
    }
    const placeholderCount = repaired.filter((item) => item.is_placeholder).length;
    if (placeholderCount > 0) {
        const warning = `检测到 ${placeholderCount} 个章节缺少有效大纲蓝图，这些章节可能是按占位信息生成的，建议回到大纲阶段重新规划后再重写对应章节。`;
        const warnings = Array.isArray(workflow.warnings) ? [...workflow.warnings] : [];
        if (!warnings.includes(warning)) {
            warnings.push(warning);
            workflow.warnings = warnings;
        }
    }
    return workflow;
}

function createShortStoryProjectState() {
    return {
        workflow: null,
        selectedApiConfigId: '',
        selectedModel: '',
        draftSourceInput: '',
        draftKeywords: '',
        draftTotalWords: 5000,
        draftChapterWords: 800,
        draftChapterWordsCustomized: false,
        draftCategory: '其他',
        inputAnalysisRawOutput: '',
        fusionRawOutput: '',
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
        qualitySuggestedChapters: [],
        coherenceSuggestedChapters: [],
        outlineRevisionFeedback: '',
        partialChapterGeneration: null,
        activeView: 'panel',
        collapsedSections: {},
        draftSavedAt: 0,
        loadingAction: '',
        loadingStartedAt: 0,
        batchGenerationProgress: null,
        highlightSection: ''
    };
}

const shortStoryState = {
    apiConfigs: [],
    activeConfigId: '',
    globalModel: '',
    globalConfigured: false,
    isRendering: false,
    loadedProjectId: '',
    ...createShortStoryProjectState()
};

function getShortStoryActiveProjectId() {
    if (typeof getActiveProjectId === 'function') {
        return getActiveProjectId() || '';
    }
    return store?.currentProjectId || '';
}

function getShortStoryStorageKey(projectId = getShortStoryActiveProjectId()) {
    return projectId ? `short_story_data_${projectId}` : SHORT_STORY_LEGACY_STORAGE_KEY;
}

function applyShortStoryProjectState(data = {}) {
    const defaults = createShortStoryProjectState();

    shortStoryState.workflow = repairShortStoryWorkflowBlueprints(data.workflow || defaults.workflow);
    shortStoryState.selectedApiConfigId = data.selectedApiConfigId || defaults.selectedApiConfigId;
    shortStoryState.selectedModel = data.selectedModel || defaults.selectedModel;
    shortStoryState.draftSourceInput = data.draftSourceInput || data.draftKeywords || defaults.draftSourceInput;
    shortStoryState.draftKeywords = data.draftKeywords || defaults.draftKeywords;
    shortStoryState.draftTotalWords = Number(data.draftTotalWords || defaults.draftTotalWords);
    const workflowChapterWords = Number(data.workflow?.chapter_word_target || defaults.draftChapterWords);
    shortStoryState.draftChapterWordsCustomized = Boolean(data.draftChapterWordsCustomized || data.workflow?.custom_chapter_word_target);
    shortStoryState.draftChapterWords = shortStoryState.draftChapterWordsCustomized
        ? Number(data.draftChapterWords || workflowChapterWords)
        : workflowChapterWords;
    shortStoryState.draftCategory = normalizeShortStoryCategory(data.draftCategory || data.draftTone, defaults.draftCategory);
    shortStoryState.inputAnalysisRawOutput = data.inputAnalysisRawOutput || defaults.inputAnalysisRawOutput;
    shortStoryState.fusionRawOutput = data.fusionRawOutput || defaults.fusionRawOutput;
    shortStoryState.synopsisRawOutput = data.synopsisRawOutput || defaults.synopsisRawOutput;
    shortStoryState.outlineRawOutput = data.outlineRawOutput || defaults.outlineRawOutput;
    shortStoryState.qualityReportDraft = data.qualityReportDraft || defaults.qualityReportDraft;
    shortStoryState.qualityPassedDraft = Boolean(data.qualityPassedDraft);
    shortStoryState.qualitySimpleFixes = Array.isArray(data.qualitySimpleFixes) ? data.qualitySimpleFixes : defaults.qualitySimpleFixes;
    shortStoryState.coherenceReportDraft = data.coherenceReportDraft || defaults.coherenceReportDraft;
    shortStoryState.coherencePassedDraft = Boolean(data.coherencePassedDraft);
    shortStoryState.titleRawOutput = data.titleRawOutput || defaults.titleRawOutput;
    shortStoryState.titleFeedback = data.titleFeedback || defaults.titleFeedback;
    shortStoryState.synopsisFeedback = data.synopsisFeedback || defaults.synopsisFeedback;
    shortStoryState.qualitySuggestedChapters = Array.isArray(data.qualitySuggestedChapters) ? data.qualitySuggestedChapters : defaults.qualitySuggestedChapters;
    shortStoryState.coherenceSuggestedChapters = Array.isArray(data.coherenceSuggestedChapters) ? data.coherenceSuggestedChapters : defaults.coherenceSuggestedChapters;
    shortStoryState.outlineRevisionFeedback = data.outlineRevisionFeedback || defaults.outlineRevisionFeedback;
    shortStoryState.partialChapterGeneration = data.partialChapterGeneration && typeof data.partialChapterGeneration === 'object'
        ? data.partialChapterGeneration
        : defaults.partialChapterGeneration;
    shortStoryState.activeView = data.activeView === 'final' ? 'final' : 'panel';
    shortStoryState.collapsedSections = data.collapsedSections && typeof data.collapsedSections === 'object' ? data.collapsedSections : defaults.collapsedSections;
    shortStoryState.draftSavedAt = Number(data.draftSavedAt || 0);
    shortStoryState.loadingAction = defaults.loadingAction;
    shortStoryState.loadingStartedAt = defaults.loadingStartedAt;
    shortStoryState.batchGenerationProgress = defaults.batchGenerationProgress;
    shortStoryState.highlightSection = defaults.highlightSection;
}

function readShortStoryLocalCache(projectId = getShortStoryActiveProjectId()) {
    const preserveTransientState = shortStoryState.loadedProjectId === projectId;
    const transientLoadingAction = preserveTransientState ? shortStoryState.loadingAction : '';
    const transientHighlightSection = preserveTransientState ? shortStoryState.highlightSection : '';
    const storageKey = getShortStoryStorageKey(projectId);
    let raw = localStorage.getItem(storageKey);

    if (!raw) {
        const legacyRaw = localStorage.getItem(SHORT_STORY_LEGACY_STORAGE_KEY);
        if (legacyRaw) {
            raw = legacyRaw;
            if (projectId) {
                localStorage.setItem(storageKey, legacyRaw);
                localStorage.removeItem(SHORT_STORY_LEGACY_STORAGE_KEY);
            }
        }
    }

    let parsed = {};
    if (raw) {
        try {
            parsed = JSON.parse(raw) || {};
        } catch (e) {
            console.error('[ShortStory] 解析本地存储失败:', e);
        }
    }

    return { parsed, preserveTransientState, transientLoadingAction, transientHighlightSection, storageKey };
}

function loadShortStoryDataForCurrentProject() {
    const projectId = getShortStoryActiveProjectId();
    const { parsed, preserveTransientState, transientLoadingAction, transientHighlightSection } = readShortStoryLocalCache(projectId);

    applyShortStoryProjectState(parsed);
    if (preserveTransientState) {
        shortStoryState.loadingAction = transientLoadingAction;
        shortStoryState.highlightSection = transientHighlightSection;
    }

    shortStoryState.loadedProjectId = projectId;
}

function buildShortStoryPersistedPayload() {
    return {
        workflow: shortStoryState.workflow,
        selectedApiConfigId: shortStoryState.selectedApiConfigId,
        selectedModel: shortStoryState.selectedModel,
        draftSourceInput: shortStoryState.draftSourceInput,
        draftKeywords: shortStoryState.draftKeywords,
        draftTotalWords: shortStoryState.draftTotalWords,
        draftChapterWords: shortStoryState.draftChapterWords,
        draftChapterWordsCustomized: shortStoryState.draftChapterWordsCustomized,
        draftCategory: shortStoryState.draftCategory,
        inputAnalysisRawOutput: shortStoryState.inputAnalysisRawOutput,
        fusionRawOutput: shortStoryState.fusionRawOutput,
        synopsisRawOutput: shortStoryState.synopsisRawOutput,
        outlineRawOutput: shortStoryState.outlineRawOutput,
        qualityReportDraft: shortStoryState.qualityReportDraft,
        qualityPassedDraft: shortStoryState.qualityPassedDraft,
        qualitySimpleFixes: shortStoryState.qualitySimpleFixes,
        coherenceReportDraft: shortStoryState.coherenceReportDraft,
        coherencePassedDraft: shortStoryState.coherencePassedDraft,
        titleRawOutput: shortStoryState.titleRawOutput,
        titleFeedback: shortStoryState.titleFeedback,
        synopsisFeedback: shortStoryState.synopsisFeedback,
        qualitySuggestedChapters: shortStoryState.qualitySuggestedChapters,
        coherenceSuggestedChapters: shortStoryState.coherenceSuggestedChapters,
        outlineRevisionFeedback: shortStoryState.outlineRevisionFeedback,
        partialChapterGeneration: shortStoryState.partialChapterGeneration,
        activeView: shortStoryState.activeView,
        collapsedSections: shortStoryState.collapsedSections,
        draftSavedAt: shortStoryState.draftSavedAt
    };
}

async function persistShortStoryProjectState() {
    const projectId = getShortStoryActiveProjectId();
    if (!projectId) return;

    try {
        await apiCall(`/api/project-state/${SHORT_STORY_PROJECT_STATE_KEY}`, 'POST', {
            data: buildShortStoryPersistedPayload()
        });
    } catch (e) {
        console.error('[ShortStory] 项目状态持久化失败:', e);
    }
}

function clearQueuedShortStoryProjectStateSave() {
    if (shortStoryPersistTimer) {
        clearTimeout(shortStoryPersistTimer);
        shortStoryPersistTimer = null;
    }
}

function queueShortStoryProjectStateSave() {
    clearQueuedShortStoryProjectStateSave();
    shortStoryPersistTimer = setTimeout(() => {
        shortStoryPersistTimer = null;
        persistShortStoryProjectState();
    }, 180);
}

async function hydrateShortStoryProjectState(force = false) {
    const projectId = getShortStoryActiveProjectId();
    if (!projectId) {
        loadShortStoryDataForCurrentProject();
        return;
    }

    if (!force && shortStoryState.loadedProjectId === projectId && shortStoryState.workflow) {
        return;
    }

    const { parsed: localCache, preserveTransientState, transientLoadingAction, transientHighlightSection, storageKey } = readShortStoryLocalCache(projectId);
    let projectState = null;

    try {
        const response = await apiCall(`/api/project-state/${SHORT_STORY_PROJECT_STATE_KEY}`, 'GET');
        projectState = response?.data || null;
    } catch (e) {
        console.error('[ShortStory] 读取项目状态失败，回退本地缓存:', e);
    }

    const nextState = projectState && typeof projectState === 'object' ? projectState : localCache;
    applyShortStoryProjectState(nextState || {});

    if (preserveTransientState) {
        shortStoryState.loadingAction = transientLoadingAction;
        shortStoryState.highlightSection = transientHighlightSection;
    }

    shortStoryState.loadedProjectId = projectId;
    localStorage.setItem(storageKey, JSON.stringify(buildShortStoryPersistedPayload()));

    if (!projectState && localCache && Object.keys(localCache).length > 0) {
        queueShortStoryProjectStateSave();
    }
}

function saveShortStoryData() {
    const projectId = getShortStoryActiveProjectId();
    const storageKey = getShortStoryStorageKey(projectId);
    localStorage.setItem(storageKey, JSON.stringify(buildShortStoryPersistedPayload()));
    queueShortStoryProjectStateSave();
}

async function persistShortStoryProjectStateNow() {
    clearQueuedShortStoryProjectStateSave();
    await persistShortStoryProjectState();
}

async function resetShortStoryProjectState() {
    const projectId = getShortStoryActiveProjectId();
    const storageKey = getShortStoryStorageKey(projectId);

    clearQueuedShortStoryProjectStateSave();
    applyShortStoryProjectState(createShortStoryProjectState());
    shortStoryState.loadedProjectId = projectId;
    localStorage.setItem(storageKey, JSON.stringify(buildShortStoryPersistedPayload()));
    await persistShortStoryProjectState();
}

function toggleShortStorySection(sectionId) {
    const currentSectionId = getShortStoryCurrentSectionId();
    if (sectionId === currentSectionId) {
        return;
    }

    shortStoryState.collapsedSections[sectionId] = !shortStoryState.collapsedSections[sectionId];
    saveShortStoryData();
    renderShortStoryInterface();
}

function isShortStorySectionCollapsed(sectionId, currentSectionId) {
    if (sectionId === currentSectionId || sectionId === shortStoryState.highlightSection) {
        return false;
    }
    return Boolean(shortStoryState.collapsedSections[sectionId]);
}

function markShortStoryDraftSaved() {
    shortStoryState.draftSavedAt = Date.now();
    saveShortStoryData();
}

function resetShortStoryWorkflowArtifacts() {
    shortStoryState.inputAnalysisRawOutput = '';
    shortStoryState.fusionRawOutput = '';
    shortStoryState.synopsisRawOutput = '';
    shortStoryState.outlineRawOutput = '';
    shortStoryState.qualityReportDraft = '';
    shortStoryState.qualityPassedDraft = false;
    shortStoryState.qualitySimpleFixes = [];
    shortStoryState.coherenceReportDraft = '';
    shortStoryState.coherencePassedDraft = false;
    shortStoryState.titleRawOutput = '';
    shortStoryState.synopsisFeedback = '';
    shortStoryState.titleFeedback = '';
    shortStoryState.outlineRevisionFeedback = '';
    shortStoryState.qualitySuggestedChapters = [];
    shortStoryState.coherenceSuggestedChapters = [];
    shortStoryState.partialChapterGeneration = null;
}

function resetShortStoryReviewArtifacts() {
    shortStoryState.qualityReportDraft = '';
    shortStoryState.qualityPassedDraft = false;
    shortStoryState.qualitySimpleFixes = [];
    shortStoryState.coherenceReportDraft = '';
    shortStoryState.coherencePassedDraft = false;
    shortStoryState.titleRawOutput = '';
    shortStoryState.qualitySuggestedChapters = [];
    shortStoryState.coherenceSuggestedChapters = [];
}

function parseShortStoryKeywords() {
    const raw = document.getElementById('short-story-keywords')?.value || '';
    return raw.split(/[\n,，、;；|/]+/).map((item) => item.trim()).filter(Boolean);
}

function getRecommendedShortStoryChapterWords(totalWords) {
    return Number(totalWords || 0) >= 8000 ? 1000 : 800;
}

function syncShortStoryWorkflowDrafts() {
    const workflow = getCurrentShortStoryWorkflow();
    const sourceInput = document.getElementById('short-story-keywords')?.value || shortStoryState.draftSourceInput || shortStoryState.draftKeywords || '';
    const totalWords = parseInt(document.getElementById('short-story-total-words')?.value || `${shortStoryState.draftTotalWords || 5000}`, 10);
    const recommendedChapterWords = getRecommendedShortStoryChapterWords(totalWords);
    const chapterWords = parseInt(document.getElementById('short-story-chapter-words')?.value || `${shortStoryState.draftChapterWords || recommendedChapterWords}`, 10);
    const category = normalizeShortStoryCategory(document.getElementById('short-story-category')?.value || shortStoryState.draftCategory);

    shortStoryState.draftSourceInput = sourceInput;
    shortStoryState.draftKeywords = sourceInput;
    shortStoryState.draftTotalWords = Number.isFinite(totalWords) ? totalWords : 5000;
    shortStoryState.draftChapterWords = Number.isFinite(chapterWords) ? chapterWords : recommendedChapterWords;
    shortStoryState.draftCategory = category;

    if (!workflow) return;

    workflow.raw_input = sourceInput;
    workflow.legacy_keywords = parseShortStoryKeywords();
    workflow.keywords = Array.isArray(workflow.keywords) && workflow.keywords.length > 0 ? workflow.keywords : workflow.legacy_keywords;
    workflow.target_total_words = shortStoryState.draftTotalWords;
    const resolvedChapterWords = shortStoryState.draftChapterWordsCustomized ? shortStoryState.draftChapterWords : recommendedChapterWords;
    workflow.custom_chapter_word_target = shortStoryState.draftChapterWordsCustomized ? resolvedChapterWords : null;
    workflow.chapter_word_target = resolvedChapterWords;
    workflow.chapter_word_min = Math.max(300, resolvedChapterWords - 100);
    workflow.chapter_word_max = Math.min(5000, resolvedChapterWords + 100);
    workflow.category = category;
    workflow.tone = category;

    const outlineText = document.getElementById('short-story-outline-text')?.value;
    if (typeof outlineText === 'string') {
        workflow.outline_text = outlineText;
    }

    shortStoryState.synopsisFeedback = document.getElementById('short-story-synopsis-feedback')?.value || shortStoryState.synopsisFeedback || '';
    shortStoryState.titleFeedback = document.getElementById('short-story-title-feedback')?.value || shortStoryState.titleFeedback || '';
    shortStoryState.outlineRevisionFeedback = document.getElementById('short-story-outline-feedback')?.value || '';
    shortStoryState.qualityReportDraft = document.getElementById('short-story-quality-report')?.value || shortStoryState.qualityReportDraft || '';
    shortStoryState.coherenceReportDraft = document.getElementById('short-story-coherence-report')?.value || shortStoryState.coherenceReportDraft || '';
}

function collectShortStoryChaptersFromEditor() {
    const workflow = getCurrentShortStoryWorkflow();
    const blueprints = workflow?.chapter_blueprints || [];
    return blueprints.map((blueprint) => ({
        chapter_number: blueprint.chapter_number,
        title: blueprint.title || `第${blueprint.chapter_number}章`,
        content: document.querySelector(`.short-story-chapter-content[data-chapter="${blueprint.chapter_number}"]`)?.value?.trim() || ''
    })).filter((item) => item.content);
}

window.SHORT_STORY_MAIN_CATEGORIES = SHORT_STORY_MAIN_CATEGORIES;
window.SHORT_STORY_PROJECT_STATE_KEY = SHORT_STORY_PROJECT_STATE_KEY;
window.shortStoryState = shortStoryState;
window.createShortStoryProjectState = createShortStoryProjectState;
window.parseShortStoryBlueprintsFromOutline = parseShortStoryBlueprintsFromOutline;
window.repairShortStoryWorkflowBlueprints = repairShortStoryWorkflowBlueprints;
window.getShortStoryStorageKey = getShortStoryStorageKey;
window.applyShortStoryProjectState = applyShortStoryProjectState;
window.readShortStoryLocalCache = readShortStoryLocalCache;
window.loadShortStoryDataForCurrentProject = loadShortStoryDataForCurrentProject;
window.buildShortStoryPersistedPayload = buildShortStoryPersistedPayload;
window.persistShortStoryProjectState = persistShortStoryProjectState;
window.clearQueuedShortStoryProjectStateSave = clearQueuedShortStoryProjectStateSave;
window.queueShortStoryProjectStateSave = queueShortStoryProjectStateSave;
window.hydrateShortStoryProjectState = hydrateShortStoryProjectState;
window.saveShortStoryData = saveShortStoryData;
window.persistShortStoryProjectStateNow = persistShortStoryProjectStateNow;
window.resetShortStoryProjectState = resetShortStoryProjectState;
window.toggleShortStorySection = toggleShortStorySection;
window.isShortStorySectionCollapsed = isShortStorySectionCollapsed;
window.markShortStoryDraftSaved = markShortStoryDraftSaved;
window.resetShortStoryWorkflowArtifacts = resetShortStoryWorkflowArtifacts;
window.resetShortStoryReviewArtifacts = resetShortStoryReviewArtifacts;
window.normalizeShortStoryCategory = normalizeShortStoryCategory;
window.parseShortStoryKeywords = parseShortStoryKeywords;
window.getRecommendedShortStoryChapterWords = getRecommendedShortStoryChapterWords;
window.syncShortStoryWorkflowDrafts = syncShortStoryWorkflowDrafts;
window.collectShortStoryChaptersFromEditor = collectShortStoryChaptersFromEditor;
