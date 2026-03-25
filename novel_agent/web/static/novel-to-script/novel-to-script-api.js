/**
 * 文思Agent - 小说转剧本接口层
 */

function getNovelToScriptFallbackCapabilities() {
    return {
        defaults: {
            script_style: 'scene_block_webnovel_script',
            convert_mode: 'auto',
            scene_density: 'medium',
            dialogue_ratio: 'medium',
            keep_voice_style: true,
            human_name_strategy: 'keep_original'
        },
        options: {
            script_styles: [
                { value: 'scene_block_webnovel_script', label: '网文场景台本' },
                { value: 'dialogue_enhanced_script', label: '对话强化版' },
                { value: 'web_short_drama_script', label: '网文短剧版' }
            ],
            convert_modes: [
                { value: 'auto', label: '自动识别（推荐）' },
                { value: 'full_text', label: '单次转换' },
                { value: 'chapterwise', label: '按章节转换' },
                { value: 'batchwise', label: '批量转换' }
            ],
            scene_densities: [
                { value: 'low', label: '低' },
                { value: 'medium', label: '中' },
                { value: 'high', label: '高' }
            ],
            dialogue_ratios: [
                { value: 'low', label: '低' },
                { value: 'medium', label: '中' },
                { value: 'high', label: '高' }
            ],
            human_name_strategies: [
                { value: 'keep_original', label: '保留原名' },
                { value: 'soft_correct', label: '模糊修正' }
            ]
        },
        strategy: {
            single_pass_max_words: 15000,
            chapterwise_max_words: 80000,
            batch_target_words: 12000,
            chapter_split_words: 18000
        }
    };
}

async function loadNovelToScriptCapabilities() {
    if (novelToScriptState.capabilities) {
        return novelToScriptState.capabilities;
    }

    try {
        const response = await apiCall('/api/novel-to-script/capabilities', 'GET');
        novelToScriptState.capabilities = response?.data || getNovelToScriptFallbackCapabilities();
    } catch (e) {
        console.error('[NovelToScript] 加载能力配置失败，使用默认值:', e);
        novelToScriptState.capabilities = getNovelToScriptFallbackCapabilities();
    }
    return novelToScriptState.capabilities;
}

async function loadGlobalApiConfigForNovelToScript() {
    try {
        const configsData = await apiCall('/api/api-configs', 'GET');
        const globalConfig = await apiCall('/api/global-config', 'GET');

        novelToScriptState.apiConfigs = configsData.configs || [];
        novelToScriptState.activeConfigId = configsData.active_config_id || '';
        novelToScriptState.globalModel = globalConfig?.model || '';
        novelToScriptState.globalConfigured = novelToScriptState.apiConfigs.length > 0 || Boolean(globalConfig?.is_configured);

        if (!novelToScriptState.selectedApiConfigId && novelToScriptState.activeConfigId) {
            novelToScriptState.selectedApiConfigId = novelToScriptState.activeConfigId;
        }

        if (!novelToScriptState.selectedModel) {
            const config = novelToScriptState.apiConfigs.find((item) => item.id === novelToScriptState.selectedApiConfigId);
            novelToScriptState.selectedModel = config?.models?.[0] || novelToScriptState.globalModel || '';
        }
    } catch (e) {
        console.error('[NovelToScript] 加载API配置失败:', e);
        novelToScriptState.apiConfigs = [];
        novelToScriptState.activeConfigId = '';
        novelToScriptState.globalModel = '';
        novelToScriptState.globalConfigured = false;
    }
}

function renderNovelToScriptModelOptions(configId, selectedModel) {
    const config = novelToScriptState.apiConfigs.find((item) => item.id === configId);
    const models = Array.isArray(config?.models) ? config.models.filter(Boolean) : [];

    if (models.length > 0) {
        return models.map((model) => `<option value="${escapeHtml(model)}" ${selectedModel === model ? 'selected' : ''}>${escapeHtml(model)}</option>`).join('');
    }

    if (novelToScriptState.globalModel) {
        return `<option value="${escapeHtml(novelToScriptState.globalModel)}" selected>${escapeHtml(novelToScriptState.globalModel)}（全局模型）</option>`;
    }

    return '<option value="">-- 请先配置模型 --</option>';
}

function getSelectedApiConfigIdForNovelToScript() {
    return document.getElementById('novel-to-script-api-config')?.value || novelToScriptState.selectedApiConfigId || '';
}

function getSelectedModelForNovelToScript() {
    return document.getElementById('novel-to-script-model')?.value || novelToScriptState.selectedModel || '';
}

async function importNovelToScriptFile(file) {
    const formData = new FormData();
    formData.append('novel_file', file);
    const response = await apiFormCall('/api/novel-to-script/import', formData);
    const data = response?.data || {};
    novelToScriptState.sourceType = data.source_type || 'file';
    novelToScriptState.sourceFilename = data.source_filename || file.name || '';
    novelToScriptState.sourceText = data.source_text || '';
    novelToScriptState.sourceChapters = Array.isArray(data.source_chapters) ? data.source_chapters : [];
    novelToScriptState.analysis = data.analysis || null;
    novelToScriptState.conversionPlan = null;
    novelToScriptState.activeView = 'workbench';
    novelToScriptState.selectedSceneIndex = 0;
    saveNovelToScriptData();
    await persistNovelToScriptProjectStateNow();
    return response;
}

async function convertNovelToScript() {
    if (!String(novelToScriptState.sourceText || '').trim()) {
        throw new Error('请先粘贴小说正文或导入小说文件。');
    }

    const response = await apiCall('/api/novel-to-script/convert', 'POST', {
        source_type: novelToScriptState.sourceType,
        source_filename: novelToScriptState.sourceFilename,
        source_text: novelToScriptState.sourceText,
        source_chapters: novelToScriptState.sourceChapters,
        config: novelToScriptState.config,
        api_config_id: getSelectedApiConfigIdForNovelToScript(),
        model: getSelectedModelForNovelToScript(),
        title: novelToScriptState.sourceFilename || '小说转剧本'
    });

    const data = response?.data || {};
    const source = data.source || {};
    novelToScriptState.sourceType = source.source_type || novelToScriptState.sourceType;
    novelToScriptState.sourceFilename = source.source_filename || novelToScriptState.sourceFilename;
    novelToScriptState.sourceText = source.source_text || novelToScriptState.sourceText;
    novelToScriptState.sourceChapters = Array.isArray(source.source_chapters) ? source.source_chapters : novelToScriptState.sourceChapters;
    novelToScriptState.analysis = data.analysis || null;
    novelToScriptState.conversionPlan = data.conversion_plan || null;
    novelToScriptState.result = data.result || null;
    novelToScriptState.activeView = 'result';
    novelToScriptState.resultTab = 'text';
    novelToScriptState.selectedSceneIndex = 0;
    saveNovelToScriptData();
    await persistNovelToScriptProjectStateNow();
    return response;
}

async function reconvertNovelToScriptBatch(batchNumber) {
    if (!String(novelToScriptState.sourceText || '').trim()) {
        throw new Error('当前没有可用于重转的原始小说内容。');
    }
    const response = await apiCall('/api/novel-to-script/reconvert-batch', 'POST', {
        source_type: novelToScriptState.sourceType,
        source_filename: novelToScriptState.sourceFilename,
        source_text: novelToScriptState.sourceText,
        source_chapters: novelToScriptState.sourceChapters,
        config: novelToScriptState.config,
        api_config_id: getSelectedApiConfigIdForNovelToScript(),
        model: getSelectedModelForNovelToScript(),
        batch_number: Number(batchNumber || 0),
        existing_batches: Array.isArray(novelToScriptState.result?.batches) ? novelToScriptState.result.batches : []
    });

    const data = response?.data || {};
    novelToScriptState.analysis = data.analysis || novelToScriptState.analysis;
    novelToScriptState.conversionPlan = data.conversion_plan || novelToScriptState.conversionPlan;
    novelToScriptState.result = data.result || novelToScriptState.result;
    novelToScriptState.activeView = 'result';
    saveNovelToScriptData();
    await persistNovelToScriptProjectStateNow();
    return response;
}

async function exportNovelToScriptFile(format) {
    const result = novelToScriptState.result;
    if (!result?.formatted_text && !result?.full_text) {
        throw new Error('请先生成剧本结果后再导出。');
    }

    const response = await fetch(`/api/novel-to-script/export?format=${encodeURIComponent(format)}`, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({
            title: novelToScriptState.sourceFilename ? novelToScriptState.sourceFilename.replace(/\.[^.]+$/, '') : '小说转剧本',
            result
        })
    });

    if (!response.ok) {
        const payload = await response.json().catch(() => ({}));
        throw new Error(payload.detail || payload.error || '导出失败');
    }

    const blob = await response.blob();
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement('a');
    anchor.href = url;
    anchor.download = `novel-to-script.${format}`;
    document.body.appendChild(anchor);
    anchor.click();
    document.body.removeChild(anchor);
    URL.revokeObjectURL(url);
}

window.loadNovelToScriptCapabilities = loadNovelToScriptCapabilities;
window.loadGlobalApiConfigForNovelToScript = loadGlobalApiConfigForNovelToScript;
window.renderNovelToScriptModelOptions = renderNovelToScriptModelOptions;
window.getSelectedApiConfigIdForNovelToScript = getSelectedApiConfigIdForNovelToScript;
window.getSelectedModelForNovelToScript = getSelectedModelForNovelToScript;
window.importNovelToScriptFile = importNovelToScriptFile;
window.convertNovelToScript = convertNovelToScript;
window.reconvertNovelToScriptBatch = reconvertNovelToScriptBatch;
window.exportNovelToScriptFile = exportNovelToScriptFile;
