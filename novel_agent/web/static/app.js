/**
 * Legacy app bundle shim.
 *
 * This file used to contain the monolithic frontend implementation.
 * The application now loads modular scripts from index.html instead.
 * Keep only a tiny, parse-safe compatibility layer so accidental legacy
 * references fail gracefully instead of reviving stale logic.
 */

(function legacyAppShim() {
    const LEGACY_NOTICE_TITLE = '旧版前端包已废弃';
    const LEGACY_NOTICE_BODY =
        '当前应用已经迁移到模块化脚本，请使用 index.html 中加载的 app-core.js、app-settings.js、app-short-story.js 等新模块。';

    function escapeHtmlFallback(text) {
        if (text === null || text === undefined) return '';
        return String(text).replace(/[&<>"']/g, (char) => {
            const entities = {
                '&': '&amp;',
                '<': '&lt;',
                '>': '&gt;',
                '"': '&quot;',
                "'": '&#39;'
            };
            return entities[char] || char;
        });
    }

    function getRootContainer() {
        return document.getElementById('main-view')
            || document.getElementById('settings-content')
            || document.body;
    }

    function renderLegacyNotice(extra = '') {
        const root = getRootContainer();
        if (!root) return;

        const detail = extra ? `<p style="margin: 12px 0 0; color: var(--text-secondary, #94a3b8); line-height: 1.7;">${escapeHtml(extra)}</p>` : '';
        root.innerHTML = `
            <div style="max-width: 760px; margin: 40px auto; padding: 0 20px;">
                <div style="background: rgba(245, 158, 11, 0.12); border: 1px solid rgba(245, 158, 11, 0.35); border-radius: 14px; padding: 24px;">
                    <h2 style="margin: 0 0 12px; color: var(--text-primary, #e5e7eb); font-size: 20px;">${LEGACY_NOTICE_TITLE}</h2>
                    <p style="margin: 0; color: var(--text-secondary, #94a3b8); line-height: 1.7;">${LEGACY_NOTICE_BODY}</p>
                    <p style="margin: 12px 0 0; color: var(--text-secondary, #94a3b8); line-height: 1.7;">请改用 <code>app-settings.js</code> 暴露的设置页能力，不要再恢复旧版 <code>app.js</code> 逻辑。</p>
                    ${detail}
                </div>
            </div>
        `;
    }

    function delegateToModern(name, argsLike) {
        const fn = window[name];
        if (typeof fn === 'function' && fn !== legacyApi[name]) {
            return fn.apply(window, Array.from(argsLike || []));
        }
        renderLegacyNotice(`尝试调用遗留接口：${name}`);
        return undefined;
    }

    function showToastFallback(message, type) {
        if (typeof window.showToast === 'function' && window.showToast !== showToastFallback) {
            return window.showToast(message, type);
        }
        const prefix = type === 'error' ? '[error]' : type === 'warning' ? '[warn]' : '[info]';
        console.warn(prefix, message);
    }

    function init() {
        renderLegacyNotice('旧 bundle 不再承担初始化职责。');
    }

    function switchModule(moduleId) {
        if (typeof window.switchModule === 'function' && window.switchModule !== switchModule) {
            return window.switchModule(moduleId);
        }
        renderLegacyNotice(`尝试切换模块：${moduleId || 'unknown'}`);
        return undefined;
    }

    function renderSettings() {
        return delegateToModern('renderSettings', arguments);
    }

    function loadSettingsTab() {
        return delegateToModern('loadSettingsTab', arguments);
    }

    function loadThemeSettings() {
        return delegateToModern('loadThemeSettings', arguments);
    }

    function loadGlobalAPISettings() {
        if (typeof window.loadGlobalAPISettingsModern === 'function') {
            return window.loadGlobalAPISettingsModern.apply(window, arguments);
        }
        renderLegacyNotice('旧版设置页已废弃，请改用 <code>app-settings.js</code> 提供的新设置模块。');
        return undefined;
    }

    function loadKnowledgeBaseSettings() {
        return delegateToModern('loadKnowledgeBaseSettings', arguments);
    }

    function loadAgentSettings() {
        return delegateToModern('loadAgentSettings', arguments);
    }

    function loadRegexRulesSettings() {
        return delegateToModern('loadRegexRulesSettings', arguments);
    }

    function loadSkillsSettings() {
        return delegateToModern('loadSkillsSettings', arguments);
    }

    if (typeof window.escapeHtml !== 'function') {
        window.escapeHtml = escapeHtmlFallback;
    }
    if (typeof window.showToast !== 'function') {
        window.showToast = showToastFallback;
    }

    window.init = init;
    window.switchModule = switchModule;
    window.renderSettings = renderSettings;
    window.loadSettingsTab = loadSettingsTab;
    window.loadThemeSettings = loadThemeSettings;
    window.loadGlobalAPISettings = loadGlobalAPISettings;
    window.loadKnowledgeBaseSettings = loadKnowledgeBaseSettings;
    window.loadAgentSettings = loadAgentSettings;
    window.loadRegexRulesSettings = loadRegexRulesSettings;
    window.loadSkillsSettings = loadSkillsSettings;

    console.warn('[legacy-app] app.js is deprecated and replaced by modular frontend bundles.');
})();
