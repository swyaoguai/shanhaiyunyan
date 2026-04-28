/**
 * 文思Agent - 小说转剧本状态层
 */

const NOVEL_TO_SCRIPT_PROJECT_STATE_KEY = 'novel_to_script_draft';
const NOVEL_TO_SCRIPT_LEGACY_STORAGE_KEY = 'novel_to_script_data';

let novelToScriptPersistTimer = null;

function createNovelToScriptProjectState() {
    return {
        sourceType: 'paste',
        sourceFilename: '',
        sourceText: '',
        sourceChapters: [],
        config: {
            script_style: 'scene_block_webnovel_script',
            convert_mode: 'auto',
            scene_density: 'medium',
            dialogue_ratio: 'medium',
            keep_voice_style: true,
            human_name_strategy: 'keep_original'
        },
        analysis: null,
        conversionPlan: null,
        result: null,
        activeView: 'workbench',
        resultTab: 'text',
        selectedSceneIndex: 0,
        draftSavedAt: 0,
        loadingAction: ''
    };
}

const novelToScriptState = {
    apiConfigs: [],
    activeConfigId: '',
    globalModel: '',
    globalConfigured: false,
    capabilities: null,
    loadedProjectId: '',
    selectedApiConfigId: '',
    selectedModel: '',
    ...createNovelToScriptProjectState()
};

function getNovelToScriptActiveProjectId() {
    if (typeof getActiveProjectId === 'function') {
        return getActiveProjectId() || '';
    }
    return store?.currentProjectId || '';
}

function getNovelToScriptStorageKey(projectId = getNovelToScriptActiveProjectId()) {
    return projectId ? `novel_to_script_data_${projectId}` : NOVEL_TO_SCRIPT_LEGACY_STORAGE_KEY;
}

function applyNovelToScriptProjectState(data = {}) {
    const defaults = createNovelToScriptProjectState();

    novelToScriptState.sourceType = data.sourceType || defaults.sourceType;
    novelToScriptState.sourceFilename = data.sourceFilename || defaults.sourceFilename;
    novelToScriptState.sourceText = data.sourceText || defaults.sourceText;
    novelToScriptState.sourceChapters = Array.isArray(data.sourceChapters) ? data.sourceChapters : defaults.sourceChapters;
    novelToScriptState.config = {
        ...defaults.config,
        ...(data.config && typeof data.config === 'object' ? data.config : {})
    };
    novelToScriptState.analysis = data.analysis && typeof data.analysis === 'object' ? data.analysis : defaults.analysis;
    novelToScriptState.conversionPlan = data.conversionPlan && typeof data.conversionPlan === 'object' ? data.conversionPlan : defaults.conversionPlan;
    novelToScriptState.result = data.result && typeof data.result === 'object' ? data.result : defaults.result;
    novelToScriptState.activeView = data.activeView === 'result' ? 'result' : 'workbench';
    novelToScriptState.resultTab = ['text', 'scenes', 'characters'].includes(data.resultTab) ? data.resultTab : defaults.resultTab;
    novelToScriptState.selectedSceneIndex = Math.max(0, Number(data.selectedSceneIndex || 0));
    novelToScriptState.draftSavedAt = Number(data.draftSavedAt || 0);
    novelToScriptState.loadingAction = defaults.loadingAction;
    novelToScriptState.selectedApiConfigId = data.selectedApiConfigId || novelToScriptState.selectedApiConfigId || '';
    novelToScriptState.selectedModel = data.selectedModel || novelToScriptState.selectedModel || '';
}

function buildNovelToScriptPersistedPayload() {
    return {
        sourceType: novelToScriptState.sourceType,
        sourceFilename: novelToScriptState.sourceFilename,
        sourceText: novelToScriptState.sourceText,
        sourceChapters: novelToScriptState.sourceChapters,
        config: novelToScriptState.config,
        analysis: novelToScriptState.analysis,
        conversionPlan: novelToScriptState.conversionPlan,
        result: novelToScriptState.result,
        activeView: novelToScriptState.activeView,
        resultTab: novelToScriptState.resultTab,
        selectedSceneIndex: novelToScriptState.selectedSceneIndex,
        draftSavedAt: novelToScriptState.draftSavedAt,
        selectedApiConfigId: novelToScriptState.selectedApiConfigId,
        selectedModel: novelToScriptState.selectedModel
    };
}

function readNovelToScriptLocalCache(projectId = getNovelToScriptActiveProjectId()) {
    const preserveTransientState = novelToScriptState.loadedProjectId === projectId;
    const transientLoadingAction = preserveTransientState ? novelToScriptState.loadingAction : '';
    const storageKey = getNovelToScriptStorageKey(projectId);
    let raw = localStorage.getItem(storageKey);

    if (!raw) {
        const legacyRaw = localStorage.getItem(NOVEL_TO_SCRIPT_LEGACY_STORAGE_KEY);
        if (legacyRaw) {
            raw = legacyRaw;
            if (projectId) {
                localStorage.setItem(storageKey, legacyRaw);
                localStorage.removeItem(NOVEL_TO_SCRIPT_LEGACY_STORAGE_KEY);
            }
        }
    }

    let parsed = {};
    if (raw) {
        try {
            parsed = JSON.parse(raw) || {};
        } catch (e) {
            console.error('[NovelToScript] 解析本地缓存失败:', e);
        }
    }

    return { parsed, preserveTransientState, transientLoadingAction, storageKey };
}

function loadNovelToScriptDataForCurrentProject() {
    const projectId = getNovelToScriptActiveProjectId();
    const { parsed, preserveTransientState, transientLoadingAction } = readNovelToScriptLocalCache(projectId);

    applyNovelToScriptProjectState(parsed);
    if (preserveTransientState) {
        novelToScriptState.loadingAction = transientLoadingAction;
    }

    novelToScriptState.loadedProjectId = projectId;
}

async function persistNovelToScriptProjectState() {
    const projectId = getNovelToScriptActiveProjectId();
    if (!projectId) return;

    try {
        await apiCall('/api/novel-to-script/state', 'POST', {
            data: buildNovelToScriptPersistedPayload()
        });
    } catch (e) {
        console.error('[NovelToScript] 项目状态持久化失败:', e);
    }
}

function clearQueuedNovelToScriptProjectStateSave() {
    if (novelToScriptPersistTimer) {
        clearTimeout(novelToScriptPersistTimer);
        novelToScriptPersistTimer = null;
    }
}

function queueNovelToScriptProjectStateSave() {
    clearQueuedNovelToScriptProjectStateSave();
    novelToScriptPersistTimer = setTimeout(() => {
        novelToScriptPersistTimer = null;
        persistNovelToScriptProjectState();
    }, 180);
}

async function hydrateNovelToScriptProjectState(force = false) {
    const projectId = getNovelToScriptActiveProjectId();
    if (!projectId) {
        loadNovelToScriptDataForCurrentProject();
        return;
    }

    if (!force && novelToScriptState.loadedProjectId === projectId && (novelToScriptState.sourceText || novelToScriptState.result)) {
        return;
    }

    const { parsed: localCache, preserveTransientState, transientLoadingAction, storageKey } = readNovelToScriptLocalCache(projectId);
    let projectState = null;

    try {
        const response = await apiCall('/api/novel-to-script/state', 'GET');
        projectState = response?.data || null;
    } catch (e) {
        console.error('[NovelToScript] 读取项目状态失败，回退本地缓存:', e);
    }

    const nextState = projectState && typeof projectState === 'object' ? projectState : localCache;
    applyNovelToScriptProjectState(nextState || {});
    if (preserveTransientState) {
        novelToScriptState.loadingAction = transientLoadingAction;
    }

    novelToScriptState.loadedProjectId = projectId;
    localStorage.setItem(storageKey, JSON.stringify(buildNovelToScriptPersistedPayload()));
    if (!projectState && localCache && Object.keys(localCache).length > 0) {
        queueNovelToScriptProjectStateSave();
    }
}

function saveNovelToScriptData() {
    const projectId = getNovelToScriptActiveProjectId();
    const storageKey = getNovelToScriptStorageKey(projectId);
    localStorage.setItem(storageKey, JSON.stringify(buildNovelToScriptPersistedPayload()));
    queueNovelToScriptProjectStateSave();
}

async function persistNovelToScriptProjectStateNow() {
    clearQueuedNovelToScriptProjectStateSave();
    await persistNovelToScriptProjectState();
}

async function resetNovelToScriptProjectState() {
    const projectId = getNovelToScriptActiveProjectId();
    const storageKey = getNovelToScriptStorageKey(projectId);

    clearQueuedNovelToScriptProjectStateSave();
    applyNovelToScriptProjectState(createNovelToScriptProjectState());
    novelToScriptState.loadedProjectId = projectId;
    localStorage.setItem(storageKey, JSON.stringify(buildNovelToScriptPersistedPayload()));
    await persistNovelToScriptProjectState();
}

function getNovelToScriptWordCount() {
    const source = String(novelToScriptState.sourceText || '').replace(/\s/g, '');
    return source.length;
}

function getNovelToScriptChapterCount() {
    if (Array.isArray(novelToScriptState.sourceChapters) && novelToScriptState.sourceChapters.length > 0) {
        return novelToScriptState.sourceChapters.length;
    }
    return novelToScriptState.sourceText.trim() ? 1 : 0;
}

function getNovelToScriptScenes() {
    return Array.isArray(novelToScriptState.result?.scenes) ? novelToScriptState.result.scenes : [];
}

function getNovelToScriptStrategySummary() {
    const capabilities = novelToScriptState.capabilities || {};
    const strategy = capabilities.strategy || {};
    const wordCount = getNovelToScriptWordCount();
    const chapterCount = getNovelToScriptChapterCount();
    const singleLimit = Number(strategy.single_pass_max_words || 15000);
    const chapterLimit = Number(strategy.chapterwise_max_words || 80000);
    const batchTarget = Number(strategy.batch_target_words || 12000);
    let recommendedMode = 'full_text';
    let reason = `全文约 ${wordCount} 字，适合单次转换。`;
    if (wordCount > singleLimit && chapterCount > 1 && wordCount <= chapterLimit) {
        recommendedMode = 'chapterwise';
        reason = `全文约 ${wordCount} 字，已识别 ${chapterCount} 章，推荐按章节转换。`;
    } else if (wordCount > singleLimit && (wordCount > chapterLimit || chapterCount <= 1)) {
        recommendedMode = 'batchwise';
        reason = `全文约 ${wordCount} 字，已超出单次稳定范围，推荐自动分批转换。`;
    }

    const estimatedBatches = recommendedMode === 'batchwise'
        ? Math.max(1, Math.ceil(wordCount / Math.max(batchTarget, 1)))
        : (recommendedMode === 'chapterwise' ? Math.max(chapterCount, 1) : 1);

    return {
        wordCount,
        chapterCount,
        recommendedMode,
        recommendedModeLabel: recommendedMode === 'batchwise' ? '批量转换' : (recommendedMode === 'chapterwise' ? '按章节转换' : '单次转换'),
        estimatedBatches,
        reason
    };
}

function parseNovelToScriptScenesFromText(text) {
    const normalized = String(text || '').replace(/\r\n/g, '\n').replace(/\r/g, '\n').trim();
    if (!normalized) return [];

    const blocks = normalized
        .split(/(?=^【场景[^\n]+】)/m)
        .map((block) => block.trim())
        .filter(Boolean);

    return blocks.map((block, index) => {
        const lines = block.split('\n').map((line) => line.trim()).filter(Boolean);
        const headingMatch = lines[0]?.match(/^【(场景[^：:]+)[：:]\s*(.+?)】$/);
        const scene = {
            scene_number: index + 1,
            scene_label: headingMatch?.[1] || `场景${index + 1}`,
            heading: headingMatch?.[2] || lines[0]?.replace(/[【】]/g, '') || `场景${index + 1}`,
            characters_text: '待补充',
            environment_text: '待补充',
            beats: []
        };

        lines.slice(1).forEach((line) => {
            const matched = line.match(/^([^：:]+)[：:]\s*(.*)$/);
            if (!matched) {
                scene.beats.push({ type: 'action_narration', label: '动作/旁白', text: line });
                return;
            }
            const label = matched[1].trim();
            const content = matched[2].trim();
            if (label === '人物') {
                scene.characters_text = content || '待补充';
                return;
            }
            if (label === '环境') {
                scene.environment_text = content || '待补充';
                return;
            }
            const labelMatch = label.match(/^([^（(]+?)(?:[（(](.+?)[）)])?$/);
            const baseLabel = labelMatch?.[1]?.trim() || label;
            const qualifier = labelMatch?.[2]?.trim() || '';
            if (baseLabel === '动作/旁白' || baseLabel === '动作/音效' || baseLabel === '闪回片段') {
                scene.beats.push({
                    type: baseLabel === '动作/音效' ? 'fx_line' : (baseLabel === '闪回片段' ? 'flashback_line' : 'action_narration'),
                    label: baseLabel,
                    qualifier,
                    text: content
                });
                return;
            }
            scene.beats.push({
                type: 'character_line',
                speaker: baseLabel,
                label: baseLabel,
                qualifier,
                text: content
            });
        });

        return scene;
    });
}

function buildNovelToScriptCharacterIndex(scenes) {
    const map = new Map();
    (scenes || []).forEach((scene) => {
        const sceneNumber = Number(scene.scene_number || 0);
        String(scene.characters_text || '')
            .split(/[，,、；;]/)
            .map((part) => part.trim())
            .filter(Boolean)
            .forEach((token) => {
                const matched = token.match(/^([^（(]+?)(?:[（(](.+?)[）)])?$/);
                const name = matched?.[1]?.trim() || token;
                const description = matched?.[2]?.trim() || '';
                if (!name || name === '待补充') return;
                const current = map.get(name) || {
                    name,
                    description,
                    scene_numbers: [],
                    scene_count: 0
                };
                if (!current.description && description) {
                    current.description = description;
                }
                if (sceneNumber && !current.scene_numbers.includes(sceneNumber)) {
                    current.scene_numbers.push(sceneNumber);
                }
                map.set(name, current);
            });
    });

    return Array.from(map.values())
        .map((item) => ({
            ...item,
            scene_numbers: item.scene_numbers.sort((a, b) => a - b),
            scene_count: item.scene_numbers.length
        }))
        .sort((a, b) => b.scene_count - a.scene_count || a.name.localeCompare(b.name, 'zh-CN'));
}

function buildNovelToScriptSceneOutline(scenes) {
    return (scenes || []).map((scene, index) => ({
        scene_number: Number(scene.scene_number || index + 1),
        scene_label: scene.scene_label || `场景${index + 1}`,
        heading: scene.heading || `未命名场景 ${index + 1}`,
        beat_count: Array.isArray(scene.beats) ? scene.beats.length : 0,
        characters_text: scene.characters_text || '待补充'
    }));
}

function syncNovelToScriptResultFromText(text) {
    const scenes = parseNovelToScriptScenesFromText(text);
    const characterIndex = buildNovelToScriptCharacterIndex(scenes);
    const sceneOutline = buildNovelToScriptSceneOutline(scenes);

    if (!novelToScriptState.result || typeof novelToScriptState.result !== 'object') {
        novelToScriptState.result = {};
    }

    novelToScriptState.result.formatted_text = text;
    novelToScriptState.result.full_text = text;
    novelToScriptState.result.scenes = scenes;
    novelToScriptState.result.scene_count = scenes.length;
    novelToScriptState.result.character_index = characterIndex;
    novelToScriptState.result.scene_outline = sceneOutline;
}

function getSelectedNovelToScriptScene() {
    const scenes = getNovelToScriptScenes();
    if (scenes.length === 0) return null;
    const index = Math.min(novelToScriptState.selectedSceneIndex, scenes.length - 1);
    return scenes[index] || null;
}

function markNovelToScriptDraftSaved() {
    novelToScriptState.draftSavedAt = Date.now();
    saveNovelToScriptData();
}

window.novelToScriptState = novelToScriptState;
window.getNovelToScriptScenes = getNovelToScriptScenes;
window.getSelectedNovelToScriptScene = getSelectedNovelToScriptScene;
window.getNovelToScriptWordCount = getNovelToScriptWordCount;
window.getNovelToScriptChapterCount = getNovelToScriptChapterCount;
window.getNovelToScriptStrategySummary = getNovelToScriptStrategySummary;
window.syncNovelToScriptResultFromText = syncNovelToScriptResultFromText;
window.saveNovelToScriptData = saveNovelToScriptData;
window.hydrateNovelToScriptProjectState = hydrateNovelToScriptProjectState;
window.persistNovelToScriptProjectStateNow = persistNovelToScriptProjectStateNow;
window.resetNovelToScriptProjectState = resetNovelToScriptProjectState;
window.markNovelToScriptDraftSaved = markNovelToScriptDraftSaved;
