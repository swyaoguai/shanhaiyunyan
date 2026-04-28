/**
 * 文思Agent - 设置页共享辅助函数
 */

let currentApiConfigs = [];
let currentActiveConfigId = '';
let currentActiveModel = '';
let editingConfigId = null;

let agentPageApiConfigs = [];
let agentPageActiveConfigId = '';
let agentSettingsShowAdvanced = false;

function renderSettingsLoadingState() {
    return `
        <div class="settings-loading-state">
            <i class="ri-loader-4-line"></i>
        </div>
    `;
}

function renderSettingsErrorState(message) {
    return `
        <div class="settings-error-state">
            <div>
                <i class="ri-error-warning-line"></i>
                <p class="settings-subtitle settings-subtitle--md" style="margin-top: 16px;">${message}</p>
            </div>
        </div>
    `;
}

function renderSettingsShell() {
    ui.workspace.innerHTML = `
        <div class="settings-container settings-shell">
            <div id="settings-content" class="settings-content"></div>
        </div>
    `;
}

function ensureSettingsContentRoot() {
    let content = document.getElementById('settings-content');

    if (!content) {
        renderSettingsShell();
        content = document.getElementById('settings-content');
    }

    return content;
}

function safeText(value, fallback = '') {
    return escapeHtml(value === null || value === undefined ? fallback : String(value));
}

function safeAttr(value, fallback = '') {
    return safeText(value, fallback);
}

function safeHostText(apiBase, fallback = '未设置') {
    return safeText(window.safeHostname ? window.safeHostname(apiBase, fallback) : (apiBase || fallback));
}

function safeErrorText(error, fallback = '未知错误') {
    return safeText(error?.message || fallback);
}

window.renderSettingsShell = renderSettingsShell;
window.ensureSettingsContentRoot = ensureSettingsContentRoot;
window.renderSettingsLoadingState = renderSettingsLoadingState;
window.renderSettingsErrorState = renderSettingsErrorState;
window.safeText = safeText;
window.safeAttr = safeAttr;
window.safeHostText = safeHostText;
window.safeErrorText = safeErrorText;
window.agentSettingsShowAdvanced = agentSettingsShowAdvanced;
