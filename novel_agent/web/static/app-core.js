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
    focusMode: false,
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
    currentProjectName: null
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
}

// 初始化
async function init() {
    initUIReferences();
    bindEvents();
    await loadSavedSettings(); // 加载保存的主题和背景设置（异步加载IndexedDB背景图片）
    restoreSidebarState(); // 恢复侧边栏状态
    loadKnowledgeCategories(); // 加载自定义资料库分类
    await loadProjects(); // 加载项目列表
    await checkGlobalAPIConfig(); // 检查全局API配置
    switchModule('dashboard');
    
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
    store.currentModule = moduleId;

    // 更新资源栏激活状态
    ui.resItems.forEach(item => {
        item.classList.toggle('active', item.dataset.module === moduleId);
    });

    // 更新导航面板
    renderNavPanel(moduleId);
    
    // 控制创作助手按钮的显示（只在创作相关页面显示）
    const isWritingModule = moduleId === 'infinite-write' || moduleId === 'write';
    if (ui.toggleCopilotBtn) {
        ui.toggleCopilotBtn.style.display = isWritingModule ? '' : 'none';
    }
    // 如果切换到非创作模块，自动关闭Copilot面板
    if (!isWritingModule && store.copilotVisible) {
        store.copilotVisible = false;
        if (ui.copilotPanel) {
            ui.copilotPanel.classList.add('collapsed');
            ui.copilotPanel.style.display = 'none';
        }
    }

    // 根据模块渲染工作区
    if (moduleId === 'dashboard') {
        renderDashboard();
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

// 新建会话 - 清空聊天记录
function clearCopilotChat() {
    if (!ui.copilotMsgs) return;
    
    // 确认对话框
    if (ui.copilotMsgs.children.length > 1) {
        if (!confirm('确定要清空当前会话吗？\n\n这将清除所有对话记录，开始新的会话。')) {
            return;
        }
    }
    
    // 清空消息容器
    ui.copilotMsgs.innerHTML = '';
    
    // 添加欢迎消息
    const welcomeMsg = document.createElement('div');
    welcomeMsg.className = 'msg ai';
    welcomeMsg.innerHTML = `你好！我是你的写作助手。试试：
        <ul style="margin: 8px 0; padding-left: 20px;">
            <li>输入 <code>@</code> 引用角色、章节或设定</li>
            <li>直接提问或发指令</li>
        </ul>`;
    ui.copilotMsgs.appendChild(welcomeMsg);
    
    // 清空输入框
    const input = document.getElementById('copilot-input-text');
    if (input) {
        input.value = '';
        input.dataset.mentions = '[]';
    }
    
    showToast('已开始新会话 ✨');
}

function toggleCopilot() {
    store.copilotVisible = !store.copilotVisible;
    if (ui.copilotPanel) {
        ui.copilotPanel.classList.toggle('collapsed', !store.copilotVisible);
        ui.copilotPanel.style.display = store.copilotVisible ? 'flex' : 'none';
    }
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

async function sendCopilotMessage() {
    if (!ui.copilotInput) return;
    const text = ui.copilotInput.value.trim();
    if (!text) return;

    appendMessage(text, 'user');
    ui.copilotInput.value = '';

    try {
        const res = await apiCall('/api/chat', 'POST', {
            message: text,
            session_id: 'copilot'
        });
        appendMessage(res.reply || '收到', 'ai');
    } catch (e) {
        appendMessage('连接失败，请检查API配置', 'ai');
    }
}

function appendMessage(text, role) {
    if (!ui.copilotMsgs) return;
    const div = document.createElement('div');
    div.className = `msg ${role}`;
    div.textContent = text;
    ui.copilotMsgs.appendChild(div);
    ui.copilotMsgs.scrollTop = ui.copilotMsgs.scrollHeight;
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

console.log('[app-core.js] 核心模块已加载');