/**
 * 文思Agent - 设置模块入口
 */

function renderSettings() {
    updateBreadcrumbs(['设置']);
    renderSettingsShell();
    loadThemeSettings();
}

function loadSettingsTab(tabName) {
    switch (tabName) {
        case 'theme':
            loadThemeSettings();
            break;
        case 'api':
            loadGlobalAPISettings();
            break;
        case 'agents':
            loadAgentSettings();
            break;
        case 'knowledge':
            loadKnowledgeBaseSettings();
            break;
        case 'regex':
            loadRegexRulesSettings();
            break;
        case 'skills':
        case 'trends':
            loadSkillsSettings();
            break;
        case 'backup':
            loadBackupSettings();
            break;
        case 'resources':
            loadResourcesSettings();
            break;
        case 'writing':
            loadWritingSettings();
            break;
    }
}

window.renderSettings = renderSettings;
window.loadSettingsTab = loadSettingsTab;
window.loadThemeSettings = loadThemeSettings;
window.loadGlobalAPISettingsModern = loadGlobalAPISettings;
window.loadGlobalAPISettings = loadGlobalAPISettings;
window.loadAgentSettings = loadAgentSettings;
window.loadKnowledgeBaseSettings = loadKnowledgeBaseSettings;
window.loadRegexRulesSettings = loadRegexRulesSettings;
window.loadSkillsSettings = loadSkillsSettings;

console.log('[app-settings.js] 设置模块入口已加载');
