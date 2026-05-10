/**
 * 山海·云烟 - 核心状态和初始化模块
 * 包含：全局状态store、UI引用、初始化、事件绑定、模块切换
 */

const DEBUG_COPILOT_WORKFLOW = false;

// 全局状态 Store
const store = {
    currentModule: 'dashboard',
    currentChapterId: null,
    currentDashboardView: 'home', // 'home' 或 'stats'
    // 项目相关
    currentProjectId: null,
    currentProjectName: '',
    projects: [],
    // 当前项目数据
    projectData: {
        characters: [],
        outline: [],
        chapters: [],
        worldbuilding: [],
        items: [],
        // 资料库扩展分类
        eventlines: [],      // 事件线
        outline_settings: [], // 大纲设定（兼容保留）
        detail_settings: [],  // 细纲设定
        chapter_settings: [], // 章纲设定
        chapter_summary: [],  // 正文摘要
        custom_knowledge: []  // 用户自定义资料库
    },
    // 资料库分类配置
    knowledgeCategories: [
        { id: 'db-outline-main', key: 'outline', name: '大纲', icon: 'ri-draft-line', builtin: true },
        { id: 'db-char', key: 'characters', name: '角色档案', icon: 'ri-user-smile-line', builtin: true },
        { id: 'db-world', key: 'worldbuilding', name: '世界观设定', icon: 'ri-earth-line', builtin: true },
        { id: 'db-item', key: 'items', name: '道具物品', icon: 'ri-sword-line', builtin: true },
        { id: 'db-event', key: 'eventlines', name: '事件线', icon: 'ri-git-branch-line', builtin: true },
        { id: 'db-detail', key: 'detail_settings', name: '细纲设定', icon: 'ri-file-text-line', builtin: true },
        { id: 'db-chapter', key: 'chapter_settings', name: '章纲设定', icon: 'ri-book-open-line', builtin: true },
        { id: 'db-chsummary', key: 'chapter_summary', name: '正文摘要', icon: 'ri-article-line', builtin: true }
    ],
    copilotVisible: false,
    copilotSessionId: 'copilot',
    focusMode: false,
    copilotWorkflow: null,
    copilotRealtimeHint: null,
    copilotRouting: null,
    copilotAutoSave: {
        enabled: false,
        loaded: false,
        projectId: null
    },
    copilotCreativeMode: 'plan',
    lastWorkflowFocusedRunId: '',
    pendingCreationContract: null,
    currentTaskPool: null,
    collabExecutionTrace: null,
    projectReadyExecution: null,
    runtimeProjectStatus: null,
    collabRuntimePollingTimer: null,
    collabRuntimePollingBusy: false,
    collabRuntimePollingIntervalMs: 10000,
    collabRuntimeMinRefreshIntervalMs: 1500,
    collabRuntimeNextPollAt: 0,
    collabRuntimeLastFetchAt: 0,
    collabRuntimeRequestPromise: null,
    lastCopilotWorkflowFetchAt: 0,
    collabRealtimeSocket: null,
    collabRealtimeConnected: false,
    collabRealtimeReconnectTimer: null,
    collabRealtimeRefreshTimer: null,
    activeSubAgent: null,  // 当前活跃的子Agent实时状态 {agent, taskType, title, status, message, timestamp}
    copilotModel: {
        configs: [],
        activeConfigId: '',
        activeModel: '',
        loading: false,
        applying: false
    },
    settings: {
        bgUrl: '',
        bgOpacity: 0.85,
        bgLightness: 12,       // 背景亮度 0-100，0=纯黑，100=纯白
        accentHue: 250,
        accentSaturation: 40,  // 饱和度 0-100，0=黑白灰
        textLightness: 90,     // 字体亮度 0-100
        theme: 'dark'
    }
};

// UI 引用
const ui = {
    resItems: null,
    navPanel: null,
    navTitle: null,
    navList: null,
    navActionAdd: null,
    workspace: null,
    breadcrumbs: null,
    copilotPanel: null,
    toggleCopilotBtn: null,
    closeCopilotBtn: null,
    toggleFocusBtn: null,
    copilotInput: null,
    copilotSendBtn: null,
    copilotMsgs: null,
    resBar: null,
    // 项目选择器
    projectCurrent: null,
    projectDropdown: null,
    projectList: null,
    projectAdd: null,
    currentProjectName: null,
    copilotSessionMode: null,
    copilotSessionAgent: null,
    copilotModelSelect: null,
    copilotModelStatus: null,
    copilotSessionListBtn: null,
    copilotSessionMenu: null,
    copilotWorkflowPanel: null
};

let currentStreamAbort = null;
const appRuntimeLifecycle = {
    windowId: '',
    enabled: false,
    heartbeatTimer: null,
    closeSent: false,
    heartbeatIntervalMs: 5000
};

function createRuntimeWindowId() {
    if (window.crypto && typeof window.crypto.randomUUID === 'function') {
        return window.crypto.randomUUID();
    }
    return `win-${Date.now()}-${Math.random().toString(36).slice(2)}`;
}

function postAppRuntimeEvent(path, useBeacon = false) {
    if (!appRuntimeLifecycle.enabled || !appRuntimeLifecycle.windowId) return false;
    const payload = JSON.stringify({ window_id: appRuntimeLifecycle.windowId });
    if (useBeacon && navigator.sendBeacon) {
        const blob = new Blob([payload], { type: 'application/json' });
        return navigator.sendBeacon(path, blob);
    }
    fetch(path, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: payload,
        keepalive: Boolean(useBeacon),
        credentials: 'same-origin'
    }).catch(() => {});
    return true;
}

function stopAppRuntimeHeartbeat() {
    if (appRuntimeLifecycle.heartbeatTimer) {
        clearInterval(appRuntimeLifecycle.heartbeatTimer);
        appRuntimeLifecycle.heartbeatTimer = null;
    }
}

function notifyAppRuntimeWindowClosed() {
    if (!appRuntimeLifecycle.enabled || appRuntimeLifecycle.closeSent) return;
    appRuntimeLifecycle.closeSent = true;
    stopAppRuntimeHeartbeat();
    postAppRuntimeEvent('/api/app/window-closed', true);
}

async function initAppRuntimeLifecycle() {
    if (appRuntimeLifecycle.windowId) return;
    try {
        const response = await fetch('/api/app/runtime', {
            method: 'GET',
            cache: 'no-store',
            credentials: 'same-origin'
        });
        if (!response.ok) return;
        const runtime = await response.json();
        if (!runtime || !runtime.close_shutdown_enabled) return;

        appRuntimeLifecycle.enabled = true;
        appRuntimeLifecycle.windowId = createRuntimeWindowId();
        appRuntimeLifecycle.heartbeatIntervalMs = Math.max(
            Number(runtime.heartbeat_interval_ms || 5000),
            2000
        );

        postAppRuntimeEvent('/api/app/window-heartbeat');
        appRuntimeLifecycle.heartbeatTimer = setInterval(() => {
            postAppRuntimeEvent('/api/app/window-heartbeat');
        }, appRuntimeLifecycle.heartbeatIntervalMs);

        window.addEventListener('pagehide', notifyAppRuntimeWindowClosed);
        window.addEventListener('beforeunload', notifyAppRuntimeWindowClosed);
    } catch (error) {
        console.debug('[Runtime] 生命周期检测不可用:', error);
    }
}

function resetAppRuntimeLifecycleForTests() {
    stopAppRuntimeHeartbeat();
    appRuntimeLifecycle.windowId = '';
    appRuntimeLifecycle.enabled = false;
    appRuntimeLifecycle.closeSent = false;
    appRuntimeLifecycle.heartbeatIntervalMs = 5000;
}

function setStreamingButtonState(streaming) {
    if (!ui.copilotSendBtn) return;
    const icon = ui.copilotSendBtn.querySelector('i');
    if (!icon) return;
    if (streaming) {
        icon.className = 'ri-stop-fill';
        ui.copilotSendBtn.classList.add('is-streaming');
        ui.copilotSendBtn.title = '停止生成';
    } else {
        icon.className = 'ri-send-plane-fill';
        ui.copilotSendBtn.classList.remove('is-streaming');
        ui.copilotSendBtn.title = '发送';
    }
}

function formatChapterDisplay(chapterNum, title) {
    if (!title || !title.trim()) return `第${chapterNum}章`;
    const stripped = title.replace(/^第[\d一二三四五六七八九十百千万零〇]+章[\s\-_:：]*/, '').trim();
    return stripped ? `第${chapterNum}章 ${stripped}` : `第${chapterNum}章`;
}

// 初始化UI引用
function initUIReferences() {
    ui.resItems = document.querySelectorAll('.res-item[data-module]');
    ui.navPanel = document.getElementById('nav-panel');
    ui.navTitle = document.getElementById('nav-title');
    ui.navList = document.getElementById('nav-list-container');
    ui.navActionAdd = document.getElementById('nav-action-add');
    ui.workspace = document.getElementById('main-view');
    ui.breadcrumbs = document.getElementById('breadcrumbs');
    ui.copilotPanel = document.getElementById('copilot-panel');
    ui.toggleCopilotBtn = document.getElementById('toggle-copilot');
    ui.closeCopilotBtn = document.querySelector('.close-copilot');
    ui.toggleFocusBtn = document.getElementById('toggle-focus');
    ui.copilotInput = document.querySelector('.copilot-input textarea');
    ui.copilotSendBtn = document.querySelector('.copilot-input button');
    ui.copilotMsgs = document.getElementById('copilot-messages');
    ui.resBar = document.querySelector('.resource-bar');
    // 项目选择器
    ui.projectCurrent = document.getElementById('project-current');
    ui.projectDropdown = document.getElementById('project-dropdown');
    ui.projectList = document.getElementById('project-list');
    ui.projectAdd = document.getElementById('project-add');
    ui.currentProjectName = document.getElementById('current-project-name');
    ui.copilotSessionMode = document.getElementById('copilot-session-mode');
    ui.copilotSessionAgent = document.getElementById('copilot-session-agent');
    ui.copilotModelSelect = document.getElementById('copilot-model-select');
    ui.copilotModelStatus = document.getElementById('copilot-model-status');
    ui.copilotSessionListBtn = document.getElementById('copilot-session-list-btn');
    ui.copilotSessionMenu = document.getElementById('copilot-session-menu');
    ui.copilotWorkflowPanel = document.getElementById('copilot-workflow-panel');
}

// 初始化
async function init() {
    initUIReferences();
    restoreCopilotSessionId();
    setCopilotSessionHeader('加载中...');
    bindEvents();
    initAppRuntimeLifecycle();
    await loadSavedSettings(); // 加载保存的主题和背景设置（异步加载IndexedDB背景图片）
    restoreSidebarState(); // 恢复侧边栏状态
    loadKnowledgeCategories(); // 加载自定义资料库分类
    await loadProjects(); // 加载项目列表
    await loadCopilotCreativeModePreference(); // 加载当前项目的Copilot创作方式
    await checkGlobalAPIConfig(); // 检查全局API配置
    await loadCopilotModelOptions({ silent: true }); // 加载聊天面板模型快速切换
    switchModule('dashboard');
    await restoreCopilotHistory();
    await restoreCopilotWorkflowStatus();
    bindCopilotWorkflowPanel();
    syncCopilotToggleButton();
    
    // 初始化Copilot增强功能
    if (typeof initCopilotEnhancements === 'function') {
        initCopilotEnhancements();
    }
}

// 检查全局API配置
async function checkGlobalAPIConfig() {
    try {
        const config = await apiCall('/api/global-config', 'GET');
        const globalModel = String(config && config.model || '').trim();
        if (globalModel) {
            setCopilotSessionHeader(globalModel);
        }
        if (!config.is_configured) {
            // 延迟显示提示，避免影响初始加载
            setTimeout(() => {
                showToast('💡 提示：请先在设置中配置全局API', 'warning');
            }, 2000);
        }
    } catch (e) {
        console.error('Failed to check global API config:', e);
    }
}

function getCopilotModelOptionValue(configId, model) {
    return `${encodeURIComponent(String(configId || ''))}::${encodeURIComponent(String(model || ''))}`;
}

function getCopilotModelSelectedOption() {
    const select = ui.copilotModelSelect || document.getElementById('copilot-model-select');
    const option = select?.selectedOptions?.[0];
    if (!option) return { configId: '', model: '' };
    return {
        configId: String(option.dataset.configId || '').trim(),
        model: String(option.dataset.model || '').trim()
    };
}

function setCopilotModelStatus(text = '', state = '') {
    const status = ui.copilotModelStatus || document.getElementById('copilot-model-status');
    if (!status) return;
    status.textContent = text;
    status.className = `copilot-model-status${state ? ` is-${state}` : ''}`;
}

function setCopilotModelApplying(applying) {
    store.copilotModel.applying = Boolean(applying);
    const select = ui.copilotModelSelect || document.getElementById('copilot-model-select');
    if (select) {
        select.disabled = Boolean(applying || store.copilotModel.loading || !store.copilotModel.configs.length);
    }
}

function renderCopilotModelSelector() {
    const select = ui.copilotModelSelect || document.getElementById('copilot-model-select');
    if (!select) return;

    const configs = Array.isArray(store.copilotModel.configs) ? store.copilotModel.configs : [];
    const activeConfigId = String(store.copilotModel.activeConfigId || '').trim();
    const activeModel = String(store.copilotModel.activeModel || '').trim();
    select.innerHTML = '';

    if (store.copilotModel.loading) {
        const option = document.createElement('option');
        option.value = '';
        option.textContent = '加载模型中...';
        select.appendChild(option);
        select.disabled = true;
        return;
    }

    const configured = configs.filter((cfg) => cfg && Array.isArray(cfg.models) && cfg.models.length > 0);
    if (!configured.length) {
        const option = document.createElement('option');
        option.value = '';
        option.textContent = '未配置可切换模型';
        select.appendChild(option);
        select.disabled = true;
        return;
    }

    let selectedValue = '';
    configured.forEach((cfg) => {
        const configId = String(cfg.id || '').trim();
        const configName = String(cfg.name || '未命名配置').trim();
        (cfg.models || []).forEach((rawModel) => {
            const model = String(rawModel || '').trim();
            if (!configId || !model) return;
            const option = document.createElement('option');
            option.value = getCopilotModelOptionValue(configId, model);
            option.dataset.configId = configId;
            option.dataset.model = model;
            option.textContent = `${configName} / ${model}`;
            if (configId === activeConfigId && model === activeModel) {
                option.selected = true;
                selectedValue = option.value;
            }
            select.appendChild(option);
        });
    });

    if (!selectedValue && select.options.length > 0) {
        select.selectedIndex = 0;
    }
    select.disabled = Boolean(store.copilotModel.applying);
}

function syncCopilotModelSelectorSelection(configId, model) {
    const select = ui.copilotModelSelect || document.getElementById('copilot-model-select');
    const normalizedConfigId = String(configId || '').trim();
    const normalizedModel = String(model || '').trim();
    if (normalizedConfigId) {
        store.copilotModel.activeConfigId = normalizedConfigId;
    }
    if (normalizedModel) {
        store.copilotModel.activeModel = normalizedModel;
    }
    if (!select) return;
    for (const option of Array.from(select.options || [])) {
        if (
            (!normalizedConfigId || option.dataset.configId === normalizedConfigId)
            && (!normalizedModel || option.dataset.model === normalizedModel)
        ) {
            select.value = option.value;
            return;
        }
    }
}

async function loadCopilotModelOptions(options = {}) {
    if (typeof apiCall !== 'function') return;
    const silent = Boolean(options.silent);
    store.copilotModel.loading = true;
    renderCopilotModelSelector();
    try {
        const data = await apiCall('/api/api-configs', 'GET');
        store.copilotModel.configs = Array.isArray(data?.configs) ? data.configs : [];
        store.copilotModel.activeConfigId = String(data?.active_config_id || '').trim();
        store.copilotModel.activeModel = String(data?.active_model || '').trim();
        if (store.copilotModel.activeModel) {
            updateCopilotSessionModelLabel(store.copilotModel.activeModel);
        }
        setCopilotModelStatus('');
    } catch (error) {
        console.warn('[Copilot] 加载模型选择器失败:', error);
        if (!silent) {
            setCopilotModelStatus('加载失败', 'error');
        }
    } finally {
        store.copilotModel.loading = false;
        renderCopilotModelSelector();
    }
}

async function applyCopilotModelSelection(configId, model) {
    const normalizedConfigId = String(configId || '').trim();
    const normalizedModel = String(model || '').trim();
    if (!normalizedConfigId || !normalizedModel || typeof apiCall !== 'function') return false;

    setCopilotModelApplying(true);
    setCopilotModelStatus('应用中...', 'loading');
    try {
        const response = await apiCall('/api/api-configs/active', 'POST', {
            config_id: normalizedConfigId,
            model: normalizedModel
        });
        const activeConfigId = String(response?.active_config_id || normalizedConfigId).trim();
        const activeModel = String(response?.active_model || normalizedModel).trim();
        store.copilotModel.activeConfigId = activeConfigId;
        store.copilotModel.activeModel = activeModel;
        updateCopilotSessionModelLabel(activeModel);
        syncCopilotModelSelectorSelection(activeConfigId, activeModel);
        setCopilotModelStatus('已切换', 'success');
        window.dispatchEvent(new CustomEvent('global-api-config-updated', {
            detail: { activeConfigId, activeModel }
        }));
        if (typeof showToast === 'function') {
            showToast(`聊天模型已切换为 ${activeModel}`, 'success');
        }
        setTimeout(() => {
            if (String(store.copilotModel.activeModel || '') === activeModel) {
                setCopilotModelStatus('');
            }
        }, 1800);
        return true;
    } catch (error) {
        console.error('[Copilot] 切换聊天模型失败:', error);
        renderCopilotModelSelector();
        setCopilotModelStatus('切换失败', 'error');
        if (typeof showToast === 'function') {
            showToast(`切换模型失败: ${error.message || error}`, 'error');
        }
        return false;
    } finally {
        setCopilotModelApplying(false);
    }
}

// 绑定事件
function bindEvents() {
    window.addEventListener('global-api-config-updated', (event) => {
        const activeModel = String(event.detail?.activeModel || event.detail?.active_model || '').trim();
        const activeConfigId = String(event.detail?.activeConfigId || event.detail?.active_config_id || '').trim();
        if (activeModel) {
            updateCopilotSessionModelLabel(activeModel);
            syncCopilotModelSelectorSelection(activeConfigId, activeModel);
            void loadCopilotModelOptions({ silent: true });
        } else {
            checkGlobalAPIConfig();
            void loadCopilotModelOptions({ silent: true });
        }
    });

    if (ui.copilotModelSelect && ui.copilotModelSelect.dataset.bound !== 'true') {
        ui.copilotModelSelect.dataset.bound = 'true';
        ui.copilotModelSelect.addEventListener('change', () => {
            const { configId, model } = getCopilotModelSelectedOption();
            applyCopilotModelSelection(configId, model);
        });
    }

    // 资源栏切换
    ui.resItems.forEach(item => {
        item.addEventListener('click', () => switchModule(item.dataset.module));
    });

    // Copilot 开关
    if (ui.toggleCopilotBtn) {
        ui.toggleCopilotBtn.addEventListener('click', toggleCopilot);
    }
    if (ui.closeCopilotBtn) {
        ui.closeCopilotBtn.addEventListener('click', toggleCopilot);
    }
    
    // 新建会话按钮
    const newChatBtn = document.getElementById('new-chat-btn');
    if (newChatBtn) {
        newChatBtn.addEventListener('click', clearCopilotChat);
    }
    if (ui.copilotSessionListBtn) {
        ui.copilotSessionListBtn.addEventListener('click', (e) => {
            e.stopPropagation();
            toggleCopilotSessionMenu();
        });
    }

    // Copilot 发送
    if (ui.copilotSendBtn) {
        ui.copilotSendBtn.addEventListener('click', () => {
            if (currentStreamAbort) {
                currentStreamAbort.abort();
                currentStreamAbort = null;
                setStreamingButtonState(false);
            } else {
                sendCopilotMessage();
            }
        });
    }
    if (ui.copilotInput) {
        ui.copilotInput.addEventListener('keydown', (e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                if (!currentStreamAbort) sendCopilotMessage();
            }
        });
    }

    // 专注模式
    if (ui.toggleFocusBtn) {
        ui.toggleFocusBtn.addEventListener('click', toggleFocusMode);
    }

    // 项目选择器
    if (ui.projectCurrent) {
        ui.projectCurrent.addEventListener('click', toggleProjectDropdown);
    }
    if (ui.projectAdd) {
        ui.projectAdd.addEventListener('click', showCreateProjectDialog);
    }

    // 点击外部关闭下拉
    document.addEventListener('click', (e) => {
        if (ui.projectDropdown && !ui.projectDropdown.classList.contains('hidden')) {
            if (!e.target.closest('.project-selector')) {
                ui.projectDropdown.classList.add('hidden');
                ui.projectCurrent?.setAttribute('aria-expanded', 'false');
            }
        }
        if (ui.copilotSessionMenu && !ui.copilotSessionMenu.classList.contains('hidden')) {
            if (!e.target.closest('#copilot-session-list-btn') && !e.target.closest('#copilot-session-menu')) {
                hideCopilotSessionMenu();
            }
        }
    });

    document.addEventListener('visibilitychange', () => {
        if (document.hidden) {
            stopNovelCollabRuntimePolling();
            return;
        }
        if (shouldPollNovelCollabRuntime()) {
            startNovelCollabRuntimePolling();
        }
    });

    // 侧边栏收缩按钮
    const sidebarToggleBtn = document.getElementById('sidebar-toggle-btn');
    if (sidebarToggleBtn) {
        sidebarToggleBtn.addEventListener('click', (e) => {
            e.stopPropagation();
            toggleSidebar();
        });
    }
}

// ===== 核心逻辑：模块切换 =====
function switchModule(moduleId) {
    const shouldOpenMergedKnowledge = moduleId === 'world' && typeof window.openMultiAgentKnowledgeWorkspace === 'function';
    const normalizedModuleId = shouldOpenMergedKnowledge ? 'write' : moduleId;
    const previousModule = store.currentModule;
    store.currentModule = normalizedModuleId;

    // 更新资源栏激活状态
    ui.resItems.forEach(item => {
        item.classList.toggle('active', item.dataset.module === normalizedModuleId);
    });

    // 更新导航面板
    renderNavPanel(normalizedModuleId);
    
    // 控制创作助手按钮的显示（只在多Agent创作模式显示）
    const isWritingModule = normalizedModuleId === 'write';
    const wasWritingModule = previousModule === 'write';
    // 如果切换到非创作模块，自动关闭Copilot面板
    if (!isWritingModule && store.copilotVisible) {
        setCopilotVisible(false);
    }
    // 首次进入创作模块时默认打开山海·云烟助手
    if (isWritingModule && !wasWritingModule && !store.copilotVisible) {
        setCopilotVisible(true);
    }
    syncCopilotToggleButton();

    if (isWritingModule) {
        connectNovelCollabRealtime();
    } else {
        disconnectNovelCollabRealtime();
    }

    if (!shouldPollNovelCollabRuntime()) {
        stopNovelCollabRuntimePolling();
    } else {
        startNovelCollabRuntimePolling();
    }

    // 根据模块渲染工作区
    if (normalizedModuleId === 'dashboard') {
        renderDashboard();
    } else if (normalizedModuleId === 'short-story') {
        if (typeof renderShortStoryInterface === 'function') {
            renderShortStoryInterface();
        } else {
            console.error('[switchModule] renderShortStoryInterface not found');
        }
    } else if (normalizedModuleId === 'novel-to-script') {
        if (typeof renderNovelToScriptInterface === 'function') {
            renderNovelToScriptInterface();
        } else {
            console.error('[switchModule] renderNovelToScriptInterface not found');
        }
    } else if (normalizedModuleId === 'infinite-write') {
        // 无限续写模块
        if (typeof renderInfiniteWriteInterface === 'function') {
            renderInfiniteWriteInterface();
        } else {
            console.error('[switchModule] renderInfiniteWriteInterface not found');
        }
    } else if (normalizedModuleId === 'settings') {
        renderSettings(); // 渲染设置页面容器，然后自动加载主题设置
    } else if (normalizedModuleId === 'write') {
        if (shouldOpenMergedKnowledge) {
            window.openMultiAgentKnowledgeWorkspace();
        } else {
            // 不自动渲染协作状态面板，只显示空编辑器
            showEmptyEditor();
        }
    } else if (normalizedModuleId === 'aux-memory' || normalizedModuleId === 'knowledge-workbench') {
        // 知识中心已合并到Wiki系统
        if (typeof WikiModule !== 'undefined' && typeof WikiModule.render === 'function') {
            WikiModule.render();
        } else {
            console.error('[switchModule] WikiModule not found');
        }
    } else if (normalizedModuleId === 'about') {
        // 关于页面
        if (typeof renderAboutPage === 'function') {
            renderAboutPage();
        }
    } else if (normalizedModuleId === 'wiki') {
        // Wiki知识系统
        if (typeof WikiModule !== 'undefined' && typeof WikiModule.render === 'function') {
            WikiModule.render();
        } else {
            console.error('[switchModule] WikiModule not found');
        }
    }
}

// ===== 侧边栏收缩功能 =====
function toggleSidebar() {
    const workbench = document.querySelector('.workbench');
    const navPanel = document.getElementById('nav-panel');

    if (workbench && navPanel) {
        const isCollapsed = workbench.classList.contains('sidebar-collapsed');

        if (isCollapsed) {
            // 展开侧边栏
            workbench.classList.remove('sidebar-collapsed');
            workbench.style.gridTemplateColumns = '';  // 恢复默认
            navPanel.style.width = '';
            navPanel.style.display = '';
        } else {
            // 收缩侧边栏
            workbench.classList.add('sidebar-collapsed');
            workbench.style.gridTemplateColumns = 'var(--res-bar-w) 0px 1fr auto';
            navPanel.style.width = '0';
            navPanel.style.display = 'none';
        }

        localStorage.setItem('sidebar_collapsed', !isCollapsed ? 'true' : 'false');
    }
}

// 初始化时恢复侧边栏状态
function restoreSidebarState() {
    const isCollapsed = localStorage.getItem('sidebar_collapsed') === 'true';
    if (isCollapsed) {
        const workbench = document.querySelector('.workbench');
        const navPanel = document.getElementById('nav-panel');
        if (workbench && navPanel) {
            workbench.classList.add('sidebar-collapsed');
            workbench.style.gridTemplateColumns = 'var(--res-bar-w) 0px 1fr auto';
            navPanel.style.width = '0';
            navPanel.style.display = 'none';
        }
    }
}

// ===== Copilot 基础功能 =====

const COPILOT_SESSION_STORAGE_KEY = 'copilot_active_session_id';

function isCopilotModule() {
    return store.currentModule === 'write';
}

function setCopilotVisible(visible) {
    store.copilotVisible = Boolean(visible);
    if (ui.copilotPanel) {
        ui.copilotPanel.classList.toggle('collapsed', !store.copilotVisible);
        ui.copilotPanel.style.display = store.copilotVisible ? 'flex' : 'none';
    }
    if (!store.copilotVisible) {
        hideCopilotSessionMenu();
    } else {
        // Copilot 打开时，更新状态面板
        updateCopilotWorkflowPanel();
    }
    if (store.currentModule === 'write') {
        connectNovelCollabRealtime();
        startNovelCollabRuntimePolling();
    }
    syncCopilotToggleButton();
}

function syncCopilotToggleButton() {
    if (!ui.toggleCopilotBtn) return;
    const shouldShow = isCopilotModule() && !store.copilotVisible;
    ui.toggleCopilotBtn.style.display = shouldShow ? 'flex' : 'none';
}

function hideCopilotSessionMenu() {
    if (!ui.copilotSessionMenu) return;
    ui.copilotSessionMenu.classList.add('hidden');
}

function getCurrentCopilotSessionId() {
    return String(store.copilotSessionId || '').trim() || 'copilot';
}

function setCurrentCopilotSessionId(sessionId) {
    const next = String(sessionId || '').trim() || 'copilot';
    store.copilotSessionId = next;
    localStorage.setItem(COPILOT_SESSION_STORAGE_KEY, next);
}

function restoreCopilotSessionId() {
    const saved = localStorage.getItem(COPILOT_SESSION_STORAGE_KEY);
    setCurrentCopilotSessionId(saved || 'copilot');
}

function getCopilotWelcomeHtml() {
    return `你好！我是你的写作助手。试试：
        <ul style="margin: 8px 0; padding-left: 20px;">
            <li>输入 <code>@</code> 引用角色、章节或设定</li>
            <li>输入 <code>/</code> 查看显式命令，例如 <code>/create</code></li>
            <li>直接提问或发指令</li>
        </ul>`;
}

function renderCopilotWelcomeMessage() {
    if (!ui.copilotMsgs) return;
    ui.copilotMsgs.innerHTML = '';
    const welcomeMsg = document.createElement('div');
    welcomeMsg.className = 'msg ai';
    welcomeMsg.innerHTML = getCopilotWelcomeHtml();
    ui.copilotMsgs.appendChild(welcomeMsg);
}

function getWorkflowStatusLabel(status) {
    const value = String(status || '').trim().toLowerCase();
    const labels = {
        running: '执行中',
        completed: '已完成',
        failed: '执行失败',
        paused: '已暂停',
        cancelled: '已取消',
        starting: '准备中'
    };
    return labels[value] || (value || '待机');
}

function getWorkflowFileStatusLabel(status) {
    return String(status || '').trim() === 'updated' ? '已更新' : '已创建';
}

function normalizeWorkflowFiles(files) {
    if (!Array.isArray(files)) return [];
    return files
        .filter((item) => item && typeof item === 'object')
        .map((item) => ({
            path: String(item.path || '').trim(),
            label: String(item.label || item.name || '').trim(),
            kind: translateTechnicalText(String(item.kind || 'file').trim()),
            status: String(item.status || 'created').trim()
        }))
        .filter((item) => item.path);
}

function normalizeWorkflowTaskQueue(tasks) {
    if (!Array.isArray(tasks)) return [];
    return tasks
        .filter((item) => item && typeof item === 'object')
        .map((item) => ({
            task_id: String(item.task_id || '').trim(),
            title: String(item.title || item.task_type || item.task_id || '').trim(),
            task_type: String(item.task_type || '').trim(),
            target_agent: String(item.target_agent || '').trim(),
            status: String(item.status || 'pending').trim() || 'pending',
            retry_count: Number(item.retry_count || 0) || 0,
            review_required: Boolean(item.review_required)
        }))
        .filter((item) => item.task_id || item.title);
}

function normalizeWorkflowReviews(reviews) {
    if (!Array.isArray(reviews)) return [];
    return reviews
        .filter((item) => item && typeof item === 'object')
        .map((item) => ({
            task_id: String(item.task_id || '').trim(),
            artifact_type: String(item.artifact_type || '').trim(),
            passed: Boolean(item.passed),
            severity: String(item.severity || '').trim(),
            revision_target: String(item.revision_target || '').trim(),
            issues: Array.isArray(item.issues) ? item.issues.map((issue) => {
                if (typeof issue === 'string') return issue;
                return String(issue?.message || issue?.type || '').trim();
            }).filter(Boolean) : []
        }));
}

function normalizeCopilotWorkflow(workflow) {
    if (!workflow || typeof workflow !== 'object') return null;
    const modelLabel = extractModelLabelFromPayload(workflow);
    return {
        run_id: String(workflow.run_id || '').trim(),
        status: String(workflow.status || '').trim() || 'idle',
        command: String(workflow.command || '').trim(),
        current_agent: String(workflow.current_agent || '').trim(),
        target_agent: String(workflow.target_agent || '').trim(),
        stage: String(workflow.stage || '').trim(),
        last_progress: formatWorkflowProgressText(workflow.last_progress || ''),
        last_error: translateTechnicalText(String(workflow.last_error || '').trim()),
        output_dir: String(workflow.output_dir || '').trim(),
        focus_module: String(workflow.focus_module || '').trim(),
        focus_chapter: Number(workflow.focus_chapter || 0) || 0,
        model: modelLabel,
        current_model: String(workflow.current_model || modelLabel || '').trim(),
        active_model: String(workflow.active_model || modelLabel || '').trim(),
        model_used: String(workflow.model_used || modelLabel || '').trim(),
        created_files: normalizeWorkflowFiles(workflow.created_files),
        updated_files: normalizeWorkflowFiles(workflow.updated_files),
        reused_files: normalizeWorkflowFiles(workflow.reused_files),
        workflow_plan: workflow.workflow_plan && typeof workflow.workflow_plan === 'object' ? workflow.workflow_plan : {},
        task_queue: normalizeWorkflowTaskQueue(workflow.task_queue),
        completed_tasks: Array.isArray(workflow.completed_tasks) ? workflow.completed_tasks : [],
        reviews: normalizeWorkflowReviews(workflow.reviews),
        handoff_notes: Array.isArray(workflow.handoff_notes) ? workflow.handoff_notes : []
    };
}

function normalizeRuntimeProjectStatus(status) {
    if (!status || typeof status !== 'object') return null;
    const modelLabel = extractModelLabelFromPayload(status);
    return {
        workflow_state: String(status.workflow_state || 'idle').trim() || 'idle',
        checkpoint: status.checkpoint && typeof status.checkpoint === 'object' ? status.checkpoint : {},
        project: status.project && typeof status.project === 'object' ? status.project : {},
        model: modelLabel,
        current_model: String(status.current_model || modelLabel || '').trim(),
        active_model: String(status.active_model || modelLabel || '').trim(),
        model_used: String(status.model_used || modelLabel || '').trim()
    };
}

function translateTechnicalText(text) {
    let value = String(text || '').trim();
    if (!value) return '';
    const replacements = [
        [/OpenAI Chat Completions/gi, '聊天补全接口'],
        [/OpenAI Responses API/gi, '响应接口'],
        [/OpenAI Responses/gi, '响应接口'],
        [/Anthropic Messages API/gi, 'Anthropic 消息接口'],
        [/Anthropic Messages/gi, 'Anthropic 消息接口'],
        [/Max Tokens/gi, '最大输出长度'],
        [/Temperature/gi, '温度参数'],
        [/Markdown/gi, '格式化文本'],
        [/Slash 命令/gi, '快捷命令'],
        [/Agent/gi, '助手'],
        [/Coordinator/gi, '创作协调器'],
        [/Communicator/gi, '沟通助手'],
        [/Worldbuilder/gi, '世界观构建师'],
        [/Outliner/gi, '大纲规划师'],
        [/DetailOutlineBuilder/gi, '细纲构建师'],
        [/ChapterSettingBuilder/gi, '章纲构建师'],
        [/EventlineBuilder/gi, '事件线构建师'],
        [/ChapterWriter/gi, '章节写手'],
        [/ContinuousWriter/gi, '续写助手'],
        [/Polisher/gi, '润色助手'],
        [/SummaryOrchestrator/gi, '摘要编排助手'],
        [/ContextStrategy/gi, '上下文策略助手'],
        [/ContentReader/gi, '内容读取助手'],
        [/ContentExpansion/gi, '内容扩展助手'],
        [/FileNaming/gi, '文件命名助手'],
        [/CharacterBuilder/gi, '角色构建师'],
        [/ProjectDataBuilder/gi, '项目资料构建器'],
        [/Router/gi, '智能路由'],
        [/WebSearch/gi, '网络搜索助手'],
        [/TrendsSearch/gi, '热点搜索助手'],
        [/missing_chapter_number/gi, '缺少章节号：当前任务没有拿到要写第几章'],
        [/chapter_not_found/gi, '未找到对应章节：请先生成或检查大纲'],
        [/missing_outline/gi, '缺少大纲：需要先有章节大纲才能写正文'],
        [/empty_workflow_plan/gi, '没有可执行的工作流计划'],
        [/unsupported_task_type/gi, '当前任务类型还不支持自动执行'],
        [/max_chapter_tasks_reached/gi, '这一轮连续写章先跑满了'],
        [/max_tasks_reached/gi, '这一轮任务先跑到上限了'],
        [/fallback_triggered/gi, '系统已触发回退处理'],
        [/review_required/gi, '这一步需要先复核确认'],
        [/task_failed/gi, '任务执行失败'],
        [/\bchapters\b/gi, '正文章节'],
        [/\bworldbuilding\b/gi, '世界观设定'],
        [/\bcharacters\b/gi, '角色档案'],
        [/\boutline\b/gi, '大纲'],
        [/\beventlines\b/gi, '事件线'],
        [/\bdetail_settings\b/gi, '细纲设定'],
        [/\bchapter_settings\b/gi, '章纲设定'],
        [/\bchapter_summary\b/gi, '正文摘要'],
        [/running/gi, '执行中'],
        [/starting/gi, '准备中'],
        [/completed/gi, '已完成'],
        [/failed/gi, '执行失败'],
        [/paused/gi, '已暂停'],
        [/cancelled/gi, '已取消'],
        [/pending/gi, '等待中'],
        [/claimed/gi, '已接收'],
        [/blocked/gi, '受阻'],
        [/idle/gi, '空闲'],
        [/file/gi, '文件'],
        [/created/gi, '已创建'],
        [/updated/gi, '已更新'],
        [/reused/gi, '已复用']
    ];
    replacements.forEach(([pattern, replacement]) => {
        value = value.replace(pattern, replacement);
    });
    return value;
}

function stripVisibleMarkdownHeadingMarkers(text) {
    return String(text || '')
        .split(/\r?\n/)
        .map((line) => line
            .replace(/^\s{0,3}#{1,6}\s*/, '')
            .replace(/\s+#{1,6}\s*$/, '')
            .trim())
        .filter(Boolean)
        .join(' ')
        .replace(/\s+/g, ' ')
        .trim();
}

function formatWorkflowProgressText(text) {
    return translateTechnicalText(stripVisibleMarkdownHeadingMarkers(text));
}

function isInternalStreamEventType(value) {
    const type = String(value || '').trim();
    return [
        'llm_chunk',
        'tool_call',
        'tool_result',
        'agent_task_progress',
        'agent_task_completed',
        'agent_task_failed'
    ].includes(type);
}

function isProtocolOnlyPayload(payload) {
    if (!payload || typeof payload !== 'object' || Array.isArray(payload)) return false;
    const type = String(payload.type || '').trim();
    if (isInternalStreamEventType(type)) return true;
    if (type === 'chunk' && (payload.content !== undefined || payload.delta !== undefined || payload.text !== undefined)) {
        return false;
    }
    if (payload.reply || payload.response || payload.message || payload.text || payload.summary || payload.result_summary) {
        return false;
    }
    const protocolKeys = [
        'type', 'agent', 'current_agent', 'target_agent', 'delta', 'seed', 'source', 'source_type',
        'source_preview', 'metadata', 'created_at', 'updated_at', 'revision_notes', 'task_id',
        'task_type', 'status', 'stage', 'model', 'model_used', 'current_model', 'active_model',
        'usage', 'index', 'id', '_id'
    ];
    return Object.keys(payload).length > 0 && Object.keys(payload).every((key) => protocolKeys.includes(key));
}

function extractVisibleTextFromStructuredPayload(payload, depth = 0) {
    if (depth > 5 || payload === null || payload === undefined) return '';
    if (typeof payload === 'string') {
        return payload.trim();
    }
    if (Array.isArray(payload)) {
        return payload
            .map((item) => extractVisibleTextFromStructuredPayload(item, depth + 1))
            .filter(Boolean)
            .join('\n')
            .trim();
    }
    if (typeof payload !== 'object') return '';
    if (isProtocolOnlyPayload(payload)) return '';

    const preferredFields = ['reply', 'response'];
    const visibleFields = ['reply', 'response', 'content', 'message', 'text', 'summary', 'result_summary'];
    for (const field of preferredFields) {
        const value = payload[field];
        if (typeof value === 'string' && value.trim()) {
            return value.trim();
        }
    }
    for (const field of visibleFields) {
        const value = payload[field];
        if (typeof value === 'string' && value.trim()) {
            return value.trim();
        }
    }
    for (const field of ['delegated_result', 'result', 'data', 'payload', 'output']) {
        const visible = extractVisibleTextFromStructuredPayload(payload[field], depth + 1);
        if (visible) return visible;
    }
    return '';
}

function parseFirstJsonPayloadFromText(text) {
    const rawValue = String(text || '');
    const leadingMatch = rawValue.match(/^\s*/);
    const leadingLength = leadingMatch ? leadingMatch[0].length : 0;
    const value = rawValue.slice(leadingLength);
    if (!value || !/^[\[{]/.test(value)) {
        return { status: 'not-json' };
    }

    const closingFor = { '{': '}', '[': ']' };
    const stack = [];
    let inString = false;
    let escaped = false;
    let jsonEnd = -1;

    for (let i = 0; i < value.length; i += 1) {
        const char = value[i];
        if (inString) {
            if (escaped) {
                escaped = false;
            } else if (char === '\\') {
                escaped = true;
            } else if (char === '"') {
                inString = false;
            }
            continue;
        }

        if (char === '"') {
            inString = true;
            continue;
        }

        if (char === '{' || char === '[') {
            stack.push(closingFor[char]);
            continue;
        }

        if (char === '}' || char === ']') {
            if (!stack.length || stack[stack.length - 1] !== char) {
                return { status: 'invalid' };
            }
            stack.pop();
            if (!stack.length) {
                jsonEnd = i + 1;
                break;
            }
        }
    }

    if (jsonEnd < 0) {
        return { status: 'partial' };
    }

    try {
        const jsonText = value.slice(0, jsonEnd);
        const payload = JSON.parse(jsonText);
        const rest = value.slice(jsonEnd);
        return { status: 'complete', payload, rest };
    } catch (_) {
        return { status: 'invalid' };
    }
}

function looksLikeProtocolFragment(text) {
    const value = String(text || '').trim();
    if (!value) return false;
    if (/^[\[{]/.test(value)) return true;
    if (/^(data:\s*)?["']?(type|agent|current_agent|target_agent|delta|content|seed|source|metadata|status|stage|task_id|task_type)["']?\s*[:：,]?/i.test(value)) {
        return true;
    }
    if (/^["']?[A-Za-z_][\w-]{0,40}["']?\s*[:：,]\s*["']?[^"']{0,80}$/.test(value) && !/[。！？!?，、]/.test(value)) {
        return true;
    }
    const lines = value.split(/\r?\n/).map((line) => line.trim()).filter(Boolean);
    if (!lines.length || lines.length > 18) return false;
    const protocolLineCount = lines.filter((line) => (
        /^["']?[A-Za-z_][\w-]{0,40}["']?\s*[:：,]?\s*["']?[^"']{0,80}["']?,?$/.test(line)
        || /^[{}\[\]",:：-]+$/.test(line)
    )).length;
    return protocolLineCount === lines.length;
}

function stripLeadingProtocolNoise(text) {
    let value = String(text || '').replace(/^\s+/, '');
    while (value) {
        const next = value.replace(/^(?:[{}\[\]",:：-]|\b(?:type|agent|current_agent|target_agent|delta|content|seed|source|metadata|status|stage|task_id|task_type)\b)\s*/i, '');
        if (next === value) break;
        value = next.replace(/^\s+/, '');
    }
    return value;
}

function createCopilotStreamTextFilter() {
    let pending = '';

    function consume(value) {
        if (value === null || value === undefined) return '';
        pending += String(value);
        if (!pending.trim()) {
            pending = '';
            return '';
        }

        const visibleParts = [];
        while (pending.trim()) {
            const parsed = parseFirstJsonPayloadFromText(pending);
            if (parsed.status === 'partial') {
                return visibleParts.join('');
            }
            if (parsed.status === 'complete') {
                const visible = extractVisibleTextFromStructuredPayload(parsed.payload);
                if (visible) {
                    visibleParts.push(visible);
                }
                pending = parsed.rest || '';
                continue;
            }

            if (looksLikeProtocolFragment(pending)) {
                return visibleParts.join('');
            }

            const visible = stripLeadingProtocolNoise(pending).replace(/^\s+/, '');
            pending = '';
            if (visible) {
                visibleParts.push(visible);
            }
        }

        pending = '';
        return visibleParts.join('');
    }

    function flush() {
        if (!pending) return '';
        const leftover = pending;
        pending = '';
        if (looksLikeProtocolFragment(leftover)) return '';
        return stripLeadingProtocolNoise(leftover).trim();
    }

    return {
        push: consume,
        flush
    };
}

function getWorkflowStageDisplayName(stageName) {
    const labels = {
        build_world: '世界观构建',
        build_outline: '大纲生成',
        write_chapter: '章节写作',
        summary_orchestrate: '阶段总结',
        context_plan: '上下文规划',
        content_read: '内容读取',
        evaluate_chapter: '章节评估',
        polish_chapter: '章节润色',
        expand_content: '内容补足',
        project_dispatch: '项目调度',
        contract_init: '合同初始化',
        worldbuilding: '世界观构建',
        chapters: '正文章节',
        outlining: '大纲生成',
        writing: '章节写作',
        completed: '已完成',
        failed: '执行失败',
        paused: '已暂停',
        cancelled: '已取消',
        starting: '准备中'
    };
    const key = String(stageName || '').trim();
    return labels[key] || translateTechnicalText(key);
}

function renderCompactWorkflowQueue(flow) {
    const tasks = Array.isArray(flow?.task_queue) ? flow.task_queue.slice(0, 6) : [];
    const reviews = Array.isArray(flow?.reviews) ? flow.reviews : [];
    if (!tasks.length && !reviews.length) return '';

    const statusLabels = {
        pending: '等待中',
        running: '执行中',
        completed: '已完成',
        failed: '失败',
        revision_requested: '待修订'
    };
    const taskRows = tasks.map((task, index) => {
        const title = window.escapeHtml ? window.escapeHtml(translateTechnicalText(task.title || task.task_type || `任务 ${index + 1}`)) : translateTechnicalText(task.title || task.task_type || `任务 ${index + 1}`);
        const status = String(task.status || 'pending').trim().toLowerCase();
        const statusText = statusLabels[status] || translateTechnicalText(status);
        const review = reviews.find((item) => item.task_id === task.task_id);
        const reviewText = review ? (review.passed ? '审查通过' : '审查退回') : (task.review_required ? '待审查' : '');
        return `
            <div class="copilot-workflow-task-row">
                <span class="copilot-workflow-task-index">${index + 1}</span>
                <span class="copilot-workflow-task-title">${title}</span>
                <span class="copilot-workflow-task-status">${window.escapeHtml ? window.escapeHtml(statusText) : statusText}</span>
                ${reviewText ? `<span class="copilot-workflow-task-review">${window.escapeHtml ? window.escapeHtml(reviewText) : reviewText}</span>` : ''}
            </div>
        `;
    }).join('');
    const latestIssue = reviews
        .flatMap((review) => Array.isArray(review.issues) ? review.issues : [])
        .filter(Boolean)
        .slice(-1)[0] || '';
    const issueHtml = latestIssue
        ? `<div class="copilot-workflow-review-note">${window.escapeHtml ? window.escapeHtml(latestIssue) : latestIssue}</div>`
        : '';
    return `
        <div class="copilot-workflow-task-queue">
            ${taskRows}
            ${issueHtml}
        </div>
    `;
}

function normalizeCopilotRouting(routing) {
    if (!routing || typeof routing !== 'object') return null;
    const modelLabel = extractModelLabelFromPayload(routing);
    return {
        intent: String(routing.intent || '').trim(),
        target_agent: String(routing.target_agent || '').trim(),
        model: modelLabel,
        current_model: String(routing.current_model || modelLabel || '').trim(),
        active_model: String(routing.active_model || modelLabel || '').trim(),
        model_used: String(routing.model_used || modelLabel || '').trim(),
        confidence: Number(routing.confidence || 0) || 0
    };
}

function shouldShowWorkflowPanel(workflow) {
    if (!workflow) return false;
    const status = String(workflow.status || '').trim().toLowerCase();
    if (['running', 'starting', 'completed', 'failed', 'paused', 'cancelled'].includes(status)) {
        return true;
    }
    if (workflow.last_error) return true;
    if (workflow.run_id || workflow.last_progress) return true;
    if (Array.isArray(workflow.created_files) && workflow.created_files.length > 0) return true;
    if (Array.isArray(workflow.updated_files) && workflow.updated_files.length > 0) return true;
    if (Array.isArray(workflow.task_queue) && workflow.task_queue.length > 0) return true;
    if (Array.isArray(workflow.reviews) && workflow.reviews.length > 0) return true;
    return false;
}

function hasMeaningfulWorkflowState(workflow) {
    return Boolean(workflow && shouldShowWorkflowPanel(workflow));
}

async function handleAssistantAutoSaveResult(autoSave) {
    if (!autoSave || !autoSave.applied) return;
    try {
        if (typeof loadCurrentProjectData === 'function') {
            await loadCurrentProjectData();
        }
        if (typeof updateMentionData === 'function') {
            updateMentionData();
        }
        if (typeof renderKnowledgeNavPanel === 'function') {
            renderKnowledgeNavPanel();
        }
        if (store.currentModule === 'write' && typeof window.renderMultiAgentWriteNavPanel === 'function') {
            window.renderMultiAgentWriteNavPanel();
        }
        if (typeof showToast === 'function' && autoSave.summary) {
            showToast(autoSave.summary, 'success');
        }
    } catch (error) {
        console.warn('[Copilot] 助手回复自动同步后刷新失败:', error);
    }
}

function buildRealtimeWorkflowHint(payload, messageType) {
    if (!payload || typeof payload !== 'object') return null;
    const agent = String(payload.agent || payload.current_agent || '').trim();
    const progressMessage = String(
        payload.message
        || payload.progress_message
        || payload.result_summary
        || payload.error
        || payload.stage
        || payload.type
        || ''
    ).trim();
    const stage = String(payload.stage || payload.type || messageType || '').trim();
    const status = payload.error
        ? 'failed'
        : (messageType === 'alert' ? 'failed' : 'running');
    const modelLabel = extractModelLabelFromPayload(payload);
    const hint = normalizeCopilotWorkflow({
        status,
        current_agent: agent || 'Coordinator',
        target_agent: agent || '',
        stage,
        last_progress: progressMessage,
        model: modelLabel,
        current_model: modelLabel
    });
    return hasMeaningfulWorkflowState(hint) ? hint : null;
}

function mapRuntimeWorkflowStateToStatus(workflowState, tasks) {
    const normalizedState = String(workflowState || '').trim().toLowerCase();
    if (normalizedState === 'paused') return 'paused';
    if (normalizedState === 'failed') return 'failed';
    if (normalizedState === 'cancelled') return 'cancelled';
    if (normalizedState === 'completed') return 'completed';
    if (['writing', 'worldbuilding', 'outlining', 'editing', 'reviewing'].includes(normalizedState)) {
        return 'running';
    }
    if (Array.isArray(tasks) && tasks.some((task) => ['running', 'claimed', 'blocked'].includes(String(task?.status || '').trim().toLowerCase()))) {
        return 'running';
    }
    if (Array.isArray(tasks) && tasks.some((task) => String(task?.status || '').trim().toLowerCase() === 'pending')) {
        return 'starting';
    }
    if (Array.isArray(tasks) && tasks.length > 0 && tasks.every((task) => String(task?.status || '').trim().toLowerCase() === 'completed')) {
        return 'completed';
    }
    return normalizedState && normalizedState !== 'idle' ? 'running' : 'idle';
}

function deriveWorkflowFromRuntime() {
    const runtimeStatus = store.runtimeProjectStatus && typeof store.runtimeProjectStatus === 'object'
        ? store.runtimeProjectStatus
        : null;
    const taskPool = store.currentTaskPool && typeof store.currentTaskPool === 'object'
        ? store.currentTaskPool
        : null;
    const trace = store.collabExecutionTrace && typeof store.collabExecutionTrace === 'object'
        ? store.collabExecutionTrace
        : null;
    const tasks = Array.isArray(taskPool?.tasks) ? taskPool.tasks.filter((item) => item && typeof item === 'object') : [];
    const activeTask = tasks.find((task) => ['running', 'claimed', 'blocked'].includes(String(task.status || '').trim().toLowerCase()))
        || tasks.find((task) => String(task.status || '').trim().toLowerCase() === 'pending')
        || null;
    const lastTraceEvent = Array.isArray(trace?.events) && trace.events.length > 0
        ? trace.events[trace.events.length - 1]
        : null;
    const workflowState = String(runtimeStatus?.workflow_state || trace?.status || '').trim();
    const status = mapRuntimeWorkflowStateToStatus(workflowState, tasks);
    const projectInfo = runtimeStatus?.project && typeof runtimeStatus.project === 'object'
        ? runtimeStatus.project
        : {};
    const checkpoint = runtimeStatus?.checkpoint && typeof runtimeStatus.checkpoint === 'object'
        ? runtimeStatus.checkpoint
        : {};
    const completedChapters = Number(projectInfo.completed_chapters || 0) || 0;
    const totalChapters = Number(projectInfo.total_chapters || 0) || 0;
    const currentChapter = Number(checkpoint.current_chapter || 0) || 0;
    const activeTaskTitle = activeTask
        ? String(activeTask.title || activeTask.task_type || '').trim()
        : '';
    const traceTitle = lastTraceEvent
        ? String(lastTraceEvent.title || lastTraceEvent.message || lastTraceEvent.task_type || '').trim()
        : '';
    let lastProgress = activeTaskTitle || traceTitle;
    if (!lastProgress && totalChapters > 0) {
        lastProgress = `章节进度 ${completedChapters}/${totalChapters}`;
    } else if (!lastProgress && currentChapter > 0) {
        lastProgress = `当前章节 ${currentChapter}`;
    }

    const currentAgent = activeTask
        ? String(activeTask.assigned_agent || '').trim()
        : String(lastTraceEvent?.agent || lastTraceEvent?.assigned_agent || '').trim();
    const stage = activeTask
        ? String(activeTask.task_type || activeTask.title || '').trim()
        : String(workflowState || lastTraceEvent?.task_type || lastTraceEvent?.type || '').trim();

    const derivedWorkflow = normalizeCopilotWorkflow({
        status,
        current_agent: currentAgent || (status !== 'idle' ? 'Coordinator' : ''),
        target_agent: currentAgent || '',
        stage: getWorkflowStageDisplayName(stage),
        last_progress: lastProgress,
        focus_chapter: currentChapter
    });

    return hasMeaningfulWorkflowState(derivedWorkflow) ? derivedWorkflow : null;
}

function renderWorkflowFileList(title, files) {
    const safeTitle = window.escapeHtml ? window.escapeHtml(title) : title;
    const rows = files.slice(0, 8).map((item) => {
        const label = window.escapeHtml ? window.escapeHtml(item.label || item.path) : (item.label || item.path);
        const kind = window.escapeHtml ? window.escapeHtml(item.kind || 'file') : (item.kind || 'file');
        const status = getWorkflowFileStatusLabel(item.status);
        const path = window.escapeHtml ? window.escapeHtml(item.path) : item.path;
        return `
            <div class="copilot-workflow-file">
                <button type="button" class="copilot-workflow-file-main-btn" data-workflow-path="${path}" title="预览文件">
                    <div class="copilot-workflow-file-main">
                        <span class="copilot-workflow-file-kind">${kind}</span>
                        <span class="copilot-workflow-file-label">${label}</span>
                    </div>
                    <span class="copilot-workflow-file-status">${status}</span>
                </button>
                <button type="button" class="copilot-workflow-file-action" data-workflow-download="${path}" title="下载文件">
                    <i class="ri-download-line"></i>
                </button>
            </div>
        `;
    }).join('');
    return `
        <div class="copilot-workflow-files">
            <div class="copilot-workflow-files-title">${safeTitle}</div>
            <div class="copilot-workflow-file-list">${rows}</div>
        </div>
    `;
}

function updateCopilotWorkflowPanel(workflow, routing) {
    const normalizedWorkflow = workflow === undefined ? store.copilotWorkflow : normalizeCopilotWorkflow(workflow);
    const normalizedRouting = routing === undefined ? store.copilotRouting : normalizeCopilotRouting(routing);
    const effectiveWorkflow = hasMeaningfulWorkflowState(normalizedWorkflow)
        ? normalizedWorkflow
        : hasMeaningfulWorkflowState(store.copilotRealtimeHint)
            ? store.copilotRealtimeHint
            : deriveWorkflowFromRuntime();

    store.copilotWorkflow = normalizedWorkflow;
    store.copilotRouting = normalizedRouting;

    if (DEBUG_COPILOT_WORKFLOW) {
        console.log('[DEBUG] updateCopilotWorkflowPanel called:', {
            workflow: normalizedWorkflow,
            effectiveWorkflow,
            routing: normalizedRouting,
            uiWorkflowPanelExists: !!ui.copilotWorkflowPanel,
            uiWorkflowPanelClass: ui.copilotWorkflowPanel?.className,
            copilotVisible: store.copilotVisible
        });
    }

    if (!ui.copilotWorkflowPanel) {
        if (DEBUG_COPILOT_WORKFLOW) {
            console.log('[DEBUG] ui.copilotWorkflowPanel is null!');
        }
        return;
    }

    // 构建简化状态信息
    const route = normalizedRouting || {};
    const flow = effectiveWorkflow || normalizedWorkflow || {};
    const currentAgent = String(flow.current_agent || route.target_agent || '').trim();
    const status = String(flow.status || '').trim().toLowerCase();
    const rawProgress = String(flow.last_progress || flow.stage || '').trim();
    const progress = getWorkflowStageDisplayName(rawProgress);
    const targetAgent = String(route.target_agent || '').trim();

    // 如果没有任何有效状态信息，显示默认状态
    const effectiveAgent = currentAgent || targetAgent || '';
    const hasValidStatus = status && status !== 'idle' && status !== '';
    const hasMeaningfulData = effectiveAgent || progress || hasValidStatus;
    if (!hasMeaningfulData) {
        ui.copilotWorkflowPanel.innerHTML = '';
        ui.copilotWorkflowPanel.classList.add('hidden');
        return;
    }

    // 状态映射
    const statusMap = {
        'running': { text: '进行中', color: '#22c55e' },
        'starting': { text: '启动中', color: '#f59e0b' },
        'completed': { text: '已完成', color: '#6366f1' },
        'failed': { text: '失败', color: '#ef4444' },
        'paused': { text: '已暂停', color: '#f59e0b' },
        'cancelled': { text: '已取消', color: '#6b7280' }
    };

    const agentDisplayMap = {
        'Worldbuilder': '🌍 世界观构建',
        'Outliner': '📋 大纲规划',
        'EventlineBuilder': '🧭 事件线构建',
        'DetailOutlineBuilder': '🗂️ 细纲构建',
        'ChapterSettingBuilder': '📑 章纲构建',
        'ChapterWriter': '✍️ 章节创作',
        'ContinuousWriter': '🔄 续写生成',
        'Polisher': '✨ 润色处理',
        'SummaryOrchestrator': '🧾 摘要编排',
        'Coordinator': '🎯 创作协调',
        'Communicator': '💬 沟通助手',
        'Router': '🔀 智能路由',
        'WebSearch': '🔍 网络搜索',
        'TrendsSearch': '🔥 热点搜索'
    };

    const currentAgentDisplay = agentDisplayMap[currentAgent] || getAgentDisplayName(currentAgent) || '等待中';
    const statusInfo = statusMap[status] || { text: '待机', color: '#6b7280' };
    const queueHtml = renderCompactWorkflowQueue(flow);

    // 如果有活跃子Agent实时状态，优先展示
    const subAgent = store.activeSubAgent;
    if (subAgent && subAgent.agent && subAgent.status) {
        const subAgentDisplayMap = {
            'Worldbuilder': '🌍 世界观构建器',
            'Outliner': '📋 大纲规划器',
            'EventlineBuilder': '🧭 事件线构建器',
            'DetailOutlineBuilder': '🗂️ 细纲构建器',
            'ChapterSettingBuilder': '📑 章纲构建器',
            'ChapterWriter': '✍️ 章节写作器',
            'ContinuousWriter': '🔄 续写生成器',
            'Polisher': '✨ 润色处理器',
            'SummaryOrchestrator': '🧾 摘要编排助手（内部）',
            'Coordinator': '🎯 创作协调器',
            'Communicator': '💬 沟通助手',
            'Router': '🔀 智能路由',
            'ContextStrategy': '🧠 上下文策略助手（内部）',
            'ContentReader': '📖 内容读取助手（内部）',
            'ContentExpansion': '📝 内容扩展助手（内部）',
            'FileNaming': '📁 文件命名助手（内部）',
            'Evaluator': '🔍 质量评估器',
            'CharacterBuilder': '👤 角色构建器'
        };
        const subAgentDisplay = subAgentDisplayMap[subAgent.agent] || getAgentDisplayName(subAgent.agent);
        const subAgentTitle = translateTechnicalText(subAgent.title || subAgent.taskType || '');

        const subStatusMap = {
            'running': { indicator: '🟢', color: '#22c55e', label: '执行中', pulseClass: 'copilot-sub-agent-pulse' },
            'fallback': { indicator: '🟡', color: '#f59e0b', label: '回退执行', pulseClass: 'copilot-sub-agent-pulse' },
            'completed': { indicator: '✅', color: '#6366f1', label: '已完成', pulseClass: '' },
            'failed': { indicator: '🔴', color: '#ef4444', label: '失败', pulseClass: '' }
        };
        const subStatus = subStatusMap[subAgent.status] || subStatusMap['running'];

        ui.copilotWorkflowPanel.innerHTML = `
            <div class="copilot-workflow-simple">
                <span class="agent-status" style="display: inline-flex; align-items: center; gap: 6px; font-size: 12px; width: 100%;">
                    <span class="${subStatus.pulseClass}" style="font-size: 10px; line-height: 1;">${subStatus.indicator}</span>
                    <span style="color: var(--text-primary); font-weight: 600; font-size: 12px;">${subAgentDisplay}</span>
                    <span style="padding: 2px 8px; border-radius: 10px; font-size: 10px; background: ${subStatus.color}20; color: ${subStatus.color}; font-weight: 500;">${subStatus.label}</span>
                    ${subAgentTitle ? `<span style="color: var(--text-secondary); font-size: 11px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; max-width: 200px;">· ${window.escapeHtml ? window.escapeHtml(subAgentTitle) : subAgentTitle}</span>` : ''}
                </span>
            </div>
        `;
        ui.copilotWorkflowPanel.classList.remove('hidden');
        return;
    }

    // 构建状态HTML
    let statusHtml = `<span class="agent-status" style="display: inline-flex; align-items: center; gap: 6px; font-size: 12px;">`;

    if (currentAgent) {
        statusHtml += `<span style="color: var(--text-primary); font-weight: 500;">${currentAgentDisplay}</span>`;
    }

    if (status && status !== 'idle') {
        statusHtml += `<span style="padding: 2px 8px; border-radius: 10px; font-size: 10px; background: ${statusInfo.color}20; color: ${statusInfo.color};">${statusInfo.text}</span>`;
    }

    if (progress) {
        statusHtml += `<span style="color: var(--text-secondary); font-size: 11px;">· ${progress}</span>`;
    }

    if (targetAgent && targetAgent !== currentAgent && targetAgent !== 'Communicator') {
        const targetDisplay = agentDisplayMap[targetAgent] || getAgentDisplayName(targetAgent);
        statusHtml += `<span style="color: var(--text-secondary); font-size: 11px;">→ ${targetDisplay}</span>`;
    }

    statusHtml += `</span>`;

    ui.copilotWorkflowPanel.innerHTML = `
        <div class="copilot-workflow-simple">
            ${statusHtml}
            ${queueHtml}
        </div>
    `;
    ui.copilotWorkflowPanel.classList.remove('hidden');
}

function getNovelCollabRuntimeSnapshot() {
    return {
        runtimeProjectStatus: store.runtimeProjectStatus,
        taskPool: store.currentTaskPool,
        collabExecutionTrace: store.collabExecutionTrace,
        creationContract: store.pendingCreationContract,
        projectReadyExecution: store.projectReadyExecution
    };
}

async function refreshNovelCollabRuntime(options = {}) {
    const force = Boolean(options && options.force);
    const now = Date.now();

    if (!force) {
        if (store.collabRuntimeRequestPromise) {
            return store.collabRuntimeRequestPromise;
        }
        if (store.collabRuntimeNextPollAt && now < store.collabRuntimeNextPollAt) {
            return getNovelCollabRuntimeSnapshot();
        }
        const recentRefresh = store.collabRuntimeLastFetchAt && (now - store.collabRuntimeLastFetchAt) < store.collabRuntimeMinRefreshIntervalMs;
        if (recentRefresh) {
            return getNovelCollabRuntimeSnapshot();
        }
    }

    const requestPromise = (async () => {
        try {
            const res = await apiCall('/api/v1/status', 'GET');
            store.collabRuntimeNextPollAt = 0;
            store.collabRuntimeLastFetchAt = Date.now();
            store.copilotRealtimeHint = null;
            store.runtimeProjectStatus = normalizeRuntimeProjectStatus(res);
            store.currentTaskPool = res && res.task_pool ? res.task_pool : null;
            store.collabExecutionTrace = res && res.collab_execution_trace ? res.collab_execution_trace : null;
            store.projectReadyExecution = res && res.project_ready_execution ? res.project_ready_execution : null;
            updateCopilotSessionModelLabel(extractModelLabelFromPayload(res));
            if (res && res.creation_contract) {
                store.pendingCreationContract = res.creation_contract;
            }
            return getNovelCollabRuntimeSnapshot();
        } catch (e) {
            if (Number(e?.status) === 429) {
                const retryAfterSeconds = Number(e?.retryAfter || 0) || 0;
                const retryAfterMs = retryAfterSeconds > 0
                    ? retryAfterSeconds * 1000
                    : Math.max(store.collabRuntimePollingIntervalMs * 3, 10000);
                store.collabRuntimeNextPollAt = Date.now() + retryAfterMs;
            }
            return getNovelCollabRuntimeSnapshot();
        } finally {
            if (store.collabRuntimeRequestPromise === requestPromise) {
                store.collabRuntimeRequestPromise = null;
            }
        }
    })();

    store.collabRuntimeRequestPromise = requestPromise;
    return requestPromise;
}

function shouldPollNovelCollabRuntime() {
    const runtimeWorkflowState = String(store.runtimeProjectStatus?.workflow_state || '').trim().toLowerCase();
    return Boolean(
        store.currentModule === 'write'
        && (
            store.copilotVisible
            || !!store.currentTaskPool
            || !!store.collabExecutionTrace
            || !!store.projectReadyExecution
            || hasMeaningfulWorkflowState(store.copilotWorkflow)
            || (runtimeWorkflowState && runtimeWorkflowState !== 'idle')
        )
    );
}

function stopNovelCollabRuntimePolling() {
    if (store.collabRuntimePollingTimer) {
        clearInterval(store.collabRuntimePollingTimer);
        store.collabRuntimePollingTimer = null;
    }
    store.collabRuntimePollingBusy = false;
    store.collabRuntimeNextPollAt = 0;
    store.collabRuntimeRequestPromise = null;
}

function clearNovelCollabRealtimeReconnectTimer() {
    if (store.collabRealtimeReconnectTimer) {
        clearTimeout(store.collabRealtimeReconnectTimer);
        store.collabRealtimeReconnectTimer = null;
    }
}

function clearNovelCollabRealtimeRefreshTimer() {
    if (store.collabRealtimeRefreshTimer) {
        clearTimeout(store.collabRealtimeRefreshTimer);
        store.collabRealtimeRefreshTimer = null;
    }
}

function scheduleNovelCollabRuntimeRefresh(delayMs = 1500) {
    if (store.collabRealtimeRefreshTimer) {
        return;
    }
    store.collabRealtimeRefreshTimer = window.setTimeout(async () => {
        store.collabRealtimeRefreshTimer = null;
        const runtime = await refreshNovelCollabRuntime();
        if (
            ['status', 'task-pool'].includes(String(window.multiAgentWriteState?.activeView || '').trim())
            && typeof window.renderCollabTaskPoolWorkspace === 'function'
        ) {
            window.renderCollabTaskPoolWorkspace(runtime.taskPool, runtime.collabExecutionTrace, runtime.projectReadyExecution);
        }
        updateCopilotWorkflowPanel(store.copilotWorkflow, store.copilotRouting);
    }, Math.max(0, Number(delayMs) || 0));
}

function shouldUseNovelCollabRealtime() {
    return Boolean(
        store.currentModule === 'write'
        && typeof window.WebSocket === 'function'
    );
}

function getNovelCollabRealtimeSocketUrl() {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    return `${protocol}//${window.location.host}/ws`;
}

function handleNovelCollabRealtimePayload(messageType, payload) {
    if (!payload || typeof payload !== 'object') {
        return;
    }
    updateCopilotSessionModelLabel(extractModelLabelFromPayload(payload));
    const realtimeAgentLabel = String(payload.agent || payload.current_agent || payload.target_agent || '').trim();
    if (realtimeAgentLabel) {
        updateCopilotSessionAgentLabel(realtimeAgentLabel, payload.status || payload.type || messageType || '');
    }
    // 处理子Agent实时状态事件
    const subAgentEventType = String(payload.type || '').trim();
    if (['sub_agent_started', 'sub_agent_completed', 'sub_agent_failed', 'sub_agent_dispatching', 'sub_agent_fallback'].includes(subAgentEventType)) {
        const agentName = String(payload.agent || '').trim();
        const taskTitle = String(payload.title || payload.task_type || '').trim();
        const taskType = String(payload.task_type || '').trim();
        const eventMessage = String(payload.message || '').trim();

        if (subAgentEventType === 'sub_agent_started' || subAgentEventType === 'sub_agent_dispatching' || subAgentEventType === 'sub_agent_fallback') {
            store.activeSubAgent = {
                agent: agentName,
                taskType: taskType,
                title: taskTitle,
                status: subAgentEventType === 'sub_agent_fallback' ? 'fallback' : 'running',
                message: eventMessage,
                timestamp: Date.now()
            };
        } else if (subAgentEventType === 'sub_agent_completed') {
            store.activeSubAgent = {
                agent: agentName,
                taskType: taskType,
                title: taskTitle,
                status: 'completed',
                message: eventMessage,
                timestamp: Date.now()
            };
            // 完成状态短暂显示后自动清除
            setTimeout(() => {
                if (store.activeSubAgent && store.activeSubAgent.status === 'completed' && store.activeSubAgent.agent === agentName && store.activeSubAgent.taskType === taskType) {
                    store.activeSubAgent = null;
                }
            }, 2500);
        } else if (subAgentEventType === 'sub_agent_failed') {
            store.activeSubAgent = {
                agent: agentName,
                taskType: taskType,
                title: taskTitle,
                status: 'failed',
                message: eventMessage,
                error: String(payload.error || '').trim(),
                timestamp: Date.now()
            };
            // 失败状态显示更久
            setTimeout(() => {
                if (store.activeSubAgent && store.activeSubAgent.status === 'failed' && store.activeSubAgent.agent === agentName && store.activeSubAgent.taskType === taskType) {
                    store.activeSubAgent = null;
                }
            }, 5000);
        }
        // 在聊天消息流中显示内联状态
        showInlineStatusFromSubAgent(payload);
        updateCopilotWorkflowPanel(store.copilotWorkflow, store.copilotRouting);
        scheduleNovelCollabRuntimeRefresh(600);
        return;
    }

    if (['progress', 'stage_change', 'chapter_complete', 'status_update', 'workflow_state', 'alert'].includes(messageType)) {
        const hint = buildRealtimeWorkflowHint(payload, messageType);
        if (hint) {
            store.copilotRealtimeHint = hint;
            updateCopilotWorkflowPanel(store.copilotWorkflow, store.copilotRouting);
        }
        scheduleNovelCollabRuntimeRefresh(messageType === 'chapter_complete' ? 100 : 600);
        return;
    }
    if (messageType === 'notification') {
        const text = String(payload.message || '').trim().toLowerCase();
        if (text.includes('subscribed')) {
            scheduleNovelCollabRuntimeRefresh(0);
        }
    }
}

function scheduleNovelCollabRealtimeReconnect(delayMs = 2000) {
    if (!shouldUseNovelCollabRealtime()) {
        return;
    }
    clearNovelCollabRealtimeReconnectTimer();
    store.collabRealtimeReconnectTimer = window.setTimeout(() => {
        store.collabRealtimeReconnectTimer = null;
        connectNovelCollabRealtime();
    }, Math.max(500, Number(delayMs) || 2000));
}

function disconnectNovelCollabRealtime() {
    clearNovelCollabRealtimeReconnectTimer();
    clearNovelCollabRealtimeRefreshTimer();
    const socket = store.collabRealtimeSocket;
    store.collabRealtimeSocket = null;
    store.collabRealtimeConnected = false;
    if (socket && socket.readyState === window.WebSocket.OPEN) {
        try {
            socket.close();
        } catch (_) {
            // ignore close errors
        }
        return;
    }
    if (socket && socket.readyState === window.WebSocket.CONNECTING) {
        try {
            socket.close();
        } catch (_) {
            // ignore close errors
        }
    }
}

function connectNovelCollabRealtime() {
    if (!shouldUseNovelCollabRealtime()) {
        disconnectNovelCollabRealtime();
        return;
    }
    const existingSocket = store.collabRealtimeSocket;
    if (existingSocket && (existingSocket.readyState === window.WebSocket.OPEN || existingSocket.readyState === window.WebSocket.CONNECTING)) {
        return;
    }

    clearNovelCollabRealtimeReconnectTimer();

    const socket = new window.WebSocket(getNovelCollabRealtimeSocketUrl());
    store.collabRealtimeSocket = socket;

    socket.addEventListener('open', () => {
        if (store.collabRealtimeSocket !== socket) {
            return;
        }
        store.collabRealtimeConnected = true;
        try {
            socket.send(JSON.stringify({ action: 'subscribe', topic: 'novel_progress' }));
        } catch (_) {
            // ignore send errors; close handler will reconnect
        }
        startNovelCollabRuntimePolling();
        scheduleNovelCollabRuntimeRefresh(0);
    });

    socket.addEventListener('message', (event) => {
        if (store.collabRealtimeSocket !== socket) {
            return;
        }
        let parsed = null;
        try {
            parsed = JSON.parse(String(event.data || ''));
        } catch (_) {
            return;
        }
        handleNovelCollabRealtimePayload(String(parsed?.type || '').trim(), parsed?.payload);
    });

    socket.addEventListener('error', () => {
        if (store.collabRealtimeSocket === socket) {
            store.collabRealtimeConnected = false;
        }
    });

    socket.addEventListener('close', () => {
        if (store.collabRealtimeSocket === socket) {
            store.collabRealtimeSocket = null;
            store.collabRealtimeConnected = false;
            if (shouldPollNovelCollabRuntime()) {
                startNovelCollabRuntimePolling();
            }
            scheduleNovelCollabRealtimeReconnect();
        }
    });
}

function startNovelCollabRuntimePolling() {
    if (!shouldPollNovelCollabRuntime()) {
        stopNovelCollabRuntimePolling();
        return;
    }
    if (store.collabRuntimePollingTimer) {
        return;
    }
    store.collabRuntimePollingTimer = window.setInterval(async () => {
        if (!shouldPollNovelCollabRuntime()) {
            stopNovelCollabRuntimePolling();
            return;
        }
        if (store.collabRuntimeNextPollAt && Date.now() < store.collabRuntimeNextPollAt) {
            return;
        }
        if (store.collabRuntimePollingBusy) {
            return;
        }
        store.collabRuntimePollingBusy = true;
        try {
            const runtime = await refreshNovelCollabRuntime();
            if (
                ['status', 'task-pool'].includes(String(window.multiAgentWriteState?.activeView || '').trim())
                && typeof window.renderCollabTaskPoolWorkspace === 'function'
            ) {
                window.renderCollabTaskPoolWorkspace(runtime.taskPool, runtime.collabExecutionTrace, runtime.projectReadyExecution);
            }
            if (typeof updateCopilotWorkflowPanel === 'function') {
                updateCopilotWorkflowPanel(store.copilotWorkflow, store.copilotRouting);
            }
        } finally {
            store.collabRuntimePollingBusy = false;
        }
    }, store.collabRuntimePollingIntervalMs);
}

async function fetchCopilotWorkflowStatus() {
    const sessionId = getCurrentCopilotSessionId();
    const res = await apiCall(`/api/v1/chat/workflow-status?session_id=${encodeURIComponent(sessionId)}`, 'GET');
    const workflow = normalizeCopilotWorkflow(res && res.workflow);
    store.copilotWorkflow = workflow;
    updateCopilotSessionModelLabel(extractModelLabelFromPayload(res));
    store.lastCopilotWorkflowFetchAt = Date.now();
    return workflow;
}

async function restoreCopilotWorkflowStatus() {
    try {
        await fetchCopilotWorkflowStatus();
    } catch (e) {
        store.copilotWorkflow = null;
    }
    await refreshNovelCollabRuntime();
    updateCopilotWorkflowPanel(store.copilotWorkflow, store.copilotRouting);
    connectNovelCollabRealtime();
}

function bindCopilotWorkflowPanel() {
    if (!ui.copilotWorkflowPanel || ui.copilotWorkflowPanel.dataset.bound === '1') return;
    ui.copilotWorkflowPanel.dataset.bound = '1';
    ui.copilotWorkflowPanel.addEventListener('click', async (event) => {
        const previewBtn = event.target.closest('.copilot-workflow-file-main-btn');
        if (previewBtn) {
            const filePath = String(previewBtn.dataset.workflowPath || '').trim();
            if (filePath) {
                await previewWorkflowFile(filePath);
            }
            return;
        }
        
        // 新增：查看详情按钮
        const viewBtn = event.target.closest('[data-workflow-view]');
        if (viewBtn) {
            const filePath = String(viewBtn.dataset.workflowView || '').trim();
            const fileKind = String(viewBtn.dataset.workflowKind || '').trim();
            if (filePath && fileKind) {
                navigateToFileLocation(fileKind);
            }
            return;
        }
        
        const downloadBtn = event.target.closest('[data-workflow-download]');
        if (downloadBtn) {
            const filePath = String(downloadBtn.dataset.workflowDownload || '').trim();
            if (!filePath) return;
            const sessionId = getCurrentCopilotSessionId();
            const url = normalizeApiUrl(`/api/v1/chat/workflow-file?session_id=${encodeURIComponent(sessionId)}&path=${encodeURIComponent(filePath)}`);
            window.open(url, '_blank');
        }
    });
}

// 新增：导航到文件对应位置
function navigateToFileLocation(fileKind) {
    const kindModuleMap = {
        'worldbuilding': 'world',
        'characters': 'world',
        'items': 'world',
        'outline': 'write',
        'chapter': 'write'
    };
    
    const targetModule = kindModuleMap[fileKind];
    if (!targetModule) return;
    
    switchModule(targetModule);
    
    // 根据类型打开对应分类
    if (fileKind === 'worldbuilding') {
        const worldCategory = store.knowledgeCategories.find(c => c.key === 'worldbuilding');
        if (worldCategory && typeof loadDatabase === 'function') {
            setTimeout(() => loadDatabase(worldCategory.id), 100);
        }
    } else if (fileKind === 'characters') {
        const charCategory = store.knowledgeCategories.find(c => c.key === 'characters');
        if (charCategory && typeof loadDatabase === 'function') {
            setTimeout(() => loadDatabase(charCategory.id), 100);
        }
    } else if (fileKind === 'items') {
        const itemCategory = store.knowledgeCategories.find(c => c.key === 'items');
        if (itemCategory && typeof loadDatabase === 'function') {
            setTimeout(() => loadDatabase(itemCategory.id), 100);
        }
    }
    
    showToast(`已跳转到${fileKind === 'worldbuilding' ? '世界观设定' : fileKind === 'characters' ? '角色档案' : fileKind === 'items' ? '道具物品' : fileKind === 'outline' ? '大纲' : '章节'}`, 'success');
}

function openFilePreviewModal(filePath, responsePayload, downloadUrl) {
    const modal = document.getElementById('modal-container');
    if (!modal || !filePath) return;
    const filename = String(responsePayload && responsePayload.filename || filePath).trim();
    const language = String(responsePayload && responsePayload.language || 'text').trim();
    const content = String(responsePayload && responsePayload.content || '').trim();
    const truncated = Boolean(responsePayload && responsePayload.truncated);
    const rendered = language === 'markdown'
        ? renderMarkdown(content)
        : `<pre style="margin: 0; white-space: pre-wrap; word-break: break-word;"><code>${escapeHtml(content)}</code></pre>`;

    modal.classList.remove('hidden');
    modal.innerHTML = `
        <div class="copilot-preview-overlay">
            <div class="copilot-preview-dialog">
                <div class="copilot-preview-header">
                    <div class="copilot-preview-title">
                        <strong>${escapeHtml(filename)}</strong>
                        <span>${language === 'markdown' ? '格式化文本预览' : '内容预览'}</span>
                    </div>
                    <div class="copilot-preview-actions">
                        <button type="button" class="copilot-preview-download" data-preview-download="${escapeHtml(downloadUrl || '')}" title="下载文件">
                            <i class="ri-download-line"></i>
                        </button>
                        <button type="button" class="copilot-preview-close" title="关闭预览">
                            <i class="ri-close-line"></i>
                        </button>
                    </div>
                </div>
                ${truncated ? '<div class="copilot-preview-tip">文件较大，当前只展示前 120000 个字符。</div>' : ''}
                <div class="copilot-preview-body msg-content">${rendered}</div>
            </div>
        </div>
    `;
    modal.querySelector('.copilot-preview-close')?.addEventListener('click', () => {
        modal.classList.add('hidden');
        modal.innerHTML = '';
    });
    modal.querySelector('.copilot-preview-download')?.addEventListener('click', () => {
        if (!downloadUrl) return;
        window.open(normalizeApiUrl(downloadUrl), '_blank');
    });
    modal.querySelector('.copilot-preview-overlay')?.addEventListener('click', (evt) => {
        if (evt.target === evt.currentTarget) {
            modal.classList.add('hidden');
            modal.innerHTML = '';
        }
    });
}

async function previewWorkflowFile(filePath) {
    const modal = document.getElementById('modal-container');
    if (!modal || !filePath) return;
    const sessionId = getCurrentCopilotSessionId();
    try {
        const previewUrl = `/api/v1/chat/workflow-file-preview?session_id=${encodeURIComponent(sessionId)}&path=${encodeURIComponent(filePath)}`;
        const downloadUrl = `/api/v1/chat/workflow-file?session_id=${encodeURIComponent(sessionId)}&path=${encodeURIComponent(filePath)}`;
        const res = await apiCall(previewUrl, 'GET');
        openFilePreviewModal(filePath, res, downloadUrl);
    } catch (e) {
        showToast(`预览失败: ${e.message}`, 'error');
    }
}

async function previewCollabResultFile(filePath) {
    const modal = document.getElementById('modal-container');
    if (!modal || !filePath) return;
    try {
        const previewUrl = `/api/v1/result-file-preview?path=${encodeURIComponent(filePath)}`;
        const downloadUrl = `/api/v1/result-file?path=${encodeURIComponent(filePath)}`;
        const res = await apiCall(previewUrl, 'GET');
        openFilePreviewModal(filePath, res, downloadUrl);
    } catch (e) {
        showToast(`预览失败: ${e.message}`, 'error');
    }
}
window.previewWorkflowFile = previewWorkflowFile;
window.previewCollabResultFile = previewCollabResultFile;

function maybeFocusWorkflowTarget(workflow) {
    if (!workflow || typeof workflow !== 'object') return;
    const runId = String(workflow.run_id || '').trim();
    const focusModule = String(workflow.focus_module || '').trim();
    const focusChapter = Number(workflow.focus_chapter || 0) || 0;
    const status = String(workflow.status || '').trim().toLowerCase();
    if (!runId || !focusModule) return;
    if (!['running', 'paused', 'cancelled', 'failed', 'completed', 'starting'].includes(status)) return;
    if (store.lastWorkflowFocusedRunId === runId) return;
    const switchModuleFn = typeof window.switchModule === 'function' ? window.switchModule : switchModule;
    const loadProjectDataFn = typeof window.loadCurrentProjectData === 'function' ? window.loadCurrentProjectData : null;
    const openChapterEditorFn = typeof window.openChapterEditor === 'function' ? window.openChapterEditor : null;
    const loadDatabaseFn = typeof window.loadDatabase === 'function' ? window.loadDatabase : null;
    const renderNavPanelFn = typeof window.renderNavPanel === 'function' ? window.renderNavPanel : (typeof renderNavPanel === 'function' ? renderNavPanel : null);

    if (focusModule === 'world') {
        store.lastWorkflowFocusedRunId = runId;
        switchModuleFn('world');
        const worldCategory = Array.isArray(store.knowledgeCategories)
            ? store.knowledgeCategories.find((item) => String(item.key || '').trim() === 'worldbuilding')
            : null;
        if (worldCategory && typeof loadDatabaseFn === 'function') {
            window.setTimeout(() => loadDatabaseFn(worldCategory.id), 80);
        }
        return;
    }

    if (focusModule === 'write') {
        store.lastWorkflowFocusedRunId = runId;
        switchModuleFn('write');

        if (typeof loadProjectDataFn === 'function') {
            Promise.resolve(loadProjectDataFn()).then(() => {
                // 刷新左侧章节列表导航面板
                if (renderNavPanelFn) {
                    renderNavPanelFn('write');
                }
                // 如果有指定章节，打开章节编辑器
                const chapters = typeof window.getMultiAgentChapters === 'function'
                    ? window.getMultiAgentChapters()
                    : (store.projectData.chapters || []);
                if (focusChapter > 0 && typeof openChapterEditorFn === 'function') {
                    if (Array.isArray(chapters) && chapters[focusChapter - 1]) {
                        openChapterEditorFn(focusChapter - 1);
                        showToast(`已定位到第${focusChapter}章`, 'success');
                    }
                } else if (Array.isArray(chapters) && chapters.length > 0) {
                    showToast(`章节列表已更新，共${chapters.length}章`, 'success');
                }
            }).catch((err) => {
                console.warn('[maybeFocusWorkflowTarget] 加载项目数据失败', err);
                if (renderNavPanelFn) {
                    renderNavPanelFn('write');
                }
            });
        } else {
            // 无loadProjectData时，直接刷新面板
            if (renderNavPanelFn) {
                window.setTimeout(() => renderNavPanelFn('write'), 100);
            }
            const chapters = typeof window.getMultiAgentChapters === 'function'
                ? window.getMultiAgentChapters()
                : (store.projectData.chapters || []);
            if (focusChapter > 0 && typeof openChapterEditorFn === 'function' &&
                Array.isArray(chapters) && chapters[focusChapter - 1]) {
                openChapterEditorFn(focusChapter - 1);
            }
        }
    }
}

function toCopilotRole(role) {
    if (role === 'assistant') return 'ai';
    if (role === 'user') return 'user';
    return 'status';
}

function getAgentDisplayName(agentName) {
    const labels = {
        Communicator: '沟通助手',
        Coordinator: '创作协调器',
        Worldbuilder: '世界观构建师',
        Outliner: '大纲规划师',
        EventlineBuilder: '事件线构建师',
        DetailOutlineBuilder: '细纲构建师',
        ChapterSettingBuilder: '章纲构建师',
        ChapterWriter: '章节写手',
        ContinuousWriter: '续写助手',
        Polisher: '润色助手',
        SummaryOrchestrator: '摘要编排助手（内部）',
        Router: '智能路由',
        WebSearch: '网络搜索助手',
        TrendsSearch: '热点搜索助手',
        ProjectManager: '项目管理助手',
        ContextStrategy: '上下文策略助手（内部）',
        ContentReader: '内容读取助手（内部）',
        ContentExpansion: '内容扩展助手（内部）',
        FileNaming: '文件命名助手（内部）'
    };
    const key = String(agentName || '').trim();
    return labels[key] || translateTechnicalText(key) || '系统';
}

function getIntentDisplayName(intentName) {
    const labels = {
        create_novel: '创作任务',
        create_character: '角色档案任务',
        create_eventlines: '事件线任务',
        create_detail_outline: '细纲任务',
        create_chapter_settings: '章纲任务',
        continue_write: '续写任务',
        polish_content: '润色任务',
        search_web: '搜索任务',
        search_trends: '热点任务',
        query_knowledge: '知识库任务',
        general_chat: '对话任务',
        ask_help: '帮助任务',
        provide_feedback: '反馈任务',
        project_manage: '项目任务',
        config_settings: '配置任务'
    };
    return labels[String(intentName || '').trim()] || '任务';
}

function buildRoutingStatusLines(routing, workflow) {
    const lines = [];
    const route = routing && typeof routing === 'object' ? routing : {};
    const flow = workflow && typeof workflow === 'object' ? workflow : {};

    const intent = String(route.intent || '').trim();
    const targetAgent = String(route.target_agent || flow.target_agent || flow.current_agent || '').trim();
    const currentAgent = String(flow.current_agent || targetAgent || '').trim();
    const stage = String(flow.stage || '').trim();
    const progress = formatWorkflowProgressText(flow.last_progress || '');
    const status = String(flow.status || '').trim().toLowerCase();

    if (targetAgent && targetAgent !== 'Communicator') {
        lines.push(`已转交给${getAgentDisplayName(targetAgent)}处理${intent ? `（${getIntentDisplayName(intent)}）` : ''}`);
        if (status === 'running' || status === 'starting' || !status) {
            lines.push('处理状态：进行中');
        } else if (status === 'completed') {
            lines.push('处理状态：已完成');
        } else if (status === 'failed') {
            lines.push('处理状态：失败');
        }
    } else if (targetAgent === 'Communicator') {
        lines.push('沟通助手：正在继续处理当前对话');
    }

    if (currentAgent && currentAgent !== 'Communicator') {
        let agentLine = `${getAgentDisplayName(currentAgent)}：已接收任务`;
        if (progress) {
            agentLine += `，${translateTechnicalText(progress).replace(/\s+/g, ' ').trim()}`;
        } else if (stage) {
            agentLine += `，当前阶段：${translateTechnicalText(stage)}`;
        }
        lines.push(agentLine);

        if (status === 'running' || status === 'starting') {
            const runningTextMap = {
                Worldbuilder: '世界观构建中...',
                Outliner: '大纲规划中...',
                EventlineBuilder: '事件线构建中...',
                DetailOutlineBuilder: '细纲构建中...',
                ChapterSettingBuilder: '章纲构建中...',
                ChapterWriter: '章节创作中...',
                ContinuousWriter: '续写生成中...',
                Polisher: '润色处理中...',
                Coordinator: '创作协调中...',
                WebSearch: '网络搜索中...',
                TrendsSearch: '热点搜索中...'
            };
            lines.push(runningTextMap[currentAgent] || `${getAgentDisplayName(currentAgent)}处理中...`);
        } else if (status === 'completed') {
            lines.push(`${getAgentDisplayName(currentAgent)}：已完成`);
        } else if (status === 'failed') {
            lines.push(`${getAgentDisplayName(currentAgent)}：执行失败`);
        } else if (status === 'paused') {
            lines.push(`${getAgentDisplayName(currentAgent)}：已暂停`);
        } else if (status === 'cancelled') {
            lines.push(`${getAgentDisplayName(currentAgent)}：已取消`);
        }
    } else if (progress) {
        lines.push(`系统状态：${progress}`);
    }

    return lines.filter(Boolean);
}

function renderRoutingStatusBlock(routing, workflow) {
    const lines = buildRoutingStatusLines(routing, workflow);
    if (!lines.length) return '';
    const html = lines.map((line) => `<div class="copilot-route-status-line">${window.escapeHtml ? window.escapeHtml(line) : line}</div>`).join('');
    return `<div class="copilot-route-status">${html}</div>`;
}

async function restoreCopilotHistory() {
    if (!ui.copilotMsgs) return;
    try {
        const sessionId = getCurrentCopilotSessionId();
        const res = await apiCall(`/api/chat/history?session_id=${encodeURIComponent(sessionId)}`, 'GET');
        const history = Array.isArray(res && res.history) ? res.history : [];
        if (history.length === 0) {
            renderCopilotWelcomeMessage();
            return;
        }
        ui.copilotMsgs.innerHTML = '';
        history.forEach(item => {
            appendMessage(item.content || '', toCopilotRole(item.role), false);
        });
        ui.copilotMsgs.scrollTop = ui.copilotMsgs.scrollHeight;
    } catch (e) {
        renderCopilotWelcomeMessage();
    }
}

function formatSessionTime(value) {
    if (!value) return '未知时间';
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return '未知时间';
    return date.toLocaleString('zh-CN', {
        month: '2-digit',
        day: '2-digit',
        hour: '2-digit',
        minute: '2-digit',
    });
}

function renderCopilotSessionMenu(sessions) {
    if (!ui.copilotSessionMenu) return;
    const activeSessionId = getCurrentCopilotSessionId();
    const safeSessions = Array.isArray(sessions) ? sessions : [];
    if (safeSessions.length === 0) {
        ui.copilotSessionMenu.innerHTML = '<div class="copilot-session-empty">暂无会话</div>';
        return;
    }
    ui.copilotSessionMenu.innerHTML = safeSessions.map(session => {
        const sessionId = String(session.session_id || '').trim();
        const preview = window.escapeHtml ? window.escapeHtml(String(session.last_message_preview || '')) : String(session.last_message_preview || '');
        const activeClass = sessionId === activeSessionId ? 'active' : '';
        return `
            <div class="copilot-session-item ${activeClass}" data-session-id="${sessionId}">
                <button type="button" class="copilot-session-switch" data-session-id="${sessionId}">
                    <span class="copilot-session-item-id">${sessionId}</span>
                    <span class="copilot-session-item-time">${formatSessionTime(session.updated_at || session.created_at)}</span>
                    <span class="copilot-session-item-preview">${preview || '空会话'}</span>
                </button>
                <button type="button" class="copilot-session-delete" data-session-id="${sessionId}" title="删除会话">
                    <i class="ri-delete-bin-6-line"></i>
                </button>
            </div>
        `;
    }).join('');
    ui.copilotSessionMenu.querySelectorAll('.copilot-session-switch').forEach(item => {
        item.addEventListener('click', async () => {
            const sessionId = item.dataset.sessionId;
            if (!sessionId) return;
            setCurrentCopilotSessionId(sessionId);
            hideCopilotSessionMenu();
            await restoreCopilotHistory();
            await restoreCopilotWorkflowStatus();
            checkGlobalAPIConfig();
        });
    });
    ui.copilotSessionMenu.querySelectorAll('.copilot-session-delete').forEach(btn => {
        btn.addEventListener('click', async (e) => {
            e.stopPropagation();
            const sessionId = btn.dataset.sessionId;
            if (!sessionId) return;
            await deleteCopilotSession(sessionId);
        });
    });
}

async function deleteCopilotSession(sessionId) {
    const target = String(sessionId || '').trim();
    if (!target) return;
    const isCurrent = target === getCurrentCopilotSessionId();
    try {
        await apiCall(`/api/chat/sessions/${encodeURIComponent(target)}`, 'DELETE');
        const res = await apiCall('/api/chat/sessions', 'GET');
        const sessions = Array.isArray(res && res.sessions) ? res.sessions : [];

        if (isCurrent) {
            if (sessions.length > 0) {
                setCurrentCopilotSessionId(String(sessions[0].session_id || '').trim() || 'copilot');
                await restoreCopilotHistory();
                await restoreCopilotWorkflowStatus();
            } else {
                const newSessionId = await createCopilotSession();
                setCurrentCopilotSessionId(newSessionId);
                renderCopilotWelcomeMessage();
                updateCopilotWorkflowPanel(null);
            }
            checkGlobalAPIConfig();
        }

        renderCopilotSessionMenu(sessions);
        showToast('会话已删除');
    } catch (e) {
        showToast(`删除会话失败: ${e.message}`, 'error');
    }
}

async function toggleCopilotSessionMenu() {
    if (!ui.copilotSessionMenu) return;
    const willShow = ui.copilotSessionMenu.classList.contains('hidden');
    if (!willShow) {
        hideCopilotSessionMenu();
        return;
    }
    try {
        const res = await apiCall('/api/chat/sessions', 'GET');
        renderCopilotSessionMenu(res && res.sessions);
    } catch (e) {
        ui.copilotSessionMenu.innerHTML = '<div class="copilot-session-empty">加载会话失败</div>';
    }
    ui.copilotSessionMenu.classList.remove('hidden');
}

async function createCopilotSession() {
    try {
        const res = await apiCall('/api/chat/sessions', 'POST');
        const sessionId = String(res && res.session_id || '').trim();
        if (sessionId) return sessionId;
    } catch (e) {
        // fall through
    }
    return `copilot_${Date.now()}`;
}

function hideCopilotSessionAgentLabel() {
    if (!ui.copilotSessionAgent) {
        return;
    }
    ui.copilotSessionAgent.textContent = '';
    ui.copilotSessionAgent.classList.add('hidden');
    ui.copilotSessionAgent.setAttribute('aria-hidden', 'true');
}

function setCopilotSessionHeader(modelLabel, _agentLabel) {
    const normalizedModelLabel = String(modelLabel || '').trim() || '未识别模型';
    if (ui.copilotSessionMode) {
        ui.copilotSessionMode.textContent = `模型：${normalizedModelLabel}`;
    }
    hideCopilotSessionAgentLabel();
}

function updateCopilotSessionAgentLabel(_agentLabel, _statusLabel = '') {
    hideCopilotSessionAgentLabel();
}

function updateCopilotSessionModelLabel(modelLabel) {
    const normalizedModelLabel = String(modelLabel || '').trim();
    if (!normalizedModelLabel || !ui.copilotSessionMode) {
        return;
    }
    const currentLabel = String(ui.copilotSessionMode.textContent || '').replace(/^模型：/, '').trim();
    if (normalizedModelLabel !== currentLabel) {
        ui.copilotSessionMode.textContent = `模型：${normalizedModelLabel}`;
    }
    syncCopilotModelSelectorSelection('', normalizedModelLabel);
}

function extractModelLabelFromPayload(payload) {
    if (!payload || typeof payload !== 'object') return '';
    const buckets = [
        payload,
        payload.routing,
        payload.routing_info,
        payload.workflow,
        payload.runtime,
        payload.project,
        payload.checkpoint,
        payload.metadata,
        payload.task_pool,
        payload.task_pool && payload.task_pool.metadata,
        payload.collab_execution_trace,
        payload.delegated_result,
        payload.delegated_result && payload.delegated_result.params,
        payload.data,
        payload.payload
    ];
    for (const bucket of buckets) {
        if (!bucket || typeof bucket !== 'object') continue;
        for (const key of ['model', 'current_model', 'active_model', 'model_used', 'last_model']) {
            const value = String(bucket[key] || '').trim();
            if (value) return value;
        }
    }
    const taskLists = [
        payload.tasks,
        payload.task_pool && payload.task_pool.tasks,
        payload.runtime_task_pool && payload.runtime_task_pool.tasks,
        payload.data && payload.data.tasks
    ];
    for (const tasks of taskLists) {
        if (!Array.isArray(tasks)) continue;
        const activeTask = tasks.find((task) => task && typeof task === 'object' && ['running', 'claimed', 'blocked'].includes(String(task.status || '').trim().toLowerCase()))
            || tasks.find((task) => task && typeof task === 'object' && String(task.status || '').trim().toLowerCase() === 'pending')
            || null;
        const modelLabel = extractModelLabelFromPayload(activeTask);
        if (modelLabel) return modelLabel;
    }
    const events = payload.collab_execution_trace && Array.isArray(payload.collab_execution_trace.events)
        ? payload.collab_execution_trace.events
        : (Array.isArray(payload.events) ? payload.events : []);
    for (let index = events.length - 1; index >= 0; index -= 1) {
        const modelLabel = extractModelLabelFromPayload(events[index]);
        if (modelLabel) return modelLabel;
    }
    return '';
}

function updateCopilotSessionHeaderFromRouting(routing) {
    if (!routing || typeof routing !== 'object') {
        return;
    }
    updateCopilotSessionModelLabel(extractModelLabelFromPayload(routing));
    updateCopilotSessionAgentLabel(routing.current_agent || routing.target_agent || '');
}

const COPILOT_CREATIVE_MODE_STATE_KEY = 'copilot_creative_mode';
const COPILOT_CREATIVE_MODE_DEFAULT = 'plan';
const COPILOT_CREATIVE_MODE_LABELS = {
    plan: '计划后确认',
    discussion: '只讨论',
    execute: '直接执行',
    auto: '智能判断'
};

function normalizeCopilotCreativeMode(value) {
    const mode = String(value || '').trim().toLowerCase();
    return Object.prototype.hasOwnProperty.call(COPILOT_CREATIVE_MODE_LABELS, mode)
        ? mode
        : COPILOT_CREATIVE_MODE_DEFAULT;
}

function readCopilotCreativeModeFromLocalStorage() {
    try {
        return localStorage.getItem(COPILOT_CREATIVE_MODE_STATE_KEY);
    } catch (_error) {
        return null;
    }
}

function writeCopilotCreativeModeToLocalStorage(mode) {
    try {
        localStorage.setItem(COPILOT_CREATIVE_MODE_STATE_KEY, normalizeCopilotCreativeMode(mode));
    } catch (_error) {
        // 本地存储不可用时仍保留内存态。
    }
}

function getCurrentCopilotCreativeMode() {
    if (store.copilotCreativeMode) {
        return normalizeCopilotCreativeMode(store.copilotCreativeMode);
    }
    return normalizeCopilotCreativeMode(readCopilotCreativeModeFromLocalStorage());
}

function renderCopilotCreativeModeSelector() {
    const inputRoot = document.querySelector('.copilot-input');
    if (!inputRoot) return;

    document.querySelector('.copilot-creative-mode-row')?.remove();

    const mode = getCurrentCopilotCreativeMode();
    store.copilotCreativeMode = mode;

    const row = document.createElement('div');
    row.className = 'copilot-creative-mode-row';
    row.innerHTML = `
        <div class="copilot-creative-mode-main">
            <label class="copilot-creative-mode-label" for="copilot-creative-mode-select">创作方式</label>
            <select id="copilot-creative-mode-select" class="copilot-creative-mode-select" aria-label="选择Copilot创作方式">
                ${Object.entries(COPILOT_CREATIVE_MODE_LABELS).map(([value, label]) => (
                    `<option value="${value}"${value === mode ? ' selected' : ''}>${label}</option>`
                )).join('')}
            </select>
        </div>
        <div id="copilot-creative-mode-hint" class="copilot-creative-mode-hint" aria-live="polite"></div>
    `;

    const inputWrapper = inputRoot.querySelector('.copilot-input-wrapper');
    if (inputWrapper) {
        inputRoot.insertBefore(row, inputWrapper);
    } else {
        inputRoot.insertBefore(row, inputRoot.firstChild);
    }
    bindCopilotCreativeModeSelector();
    updateCopilotCreativeModeHint();
}

function updateCopilotCreativeModeHint() {
    const select = document.getElementById('copilot-creative-mode-select');
    const hint = document.getElementById('copilot-creative-mode-hint');
    const mode = normalizeCopilotCreativeMode(select?.value || store.copilotCreativeMode);
    store.copilotCreativeMode = mode;
    if (select) select.value = mode;
    if (hint) {
        hint.textContent = {
            plan: '先整理方案和任务，确认后再写入项目。',
            discussion: '只聊天和完善想法，不写入资料或正文。',
            execute: '明确执行创作任务，并把结果写入项目。',
            auto: '系统按意图判断，明确指令可能直接写入。'
        }[mode];
    }
}

async function loadCopilotCreativeModePreference() {
    let mode = normalizeCopilotCreativeMode(readCopilotCreativeModeFromLocalStorage());
    if (typeof apiCall === 'function') {
        try {
            const response = await apiCall(`/api/project-state/${COPILOT_CREATIVE_MODE_STATE_KEY}`, 'GET');
            const data = response && Object.prototype.hasOwnProperty.call(response, 'data') ? response.data : null;
            if (data && typeof data === 'object' && data.mode) {
                mode = normalizeCopilotCreativeMode(data.mode);
            } else if (typeof data === 'string') {
                mode = normalizeCopilotCreativeMode(data);
            }
        } catch (error) {
            console.warn('[Copilot] 加载创作方式失败，使用本地偏好:', error);
        }
    }
    store.copilotCreativeMode = mode;
    writeCopilotCreativeModeToLocalStorage(mode);
    renderCopilotCreativeModeSelector();
}

async function saveCopilotCreativeModePreference(mode) {
    const normalizedMode = normalizeCopilotCreativeMode(mode);
    store.copilotCreativeMode = normalizedMode;
    writeCopilotCreativeModeToLocalStorage(normalizedMode);
    updateCopilotCreativeModeHint();

    if (typeof apiCall !== 'function') return;
    try {
        await apiCall(`/api/project-state/${COPILOT_CREATIVE_MODE_STATE_KEY}`, 'POST', { data: { mode: normalizedMode } });
        if (typeof showToast === 'function') {
            showToast(`已切换到${COPILOT_CREATIVE_MODE_LABELS[normalizedMode]}`);
        }
    } catch (error) {
        console.warn('[Copilot] 保存创作方式失败:', error);
    }
}

function bindCopilotCreativeModeSelector() {
    const select = document.getElementById('copilot-creative-mode-select');
    if (!select || select.dataset.bound === 'true') return;
    select.dataset.bound = 'true';
    select.addEventListener('change', () => {
        saveCopilotCreativeModePreference(select.value);
    });
}

// 新建会话 - 清空聊天记录
async function clearCopilotChat() {
    if (!ui.copilotMsgs) return;

    const newSessionId = await createCopilotSession();
    setCurrentCopilotSessionId(newSessionId);
    hideCopilotSessionMenu();

    // 清空消息容器
    ui.copilotMsgs.innerHTML = '';
    
    // 添加欢迎消息
    renderCopilotWelcomeMessage();
    
    // 清空输入框
    const input = document.getElementById('copilot-input-text');
    if (input) {
        input.value = '';
        input.dataset.mentions = '[]';
    }
    if (typeof window.hideCopilotAutocomplete === 'function') {
        window.hideCopilotAutocomplete();
    }

    const currentLabel = ui.copilotSessionMode
        ? String(ui.copilotSessionMode.textContent || '').replace(/^模型：/, '').trim()
        : '';
    setCopilotSessionHeader(currentLabel || '未识别模型', '');
    updateCopilotWorkflowPanel(null);
    clearInlineStatus();

    showToast('已创建新会话，历史会话可在列表中切换');
}

function toggleCopilot() {
    setCopilotVisible(!store.copilotVisible);
}

function toggleFocusMode() {
    store.focusMode = !store.focusMode;

    const workbench = document.querySelector('.workbench');

    if (store.focusMode) {
        // 进入专注模式
        workbench.classList.add('focus-mode');
        if (ui.toggleFocusBtn) {
            ui.toggleFocusBtn.innerHTML = '<i class="ri-fullscreen-exit-line"></i>';
            ui.toggleFocusBtn.title = '退出专注模式';
        }
    } else {
        // 退出专注模式
        workbench.classList.remove('focus-mode');
        if (ui.toggleFocusBtn) {
            ui.toggleFocusBtn.innerHTML = '<i class="ri-fullscreen-line"></i>';
            ui.toggleFocusBtn.title = '专注模式';
        }
    }
}

// ===== Markdown 渲染 =====

function renderMarkdown(text) {
    if (!text) return '';
    const structuredPayloadHtml = renderStructuredPayloadBlock(text);
    if (structuredPayloadHtml) {
        return structuredPayloadHtml;
    }
    try {
        if (typeof marked !== 'undefined') {
            // Escape HTML entities before passing to marked to prevent XSS
            return marked.parse(escapeHtml(text), { breaks: true, gfm: true });
        }
    } catch (e) {
        console.warn('[renderMarkdown] marked parse error:', e);
    }
    // fallback: 用 escapeHtml 纯文本显示
    return '<p>' + escapeHtml(text) + '</p>';
}

function renderStructuredPayloadBlock(text) {
    const rawText = String(text || '').trim();
    if (!rawText || rawText.startsWith('<div class="copilot-')) return '';
    if (!/^[\[{]/.test(rawText)) return '';

    let displayText = rawText;
    let language = '';
    try {
        displayText = JSON.stringify(JSON.parse(rawText), null, 2);
        language = 'json';
    } catch (_) {
        if (!/^[\[{][\s\S]*(?:"[^"]+"\s*:|\][\s,]*$|\}[\s,]*$)/.test(rawText)) {
            return '';
        }
    }

    const langClass = language ? ` class="language-${language}"` : '';
    return `<pre><code${langClass}>${escapeHtml(displayText)}</code></pre>`;
}

function formatContractScopeLine(label, value) {
    const safeLabel = window.escapeHtml ? window.escapeHtml(String(label || '').trim()) : String(label || '').trim();
    const rawValue = value === null || value === undefined || value === '' ? '未指定' : String(value);
    const safeValue = window.escapeHtml ? window.escapeHtml(rawValue) : rawValue;
    return `<div class="copilot-contract-line"><span>${safeLabel}</span><strong>${safeValue}</strong></div>`;
}

function formatPlanDeliverableLabel(value) {
    const raw = String(value || '').trim();
    if (!raw) return '计划产物';
    const normalizedPath = raw.replace(/\\/g, '/').toLowerCase();
    const normalized = normalizedPath.split('/').pop();
    const labels = {
        'worldbuilding.json': '世界观设定',
        'characters.json': '角色档案',
        'outline.json': '故事大纲',
        'items.json': '道具物品',
        'eventlines.json': '事件线',
        'detail_settings.json': '细纲设定',
        'chapter_settings.json': '章纲设定',
        'chapters/*.md': '正文章节',
        'stage_summaries/*.md': '阶段总结'
    };
    if (labels[normalized]) return labels[normalized];
    if (normalizedPath.startsWith('chapters/') || normalizedPath.includes('/chapters/')) return '正文章节';
    if (normalizedPath.startsWith('stage_summaries/') || normalizedPath.includes('/stage_summaries/')) return '阶段总结';
    return translateTechnicalText(raw);
}

function normalizeTaskPoolSummary(taskPool) {
    if (!taskPool || typeof taskPool !== 'object') return null;
    const tasks = Array.isArray(taskPool.tasks) ? taskPool.tasks.filter(item => item && typeof item === 'object') : [];
    const statusCount = {};
    tasks.forEach((task) => {
        const status = String(task.status || 'pending').trim() || 'pending';
        statusCount[status] = (statusCount[status] || 0) + 1;
    });
    return {
        taskCount: tasks.length,
        statusCount,
        metadata: taskPool.metadata && typeof taskPool.metadata === 'object' ? taskPool.metadata : {},
        preview: tasks.slice(0, 6).map((task) => ({
            title: String(task.title || task.task_type || '未命名任务').trim(),
            status: String(task.status || 'pending').trim() || 'pending',
            candidateAgents: Array.isArray(task.candidate_agents) ? task.candidate_agents : []
        }))
    };
}

function renderTaskPoolSummaryCard(taskPool) {
    const summary = normalizeTaskPoolSummary(taskPool);
    if (!summary) return '';
    const statusEntries = Object.entries(summary.statusCount);
    const statusHtml = statusEntries.length
        ? statusEntries.map(([status, count]) => {
            const safeStatus = window.escapeHtml ? window.escapeHtml(translateTechnicalText(status)) : translateTechnicalText(status);
            return `<span class="copilot-taskpool-badge" data-status="${window.escapeHtml ? window.escapeHtml(status) : status}">${safeStatus} · ${count}</span>`;
        }).join('')
        : '<span class="copilot-taskpool-empty">暂无任务</span>';
    const previewHtml = summary.preview.length
        ? summary.preview.map((task) => {
            const safeTitle = window.escapeHtml ? window.escapeHtml(task.title) : task.title;
            const safeStatus = window.escapeHtml ? window.escapeHtml(translateTechnicalText(task.status)) : translateTechnicalText(task.status);
            const candidateText = task.candidateAgents.length
                ? `候选助手：${task.candidateAgents.map((agent) => getAgentDisplayName(agent)).join('、')}`
                : '候选智能体：待分配';
            const safeCandidateText = window.escapeHtml ? window.escapeHtml(candidateText) : candidateText;
            return `
                <div class="copilot-taskpool-item">
                    <div class="copilot-taskpool-item-title">${safeTitle}</div>
                    <div class="copilot-taskpool-item-meta">${safeStatus}</div>
                    <div class="copilot-taskpool-item-meta">${safeCandidateText}</div>
                </div>
            `;
        }).join('')
        : '<div class="copilot-taskpool-empty">暂无任务预览</div>';

    return `
        <div class="copilot-taskpool-card">
            <div class="copilot-taskpool-header">
                <strong>任务池摘要</strong>
                <span>${summary.taskCount} 个任务</span>
            </div>
            <div class="copilot-taskpool-statuses">${statusHtml}</div>
            <div class="copilot-taskpool-list">${previewHtml}</div>
        </div>
    `;
}

function renderCreationContractCard(contractPayload) {
    if (!contractPayload || typeof contractPayload !== 'object') return '';
    const scope = contractPayload.scope && typeof contractPayload.scope === 'object' ? contractPayload.scope : {};
    const constraints = contractPayload.constraints && typeof contractPayload.constraints === 'object' ? contractPayload.constraints : {};
    const deliverables = Array.isArray(contractPayload.deliverables) ? contractPayload.deliverables : [];
    const taskGraphDraft = Array.isArray(contractPayload.task_graph) ? contractPayload.task_graph : [];
    const aiAutonomyRequested = Boolean(scope.ai_autonomy_requested);
    const styleText = Array.isArray(constraints.style) && constraints.style.length ? constraints.style.join('、') : '未指定';
    const qualityText = Array.isArray(constraints.quality_rules) && constraints.quality_rules.length ? constraints.quality_rules.join('、') : '未指定';
    const deliverablesHtml = deliverables.length
        ? `<ul>${deliverables.slice(0, 8).map(item => `<li>${window.escapeHtml ? window.escapeHtml(formatPlanDeliverableLabel(item)) : formatPlanDeliverableLabel(item)}</li>`).join('')}</ul>`
        : '<div class="copilot-contract-empty">暂无计划产物</div>';
    const taskHtml = taskGraphDraft.length
        ? `<ul>${taskGraphDraft.slice(0, 6).map(item => {
            const title = item && typeof item === 'object' ? String(item.title || item.task_type || '未命名任务').trim() : '未命名任务';
            const safeTitle = window.escapeHtml ? window.escapeHtml(title) : title;
            return `<li>${safeTitle}</li>`;
        }).join('')}</ul>`
        : '<div class="copilot-contract-empty">暂无任务草案</div>';
    const contractJson = window.escapeHtml
        ? window.escapeHtml(JSON.stringify(contractPayload))
        : JSON.stringify(contractPayload);

    return `
        <div class="copilot-contract-card" data-contract-id="${window.escapeHtml ? window.escapeHtml(String(contractPayload.contract_id || '')) : String(contractPayload.contract_id || '')}">
            <div class="copilot-contract-header">
                <strong>创作合同草案</strong>
                <span>${contractPayload.user_confirmed ? '已确认' : '待确认'}</span>
            </div>
            <div class="copilot-contract-grid">
                ${formatContractScopeLine('类型', scope.novel_type)}
                ${formatContractScopeLine('主题', scope.theme)}
                ${formatContractScopeLine('主角', scope.protagonist || (aiAutonomyRequested ? '由助手自主设定' : ''))}
                ${formatContractScopeLine('剧情', scope.plot_idea || (aiAutonomyRequested ? '由助手自主构思' : ''))}
                ${formatContractScopeLine('篇幅', scope.target_word_count ? `约${Number(scope.target_word_count).toLocaleString()}字` : '')}
                ${formatContractScopeLine('卷数', scope.volume_count)}
                ${formatContractScopeLine('每卷章节', scope.chapters_per_volume)}
                ${formatContractScopeLine('总章节', scope.total_chapters)}
                ${formatContractScopeLine('风格约束', styleText)}
                ${formatContractScopeLine('质量规则', qualityText)}
            </div>
            <div class="copilot-contract-section">
                <div class="copilot-contract-section-title">计划产物</div>
                ${deliverablesHtml}
            </div>
            <div class="copilot-contract-section">
                <div class="copilot-contract-section-title">任务预览</div>
                ${taskHtml}
            </div>
            <div class="copilot-contract-actions">
                <button type="button" class="copilot-contract-confirm-btn" data-contract-confirm="${contractJson}">确认当前任务并开始</button>
            </div>
        </div>
    `;
}

function decodeHtmlAttributeValue(value) {
    const raw = String(value || '');
    if (!raw || !/[&][a-z#0-9]+;/i.test(raw)) return raw;
    const textarea = document.createElement('textarea');
    textarea.innerHTML = raw;
    return textarea.value;
}

function getFallbackCreationContractForButton(button) {
    const fallback = store.pendingCreationContract;
    if (!fallback || typeof fallback !== 'object') return null;
    const card = button && button.closest ? button.closest('.copilot-contract-card') : null;
    const cardContractId = String(card?.dataset?.contractId || '').trim();
    const fallbackContractId = String(fallback.contract_id || '').trim();
    if (cardContractId && fallbackContractId && cardContractId !== fallbackContractId) {
        return null;
    }
    return fallback;
}

function parseCreationContractFromButton(button) {
    const raw = String(button?.dataset?.contractConfirm || '').trim();
    const candidates = [raw, decodeHtmlAttributeValue(raw)]
        .map((item) => String(item || '').trim())
        .filter(Boolean);
    for (const candidate of candidates) {
        try {
            const payload = JSON.parse(candidate);
            if (payload && typeof payload === 'object') {
                return payload;
            }
        } catch (_) {
            // Try the next representation, then fall back to the runtime copy.
        }
    }
    return getFallbackCreationContractForButton(button);
}

async function confirmCreationContract(contractPayload) {
    if (!contractPayload || typeof contractPayload !== 'object') {
        throw new Error('缺少合同草案数据');
    }
    const response = await apiCall('/api/v1/contract/confirm', 'POST', {
        contract_id: String(contractPayload.contract_id || '').trim(),
        approved: true,
        session_id: getCurrentCopilotSessionId(),
        contract_payload: contractPayload
    });
    const nextContract = response && response.creation_contract ? response.creation_contract : contractPayload;
    const nextTaskPool = response && response.task_pool ? response.task_pool : null;
    store.pendingCreationContract = nextContract;
    store.currentTaskPool = nextTaskPool;
    return {
        contract: nextContract,
        taskPool: nextTaskPool,
        collabExecutionTrace: response && response.collab_execution_trace ? response.collab_execution_trace : null,
        response
    };
}

function bindContractCardActions(container) {
    const root = container && container.querySelectorAll ? container : document;
    root.querySelectorAll('.copilot-contract-confirm-btn').forEach((button) => {
        if (button.dataset.bound === '1') return;
        button.dataset.bound = '1';
        button.addEventListener('click', async () => {
            const payload = parseCreationContractFromButton(button);
            if (!payload) {
                showToast('合同草案解析失败', 'error');
                return;
            }
            button.disabled = true;
            try {
                const result = await confirmCreationContract(payload);
                const confirmedText = '合同已确认，正式任务池已初始化。';
                appendMessage(confirmedText, 'ai');
                if (result.taskPool) {
                    appendMessage(renderTaskPoolSummaryCard(result.taskPool), 'ai');
                }
                showToast('合同确认成功', 'success');
            } catch (e) {
                button.disabled = false;
                showToast(`合同确认失败: ${e.message}`, 'error');
            }
        });
    });
}

// 初始化 marked 配置
(function initMarked() {
    if (typeof marked === 'undefined') return;
    marked.setOptions({
        breaks: true,
        gfm: true,
        headerIds: false,
        mangle: false
    });
})();

// ===== 流式消息 =====

async function sendCopilotMessage() {
    if (!ui.copilotInput) return;
    const text = ui.copilotInput.value.trim();
    if (!text) return;

    if (typeof window.hideCopilotAutocomplete === 'function') {
        window.hideCopilotAutocomplete();
    }
    ui.copilotInput.value = '';

    appendMessage(text, 'user');
    const sid = getCurrentCopilotSessionId();
    const creativeMode = getCurrentCopilotCreativeMode();

    // 显示思考中状态
    showInlineStatus('Router', '正在思考...', 'running');

    // 创建空的AI消息容器
    const aiDiv = createStreamMessage();
    const contentEl = aiDiv.querySelector('.msg-content');
    const streamTextFilter = createCopilotStreamTextFilter();
    let fullText = '';
    let pendingChunks = '';
    let flushTimer = null;
    const FLUSH_INTERVAL = 50; // 50ms 批量刷新一次

    function flushPendingChunks() {
        if (!pendingChunks || !contentEl) return;
        const textNode = document.createTextNode(pendingChunks);
        contentEl.appendChild(textNode);
        pendingChunks = '';
        scrollCopilotToBottom();
    }

    function scheduleFlush() {
        if (flushTimer) return;
        flushTimer = setTimeout(() => {
            flushTimer = null;
            flushPendingChunks();
        }, FLUSH_INTERVAL);
    }

    currentStreamAbort = new AbortController();
    setStreamingButtonState(true);

    try {
        const response = await fetch('/api/chat/stream', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ message: text, session_id: sid, creative_mode: creativeMode }),
            signal: currentStreamAbort.signal
        });

        if (!response.ok) {
            // 流式端点不可用，回退到普通模式
            aiDiv.remove();
            const res = await apiCall('/api/chat', 'POST', {
                message: text,
                session_id: sid,
                creative_mode: creativeMode
            });
            updateCopilotSessionModelLabel(extractModelLabelFromPayload(res));
            updateCopilotSessionHeaderFromRouting(res && res.routing);
            updateCopilotWorkflowPanel(res && res.workflow, res && res.routing);
            clearInlineStatus();
            if (res && res.workflow) {
                showInlineStatusFromWorkflow(res.workflow);
            }

            if (res && res.workflow) {
                if (typeof handleWorkflowAutoSave === 'function') {
                    try {
                        await handleWorkflowAutoSave(res.workflow);
                    } catch (autoSaveError) {
                        console.error('[Copilot] 自动保存失败', autoSaveError);
                    }
                } else {
                    maybeFocusWorkflowTarget(res.workflow);
                }
            }
            await handleAssistantAutoSaveResult(res && res.assistant_auto_save);

            appendMessage((res.reply || '收到'), 'ai');

            const delegatedParams = res && res.delegated_result && res.delegated_result.params && typeof res.delegated_result.params === 'object'
                ? res.delegated_result.params
                : {};
            if (delegatedParams.creation_contract) {
                store.pendingCreationContract = delegatedParams.creation_contract;
                appendMessage(renderCreationContractCard(delegatedParams.creation_contract), 'ai');
            }
            if (res && res.task_pool) {
                store.currentTaskPool = res.task_pool;
                appendMessage(renderTaskPoolSummaryCard(res.task_pool), 'ai');
            }
            currentStreamAbort = null;
            setStreamingButtonState(false);
            return;
        }

        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';

        while (true) {
            const { done, value } = await reader.read();
            if (done) break;

            buffer += decoder.decode(value, { stream: true });
            const lines = buffer.split('\n');
            buffer = lines.pop() || '';

            for (const line of lines) {
                if (!line.startsWith('data: ')) continue;
                const dataStr = line.slice(6).trim();
                if (!dataStr) continue;

                try {
                    const evt = JSON.parse(dataStr);

                    if (evt.type === 'chunk') {
                        const visibleContent = streamTextFilter.push(evt.content || '');
                        if (!visibleContent) {
                            continue;
                        }
                        if (!fullText) {
                            clearInlineStatus(); // 第一个文字块到达时清除思考状态
                            contentEl.innerHTML = ''; // 初始化空容器
                        }
                        fullText += visibleContent;
                        // 累积到缓冲区，批量渲染而非逐字渲染
                        pendingChunks += visibleContent;
                        scheduleFlush();
                    } else if (evt.type === 'workflow') {
                        updateCopilotSessionModelLabel(extractModelLabelFromPayload(evt));
                        showInlineStatusFromWorkflow(evt.workflow);
                        updateCopilotWorkflowPanel(evt.workflow);
                        appendStreamWorkflowProgress(aiDiv, evt.workflow);
                    } else if (evt.type === 'done') {
                        updateCopilotSessionModelLabel(extractModelLabelFromPayload(evt));
                        // 清除内联状态指示器
                        clearInlineStatus();
                        // 刷新剩余缓冲内容
                        if (flushTimer) { clearTimeout(flushTimer); flushTimer = null; }
                        flushPendingChunks();
                        // 最终完整回复
                        if (evt.reply) {
                            fullText = evt.reply;
                            contentEl.innerHTML = renderMarkdown(fullText);
                        }
                        if (evt.routing) {
                            updateCopilotSessionHeaderFromRouting(evt.routing);
                        }
                        if (evt.workflow) {
                            showInlineStatusFromWorkflow(evt.workflow);
                            updateCopilotWorkflowPanel(evt.workflow);
                            
                            if (typeof handleWorkflowAutoSave === 'function') {
                                try {
                                    await handleWorkflowAutoSave(evt.workflow);
                                } catch (autoSaveError) {
                                    console.error('[Copilot] 自动保存失败', autoSaveError);
                                }
                            } else {
                                maybeFocusWorkflowTarget(evt.workflow);
                            }
                        }
                        await handleAssistantAutoSaveResult(evt && evt.assistant_auto_save);

                        const delegatedParams = evt && evt.delegated_result && evt.delegated_result.params && typeof evt.delegated_result.params === 'object'
                            ? evt.delegated_result.params
                            : {};
                        if (delegatedParams.creation_contract) {
                            store.pendingCreationContract = delegatedParams.creation_contract;
                            appendMessage(renderCreationContractCard(delegatedParams.creation_contract), 'ai');
                        }
                        if (evt && evt.task_pool) {
                            store.currentTaskPool = evt.task_pool;
                            appendMessage(renderTaskPoolSummaryCard(evt.task_pool), 'ai');
                        }
                        // 移除打字光标
                        aiDiv.classList.remove('streaming');
                    } else if (evt.type === 'error') {
                        updateCopilotSessionModelLabel(extractModelLabelFromPayload(evt));
                        clearInlineStatus();
                        fullText = evt.message || '处理请求时出错';
                        contentEl.innerHTML = renderMarkdown(fullText);
                        if (evt.workflow) {
                            updateCopilotWorkflowPanel(evt.workflow);
                        }
                        aiDiv.classList.remove('streaming');
                    }
                } catch (parseErr) {
                    // 忽略解析错误
                }
            }
        }

        // 流结束，刷新剩余缓冲并确保移除打字光标
        if (flushTimer) { clearTimeout(flushTimer); flushTimer = null; }
        const trailingVisibleContent = streamTextFilter.flush();
        if (trailingVisibleContent) {
            if (!fullText) {
                clearInlineStatus();
                contentEl.innerHTML = '';
            }
            fullText += trailingVisibleContent;
            pendingChunks += trailingVisibleContent;
        }
        flushPendingChunks();
        aiDiv.classList.remove('streaming');
        if (!fullText) {
            contentEl.innerHTML = renderMarkdown('收到');
        }

    } catch (e) {
        clearInlineStatus();
        if (flushTimer) { clearTimeout(flushTimer); flushTimer = null; }
        const trailingVisibleContent = streamTextFilter.flush();
        if (trailingVisibleContent) {
            fullText += trailingVisibleContent;
            pendingChunks += trailingVisibleContent;
        }
        flushPendingChunks();
        aiDiv.classList.remove('streaming');
        const contentEl = aiDiv.querySelector('.msg-content');
        if (e.name === 'AbortError') {
            if (contentEl && !contentEl.textContent.trim()) {
                contentEl.innerHTML = renderMarkdown('已停止生成');
            }
        } else {
            console.error('[sendCopilotMessage] stream error:', e);
            if (contentEl) {
                contentEl.innerHTML = renderMarkdown('连接失败，请检查API配置');
            }
            setCopilotSessionHeader('多Agent创作模式', '连接失败');
        }
    } finally {
        currentStreamAbort = null;
        setStreamingButtonState(false);
    }
}

function createStreamMessage() {
    if (!ui.copilotMsgs) return null;
    const div = document.createElement('div');
    div.className = 'msg ai streaming';
    const content = document.createElement('div');
    content.className = 'msg-content';
    div.appendChild(content);
    ui.copilotMsgs.appendChild(div);
    scrollCopilotToBottom();
    return div;
}

function appendStreamWorkflowProgress(aiDiv, workflow) {
    if (!aiDiv || !workflow || typeof workflow !== 'object') return;
    if (isInternalStreamEventType(workflow.type)) return;
    const progressText = formatWorkflowProgressText(workflow.last_progress || '');
    if (!progressText || looksLikeProtocolFragment(progressText)) return;

    let traceEl = aiDiv.querySelector('.copilot-progress-trace');
    if (!traceEl) {
        traceEl = document.createElement('div');
        traceEl.className = 'copilot-progress-trace';
        const contentEl = aiDiv.querySelector('.msg-content');
        aiDiv.insertBefore(traceEl, contentEl || null);
    }

    if (traceEl.dataset.lastProgress === progressText) return;
    traceEl.dataset.lastProgress = progressText;

    const lineEl = document.createElement('div');
    lineEl.className = 'copilot-progress-trace-line';
    lineEl.textContent = progressText;
    traceEl.appendChild(lineEl);

    while (traceEl.children.length > 6) {
        traceEl.removeChild(traceEl.firstElementChild);
    }
    scrollCopilotToBottom();
}

function appendMessage(text, role, shouldScroll = true) {
    if (!ui.copilotMsgs) return null;
    const div = document.createElement('div');
    div.className = `msg ${role}`;

    if (role === 'ai') {
        const content = document.createElement('div');
        content.className = 'msg-content';
        if (typeof text === 'string' && /copilot-(contract|taskpool|route-status)/.test(text)) {
            const rawText = String(text);
            const routeStatusMatch = rawText.match(/<div class="copilot-route-status">[\s\S]*$/);
            const standaloneCardPattern = /^<div class="copilot-(?:contract-card|taskpool-card|route-status)[\s\S]*$/;
            if (standaloneCardPattern.test(rawText.trim())) {
                content.innerHTML = rawText;
            } else {
                const routeStatusHtml = routeStatusMatch ? routeStatusMatch[0] : '';
                const markdownPart = routeStatusHtml ? rawText.slice(0, rawText.indexOf(routeStatusHtml)) : rawText;
                content.innerHTML = (markdownPart ? renderMarkdown(markdownPart) : '') + routeStatusHtml;
            }
        } else {
            content.innerHTML = renderMarkdown(text);
        }
        div.appendChild(content);
        bindContractCardActions(content);
    } else {
        div.textContent = text;
    }

    ui.copilotMsgs.appendChild(div);
    if (shouldScroll) {
        scrollCopilotToBottom();
    }
    return div;
}

function scrollCopilotToBottom() {
    if (ui.copilotMsgs) {
        ui.copilotMsgs.scrollTop = ui.copilotMsgs.scrollHeight;
    }
}

// ===== 内联Agent状态指示器系统 =====

// Agent能力活动描述映射
const AGENT_ACTIVITY_MAP = {
    'Worldbuilder': { icon: '🌍', activity: '正在构建世界观', done: '世界观构建完成' },
    'Outliner': { icon: '📋', activity: '正在创建大纲', done: '大纲创建完成' },
    'EventlineBuilder': { icon: '🧭', activity: '正在整理事件线', done: '事件线构建完成' },
    'DetailOutlineBuilder': { icon: '🗂️', activity: '正在生成细纲', done: '细纲构建完成' },
    'ChapterSettingBuilder': { icon: '📑', activity: '正在生成章纲', done: '章纲构建完成' },
    'ChapterWriter': { icon: '✍️', activity: '正在创作正文', done: '章节创作完成' },
    'ContinuousWriter': { icon: '🔄', activity: '正在续写内容', done: '续写完成' },
    'Polisher': { icon: '✨', activity: '正在润色内容', done: '润色完成' },
    'SummaryOrchestrator': { icon: '🧾', activity: '正在执行内部摘要编排', done: '内部摘要编排完成' },
    'Coordinator': { icon: '🎯', activity: '正在协调创作任务', done: '创作协调完成' },
    'Communicator': { icon: '💬', activity: '正在思考', done: '回复完成' },
    'Router': { icon: '🔀', activity: '正在分析意图', done: '路由完成' },
    'WebSearch': { icon: '🔍', activity: '正在搜索网络信息', done: '搜索完成' },
    'TrendsSearch': { icon: '🔥', activity: '正在搜索热点信息', done: '热点搜索完成' },
    'ContextStrategy': { icon: '🧠', activity: '正在执行内部上下文规划', done: '内部上下文规划完成' },
    'ContentReader': { icon: '📖', activity: '正在执行内部内容读取', done: '内部内容读取完成' },
    'ContentExpansion': { icon: '📝', activity: '正在执行内部内容扩展', done: '内部内容扩展完成' },
    'FileNaming': { icon: '📁', activity: '正在执行内部文件命名', done: '内部文件命名完成' },
    'Evaluator': { icon: '🔍', activity: '正在评估质量', done: '质量评估完成' },
    'CharacterBuilder': { icon: '👤', activity: '正在创建角色信息', done: '角色创建完成' },
    'ProjectManager': { icon: '📊', activity: '正在管理项目', done: '项目管理完成' }
};

// 阶段描述映射
const STAGE_ACTIVITY_MAP = {
    'worldbuilding': '正在构建世界观...',
    'outlining': '正在创建大纲...',
    'writing': '正在创作正文...',
    'starting': '正在准备创作...',
    'packaging': '正在整理输出文件...',
    'completed': '创作流程已完成',
    'failed': '执行遇到问题',
    'paused': '创作已暂停',
    'cancelled': '创作已取消'
};

let _currentInlineStatusEl = null;
let _inlineStatusFadeTimer = null;

function getAgentActivity(agentName, stage, status) {
    const agent = AGENT_ACTIVITY_MAP[agentName];
    if (!agent) {
        return { icon: '⚙️', text: `正在处理（${getAgentDisplayName(agentName) || '未知'}）` };
    }
    if (status === 'completed' || status === 'done') {
        return { icon: '✅', text: agent.done };
    }
    if (status === 'failed') {
        return { icon: '❌', text: agent.done.replace('完成', '失败') };
    }
    // 根据阶段给出更具体的描述
    if (stage && STAGE_ACTIVITY_MAP[stage]) {
        return { icon: agent.icon, text: STAGE_ACTIVITY_MAP[stage] };
    }
    return { icon: agent.icon, text: agent.activity };
}

function showInlineStatus(agentName, detail, status, stage) {
    if (!ui.copilotMsgs) return;

    const normalizedStatus = String(status || 'running').trim().toLowerCase();
    const normalizedAgent = String(agentName || '').trim();
    const normalizedStage = String(stage || '').trim();
    const normalizedDetail = formatWorkflowProgressText(detail || '');

    // 不对Communicator常规对话显示状态（太频繁）
    if (normalizedAgent === 'Communicator' && normalizedStatus === 'running' && !normalizedDetail) return;

    const activity = getAgentActivity(normalizedAgent, normalizedStage, normalizedStatus);
    const isCompleted = normalizedStatus === 'completed' || normalizedStatus === 'done';
    const isFailed = normalizedStatus === 'failed';

    // 清除旧的淡出计时器
    if (_inlineStatusFadeTimer) {
        clearTimeout(_inlineStatusFadeTimer);
        _inlineStatusFadeTimer = null;
    }

    // 如果已有状态指示器，更新它（而非创建新的）
    if (_currentInlineStatusEl && _currentInlineStatusEl.parentNode) {
        _currentInlineStatusEl.className = `copilot-inline-status${isCompleted ? ' is-completed' : ''}${isFailed ? ' is-failed' : ''}`;
        const iconEl = _currentInlineStatusEl.querySelector('.copilot-inline-status-icon');
        const textEl = _currentInlineStatusEl.querySelector('.copilot-inline-status-text');
        const detailEl = _currentInlineStatusEl.querySelector('.copilot-inline-status-detail');
        const dotEl = _currentInlineStatusEl.querySelector('.copilot-inline-status-dot');
        if (iconEl) iconEl.textContent = activity.icon;
        if (textEl) textEl.textContent = normalizedDetail || activity.text;
        if (detailEl) detailEl.textContent = normalizedAgent && !isCompleted && !isFailed ? getAgentDisplayName(normalizedAgent) : '';
        if (dotEl) dotEl.className = `copilot-inline-status-dot`;
    } else {
        // 创建新的状态指示器
        const el = document.createElement('div');
        el.className = `copilot-inline-status${isCompleted ? ' is-completed' : ''}${isFailed ? ' is-failed' : ''}`;
        el.innerHTML = `
            <span class="copilot-inline-status-dot"></span>
            <span class="copilot-inline-status-icon">${activity.icon}</span>
            <span class="copilot-inline-status-text">${window.escapeHtml ? window.escapeHtml(normalizedDetail || activity.text) : (normalizedDetail || activity.text)}</span>
            <span class="copilot-inline-status-detail">${normalizedAgent && !isCompleted && !isFailed ? getAgentDisplayName(normalizedAgent) : ''}</span>
        `;
        ui.copilotMsgs.appendChild(el);
        _currentInlineStatusEl = el;
    }

    scrollCopilotToBottom();

    // 完成/失败状态自动淡出
    if (isCompleted || isFailed) {
        _inlineStatusFadeTimer = setTimeout(() => {
            if (_currentInlineStatusEl && _currentInlineStatusEl.parentNode) {
                _currentInlineStatusEl.classList.add('is-fading');
                setTimeout(() => {
                    if (_currentInlineStatusEl && _currentInlineStatusEl.parentNode) {
                        _currentInlineStatusEl.remove();
                    }
                    _currentInlineStatusEl = null;
                }, 400);
            }
        }, isCompleted ? 2000 : 4000);
    }
}

function clearInlineStatus() {
    if (_inlineStatusFadeTimer) {
        clearTimeout(_inlineStatusFadeTimer);
        _inlineStatusFadeTimer = null;
    }
    if (_currentInlineStatusEl && _currentInlineStatusEl.parentNode) {
        _currentInlineStatusEl.remove();
    }
    _currentInlineStatusEl = null;
}

function showInlineStatusFromWorkflow(workflow) {
    if (!workflow || typeof workflow !== 'object') return;
    if (isInternalStreamEventType(workflow.type)) return;
    const agent = String(workflow.current_agent || workflow.target_agent || '').trim();
    const status = String(workflow.status || '').trim().toLowerCase();
    const stage = String(workflow.stage || '').trim();
    const progress = formatWorkflowProgressText(workflow.last_progress || '');

    if (progress && looksLikeProtocolFragment(progress)) return;
    if (!agent && !status && !progress) return;
    // 最终完成时清除（让done事件的消息来代替）
    if (status === 'completed' && stage === 'completed') {
        showInlineStatus(agent, progress || '任务已完成', 'completed', stage);
        return;
    }
    if (status === 'failed') {
        showInlineStatus(agent, progress || '执行失败', 'failed', stage);
        return;
    }
    showInlineStatus(agent, progress, status, stage);
}

function showInlineStatusFromSubAgent(subAgentEvent) {
    if (!subAgentEvent || typeof subAgentEvent !== 'object') return;
    const agentName = String(subAgentEvent.agent || '').trim();
    const eventType = String(subAgentEvent.type || '').trim();
    const title = String(subAgentEvent.title || subAgentEvent.task_type || '').trim();

    if (eventType === 'sub_agent_started' || eventType === 'sub_agent_dispatching') {
        const activity = AGENT_ACTIVITY_MAP[agentName];
        const detailText = title ? `${activity ? activity.activity : '正在处理'}：${title}` : '';
        showInlineStatus(agentName, detailText, 'running');
    } else if (eventType === 'sub_agent_fallback') {
        showInlineStatus(agentName, `正在切换备用方案${title ? '：' + title : ''}...`, 'running');
    } else if (eventType === 'sub_agent_completed') {
        showInlineStatus(agentName, title ? `已完成：${title}` : '', 'completed');
    } else if (eventType === 'sub_agent_failed') {
        showInlineStatus(agentName, title ? `失败：${title}` : '', 'failed');
    }
}

// 全局暴露核心函数和状态
window.NovelAgentApp = window.NovelAgentApp || {};
window.NovelAgentApp.core = {
    store,
    ui,
    init,
    initUIReferences,
    checkGlobalAPIConfig,
    bindEvents,
    switchModule,
    toggleSidebar,
    restoreSidebarState,
    clearCopilotChat,
    toggleCopilot,
    toggleFocusMode,
    sendCopilotMessage,
    appendMessage,
    renderMarkdown,
    createCopilotStreamTextFilter,
    formatPlanDeliverableLabel,
    renderCreationContractCard,
    renderTaskPoolSummaryCard,
    confirmCreationContract,
    parseCreationContractFromButton,
    bindContractCardActions,
    createStreamMessage,
    appendStreamWorkflowProgress,
    scrollCopilotToBottom,
    updateCopilotWorkflowPanel,
    restoreCopilotWorkflowStatus,
    refreshNovelCollabRuntime,
    startNovelCollabRuntimePolling,
    stopNovelCollabRuntimePolling,
    showInlineStatus,
    clearInlineStatus,
    showInlineStatusFromWorkflow,
    showInlineStatusFromSubAgent,
    handleAssistantAutoSaveResult,
    getCurrentCopilotCreativeMode,
    renderCopilotCreativeModeSelector,
    loadCopilotCreativeModePreference,
    saveCopilotCreativeModePreference,
    loadCopilotModelOptions,
    renderCopilotModelSelector,
    applyCopilotModelSelection
};

// 兼容旧版全局访问，后续模块优先使用 window.NovelAgentApp.core
window.store = store;
window.ui = ui;
window.init = init;
window.initUIReferences = initUIReferences;
window.checkGlobalAPIConfig = checkGlobalAPIConfig;
window.bindEvents = bindEvents;
window.switchModule = switchModule;
window.toggleSidebar = toggleSidebar;
window.restoreSidebarState = restoreSidebarState;
window.clearCopilotChat = clearCopilotChat;
window.toggleCopilot = toggleCopilot;
window.toggleFocusMode = toggleFocusMode;
window.sendCopilotMessage = sendCopilotMessage;
window.appendMessage = appendMessage;
window.renderMarkdown = renderMarkdown;
window.createCopilotStreamTextFilter = createCopilotStreamTextFilter;
window.formatPlanDeliverableLabel = formatPlanDeliverableLabel;
window.renderCreationContractCard = renderCreationContractCard;
window.renderTaskPoolSummaryCard = renderTaskPoolSummaryCard;
window.startNovelCollabRuntimePolling = startNovelCollabRuntimePolling;
window.stopNovelCollabRuntimePolling = stopNovelCollabRuntimePolling;
window.confirmCreationContract = confirmCreationContract;
window.parseCreationContractFromButton = parseCreationContractFromButton;
window.bindContractCardActions = bindContractCardActions;
window.createStreamMessage = createStreamMessage;
window.appendStreamWorkflowProgress = appendStreamWorkflowProgress;
window.scrollCopilotToBottom = scrollCopilotToBottom;
window.updateCopilotWorkflowPanel = updateCopilotWorkflowPanel;
window.restoreCopilotWorkflowStatus = restoreCopilotWorkflowStatus;
window.refreshNovelCollabRuntime = refreshNovelCollabRuntime;
window.showInlineStatus = showInlineStatus;
window.clearInlineStatus = clearInlineStatus;
window.showInlineStatusFromWorkflow = showInlineStatusFromWorkflow;
window.showInlineStatusFromSubAgent = showInlineStatusFromSubAgent;
window.handleAssistantAutoSaveResult = handleAssistantAutoSaveResult;
window.getCurrentCopilotCreativeMode = getCurrentCopilotCreativeMode;
window.renderCopilotCreativeModeSelector = renderCopilotCreativeModeSelector;
window.loadCopilotCreativeModePreference = loadCopilotCreativeModePreference;
window.saveCopilotCreativeModePreference = saveCopilotCreativeModePreference;
window.loadCopilotModelOptions = loadCopilotModelOptions;
window.renderCopilotModelSelector = renderCopilotModelSelector;
window.applyCopilotModelSelection = applyCopilotModelSelection;

console.log('[app-core.js] 核心模块已加载');
