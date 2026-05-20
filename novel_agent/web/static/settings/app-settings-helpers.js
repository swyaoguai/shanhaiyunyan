/**
 * 山海·云烟 - 设置页共享辅助函数
 */

let currentApiConfigs = [];
let currentActiveConfigId = '';
let currentActiveModel = '';
let editingConfigId = null;

let agentPageApiConfigs = [];
let agentPageActiveConfigId = '';
let agentSettingsShowAdvanced = false;
let settingsReconnectInProgress = false;

function renderSettingsLoadingState() {
    return `
        <div class="settings-loading-state">
            <i class="ri-loader-4-line"></i>
        </div>
    `;
}

function renderSettingsErrorState(message, options = {}) {
    if (typeof options.retryAction === 'function') {
        window.__lastSettingsRetryAction = options.retryAction;
    }

    return `
        <div class="settings-error-state">
            <div class="settings-error-panel">
                <i class="ri-error-warning-line"></i>
                <p class="settings-subtitle settings-subtitle--md" style="margin-top: 16px;">${message}</p>
                <div class="settings-error-actions">
                    <button type="button" class="settings-button settings-button--primary" data-settings-reconnect>
                        <i class="ri-refresh-line"></i> 重新连接
                    </button>
                    <button type="button" class="settings-button" data-settings-refresh>
                        <i class="ri-restart-line"></i> 刷新应用
                    </button>
                </div>
                <p class="settings-error-hint">如果后端进程已经退出，请重新打开山海·云烟。</p>
            </div>
        </div>
    `;
}

async function waitForBackendConnection() {
    const response = await fetch('/api/app/runtime', {
        method: 'GET',
        cache: 'no-store',
        credentials: 'same-origin'
    });
    if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
    }
    return response;
}

async function handleSettingsReconnect(button) {
    if (settingsReconnectInProgress) return;
    settingsReconnectInProgress = true;

    const originalHtml = button.innerHTML;
    button.disabled = true;
    button.innerHTML = '<i class="ri-loader-4-line"></i> 连接中...';

    try {
        await waitForBackendConnection();
        if (typeof showToast === 'function') {
            showToast('后端连接已恢复', 'success');
        }
        const retryAction = window.__lastSettingsRetryAction;
        if (typeof retryAction === 'function') {
            await retryAction();
        } else {
            window.location.reload();
        }
    } catch (error) {
        if (typeof showToast === 'function') {
            showToast('后端仍未响应，请确认程序没有退出', 'error');
        }
        button.disabled = false;
        button.innerHTML = originalHtml;
    } finally {
        settingsReconnectInProgress = false;
    }
}

document.addEventListener('click', (event) => {
    const reconnectButton = event.target.closest('[data-settings-reconnect]');
    if (reconnectButton) {
        handleSettingsReconnect(reconnectButton);
        return;
    }

    if (event.target.closest('[data-settings-refresh]')) {
        window.location.reload();
    }
});

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
