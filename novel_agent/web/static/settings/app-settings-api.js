/**
 * 文思Agent - 设置页接口包装
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
    await apiCall('/api/api-configs/active', 'POST', {
        config_id: configId,
        model
    });

    currentActiveConfigId = configId;
    currentActiveModel = model;
}

async function testApiConnection(configId, model) {
    const selectedConfig = currentApiConfigs.find((item) => item.id === configId);

    if (!selectedConfig) {
        throw new Error('请先选择一个配置');
    }

    return apiCall('/api/test-connection', 'POST', {
        api_base: selectedConfig.api_base,
        config_id: configId,
        model: model || (selectedConfig.models ? selectedConfig.models[0] : '')
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
    const [config, stats] = await Promise.all([
        apiCall('/api/knowledge-base/config'),
        apiCall('/api/knowledge-base/stats')
    ]);

    return { config, stats };
}

async function testKnowledgeBaseConnection(payload) {
    return apiCall('/api/knowledge-base/test-embedding', 'POST', payload);
}

async function saveKnowledgeBaseConfig(payload) {
    return apiCall('/api/knowledge-base/config', 'POST', payload);
}

async function clearKnowledgeBaseData(payload) {
    return apiCall('/api/knowledge-base/clear', 'POST', payload);
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
window.clearKnowledgeBaseData = clearKnowledgeBaseData;
window.fetchSkillsSettingsData = fetchSkillsSettingsData;
window.deleteSkill = deleteSkill;
window.saveSkillsConfig = saveSkillsConfig;
