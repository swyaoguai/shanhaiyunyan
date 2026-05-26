/**
 * 山海·云烟 - 设置页接口包装
 */

async function fetchGlobalApiSettingsData() {
    const [configsData, timeoutSettingsResp] = await Promise.all([
        apiCall('/api/api-configs'),
        apiCall('/api/timeout-settings')
    ]);

    currentApiConfigs = configsData.configs || [];
    currentActiveConfigId = configsData.active_config_id || '';
    currentActiveModel = configsData.active_model || '';

    return {
        configs: currentApiConfigs,
        activeConfigId: currentActiveConfigId,
        activeModel: currentActiveModel,
        timeoutSettings: timeoutSettingsResp?.data || {}
    };
}

async function saveActiveApiConfig(configId, model) {
    const response = await apiCall('/api/api-configs/active', 'POST', {
        config_id: configId,
        model
    });

    currentActiveConfigId = configId;
    currentActiveModel = response?.active_model || model;
    window.dispatchEvent(new CustomEvent('global-api-config-updated', {
        detail: {
            activeConfigId: response?.active_config_id || configId,
            activeModel: currentActiveModel
        }
    }));
    return response;
}

function notifyApiConfigsUpdated(detail = {}) {
    window.dispatchEvent(new CustomEvent('api-configs-updated', { detail }));
}
window.notifyApiConfigsUpdated = notifyApiConfigsUpdated;

function isBuiltinPresetApiConfig(config) {
    return Boolean(config && config.id === 'preset-tsc5' && !config.api_key_set && (!Array.isArray(config.models) || config.models.length === 0));
}

function getFirstConfiguredModel(config) {
    return Array.isArray(config?.models)
        ? String(config.models.find((item) => String(item || '').trim()) || '').trim()
        : '';
}

async function testApiConnection(configId, model) {
    const selectedConfig = currentApiConfigs.find((item) => item.id === configId);

    if (!selectedConfig) {
        throw new Error('请先选择一个配置');
    }
    if (isBuiltinPresetApiConfig(selectedConfig)) {
        throw new Error('探索仓API不能直接测试。请先新建或选择一套已填写 Key 和模型的 API 配置');
    }

    const textModels = typeof window.getTextModelsFromConfig === 'function'
        ? window.getTextModelsFromConfig(selectedConfig)
        : [];
    const chosenModel = String(model || textModels[0] || '').trim();
    if (!chosenModel) {
        throw new Error('请先选择一个文本模型');
    }

    return apiCall('/api/test-connection', 'POST', {
        api_base: selectedConfig.api_base,
        config_id: configId,
        model: chosenModel,
        api_type: selectedConfig.api_type || 'openai_chat'
    });
}

async function testImageApiConnection(configId, model) {
    const selectedConfig = currentApiConfigs.find((item) => item.id === configId);

    if (!selectedConfig) {
        throw new Error('请先选择一个配置');
    }
    if (isBuiltinPresetApiConfig(selectedConfig)) {
        throw new Error('探索仓API不能直接测试。请先新建或选择一套已填写 Key 和图片模型的 API 配置');
    }

    const imageModels = typeof window.getImageModelsFromConfig === 'function'
        ? window.getImageModelsFromConfig(selectedConfig)
        : [];
    const requestedModel = String(model || '').trim();
    const chosenModel = imageModels.includes(requestedModel)
        ? requestedModel
        : (imageModels[0] || requestedModel || getFirstConfiguredModel(selectedConfig));
    if (!chosenModel) {
        throw new Error('请先为该配置添加图片模型');
    }

    return apiCall('/api/test-image-connection', 'POST', {
        api_base: selectedConfig.api_base,
        config_id: configId,
        model: chosenModel,
        api_type: selectedConfig.api_type || 'openai_chat',
        image_api_format: selectedConfig.image_api_format || 'auto'
    });
}

async function testAgentApiConnection(agentId, configId, model) {
    const selectedConfig = agentPageApiConfigs.find((item) => item.id === configId);

    if (!selectedConfig) {
        throw new Error('请先为这个Agent选择一个API配置');
    }
    if (isBuiltinPresetApiConfig(selectedConfig)) {
        throw new Error('探索仓API不能直接测试。请先为这个Agent选择一套已填写 Key 和模型的 API 配置');
    }

    const textModels = typeof window.getTextModelsFromConfig === 'function'
        ? window.getTextModelsFromConfig(selectedConfig)
        : [];
    const chosenModel = String(model || textModels[0] || '').trim();
    if (!chosenModel) {
        throw new Error('请先为这个Agent选择文本模型');
    }

    return apiCall('/api/test-connection', 'POST', {
        api_base: selectedConfig.api_base,
        config_id: configId,
        model: chosenModel,
        api_type: selectedConfig.api_type || 'openai_chat'
    });
}

async function saveTimeoutSettings(payload) {
    return apiCall('/api/timeout-settings', 'POST', payload);
}

async function deleteApiConfig(configId) {
    return apiCall(`/api/api-configs/${configId}`, 'DELETE');
}

async function fetchModelsForApiConfig(requestData) {
    return apiCall('/api/models', 'POST', requestData);
}

async function createApiConfig(payload) {
    return apiCall('/api/api-configs', 'POST', payload);
}

async function updateApiConfig(configId, payload) {
    return apiCall(`/api/api-configs/${configId}`, 'PUT', payload);
}

async function fetchAgentSettingsData(includeAdvanced = false) {
    const [agentData, apiConfigData] = await Promise.all([
        apiCall(`/api/agents?include_advanced=${includeAdvanced ? 'true' : 'false'}`),
        apiCall('/api/api-configs')
    ]);

    agentPageApiConfigs = apiConfigData.configs || [];
    agentPageActiveConfigId = apiConfigData.active_config_id || '';

    return {
        agents: agentData.agents || [],
        apiConfigs: agentPageApiConfigs,
        activeConfigId: agentPageActiveConfigId
    };
}

async function saveAgentConfig(agentId, payload) {
    return apiCall(`/api/agents/${agentId}`, 'POST', payload);
}

async function fetchKnowledgeBaseSettingsData() {
    const [config, stats, chapterSummaryConfig, chapterSyncConfig] = await Promise.all([
        apiCall('/api/knowledge-base/config'),
        apiCall('/api/knowledge-base/stats'),
        apiCall('/api/chapter-summary-config').catch(() => ({ auto_summary_enabled: false })),
        apiCall('/api/chapter-knowledge-sync-config').catch(() => ({
            auto_vector_sync_enabled: true,
            sync_on_edit_enabled: true,
            sync_on_delete_enabled: true
        }))
    ]);

    return { config, stats, chapterSummaryConfig, chapterSyncConfig };
}

async function testKnowledgeBaseConnection(payload) {
    return apiCall('/api/knowledge-base/test-embedding', 'POST', payload);
}

async function saveKnowledgeBaseConfig(payload) {
    return apiCall('/api/knowledge-base/config', 'POST', payload);
}

async function installLocalOnnxPackage(file) {
    const formData = new FormData();
    formData.append('model_package', file);
    const response = await fetch(normalizeApiUrl('/api/knowledge-base/local-onnx/install'), {
        method: 'POST',
        body: formData
    });
    const contentType = response.headers.get('content-type') || '';
    const payload = contentType.includes('application/json')
        ? await response.json()
        : { error: await response.text() };
    if (!response.ok || payload.success === false) {
        throw new Error(payload.detail || payload.error || `HTTP ${response.status}`);
    }
    return payload;
}

async function clearKnowledgeBaseData(payload) {
    return apiCall('/api/knowledge-base/clear', 'POST', payload);
}

async function saveChapterKnowledgeSyncConfig(payload) {
    return apiCall('/api/chapter-knowledge-sync-config', 'POST', payload);
}

async function rebuildChapterKnowledgeIndex() {
    return apiCall('/api/chapter-knowledge-sync/rebuild', 'POST', {});
}

async function fetchSkillsSettingsData() {
    const skillsData = await apiCall('/api/skills', 'GET');
    return skillsData.skills || [];
}

async function deleteSkill(skillName) {
    return apiCall(`/api/skills/${skillName}`, 'DELETE');
}

async function saveSkillsConfig(skills) {
    return apiCall('/api/skills/batch-toggle', 'POST', { skills });
}

window.fetchGlobalApiSettingsData = fetchGlobalApiSettingsData;
window.saveActiveApiConfig = saveActiveApiConfig;
window.testApiConnection = testApiConnection;
window.testImageApiConnection = testImageApiConnection;
window.testAgentApiConnection = testAgentApiConnection;
window.saveTimeoutSettings = saveTimeoutSettings;
window.deleteApiConfig = deleteApiConfig;
window.fetchModelsForApiConfig = fetchModelsForApiConfig;
window.createApiConfig = createApiConfig;
window.updateApiConfig = updateApiConfig;
window.fetchAgentSettingsData = fetchAgentSettingsData;
window.saveAgentConfig = saveAgentConfig;
window.fetchKnowledgeBaseSettingsData = fetchKnowledgeBaseSettingsData;
window.testKnowledgeBaseConnection = testKnowledgeBaseConnection;
window.saveKnowledgeBaseConfig = saveKnowledgeBaseConfig;
window.installLocalOnnxPackage = installLocalOnnxPackage;
window.clearKnowledgeBaseData = clearKnowledgeBaseData;
window.saveChapterKnowledgeSyncConfig = saveChapterKnowledgeSyncConfig;
window.rebuildChapterKnowledgeIndex = rebuildChapterKnowledgeIndex;
window.fetchSkillsSettingsData = fetchSkillsSettingsData;
window.deleteSkill = deleteSkill;
window.saveSkillsConfig = saveSkillsConfig;
