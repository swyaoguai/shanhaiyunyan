/**
 * 文思Agent - 核心状态和初始化模块
 * 包含：全局状态store、UI引用、初始化、事件绑定、模块切换
 */

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
        worldbuilding: [],
        items: [],
        // 资料库扩展分类
        eventlines: [],      // 事件线
        outline_settings: [], // 大纲设定
        detail_settings: [],  // 细纲设定
        chapter_settings: [], // 章纲设定
        custom_knowledge: []  // 用户自定义资料库
    },
    // 资料库分类配置
    knowledgeCategories: [
        { id: 'db-char', key: 'characters', name: '角色档案', icon: 'ri-user-smile-line', builtin: true },
        { id: 'db-world', key: 'worldbuilding', name: '世界设定', icon: 'ri-earth-line', builtin: true },
        { id: 'db-item', key: 'items', name: '道具物品', icon: 'ri-sword-line', builtin: true },
        { id: 'db-event', key: 'eventlines', name: '事件线', icon: 'ri-timeline-view', builtin: true },
        { id: 'db-outline', key: 'outline_settings', name: '大纲设定', icon: 'ri-file-list-3-line', builtin: true },
        { id: 'db-detail', key: 'detail_settings', name: '细纲设定', icon: 'ri-file-text-line', builtin: true },
        { id: 'db-chapter', key: 'chapter_settings', name: '章纲设定', icon: 'ri-book-open-line', builtin: true }
    ],
    copilotVisible: false,
    copilotSessionId: 'copilot',
    focusMode: false,
    copilotWorkflow: null,
    lastWorkflowFocusedRunId: '',
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
    copilotSessionListBtn: null,
    copilotSessionMenu: null,
    copilotWorkflowPanel: null
};

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
    ui.copilotSessionListBtn = document.getElementById('copilot-session-list-btn');
    ui.copilotSessionMenu = document.getElementById('copilot-session-menu');
    ui.copilotWorkflowPanel = document.getElementById('copilot-workflow-panel');
    bindCopilotWorkflowPanel();
}

// 初始化
async function init() {
    initUIReferences();
    restoreCopilotSessionId();
    setCopilotSessionHeader('默认模型', '准备就绪');
    bindEvents();
    await loadSavedSettings(); // 加载保存的主题和背景设置（异步加载IndexedDB背景图片）
    restoreSidebarState(); // 恢复侧边栏状态
    loadKnowledgeCategories(); // 加载自定义资料库分类
    await loadProjects(); // 加载项目列表
    await checkGlobalAPIConfig(); // 检查全局API配置
    switchModule('dashboard');
    await restoreCopilotHistory();
    await restoreCopilotWorkflowStatus();
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

// 绑定事件
function bindEvents() {
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
        ui.copilotSendBtn.addEventListener('click', sendCopilotMessage);
    }
    if (ui.copilotInput) {
        ui.copilotInput.addEventListener('keydown', (e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                sendCopilotMessage();
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
    const previousModule = store.currentModule;
    store.currentModule = moduleId;

    // 更新资源栏激活状态
    ui.resItems.forEach(item => {
        item.classList.toggle('active', item.dataset.module === moduleId);
    });

    // 更新导航面板
    renderNavPanel(moduleId);
    
    // 控制创作助手按钮的显示（只在协作创作模式显示）
    const isWritingModule = moduleId === 'write';
    const wasWritingModule = previousModule === 'write';
    // 如果切换到非创作模块，自动关闭Copilot面板
    if (!isWritingModule && store.copilotVisible) {
        setCopilotVisible(false);
    }
    // 首次进入创作模块时默认打开文思助手
    if (isWritingModule && !wasWritingModule && !store.copilotVisible) {
        setCopilotVisible(true);
    }
    syncCopilotToggleButton();

    // 根据模块渲染工作区
    if (moduleId === 'dashboard') {
        renderDashboard();
    } else if (moduleId === 'short-story') {
        if (typeof renderShortStoryInterface === 'function') {
            renderShortStoryInterface();
        } else {
            console.error('[switchModule] renderShortStoryInterface not found');
        }
    } else if (moduleId === 'novel-to-script') {
        if (typeof renderNovelToScriptInterface === 'function') {
            renderNovelToScriptInterface();
        } else {
            console.error('[switchModule] renderNovelToScriptInterface not found');
        }
    } else if (moduleId === 'infinite-write') {
        // 无限续写模块
        if (typeof renderInfiniteWriteInterface === 'function') {
            renderInfiniteWriteInterface();
        } else {
            console.error('[switchModule] renderInfiniteWriteInterface not found');
        }
    } else if (moduleId === 'settings') {
        renderSettings(); // 渲染设置页面容器，然后自动加载主题设置
    } else if (moduleId === 'write') {
        // 写作模块默认显示空编辑器
        showEmptyEditor();
    } else if (moduleId === 'world') {
        showEmptyWorld();
    } else if (moduleId === 'about') {
        // 关于页面
        if (typeof renderAboutPage === 'function') {
            renderAboutPage();
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
            kind: String(item.kind || 'file').trim(),
            status: String(item.status || 'created').trim()
        }))
        .filter((item) => item.path);
}

function normalizeCopilotWorkflow(workflow) {
    if (!workflow || typeof workflow !== 'object') return null;
    return {
        run_id: String(workflow.run_id || '').trim(),
        status: String(workflow.status || '').trim() || 'idle',
        command: String(workflow.command || '').trim(),
        current_agent: String(workflow.current_agent || '').trim(),
        target_agent: String(workflow.target_agent || '').trim(),
        stage: String(workflow.stage || '').trim(),
        last_progress: String(workflow.last_progress || '').trim(),
        last_error: String(workflow.last_error || '').trim(),
        output_dir: String(workflow.output_dir || '').trim(),
        focus_module: String(workflow.focus_module || '').trim(),
        focus_chapter: Number(workflow.focus_chapter || 0) || 0,
        created_files: normalizeWorkflowFiles(workflow.created_files),
        updated_files: normalizeWorkflowFiles(workflow.updated_files)
    };
}

function shouldShowWorkflowPanel(workflow) {
    if (!workflow) return false;
    // 只在工作流正在执行时显示面板（running, starting状态）
    const status = String(workflow.status || '').trim().toLowerCase();
    if (status === 'running' || status === 'starting') return true;
    // 如果有错误，显示面板
    if (workflow.last_error) return true;
    // 其他情况（completed, failed, paused, cancelled等）都不显示
    return false;
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

function updateCopilotWorkflowPanel(workflow) {
    if (!ui.copilotWorkflowPanel) return;
    const normalized = normalizeCopilotWorkflow(workflow);
    store.copilotWorkflow = normalized;
    if (!normalized || !shouldShowWorkflowPanel(normalized)) {
        ui.copilotWorkflowPanel.innerHTML = '';
        ui.copilotWorkflowPanel.classList.add('hidden');
        return;
    }

    const createdFiles = normalized.created_files;
    const updatedFiles = normalized.updated_files;
    const agentName = normalized.current_agent || normalized.target_agent || '待机';
    const stageName = normalized.stage || '未开始';
    const commandName = normalized.command || '自然语言';
    const progress = normalized.last_progress;
    const error = normalized.last_error;
    const outputDir = normalized.output_dir;
    const safeAgent = window.escapeHtml ? window.escapeHtml(agentName) : agentName;
    const safeStage = window.escapeHtml ? window.escapeHtml(stageName) : stageName;
    const safeCommand = window.escapeHtml ? window.escapeHtml(commandName) : commandName;
    const safeRunId = window.escapeHtml ? window.escapeHtml(normalized.run_id || '') : (normalized.run_id || '');
    const safeProgress = window.escapeHtml ? window.escapeHtml(progress) : progress;
    const safeError = window.escapeHtml ? window.escapeHtml(error) : error;
    const safeOutputDir = window.escapeHtml ? window.escapeHtml(outputDir) : outputDir;

    ui.copilotWorkflowPanel.innerHTML = `
        <div class="copilot-workflow-header">
            <div class="copilot-workflow-title">
                <strong>真实执行状态</strong>
                <span class="copilot-workflow-run">${safeRunId ? `run_id: ${safeRunId}` : '当前会话暂无运行ID'}</span>
            </div>
            <span class="copilot-workflow-badge" data-status="${window.escapeHtml ? window.escapeHtml(normalized.status) : normalized.status}">${getWorkflowStatusLabel(normalized.status)}</span>
        </div>
        <div class="copilot-workflow-grid">
            <div class="copilot-workflow-meta">
                <span>当前Agent</span>
                <span>${safeAgent}</span>
            </div>
            <div class="copilot-workflow-meta">
                <span>当前阶段</span>
                <span>${safeStage}</span>
            </div>
            <div class="copilot-workflow-meta">
                <span>触发命令</span>
                <span>${safeCommand}</span>
            </div>
            <div class="copilot-workflow-meta">
                <span>输出目录</span>
                <span>${safeOutputDir || '未写入'}</span>
            </div>
        </div>
        ${safeProgress ? `<div class="copilot-workflow-progress">${safeProgress}</div>` : ''}
        ${safeError ? `<div class="copilot-workflow-error">${safeError}</div>` : ''}
        ${createdFiles.length ? renderWorkflowFileList('新建文件', createdFiles) : ''}
        ${updatedFiles.length ? renderWorkflowFileList('更新文件', updatedFiles) : ''}
    `;
    ui.copilotWorkflowPanel.classList.remove('hidden');
    maybeFocusWorkflowTarget(normalized);
}

async function restoreCopilotWorkflowStatus() {
    try {
        const sessionId = getCurrentCopilotSessionId();
        const res = await apiCall(`/api/chat/workflow-status?session_id=${encodeURIComponent(sessionId)}`, 'GET');
        updateCopilotWorkflowPanel(res && res.workflow);
    } catch (e) {
        updateCopilotWorkflowPanel(null);
    }
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
            const url = `/api/chat/workflow-file?session_id=${encodeURIComponent(sessionId)}&path=${encodeURIComponent(filePath)}`;
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
    
    showToast(`已跳转到${fileKind === 'worldbuilding' ? '世界设定' : fileKind === 'characters' ? '角色档案' : fileKind === 'items' ? '道具物品' : fileKind === 'outline' ? '大纲' : '章节'}`, 'success');
}

async function previewWorkflowFile(filePath) {
    const modal = document.getElementById('modal-container');
    if (!modal || !filePath) return;
    const sessionId = getCurrentCopilotSessionId();
    try {
        const res = await apiCall(`/api/chat/workflow-file-preview?session_id=${encodeURIComponent(sessionId)}&path=${encodeURIComponent(filePath)}`, 'GET');
        const filename = String(res && res.filename || filePath).trim();
        const language = String(res && res.language || 'text').trim();
        const content = String(res && res.content || '').trim();
        const truncated = Boolean(res && res.truncated);
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
                            <span>${escapeHtml(filePath)}</span>
                        </div>
                        <div class="copilot-preview-actions">
                            <button type="button" class="copilot-preview-download" data-preview-download="${escapeHtml(filePath)}" title="下载文件">
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
            const url = `/api/chat/workflow-file?session_id=${encodeURIComponent(sessionId)}&path=${encodeURIComponent(filePath)}`;
            window.open(url, '_blank');
        });
        modal.querySelector('.copilot-preview-overlay')?.addEventListener('click', (evt) => {
            if (evt.target === evt.currentTarget) {
                modal.classList.add('hidden');
                modal.innerHTML = '';
            }
        });
    } catch (e) {
        showToast(`预览失败: ${e.message}`, 'error');
    }
}

function maybeFocusWorkflowTarget(workflow) {
    if (!workflow || typeof workflow !== 'object') return;
    const runId = String(workflow.run_id || '').trim();
    const focusModule = String(workflow.focus_module || '').trim();
    const focusChapter = Number(workflow.focus_chapter || 0) || 0;
    const status = String(workflow.status || '').trim();
    if (!runId || !focusModule || focusChapter <= 0) return;
    if (!['running', 'paused', 'cancelled', 'failed'].includes(status)) return;
    if (store.lastWorkflowFocusedRunId === runId) return;
    const switchModuleFn = typeof window.switchModule === 'function' ? window.switchModule : switchModule;
    const loadProjectDataFn = typeof window.loadCurrentProjectData === 'function' ? window.loadCurrentProjectData : null;
    const openChapterEditorFn = typeof window.openChapterEditor === 'function' ? window.openChapterEditor : null;
    if (focusModule === 'write' && typeof openChapterEditorFn === 'function') {
        store.lastWorkflowFocusedRunId = runId;
        switchModuleFn('write');
        if (typeof loadProjectDataFn === 'function') {
            Promise.resolve(loadProjectDataFn()).finally(() => {
                if (Array.isArray(store.projectData.outline) && store.projectData.outline[focusChapter - 1]) {
                    openChapterEditorFn(focusChapter - 1);
                    showToast(`已定位到第${focusChapter}章`, 'success');
                }
            });
        } else if (Array.isArray(store.projectData.outline) && store.projectData.outline[focusChapter - 1]) {
            openChapterEditorFn(focusChapter - 1);
        }
    }
}

function toCopilotRole(role) {
    if (role === 'assistant') return 'ai';
    if (role === 'user') return 'user';
    return 'status';
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
            setCopilotSessionHeader('默认模型', '准备就绪');
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
            setCopilotSessionHeader('默认模型', '准备就绪');
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

function setCopilotSessionHeader(modelLabel, agentLabel) {
    if (ui.copilotSessionMode) {
        ui.copilotSessionMode.textContent = `模型：${modelLabel}`;
    }
    if (ui.copilotSessionAgent) {
        ui.copilotSessionAgent.textContent = `${agentLabel}`;
    }
}

function updateCopilotSessionHeaderFromRouting(routing) {
    if (!routing || typeof routing !== 'object') {
        // 不显示错误信息，保持友好的默认状态
        return;
    }

    const intent = String(routing.intent || '').trim();
    const targetAgent = String(routing.target_agent || '').trim();
    const routingModel = String(routing.model || '').trim();

    // 意图中文映射
    const intentLabels = {
        'create_novel': '创作小说',
        'continue_write': '续写章节',
        'polish_content': '润色内容',
        'search_web': '网络搜索',
        'search_trends': '热点搜索',
        'query_knowledge': '查询知识库',
        'general_chat': '对话交流',
        'ask_help': '寻求帮助',
        'provide_feedback': '提供反馈',
        'project_manage': '项目管理',
        'config_settings': '配置设置'
    };

    // Agent中文映射
    const agentLabels = {
        'Communicator': '沟通助手',
        'Coordinator': '创作协调器',
        'Worldbuilder': '世界观构建',
        'Outliner': '大纲规划',
        'ChapterWriter': '章节写手',
        'ContinuousWriter': '无限续写',
        'Polisher': '润色助手',
        'Router': '智能路由',
        'WebSearch': '网络搜索',
        'TrendsSearch': '热点搜索'
    };

    // 只有在有有效路由信息时才更新显示
    if (intent && targetAgent) {
        const modelLabel = routingModel || '默认模型';
        const agentName = agentLabels[targetAgent] || targetAgent;
        setCopilotSessionHeader(modelLabel, agentName);
    }
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

    setCopilotSessionHeader('默认模型', '准备就绪');
    updateCopilotWorkflowPanel(null);

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
    try {
        if (typeof marked !== 'undefined') {
            return marked.parse(text, { breaks: true, gfm: true });
        }
    } catch (e) {
        console.warn('[renderMarkdown] marked parse error:', e);
    }
    // fallback: 用 escapeHtml 纯文本显示
    return '<p>' + escapeHtml(text) + '</p>';
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
    appendMessage(text, 'user');
    ui.copilotInput.value = '';
    const sid = getCurrentCopilotSessionId();

    // 创建空的AI消息容器
    const aiDiv = createStreamMessage();

    try {
        const response = await fetch('/api/chat/stream', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ message: text, session_id: sid })
        });

        if (!response.ok) {
            // 流式端点不可用，回退到普通模式
            aiDiv.remove();
            const res = await apiCall('/api/chat', 'POST', {
                message: text,
                session_id: sid
            });
            updateCopilotSessionHeaderFromRouting(res && res.routing);
            updateCopilotWorkflowPanel(res && res.workflow);
            appendMessage(res.reply || '收到', 'ai');
            return;
        }

        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';
        let fullText = '';
        const contentEl = aiDiv.querySelector('.msg-content');

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
                        fullText += evt.content;
                        contentEl.innerHTML = renderMarkdown(fullText);
                        scrollCopilotToBottom();
                    } else if (evt.type === 'workflow') {
                        updateCopilotWorkflowPanel(evt.workflow);
                    } else if (evt.type === 'done') {
                        // 最终完整回复
                        if (evt.reply) {
                            fullText = evt.reply;
                            contentEl.innerHTML = renderMarkdown(fullText);
                        }
                        if (evt.routing) {
                            updateCopilotSessionHeaderFromRouting(evt.routing);
                        }
                        if (evt.workflow) {
                            updateCopilotWorkflowPanel(evt.workflow);
                            
                            // ===== 新增：自动保存工作流文件 =====
                            if (typeof handleWorkflowAutoSave === 'function') {
                                try {
                                    await handleWorkflowAutoSave(evt.workflow);
                                } catch (autoSaveError) {
                                    console.error('[Copilot] 自动保存失败', autoSaveError);
                                    // 不影响主流程，只记录错误
                                }
                            }
                            // ===== 自动保存结束 =====
                        }
                        // 移除打字光标
                        aiDiv.classList.remove('streaming');
                    } else if (evt.type === 'error') {
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

        // 流结束，确保移除打字光标
        aiDiv.classList.remove('streaming');
        if (!fullText) {
            contentEl.innerHTML = renderMarkdown('收到');
        }

    } catch (e) {
        console.error('[sendCopilotMessage] stream error:', e);
        aiDiv.classList.remove('streaming');
        const contentEl = aiDiv.querySelector('.msg-content');
        if (contentEl) {
            contentEl.innerHTML = renderMarkdown('连接失败，请检查API配置');
        }
        setCopilotSessionHeader('协作创作', '连接失败');
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

function appendMessage(text, role, shouldScroll = true) {
    if (!ui.copilotMsgs) return;
    const div = document.createElement('div');
    div.className = `msg ${role}`;

    if (role === 'ai') {
        const content = document.createElement('div');
        content.className = 'msg-content';
        content.innerHTML = renderMarkdown(text);
        div.appendChild(content);
    } else {
        div.textContent = text;
    }

    ui.copilotMsgs.appendChild(div);
    if (shouldScroll) {
        scrollCopilotToBottom();
    }
}

function scrollCopilotToBottom() {
    if (ui.copilotMsgs) {
        ui.copilotMsgs.scrollTop = ui.copilotMsgs.scrollHeight;
    }
}

// 全局暴露核心函数和状态
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
window.createStreamMessage = createStreamMessage;
window.scrollCopilotToBottom = scrollCopilotToBottom;
window.updateCopilotWorkflowPanel = updateCopilotWorkflowPanel;
window.restoreCopilotWorkflowStatus = restoreCopilotWorkflowStatus;

console.log('[app-core.js] 核心模块已加载');
