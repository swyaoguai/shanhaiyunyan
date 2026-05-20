/**
 * 山海·云烟 - 设置页渲染层
 */

const SETTINGS_DEFAULT_API_PRESET_ID = 'preset-tsc5';
const SETTINGS_DEFAULT_API_PRESET_LEGACY_NAME = '预设接口';
const SETTINGS_DEFAULT_API_PRESET_DISPLAY_NAME = '探索仓API';
const SETTINGS_RELAY_SITE_URL = 'https://test.tsc5.top/';

function normalizeApiConfigDisplayName(config) {
    const name = String(config?.name || '').trim();
    if (config?.id === SETTINGS_DEFAULT_API_PRESET_ID && (!name || name === SETTINGS_DEFAULT_API_PRESET_LEGACY_NAME)) {
        return SETTINGS_DEFAULT_API_PRESET_DISPLAY_NAME;
    }
    return name || '未命名配置';
}

function shouldShowRelayQuickLink(config) {
    const apiBase = String(config?.api_base || '').trim();
    return config?.id === SETTINGS_DEFAULT_API_PRESET_ID || apiBase.includes('api.tsc5.top') || apiBase.includes('test.tsc5.top');
}

function renderRelayQuickLink(config, className = '') {
    if (!shouldShowRelayQuickLink(config)) {
        return '';
    }
    return `
        <a class="settings-quick-link ${className}" href="${SETTINGS_RELAY_SITE_URL}" target="_blank" rel="noopener noreferrer">
            <i class="ri-external-link-line"></i>
            打开中转站
        </a>
    `;
}

function loadThemeSettings() {
    const content = ensureSettingsContentRoot();

    if (!content) {
        return;
    }

    const currentTheme = localStorage.getItem('theme_mode') || 'dark';
    const currentHue = parseInt(localStorage.getItem('theme_hue') || '250', 10);
    const currentSaturation = parseInt(localStorage.getItem('theme_saturation') || '40', 10);
    const currentTextLightness = parseInt(localStorage.getItem('theme_text_lightness') || '90', 10);
    const currentBgLightness = parseInt(localStorage.getItem('theme_bg_lightness') || '12', 10);
    const currentBgOpacity = parseFloat(localStorage.getItem('theme_opacity') || '0.85');
    const hasBackground = !!store.settings.bgUrl;

    content.innerHTML = `
        <div class="settings-page settings-page--narrow">
            <div class="settings-page-header">
                <h2 class="settings-page-title">
                    <i class="ri-palette-line"></i>
                    主题设置
                </h2>
            </div>

            <div class="setting-section settings-section-panel">
                <h3 class="settings-section-title">快捷主题</h3>
                <div class="settings-grid settings-grid--12 settings-grid-5">
                    <button class="theme-preset-btn theme-preset-btn--dark ${currentTheme === 'dark' ? 'active' : ''}" data-theme="dark">
                        <div class="theme-preset-btn-title">暗夜</div>
                        <div class="theme-preset-btn-copy">护眼深色</div>
                    </button>
                    <button class="theme-preset-btn theme-preset-btn--light ${currentTheme === 'light' ? 'active' : ''}" data-theme="light">
                        <div class="theme-preset-btn-title">浅白</div>
                        <div class="theme-preset-btn-copy">明亮清新</div>
                    </button>
                    <button class="theme-preset-btn theme-preset-btn--green ${currentTheme === 'green' ? 'active' : ''}" data-theme="green">
                        <div class="theme-preset-btn-title">护眼绿</div>
                        <div class="theme-preset-btn-copy">舒适自然</div>
                    </button>
                    <button class="theme-preset-btn theme-preset-btn--warm ${currentTheme === 'warm' ? 'active' : ''}" data-theme="warm">
                        <div class="theme-preset-btn-title">暖光</div>
                        <div class="theme-preset-btn-copy">温馨柔和</div>
                    </button>
                    <button class="theme-preset-btn theme-preset-btn--blue ${currentTheme === 'blue' ? 'active' : ''}" data-theme="blue">
                        <div class="theme-preset-btn-title">深蓝</div>
                        <div class="theme-preset-btn-copy">专注沉浸</div>
                    </button>
                </div>
            </div>

            <div class="setting-section settings-section-panel">
                <h3 class="settings-section-title">
                    自定义调色
                    <span class="settings-section-title-note">精细调整颜色</span>
                </h3>

                <div class="settings-stack">
                    <div>
                        <div class="settings-label-row">
                            <label class="settings-label">色相 (Hue)</label>
                            <span id="hue-value" class="settings-label-accent">${currentHue}°</span>
                        </div>
                        <input type="range" id="hue-slider" min="0" max="360" value="${currentHue}"
                            class="settings-range"
                            style="background: linear-gradient(to right, hsl(0, 70%, 50%), hsl(60, 70%, 50%), hsl(120, 70%, 50%), hsl(180, 70%, 50%), hsl(240, 70%, 50%), hsl(300, 70%, 50%), hsl(360, 70%, 50%));">
                    </div>

                    <div>
                        <div class="settings-label-row">
                            <label class="settings-label">饱和度 (Saturation)</label>
                            <span id="saturation-value" class="settings-label-accent">${currentSaturation}%</span>
                        </div>
                        <input type="range" id="saturation-slider" min="0" max="100" value="${currentSaturation}"
                            class="settings-range"
                            style="background: linear-gradient(to right, #808080, var(--accent-color));">
                    </div>

                    <div>
                        <div class="settings-label-row">
                            <label class="settings-label">背景亮度 (Background Lightness)</label>
                            <span id="bg-lightness-value" class="settings-label-accent">${currentBgLightness}%</span>
                        </div>
                        <input type="range" id="bg-lightness-slider" min="0" max="100" value="${currentBgLightness}"
                            class="settings-range"
                            style="background: linear-gradient(to right, #000, #fff);">
                    </div>

                    <div>
                        <div class="settings-label-row">
                            <label class="settings-label">文字亮度 (Text Lightness)</label>
                            <span id="text-lightness-value" class="settings-label-accent">${currentTextLightness}%</span>
                        </div>
                        <input type="range" id="text-lightness-slider" min="0" max="100" value="${currentTextLightness}"
                            class="settings-range"
                            style="background: linear-gradient(to right, #000, #fff);">
                    </div>
                </div>
            </div>

            <div class="setting-section settings-section-panel">
                <h3 class="settings-section-title">
                    背景图片
                    <span class="settings-section-title-note">个性化背景</span>
                </h3>

                <div class="settings-row settings-row--center settings-row--wrap">
                    <input type="file" id="bg-image-input" accept="image/*" style="display: none;">
                    <button id="select-bg-btn" class="settings-button">
                        <i class="ri-image-add-line"></i> 选择图片
                    </button>
                    <button id="clear-bg-btn" class="settings-button settings-button--danger" style="${hasBackground ? '' : 'opacity: 0.5; pointer-events: none;'}">
                        <i class="ri-delete-bin-line"></i> 清除背景
                    </button>
                    ${hasBackground ? '<span class="settings-status-text" style="color: #10b981;"><i class="ri-check-line"></i> 已设置背景图</span>' : ''}
                </div>

                <div style="margin-top: 16px; ${hasBackground ? '' : 'opacity: 0.5; pointer-events: none;'}">
                    <div class="settings-label-row">
                        <label class="settings-label">
                            叠加层透明度
                            <span class="settings-note"> (值越低背景图越清晰)</span>
                        </label>
                        <span id="overlay-opacity-value" class="settings-label-accent">${Math.round(currentBgOpacity * 100)}%</span>
                    </div>
                    <input type="range" id="overlay-opacity-slider" min="0" max="100" value="${Math.round(currentBgOpacity * 100)}"
                        class="settings-range"
                        style="background: linear-gradient(to right, transparent, rgba(0,0,0,0.9));">
                </div>

                <div class="settings-note" style="margin-top: 16px;">
                    提示：设置背景图片后，调节「叠加层透明度」控制背景图片的显示强度
                </div>
            </div>

            <div class="settings-row settings-row--center" style="margin-top: 4px;">
                <button id="save-theme-settings" class="settings-button settings-button--primary">
                    <i class="ri-save-line"></i> 保存主题设置
                </button>
                <span id="theme-save-status" class="settings-status-text"></span>
            </div>
        </div>
    `;

    bindThemeSettingsEvents();
}

async function loadGlobalAPISettings() {
    const content = ensureSettingsContentRoot();
    if (!content) return;

    content.innerHTML = renderSettingsLoadingState();

    try {
        const { configs, activeConfigId, activeModel, timeoutSettings } = await fetchGlobalApiSettingsData();
        const llmTimeouts = timeoutSettings.llm || {};
        const shortStoryTimeouts = timeoutSettings.short_story || {};
        const llmRanges = timeoutSettings.ranges?.llm || {};
        const shortStoryRange = timeoutSettings.ranges?.short_story || { min: 30, max: 600 };
        const hasConfigs = configs.length > 0;
        const activeConfig = configs.find((item) => item.id === activeConfigId);

        content.innerHTML = renderGlobalApiSettingsView({
            configs,
            activeConfig,
            activeConfigId,
            activeModel,
            hasConfigs,
            llmTimeouts,
            shortStoryTimeouts,
            llmRanges,
            shortStoryRange
        });

        bindGlobalAPISettingsEvents(timeoutSettings);
    } catch (e) {
        content.innerHTML = renderSettingsErrorState(`加载配置失败: ${safeErrorText(e)}`, {
            retryAction: loadGlobalAPISettings
        });
    }
}

function renderGlobalApiSettingsView({
    configs,
    activeConfig,
    activeConfigId,
    activeModel,
    hasConfigs,
    llmTimeouts,
    shortStoryTimeouts,
    llmRanges,
    shortStoryRange
}) {
    return `
        <div class="settings-page">
            <div class="settings-page-header">
                <h2 class="settings-page-title">
                    <i class="ri-server-line"></i>
                    全局API配置
                    <span class="settings-page-status ${hasConfigs && activeConfig ? 'settings-page-status--success' : 'settings-page-status--warning'}">
                        ${hasConfigs && activeConfig ? '已配置 ✓' : '未配置'}
                    </span>
                </h2>

                <p class="settings-subtitle">
                    管理多个API配置，每个配置可包含多个模型。使用时通过下拉框选择当前使用的配置和模型。
                </p>
            </div>

            <div class="setting-section settings-section-panel settings-section-panel--accent">
                <h3 class="settings-section-title">
                    <i class="ri-play-circle-line" style="color: #10b981;"></i>
                    当前使用配置
                </h3>

                <div class="settings-grid settings-grid-2">
                    <div>
                        <div class="settings-label-row">
                            <label class="settings-label">选择API配置</label>
                            ${renderRelayQuickLink(activeConfig, 'settings-quick-link--inline')}
                        </div>
                        <select id="active-config-select" class="settings-field">
                            ${!hasConfigs ? '<option value="">-- 请先添加配置 --</option>' : ''}
                            ${configs.map((cfg) => `
                                <option value="${safeAttr(cfg.id)}" ${cfg.id === activeConfigId ? 'selected' : ''}>
                                    ${safeText(normalizeApiConfigDisplayName(cfg))} (${safeHostText(cfg.api_base)})
                                </option>
                            `).join('')}
                        </select>
                    </div>

                    <div>
                        <label class="settings-label">选择模型</label>
                        <select id="active-model-select" class="settings-field">
                            ${renderModelOptions(activeConfig, activeModel)}
                        </select>
                    </div>
                </div>

                <div class="settings-row settings-row--center settings-row--wrap" style="margin-top: 16px;">
                    <button id="apply-active-config" class="settings-button settings-button--success">
                        <i class="ri-check-line"></i> 应用配置
                    </button>
                    <button id="test-active-config" class="settings-button">
                        <i class="ri-wifi-line"></i> 测试连接
                    </button>
                    <span id="active-config-status" class="settings-status-text" style="margin-left: auto;">
                        ${activeConfig ? `当前: ${safeText(normalizeApiConfigDisplayName(activeConfig))} / ${safeText(activeModel || '未选择模型')}` : '未选择配置'}
                    </span>
                </div>

                <div id="active-config-test-result" class="settings-inline-panel" style="margin-top: 16px;">
                    ${renderApiTestResultPanel()}
                </div>
            </div>

            <div class="setting-section settings-section-panel">
                <div class="settings-section-header">
                    <h3 class="settings-section-title">
                        <i class="ri-list-check"></i>
                        配置列表 (${configs.length})
                    </h3>
                    <button id="add-new-config" class="settings-button settings-button--primary settings-button--sm">
                        <i class="ri-add-line"></i> 新建配置
                    </button>
                </div>

                <div id="config-list-container" class="settings-list">
                    ${configs.length === 0 ? `
                        <div class="settings-empty-state">
                            <i class="ri-inbox-line settings-empty-icon"></i>
                            <p style="margin-top: 12px;">还没有API配置，点击上方"新建配置"添加</p>
                        </div>
                    ` : configs.map((cfg) => renderConfigCard(cfg)).join('')}
                </div>
            </div>

            <div id="config-edit-modal" class="settings-modal">
                <div class="settings-modal-card">
                    <div id="config-edit-content"></div>
                </div>
            </div>

            <div class="setting-section settings-section-panel">
                <div class="settings-section-header settings-section-header--start">
                    <div>
                        <h3 class="settings-section-title">
                            <i class="ri-timer-line"></i>
                            全局超时设置
                        </h3>
                        <div class="settings-status-text">通用模型请求和短篇流程都使用这里的超时配置。调整后会影响全局 Agent 调用与短篇创作面板。</div>
                    </div>
                    <button id="save-timeout-settings" class="settings-button settings-button--primary">
                        <i class="ri-save-line"></i> 保存全局超时设置
                    </button>
                </div>

                <div class="settings-stack">
                    <div class="settings-inline-panel">
                        <div class="settings-inline-panel-title">通用模型请求超时</div>
                        <div class="settings-inline-panel-copy">影响多数 Agent 与通用 LLM 客户端的连接、读取、写入与连接池等待时间。</div>
                        <div class="settings-grid settings-grid-auto">
                            ${[
                                ['connect', '连接超时'],
                                ['read', '读取超时'],
                                ['write', '写入超时'],
                                ['pool', '连接池超时']
                            ].map(([key, label]) => `
                                <div>
                                    <label class="settings-label">${label}</label>
                                    <input type="number" id="llm-timeout-${key}" value="${llmTimeouts[key] ?? ''}" min="${llmRanges[key]?.min ?? 1}" max="${llmRanges[key]?.max ?? 3600}" step="5" class="settings-field">
                                </div>
                            `).join('')}
                        </div>
                    </div>

                    <div class="settings-inline-panel">
                        <div class="settings-inline-panel-title">短篇流程步骤超时</div>
                        <div class="settings-inline-panel-copy">在通用 LLM 读取超时之上，再限制短篇各步骤的最长等待时间。建议范围 ${shortStoryRange.min}~${shortStoryRange.max} 秒。</div>
                        <div class="settings-grid settings-grid-auto">
                            ${[
                                ['synopsis', '导语生成'],
                                ['outline', '大纲生成'],
                                ['chapter', '章节生成'],
                                ['quality', '质量检查'],
                                ['coherence', '复审定稿'],
                                ['title', '书名生成'],
                                ['tags', '标签生成']
                            ].map(([key, label]) => `
                                <div>
                                    <label class="settings-label">${label}</label>
                                    <input type="number" id="short-story-timeout-${key}" value="${shortStoryTimeouts[key] ?? ''}" min="${shortStoryRange.min}" max="${shortStoryRange.max}" step="10" class="settings-field">
                                </div>
                            `).join('')}
                        </div>
                    </div>
                </div>
            </div>
        </div>
    `;
}

function renderApiTestResultPanel(result = null) {
    if (!result) {
        return `
            <div class="settings-test-card settings-test-card--idle">
                <div class="settings-test-card-header">
                    <div class="settings-test-card-icon">
                        <i class="ri-wifi-line"></i>
                    </div>
                    <div class="settings-test-card-main">
                        <div class="settings-test-card-title">测试结果</div>
                        <div class="settings-test-card-copy">想知道这套配置能不能用，点一下上面的「测试连接」就行。</div>
                    </div>
                </div>
                <div class="settings-test-card-placeholder">
                    这里会直接告诉你：现在能不能用、卡在哪、下一步该怎么处理。
                </div>
            </div>
        `;
    }

    const success = !!result.success;
    let verdict = '这次测试没过，先别急着开工。';
    let badgeText = '现在用不了';
    let badgeClass = 'settings-chip settings-chip--warning';
    let cardClass = 'settings-test-card settings-test-card--error';
    let iconClass = 'ri-close-circle-line';

    if (success) {
        verdict = '这次测试通过了，这套配置现在能正常用。';
        badgeText = '能正常用';
        badgeClass = 'settings-chip settings-chip--success';
        cardClass = 'settings-test-card settings-test-card--success';
        iconClass = 'ri-checkbox-circle-line';
    }

    const detail = result.detail ? safeText(result.detail) : '没有拿到额外返回信息';
    const errorCode = safeText(result.error_code || '无');
    const title = safeText(result.title || (success ? '可以正常用' : '测试没通过'));
    const solution = safeText(result.solution || (success ? '可以直接拿来创作。' : '先看看错误详情再处理。'));
    const statusCode = safeText(result.status_code ?? '未知');
    const responseTime = success ? safeText(result.response_time ?? '') : '';

    return `
        <div class="${cardClass}">
            <div class="settings-test-card-header">
                <div class="settings-test-card-icon">
                    <i class="${iconClass}"></i>
                </div>
                <div class="settings-test-card-main">
                    <div class="settings-test-card-title">测试结果</div>
                    <div class="settings-test-card-copy">${verdict}</div>
                </div>
                <span class="${badgeClass}">${badgeText}</span>
            </div>

            <div class="settings-chip-list settings-test-meta">
            <span class="settings-chip settings-chip--info">错误代号：${errorCode}</span>
            <span class="settings-chip settings-chip--info">状态码：${statusCode}</span>
            ${success ? `<span class="settings-chip settings-chip--success">响应：${responseTime}ms</span>` : ''}
            </div>

            <div class="settings-test-body">
                <div class="settings-test-row">
                    <div class="settings-test-label">结果判断</div>
                    <div class="settings-test-value">${title}</div>
                </div>
                <div class="settings-test-row">
                    <div class="settings-test-label">建议处理</div>
                    <div class="settings-test-value">${solution}</div>
                </div>
                <div class="settings-test-row">
                    <div class="settings-test-label">错误详情</div>
                    <div class="settings-test-detail">${detail}</div>
                </div>
            </div>
        </div>
    `;
}

function renderModelOptions(config, selectedModel = currentActiveModel) {
    if (!config || !config.models || config.models.length === 0) {
        return '<option value="">-- 请先添加模型 --</option>';
    }

    return config.models.map((model) => `
        <option value="${safeAttr(model)}" ${model === selectedModel ? 'selected' : ''}>${safeText(model)}</option>
    `).join('');
}

function _apiTypeLabel(apiType) {
    const labels = {
        'openai_chat': 'OpenAI Chat',
        'openai_responses': 'OpenAI Responses',
        'anthropic': 'Anthropic'
    };
    return labels[apiType] || 'OpenAI Chat';
}

function _apiTypeBadgeClass(apiType) {
    if (apiType === 'anthropic') return 'settings-chip--warning';
    if (apiType === 'openai_responses') return 'settings-chip--success';
    return 'settings-chip--info';
}

function renderConfigCard(cfg) {
    const isActive = cfg.id === currentActiveConfigId;
    const modelCount = cfg.models ? cfg.models.length : 0;
    const apiType = cfg.api_type || 'openai_chat';
    const keyCount = Array.isArray(cfg.api_keys)
        ? cfg.api_keys.filter((entry) => entry?.key_set).length
        : (cfg.api_key_set ? 1 : 0);
    const keyStatusChip = keyCount > 0
        ? `<span class="settings-chip settings-chip--success"><i class="ri-key-line"></i> 已配置${keyCount > 1 ? ` ${keyCount} 个` : ''}Key</span>`
        : '<span class="settings-chip settings-chip--warning"><i class="ri-key-line"></i> 未配置Key</span>';

    return `
        <div class="config-card ${isActive ? 'is-active' : ''}" data-config-id="${safeAttr(cfg.id)}">
            <div class="settings-card-header">
                <div style="flex: 1;">
                    <div class="settings-card-title-row">
                        <span class="settings-card-title">${safeText(normalizeApiConfigDisplayName(cfg))}</span>
                        ${renderRelayQuickLink(cfg, 'settings-quick-link--card')}
                        ${isActive ? '<span class="settings-badge settings-badge--success">当前使用</span>' : ''}
                        <span class="settings-chip ${_apiTypeBadgeClass(apiType)}"><i class="ri-plug-line"></i> ${_apiTypeLabel(apiType)}</span>
                        ${keyStatusChip}
                    </div>
                    <div class="settings-card-copy">
                        <i class="ri-link" style="margin-right: 4px;"></i>
                        ${safeText(cfg.api_base || '未设置URL')}
                    </div>
                    <div class="settings-chip-list">
                        ${cfg.models && cfg.models.length > 0 ? cfg.models.map((model) => `
                            <span class="settings-chip settings-chip--info">${safeText(model)}</span>
                        `).join('') : '<span class="settings-chip settings-chip--muted">无模型</span>'}
                    </div>
                </div>
                <div class="settings-card-actions">
                    <button class="edit-config-btn settings-button settings-button--sm" data-config-id="${safeAttr(cfg.id)}" title="编辑">
                        <i class="ri-edit-line"></i>
                    </button>
                    <button class="delete-config-btn settings-button settings-button--sm settings-button--danger-soft" data-config-id="${safeAttr(cfg.id)}" title="删除">
                        <i class="ri-delete-bin-line"></i>
                    </button>
                </div>
            </div>
            <div class="settings-card-meta">
                <span><i class="ri-cpu-line"></i> ${modelCount} 个模型</span>
                <span><i class="ri-settings-3-line"></i> 温度参数：${cfg.temperature ?? 0.7}</span>
                <span><i class="ri-file-text-line"></i> 最大输出长度：${cfg.max_tokens || 4096}</span>
            </div>
        </div>
    `;
}

async function loadAgentSettings() {
    const content = ensureSettingsContentRoot();
    if (!content) return;

    content.innerHTML = renderSettingsLoadingState();

    try {
        const { agents } = await fetchAgentSettingsData(agentSettingsShowAdvanced);
        const agentsById = {};
        agents.forEach((agent) => {
            agentsById[agent.name] = agent;
        });

        const iconMap = {
            Outliner: 'ri-file-list-3-line',
            Worldbuilder: 'ri-earth-line',
            ChapterWriter: 'ri-quill-pen-line',
            Polisher: 'ri-magic-line',
            Evaluator: 'ri-star-line',
            Communicator: 'ri-chat-3-line',
            ContinuousWriter: 'ri-infinity-line',
            CharacterBuilder: 'ri-user-star-line',
            ProjectScanner: 'ri-scan-line',
            ContextStrategy: 'ri-route-line',
            ContentReader: 'ri-file-text-line',
            CreativeWriter: 'ri-quill-pen-fill',
            ContentExpansion: 'ri-text-spacing',
            QualityValidator: 'ri-shield-check-line',
            FileNaming: 'ri-file-edit-line',
            SummaryOrchestrator: 'ri-list-ordered',
            ContextCompressor: 'ri-compasses-2-line',
            FileEditor: 'ri-edit-box-line'
        };

        const agentTypes = agents.map((agent) => ({
            id: agent.name,
            name: agent.display_name || agent.name,
            icon: iconMap[agent.name] || 'ri-robot-line',
            desc: agent.description || '无描述'
        }));

        content.innerHTML = renderAgentSettingsView(agentTypes, agentsById);
        bindAgentSettingsEvents();
        document.getElementById('agent-advanced-toggle')?.addEventListener('change', async (event) => {
            agentSettingsShowAdvanced = !!event.currentTarget.checked;
            await loadAgentSettings();
        });
    } catch (e) {
        content.innerHTML = renderSettingsErrorState(`加载Agent配置失败: ${safeErrorText(e)}`, {
            retryAction: loadAgentSettings
        });
    }
}

function renderAgentSettingsView(agentTypes, agents) {
    const findApiConfigId = (config) => {
        const explicitId = String(config.api_config_id || '').trim();
        if (explicitId && agentPageApiConfigs.some((cfg) => cfg.id === explicitId)) {
            return explicitId;
        }

        const apiBase = String(config.api_base || '').trim();
        if (!apiBase) return '';

        const sameBase = agentPageApiConfigs.filter((cfg) => cfg.api_base === apiBase);
        if (sameBase.length === 0) return '';

        const savedModel = String(config.model || '').trim();
        if (savedModel) {
            const modelMatched = sameBase.find((cfg) => Array.isArray(cfg.models) && cfg.models.includes(savedModel));
            if (modelMatched) {
                return modelMatched.id;
            }
        }

        return sameBase[0].id;
    };

    return `
        <div class="settings-page">
            <div class="settings-page-header">
                <h2 class="settings-page-title">
                    <i class="ri-robot-line"></i>
                    Agent配置
                </h2>

                <p class="settings-subtitle settings-subtitle--md">
                    默认只显示会直接影响创作结果的核心 AI Agent。开启高级模式后，可查看内部辅助 Agent 的配置入口。
                </p>
            </div>

            <div style="display: flex; align-items: center; justify-content: space-between; gap: 12px; margin-bottom: 20px; padding: 14px 16px; background: rgba(255,255,255,0.03); border: 1px solid var(--border-color); border-radius: 10px;">
                <div>
                    <div style="font-size: 14px; color: var(--text-primary); font-weight: 600;">高级 / 开发者模式</div>
                    <div style="font-size: 12px; color: var(--text-secondary); margin-top: 4px;">仅在需要调试内部辅助 Agent 时开启，普通使用建议保持关闭。</div>
                </div>
                <label style="display: inline-flex; align-items: center; gap: 8px; color: var(--text-primary); cursor: pointer; user-select: none;">
                    <input id="agent-advanced-toggle" type="checkbox" ${agentSettingsShowAdvanced ? 'checked' : ''} style="accent-color: var(--accent-color);">
                    <span style="font-size: 13px;">显示高级Agent</span>
                </label>
            </div>

            <div class="settings-list">
                ${agentTypes.map((agent) => {
                    const config = agents[agent.id] || {};
                    const isOverride = config.override || !config.use_global;
                    const matchedApiConfigId = findApiConfigId(config);
                    const savedModel = config.model || '';

                    return `
                        <div class="agent-config-card" data-agent="${safeAttr(agent.id)}">
                            <div class="settings-section-header">
                                <div class="settings-icon-box">
                                    <i class="${agent.icon}"></i>
                                </div>
                                <div>
                                    <h3 class="settings-card-title" style="margin-bottom: 4px;">${safeText(agent.name)}</h3>
                                    <p class="settings-card-copy">${safeText(agent.desc)}</p>
                                    ${config.visibility === 'advanced' ? '<div style="font-size: 11px; color: #a78bfa; margin-top: 4px;">🛠 高级Agent</div>' : ''}
                                </div>
                                <label class="settings-checkbox-label" style="margin-left: auto;">
                                    <input type="checkbox" class="agent-override-toggle settings-checkbox" data-agent="${safeAttr(agent.id)}" ${isOverride ? 'checked' : ''}>
                                    <span class="settings-status-text">单独配置</span>
                                </label>
                            </div>

                            <div class="agent-config-fields settings-grid settings-grid-2 settings-grid--12" style="display: ${isOverride ? 'grid' : 'none'};">
                                <div>
                                    <label class="settings-label settings-label--sm">选择API配置</label>
                                    <select class="agent-api-config settings-field settings-field--sm" data-agent="${safeAttr(agent.id)}">
                                        <option value="">-- 使用全局配置 --</option>
                                        ${agentPageApiConfigs.map((cfg) => `
                                            <option value="${safeAttr(cfg.id)}" ${matchedApiConfigId === cfg.id ? 'selected' : ''}>
                                                ${safeText(normalizeApiConfigDisplayName(cfg))} (${safeHostText(cfg.api_base)})
                                            </option>
                                        `).join('')}
                                    </select>
                                </div>
                                <div>
                                    <label class="settings-label settings-label--sm">选择模型</label>
                                    <select class="agent-model-select settings-field settings-field--sm" data-agent="${safeAttr(agent.id)}">
                                        ${renderAgentModelOptions(matchedApiConfigId, savedModel)}
                                    </select>
                                </div>
                                <div>
                                    <label class="settings-label settings-label--sm">温度参数</label>
                                    <input type="number" class="agent-temperature settings-field settings-field--sm" data-agent="${safeAttr(agent.id)}" value="${config.temperature !== undefined && config.temperature !== null ? config.temperature : ''}" placeholder="0.7" min="0" max="2" step="0.1">
                                </div>
                                <div>
                                    <label class="settings-label settings-label--sm">最大输出长度</label>
                                    <input type="number" class="agent-max-tokens settings-field settings-field--sm" data-agent="${safeAttr(agent.id)}" value="${config.max_tokens !== undefined && config.max_tokens !== null ? config.max_tokens : ''}" placeholder="4096" min="100" max="128000">
                                </div>
                                <div class="settings-row settings-row--center settings-row--wrap" style="grid-column: 1 / -1; margin-top: 2px;">
                                    <button type="button" class="agent-test-config settings-button settings-button--sm" data-agent="${safeAttr(agent.id)}">
                                        <i class="ri-wifi-line"></i> 测试连接
                                    </button>
                                    <span class="agent-test-status settings-status-text" data-agent="${safeAttr(agent.id)}">
                                        测试当前Agent选中的API配置和模型
                                    </span>
                                </div>
                                <div class="agent-test-result settings-inline-panel" data-agent="${safeAttr(agent.id)}" style="grid-column: 1 / -1; display: none;"></div>
                            </div>
                        </div>
                    `;
                }).join('')}
            </div>

            <div>
                <button id="save-agent-configs" class="settings-button settings-button--primary">
                    <i class="ri-save-line"></i> 保存所有Agent配置
                </button>
            </div>
        </div>
    `;
}

function renderAgentModelOptions(configId, selectedModel) {
    if (!configId) {
        const activeConfig = agentPageApiConfigs.find((cfg) => cfg.id === agentPageActiveConfigId);
        if (activeConfig && activeConfig.models && activeConfig.models.length > 0) {
            return activeConfig.models.map((model) => `
                <option value="${safeAttr(model)}" ${model === selectedModel ? 'selected' : ''}>${safeText(model)} (全局)</option>
            `).join('');
        }
        return '<option value="">-- 请先配置全局API --</option>';
    }

    const config = agentPageApiConfigs.find((item) => item.id === configId);
    if (config && config.models && config.models.length > 0) {
        return config.models.map((model) => `
            <option value="${safeAttr(model)}" ${model === selectedModel ? 'selected' : ''}>${safeText(model)}</option>
        `).join('');
    }

    return '<option value="">-- 该配置无可用模型 --</option>';
}

async function loadKnowledgeBaseSettings() {
    const content = ensureSettingsContentRoot();
    if (!content) return;

    content.innerHTML = renderSettingsLoadingState();

    try {
        const { config, stats, chapterSummaryConfig, chapterSyncConfig } = await fetchKnowledgeBaseSettingsData();
        const embeddingProvider = String(config.embedding_provider || 'api').toLowerCase();
        const isLocalProvider = embeddingProvider === 'local_onnx' || embeddingProvider === 'local';
        const hasApiKey = Boolean(config.siliconflow_api_key_set || (config.siliconflow_api_key && config.siliconflow_api_key.length > 10));
        const hasLocalModel = Boolean(config.onnx_model_installed);
        const activeEmbeddingReady = Boolean(config.is_configured ?? (isLocalProvider ? hasLocalModel : hasApiKey));
        const kbStatusClass = activeEmbeddingReady ? 'settings-section-panel--accent' : 'settings-section-panel--danger';
        const kbBadgeClass = activeEmbeddingReady ? 'settings-badge--success' : 'settings-badge--danger';
        const kbIconColor = activeEmbeddingReady ? '#10b981' : '#ef4444';
        const localModelName = config.onnx_model_metadata?.model_id || config.onnx_model_metadata?.base_model || '本地模型包';
        const localModelDim = config.onnx_model_metadata?.embedding_dim || '';
        const autoSummaryEnabled = Boolean(chapterSummaryConfig?.auto_summary_enabled);
        const autoVectorSyncEnabled = chapterSyncConfig?.auto_vector_sync_enabled !== false;
        const syncOnEditEnabled = chapterSyncConfig?.sync_on_edit_enabled !== false;
        const syncOnDeleteEnabled = chapterSyncConfig?.sync_on_delete_enabled !== false;
        const hasActiveProject = Boolean(
            typeof getActiveProjectId === 'function'
                ? getActiveProjectId()
                : (window.store && window.store.currentProjectId)
        );

        content.innerHTML = `
            <div class="settings-page">
                <div class="settings-page-header">
                    <h2 class="settings-page-title">
                        <i class="ri-brain-line"></i>
                        知识库配置
                        <span class="settings-section-title-note">（向量检索系统）</span>
                    </h2>
                    <p class="settings-subtitle">
                        知识库用于章节内容的向量化存储和语义检索，需要配置向量化API服务。
                        <br><span class="settings-note settings-note--warning">注意：这与左侧"资料库"（角色/物品/世界观设定）是不同的功能。</span>
                    </p>
                </div>

                <div class="setting-section settings-section-panel settings-section-panel--spacious ${kbStatusClass}">
                    <div class="settings-section-header">
                        <h3 class="settings-section-title">
                            <i class="ri-cpu-line" style="color: ${kbIconColor};"></i>
                            向量化服务配置
                            <span class="settings-badge ${kbBadgeClass}" style="margin-left: 8px;">${activeEmbeddingReady ? '已配置 ✓' : '未配置'}</span>
                        </h3>
                        <button id="test-embedding-btn" class="settings-button settings-button--sm">
                            <i class="ri-wifi-line"></i> 测试连接
                        </button>
                    </div>
                    <p class="settings-note">
                        当前使用：${isLocalProvider ? '本地模型包' : '硅基流动线上模型'}
                    </p>
                    <div class="settings-stack" style="margin-top: 16px;">
                        <div>
                            <label class="settings-label">嵌入模型来源</label>
                            <select id="kb-embedding-provider" class="settings-field">
                                <option value="api" ${!isLocalProvider ? 'selected' : ''}>硅基流动线上模型</option>
                                <option value="local_onnx" ${isLocalProvider ? 'selected' : ''}>本地模型包</option>
                            </select>
                        </div>

                        <div id="kb-provider-api-panel" class="settings-stack" style="${isLocalProvider ? 'display: none;' : ''}">
                            <div class="settings-grid settings-grid-wide-narrow">
                                <div>
                                    <label class="settings-label">API Base URL</label>
                                    <input type="text" id="kb-siliconflow-base" value="${safeAttr(config.siliconflow_base_url || 'https://api.siliconflow.cn/v1')}" placeholder="https://api.siliconflow.cn/v1" class="settings-field">
                                </div>
                                <div>
                                    <label class="settings-label">向量维度</label>
                                    <select id="kb-embedding-dim" class="settings-field">
                                        <option value="512" ${config.siliconflow_embedding_dim == 512 ? 'selected' : ''}>512</option>
                                        <option value="1024" ${config.siliconflow_embedding_dim == 1024 || !config.siliconflow_embedding_dim ? 'selected' : ''}>1024 (推荐)</option>
                                        <option value="2048" ${config.siliconflow_embedding_dim == 2048 ? 'selected' : ''}>2048</option>
                                    </select>
                                </div>
                            </div>
                            <div>
                                <label class="settings-label">
                                    API Key <span style="color: #ef4444;">*</span>
                                    ${hasApiKey ? '<span class="settings-chip settings-chip--success" style="margin-left: 8px;">✓ 已保存</span>' : ''}
                                </label>
                                <div class="settings-input-action">
                                    <input type="password" id="kb-siliconflow-key" value="" placeholder="${hasApiKey ? '已保存，如需修改请输入新Key' : '请输入硅基流动API Key（sk-...）'}" class="settings-field settings-field--with-action">
                                    <button id="toggle-kb-key" class="settings-button settings-button--ghost" type="button">
                                        <i class="ri-eye-line"></i>
                                    </button>
                                </div>
                            </div>
                            <div>
                                <label class="settings-label">Embedding 模型</label>
                                <select id="kb-siliconflow-model" class="settings-field">
                                    <option value="BAAI/bge-m3" ${config.siliconflow_model === 'BAAI/bge-m3' || !config.siliconflow_model ? 'selected' : ''}>BAAI/bge-m3 (推荐，多语言)</option>
                                    <option value="BAAI/bge-large-zh-v1.5" ${config.siliconflow_model === 'BAAI/bge-large-zh-v1.5' ? 'selected' : ''}>BAAI/bge-large-zh-v1.5 (中文优化)</option>
                                    <option value="BAAI/bge-large-en-v1.5" ${config.siliconflow_model === 'BAAI/bge-large-en-v1.5' ? 'selected' : ''}>BAAI/bge-large-en-v1.5 (英文优化)</option>
                                </select>
                            </div>
                        </div>

                        <div id="kb-provider-local-panel" class="settings-stack" style="${isLocalProvider ? '' : 'display: none;'}">
                            <div class="settings-toggle-row">
                                <span class="settings-status-text">
                                    ${hasLocalModel ? `已安装：${safeText(localModelName)}${localModelDim ? ` · ${safeText(localModelDim)}维` : ''}` : '未安装本地模型包'}
                                </span>
                            </div>
                            <div class="settings-input-action">
                                <input type="file" id="kb-onnx-package-file" accept=".zip" class="settings-field settings-field--with-action">
                                <button id="install-onnx-package-btn" class="settings-button" type="button">
                                    <i class="ri-upload-cloud-line"></i> 安装模型包
                                </button>
                            </div>
                            <div class="settings-grid settings-grid-wide-narrow">
                                <div>
                                    <label class="settings-label">模型目录</label>
                                    <input type="text" id="kb-onnx-model-dir" value="${safeAttr(config.onnx_model_dir || 'novel_agent/models/embedding/default')}" class="settings-field">
                                </div>
                                <div>
                                    <label class="settings-label">模型文件</label>
                                    <input type="text" id="kb-onnx-model-file" value="${safeAttr(config.onnx_model_file || 'model.onnx')}" class="settings-field">
                                </div>
                            </div>
                            <div class="settings-grid settings-grid-wide-narrow">
                                <div>
                                    <label class="settings-label">池化方式</label>
                                    <select id="kb-onnx-pooling" class="settings-field">
                                        <option value="cls" ${(config.onnx_pooling || 'cls') === 'cls' ? 'selected' : ''}>CLS</option>
                                        <option value="mean" ${config.onnx_pooling === 'mean' ? 'selected' : ''}>Mean</option>
                                    </select>
                                </div>
                                <div>
                                    <label class="settings-label">最大长度</label>
                                    <input type="number" id="kb-onnx-max-length" min="64" max="2048" value="${safeAttr(config.onnx_max_length || 512)}" class="settings-field">
                                </div>
                            </div>
                            <div id="onnx-install-result" style="display: none;"></div>
                        </div>
                    </div>
                    <div id="embedding-test-result" style="margin-top: 16px; display: none;"></div>
                </div>

                <div class="setting-section settings-section-panel settings-section-panel--spacious">
                    <div class="settings-section-header">
                        <h3 class="settings-section-title">
                            <i class="ri-article-line" style="color: #8b5cf6;"></i>
                            章节摘要自动化
                            <span class="settings-badge ${autoSummaryEnabled ? 'settings-badge--success' : 'settings-badge--muted'}" id="cs-status-badge" style="margin-left: 8px;">${autoSummaryEnabled ? '已启用' : '未启用'}</span>
                        </h3>
                    </div>
                    <p class="settings-note">
                        自动生成的章节摘要会进入资料库的「正文摘要」，后续写作和检索都可以复用。
                    </p>
                    <div class="settings-toggle-row" style="margin-top: 12px;">
                        <label class="settings-checkbox-label" style="${hasActiveProject ? '' : 'opacity: 0.6;'}">
                            <input type="checkbox" id="cs-auto-summary-toggle" class="settings-checkbox" ${autoSummaryEnabled ? 'checked' : ''} ${hasActiveProject ? '' : 'disabled'}>
                            <span class="settings-status-text">${hasActiveProject ? (autoSummaryEnabled ? '已启用' : '未启用') : '请先选择项目后再配置'}</span>
                        </label>
                    </div>
                </div>

                <div class="setting-section settings-section-panel settings-section-panel--spacious">
                    <div class="settings-section-header">
                        <h3 class="settings-section-title">
                            <i class="ri-node-tree" style="color: #10b981;"></i>
                            章节知识同步
                            <span class="settings-badge ${autoVectorSyncEnabled ? 'settings-badge--success' : 'settings-badge--muted'}" id="cks-status-badge" style="margin-left: 8px;">${autoVectorSyncEnabled ? '自动同步' : '手动同步'}</span>
                        </h3>
                        <button id="rebuild-chapter-knowledge-btn" class="settings-button settings-button--sm" ${hasActiveProject ? '' : 'disabled'}>
                            <i class="ri-refresh-line"></i> 重建全文索引
                        </button>
                    </div>
                    <p class="settings-note">
                        正文全文进入向量库用于查找原文细节；章节摘要进入 Wiki 用于剧情关系和伏笔关联。
                    </p>
                    <div class="settings-stack" style="margin-top: 12px;">
                        <label class="settings-checkbox-label" style="${hasActiveProject ? '' : 'opacity: 0.6;'}">
                            <input type="checkbox" id="cks-auto-vector-sync-toggle" class="settings-checkbox" ${autoVectorSyncEnabled ? 'checked' : ''} ${hasActiveProject ? '' : 'disabled'}>
                            <span class="settings-status-text">写完/导入章节后同步正文全文向量</span>
                        </label>
                        <label class="settings-checkbox-label" style="${hasActiveProject ? '' : 'opacity: 0.6;'}">
                            <input type="checkbox" id="cks-sync-edit-toggle" class="settings-checkbox" ${syncOnEditEnabled ? 'checked' : ''} ${hasActiveProject ? '' : 'disabled'}>
                            <span class="settings-status-text">编辑章节后更新对应索引</span>
                        </label>
                        <label class="settings-checkbox-label" style="${hasActiveProject ? '' : 'opacity: 0.6;'}">
                            <input type="checkbox" id="cks-sync-delete-toggle" class="settings-checkbox" ${syncOnDeleteEnabled ? 'checked' : ''} ${hasActiveProject ? '' : 'disabled'}>
                            <span class="settings-status-text">删除章节后清理对应索引</span>
                        </label>
                    </div>
                    <div id="chapter-knowledge-sync-result" style="display: none; margin-top: 12px;"></div>
                </div>

                <div class="setting-section settings-section-panel settings-section-panel--spacious">
                    <h3 class="settings-section-title">
                        <i class="ri-database-2-line" style="color: #3b82f6;"></i>
                        知识库数据统计
                    </h3>
                    <div class="settings-stat-grid">
                        <div class="settings-stat-card"><div class="settings-stat-value" style="color: var(--accent-color);">${stats.chapter_count || 0}</div><div class="settings-stat-label">章节数</div></div>
                        <div class="settings-stat-card"><div class="settings-stat-value" style="color: #10b981;">${stats.chunk_count || 0}</div><div class="settings-stat-label">分块数</div></div>
                        <div class="settings-stat-card"><div class="settings-stat-value" style="color: #f59e0b;">${stats.vector_count || 0}</div><div class="settings-stat-label">向量数</div></div>
                        <div class="settings-stat-card"><div class="settings-stat-value" style="color: #ec4899;">${stats.storage_size_mb || 0}</div><div class="settings-stat-label">存储 (MB)</div></div>
                    </div>
                    ${stats.chapters && stats.chapters.length > 0 ? `
                        <div>
                            <label class="settings-label">按章节删除（选择要删除的章节向量数据）</label>
                            <div id="chapter-list-container" class="settings-list-scroll">
                                ${stats.chapters.map((ch) => `
                                    <label class="settings-chapter-row">
                                        <input type="checkbox" class="chapter-checkbox settings-checkbox" value="${safeAttr(ch.chapter_id)}">
                                        <span class="settings-chapter-index">第${ch.chapter_number}章</span>
                                        <span class="settings-chapter-title">${safeText(ch.title)}</span>
                                    </label>
                                `).join('')}
                            </div>
                            <div class="settings-row settings-row--wrap" style="margin-top: 12px;">
                                <button id="select-all-chapters" class="settings-button settings-button--sm"><i class="ri-checkbox-multiple-line"></i> 全选</button>
                                <button id="delete-selected-chapters" class="settings-button settings-button--sm settings-button--danger"><i class="ri-delete-bin-line"></i> 删除选中章节</button>
                            </div>
                        </div>
                    ` : `
                        <div class="settings-empty-state settings-empty-state--compact">
                            <i class="ri-inbox-line settings-empty-icon settings-empty-icon--sm"></i>
                            <p class="settings-status-text" style="margin-top: 8px;">当前项目暂无向量化数据</p>
                        </div>
                    `}
                    <div class="settings-danger-zone">
                        <button id="clear-all-kb" class="settings-button settings-button--danger">
                            <i class="ri-delete-bin-7-line"></i> 清空当前项目所有知识库数据
                        </button>
                        <p class="settings-note" style="margin-top: 8px;">⚠️ 此操作不可恢复，将删除当前项目的所有向量化数据</p>
                    </div>
                </div>

                <div class="setting-section settings-section-panel settings-section-panel--spacious">
                    <h3 class="settings-section-title"><i class="ri-search-line"></i>检索参数</h3>
                    <div class="settings-grid settings-grid-3">
                        <div><label class="settings-label">检索数量 (Top-K)</label><input type="number" id="kb-top-k" value="${config.default_top_k || 5}" min="1" max="20" class="settings-field"></div>
                        <div><label class="settings-label">向量权重 (0-1)</label><input type="number" id="kb-vector-weight" value="${config.vector_weight || 0.7}" min="0" max="1" step="0.1" class="settings-field"></div>
                        <div><label class="settings-label">全文权重 (0-1)</label><input type="number" id="kb-fulltext-weight" value="${config.fulltext_weight || 0.3}" min="0" max="1" step="0.1" class="settings-field"></div>
                    </div>
                </div>

                <div class="setting-section settings-section-panel settings-section-panel--spacious">
                    <h3 class="settings-section-title"><i class="ri-scissors-line"></i>文本分块设置</h3>
                    <div class="settings-grid settings-grid-2">
                        <div><label class="settings-label">分块大小 (字符)</label><input type="number" id="kb-chunk-size" value="${config.chunk_size || 500}" min="100" max="2000" class="settings-field"></div>
                        <div><label class="settings-label">重叠大小 (字符)</label><input type="number" id="kb-chunk-overlap" value="${config.chunk_overlap || 50}" min="0" max="500" class="settings-field"></div>
                    </div>
                </div>

                <div>
                    <button id="save-kb-config" class="settings-button settings-button--primary">
                        <i class="ri-save-line"></i> 保存知识库配置
                    </button>
                </div>
            </div>
        `;

        bindKnowledgeBaseEvents(config);
    } catch (e) {
        content.innerHTML = renderSettingsErrorState(`加载资料库配置失败: ${safeErrorText(e)}`, {
            retryAction: loadKnowledgeBaseSettings
        });
    }
}

async function loadRegexRulesSettings() {
    const content = ensureSettingsContentRoot();
    if (!content) return;

    const rules = getRegexRules();
    content.innerHTML = `
        <div class="settings-page">
            <div class="settings-page-header">
                <h2 class="settings-page-title">
                    <i class="ri-code-line"></i>
                    正则替换规则
                </h2>
                <p class="settings-subtitle settings-subtitle--md">配置文本替换规则，用于词汇检测和自动替换功能。规则按顺序执行。</p>
            </div>
            <div id="regex-rules-container" class="settings-list" style="margin-bottom: 20px;">
                ${rules.map((rule, index) => renderRegexRuleItem(rule, index)).join('')}
            </div>
            <div class="settings-row settings-row--wrap">
                <button id="add-regex-rule" class="settings-button"><i class="ri-add-line"></i> 添加规则</button>
                <button id="save-regex-rules" class="settings-button settings-button--primary"><i class="ri-save-line"></i> 保存规则</button>
            </div>
        </div>
    `;

    bindRegexRuleEvents();
}

function renderRegexRuleItem(rule, index) {
    return `
        <div class="regex-rule-item settings-regex-rule" data-index="${index}">
            <div class="settings-row settings-row--center settings-row--wrap" style="margin-bottom: 12px;">
                <label class="settings-checkbox-label">
                    <input type="checkbox" class="rule-enabled settings-checkbox" ${rule.enabled ? 'checked' : ''}>
                    <span class="settings-status-text">启用</span>
                </label>
                <input type="text" class="rule-description settings-field settings-field--compact" value="${escapeHtml(rule.description || '')}" placeholder="规则描述（可选）" style="flex: 1;">
                <button class="delete-rule-btn settings-button settings-button--sm settings-button--danger"><i class="ri-delete-bin-line"></i></button>
            </div>
            <div class="settings-grid settings-grid-2 settings-grid--12">
                <div><label class="settings-label settings-label--sm">匹配模式 (正则)</label><input type="text" class="rule-pattern settings-field settings-field--sm settings-field--mono" value="${escapeHtml(rule.pattern || '')}" placeholder="例如: \\b(违禁词)\\b"></div>
                <div><label class="settings-label settings-label--sm">替换为</label><input type="text" class="rule-replacement settings-field settings-field--sm settings-field--mono" value="${escapeHtml(rule.replacement || '')}" placeholder="例如: ***"></div>
            </div>
        </div>
    `;
}

async function loadSkillsSettings() {
    const content = ensureSettingsContentRoot();
    if (!content) return;

    content.innerHTML = renderSettingsLoadingState();

    try {
        const skills = await fetchSkillsSettingsData();
        content.innerHTML = renderSkillsSettingsView(skills);
        bindSkillsSettingsEvents();
    } catch (e) {
        content.innerHTML = renderSettingsErrorState(`加载技能失败: ${safeErrorText(e)}`, {
            retryAction: loadSkillsSettings
        });
    }
}

function renderSkillsSettingsView(skills) {
    return `
        <div class="settings-page">
            <div class="settings-page-header">
                <h2 class="settings-page-title">
                    <i class="ri-puzzle-line"></i>
                    技能管理
                </h2>
                <p class="settings-subtitle settings-subtitle--md">
                    技能是可扩展的小功能，可以给助手补充额外能力，比如热点搜索、联网搜索这些。
                    启用后，无限续写和多Agent创作都能直接用上这些功能。
                </p>
            </div>
            <div class="setting-section settings-section-panel settings-section-panel--spacious">
                <h3 class="settings-section-title">
                    <i class="ri-list-check"></i>
                    可用技能（${skills.length}）
                </h3>
                ${skills.length === 0 ? `
                    <div class="settings-empty-state">
                        <i class="ri-inbox-line settings-empty-icon"></i>
                        <p style="margin-top: 12px;">还没找到可用技能</p>
                        <p style="font-size: 12px; margin-top: 8px;">请在 skills/ 目录下添加技能模块</p>
                    </div>
                ` : `
                    <div class="settings-list">
                        ${skills.map((skill) => {
                            const skillIcons = {
                                web_search: '🔍',
                                meme_search: '😄',
                                trends_search: '🔥',
                                novel_writing_assistant: '✍️',
                                short_story_creator: '📝'
                            };
                            const icon = skillIcons[skill.name] || '🧩';
                            const triggerHint = skill.trigger_hint ? `
                                <div class="settings-subtitle settings-subtitle--accent" style="margin-top: 8px; font-size: 12px;">
                                    <i class="ri-flashlight-line"></i> 触发方式：${safeText(skill.trigger_hint)}
                                </div>
                            ` : '';

                            return `
                                <div class="skill-card" data-skill="${safeAttr(skill.name)}">
                                    <div class="settings-card-header">
                                        <div style="flex: 1;">
                                            <div class="settings-card-title-row">
                                                <span style="font-size: 24px;">${icon}</span>
                                                <span class="settings-card-title">${safeText(skill.display_name || skill.name)}</span>
                                                ${skill.enabled ? '<span class="settings-badge settings-badge--success">已启用</span>' : '<span class="settings-badge settings-badge--muted">未启用</span>'}
                                                ${!skill.available ? '<span class="settings-badge settings-badge--danger">不可用</span>' : ''}
                                            </div>
                                            <div class="settings-card-copy">${safeText(skill.description || '无描述')}</div>
                                            <div class="settings-card-copy settings-card-copy--sm"><i class="ri-folder-line"></i> ${safeText(skill.path)}</div>
                                            ${triggerHint}
                                        </div>
                                        <div class="settings-card-actions" style="align-items: center;">
                                            <label class="settings-checkbox-label">
                                                <input type="checkbox" class="skill-toggle settings-checkbox settings-checkbox--lg" data-skill="${safeAttr(skill.name)}" ${skill.enabled ? 'checked' : ''} ${!skill.available ? 'disabled' : ''}>
                                                <span class="settings-status-text">${skill.available ? '启用' : '不可用'}</span>
                                            </label>
                                            <button class="delete-skill-btn settings-button settings-button--sm settings-button--danger-soft" data-skill="${safeAttr(skill.name)}" title="删除技能">
                                                <i class="ri-delete-bin-line"></i>
                                            </button>
                                        </div>
                                    </div>
                                </div>
                            `;
                        }).join('')}
                    </div>
                `}
            </div>
            <div class="settings-info-block">
                <h3 class="settings-info-title">
                    <i class="ri-information-line"></i>
                    关于技能
                </h3>
                <p class="settings-subtitle">
                    技能是独立的小功能，放在 skills/ 目录下。每个技能一般会带一个 SKILL.md 说明文件，以及 scripts/ 目录下的实现。
                    启用后，创作助手就能直接调用这些功能。
                </p>
            </div>
            <button id="save-skills-settings" class="settings-button settings-button--primary settings-button--wide">
                <i class="ri-save-line"></i> 保存技能设置
            </button>
        </div>
    `;
}

async function loadWritingSettings() {
    return loadKnowledgeBaseSettings();
}

window.loadWritingSettings = loadWritingSettings;
window.loadThemeSettings = loadThemeSettings;
window.loadGlobalAPISettings = loadGlobalAPISettings;
window.renderGlobalApiSettingsView = renderGlobalApiSettingsView;
window.renderModelOptions = renderModelOptions;
window.renderConfigCard = renderConfigCard;
window.loadAgentSettings = loadAgentSettings;
window.renderAgentSettingsView = renderAgentSettingsView;
window.renderAgentModelOptions = renderAgentModelOptions;
window.loadKnowledgeBaseSettings = loadKnowledgeBaseSettings;
window.loadRegexRulesSettings = loadRegexRulesSettings;
window.renderRegexRuleItem = renderRegexRuleItem;
window.loadSkillsSettings = loadSkillsSettings;
window.renderSkillsSettingsView = renderSkillsSettingsView;
