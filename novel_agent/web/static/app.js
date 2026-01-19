/**
 * 鏂囨€滱gent - 宸ヤ綔鍙版帶鍒跺櫒
 */

// 鍏ㄥ眬鐘舵€?Store
const store = {
    currentModule: 'dashboard',
    currentChapterId: null,
    currentDashboardView: 'home', // 'home' 鎴?'stats'
    // 椤圭洰鐩稿叧
    currentProjectId: null,
    currentProjectName: '',
    projects: [],
    // 褰撳墠椤圭洰鏁版嵁
    projectData: {
        characters: [],
        outline: [],
        worldbuilding: [],
        items: [],
        // 璧勬枡搴撴墿灞曞垎绫?
        eventlines: [],      // 浜嬩欢绾?
        outline_settings: [], // 澶х翰璁惧畾
        detail_settings: [],  // 缁嗙翰璁惧畾
        chapter_settings: [], // 绔犵翰璁惧畾
        custom_knowledge: []  // 鐢ㄦ埛鑷畾涔夎祫鏂欏簱
    },
    // 璧勬枡搴撳垎绫婚厤缃?
    knowledgeCategories: [
        { id: 'db-char', key: 'characters', name: '瑙掕壊妗ｆ', icon: 'ri-user-smile-line', builtin: true },
        { id: 'db-world', key: 'worldbuilding', name: '涓栫晫璁惧畾', icon: 'ri-earth-line', builtin: true },
        { id: 'db-item', key: 'items', name: '閬撳叿鐗╁搧', icon: 'ri-sword-line', builtin: true },
        { id: 'db-event', key: 'eventlines', name: '浜嬩欢绾?, icon: 'ri-timeline-view', builtin: true },
        { id: 'db-outline', key: 'outline_settings', name: '澶х翰璁惧畾', icon: 'ri-file-list-3-line', builtin: true },
        { id: 'db-detail', key: 'detail_settings', name: '缁嗙翰璁惧畾', icon: 'ri-file-text-line', builtin: true },
        { id: 'db-chapter', key: 'chapter_settings', name: '绔犵翰璁惧畾', icon: 'ri-book-open-line', builtin: true }
    ],
    copilotVisible: false,
    focusMode: false,
    settings: {
        bgUrl: '',
        bgOpacity: 0.85,
        bgLightness: 12,       // 鑳屾櫙浜害 0-100锛?=绾粦锛?00=绾櫧
        accentHue: 250,
        accentSaturation: 40,  // 楗卞拰搴?0-100锛?=榛戠櫧鐏?
        textLightness: 90,     // 瀛椾綋浜害 0-100
        theme: 'dark'
    }
};

// UI 寮曠敤
const ui = {
    resItems: document.querySelectorAll('.res-item[data-module]'),
    navPanel: document.getElementById('nav-panel'),
    navTitle: document.getElementById('nav-title'),
    navList: document.getElementById('nav-list-container'),
    navActionAdd: document.getElementById('nav-action-add'),
    workspace: document.getElementById('main-view'),
    breadcrumbs: document.getElementById('breadcrumbs'),
    copilotPanel: document.getElementById('copilot-panel'),
    toggleCopilotBtn: document.getElementById('toggle-copilot'),
    closeCopilotBtn: document.querySelector('.close-copilot'),
    toggleFocusBtn: document.getElementById('toggle-focus'),
    copilotInput: document.querySelector('.copilot-input textarea'),
    copilotSendBtn: document.querySelector('.copilot-input button'),
    copilotMsgs: document.getElementById('copilot-messages'),
    resBar: document.querySelector('.resource-bar'),
    // 椤圭洰閫夋嫨鍣?
    projectCurrent: document.getElementById('project-current'),
    projectDropdown: document.getElementById('project-dropdown'),
    projectList: document.getElementById('project-list'),
    projectAdd: document.getElementById('project-add'),
    currentProjectName: document.getElementById('current-project-name')
};

// 鍒濆鍖?
async function init() {
    bindEvents();
    await loadSavedSettings(); // 鍔犺浇淇濆瓨鐨勪富棰樺拰鑳屾櫙璁剧疆锛堝紓姝ュ姞杞絀ndexedDB鑳屾櫙鍥剧墖锛?
    restoreSidebarState(); // 鎭㈠渚ц竟鏍忕姸鎬?
    loadKnowledgeCategories(); // 鍔犺浇鑷畾涔夎祫鏂欏簱鍒嗙被
    await loadProjects(); // 鍔犺浇椤圭洰鍒楄〃
    await checkGlobalAPIConfig(); // 妫€鏌ュ叏灞€API閰嶇疆
    switchModule('dashboard');
}

// 妫€鏌ュ叏灞€API閰嶇疆
async function checkGlobalAPIConfig() {
    try {
        const config = await apiCall('/api/global-config', 'GET');
        if (!config.is_configured) {
            // 寤惰繜鏄剧ず鎻愮ず锛岄伩鍏嶅奖鍝嶅垵濮嬪姞杞?
            setTimeout(() => {
                showToast('馃挕 鎻愮ず锛氳鍏堝湪璁剧疆涓厤缃叏灞€API', 'warning');
            }, 2000);
        }
    } catch (e) {
        console.error('Failed to check global API config:', e);
    }
}

// 缁戝畾浜嬩欢
function bindEvents() {
    // 璧勬簮鏍忓垏鎹?
    ui.resItems.forEach(item => {
        item.addEventListener('click', () => switchModule(item.dataset.module));
    });

    // Copilot 寮€鍏?
    if (ui.toggleCopilotBtn) {
        ui.toggleCopilotBtn.addEventListener('click', toggleCopilot);
    }
    if (ui.closeCopilotBtn) {
        ui.closeCopilotBtn.addEventListener('click', toggleCopilot);
    }
    
    // 鏂板缓浼氳瘽鎸夐挳
    const newChatBtn = document.getElementById('new-chat-btn');
    if (newChatBtn) {
        newChatBtn.addEventListener('click', clearCopilotChat);
    }

    // Copilot 鍙戦€?
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

    // 涓撴敞妯″紡
    if (ui.toggleFocusBtn) {
        ui.toggleFocusBtn.addEventListener('click', toggleFocusMode);
    }

    // 椤圭洰閫夋嫨鍣?
    if (ui.projectCurrent) {
        ui.projectCurrent.addEventListener('click', toggleProjectDropdown);
    }
    if (ui.projectAdd) {
        ui.projectAdd.addEventListener('click', showCreateProjectDialog);
    }

    // 鐐瑰嚮澶栭儴鍏抽棴涓嬫媺
    document.addEventListener('click', (e) => {
        if (ui.projectDropdown && !ui.projectDropdown.classList.contains('hidden')) {
            if (!e.target.closest('.project-selector')) {
                ui.projectDropdown.classList.add('hidden');
            }
        }
    });

    // 渚ц竟鏍忔敹缂╂寜閽?
    const sidebarToggleBtn = document.getElementById('sidebar-toggle-btn');
    if (sidebarToggleBtn) {
        sidebarToggleBtn.addEventListener('click', (e) => {
            e.stopPropagation();
            toggleSidebar();
        });
    }
}

// ===== 鏍稿績閫昏緫锛氭ā鍧楀垏鎹?=====
function switchModule(moduleId) {
    store.currentModule = moduleId;

    // 鏇存柊璧勬簮鏍忔縺娲荤姸鎬?
    ui.resItems.forEach(item => {
        item.classList.toggle('active', item.dataset.module === moduleId);
    });

    // 鏇存柊瀵艰埅闈㈡澘
    renderNavPanel(moduleId);

    // 鏍规嵁妯″潡娓叉煋宸ヤ綔鍖?
    if (moduleId === 'dashboard') {
        renderDashboard();
    } else if (moduleId === 'settings') {
        loadThemeSettings(); // 榛樿鍔犺浇涓婚璁剧疆
    } else if (moduleId === 'write') {
        // 鍐欎綔妯″潡榛樿鏄剧ず绌虹紪杈戝櫒
        showEmptyEditor();
    } else if (moduleId === 'world') {
        showEmptyWorld();
    }
}

// ===== 渚ц竟鏍忔敹缂╁姛鑳?=====
function toggleSidebar() {
    const workbench = document.querySelector('.workbench');
    const navPanel = document.getElementById('nav-panel');

    if (workbench && navPanel) {
        const isCollapsed = workbench.classList.contains('sidebar-collapsed');

        if (isCollapsed) {
            // 灞曞紑渚ц竟鏍?
            workbench.classList.remove('sidebar-collapsed');
            workbench.style.gridTemplateColumns = '';  // 鎭㈠榛樿
            navPanel.style.width = '';
            navPanel.style.display = '';
        } else {
            // 鏀剁缉渚ц竟鏍?
            workbench.classList.add('sidebar-collapsed');
            workbench.style.gridTemplateColumns = 'var(--res-bar-w) 0px 1fr auto';
            navPanel.style.width = '0';
            navPanel.style.display = 'none';
        }

        localStorage.setItem('sidebar_collapsed', !isCollapsed ? 'true' : 'false');
    }
}

// 鍒濆鍖栨椂鎭㈠渚ц竟鏍忕姸鎬?
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

// ===== 娓叉煋锛氬鑸潰鏉?=====
function renderNavPanel(moduleId) {
    ui.navList.innerHTML = '';

    switch (moduleId) {
        case 'dashboard':
            ui.navTitle.textContent = '椤圭洰姒傝';
            ui.navActionAdd.style.display = 'none';
            renderNavList([
                { id: 'dash-home', icon: 'ri-home-line', text: '涓婚〉', active: store.currentDashboardView === 'home' },
                { id: 'dash-stat', icon: 'ri-pie-chart-line', text: '缁熻', active: store.currentDashboardView === 'stats' }
            ], (item) => {
                if (item.id === 'dash-home') {
                    store.currentDashboardView = 'home';
                    renderDashboard();
                } else if (item.id === 'dash-stat') {
                    store.currentDashboardView = 'stats';
                    renderStatistics();
                }
            });
            break;

        case 'write':
            ui.navTitle.textContent = '鍐欎綔涓績';
            ui.navActionAdd.style.display = 'block';
            ui.navActionAdd.onclick = addNewChapter;

            // 娓叉煋鍐欎綔妯″潡瀵艰埅锛堝寘鎷棤闄愮画鍐欏拰绔犺妭鍒楄〃锛?
            renderWriteNavPanel();
            break;

        case 'world':
            ui.navTitle.textContent = '璧勬枡搴?;
            ui.navActionAdd.style.display = 'block';
            ui.navActionAdd.onclick = addNewSetting;
            renderKnowledgeNavPanel();
            break;

        case 'settings':
            ui.navTitle.textContent = '鍋忓ソ璁剧疆';
            ui.navActionAdd.style.display = 'none';
            renderNavList([
                { id: 'set-theme', icon: 'ri-palette-line', text: '澶栬涓婚', active: true },
                { id: 'set-global-api', icon: 'ri-global-line', text: '鍏ㄥ眬API閰嶇疆' },
                { id: 'set-knowledge-base', icon: 'ri-database-2-line', text: '鐭ヨ瘑搴撻厤缃? },
                { id: 'set-agent', icon: 'ri-brain-line', text: 'Agent閰嶇疆' },
                { id: 'set-prompts', icon: 'ri-file-text-line', text: '鎻愮ず璇嶇鐞? },
                { id: 'set-regex', icon: 'ri-code-line', text: '姝ｅ垯鏇挎崲瑙勫垯' }
            ], (item) => {
                if (item.id === 'set-theme') loadThemeSettings();
                if (item.id === 'set-global-api') loadGlobalAPISettings();
                if (item.id === 'set-knowledge-base') loadKnowledgeBaseSettings();
                if (item.id === 'set-agent') loadAgentSettings();
                if (item.id === 'set-prompts') {
                    // 寤惰繜璋冪敤纭繚 prompt_manager.js 宸插姞杞斤紝浣跨敤閲嶈瘯鏈哄埗
                    let retryCount = 0;
                    const maxRetries = 10;
                    const checkAndLoad = () => {
                        if (typeof window.loadPromptSettings === 'function') {
                            window.loadPromptSettings();
                        } else if (retryCount < maxRetries) {
                            retryCount++;
                            console.log(`[Settings] 绛夊緟 prompt_manager.js 鍔犺浇... (${retryCount}/${maxRetries})`);
                            setTimeout(checkAndLoad, 100);
                        } else {
                            console.error('[Settings] loadPromptSettings 鍑芥暟鏈壘鍒帮紝璇锋鏌?prompt_manager.js 鏄惁姝ｇ‘鍔犺浇');
                            showToast('鎻愮ず璇嶇鐞嗘ā鍧楀姞杞藉け璐ワ紝璇峰埛鏂伴〉闈?, 'error');
                        }
                    };
                    setTimeout(checkAndLoad, 50);
                }
                if (item.id === 'set-regex') loadRegexRulesSettings();
            });
            break;
    }
}

function renderNavList(items, onClick) {
    ui.navList.innerHTML = '';
    items.forEach(item => {
        const div = document.createElement('div');
        div.className = `list-item ${item.active ? 'active' : ''}`;
        div.innerHTML = `
            <i class="${item.icon}"></i>
            <span>${item.text}</span>
            ${item.count !== undefined ? `<span style="margin-left:auto; font-size:11px; opacity:0.6;">(${item.count})</span>` : ''}
        `;
        div.addEventListener('click', () => {
            ui.navList.querySelectorAll('.list-item').forEach(el => el.classList.remove('active'));
            div.classList.add('active');
            if (onClick) onClick(item);
        });
        ui.navList.appendChild(div);
    });
}

// 娓叉煋甯︽搷浣滄寜閽殑鍒楄〃锛堢敤浜庣珷鑺傦級
function renderNavListWithActions(items, type) {
    ui.navList.innerHTML = '';

    if (items.length === 0) {
        ui.navList.innerHTML = `
            <div style="padding: 20px; text-align: center; color: var(--text-secondary); font-size: 13px;">
                <p>鏆傛棤鍐呭</p>
                <p style="font-size: 11px; margin-top: 8px;">鐐瑰嚮涓婃柟 + 娣诲姞</p>
            </div>
        `;
        return;
    }

    items.forEach(item => {
        const div = document.createElement('div');
        div.className = 'list-item';
        div.style.cssText = 'display: flex; align-items: center; gap: 8px; padding: 10px 12px;';
        div.innerHTML = `
            <i class="${item.icon}" style="opacity: 0.6;"></i>
            <span style="flex: 1; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;">${item.text}</span>
            <div class="item-actions" style="display: flex; gap: 4px; opacity: 0; transition: opacity 0.2s;">
                <button class="edit-btn" title="缂栬緫" style="background: none; border: none; color: var(--text-secondary); cursor: pointer; padding: 4px;">
                    <i class="ri-edit-line"></i>
                </button>
                <button class="delete-btn" title="鍒犻櫎" style="background: none; border: none; color: #ef4444; cursor: pointer; padding: 4px;">
                    <i class="ri-delete-bin-line"></i>
                </button>
            </div>
        `;

        // 鎮仠鏄剧ず鎿嶄綔鎸夐挳
        div.addEventListener('mouseenter', () => {
            div.querySelector('.item-actions').style.opacity = '1';
        });
        div.addEventListener('mouseleave', () => {
            div.querySelector('.item-actions').style.opacity = '0';
        });

        // 鐐瑰嚮鎵撳紑缂栬緫鍣?
        div.addEventListener('click', (e) => {
            if (!e.target.closest('.item-actions')) {
                ui.navList.querySelectorAll('.list-item').forEach(el => el.classList.remove('active'));
                div.classList.add('active');
                if (type === 'chapter') {
                    openChapterEditor(item.index);
                }
            }
        });

        // 缂栬緫鎸夐挳
        div.querySelector('.edit-btn').addEventListener('click', (e) => {
            e.stopPropagation();
            if (type === 'chapter') {
                editChapterTitle(item.index);
            }
        });

        // 鍒犻櫎鎸夐挳
        div.querySelector('.delete-btn').addEventListener('click', (e) => {
            e.stopPropagation();
            if (type === 'chapter') {
                deleteChapter(item.index);
            }
        });

        ui.navList.appendChild(div);
    });
}


// ===== 娓叉煋锛氫富宸ヤ綔鍖哄唴瀹?=====

function renderDashboard() {
    store.currentDashboardView = 'home';
    updateBreadcrumbs([store.currentProjectName || '鎴戠殑椤圭洰', '涓婚〉']);

    // 璁＄畻缁熻鏁版嵁
    const chapters = store.projectData.outline || [];
    const totalWords = chapters.reduce((sum, ch) => sum + (ch.content || '').replace(/\s/g, '').length, 0);
    const chapterCount = chapters.length;
    const writtenChapters = chapters.filter(ch => (ch.content || '').length > 0).length;
    const characterCount = (store.projectData.characters || []).length;
    const settingCount = (store.projectData.worldbuilding || []).length + (store.projectData.items || []).length;

    ui.workspace.innerHTML = `
        <div style="padding: 40px; text-align: center;">
            <div style="font-size: 48px; margin-bottom: 20px;">鉁?/div>
            <h1 style="color: var(--text-primary); margin-bottom: 10px;">銆?{store.currentProjectName || '鏈懡鍚嶉」鐩?}銆?/h1>
            <p style="color: var(--text-secondary);">鏂囨€濆娉夋秾锛屽垱浣滄棤鏋侀檺</p>
            
            <div style="display: flex; gap: 16px; justify-content: center; margin-top: 40px; flex-wrap: wrap;">
                <div class="meta-card" style="width: 140px; height: 100px; align-items: center; justify-content: center;">
                    <div style="font-size: 28px; font-weight: bold; color: var(--accent-color);">${totalWords.toLocaleString()}</div>
                    <div style="font-size: 12px; color: var(--text-secondary);">鎬诲瓧鏁?/div>
                </div>
                <div class="meta-card" style="width: 140px; height: 100px; align-items: center; justify-content: center;">
                    <div style="font-size: 28px; font-weight: bold; color: #10b981;">${chapterCount}</div>
                    <div style="font-size: 12px; color: var(--text-secondary);">绔犺妭鏁?/div>
                </div>
                <div class="meta-card" style="width: 140px; height: 100px; align-items: center; justify-content: center;">
                    <div style="font-size: 28px; font-weight: bold; color: #f59e0b;">${characterCount}</div>
                    <div style="font-size: 12px; color: var(--text-secondary);">瑙掕壊鏁?/div>
                </div>
                <div class="meta-card" style="width: 140px; height: 100px; align-items: center; justify-content: center;">
                    <div style="font-size: 28px; font-weight: bold; color: #8b5cf6;">${settingCount}</div>
                    <div style="font-size: 12px; color: var(--text-secondary);">鐭ヨ瘑鏉＄洰</div>
                </div>
            </div>
            
            <div style="margin-top: 40px; display: flex; gap: 12px; justify-content: center;">
                <button onclick="switchModule('write')" style="padding: 12px 24px; background: var(--accent-color); border: none; color: white; border-radius: 8px; cursor: pointer; font-weight: 500;">
                    <i class="ri-quill-pen-line"></i> 寮€濮嬪啓浣?
                </button>
                <button onclick="switchModule('world')" style="padding: 12px 24px; background: rgba(255,255,255,0.1); border: 1px solid var(--border-color); color: var(--text-primary); border-radius: 8px; cursor: pointer;">
                    <i class="ri-book-mark-line"></i> 绠＄悊璧勬枡搴?
                </button>
            </div>
            
            ${chapterCount === 0 ? `
            <p style="margin-top: 30px; color: var(--text-secondary); font-size: 13px;">
                馃挕 鎻愮ず锛氱偣鍑诲乏渚?<i class="ri-settings-4-line"></i> 璁剧疆锛岃繘鍏ャ€屽叏灞€API閰嶇疆銆嶉厤缃偍鐨凙PI
            </p>
            ` : ''}
        </div>
    `;
}

// 娓叉煋缁熻椤甸潰
function renderStatistics() {
    store.currentDashboardView = 'stats';
    updateBreadcrumbs([store.currentProjectName || '鎴戠殑椤圭洰', '缁熻']);

    // 璁＄畻鍚勯」缁熻鏁版嵁
    const chapters = store.projectData.outline || [];
    const totalWords = chapters.reduce((sum, ch) => sum + (ch.content || '').replace(/\s/g, '').length, 0);
    const chapterCount = chapters.length;
    const writtenChapters = chapters.filter(ch => (ch.content || '').length > 0).length;
    const emptyChapters = chapterCount - writtenChapters;
    const avgWordsPerChapter = writtenChapters > 0 ? Math.round(totalWords / writtenChapters) : 0;
    
    const characterCount = (store.projectData.characters || []).length;
    const worldCount = (store.projectData.worldbuilding || []).length;
    const itemCount = (store.projectData.items || []).length;
    const eventCount = (store.projectData.eventlines || []).length;
    const outlineSettingCount = (store.projectData.outline_settings || []).length;
    const detailSettingCount = (store.projectData.detail_settings || []).length;
    const chapterSettingCount = (store.projectData.chapter_settings || []).length;
    
    // 璁＄畻姣忕珷瀛楁暟鍒嗗竷
    const chapterWordsData = chapters.map((ch, i) => ({
        chapter: i + 1,
        title: ch.title || `绗?{i + 1}绔燻,
        words: (ch.content || '').replace(/\s/g, '').length
    }));
    
    // 璁＄畻瀹屾垚杩涘害
    const completionRate = chapterCount > 0 ? Math.round((writtenChapters / chapterCount) * 100) : 0;
    
    // 璁＄畻鏈€澶у瓧鏁扮敤浜庤繘搴︽潯姣斾緥
    const maxWords = chapterWordsData.length > 0 ? Math.max(...chapterWordsData.map(c => c.words || 1)) : 1;

    ui.workspace.innerHTML = `
        <div style="padding: 30px; max-width: 1000px; margin: 0 auto;">
            <h2 style="color: var(--text-primary); margin-bottom: 30px; font-size: 20px; display: flex; align-items: center; gap: 10px;">
                <i class="ri-pie-chart-line"></i>
                椤圭洰缁熻鍒嗘瀽
            </h2>
            
            <!-- 鏍稿績鎸囨爣鍗＄墖 -->
            <div style="display: grid; grid-template-columns: repeat(4, 1fr); gap: 16px; margin-bottom: 30px;">
                <div class="stats-card" style="background: rgba(255,255,255,0.03); border: 1px solid var(--border-color); border-radius: 12px; padding: 20px; text-align: center;">
                    <div style="font-size: 32px; font-weight: bold; color: var(--accent-color);">${totalWords.toLocaleString()}</div>
                    <div style="font-size: 13px; color: var(--text-secondary); margin-top: 6px;">鎬诲瓧鏁?/div>
                </div>
                <div class="stats-card" style="background: rgba(255,255,255,0.03); border: 1px solid var(--border-color); border-radius: 12px; padding: 20px; text-align: center;">
                    <div style="font-size: 32px; font-weight: bold; color: #10b981;">${chapterCount}</div>
                    <div style="font-size: 13px; color: var(--text-secondary); margin-top: 6px;">鎬荤珷鑺?/div>
                </div>
                <div class="stats-card" style="background: rgba(255,255,255,0.03); border: 1px solid var(--border-color); border-radius: 12px; padding: 20px; text-align: center;">
                    <div style="font-size: 32px; font-weight: bold; color: #f59e0b;">${avgWordsPerChapter.toLocaleString()}</div>
                    <div style="font-size: 13px; color: var(--text-secondary); margin-top: 6px;">骞冲潎姣忕珷瀛楁暟</div>
                </div>
                <div class="stats-card" style="background: rgba(255,255,255,0.03); border: 1px solid var(--border-color); border-radius: 12px; padding: 20px; text-align: center;">
                    <div style="font-size: 32px; font-weight: bold; color: #8b5cf6;">${completionRate}%</div>
                    <div style="font-size: 13px; color: var(--text-secondary); margin-top: 6px;">瀹屾垚杩涘害</div>
                </div>
            </div>
            
            <!-- 绔犺妭瀹屾垚鎯呭喌 -->
            <div style="background: rgba(255,255,255,0.03); border: 1px solid var(--border-color); border-radius: 12px; padding: 20px; margin-bottom: 20px;">
                <h3 style="color: var(--text-primary); margin-bottom: 16px; font-size: 15px; display: flex; align-items: center; gap: 8px;">
                    <i class="ri-file-list-3-line"></i>
                    绔犺妭瀹屾垚鎯呭喌
                </h3>
                <div style="display: flex; gap: 24px; align-items: center;">
                    <div style="display: flex; align-items: center; gap: 8px;">
                        <div style="width: 10px; height: 10px; background: #22c55e; border-radius: 50%;"></div>
                        <span style="color: var(--text-secondary); font-size: 13px;">宸插畬鎴愮珷鑺?/span>
                        <span style="font-weight: 600; color: var(--text-primary); margin-left: 4px;">${writtenChapters}</span>
                    </div>
                    <div style="display: flex; align-items: center; gap: 8px;">
                        <div style="width: 10px; height: 10px; background: #ef4444; border-radius: 50%;"></div>
                        <span style="color: var(--text-secondary); font-size: 13px;">寰呭畬鎴愮珷鑺?/span>
                        <span style="font-weight: 600; color: var(--text-primary); margin-left: 4px;">${emptyChapters}</span>
                    </div>
                </div>
                <!-- 杩涘害鏉?-->
                <div style="background: rgba(255,255,255,0.1); height: 8px; border-radius: 4px; overflow: hidden; margin-top: 16px;">
                    <div style="background: linear-gradient(90deg, #22c55e, #10b981); height: 100%; width: ${completionRate}%; transition: width 0.5s;"></div>
                </div>
            </div>
            
            <!-- 璧勬枡搴撶粺璁?-->
            <div style="background: rgba(255,255,255,0.03); border: 1px solid var(--border-color); border-radius: 12px; padding: 20px; margin-bottom: 20px;">
                <h3 style="color: var(--text-primary); margin-bottom: 16px; font-size: 15px; display: flex; align-items: center; gap: 8px;">
                    <i class="ri-database-2-line"></i>
                    璧勬枡搴撶粺璁?
                </h3>
                <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(120px, 1fr)); gap: 12px;">
                    <div style="background: rgba(236, 72, 153, 0.1); padding: 14px; border-radius: 8px; text-align: center;">
                        <div style="font-size: 22px; font-weight: bold; color: #ec4899;">${characterCount}</div>
                        <div style="font-size: 11px; color: var(--text-secondary); margin-top: 4px;">瑙掕壊妗ｆ</div>
                    </div>
                    <div style="background: rgba(6, 182, 212, 0.1); padding: 14px; border-radius: 8px; text-align: center;">
                        <div style="font-size: 22px; font-weight: bold; color: #06b6d4;">${worldCount}</div>
                        <div style="font-size: 11px; color: var(--text-secondary); margin-top: 4px;">涓栫晫璁惧畾</div>
                    </div>
                    <div style="background: rgba(249, 115, 22, 0.1); padding: 14px; border-radius: 8px; text-align: center;">
                        <div style="font-size: 22px; font-weight: bold; color: #f97316;">${itemCount}</div>
                        <div style="font-size: 11px; color: var(--text-secondary); margin-top: 4px;">閬撳叿鐗╁搧</div>
                    </div>
                    <div style="background: rgba(168, 85, 247, 0.1); padding: 14px; border-radius: 8px; text-align: center;">
                        <div style="font-size: 22px; font-weight: bold; color: #a855f7;">${eventCount}</div>
                        <div style="font-size: 11px; color: var(--text-secondary); margin-top: 4px;">浜嬩欢绾?/div>
                    </div>
                    <div style="background: rgba(20, 184, 166, 0.1); padding: 14px; border-radius: 8px; text-align: center;">
                        <div style="font-size: 22px; font-weight: bold; color: #14b8a6;">${outlineSettingCount}</div>
                        <div style="font-size: 11px; color: var(--text-secondary); margin-top: 4px;">澶х翰璁惧畾</div>
                    </div>
                    <div style="background: rgba(234, 179, 8, 0.1); padding: 14px; border-radius: 8px; text-align: center;">
                        <div style="font-size: 22px; font-weight: bold; color: #eab308;">${detailSettingCount}</div>
                        <div style="font-size: 11px; color: var(--text-secondary); margin-top: 4px;">缁嗙翰璁惧畾</div>
                    </div>
                </div>
            </div>
            
            <!-- 绔犺妭瀛楁暟鍒嗗竷 -->
            ${chapterWordsData.length > 0 ? `
            <div style="background: rgba(255,255,255,0.03); border: 1px solid var(--border-color); border-radius: 12px; padding: 20px;">
                <h3 style="color: var(--text-primary); margin-bottom: 16px; font-size: 15px; display: flex; align-items: center; gap: 8px;">
                    <i class="ri-bar-chart-line"></i>
                    绔犺妭瀛楁暟鍒嗗竷
                </h3>
                <div style="display: flex; flex-direction: column; gap: 8px; max-height: 280px; overflow-y: auto; padding-right: 8px;">
                    ${chapterWordsData.map(ch => {
                        const widthPercent = maxWords > 0 ? Math.min(100, (ch.words / maxWords) * 100) : 0;
                        return `
                        <div style="display: flex; align-items: center; gap: 10px; padding: 4px 0;">
                            <span style="min-width: 70px; font-size: 12px; color: var(--text-secondary); flex-shrink: 0;">绗?{ch.chapter}绔?/span>
                            <div style="flex: 1; background: rgba(255,255,255,0.08); height: 18px; border-radius: 4px; overflow: hidden; position: relative;">
                                <div style="background: linear-gradient(90deg, var(--accent-color), #8b5cf6); height: 100%; width: ${widthPercent}%; transition: width 0.3s; border-radius: 4px;"></div>
                            </div>
                            <span style="min-width: 55px; text-align: right; font-size: 12px; color: var(--text-primary); flex-shrink: 0;">${ch.words.toLocaleString()}瀛?/span>
                        </div>
                    `;
                    }).join('')}
                </div>
            </div>
            ` : `
            <div style="background: rgba(255,255,255,0.03); border: 1px solid var(--border-color); border-radius: 12px; padding: 40px; text-align: center;">
                <i class="ri-bar-chart-line" style="font-size: 40px; color: var(--text-secondary); opacity: 0.3;"></i>
                <p style="color: var(--text-secondary); margin-top: 12px; font-size: 13px;">鏆傛棤绔犺妭鏁版嵁</p>
            </div>
            `}
        </div>
    `;
}

function showEmptyEditor() {
    updateBreadcrumbs(['鍐欎綔', '閫夋嫨绔犺妭']);
    ui.workspace.innerHTML = `
        <div style="display: flex; align-items: center; justify-content: center; height: 100%; color: var(--text-secondary);">
            <div style="text-align: center;">
                <i class="ri-file-text-line" style="font-size: 48px; opacity: 0.3;"></i>
                <p style="margin-top: 16px;">浠庡乏渚ч€夋嫨涓€涓珷鑺傚紑濮嬪啓浣?/p>
            </div>
        </div>
    `;
}

function showEmptyWorld() {
    updateBreadcrumbs(['璧勬枡搴?, '閫夋嫨绫诲埆']);
    ui.workspace.innerHTML = `
        <div style="display: flex; align-items: center; justify-content: center; height: 100%; color: var(--text-secondary);">
            <div style="text-align: center;">
                <i class="ri-book-mark-line" style="font-size: 48px; opacity: 0.3;"></i>
                <p style="margin-top: 16px;">浠庡乏渚ч€夋嫨涓€涓祫鏂欏簱绫诲埆</p>
            </div>
        </div>
    `;
}

// ===== 璧勬枡搴撳鑸潰鏉?=====

function renderKnowledgeNavPanel() {
    ui.navList.innerHTML = '';
    
    // 鍐呯疆璧勬枡搴撳垎绫?
    const builtinCategories = store.knowledgeCategories.filter(c => c.builtin);
    
    builtinCategories.forEach(cat => {
        const count = (store.projectData[cat.key] || []).length;
        const div = document.createElement('div');
        div.className = 'list-item';
        div.innerHTML = `
            <i class="${cat.icon}"></i>
            <span>${cat.name}</span>
            <span style="margin-left:auto; font-size:11px; opacity:0.6;">(${count})</span>
        `;
        div.addEventListener('click', () => {
            ui.navList.querySelectorAll('.list-item').forEach(el => el.classList.remove('active'));
            div.classList.add('active');
            loadDatabase(cat.id);
        });
        ui.navList.appendChild(div);
    });
    
    // 鑷畾涔夎祫鏂欏簱鍒嗙被
    const customCategories = store.knowledgeCategories.filter(c => !c.builtin);
    
    if (customCategories.length > 0) {
        // 鍒嗛殧绾?
        const separator = document.createElement('div');
        separator.style.cssText = 'height: 1px; background: var(--border-color); margin: 12px 8px;';
        ui.navList.appendChild(separator);
        
        // 鑷畾涔夊垎绫绘爣棰?
        const customTitle = document.createElement('div');
        customTitle.style.cssText = 'font-size: 11px; color: var(--text-secondary); padding: 8px 12px; opacity: 0.7;';
        customTitle.textContent = '鑷畾涔夎祫鏂欏簱';
        ui.navList.appendChild(customTitle);
        
        customCategories.forEach(cat => {
            const count = (store.projectData[cat.key] || []).length;
            const div = document.createElement('div');
            div.className = 'list-item';
            div.style.cssText = 'display: flex; align-items: center;';
            div.innerHTML = `
                <i class="${cat.icon}"></i>
                <span style="flex: 1;">${cat.name}</span>
                <span style="font-size:11px; opacity:0.6; margin-right: 8px;">(${count})</span>
                <button class="delete-category-btn" title="鍒犻櫎鍒嗙被" style="background: none; border: none; color: #ef4444; cursor: pointer; padding: 4px; opacity: 0; transition: opacity 0.2s;">
                    <i class="ri-delete-bin-line" style="font-size: 12px;"></i>
                </button>
            `;
            
            div.addEventListener('mouseenter', () => {
                div.querySelector('.delete-category-btn').style.opacity = '1';
            });
            div.addEventListener('mouseleave', () => {
                div.querySelector('.delete-category-btn').style.opacity = '0';
            });
            
            div.querySelector('.delete-category-btn').addEventListener('click', (e) => {
                e.stopPropagation();
                deleteKnowledgeCategory(cat.id);
            });
            
            div.addEventListener('click', (e) => {
                if (!e.target.closest('.delete-category-btn')) {
                    ui.navList.querySelectorAll('.list-item').forEach(el => el.classList.remove('active'));
                    div.classList.add('active');
                    loadDatabase(cat.id);
                }
            });
            ui.navList.appendChild(div);
        });
    }
    
    // 娣诲姞鏂拌祫鏂欏簱鎸夐挳
    const addBtn = document.createElement('div');
    addBtn.className = 'list-item';
    addBtn.style.cssText = 'margin-top: 12px; color: var(--accent-color); border: 1px dashed var(--border-color); border-radius: 8px;';
    addBtn.innerHTML = `
        <i class="ri-add-line"></i>
        <span>娣诲姞鏂拌祫鏂欏簱</span>
    `;
    addBtn.addEventListener('click', showAddKnowledgeCategoryDialog);
    ui.navList.appendChild(addBtn);
}

function showAddKnowledgeCategoryDialog() {
    const modal = document.getElementById('modal-container');
    modal.classList.remove('hidden');
    modal.innerHTML = `
        <div style="position: fixed; top: 0; left: 0; right: 0; bottom: 0; background: rgba(0,0,0,0.6); display: flex; align-items: center; justify-content: center; z-index: 1000;">
            <div style="background: var(--bg-panel); border: 1px solid var(--border-color); border-radius: 16px; padding: 30px; width: 400px; max-width: 90%;">
                <h3 style="color: var(--text-primary); margin-bottom: 24px; font-size: 18px;">
                    <i class="ri-folder-add-line" style="margin-right: 8px;"></i>
                    娣诲姞鏂拌祫鏂欏簱
                </h3>
                
                <div style="margin-bottom: 20px;">
                    <label style="display: block; font-size: 13px; color: var(--text-secondary); margin-bottom: 8px;">璧勬枡搴撳悕绉?/label>
                    <input type="text" id="new-category-name" placeholder="渚嬪锛氬娍鍔涢樀钀ャ€佹妧鑳戒綋绯?.."
                        style="width: 100%; background: rgba(0,0,0,0.3); border: 1px solid var(--border-color); padding: 12px; color: var(--text-primary); border-radius: 8px; font-size: 14px;">
                </div>
                
                <div style="margin-bottom: 24px;">
                    <label style="display: block; font-size: 13px; color: var(--text-secondary); margin-bottom: 8px;">閫夋嫨鍥炬爣</label>
                    <div id="icon-picker" style="display: grid; grid-template-columns: repeat(8, 1fr); gap: 8px;">
                        ${['ri-folder-line', 'ri-bookmark-line', 'ri-flag-line', 'ri-star-line', 'ri-heart-line', 'ri-map-pin-line', 'ri-compass-line', 'ri-lightbulb-line',
                           'ri-magic-line', 'ri-gamepad-line', 'ri-sword-line', 'ri-shield-line', 'ri-vip-crown-line', 'ri-home-line', 'ri-building-line', 'ri-tree-line']
                            .map((icon, i) => `
                                <div class="icon-option ${i === 0 ? 'selected' : ''}" data-icon="${icon}"
                                    style="width: 36px; height: 36px; display: flex; align-items: center; justify-content: center; border: 2px solid ${i === 0 ? 'var(--accent-color)' : 'var(--border-color)'}; border-radius: 8px; cursor: pointer; transition: all 0.2s;">
                                    <i class="${icon}" style="font-size: 16px;"></i>
                                </div>
                            `).join('')}
                    </div>
                </div>
                
                <div style="display: flex; gap: 12px;">
                    <button id="cancel-add-category" style="flex: 1; padding: 12px; background: rgba(255,255,255,0.1); border: 1px solid var(--border-color); color: var(--text-primary); border-radius: 8px; cursor: pointer;">鍙栨秷</button>
                    <button id="confirm-add-category" style="flex: 1; padding: 12px; background: var(--accent-color); border: none; color: white; border-radius: 8px; cursor: pointer; font-weight: 600;">鍒涘缓</button>
                </div>
            </div>
        </div>
    `;
    
    let selectedIcon = 'ri-folder-line';
    
    // 鍥炬爣閫夋嫨
    modal.querySelectorAll('.icon-option').forEach(opt => {
        opt.addEventListener('click', () => {
            modal.querySelectorAll('.icon-option').forEach(o => {
                o.style.borderColor = 'var(--border-color)';
                o.classList.remove('selected');
            });
            opt.style.borderColor = 'var(--accent-color)';
            opt.classList.add('selected');
            selectedIcon = opt.dataset.icon;
        });
    });
    
    // 鍙栨秷
    document.getElementById('cancel-add-category').addEventListener('click', () => {
        modal.classList.add('hidden');
        modal.innerHTML = '';
    });
    
    // 纭
    document.getElementById('confirm-add-category').addEventListener('click', () => {
        const name = document.getElementById('new-category-name').value.trim();
        if (!name) {
            showToast('璇疯緭鍏ヨ祫鏂欏簱鍚嶇О', 'error');
            return;
        }
        
        addKnowledgeCategory(name, selectedIcon);
        modal.classList.add('hidden');
        modal.innerHTML = '';
    });
}

function addKnowledgeCategory(name, icon) {
    // 鐢熸垚鍞竴ID鍜宬ey
    const id = `db-custom-${Date.now()}`;
    const key = `custom_${Date.now()}`;
    
    // 娣诲姞鍒板垎绫诲垪琛?
    store.knowledgeCategories.push({
        id: id,
        key: key,
        name: name,
        icon: icon,
        builtin: false
    });
    
    // 鍒濆鍖栨暟鎹?
    store.projectData[key] = [];
    
    // 淇濆瓨鍒版湰鍦板瓨鍌?
    saveKnowledgeCategories();
    
    // 鍒锋柊瀵艰埅
    renderKnowledgeNavPanel();
    
    showToast(`璧勬枡搴撱€?{name}銆嶅垱寤烘垚鍔焋);
}

function deleteKnowledgeCategory(categoryId) {
    const category = store.knowledgeCategories.find(c => c.id === categoryId);
    if (!category) return;
    
    const count = (store.projectData[category.key] || []).length;
    
    if (confirm(`纭畾瑕佸垹闄よ祫鏂欏簱銆?{category.name}銆嶅悧锛焅n\n璇ュ垎绫讳笅鏈?${count} 鏉″唴瀹瑰皢琚竴骞跺垹闄わ紝姝ゆ搷浣滀笉鍙仮澶嶏紒`)) {
        // 鍒犻櫎鍒嗙被
        store.knowledgeCategories = store.knowledgeCategories.filter(c => c.id !== categoryId);
        
        // 鍒犻櫎鏁版嵁
        delete store.projectData[category.key];
        
        // 淇濆瓨
        saveKnowledgeCategories();
        
        // 鍒锋柊瀵艰埅
        renderKnowledgeNavPanel();
        showEmptyWorld();
        
        showToast(`璧勬枡搴撱€?{category.name}銆嶅凡鍒犻櫎`);
    }
}

function saveKnowledgeCategories() {
    // 鍙繚瀛樿嚜瀹氫箟鐨勫垎绫?
    const customCategories = store.knowledgeCategories.filter(c => !c.builtin);
    localStorage.setItem('custom_knowledge_categories', JSON.stringify(customCategories));
}

function loadKnowledgeCategories() {
    try {
        const saved = localStorage.getItem('custom_knowledge_categories');
        if (saved) {
            const customCategories = JSON.parse(saved);
            // 娣诲姞鍒板垎绫诲垪琛?
            customCategories.forEach(cat => {
                if (!store.knowledgeCategories.find(c => c.id === cat.id)) {
                    store.knowledgeCategories.push(cat);
                    // 鍒濆鍖栨暟鎹?
                    if (!store.projectData[cat.key]) {
                        store.projectData[cat.key] = [];
                    }
                }
            });
        }
    } catch (e) {
        console.error('Failed to load custom knowledge categories:', e);
    }
}

// ===== 绔犺妭绠＄悊鍔熻兘 =====

let currentEditingChapterIndex = null;
let autoSaveTimer = null;

function addNewChapter() {
    showAddChapterDialog();
}

function showAddChapterDialog() {
    const modal = document.getElementById('modal-container');
    modal.classList.remove('hidden');
    
    const chapters = store.projectData.outline || [];
    const nextChapterNum = chapters.length + 1;
    
    modal.innerHTML = `
        <div style="position: fixed; top: 0; left: 0; right: 0; bottom: 0; background: rgba(0,0,0,0.6); display: flex; align-items: center; justify-content: center; z-index: 1000;">
            <div style="background: var(--bg-panel); border: 1px solid var(--border-color); border-radius: 16px; padding: 30px; width: 500px; max-width: 90%;">
                <h3 style="color: var(--text-primary); margin-bottom: 24px; font-size: 18px;">
                    <i class="ri-file-add-line" style="margin-right: 8px;"></i>
                    娣诲姞鏂扮珷鑺?
                </h3>
                
                <div style="margin-bottom: 20px;">
                    <label style="display: block; font-size: 13px; color: var(--text-secondary); margin-bottom: 8px;">绔犺妭鏍囬</label>
                    <input type="text" id="new-chapter-title" placeholder="渚嬪锛氬垵鍏ユ睙婀栥€佸懡杩愪箣澶?.."
                        value="绗?{nextChapterNum}绔?
                        style="width: 100%; background: rgba(0,0,0,0.3); border: 1px solid var(--border-color); padding: 12px; color: var(--text-primary); border-radius: 8px; font-size: 14px;">
                </div>
                
                <div style="margin-bottom: 24px;">
                    <label style="display: block; font-size: 13px; color: var(--text-secondary); margin-bottom: 8px;">绔犺妭鎽樿 (鍙€?</label>
                    <textarea id="new-chapter-summary" rows="3" placeholder="绠€瑕佹弿杩版湰绔犱富瑕佸唴瀹?.."
                        style="width: 100%; background: rgba(0,0,0,0.3); border: 1px solid var(--border-color); padding: 12px; color: var(--text-primary); border-radius: 8px; font-size: 14px; resize: vertical;"></textarea>
                </div>
                
                <div style="display: flex; gap: 12px;">
                    <button id="cancel-add-chapter" style="flex: 1; padding: 12px; background: rgba(255,255,255,0.1); border: 1px solid var(--border-color); color: var(--text-primary); border-radius: 8px; cursor: pointer;">鍙栨秷</button>
                    <button id="confirm-add-chapter" style="flex: 1; padding: 12px; background: var(--accent-color); border: none; color: white; border-radius: 8px; cursor: pointer; font-weight: 600;">鍒涘缓绔犺妭</button>
                </div>
            </div>
        </div>
    `;
    
    // 鑷姩鑱氱劍杈撳叆妗嗗苟閫変腑鏂囨湰
    setTimeout(() => {
        const input = document.getElementById('new-chapter-title');
        input.focus();
        input.select();
    }, 100);
    
    // 鍙栨秷
    document.getElementById('cancel-add-chapter').addEventListener('click', () => {
        modal.classList.add('hidden');
        modal.innerHTML = '';
    });
    
    // 纭
    document.getElementById('confirm-add-chapter').addEventListener('click', () => {
        const title = document.getElementById('new-chapter-title').value.trim();
        const summary = document.getElementById('new-chapter-summary').value.trim();
        
        if (!title) {
            showToast('璇疯緭鍏ョ珷鑺傛爣棰?, 'error');
            return;
        }
        
        store.projectData.outline.push({
            title: title,
            summary: summary,
            content: '',
            created_at: new Date().toISOString()
        });
        saveOutlineData();
        renderNavPanel('write');
        
        modal.classList.add('hidden');
        modal.innerHTML = '';
        showToast(`绔犺妭銆?{title}銆嶅凡鍒涘缓`);
        
        // 鑷姩鎵撳紑鏂板垱寤虹殑绔犺妭
        openChapterEditor(store.projectData.outline.length - 1);
    });
    
    // 鍥炶溅纭
    document.getElementById('new-chapter-title').addEventListener('keydown', (e) => {
        if (e.key === 'Enter') {
            document.getElementById('confirm-add-chapter').click();
        }
    });
}

function editChapterTitle(index) {
    const chapter = store.projectData.outline[index];
    if (!chapter) return;

    const newTitle = prompt('淇敼绔犺妭鏍囬锛?, chapter.title);
    if (newTitle && newTitle.trim() && newTitle !== chapter.title) {
        store.projectData.outline[index].title = newTitle.trim();
        saveOutlineData();
        renderNavPanel('write'); // 鍒锋柊鍒楄〃锛屼紶鍏ユ纭殑妯″潡ID
        showToast('鏍囬宸叉洿鏂?);
    }
}

function deleteChapter(index) {
    const chapter = store.projectData.outline[index];
    if (!chapter) return;

    if (confirm(`纭畾瑕佸垹闄ゃ€岀${index + 1}绔?${chapter.title}銆嶅悧锛焅n\n姝ゆ搷浣滀笉鍙仮澶嶏紒`)) {
        store.projectData.outline.splice(index, 1);
        saveOutlineData();
        renderNavPanel('write'); // 鍒锋柊鍒楄〃锛屼紶鍏ユ纭殑妯″潡ID

        // 濡傛灉姝ｅ湪缂栬緫杩欎釜绔犺妭锛屾竻绌虹紪杈戝櫒
        if (currentEditingChapterIndex === index) {
            showEmptyEditor();
            currentEditingChapterIndex = null;
        }

        showToast('绔犺妭宸插垹闄?);
    }
}

function openChapterEditor(index) {
    const chapter = store.projectData.outline[index];
    if (!chapter) return;

    currentEditingChapterIndex = index;
    updateBreadcrumbs(['鍐欎綔', `绗?{index + 1}绔?${chapter.title}`]);

    const wordCount = (chapter.content || '').replace(/\s/g, '').length;

    ui.workspace.innerHTML = `
        <div class="editor-container" style="display: flex; flex-direction: column; height: 100%; padding: 24px;">
            <div class="editor-header" style="display: flex; align-items: center; gap: 16px; margin-bottom: 16px; padding-bottom: 16px; border-bottom: 1px solid var(--border-color);">
                <input type="text" id="chapter-title-input" class="title-input" value="${chapter.title || ''}" 
                    placeholder="绔犺妭鏍囬" style="flex: 1; background: transparent; border: none; font-size: 24px; font-weight: 600; color: var(--text-primary); outline: none;">
                <div style="display: flex; align-items: center; gap: 12px; color: var(--text-secondary); font-size: 13px;">
                    <span id="word-count">${wordCount} 瀛?/span>
                    <span id="save-status" style="color: #10b981;">宸蹭繚瀛?/span>
                </div>
                <button id="ai-continue-btn" style="padding: 8px 16px; background: linear-gradient(135deg, #8b5cf6, #6366f1); border: none; color: white; border-radius: 6px; cursor: pointer; font-weight: 500; margin-right: 8px;">
                    <i class="ri-magic-line"></i> AI缁啓
                </button>
                <button id="word-check-btn" style="padding: 8px 16px; background: rgba(255,255,255,0.1); border: 1px solid var(--border-color); color: var(--text-primary); border-radius: 6px; cursor: pointer; margin-right: 8px;">
                    <i class="ri-search-eye-line"></i> 璇嶆眹妫€娴?
                </button>
                <button id="save-chapter-btn" style="padding: 8px 20px; background: var(--accent-color); border: none; color: white; border-radius: 6px; cursor: pointer; font-weight: 500;">
                    <i class="ri-save-line"></i> 淇濆瓨
                </button>
            </div>
            <textarea id="chapter-content-input" class="body-input" placeholder="寮€濮嬪垱浣?.." 
                style="flex: 1; background: rgba(0,0,0,0.2); border: 1px solid var(--border-color); border-radius: 8px; padding: 20px; color: var(--text-primary); font-size: 16px; line-height: 1.8; resize: none; outline: none;">${chapter.content || ''}</textarea>
        </div>
    `;

    // 缁戝畾浜嬩欢
    const titleInput = document.getElementById('chapter-title-input');
    const contentInput = document.getElementById('chapter-content-input');
    const saveBtn = document.getElementById('save-chapter-btn');
    const wordCountEl = document.getElementById('word-count');
    const saveStatusEl = document.getElementById('save-status');

    // 鑷姩淇濆瓨
    const triggerAutoSave = () => {
        saveStatusEl.textContent = '淇濆瓨涓?..';
        saveStatusEl.style.color = 'var(--accent-color)';

        clearTimeout(autoSaveTimer);
        autoSaveTimer = setTimeout(() => {
            saveCurrentChapter();
            saveStatusEl.textContent = '宸蹭繚瀛?;
            saveStatusEl.style.color = '#10b981';
        }, 1000);
    };

    titleInput.addEventListener('input', triggerAutoSave);
    contentInput.addEventListener('input', () => {
        // 鏇存柊瀛楁暟
        const count = contentInput.value.replace(/\s/g, '').length;
        wordCountEl.textContent = `${count} 瀛梎;
        triggerAutoSave();
    });

    // AI缁啓鎸夐挳
    const aiContinueBtn = document.getElementById('ai-continue-btn');
    const wordCheckBtn = document.getElementById('word-check-btn');
    
    aiContinueBtn.addEventListener('click', async () => {
        const content = contentInput.value.trim();
        if (!content) {
            showToast('璇峰厛杈撳叆涓€浜涘唴瀹逛綔涓轰笂涓嬫枃', 'warning');
            return;
        }
        
        aiContinueBtn.disabled = true;
        aiContinueBtn.innerHTML = '<i class="ri-loader-4-line"></i> AI缁啓涓?..';
        
        try {
            const chapter = store.projectData.outline[currentEditingChapterIndex];
            const response = await apiCall('/api/chapter', 'POST', {
                chapter_index: currentEditingChapterIndex,
                chapter_title: chapter.title,
                existing_content: content,
                action: 'continue',
                word_count: 500  // 缁啓绾?00瀛?
            });
            
            if (response.content) {
                // 杩藉姞AI鐢熸垚鐨勫唴瀹?
                contentInput.value = content + '\n\n' + response.content;
                const newCount = contentInput.value.replace(/\s/g, '').length;
                wordCountEl.textContent = `${newCount} 瀛梎;
                saveCurrentChapter();
                showToast('AI缁啓瀹屾垚 鉁?);
            } else if (response.error) {
                showToast('AI缁啓澶辫触: ' + response.error, 'error');
            }
        } catch (e) {
            showToast('AI缁啓澶辫触: ' + e.message, 'error');
        } finally {
            aiContinueBtn.disabled = false;
            aiContinueBtn.innerHTML = '<i class="ri-magic-line"></i> AI缁啓';
        }
    });
    
    wordCheckBtn.addEventListener('click', () => {
        const content = contentInput.value.trim();
        if (!content) {
            showToast('璇峰厛杈撳叆闇€瑕佹娴嬬殑鍐呭', 'warning');
            return;
        }
        
        showWordCheckDialog(content, (newContent) => {
            contentInput.value = newContent;
            const newCount = newContent.replace(/\s/g, '').length;
            wordCountEl.textContent = `${newCount} 瀛梎;
            saveCurrentChapter();
        });
    });
    
    saveBtn.addEventListener('click', () => {
        clearTimeout(autoSaveTimer);
        saveCurrentChapter();
        saveStatusEl.textContent = '宸蹭繚瀛?;
        saveStatusEl.style.color = '#10b981';
        showToast('绔犺妭宸蹭繚瀛?);
    });
}

function saveCurrentChapter() {
    if (currentEditingChapterIndex === null) return;

    const titleInput = document.getElementById('chapter-title-input');
    const contentInput = document.getElementById('chapter-content-input');

    if (titleInput && contentInput) {
        store.projectData.outline[currentEditingChapterIndex].title = titleInput.value;
        store.projectData.outline[currentEditingChapterIndex].content = contentInput.value;
        store.projectData.outline[currentEditingChapterIndex].updated_at = new Date().toISOString();
        saveOutlineData();

        // 鏇存柊宸︿晶鍒楄〃涓殑鏍囬
        renderNavPanel('write'); // 鍒锋柊鍒楄〃锛屼紶鍏ユ纭殑妯″潡ID
    }
}

async function saveOutlineData() {
    try {
        await apiCall('/api/project-data/outline', 'POST', {
            data: store.projectData.outline
        });
    } catch (e) {
        console.error('Failed to save outline:', e);
    }
}

// ===== 璁惧畾绠＄悊鍔熻兘 =====

let currentSettingType = null;

function addNewSetting() {
    // 鏍规嵁褰撳墠閫変腑鐨勮祫鏂欏簱绫诲瀷娣诲姞
    const category = store.knowledgeCategories.find(c => c.id === currentSettingType);
    if (!category) {
        showToast('璇峰厛閫夋嫨涓€涓祫鏂欏簱绫诲埆', 'warning');
        return;
    }

    showAddSettingDialog(category);
}

function showAddSettingDialog(category) {
    const modal = document.getElementById('modal-container');
    modal.classList.remove('hidden');
    
    modal.innerHTML = `
        <div style="position: fixed; top: 0; left: 0; right: 0; bottom: 0; background: rgba(0,0,0,0.6); display: flex; align-items: center; justify-content: center; z-index: 1000;">
            <div style="background: var(--bg-panel); border: 1px solid var(--border-color); border-radius: 16px; padding: 30px; width: 500px; max-width: 90%;">
                <h3 style="color: var(--text-primary); margin-bottom: 24px; font-size: 18px;">
                    <i class="${category.icon}" style="margin-right: 8px;"></i>
                    娣诲姞${category.name}
                </h3>
                
                <div style="margin-bottom: 20px;">
                    <label style="display: block; font-size: 13px; color: var(--text-secondary); margin-bottom: 8px;">鍚嶇О <span style="color: #ef4444;">*</span></label>
                    <input type="text" id="new-setting-name" placeholder="渚嬪锛氭灄閫搁銆佷粰鐏靛墤..."
                        style="width: 100%; background: rgba(0,0,0,0.3); border: 1px solid var(--border-color); padding: 12px; color: var(--text-primary); border-radius: 8px; font-size: 14px;">
                </div>
                
                <div style="margin-bottom: 24px;">
                    <label style="display: block; font-size: 13px; color: var(--text-secondary); margin-bottom: 8px;">鎻忚堪</label>
                    <textarea id="new-setting-description" rows="4" placeholder="绠€瑕佹弿杩?.."
                        style="width: 100%; background: rgba(0,0,0,0.3); border: 1px solid var(--border-color); padding: 12px; color: var(--text-primary); border-radius: 8px; font-size: 14px; resize: vertical;"></textarea>
                </div>
                
                <div style="display: flex; gap: 12px;">
                    <button id="cancel-add-setting" style="flex: 1; padding: 12px; background: rgba(255,255,255,0.1); border: 1px solid var(--border-color); color: var(--text-primary); border-radius: 8px; cursor: pointer;">鍙栨秷</button>
                    <button id="confirm-add-setting" style="flex: 1; padding: 12px; background: var(--accent-color); border: none; color: white; border-radius: 8px; cursor: pointer; font-weight: 600;">鍒涘缓</button>
                </div>
            </div>
        </div>
    `;
    
    // 鑷姩鑱氱劍杈撳叆妗?
    setTimeout(() => {
        document.getElementById('new-setting-name').focus();
    }, 100);
    
    // 鍙栨秷
    document.getElementById('cancel-add-setting').addEventListener('click', () => {
        modal.classList.add('hidden');
        modal.innerHTML = '';
    });
    
    // 纭
    document.getElementById('confirm-add-setting').addEventListener('click', () => {
        const name = document.getElementById('new-setting-name').value.trim();
        const description = document.getElementById('new-setting-description').value.trim();
        
        if (!name) {
            showToast('璇疯緭鍏ュ悕绉?, 'error');
            return;
        }
        
        const newItem = {
            id: Date.now().toString(),
            name: name,
            description: description,
            created_at: new Date().toISOString()
        };

        if (!store.projectData[category.key]) {
            store.projectData[category.key] = [];
        }
        store.projectData[category.key].push(newItem);
        saveSettingData(category.key);
        
        modal.classList.add('hidden');
        modal.innerHTML = '';
        showToast(`銆?{name}銆嶅凡鍒涘缓`);
        
        // 鍒锋柊骞舵墦寮€缂栬緫鍣?
        loadDatabase(currentSettingType);
    });
    
    // 鍥炶溅纭
    document.getElementById('new-setting-name').addEventListener('keydown', (e) => {
        if (e.key === 'Enter') {
            document.getElementById('confirm-add-setting').click();
        }
    });
}

async function loadDatabase(typeId) {
    currentSettingType = typeId;

    // 浠庤祫鏂欏簱鍒嗙被涓煡鎵鹃厤缃?
    const category = store.knowledgeCategories.find(c => c.id === typeId);
    if (!category) return;

    updateBreadcrumbs(['璧勬枡搴?, category.name]);

    const data = store.projectData[category.key] || [];

    if (data.length === 0) {
        ui.workspace.innerHTML = `
            <div style="display: flex; flex-direction: column; align-items: center; justify-content: center; height: 100%; color: var(--text-secondary);">
                <i class="${category.icon}" style="font-size: 48px; opacity: 0.3; margin-bottom: 16px;"></i>
                <p>鏆傛棤${category.name}鍐呭</p>
                <button id="add-first-setting" style="margin-top: 20px; padding: 10px 24px; background: var(--accent-color); border: none; color: white; border-radius: 8px; cursor: pointer;">
                    <i class="ri-add-line"></i> 娣诲姞绗竴鏉?{category.name}
                </button>
            </div>
        `;
        document.getElementById('add-first-setting').addEventListener('click', addNewSetting);
        return;
    }

    ui.workspace.innerHTML = `
        <div style="padding: 24px;">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px;">
                <h2 style="color: var(--text-primary); font-size: 18px;">${category.name} (${data.length})</h2>
                <button id="add-new-item-btn" style="padding: 8px 16px; background: var(--accent-color); border: none; color: white; border-radius: 6px; cursor: pointer; font-size: 13px;">
                    <i class="ri-add-line"></i> 娣诲姞鏉＄洰
                </button>
            </div>
            <div class="card-grid" id="setting-grid" style="display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 16px;">
            </div>
        </div>
    `;

    document.getElementById('add-new-item-btn').addEventListener('click', addNewSetting);

    const grid = document.getElementById('setting-grid');

    data.forEach((item, index) => {
        const card = document.createElement('div');
        card.className = 'meta-card';
        card.style.cssText = 'padding: 20px; cursor: pointer; position: relative;';
        card.innerHTML = `
            <div style="display: flex; justify-content: space-between; align-items: start; margin-bottom: 12px;">
                <div style="font-weight: 600; font-size: 15px; color: var(--text-primary);">${item.name}</div>
                <div class="card-actions" style="display: flex; gap: 4px;">
                    <button class="edit-card-btn" title="缂栬緫" style="background: none; border: none; color: var(--text-secondary); cursor: pointer; padding: 4px;">
                        <i class="ri-edit-line"></i>
                    </button>
                    <button class="delete-card-btn" title="鍒犻櫎" style="background: none; border: none; color: #ef4444; cursor: pointer; padding: 4px;">
                        <i class="ri-delete-bin-line"></i>
                    </button>
                </div>
            </div>
            <div style="font-size: 13px; color: var(--text-secondary); line-height: 1.6; max-height: 60px; overflow: hidden;">
                ${item.description || '鏆傛棤鎻忚堪锛岀偣鍑荤紪杈戞坊鍔?}
            </div>
        `;

        card.addEventListener('click', (e) => {
            if (!e.target.closest('.card-actions')) {
                openSettingEditor(typeId, index);
            }
        });

        card.querySelector('.edit-card-btn').addEventListener('click', (e) => {
            e.stopPropagation();
            openSettingEditor(typeId, index);
        });

        card.querySelector('.delete-card-btn').addEventListener('click', (e) => {
            e.stopPropagation();
            deleteSetting(typeId, index);
        });

        grid.appendChild(card);
    });
}

function openSettingEditor(typeId, index) {
    // 浠庤祫鏂欏簱鍒嗙被涓煡鎵鹃厤缃?
    const category = store.knowledgeCategories.find(c => c.id === typeId);
    if (!category) return;

    const item = store.projectData[category.key][index];
    if (!item) return;

    updateBreadcrumbs(['璧勬枡搴?, category.name, item.name]);

    ui.workspace.innerHTML = `
        <div style="max-width: 800px; margin: 0 auto; padding: 24px;">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 24px;">
                <button id="back-to-list" style="background: none; border: none; color: var(--text-secondary); cursor: pointer; display: flex; align-items: center; gap: 8px;">
                    <i class="ri-arrow-left-line"></i> 杩斿洖鍒楄〃
                </button>
                <button id="save-setting-btn" style="padding: 8px 20px; background: var(--accent-color); border: none; color: white; border-radius: 6px; cursor: pointer;">
                    <i class="ri-save-line"></i> 淇濆瓨
                </button>
            </div>
            
            <div style="background: rgba(255,255,255,0.03); border: 1px solid var(--border-color); border-radius: 12px; padding: 24px;">
                <div style="margin-bottom: 20px;">
                    <label style="display: block; font-size: 12px; color: var(--text-secondary); margin-bottom: 8px;">鍚嶇О</label>
                    <input type="text" id="setting-name" value="${item.name || ''}"
                        style="width: 100%; background: rgba(0,0,0,0.2); border: 1px solid var(--border-color); padding: 12px; color: var(--text-primary); border-radius: 8px; font-size: 16px;">
                </div>
                
                <div style="margin-bottom: 20px;">
                    <label style="display: block; font-size: 12px; color: var(--text-secondary); margin-bottom: 8px;">鎻忚堪</label>
                    <textarea id="setting-description" rows="4"
                        style="width: 100%; background: rgba(0,0,0,0.2); border: 1px solid var(--border-color); padding: 12px; color: var(--text-primary); border-radius: 8px; font-size: 14px; resize: vertical;">${item.description || ''}</textarea>
                </div>
                
                <div>
                    <label style="display: block; font-size: 12px; color: var(--text-secondary); margin-bottom: 8px;">璇︾粏淇℃伅</label>
                    <textarea id="setting-details" rows="8" placeholder="鍦ㄨ繖閲屾坊鍔犳洿澶氳缁嗕俊鎭?.."
                        style="width: 100%; background: rgba(0,0,0,0.2); border: 1px solid var(--border-color); padding: 12px; color: var(--text-primary); border-radius: 8px; font-size: 14px; resize: vertical; line-height: 1.6;">${item.details || item.personality || item.properties || ''}</textarea>
                </div>
            </div>
        </div>
    `;

    document.getElementById('back-to-list').addEventListener('click', () => loadDatabase(typeId));

    document.getElementById('save-setting-btn').addEventListener('click', () => {
        const name = document.getElementById('setting-name').value;
        const description = document.getElementById('setting-description').value;
        const details = document.getElementById('setting-details').value;

        store.projectData[category.key][index].name = name;
        store.projectData[category.key][index].description = description;
        store.projectData[category.key][index].details = details;
        store.projectData[category.key][index].updated_at = new Date().toISOString();

        saveSettingData(category.key);
        showToast(`銆?{name}銆嶅凡淇濆瓨`);
        loadDatabase(typeId);
    });
}

function deleteSetting(typeId, index) {
    // 浠庤祫鏂欏簱鍒嗙被涓煡鎵鹃厤缃?
    const category = store.knowledgeCategories.find(c => c.id === typeId);
    if (!category) return;

    const item = store.projectData[category.key][index];
    if (!item) return;

    if (confirm(`纭畾瑕佸垹闄ゃ€?{item.name}銆嶅悧锛焋)) {
        store.projectData[category.key].splice(index, 1);
        saveSettingData(category.key);
        loadDatabase(typeId);
        showToast(`宸插垹闄);
    }
}

async function saveSettingData(dataKey) {
    // 鍒ゆ柇鏄惁鏄墿灞曡祫鏂欏簱锛堟湰鍦板瓨鍌級
    const builtinServerKeys = ['characters', 'outline', 'worldbuilding', 'items'];
    
    if (builtinServerKeys.includes(dataKey)) {
        // 鏈嶅姟鍣ㄥ瓨鍌?
        try {
            await apiCall(`/api/project-data/${dataKey}`, 'POST', {
                data: store.projectData[dataKey]
            });
        } catch (e) {
            console.error(`Failed to save ${dataKey}:`, e);
        }
    } else {
        // 鏈湴瀛樺偍锛堟墿灞曡祫鏂欏簱锛?
        saveExtendedKnowledgeData(dataKey);
    }
    
    // 鏇存柊@寮曠敤鏁版嵁
    updateMentionData();
}

// ===== IndexedDB 鑳屾櫙鍥剧墖瀛樺偍 =====

const DB_NAME = 'wensi_agent_db';
const DB_VERSION = 1;
const STORE_NAME = 'settings';

let dbInstance = null;

async function openDatabase() {
    if (dbInstance) return dbInstance;
    
    return new Promise((resolve, reject) => {
        const request = indexedDB.open(DB_NAME, DB_VERSION);
        
        request.onerror = () => reject(request.error);
        
        request.onsuccess = () => {
            dbInstance = request.result;
            resolve(dbInstance);
        };
        
        request.onupgradeneeded = (event) => {
            const db = event.target.result;
            if (!db.objectStoreNames.contains(STORE_NAME)) {
                db.createObjectStore(STORE_NAME, { keyPath: 'key' });
            }
        };
    });
}

async function saveToIndexedDB(key, value) {
    try {
        const db = await openDatabase();
        return new Promise((resolve, reject) => {
            const transaction = db.transaction([STORE_NAME], 'readwrite');
            const store = transaction.objectStore(STORE_NAME);
            const request = store.put({ key, value });
            request.onsuccess = () => resolve(true);
            request.onerror = () => reject(request.error);
        });
    } catch (e) {
        console.error('IndexedDB save error:', e);
        return false;
    }
}

async function loadFromIndexedDB(key) {
    try {
        const db = await openDatabase();
        return new Promise((resolve, reject) => {
            const transaction = db.transaction([STORE_NAME], 'readonly');
            const store = transaction.objectStore(STORE_NAME);
            const request = store.get(key);
            request.onsuccess = () => resolve(request.result?.value || null);
            request.onerror = () => reject(request.error);
        });
    } catch (e) {
        console.error('IndexedDB load error:', e);
        return null;
    }
}

async function deleteFromIndexedDB(key) {
    try {
        const db = await openDatabase();
        return new Promise((resolve, reject) => {
            const transaction = db.transaction([STORE_NAME], 'readwrite');
            const store = transaction.objectStore(STORE_NAME);
            const request = store.delete(key);
            request.onsuccess = () => resolve(true);
            request.onerror = () => reject(request.error);
        });
    } catch (e) {
        console.error('IndexedDB delete error:', e);
        return false;
    }
}

// ===== 涓婚鍜岃儗鏅缃?=====

// 5涓富棰橀厤缃?
const THEMES = {
    dark: {
        name: '娣辫壊',
        icon: '馃寵',
        bgMain: '#0a0a0f',
        bgPanel: 'rgba(255,255,255,0.03)',
        textPrimary: '#ffffff',
        textSecondary: 'rgba(255,255,255,0.6)',
        borderColor: 'rgba(255,255,255,0.08)',
        overlayColor: '10,10,15',
        overlayOpacity: 0.85
    },
    light: {
        name: '娴呰壊',
        icon: '鈽€锔?,
        bgMain: '#f8f9fa',
        bgPanel: 'rgba(255,255,255,0.9)',
        textPrimary: '#1a1a2e',
        textSecondary: '#666',
        borderColor: 'rgba(0,0,0,0.1)',
        overlayColor: '248,249,250',
        overlayOpacity: 0.9
    },
    green: {
        name: '缁胯壊鎶ょ溂',
        icon: '馃尶',
        bgMain: '#2d5a2d',
        bgPanel: 'rgba(200,230,200,0.12)',
        textPrimary: '#e8f5e8',
        textSecondary: 'rgba(200,230,200,0.8)',
        borderColor: 'rgba(200,230,200,0.2)',
        overlayColor: '60,110,60',
        overlayOpacity: 0.65
    },
    warm: {
        name: '鏆栭粍鎶ょ溂',
        icon: '馃寘',
        bgMain: '#3d3520',
        bgPanel: 'rgba(255,240,200,0.08)',
        textPrimary: '#f5e8c8',
        textSecondary: 'rgba(255,240,200,0.7)',
        overlayColor: '70,60,35',
        borderColor: 'rgba(255,240,200,0.15)',
        overlayOpacity: 0.75
    },
    blue: {
        name: '娴呰摑娓呮柊',
        icon: '馃拵',
        bgMain: '#2d4a6a',
        bgPanel: 'rgba(200,220,255,0.12)',
        textPrimary: '#e8f0ff',
        textSecondary: 'rgba(200,220,255,0.8)',
        borderColor: 'rgba(200,220,255,0.2)',
        overlayColor: '55,85,120',
        overlayOpacity: 0.65
    }
};

const THEME_ORDER = ['dark', 'light', 'green', 'warm', 'blue'];

function setTheme(themeKey, showMessage = true) {
    const theme = THEMES[themeKey];
    if (!theme) return;

    store.settings.theme = themeKey;
    localStorage.setItem('theme_mode', themeKey);

    // 鍙簲鐢ㄦ枃鏈拰闈㈡澘棰滆壊锛岃儗鏅敱hue鎺у埗
    applyThemeColors(themeKey);

    if (showMessage) {
        showToast(`宸插垏鎹㈠埌${theme.name}鏂囨湰妯″紡 ${theme.icon}`);
    }
}

function cycleTheme() {
    // 绠€鍖栦负娣辫壊/娴呰壊鍒囨崲
    const currentTheme = store.settings.theme || 'dark';
    const nextTheme = currentTheme === 'dark' ? 'light' : 'dark';
    setTheme(nextTheme);
}

// 鑾峰彇瀹夊叏鐨勪富棰樿缃€硷紙閬垮厤0鍊奸棶棰橈級
function getSafeSettingValue(value, defaultValue) {
    return (value !== undefined && value !== null && !isNaN(value)) ? value : defaultValue;
}

function updateThemeButton() {
    const themeKey = store.settings.theme || 'dark';
    const theme = THEMES[themeKey];
    const btn = document.getElementById('theme-cycle-btn');
    if (btn && theme) {
        btn.innerHTML = `${theme.icon} ${theme.name}`;
    }
}

function setBackgroundOpacity(opacity) {
    store.settings.bgOpacity = opacity;
    localStorage.setItem('theme_opacity', opacity);
    // 閲嶆柊搴旂敤瀹屾暣鐨勪富棰橀鑹?
    applyFullThemeFromHue(store.settings.accentHue || 250);
}

// 璁剧疆鑳屾櫙浜害锛?=绾粦锛?00=绾櫧锛?
function setBackgroundLightness(lightness) {
    store.settings.bgLightness = lightness;
    localStorage.setItem('theme_bg_lightness', lightness);
    applyFullThemeFromHue(store.settings.accentHue || 250);
}

// 璁剧疆鑳屾櫙鍥剧墖閫忔槑搴︼紙鐢ㄤ簬鍙犲姞灞傦級
function setOverlayOpacity(opacity) {
    store.settings.bgOpacity = opacity;
    localStorage.setItem('theme_opacity', opacity);
    applyFullThemeFromHue(store.settings.accentHue || 250);
}

// 鏍规嵁hue鍊艰缃畬鏁寸殑涓婚棰滆壊锛堣儗鏅?+ 闈㈡澘 + 寮鸿皟鑹诧級
function setBackgroundFromHue(hue) {
    store.settings.accentHue = hue;
    localStorage.setItem('theme_hue', hue);
    document.documentElement.style.setProperty('--primary-hue', hue);
    applyFullThemeFromHue(hue);
}

// 搴旂敤瀹屾暣鐨勪富棰橀鑹插埌鎵€鏈夊厓绱?
function applyFullThemeFromHue(hue) {
    // 浣跨敤鏄庣‘鐨勯粯璁ゅ€兼鏌ワ紝閬垮厤0鍊艰褰撲綔falsy
    const saturation = (store.settings.accentSaturation !== undefined && store.settings.accentSaturation !== null)
        ? store.settings.accentSaturation : 40;
    const bgLightness = (store.settings.bgLightness !== undefined && store.settings.bgLightness !== null)
        ? store.settings.bgLightness : 12;
    const overlayOpacity = (store.settings.bgOpacity !== undefined && store.settings.bgOpacity !== null)
        ? store.settings.bgOpacity : 0.85;
    const hasBgImage = !!store.settings.bgUrl;
    
    // 鍒ゆ柇鏄祬鑹茶繕鏄繁鑹叉ā寮?
    const isLightMode = bgLightness > 50;
    
    // 1. 璁剧疆涓昏儗鏅鐩栧眰
    const overlayEl = document.getElementById('app-overlay');
    if (overlayEl) {
        if (hasBgImage) {
            // 鏈夎儗鏅浘鐗囨椂锛屼娇鐢ㄩ€忔槑搴︽帶鍒跺彔鍔犲眰
            overlayEl.style.background = `hsla(${hue}, ${saturation}%, ${bgLightness}%, ${overlayOpacity})`;
        } else {
            // 鏃犺儗鏅浘鐗囨椂锛屼娇鐢ㄧ函鑹?
            overlayEl.style.background = `hsl(${hue}, ${saturation}%, ${bgLightness}%)`;
        }
    }
    
    // 2. 鏇存柊CSS鍙橀噺
    const panelSat = Math.min(saturation, 25);
    
    if (isLightMode) {
        // 娴呰壊妯″紡
        const panelLight = Math.min(bgLightness + 5, 98);
        const panelBg = `hsl(${hue}, ${panelSat}%, ${panelLight}%)`;
        const borderColor = `hsla(${hue}, ${Math.min(saturation, 15)}%, ${bgLightness - 20}%, 0.2)`;
        const workspaceBg = `hsla(${hue}, ${Math.min(saturation, 15)}%, ${bgLightness - 5}%, 0.3)`;
        
        document.documentElement.style.setProperty('--bg-panel', panelBg);
        document.documentElement.style.setProperty('--bg-workspace', workspaceBg);
        document.documentElement.style.setProperty('--border-color', borderColor);
        document.documentElement.style.setProperty('--bg-main', `hsl(${hue}, ${panelSat}%, ${bgLightness}%)`);
    } else {
        // 娣辫壊妯″紡
        const panelLight = Math.max(bgLightness - 2, 5);
        const panelBg = `hsla(${hue}, ${panelSat}%, ${panelLight}%, 0.95)`;
        const borderColor = `hsla(${hue}, ${Math.min(saturation, 20)}%, ${bgLightness + 15}%, 0.3)`;
        const workspaceBg = `hsla(${hue}, ${Math.min(saturation, 15)}%, ${Math.max(bgLightness - 4, 3)}%, 0.3)`;
        
        document.documentElement.style.setProperty('--bg-panel', panelBg);
        document.documentElement.style.setProperty('--bg-workspace', workspaceBg);
        document.documentElement.style.setProperty('--border-color', borderColor);
        document.documentElement.style.setProperty('--bg-main', `hsl(${hue}, ${panelSat}%, ${bgLightness}%)`);
    }
    
    // 寮鸿皟鑹?
    const accentSat = Math.max(saturation, 50);
    const accentLight = isLightMode ? 45 : 60;
    const accentColor = `hsl(${hue}, ${accentSat}%, ${accentLight}%)`;
    const accentHover = `hsl(${hue}, ${accentSat}%, ${accentLight - 10}%)`;
    
    document.documentElement.style.setProperty('--accent-color', accentColor);
    document.documentElement.style.setProperty('--accent-hover', accentHover);
    document.documentElement.style.setProperty('--primary-hue', hue);
    
    // 3. 搴旂敤瀛椾綋棰滆壊
    applyTextColor();
}

// 璁剧疆楗卞拰搴?
function setSaturation(saturation) {
    store.settings.accentSaturation = saturation;
    localStorage.setItem('theme_saturation', saturation);
    applyFullThemeFromHue(store.settings.accentHue || 250);
}

// 璁剧疆瀛椾綋浜害
function setTextLightness(lightness) {
    store.settings.textLightness = lightness;
    localStorage.setItem('theme_text_lightness', lightness);
    applyTextColor();
}

// 搴旂敤瀛椾綋棰滆壊
function applyTextColor() {
    const hue = (store.settings.accentHue !== undefined && store.settings.accentHue !== null)
        ? store.settings.accentHue : 250;
    const lightness = (store.settings.textLightness !== undefined && store.settings.textLightness !== null)
        ? store.settings.textLightness : 90;
    
    // 涓绘枃瀛楅鑹诧細鍩轰簬hue鐨勬祬鑹?
    const textPrimary = `hsl(${hue}, 15%, ${lightness}%)`;
    // 娆¤鏂囧瓧棰滆壊锛氱◢鏆椾竴浜?
    const textSecondary = `hsl(${hue}, 10%, ${Math.max(40, lightness - 30)}%)`;
    
    document.documentElement.style.setProperty('--text-primary', textPrimary);
    document.documentElement.style.setProperty('--text-secondary', textSecondary);
}

async function setAppBackground(url) {
    if (!url) return;

    const bgEl = document.getElementById('app-bg');
    if (bgEl) {
        bgEl.style.backgroundImage = `url('${url}')`;
        bgEl.style.backgroundSize = 'cover';
        bgEl.style.backgroundPosition = 'center';
        bgEl.style.backgroundRepeat = 'no-repeat';
        bgEl.style.opacity = '1';  // 纭繚鑳屾櫙鍥剧墖鍙
    }

    store.settings.bgUrl = url;
    
    // 娣诲姞body绫伙紝鍚敤渚ц竟鏍忛€忔槑鏁堟灉
    document.body.classList.add('has-bg-image');

    // 浣跨敤IndexedDB瀛樺偍澶у浘鐗囷紝localStorage浣滀负澶囩敤
    try {
        await saveToIndexedDB('theme_bg', url);
        console.log('[Background] 宸蹭繚瀛樺埌IndexedDB');
    } catch (e) {
        console.warn('IndexedDB save failed, trying localStorage:', e);
        // 闄嶇骇鍒發ocalStorage锛堝皬浜?MB鎵嶄繚瀛橈級
        if (url.length < 1000000) {
            try {
                localStorage.setItem('theme_bg', url);
            } catch (e2) {
                console.warn('Background image too large for localStorage');
            }
        }
    }

    // 鏈夎儗鏅浘鐗囨椂锛岄噸鏂板簲鐢ㄤ富棰樹互璋冩暣鍙犲姞灞傞€忔槑搴?
    applyFullThemeFromHue(store.settings.accentHue || 250);
    
    showToast('鑳屾櫙鍥剧墖宸插簲鐢紝璋冭妭銆屽彔鍔犲眰閫忔槑搴︺€嶆帶鍒跺浘鐗囨樉绀哄己搴?);
}

async function clearAppBackground() {
    const bgEl = document.getElementById('app-bg');
    if (bgEl) {
        bgEl.style.backgroundImage = '';
        bgEl.style.opacity = '0';
    }

    store.settings.bgUrl = '';
    
    // 娓呴櫎IndexedDB鍜宭ocalStorage涓殑鑳屾櫙鍥剧墖
    try {
        await deleteFromIndexedDB('theme_bg');
    } catch (e) {
        console.warn('Failed to delete from IndexedDB:', e);
    }
    localStorage.removeItem('theme_bg');
    
    // 绉婚櫎body绫伙紝鎭㈠渚ц竟鏍忓師鏈夋牱寮?
    document.body.classList.remove('has-bg-image');

    // 娓呯┖杈撳叆妗?
    const urlInput = document.getElementById('bg-url-input');
    if (urlInput) {
        urlInput.value = '';
    }

    // 閲嶆柊搴旂敤涓婚锛堟仮澶嶇函鑹茶儗鏅級
    applyFullThemeFromHue(store.settings.accentHue || 250);
    
    showToast('鑳屾櫙鍥剧墖宸叉竻闄?);
}

async function loadSavedSettings() {
    // 鍔犺浇寮鸿皟鑹诧紙浼樺厛鍔犺浇锛屽洜涓鸿儗鏅鑹蹭緷璧栦簬姝わ級
    const savedHue = localStorage.getItem('theme_hue');
    if (savedHue !== null && savedHue !== '') {
        const parsedHue = parseInt(savedHue);
        store.settings.accentHue = isNaN(parsedHue) ? 250 : parsedHue;
    } else {
        store.settings.accentHue = 250; // 榛樿鍊?
    }

    // 鍔犺浇楗卞拰搴?
    const savedSaturation = localStorage.getItem('theme_saturation');
    if (savedSaturation !== null && savedSaturation !== '') {
        const parsedSat = parseInt(savedSaturation);
        store.settings.accentSaturation = isNaN(parsedSat) ? 40 : parsedSat;
    } else {
        store.settings.accentSaturation = 40; // 榛樿鍊?
    }

    // 鍔犺浇鑳屾櫙浜害
    const savedBgLightness = localStorage.getItem('theme_bg_lightness');
    if (savedBgLightness !== null && savedBgLightness !== '') {
        const parsedBgLight = parseInt(savedBgLightness);
        store.settings.bgLightness = isNaN(parsedBgLight) ? 12 : parsedBgLight;
    } else {
        store.settings.bgLightness = 12; // 榛樿娣辫壊
    }

    // 鍔犺浇鑳屾櫙閫忔槑搴?
    const savedOpacity = localStorage.getItem('theme_opacity');
    if (savedOpacity !== null && savedOpacity !== '') {
        const parsedOpacity = parseFloat(savedOpacity);
        store.settings.bgOpacity = isNaN(parsedOpacity) ? 0.85 : parsedOpacity;
    } else {
        store.settings.bgOpacity = 0.85;
    }

    // 鍔犺浇瀛椾綋浜害
    const savedTextLightness = localStorage.getItem('theme_text_lightness');
    if (savedTextLightness !== null && savedTextLightness !== '') {
        const parsedTextLight = parseInt(savedTextLightness);
        store.settings.textLightness = isNaN(parsedTextLight) ? 90 : parsedTextLight;
    } else {
        store.settings.textLightness = 90; // 榛樿鍊?
    }

    console.log('[Theme] 鍔犺浇涓婚璁剧疆:', {
        hue: store.settings.accentHue,
        saturation: store.settings.accentSaturation,
        bgLightness: store.settings.bgLightness,
        bgOpacity: store.settings.bgOpacity,
        textLightness: store.settings.textLightness
    });

    // 搴旂敤瀹屾暣鐨勪富棰橀鑹诧紙鍩轰簬hue鍜宻aturation锛?
    applyFullThemeFromHue(store.settings.accentHue);

    // 浼樺厛浠嶪ndexedDB鍔犺浇鑳屾櫙鍥剧墖锛岀劧鍚庡皾璇昹ocalStorage
    let savedBg = null;
    try {
        savedBg = await loadFromIndexedDB('theme_bg');
        if (savedBg) {
            console.log('[Background] 浠嶪ndexedDB鍔犺浇鎴愬姛');
        }
    } catch (e) {
        console.warn('Failed to load from IndexedDB:', e);
    }
    
    // 濡傛灉IndexedDB娌℃湁锛屽皾璇昹ocalStorage
    if (!savedBg) {
        savedBg = localStorage.getItem('theme_bg');
        if (savedBg) {
            console.log('[Background] 浠巐ocalStorage鍔犺浇');
            // 杩佺Щ鍒癐ndexedDB
            try {
                await saveToIndexedDB('theme_bg', savedBg);
                localStorage.removeItem('theme_bg');
                console.log('[Background] 宸茶縼绉诲埌IndexedDB');
            } catch (e) {
                console.warn('Failed to migrate to IndexedDB:', e);
            }
        }
    }
    
    if (savedBg) {
        store.settings.bgUrl = savedBg;
        // 娣诲姞body绫伙紝鍚敤渚ц竟鏍忛€忔槑鏁堟灉
        document.body.classList.add('has-bg-image');
        // 寤惰繜璁剧疆鑳屾櫙鍥剧墖锛岀‘淇滵OM鍔犺浇瀹屾垚
        setTimeout(() => {
            const bgEl = document.getElementById('app-bg');
            if (bgEl) {
                bgEl.style.backgroundImage = `url('${savedBg}')`;
                bgEl.style.backgroundSize = 'cover';
                bgEl.style.backgroundPosition = 'center';
                bgEl.style.opacity = '1';
                console.log('[Background] 鑳屾櫙鍥剧墖宸插簲鐢?);
            }
            // 閲嶆柊搴旂敤涓婚浠ョ‘淇濆彔鍔犲眰姝ｇ‘鏄剧ず
            applyFullThemeFromHue(store.settings.accentHue);
        }, 100);
    }

    // 鍔犺浇涓婚妯″紡锛堜粎鐢ㄤ簬蹇€熷垏鎹㈡繁鑹?娴呰壊锛?
    const savedTheme = localStorage.getItem('theme_mode');
    store.settings.theme = (savedTheme === 'light') ? 'light' : 'dark';
}

// 蹇€熷垏鎹㈡繁鑹?娴呰壊妯″紡
function applyThemeColors(themeKey) {
    if (themeKey === 'light') {
        // 娴呰壊妯″紡锛氫綆浜害瀛椾綋锛堟繁鑹叉枃瀛楋級锛岄珮鑳屾櫙浜害
        store.settings.textLightness = 15;
        store.settings.bgLightness = 95;
        store.settings.bgOpacity = 0.1;
    } else {
        // 娣辫壊妯″紡锛氶珮浜害瀛椾綋锛堟祬鑹叉枃瀛楋級锛屼綆鑳屾櫙浜害
        store.settings.textLightness = 90;
        store.settings.bgLightness = 12;
        store.settings.bgOpacity = 0.85;
    }
    localStorage.setItem('theme_text_lightness', store.settings.textLightness);
    localStorage.setItem('theme_bg_lightness', store.settings.bgLightness);
    localStorage.setItem('theme_opacity', store.settings.bgOpacity);
    
    const hue = getSafeSettingValue(store.settings.accentHue, 250);
    applyFullThemeFromHue(hue);
}

// ===== 璁剧疆妯″潡 =====

function loadThemeSettings() {
    updateBreadcrumbs(['璁剧疆', '涓婚閰嶇疆']);

    // 浣跨敤鏄庣‘鐨勯粯璁ゅ€兼鏌ワ紝閬垮厤0鍊艰褰撲綔falsy
    const currentHue = (store.settings.accentHue !== undefined && store.settings.accentHue !== null)
        ? store.settings.accentHue : 250;
    const currentSat = (store.settings.accentSaturation !== undefined && store.settings.accentSaturation !== null)
        ? store.settings.accentSaturation : 40;
    const currentTextLight = (store.settings.textLightness !== undefined && store.settings.textLightness !== null)
        ? store.settings.textLightness : 90;
    const currentBgLight = (store.settings.bgLightness !== undefined && store.settings.bgLightness !== null)
        ? store.settings.bgLightness : 12;
    const currentOpacity = Math.round(((store.settings.bgOpacity !== undefined && store.settings.bgOpacity !== null)
        ? store.settings.bgOpacity : 0.85) * 100);
    const hasBgImage = !!store.settings.bgUrl;

    ui.workspace.innerHTML = `
        <div class="theme-settings-container" style="max-width: 900px; margin: 0 auto; padding: 30px 20px;">
            
            <!-- 椤甸潰鏍囬 -->
            <div style="text-align: center; margin-bottom: 40px;">
                <h1 style="font-size: 28px; color: var(--text-primary); margin-bottom: 10px;">馃帹 涓婚閰嶇疆涓績</h1>
                <p style="color: var(--text-secondary); font-size: 14px;">鑷畾涔夋偍鐨勪笓灞炲垱浣滅幆澧?/p>
            </div>
            
            <!-- 涓昏鍐呭鍖哄煙 - 涓ゆ爮甯冨眬 -->
            <div style="display: grid; grid-template-columns: 1fr 320px; gap: 30px; align-items: start;">
                
                <!-- 宸︿晶锛氶鑹茶皟鑺傚尯 -->
                <div style="display: flex; flex-direction: column; gap: 20px;">
                    
                    <!-- 鑳屾櫙鍥剧墖鍗＄墖 - 绉诲埌鏈€涓婇潰 -->
                    <div class="theme-card" style="background: var(--bg-panel); border: 1px solid var(--border-color); border-radius: 16px; padding: 24px;">
                        <div style="display: flex; align-items: center; gap: 10px; margin-bottom: 20px;">
                            <span style="font-size: 20px;">馃柤锔?/span>
                            <h3 style="font-size: 16px; color: var(--text-primary); margin: 0;">鑳屾櫙鍥剧墖</h3>
                            ${hasBgImage ? '<span style="font-size: 11px; background: #22c55e; color: white; padding: 2px 8px; border-radius: 10px;">宸插惎鐢?/span>' : ''}
                        </div>
                        
                        <div style="margin-bottom: 16px;">
                            <input type="file" id="bg-file-input" accept="image/*"
                                style="width: 100%; padding: 14px; background: rgba(128,128,128,0.1); border: 2px dashed var(--border-color); border-radius: 12px; color: var(--text-primary); cursor: pointer; font-size: 13px;">
                        </div>
                        
                        <div style="display: flex; gap: 10px; margin-bottom: 16px;">
                            <input type="text" id="bg-url-input"
                                style="flex: 1; background: rgba(128,128,128,0.15); border: 1px solid var(--border-color); padding: 12px 14px; color: var(--text-primary); border-radius: 10px; font-size: 13px;"
                                value="${store.settings.bgUrl || ''}" placeholder="杈撳叆鍥剧墖URL...">
                            <button id="apply-bg-btn" style="padding: 0 20px; background: var(--accent-color); border: none; color: white; border-radius: 10px; cursor: pointer; font-weight: 600; font-size: 13px;">搴旂敤</button>
                        </div>
                        
                        <!-- 鍙犲姞灞傞€忔槑搴︽帶鍒?-->
                        <div id="overlay-opacity-section" style="margin-bottom: 16px; padding: 16px; background: rgba(128,128,128,0.1); border-radius: 10px; ${hasBgImage ? '' : 'opacity: 0.5;'}">
                            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px;">
                                <label style="font-size: 13px; color: var(--text-secondary);">
                                    馃敳 鍙犲姞灞傞€忔槑搴?
                                    <span style="opacity: 0.6; font-size: 11px;">(瓒婁綆鍥剧墖瓒婃竻鏅?</span>
                                </label>
                                <span id="overlay-opacity-value" style="font-size: 13px; color: var(--accent-color); font-weight: 600;">${currentOpacity}%</span>
                            </div>
                            <input type="range" id="overlay-opacity-slider" min="0" max="100" value="${currentOpacity}"
                                style="width: 100%; height: 12px; -webkit-appearance: none; background: linear-gradient(to right, transparent, var(--bg-main)); border-radius: 6px; cursor: pointer;"
                                ${hasBgImage ? '' : 'disabled'}>
                            <p style="font-size: 11px; color: var(--text-secondary); margin-top: 8px; margin-bottom: 0;">
                                馃挕 璁剧疆鑳屾櫙鍥剧墖鍚庯紝璋冭妭姝ら」鎺у埗鍥剧墖鏄剧ず寮哄害銆?%=瀹屽叏鏄剧ず鍥剧墖锛?00%=瀹屽叏瑕嗙洊
                            </p>
                        </div>
                        
                        <button id="clear-bg-btn" style="width: 100%; padding: 12px; background: rgba(255,100,100,0.15); border: 1px solid rgba(255,100,100,0.4); color: #ff6b6b; border-radius: 10px; cursor: pointer; font-size: 13px;">娓呴櫎鑳屾櫙鍥剧墖</button>
                    </div>
                    
                    <!-- 蹇€熼璁惧崱鐗?-->
                    <div class="theme-card" style="background: var(--bg-panel); border: 1px solid var(--border-color); border-radius: 16px; padding: 24px;">
                        <div style="display: flex; align-items: center; gap: 10px; margin-bottom: 20px;">
                            <span style="font-size: 20px;">鈿?/span>
                            <h3 style="font-size: 16px; color: var(--text-primary); margin: 0;">蹇€熼璁?/h3>
                            <span style="font-size: 11px; color: var(--text-secondary);">(鏃犺儗鏅浘鐗囨椂浣跨敤)</span>
                        </div>
                        <div style="display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px;">
                            <button class="preset-btn" data-preset="black" style="padding: 16px 8px; background: linear-gradient(135deg, #0a0a0a, #1a1a1a); border: 2px solid rgba(255,255,255,0.15); color: white; border-radius: 12px; cursor: pointer; font-size: 13px; font-weight: 500; transition: all 0.2s;">
                                猬?绾粦
                            </button>
                            <button class="preset-btn" data-preset="white" style="padding: 16px 8px; background: linear-gradient(135deg, #ffffff, #f0f0f0); border: 2px solid rgba(0,0,0,0.15); color: #222; border-radius: 12px; cursor: pointer; font-size: 13px; font-weight: 500; transition: all 0.2s;">
                                猬?绾櫧
                            </button>
                            <button class="preset-btn" data-preset="dark" style="padding: 16px 8px; background: linear-gradient(135deg, hsl(250, 35%, 25%), hsl(250, 30%, 35%)); border: 2px solid rgba(255,255,255,0.1); color: white; border-radius: 12px; cursor: pointer; font-size: 13px; font-weight: 500; transition: all 0.2s;">
                                馃寵 娣辫摑
                            </button>
                            <button class="preset-btn" data-preset="green" style="padding: 16px 8px; background: linear-gradient(135deg, hsl(120, 30%, 28%), hsl(120, 25%, 38%)); border: 2px solid rgba(255,255,255,0.1); color: #b8e8b8; border-radius: 12px; cursor: pointer; font-size: 13px; font-weight: 500; transition: all 0.2s;">
                                馃尶 鎶ょ溂缁?
                            </button>
                        </div>
                        <div style="display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; margin-top: 12px;">
                            <button class="preset-btn" data-preset="warm" style="padding: 16px 8px; background: linear-gradient(135deg, hsl(35, 40%, 28%), hsl(35, 35%, 38%)); border: 2px solid rgba(255,255,255,0.1); color: #ffe4b5; border-radius: 12px; cursor: pointer; font-size: 13px; font-weight: 500; transition: all 0.2s;">
                                馃寘 鏆栭粍
                            </button>
                            <button class="preset-btn" data-preset="purple" style="padding: 16px 8px; background: linear-gradient(135deg, hsl(280, 35%, 30%), hsl(280, 30%, 40%)); border: 2px solid rgba(255,255,255,0.1); color: #e8d0f0; border-radius: 12px; cursor: pointer; font-size: 13px; font-weight: 500; transition: all 0.2s;">
                                馃挏 浼橀泤绱?
                            </button>
                            <button class="preset-btn" data-preset="red" style="padding: 16px 8px; background: linear-gradient(135deg, hsl(0, 40%, 30%), hsl(0, 35%, 40%)); border: 2px solid rgba(255,255,255,0.1); color: #ffc0c0; border-radius: 12px; cursor: pointer; font-size: 13px; font-weight: 500; transition: all 0.2s;">
                                鉂わ笍 鐑儏绾?
                            </button>
                            <button class="preset-btn" data-preset="cyan" style="padding: 16px 8px; background: linear-gradient(135deg, hsl(180, 35%, 28%), hsl(180, 30%, 38%)); border: 2px solid rgba(255,255,255,0.1); color: #b0f0f0; border-radius: 12px; cursor: pointer; font-size: 13px; font-weight: 500; transition: all 0.2s;">
                                馃寠 娓呮柊闈?
                            </button>
                        </div>
                    </div>
                    
                    <!-- 棰滆壊璋冭妭鍗＄墖 -->
                    <div class="theme-card" style="background: var(--bg-panel); border: 1px solid var(--border-color); border-radius: 16px; padding: 24px;">
                        <div style="display: flex; align-items: center; gap: 10px; margin-bottom: 24px;">
                            <span style="font-size: 20px;">馃帹</span>
                            <h3 style="font-size: 16px; color: var(--text-primary); margin: 0;">鑷畾涔夐鑹?/h3>
                        </div>
                        
                        <!-- 鑹茬浉閫夋嫨 -->
                        <div style="margin-bottom: 24px;">
                            <label style="display: block; font-size: 13px; color: var(--text-secondary); margin-bottom: 12px;">馃寛 鑹茬浉閫夋嫨</label>
                            <input type="range" id="accent-hue" min="0" max="360" value="${currentHue}"
                                style="width: 100%; height: 24px; -webkit-appearance: none; background: linear-gradient(to right,
                                    hsl(0, 85%, 55%), hsl(30, 85%, 55%), hsl(60, 85%, 55%), hsl(90, 85%, 55%),
                                    hsl(120, 85%, 55%), hsl(150, 85%, 55%), hsl(180, 85%, 55%), hsl(210, 85%, 55%),
                                    hsl(240, 85%, 55%), hsl(270, 85%, 55%), hsl(300, 85%, 55%), hsl(330, 85%, 55%), hsl(360, 85%, 55%));
                                border-radius: 12px; cursor: pointer;">
                            <div style="display: flex; justify-content: space-between; margin-top: 6px; font-size: 10px; color: var(--text-secondary);">
                                <span>绾?/span><span>姗?/span><span>榛?/span><span>缁?/span><span>闈?/span><span>钃?/span><span>绱?/span><span>绮?/span>
                            </div>
                        </div>
                        
                        <!-- 楗卞拰搴?-->
                        <div style="margin-bottom: 24px;">
                            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px;">
                                <label style="font-size: 13px; color: var(--text-secondary);">馃帤锔?棰滆壊楗卞拰搴?<span style="opacity: 0.6;">(0=榛戠櫧鐏?</span></label>
                                <span id="saturation-value" style="font-size: 13px; color: var(--accent-color); font-weight: 600;">${currentSat}%</span>
                            </div>
                            <input type="range" id="saturation-slider" min="0" max="100" value="${currentSat}"
                                style="width: 100%; height: 16px; -webkit-appearance: none; background: linear-gradient(to right,
                                    hsl(${currentHue}, 0%, 50%), hsl(${currentHue}, 50%, 50%), hsl(${currentHue}, 100%, 50%));
                                border-radius: 8px; cursor: pointer;">
                        </div>
                        
                        <!-- 鑳屾櫙浜害锛堟牳蹇冩帶鍒讹級 -->
                        <div style="margin-bottom: 24px;">
                            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px;">
                                <label style="font-size: 13px; color: var(--text-secondary);">鈽€锔?鑳屾櫙浜害 <span style="opacity: 0.6;">(0=榛?100=鐧?</span></label>
                                <span id="bg-lightness-value" style="font-size: 13px; color: var(--accent-color); font-weight: 600;">${currentBgLight}%</span>
                            </div>
                            <input type="range" id="bg-lightness-slider" min="0" max="100" value="${currentBgLight}"
                                style="width: 100%; height: 16px; -webkit-appearance: none; background: linear-gradient(to right, #000000, #888888, #ffffff); border-radius: 8px; cursor: pointer;">
                        </div>
                        
                        <!-- 瀛椾綋浜害 -->
                        <div>
                            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px;">
                                <label style="font-size: 13px; color: var(--text-secondary);">鉁忥笍 瀛椾綋浜害</label>
                                <span id="text-lightness-value" style="font-size: 13px; color: var(--accent-color); font-weight: 600;">${currentTextLight}%</span>
                            </div>
                            <input type="range" id="text-lightness-slider" min="0" max="100" value="${currentTextLight}"
                                style="width: 100%; height: 12px; -webkit-appearance: none; background: linear-gradient(to right, #000000, #ffffff); border-radius: 6px; cursor: pointer;">
                        </div>
                    </div>
                </div>
                
                <!-- 鍙充晶锛氬疄鏃堕瑙堝尯 -->
                <div style="position: sticky; top: 30px;">
                    <div class="theme-card" style="background: var(--bg-panel); border: 1px solid var(--border-color); border-radius: 16px; padding: 24px;">
                        <div style="display: flex; align-items: center; gap: 10px; margin-bottom: 20px;">
                            <span style="font-size: 20px;">馃憗锔?/span>
                            <h3 style="font-size: 16px; color: var(--text-primary); margin: 0;">瀹炴椂棰勮</h3>
                        </div>
                        
                        <!-- 棰滆壊棰勮鍧?-->
                        <div id="theme-preview-box" style="width: 100%; height: 120px; border-radius: 12px; background: hsl(${currentHue}, ${currentSat}%, ${currentBgLight}%); margin-bottom: 20px; display: flex; align-items: center; justify-content: center; box-shadow: 0 8px 24px rgba(0,0,0,0.2); border: 1px solid rgba(128,128,128,0.3);">
                            <span style="font-size: 32px;">鉁?/span>
                        </div>
                        
                        <!-- 棰滆壊淇℃伅 -->
                        <div style="background: rgba(128,128,128,0.1); border-radius: 10px; padding: 16px; margin-bottom: 16px;">
                            <div style="display: flex; justify-content: space-between; margin-bottom: 8px;">
                                <span style="color: var(--text-secondary); font-size: 12px;">鑹茬浉 (Hue)</span>
                                <span id="preview-hue" style="color: var(--text-primary); font-size: 12px; font-weight: 600;">${currentHue}掳</span>
                            </div>
                            <div style="display: flex; justify-content: space-between; margin-bottom: 8px;">
                                <span style="color: var(--text-secondary); font-size: 12px;">楗卞拰搴?(Sat)</span>
                                <span id="preview-sat" style="color: var(--text-primary); font-size: 12px; font-weight: 600;">${currentSat}%</span>
                            </div>
                            <div style="display: flex; justify-content: space-between; margin-bottom: 8px;">
                                <span style="color: var(--text-secondary); font-size: 12px;">鑳屾櫙浜害</span>
                                <span id="preview-bg-light" style="color: var(--text-primary); font-size: 12px; font-weight: 600;">${currentBgLight}%</span>
                            </div>
                            <div style="display: flex; justify-content: space-between;">
                                <span style="color: var(--text-secondary); font-size: 12px;">瀛椾綋浜害</span>
                                <span id="preview-text-light" style="color: var(--text-primary); font-size: 12px; font-weight: 600;">${currentTextLight}%</span>
                            </div>
                        </div>
                        
                        <!-- 鏂囧瓧棰勮 -->
                        <div style="background: rgba(128,128,128,0.08); border-radius: 10px; padding: 16px;">
                            <p style="color: var(--text-primary); font-size: 14px; margin-bottom: 8px; font-weight: 500;">涓昏鏂囧瓧鏁堟灉</p>
                            <p style="color: var(--text-secondary); font-size: 12px; margin: 0;">娆¤鏂囧瓧鏁堟灉绀轰緥</p>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    `;

    // 鏇存柊棰勮鐨勮緟鍔╁嚱鏁?
    function updateAllPreviews() {
        const hue = (store.settings.accentHue !== undefined && store.settings.accentHue !== null)
            ? store.settings.accentHue : 250;
        const sat = (store.settings.accentSaturation !== undefined && store.settings.accentSaturation !== null)
            ? store.settings.accentSaturation : 40;
        const bgLight = (store.settings.bgLightness !== undefined && store.settings.bgLightness !== null)
            ? store.settings.bgLightness : 12;
        const textLight = (store.settings.textLightness !== undefined && store.settings.textLightness !== null)
            ? store.settings.textLightness : 90;
        
        // 鏇存柊棰勮鍧楅鑹?
        document.getElementById('theme-preview-box').style.background = `hsl(${hue}, ${sat}%, ${bgLight}%)`;
        
        // 鏇存柊楗卞拰搴︽粦鍧楄儗鏅?
        document.getElementById('saturation-slider').style.background =
            `linear-gradient(to right, hsl(${hue}, 0%, 50%), hsl(${hue}, 50%, 50%), hsl(${hue}, 100%, 50%))`;
        
        // 鏇存柊淇℃伅鏄剧ず
        document.getElementById('preview-hue').textContent = `${hue}掳`;
        document.getElementById('preview-sat').textContent = `${sat}%`;
        document.getElementById('preview-bg-light').textContent = `${bgLight}%`;
        document.getElementById('preview-text-light').textContent = `${textLight}%`;
    }

    // 棰勮閰嶇疆 - 浣跨敤鑳屾櫙浜害鑰岄潪閫忔槑搴?
    const presets = {
        black: { hue: 0, sat: 0, bgLight: 5, textLight: 92 },      // 绾粦
        white: { hue: 0, sat: 0, bgLight: 97, textLight: 12 },     // 绾櫧
        dark: { hue: 250, sat: 30, bgLight: 18, textLight: 90 },   // 娣辫摑
        green: { hue: 120, sat: 25, bgLight: 22, textLight: 88 },  // 鎶ょ溂缁?
        warm: { hue: 35, sat: 30, bgLight: 22, textLight: 88 },    // 鏆栭粍
        purple: { hue: 280, sat: 28, bgLight: 22, textLight: 88 }, // 浼橀泤绱?
        red: { hue: 0, sat: 32, bgLight: 22, textLight: 88 },      // 鐑儏绾?
        cyan: { hue: 180, sat: 28, bgLight: 22, textLight: 88 }    // 娓呮柊闈?
    };

    const presetNames = {
        black: '绾粦', white: '绾櫧', dark: '娣辫摑', green: '鎶ょ溂缁?,
        warm: '鏆栭粍', purple: '浼橀泤绱?, red: '鐑儏绾?, cyan: '娓呮柊闈?
    };

    // 缁戝畾蹇€熼璁炬寜閽?
    document.querySelectorAll('.preset-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            const preset = btn.dataset.preset;
            const config = presets[preset];
            if (!config) return;
            
            store.settings.accentHue = config.hue;
            store.settings.accentSaturation = config.sat;
            store.settings.bgLightness = config.bgLight;
            store.settings.textLightness = config.textLight;
            
            // 淇濆瓨璁剧疆
            localStorage.setItem('theme_hue', config.hue);
            localStorage.setItem('theme_saturation', config.sat);
            localStorage.setItem('theme_bg_lightness', config.bgLight);
            localStorage.setItem('theme_text_lightness', config.textLight);
            
            // 鏇存柊婊戝潡
            document.getElementById('accent-hue').value = config.hue;
            document.getElementById('saturation-slider').value = config.sat;
            document.getElementById('saturation-value').textContent = `${config.sat}%`;
            document.getElementById('bg-lightness-slider').value = config.bgLight;
            document.getElementById('bg-lightness-value').textContent = `${config.bgLight}%`;
            document.getElementById('text-lightness-slider').value = config.textLight;
            document.getElementById('text-lightness-value').textContent = `${config.textLight}%`;
            
            // 搴旂敤涓婚
            applyFullThemeFromHue(config.hue);
            updateAllPreviews();
            
            showToast(`宸插簲鐢ㄣ€?{presetNames[preset]}銆嶄富棰榒);
        });
    });

    // 缁戝畾鑹茬浉婊戝潡
    document.getElementById('accent-hue').addEventListener('input', (e) => {
        const hue = parseInt(e.target.value);
        store.settings.accentHue = hue;
        localStorage.setItem('theme_hue', hue);
        applyFullThemeFromHue(hue);
        updateAllPreviews();
    });

    // 缁戝畾楗卞拰搴︽粦鍧?
    document.getElementById('saturation-slider').addEventListener('input', (e) => {
        const sat = parseInt(e.target.value);
        document.getElementById('saturation-value').textContent = `${sat}%`;
        setSaturation(sat);
        updateAllPreviews();
    });

    // 缁戝畾鑳屾櫙浜害婊戝潡
    document.getElementById('bg-lightness-slider').addEventListener('input', (e) => {
        const lightness = parseInt(e.target.value);
        document.getElementById('bg-lightness-value').textContent = `${lightness}%`;
        setBackgroundLightness(lightness);
        updateAllPreviews();
    });

    // 缁戝畾瀛椾綋浜害婊戝潡
    document.getElementById('text-lightness-slider').addEventListener('input', (e) => {
        const lightness = parseInt(e.target.value);
        document.getElementById('text-lightness-value').textContent = `${lightness}%`;
        setTextLightness(lightness);
        updateAllPreviews();
    });

    // 缁戝畾鍙犲姞灞傞€忔槑搴︽粦鍧?
    document.getElementById('overlay-opacity-slider').addEventListener('input', (e) => {
        const opacity = parseInt(e.target.value) / 100;
        document.getElementById('overlay-opacity-value').textContent = `${e.target.value}%`;
        setOverlayOpacity(opacity);
    });

    // 缁戝畾鑳屾櫙鍥剧墖鎸夐挳
    document.getElementById('apply-bg-btn').addEventListener('click', () => {
        const url = document.getElementById('bg-url-input').value.trim();
        if (url) {
            setAppBackground(url);
            // 鍚敤閫忔槑搴︽粦鍧?
            document.getElementById('overlay-opacity-section').style.opacity = '1';
            document.getElementById('overlay-opacity-slider').disabled = false;
            // 鍒锋柊椤甸潰浠ユ洿鏂?宸插惎鐢?鏍囪
            setTimeout(() => loadThemeSettings(), 300);
        }
    });

    document.getElementById('bg-file-input').addEventListener('change', (e) => {
        const file = e.target.files[0];
        if (file) {
            const reader = new FileReader();
            reader.onload = (event) => {
                setAppBackground(event.target.result);
                // 鍚敤閫忔槑搴︽粦鍧?
                document.getElementById('overlay-opacity-section').style.opacity = '1';
                document.getElementById('overlay-opacity-slider').disabled = false;
                // 鍒锋柊椤甸潰浠ユ洿鏂?宸插惎鐢?鏍囪
                setTimeout(() => loadThemeSettings(), 300);
            };
            reader.readAsDataURL(file);
        }
    });

    document.getElementById('clear-bg-btn').addEventListener('click', () => {
        clearAppBackground();
        // 绂佺敤閫忔槑搴︽粦鍧?
        document.getElementById('overlay-opacity-section').style.opacity = '0.5';
        document.getElementById('overlay-opacity-slider').disabled = true;
        // 鍒锋柊椤甸潰浠ョЩ闄?宸插惎鐢?鏍囪
        setTimeout(() => loadThemeSettings(), 300);
    });
}

// ===== 鍏ㄥ眬API閰嶇疆 =====

async function loadGlobalAPISettings() {
    updateBreadcrumbs(['璁剧疆', '鍏ㄥ眬API閰嶇疆']);
    
    ui.workspace.innerHTML = `
        <div style="max-width: 700px; margin: 40px auto; padding: 0 20px;">
            <h2 style="margin-bottom: 16px; color: var(--text-primary);">馃寪 鍏ㄥ眬API閰嶇疆</h2>
            <p style="color: var(--text-secondary); margin-bottom: 24px; line-height: 1.6;">
                閰嶇疆榛樿鐨凙PI鏈嶅姟锛屾墍鏈堿gent灏嗚嚜鍔ㄤ娇鐢ㄦ閰嶇疆锛堥櫎闈炲崟鐙厤缃級銆?
                <br>鏀寔OpenAI鍙婃墍鏈夊吋瀹筄penAI v1鎺ュ彛鐨勬湇鍔°€?
            </p>
            
            <div id="global-api-status" style="margin-bottom: 24px; padding: 16px; background: rgba(255,255,255,0.03); border: 1px solid var(--border-color); border-radius: 12px;">
                <div style="display: flex; align-items: center; gap: 12px;">
                    <div id="global-status-indicator" style="width: 12px; height: 12px; border-radius: 50%; background: #666;"></div>
                    <span id="global-status-text" style="color: var(--text-secondary);">妫€鏌ラ厤缃姸鎬?..</span>
                </div>
            </div>
            
            <div style="background: rgba(255,255,255,0.03); border: 1px solid var(--border-color); border-radius: 12px; padding: 24px; margin-bottom: 24px;">
                <div style="margin-bottom: 20px;">
                    <label style="display: block; font-size: 12px; margin-bottom: 8px; color: var(--text-secondary);">
                        API 鍦板潃 <span style="color: #ef4444;">*</span>
                    </label>
                    <input type="text" id="global-api-base" placeholder="https://api.openai.com/v1"
                        style="width: 100%; background: rgba(0,0,0,0.3); border: 1px solid var(--border-color); padding: 12px; color: white; border-radius: 8px; font-size: 14px;">
                    <p style="font-size: 11px; color: var(--text-secondary); margin-top: 6px;">
                        鏀寔: OpenAI銆丏eepSeek銆丆laude銆佹湰鍦癘llama绛夊吋瀹规帴鍙?
                    </p>
                </div>
                
                <div style="margin-bottom: 20px;">
                    <label style="display: block; font-size: 12px; margin-bottom: 8px; color: var(--text-secondary);">
                        API 瀵嗛挜 <span style="color: #ef4444;">*</span>
                    </label>
                    <input type="password" id="global-api-key" placeholder="sk-..."
                        style="width: 100%; background: rgba(0,0,0,0.3); border: 1px solid var(--border-color); padding: 12px; color: white; border-radius: 8px; font-size: 14px;">
                </div>
                
                <div style="margin-bottom: 20px;">
                    <label style="display: block; font-size: 12px; margin-bottom: 8px; color: var(--text-secondary);">
                        榛樿妯″瀷 <span style="color: #ef4444;">*</span>
                    </label>
                    <div style="display: flex; gap: 8px;">
                        <input type="text" id="global-model" placeholder="gpt-4"
                            style="flex: 1; background: rgba(0,0,0,0.3); border: 1px solid var(--border-color); padding: 12px; color: white; border-radius: 8px; font-size: 14px;">
                        <button id="fetch-global-models" style="padding: 12px 20px; background: rgba(255,255,255,0.1); border: 1px solid var(--border-color); color: var(--text-primary); border-radius: 8px; cursor: pointer; white-space: nowrap;">
                            <i class="ri-download-cloud-line"></i> 鑾峰彇妯″瀷鍒楄〃
                        </button>
                    </div>
                    <div id="global-model-list" style="display: none; margin-top: 8px; background: rgba(0,0,0,0.3); border: 1px solid var(--border-color); border-radius: 8px;">
                        <input type="text" id="global-model-search" placeholder="馃攳 杈撳叆鍏抽敭璇嶈繃婊ゆā鍨?(濡?gpt, claude, gemini...)"
                            style="width: 100%; padding: 10px 12px; background: rgba(255,255,255,0.05); border: none; border-bottom: 1px solid var(--border-color); color: var(--text-primary); font-size: 13px; outline: none;">
                        <div id="global-model-items" style="max-height: 250px; overflow-y: auto;"></div>
                    </div>
                </div>
                
                <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 16px; margin-bottom: 20px;">
                    <div>
                        <label style="display: block; font-size: 12px; margin-bottom: 8px; color: var(--text-secondary);">娓╁害 (Temperature)</label>
                        <input type="number" id="global-temperature" value="0.7" min="0" max="2" step="0.1"
                            style="width: 100%; background: rgba(0,0,0,0.3); border: 1px solid var(--border-color); padding: 12px; color: white; border-radius: 8px; font-size: 14px;">
                    </div>
                    <div>
                        <label style="display: block; font-size: 12px; margin-bottom: 8px; color: var(--text-secondary);">鏈€澶oken鏁?/label>
                        <input type="number" id="global-max-tokens" value="4096" min="100" max="128000"
                            style="width: 100%; background: rgba(0,0,0,0.3); border: 1px solid var(--border-color); padding: 12px; color: white; border-radius: 8px; font-size: 14px;">
                    </div>
                </div>
                
                <div style="display: flex; gap: 12px; margin-bottom: 16px;">
                    <button id="test-global-connection" style="flex: 1; padding: 14px; background: rgba(255,255,255,0.1); border: 1px solid var(--border-color); color: var(--text-primary); border-radius: 8px; cursor: pointer; font-weight: 500; font-size: 15px;">
                        馃敆 娴嬭瘯杩炴帴
                    </button>
                    <button id="save-global-config" style="flex: 1; padding: 14px; background: var(--accent-color); border: none; color: white; border-radius: 8px; cursor: pointer; font-weight: 600; font-size: 15px;">
                        馃捑 淇濆瓨鍏ㄥ眬閰嶇疆
                    </button>
                </div>
                
                <div id="test-result-area" style="display: none; padding: 16px; border-radius: 8px; margin-top: 12px;"></div>
            </div>
            
            <div style="background: rgba(100,180,255,0.1); border: 1px solid rgba(100,180,255,0.3); border-radius: 12px; padding: 20px;">
                <h3 style="margin-bottom: 12px; font-size: 14px; color: #7dd3fc;">馃挕 閰嶇疆璇存槑</h3>
                <ul style="font-size: 13px; color: var(--text-secondary); line-height: 1.8; padding-left: 20px; margin: 0;">
                    <li>鍏ㄥ眬閰嶇疆灏嗕綔涓烘墍鏈堿gent鐨?strong>榛樿閰嶇疆</strong></li>
                    <li>鍗曚釜Agent鍙互閫夋嫨銆屼娇鐢ㄥ叏灞€閰嶇疆銆嶆垨鑷畾涔夐厤缃?/li>
                    <li>鏈厤缃叏灞€API鏃讹紝闇€瑕佷负姣忎釜Agent鍗曠嫭閰嶇疆</li>
                    <li>鎺ㄨ崘鍏堥厤缃叏灞€API锛岀劧鍚庢寜闇€涓虹壒瀹欰gent瀹氬埗</li>
                </ul>
            </div>
        </div>
    `;
    
    // 鍔犺浇褰撳墠閰嶇疆
    try {
        const config = await apiCall('/api/global-config', 'GET');
        
        // 鏇存柊鐘舵€佹寚绀哄櫒
        const indicator = document.getElementById('global-status-indicator');
        const statusText = document.getElementById('global-status-text');
        
        if (config.is_configured) {
            indicator.style.background = '#22c55e';
            statusText.textContent = '鉁?鍏ㄥ眬API宸查厤缃?;
            statusText.style.color = '#22c55e';
        } else {
            indicator.style.background = '#f59e0b';
            statusText.textContent = '鈿?鍏ㄥ眬API鏈厤缃紝璇峰～鍐欎互涓嬩俊鎭?;
            statusText.style.color = '#f59e0b';
        }
        
        // 濉厖琛ㄥ崟
        document.getElementById('global-api-base').value = config.api_base || '';
        document.getElementById('global-api-key').value = config.api_key_set ? '鈥⑩€⑩€⑩€⑩€⑩€⑩€⑩€? : '';
        document.getElementById('global-model').value = config.model || '';
        document.getElementById('global-temperature').value = config.temperature || 0.7;
        document.getElementById('global-max-tokens').value = config.max_tokens || 4096;
        
    } catch (e) {
        document.getElementById('global-status-indicator').style.background = '#ef4444';
        document.getElementById('global-status-text').textContent = '鍔犺浇閰嶇疆澶辫触: ' + e.message;
    }
    
    // 鑾峰彇妯″瀷鍒楄〃锛堝甫鎼滅储杩囨护鍔熻兘锛?
    let allGlobalModels = [];
    
    document.getElementById('fetch-global-models').addEventListener('click', async () => {
        const btn = document.getElementById('fetch-global-models');
        const baseUrl = document.getElementById('global-api-base').value.trim();
        const apiKey = document.getElementById('global-api-key').value.trim();
        const modelList = document.getElementById('global-model-list');
        const modelItems = document.getElementById('global-model-items');
        const modelInput = document.getElementById('global-model');
        const searchInput = document.getElementById('global-model-search');
        
        if (!baseUrl) {
            showToast('璇峰厛濉啓API鍦板潃', 'error');
            return;
        }
        
        btn.innerHTML = '<i class="ri-loader-4-line"></i> 鑾峰彇涓?..';
        btn.disabled = true;
        
        try {
            const res = await apiCall('/api/fetch-models', 'POST', {
                api_base: baseUrl,
                api_key: apiKey === '鈥⑩€⑩€⑩€⑩€⑩€⑩€⑩€? ? '' : apiKey
            });
            
            if (res.success && res.models.length > 0) {
                allGlobalModels = res.models;
                modelList.style.display = 'block';
                searchInput.value = '';
                
                // 甯哥敤妯″瀷浼樺厛鏄剧ず
                const priorityKeywords = ['gpt-4', 'gpt-3.5', 'claude', 'gemini', 'deepseek', 'qwen', 'glm'];
                
                // 娓叉煋妯″瀷鍒楄〃鍑芥暟
                const renderModels = (filter = '') => {
                    let filtered;
                    if (filter) {
                        // 鏈夋悳绱㈣瘝鏃讹紝杩囨护鍖归厤鐨?
                        filtered = allGlobalModels.filter(m => m.toLowerCase().includes(filter.toLowerCase()));
                    } else {
                        // 鏃犳悳绱㈣瘝鏃讹紝浼樺厛鏄剧ず甯哥敤妯″瀷
                        const priority = allGlobalModels.filter(m =>
                            priorityKeywords.some(k => m.toLowerCase().includes(k))
                        );
                        const others = allGlobalModels.filter(m =>
                            !priorityKeywords.some(k => m.toLowerCase().includes(k))
                        );
                        filtered = [...priority.slice(0, 30), ...others.slice(0, 20)];
                    }
                    
                    const showingPartial = !filter && allGlobalModels.length > 50;
                    
                    modelItems.innerHTML = `
                        ${showingPartial ? `<div style="padding: 8px 12px; font-size: 11px; color: var(--text-secondary); background: rgba(100,180,255,0.1); border-bottom: 1px solid var(--border-color);">
                            馃挕 鍏?${allGlobalModels.length} 涓ā鍨嬶紝褰撳墠鏄剧ず甯哥敤妯″瀷銆傝緭鍏ュ叧閿瘝锛堝 gpt, claude, gemini锛夋悳绱㈡洿澶?..
                        </div>` : ''}
                        ${filter && filtered.length === 0 ? `<div style="padding: 16px; color: var(--text-secondary); text-align: center;">鏃犲尮閰嶇粨鏋滐紝璇峰皾璇曞叾浠栧叧閿瘝</div>` : ''}
                        ${filtered.map(m => `
                            <div class="model-option" data-model="${m}" style="padding: 10px 12px; cursor: pointer; border-bottom: 1px solid var(--border-color); transition: background 0.2s; font-size: 13px;"
                                onmouseover="this.style.background='rgba(255,255,255,0.1)'"
                                onmouseout="this.style.background='transparent'">
                                ${m}
                            </div>
                        `).join('')}
                    `;
                    
                    // 缁戝畾鐐瑰嚮浜嬩欢
                    modelItems.querySelectorAll('.model-option').forEach(opt => {
                        opt.addEventListener('click', () => {
                            modelInput.value = opt.dataset.model;
                            modelList.style.display = 'none';
                        });
                    });
                };
                
                renderModels();
                
                // 鎼滅储杩囨护锛堥槻鎶栵級
                let searchTimeout;
                searchInput.addEventListener('input', (e) => {
                    clearTimeout(searchTimeout);
                    searchTimeout = setTimeout(() => {
                        renderModels(e.target.value.trim());
                    }, 150);
                });
                
                showToast(`鑾峰彇鍒?${res.models.length} 涓ā鍨媊);
            } else {
                showToast(res.error || '鏈幏鍙栧埌妯″瀷鍒楄〃锛岃鎵嬪姩杈撳叆', 'error');
            }
        } catch (e) {
            showToast('鑾峰彇妯″瀷澶辫触: ' + e.message, 'error');
        } finally {
            btn.innerHTML = '<i class="ri-download-cloud-line"></i> 鑾峰彇妯″瀷鍒楄〃';
            btn.disabled = false;
        }
    });
    
    // 娴嬭瘯杩炴帴
    document.getElementById('test-global-connection').addEventListener('click', async () => {
        const btn = document.getElementById('test-global-connection');
        const resultArea = document.getElementById('test-result-area');
        const apiBase = document.getElementById('global-api-base').value.trim();
        const apiKey = document.getElementById('global-api-key').value.trim();
        const model = document.getElementById('global-model').value.trim();
        
        if (!apiBase) {
            showToast('璇峰厛濉啓API鍦板潃', 'error');
            return;
        }
        
        btn.innerHTML = '<i class="ri-loader-4-line"></i> 娴嬭瘯涓?..';
        btn.disabled = true;
        resultArea.style.display = 'none';
        
        try {
            const res = await apiCall('/api/test-connection', 'POST', {
                api_base: apiBase,
                api_key: apiKey === '鈥⑩€⑩€⑩€⑩€⑩€⑩€⑩€? ? '' : apiKey,
                model: model
            });
            
            resultArea.style.display = 'block';
            
            if (res.success) {
                resultArea.style.background = 'rgba(34, 197, 94, 0.15)';
                resultArea.style.border = '1px solid rgba(34, 197, 94, 0.4)';
                resultArea.innerHTML = `
                    <div style="display: flex; align-items: center; gap: 12px; margin-bottom: 12px;">
                        <i class="ri-checkbox-circle-fill" style="color: #22c55e; font-size: 24px;"></i>
                        <span style="color: #22c55e; font-weight: 600; font-size: 16px;">杩炴帴鎴愬姛锛?/span>
                    </div>
                    <div style="color: var(--text-secondary); font-size: 13px; line-height: 1.8;">
                        ${res.model_tested ? `<p>鉁?妯″瀷鍙敤: ${res.model_tested}</p>` : ''}
                        ${res.response_time ? `<p>鈿?鍝嶅簲鏃堕棿: ${res.response_time}ms</p>` : ''}
                        ${res.message ? `<p>馃摑 ${res.message}</p>` : ''}
                    </div>
                `;
                showToast('API杩炴帴娴嬭瘯鎴愬姛 鉁?);
            } else {
                resultArea.style.background = 'rgba(239, 68, 68, 0.15)';
                resultArea.style.border = '1px solid rgba(239, 68, 68, 0.4)';
                resultArea.innerHTML = `
                    <div style="display: flex; align-items: center; gap: 12px; margin-bottom: 12px;">
                        <i class="ri-close-circle-fill" style="color: #ef4444; font-size: 24px;"></i>
                        <span style="color: #ef4444; font-weight: 600; font-size: 16px;">杩炴帴澶辫触</span>
                    </div>
                    <div style="color: var(--text-secondary); font-size: 13px;">
                        <p>鉂?${res.error || '鏃犳硶杩炴帴鍒癆PI鏈嶅姟'}</p>
                    </div>
                `;
                showToast('API杩炴帴娴嬭瘯澶辫触', 'error');
            }
        } catch (e) {
            resultArea.style.display = 'block';
            resultArea.style.background = 'rgba(239, 68, 68, 0.15)';
            resultArea.style.border = '1px solid rgba(239, 68, 68, 0.4)';
            resultArea.innerHTML = `
                <div style="display: flex; align-items: center; gap: 12px; margin-bottom: 12px;">
                    <i class="ri-close-circle-fill" style="color: #ef4444; font-size: 24px;"></i>
                    <span style="color: #ef4444; font-weight: 600; font-size: 16px;">娴嬭瘯鍑洪敊</span>
                </div>
                <div style="color: var(--text-secondary); font-size: 13px;">
                    <p>鉂?${e.message}</p>
                </div>
            `;
            showToast('娴嬭瘯杩炴帴鍑洪敊: ' + e.message, 'error');
        } finally {
            btn.innerHTML = '馃敆 娴嬭瘯杩炴帴';
            btn.disabled = false;
        }
    });
    
    // 淇濆瓨閰嶇疆
    document.getElementById('save-global-config').addEventListener('click', async () => {
        const btn = document.getElementById('save-global-config');
        const apiBase = document.getElementById('global-api-base').value.trim();
        const apiKey = document.getElementById('global-api-key').value.trim();
        const model = document.getElementById('global-model').value.trim();
        const temperature = parseFloat(document.getElementById('global-temperature').value) || 0.7;
        const maxTokens = parseInt(document.getElementById('global-max-tokens').value) || 4096;
        
        if (!apiBase || !model) {
            showToast('璇峰～鍐橝PI鍦板潃鍜屾ā鍨嬪悕绉?, 'error');
            return;
        }
        
        btn.textContent = '淇濆瓨涓?..';
        btn.disabled = true;
        
        try {
            await apiCall('/api/global-config', 'POST', {
                api_base: apiBase,
                api_key: apiKey === '鈥⑩€⑩€⑩€⑩€⑩€⑩€⑩€? ? '' : apiKey,
                model: model,
                temperature: temperature,
                max_tokens: maxTokens
            });
            
            showToast('鍏ㄥ眬API閰嶇疆宸蹭繚瀛?鉁?);
            btn.textContent = '宸蹭繚瀛?鉁?;
            
            // 鏇存柊鐘舵€?
            document.getElementById('global-status-indicator').style.background = '#22c55e';
            document.getElementById('global-status-text').textContent = '鉁?鍏ㄥ眬API宸查厤缃?;
            document.getElementById('global-status-text').style.color = '#22c55e';
            
            setTimeout(() => {
                btn.textContent = '馃捑 淇濆瓨鍏ㄥ眬閰嶇疆';
                btn.disabled = false;
            }, 2000);
            
        } catch (e) {
            showToast('淇濆瓨澶辫触: ' + e.message, 'error');
            btn.textContent = '馃捑 淇濆瓨鍏ㄥ眬閰嶇疆';
            btn.disabled = false;
        }
    });
}

// ===== 鐭ヨ瘑搴撻厤缃?=====

async function loadKnowledgeBaseSettings() {
    updateBreadcrumbs(['璁剧疆', '鐭ヨ瘑搴撻厤缃?]);
    
    ui.workspace.innerHTML = `
        <div style="max-width: 800px; margin: 40px auto; padding: 0 20px;">
            <h2 style="margin-bottom: 16px; color: var(--text-primary);">馃摎 鐭ヨ瘑搴撻厤缃?/h2>
            <p style="color: var(--text-secondary); margin-bottom: 24px; line-height: 1.6;">
                閰嶇疆鍚戦噺妫€绱㈠拰鍏ㄦ枃鎼滅储鏈嶅姟锛岀敤浜庡寮篈gent鐨勪笂涓嬫枃璁板繂鍜岀煡璇嗘绱㈣兘鍔涖€?
            </p>
            
            <div id="kb-stats-panel" style="margin-bottom: 24px; padding: 20px; background: rgba(255,255,255,0.03); border: 1px solid var(--border-color); border-radius: 12px;">
                <h3 style="margin-bottom: 16px; font-size: 15px; color: var(--text-primary); display: flex; align-items: center; gap: 8px;">
                    <i class="ri-database-2-line"></i>
                    鐭ヨ瘑搴撶粺璁?
                </h3>
                <div id="kb-stats-content" style="display: grid; grid-template-columns: repeat(4, 1fr); gap: 16px;">
                    <div style="text-align: center;">
                        <div id="kb-stat-chunks" style="font-size: 24px; font-weight: bold; color: var(--accent-color);">-</div>
                        <div style="font-size: 12px; color: var(--text-secondary);">鐭ヨ瘑鐗囨</div>
                    </div>
                    <div style="text-align: center;">
                        <div id="kb-stat-chapters" style="font-size: 24px; font-weight: bold; color: #10b981;">-</div>
                        <div style="font-size: 12px; color: var(--text-secondary);">绔犺妭绱㈠紩</div>
                    </div>
                    <div style="text-align: center;">
                        <div id="kb-stat-fulltext" style="font-size: 24px; font-weight: bold; color: #f59e0b;">-</div>
                        <div style="font-size: 12px; color: var(--text-secondary);">鍏ㄦ枃绱㈠紩</div>
                    </div>
                    <div style="text-align: center;">
                        <div id="kb-stat-status" style="font-size: 24px; font-weight: bold; color: #8b5cf6;">-</div>
                        <div style="font-size: 12px; color: var(--text-secondary);">鏈嶅姟鐘舵€?/div>
                    </div>
                </div>
            </div>
            
            <div style="background: rgba(255,255,255,0.03); border: 1px solid var(--border-color); border-radius: 12px; padding: 24px; margin-bottom: 24px;">
                <h3 style="margin-bottom: 20px; font-size: 15px; color: var(--text-primary); display: flex; align-items: center; gap: 8px;">
                    <i class="ri-cloud-line"></i>
                    纭呭熀娴佸姩鍚戦噺鍖栨湇鍔?
                </h3>
                
                <div style="margin-bottom: 20px;">
                    <label style="display: block; font-size: 12px; margin-bottom: 8px; color: var(--text-secondary);">
                        API 鍦板潃
                    </label>
                    <input type="text" id="kb-siliconflow-base" placeholder="https://api.siliconflow.cn/v1"
                        style="width: 100%; background: rgba(0,0,0,0.3); border: 1px solid var(--border-color); padding: 12px; color: white; border-radius: 8px; font-size: 14px;">
                </div>
                
                <div style="margin-bottom: 20px;">
                    <label style="display: block; font-size: 12px; margin-bottom: 8px; color: var(--text-secondary);">
                        API 瀵嗛挜 <span style="color: #ef4444;">*</span>
                    </label>
                    <input type="password" id="kb-siliconflow-key" placeholder="sk-..."
                        style="width: 100%; background: rgba(0,0,0,0.3); border: 1px solid var(--border-color); padding: 12px; color: white; border-radius: 8px; font-size: 14px;">
                </div>
                
                <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 16px; margin-bottom: 20px;">
                    <div>
                        <label style="display: block; font-size: 12px; margin-bottom: 8px; color: var(--text-secondary);">鍚戦噺妯″瀷</label>
                        <select id="kb-siliconflow-model"
                            style="width: 100%; background: rgba(0,0,0,0.3); border: 1px solid var(--border-color); padding: 12px; color: white; border-radius: 8px; font-size: 14px;">
                            <option value="BAAI/bge-m3">BAAI/bge-m3 (鎺ㄨ崘)</option>
                            <option value="BAAI/bge-large-zh-v1.5">BAAI/bge-large-zh-v1.5</option>
                            <option value="BAAI/bge-base-zh-v1.5">BAAI/bge-base-zh-v1.5</option>
                        </select>
                    </div>
                    <div>
                        <label style="display: block; font-size: 12px; margin-bottom: 8px; color: var(--text-secondary);">鍚戦噺缁村害</label>
                        <select id="kb-embedding-dim"
                            style="width: 100%; background: rgba(0,0,0,0.3); border: 1px solid var(--border-color); padding: 12px; color: white; border-radius: 8px; font-size: 14px;">
                            <option value="1024">1024 缁?/option>
                            <option value="768">768 缁?/option>
                            <option value="512">512 缁?/option>
                        </select>
                    </div>
                </div>
                
                <button id="kb-test-embedding" style="width: 100%; padding: 12px; background: rgba(255,255,255,0.1); border: 1px solid var(--border-color); color: var(--text-primary); border-radius: 8px; cursor: pointer; font-weight: 500;">
                    馃敆 娴嬭瘯鍚戦噺鍖栨湇鍔¤繛鎺?
                </button>
                <div id="kb-test-result" style="display: none; margin-top: 12px; padding: 12px; border-radius: 8px;"></div>
            </div>
            
            <div style="background: rgba(255,255,255,0.03); border: 1px solid var(--border-color); border-radius: 12px; padding: 24px; margin-bottom: 24px;">
                <h3 style="margin-bottom: 20px; font-size: 15px; color: var(--text-primary); display: flex; align-items: center; gap: 8px;">
                    <i class="ri-scissors-cut-line"></i>
                    鏂囨湰鍒嗗潡閰嶇疆
                </h3>
                
                <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 16px;">
                    <div>
                        <label style="display: block; font-size: 12px; margin-bottom: 8px; color: var(--text-secondary);">
                            鍧楀ぇ灏?(瀛楃鏁?
                        </label>
                        <input type="number" id="kb-chunk-size" value="500" min="100" max="2000"
                            style="width: 100%; background: rgba(0,0,0,0.3); border: 1px solid var(--border-color); padding: 12px; color: white; border-radius: 8px; font-size: 14px;">
                        <p style="font-size: 11px; color: var(--text-secondary); margin-top: 4px;">寤鸿: 300-800</p>
                    </div>
                    <div>
                        <label style="display: block; font-size: 12px; margin-bottom: 8px; color: var(--text-secondary);">
                            閲嶅彔澶у皬 (瀛楃鏁?
                        </label>
                        <input type="number" id="kb-chunk-overlap" value="50" min="0" max="500"
                            style="width: 100%; background: rgba(0,0,0,0.3); border: 1px solid var(--border-color); padding: 12px; color: white; border-radius: 8px; font-size: 14px;">
                        <p style="font-size: 11px; color: var(--text-secondary); margin-top: 4px;">寤鸿: 鍧楀ぇ灏忕殑10%</p>
                    </div>
                </div>
            </div>
            
            <div style="background: rgba(255,255,255,0.03); border: 1px solid var(--border-color); border-radius: 12px; padding: 24px; margin-bottom: 24px;">
                <h3 style="margin-bottom: 20px; font-size: 15px; color: var(--text-primary); display: flex; align-items: center; gap: 8px;">
                    <i class="ri-search-line"></i>
                    娣峰悎妫€绱㈤厤缃?
                </h3>
                
                <div style="margin-bottom: 20px;">
                    <label style="display: block; font-size: 12px; margin-bottom: 8px; color: var(--text-secondary);">
                        鍚戦噺妫€绱㈡潈閲?(0-1)
                    </label>
                    <div style="display: flex; align-items: center; gap: 12px;">
                        <input type="range" id="kb-vector-weight" min="0" max="100" value="70"
                            style="flex: 1; height: 8px; -webkit-appearance: none; background: linear-gradient(to right, var(--accent-color), var(--accent-color)); border-radius: 4px; cursor: pointer;">
                        <span id="kb-vector-weight-value" style="min-width: 50px; text-align: right; color: var(--text-primary);">0.7</span>
                    </div>
                    <p style="font-size: 11px; color: var(--text-secondary); margin-top: 4px;">鍚戦噺妫€绱晶閲嶈涔夌浉浼煎害锛屽叏鏂囨绱晶閲嶅叧閿瘝鍖归厤</p>
                </div>
                
                <div style="margin-bottom: 20px;">
                    <label style="display: block; font-size: 12px; margin-bottom: 8px; color: var(--text-secondary);">
                        鍏ㄦ枃妫€绱㈡潈閲?(0-1)
                    </label>
                    <div style="display: flex; align-items: center; gap: 12px;">
                        <input type="range" id="kb-fulltext-weight" min="0" max="100" value="30"
                            style="flex: 1; height: 8px; -webkit-appearance: none; background: linear-gradient(to right, #f59e0b, #f59e0b); border-radius: 4px; cursor: pointer;">
                        <span id="kb-fulltext-weight-value" style="min-width: 50px; text-align: right; color: var(--text-primary);">0.3</span>
                    </div>
                </div>
                
                <div>
                    <label style="display: block; font-size: 12px; margin-bottom: 8px; color: var(--text-secondary);">
                        榛樿杩斿洖缁撴灉鏁?(Top-K)
                    </label>
                    <input type="number" id="kb-top-k" value="5" min="1" max="20"
                        style="width: 100%; background: rgba(0,0,0,0.3); border: 1px solid var(--border-color); padding: 12px; color: white; border-radius: 8px; font-size: 14px;">
                </div>
            </div>
            
            <div style="display: flex; gap: 12px;">
                <button id="kb-save-config" style="flex: 1; padding: 14px; background: var(--accent-color); border: none; color: white; border-radius: 8px; cursor: pointer; font-weight: 600; font-size: 15px;">
                    馃捑 淇濆瓨鐭ヨ瘑搴撻厤缃?
                </button>
            </div>
            
            <div style="margin-top: 24px; background: rgba(100,180,255,0.1); border: 1px solid rgba(100,180,255,0.3); border-radius: 12px; padding: 20px;">
                <h3 style="margin-bottom: 12px; font-size: 14px; color: #7dd3fc;">馃挕 閰嶇疆璇存槑</h3>
                <ul style="font-size: 13px; color: var(--text-secondary); line-height: 1.8; padding-left: 20px; margin: 0;">
                    <li><strong>鍚戦噺妫€绱?/strong>锛氫娇鐢ㄧ鍩烘祦鍔ㄧ殑 bge-m3 妯″瀷灏嗘枃鏈浆鎹负鍚戦噺锛屽疄鐜拌涔夌浉浼煎害鎼滅储</li>
                    <li><strong>鍏ㄦ枃妫€绱?/strong>锛氫娇鐢?SQLite FTS5 瀹炵幇鍏抽敭璇嶇簿纭尮閰?/li>
                    <li><strong>娣峰悎妫€绱?/strong>锛氱粨鍚堜袱绉嶆柟寮忥紝鍚戦噺鏉冮噸瓒婇珮瓒婁晶閲嶈涔夌悊瑙ｏ紝鍏ㄦ枃鏉冮噸瓒婇珮瓒婁晶閲嶇簿纭尮閰?/li>
                    <li><strong>鏂囨湰鍒嗗潡</strong>锛氬皢闀挎枃鏈垏鍒嗕负閫傚悎妫€绱㈢殑鐗囨锛屽潡澶у皬褰卞搷妫€绱㈢簿搴﹀拰閫熷害</li>
                </ul>
            </div>
        </div>
    `;
    
    // 鍔犺浇褰撳墠閰嶇疆
    try {
        const config = await apiCall('/api/knowledge-base/config', 'GET');
        
        // 濉厖琛ㄥ崟
        document.getElementById('kb-siliconflow-base').value = config.siliconflow_base_url || 'https://api.siliconflow.cn/v1';
        document.getElementById('kb-siliconflow-key').value = config.siliconflow_api_key ? '鈥⑩€⑩€⑩€⑩€⑩€⑩€⑩€? : '';
        document.getElementById('kb-siliconflow-model').value = config.siliconflow_model || 'BAAI/bge-m3';
        document.getElementById('kb-embedding-dim').value = config.siliconflow_embedding_dim || 1024;
        document.getElementById('kb-chunk-size').value = config.chunk_size || 500;
        document.getElementById('kb-chunk-overlap').value = config.chunk_overlap || 50;
        
        const vectorWeight = Math.round((config.vector_weight || 0.7) * 100);
        const fulltextWeight = Math.round((config.fulltext_weight || 0.3) * 100);
        document.getElementById('kb-vector-weight').value = vectorWeight;
        document.getElementById('kb-vector-weight-value').textContent = (vectorWeight / 100).toFixed(1);
        document.getElementById('kb-fulltext-weight').value = fulltextWeight;
        document.getElementById('kb-fulltext-weight-value').textContent = (fulltextWeight / 100).toFixed(1);
        document.getElementById('kb-top-k').value = config.default_top_k || 5;
        
    } catch (e) {
        console.error('Failed to load knowledge base config:', e);
    }
    
    // 鍔犺浇缁熻淇℃伅
    try {
        const stats = await apiCall('/api/knowledge-base/stats', 'GET');
        document.getElementById('kb-stat-chunks').textContent = stats.total_chunks || 0;
        document.getElementById('kb-stat-chapters').textContent = stats.total_chapters || 0;
        document.getElementById('kb-stat-fulltext').textContent = stats.fulltext_entries || 0;
        document.getElementById('kb-stat-status').textContent = stats.is_initialized ? '鉁? : '脳';
        document.getElementById('kb-stat-status').style.color = stats.is_initialized ? '#22c55e' : '#ef4444';
    } catch (e) {
        console.error('Failed to load knowledge base stats:', e);
    }
    
    // 鏉冮噸婊戝潡鑱斿姩
    document.getElementById('kb-vector-weight').addEventListener('input', (e) => {
        const value = parseInt(e.target.value);
        document.getElementById('kb-vector-weight-value').textContent = (value / 100).toFixed(1);
        // 鑷姩璋冩暣鍏ㄦ枃鏉冮噸
        document.getElementById('kb-fulltext-weight').value = 100 - value;
        document.getElementById('kb-fulltext-weight-value').textContent = ((100 - value) / 100).toFixed(1);
    });
    
    document.getElementById('kb-fulltext-weight').addEventListener('input', (e) => {
        const value = parseInt(e.target.value);
        document.getElementById('kb-fulltext-weight-value').textContent = (value / 100).toFixed(1);
        // 鑷姩璋冩暣鍚戦噺鏉冮噸
        document.getElementById('kb-vector-weight').value = 100 - value;
        document.getElementById('kb-vector-weight-value').textContent = ((100 - value) / 100).toFixed(1);
    });
    
    // 娴嬭瘯杩炴帴鎸夐挳
    document.getElementById('kb-test-embedding').addEventListener('click', async () => {
        const btn = document.getElementById('kb-test-embedding');
        const resultDiv = document.getElementById('kb-test-result');
        
        const apiBase = document.getElementById('kb-siliconflow-base').value.trim();
        const apiKey = document.getElementById('kb-siliconflow-key').value.trim();
        const model = document.getElementById('kb-siliconflow-model').value;
        
        if (!apiKey || apiKey === '鈥⑩€⑩€⑩€⑩€⑩€⑩€⑩€?) {
            showToast('璇峰厛濉啓API瀵嗛挜', 'error');
            return;
        }
        
        btn.innerHTML = '<i class="ri-loader-4-line"></i> 娴嬭瘯涓?..';
        btn.disabled = true;
        resultDiv.style.display = 'none';
        
        try {
            const res = await apiCall('/api/knowledge-base/test-embedding', 'POST', {
                api_base: apiBase,
                api_key: apiKey,
                model: model
            });
            
            resultDiv.style.display = 'block';
            
            if (res.success) {
                resultDiv.style.background = 'rgba(34, 197, 94, 0.15)';
                resultDiv.style.border = '1px solid rgba(34, 197, 94, 0.4)';
                resultDiv.innerHTML = `
                    <div style="display: flex; align-items: center; gap: 8px; color: #22c55e;">
                        <i class="ri-checkbox-circle-fill"></i>
                        <span>杩炴帴鎴愬姛锛佸悜閲忕淮搴? ${res.embedding_dim}锛屽搷搴旀椂闂? ${res.response_time}ms</span>
                    </div>
                `;
                showToast('鍚戦噺鍖栨湇鍔¤繛鎺ユ垚鍔?鉁?);
            } else {
                resultDiv.style.background = 'rgba(239, 68, 68, 0.15)';
                resultDiv.style.border = '1px solid rgba(239, 68, 68, 0.4)';
                resultDiv.innerHTML = `
                    <div style="display: flex; align-items: center; gap: 8px; color: #ef4444;">
                        <i class="ri-close-circle-fill"></i>
                        <span>杩炴帴澶辫触: ${res.error || '鏈煡閿欒'}</span>
                    </div>
                `;
                showToast('鍚戦噺鍖栨湇鍔¤繛鎺ュけ璐?, 'error');
            }
        } catch (e) {
            resultDiv.style.display = 'block';
            resultDiv.style.background = 'rgba(239, 68, 68, 0.15)';
            resultDiv.style.border = '1px solid rgba(239, 68, 68, 0.4)';
            resultDiv.innerHTML = `
                <div style="display: flex; align-items: center; gap: 8px; color: #ef4444;">
                    <i class="ri-close-circle-fill"></i>
                    <span>娴嬭瘯澶辫触: ${e.message}</span>
                </div>
            `;
            showToast('娴嬭瘯杩炴帴鍑洪敊: ' + e.message, 'error');
        } finally {
            btn.innerHTML = '馃敆 娴嬭瘯鍚戦噺鍖栨湇鍔¤繛鎺?;
            btn.disabled = false;
        }
    });
    
    // 淇濆瓨閰嶇疆鎸夐挳
    document.getElementById('kb-save-config').addEventListener('click', async () => {
        const btn = document.getElementById('kb-save-config');
        
        const apiBase = document.getElementById('kb-siliconflow-base').value.trim();
        const apiKey = document.getElementById('kb-siliconflow-key').value.trim();
        const model = document.getElementById('kb-siliconflow-model').value;
        const embeddingDim = parseInt(document.getElementById('kb-embedding-dim').value);
        const chunkSize = parseInt(document.getElementById('kb-chunk-size').value);
        const chunkOverlap = parseInt(document.getElementById('kb-chunk-overlap').value);
        const vectorWeight = parseInt(document.getElementById('kb-vector-weight').value) / 100;
        const fulltextWeight = parseInt(document.getElementById('kb-fulltext-weight').value) / 100;
        const topK = parseInt(document.getElementById('kb-top-k').value);
        
        btn.textContent = '淇濆瓨涓?..';
        btn.disabled = true;
        
        try {
            await apiCall('/api/knowledge-base/config', 'POST', {
                siliconflow_api_key: apiKey === '鈥⑩€⑩€⑩€⑩€⑩€⑩€⑩€? ? '' : apiKey,
                siliconflow_base_url: apiBase || 'https://api.siliconflow.cn/v1',
                siliconflow_model: model,
                siliconflow_embedding_dim: embeddingDim,
                chunk_size: chunkSize,
                chunk_overlap: chunkOverlap,
                vector_weight: vectorWeight,
                fulltext_weight: fulltextWeight,
                default_top_k: topK
            });
            
            showToast('鐭ヨ瘑搴撻厤缃凡淇濆瓨 鉁?);
            btn.textContent = '宸蹭繚瀛?鉁?;
            
            setTimeout(() => {
                btn.textContent = '馃捑 淇濆瓨鐭ヨ瘑搴撻厤缃?;
                btn.disabled = false;
            }, 2000);
            
        } catch (e) {
            showToast('淇濆瓨澶辫触: ' + e.message, 'error');
            btn.textContent = '馃捑 淇濆瓨鐭ヨ瘑搴撻厤缃?;
            btn.disabled = false;
        }
    });
}

async function loadAgentSettings() {
    updateBreadcrumbs(['璁剧疆', 'Agent澶ц剳閰嶇疆']);
    ui.workspace.innerHTML = `<div style="max-width: 800px; margin: 40px auto; padding: 0 20px;" id="agent-list">
        <h2 style="margin-bottom: 16px; color: var(--text-primary);">馃 Agent 澶ц剳閰嶇疆</h2>
        <p style="color: var(--text-secondary); margin-bottom: 24px;">涓烘瘡涓狝gent閰嶇疆鐙珛鐨凙PI鍜屾ā鍨嬶紝鎴栦娇鐢ㄥ叏灞€閰嶇疆銆?/p>
        
        <div id="global-config-hint" style="margin-bottom: 24px; padding: 16px; background: rgba(255,200,100,0.1); border: 1px solid rgba(255,200,100,0.3); border-radius: 12px; display: none;">
            <div style="display: flex; align-items: center; gap: 12px;">
                <i class="ri-error-warning-line" style="font-size: 20px; color: #f59e0b;"></i>
                <div>
                    <p style="color: #f59e0b; font-weight: 600; margin-bottom: 4px;">鍏ㄥ眬API鏈厤缃?/p>
                    <p style="color: var(--text-secondary); font-size: 13px;">寤鸿鍏?a href="#" id="go-to-global-config" style="color: var(--accent-color);">閰嶇疆鍏ㄥ眬API</a>锛屾墍鏈堿gent灏嗚嚜鍔ㄤ娇鐢ㄥ叏灞€閰嶇疆銆?/p>
                </div>
            </div>
        </div>
        
        <div id="agent-cards">鍔犺浇涓?..</div>
    </div>`;

    try {
        const res = await apiCall('/api/agents', 'GET');
        const container = document.getElementById('agent-cards');
        container.innerHTML = '';
        
        // 鏄剧ず鍏ㄥ眬閰嶇疆鎻愮ず
        const globalHint = document.getElementById('global-config-hint');
        if (!res.global_configured) {
            globalHint.style.display = 'block';
            document.getElementById('go-to-global-config').addEventListener('click', (e) => {
                e.preventDefault();
                loadGlobalAPISettings();
                // 鏇存柊瀵艰埅閫変腑鐘舵€?
                ui.navList.querySelectorAll('.list-item').forEach(el => el.classList.remove('active'));
                ui.navList.querySelectorAll('.list-item')[1].classList.add('active');
            });
        }

        res.agents.forEach(agent => {
            const displayName = agent.display_name || agent.name;
            const useGlobal = agent.use_global !== false;
            const globalConfigured = res.global_configured;
            
            const div = document.createElement('div');
            div.style.cssText = 'background: rgba(255,255,255,0.03); border: 1px solid var(--border-color); border-radius: 12px; padding: 24px; margin-bottom: 16px;';
            div.innerHTML = `
                <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:16px;">
                    <div>
                        <strong style="font-size:16px; color: var(--text-primary);">${displayName}</strong>
                        <p style="font-size:12px; color:var(--text-secondary); margin-top:4px;">${agent.description}</p>
                    </div>
                    <span class="model-badge" style="font-size:12px; padding: 4px 12px; background: ${useGlobal && globalConfigured ? 'rgba(34, 197, 94, 0.2)' : 'rgba(255,255,255,0.05)'}; border-radius: 20px; color: ${useGlobal && globalConfigured ? '#22c55e' : 'var(--text-secondary)'};">
                        ${agent.current_model}
                    </span>
                </div>
                
                <!-- 浣跨敤鍏ㄥ眬閰嶇疆寮€鍏?-->
                <div style="margin-bottom: 16px; padding: 12px; background: rgba(0,0,0,0.2); border-radius: 8px;">
                    <label style="display: flex; align-items: center; gap: 12px; cursor: pointer;">
                        <input type="checkbox" class="use-global-checkbox" ${useGlobal ? 'checked' : ''} style="width: 18px; height: 18px; accent-color: var(--accent-color);">
                        <span style="color: var(--text-primary);">浣跨敤鍏ㄥ眬API閰嶇疆</span>
                        ${globalConfigured ? '<span style="font-size:11px; color:#22c55e;">(宸查厤缃?</span>' : '<span style="font-size:11px; color:#f59e0b;">(鏈厤缃?</span>'}
                    </label>
                </div>
                
                <!-- 鑷畾涔夐厤缃尯鍩?-->
                <div class="custom-config-area" style="${useGlobal ? 'opacity: 0.5; pointer-events: none;' : ''}">
                    <div style="margin-bottom: 16px;">
                        <label style="display:block; font-size:12px; margin-bottom:6px; color:var(--text-secondary);">API 鍦板潃</label>
                        <input class="agent-base" type="text" value="${agent.api_base.startsWith('馃搶') ? '' : (agent.api_base === '(鏈厤缃?' ? '' : agent.api_base)}" placeholder="https://api.openai.com/v1"
                            style="width:100%; background:rgba(0,0,0,0.3); border:1px solid var(--border-color); padding:10px; color:white; border-radius:6px; font-size:13px;">
                    </div>
                    
                    <div style="margin-bottom: 16px;">
                        <label style="display:block; font-size:12px; margin-bottom:6px; color:var(--text-secondary);">API 瀵嗛挜</label>
                        <input class="agent-key" type="password" placeholder="sk-... 鎴栫暀绌?
                            style="width:100%; background:rgba(0,0,0,0.3); border:1px solid var(--border-color); padding:10px; color:white; border-radius:6px; font-size:13px;">
                    </div>
                    
                    <div style="margin-bottom: 16px;">
                        <label style="display:block; font-size:12px; margin-bottom:6px; color:var(--text-secondary);">妯″瀷鍚嶇О</label>
                        <div style="display:flex; gap:8px;">
                            <input class="agent-model" type="text" value="${agent.current_model.startsWith('馃搶') ? '' : (agent.current_model === '(鏈厤缃?' ? '' : agent.current_model)}" placeholder="gpt-4"
                                style="flex:1; background:rgba(0,0,0,0.3); border:1px solid var(--border-color); padding:10px; color:white; border-radius:6px; font-size:13px;">
                            <button class="fetch-models-btn" style="padding:10px 16px; background:rgba(255,255,255,0.1); border:1px solid var(--border-color); color:var(--text-primary); border-radius:6px; cursor:pointer; white-space:nowrap;">
                                <i class="ri-download-cloud-line"></i> 鑾峰彇
                            </button>
                        </div>
                        <div class="model-list" style="display:none; margin-top:8px; max-height:200px; overflow-y:auto; background:rgba(0,0,0,0.3); border:1px solid var(--border-color); border-radius:6px;">
                        </div>
                    </div>
                    
                    <div style="display:grid; grid-template-columns:1fr 1fr; gap:16px; margin-bottom:16px;">
                        <div>
                            <label style="display:block; font-size:12px; margin-bottom:6px; color:var(--text-secondary);">娓╁害 (Temperature)</label>
                            <input class="agent-temperature" type="number" value="${agent.temperature !== undefined ? agent.temperature : 0.7}" min="0" max="2" step="0.1"
                                style="width:100%; background:rgba(0,0,0,0.3); border:1px solid var(--border-color); padding:10px; color:white; border-radius:6px; font-size:13px;">
                        </div>
                        <div>
                            <label style="display:block; font-size:12px; margin-bottom:6px; color:var(--text-secondary);">鏈€澶oken鏁?/label>
                            <input class="agent-max-tokens" type="number" value="${agent.max_tokens !== undefined ? agent.max_tokens : 4096}" min="100" max="128000"
                                style="width:100%; background:rgba(0,0,0,0.3); border:1px solid var(--border-color); padding:10px; color:white; border-radius:6px; font-size:13px;">
                        </div>
                    </div>
                </div>
                
                <button class="save-agent" data-name="${agent.name}" style="width:100%; padding:12px; background:var(--accent-color); border:none; color:white; border-radius:8px; cursor:pointer; font-weight:600; transition: opacity 0.2s;">淇濆瓨銆?{displayName}銆嶉厤缃?/button>
            `;

            // 浣跨敤鍏ㄥ眬閰嶇疆寮€鍏?
            const useGlobalCheckbox = div.querySelector('.use-global-checkbox');
            const customConfigArea = div.querySelector('.custom-config-area');
            
            useGlobalCheckbox.addEventListener('change', () => {
                if (useGlobalCheckbox.checked) {
                    customConfigArea.style.opacity = '0.5';
                    customConfigArea.style.pointerEvents = 'none';
                } else {
                    customConfigArea.style.opacity = '1';
                    customConfigArea.style.pointerEvents = 'auto';
                }
            });

            // 鑾峰彇妯″瀷鍒楄〃鎸夐挳
            div.querySelector('.fetch-models-btn').addEventListener('click', async () => {
                const btn = div.querySelector('.fetch-models-btn');
                const baseUrl = div.querySelector('.agent-base').value.trim();
                const apiKey = div.querySelector('.agent-key').value.trim();
                const modelList = div.querySelector('.model-list');
                const modelInput = div.querySelector('.agent-model');

                if (!baseUrl) {
                    showToast('璇峰厛濉啓API鍦板潃', 'error');
                    return;
                }

                btn.innerHTML = '<i class="ri-loader-4-line"></i> 鑾峰彇涓?..';
                btn.disabled = true;

                try {
                    const res = await apiCall('/api/fetch-models', 'POST', {
                        api_base: baseUrl,
                        api_key: apiKey
                    });

                    if (res.success && res.models.length > 0) {
                        modelList.style.display = 'block';
                        modelList.innerHTML = res.models.map(m => `
                            <div class="model-option" style="padding:10px 12px; cursor:pointer; border-bottom:1px solid var(--border-color); transition:background 0.2s;"
                                onmouseover="this.style.background='rgba(255,255,255,0.1)'"
                                onmouseout="this.style.background='transparent'">
                                ${m}
                            </div>
                        `).join('');

                        modelList.querySelectorAll('.model-option').forEach(opt => {
                            opt.addEventListener('click', () => {
                                modelInput.value = opt.textContent.trim();
                                modelList.style.display = 'none';
                                div.querySelector('.model-badge').textContent = opt.textContent.trim();
                            });
                        });

                        showToast(`鑾峰彇鍒?${res.models.length} 涓ā鍨媊);
                    } else {
                        showToast(res.error || '鏈幏鍙栧埌妯″瀷鍒楄〃', 'error');
                        modelList.style.display = 'none';
                    }
                } catch (e) {
                    showToast('鑾峰彇妯″瀷澶辫触: ' + e.message, 'error');
                } finally {
                    btn.innerHTML = '<i class="ri-download-cloud-line"></i> 鑾峰彇';
                    btn.disabled = false;
                }
            });

            // 缁戝畾淇濆瓨浜嬩欢
            div.querySelector('.save-agent').addEventListener('click', async (e) => {
                const btn = e.target;
                const base = div.querySelector('.agent-base').value.trim();
                const model = div.querySelector('.agent-model').value.trim();
                const key = div.querySelector('.agent-key').value.trim();
                const temperature = parseFloat(div.querySelector('.agent-temperature').value) || 0.7;
                const maxTokens = parseInt(div.querySelector('.agent-max-tokens').value) || 4096;
                const useGlobal = div.querySelector('.use-global-checkbox').checked;

                // 濡傛灉涓嶄娇鐢ㄥ叏灞€閰嶇疆锛屾鏌PI key鏄惁涓虹┖
                if (!useGlobal && !key && base) {
                    const confirmSave = confirm(
                        `鈿狅笍 娉ㄦ剰锛氥€?{displayName}銆嶆湭濉啓 API Key\n\n` +
                        `鎮ㄩ€夋嫨浜嗚嚜瀹氫箟閰嶇疆浣嗘病鏈夊～鍐橝PI瀵嗛挜锛岃繖鍙兘瀵艰嚧璇gent鏃犳硶姝ｅ父宸ヤ綔銆俓n\n` +
                        `寤鸿锛歕n` +
                        `鈥?濉啓API Key鍚庡啀淇濆瓨\n` +
                        `鈥?鎴栬€呭嬀閫?浣跨敤鍏ㄥ眬API閰嶇疆"\n\n` +
                        `纭畾瑕佺户缁繚瀛樺悧锛焋
                    );
                    if (!confirmSave) {
                        return;
                    }
                }

                btn.textContent = '淇濆瓨涓?..';
                btn.disabled = true;

                try {
                    await apiCall(`/api/agents/${agent.name}`, 'POST', {
                        api_base: base,
                        api_key: key,
                        model: model,
                        temperature: temperature,
                        max_tokens: maxTokens,
                        use_global: useGlobal
                    });
                    showToast(`銆?{displayName}銆嶉厤缃凡淇濆瓨 鉁揱);
                    btn.textContent = `宸蹭繚瀛?鉁揱;
                    
                    // 鏇存柊妯″瀷鏍囩
                    if (useGlobal && res.global_configured) {
                        div.querySelector('.model-badge').textContent = `馃搶 ${res.global_model}`;
                        div.querySelector('.model-badge').style.background = 'rgba(34, 197, 94, 0.2)';
                        div.querySelector('.model-badge').style.color = '#22c55e';
                    } else {
                        div.querySelector('.model-badge').textContent = model || '(鏈厤缃?';
                        div.querySelector('.model-badge').style.background = 'rgba(255,255,255,0.05)';
                        div.querySelector('.model-badge').style.color = 'var(--text-secondary)';
                    }
                    
                    setTimeout(() => {
                        btn.textContent = `淇濆瓨銆?{displayName}銆嶉厤缃甡;
                        btn.disabled = false;
                    }, 2000);
                } catch (e) {
                    showToast('淇濆瓨澶辫触: ' + e.message, 'error');
                    btn.textContent = `淇濆瓨銆?{displayName}銆嶉厤缃甡;
                    btn.disabled = false;
                }
            });

            container.appendChild(div);
        });
    } catch (e) {
        document.getElementById('agent-cards').innerHTML = `
            <div style="text-align: center; color: var(--text-secondary); padding: 40px;">
                <p>鍔犺浇Agent閰嶇疆澶辫触</p>
                <p style="font-size: 12px; margin-top: 8px;">${e.message}</p>
            </div>
        `;
    }
}

// ===== Copilot 閫昏緫 =====

// 鏂板缓浼氳瘽 - 娓呯┖鑱婂ぉ璁板綍
function clearCopilotChat() {
    if (!ui.copilotMsgs) return;
    
    // 纭瀵硅瘽妗?
    if (ui.copilotMsgs.children.length > 1) {
        if (!confirm('纭畾瑕佹竻绌哄綋鍓嶄細璇濆悧锛焅n\n杩欏皢娓呴櫎鎵€鏈夊璇濊褰曪紝寮€濮嬫柊鐨勪細璇濄€?)) {
            return;
        }
    }
    
    // 娓呯┖娑堟伅瀹瑰櫒
    ui.copilotMsgs.innerHTML = '';
    
    // 娣诲姞娆㈣繋娑堟伅
    const welcomeMsg = document.createElement('div');
    welcomeMsg.className = 'msg ai';
    welcomeMsg.innerHTML = `浣犲ソ锛佹垜鏄綘鐨勫啓浣滃姪鎵嬨€傝瘯璇曪細
        <ul style="margin: 8px 0; padding-left: 20px;">
            <li>杈撳叆 <code>@</code> 寮曠敤瑙掕壊銆佺珷鑺傛垨璁惧畾</li>
            <li>鐩存帴鎻愰棶鎴栧彂鎸囦护</li>
        </ul>`;
    ui.copilotMsgs.appendChild(welcomeMsg);
    
    // 娓呯┖杈撳叆妗?
    const input = document.getElementById('copilot-input-text');
    if (input) {
        input.value = '';
        input.dataset.mentions = '[]';
    }
    
    showToast('宸插紑濮嬫柊浼氳瘽 鉁?);
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
        // 杩涘叆涓撴敞妯″紡
        workbench.classList.add('focus-mode');
        if (ui.toggleFocusBtn) {
            ui.toggleFocusBtn.innerHTML = '<i class="ri-fullscreen-exit-line"></i>';
            ui.toggleFocusBtn.title = '閫€鍑轰笓娉ㄦā寮?;
        }
    } else {
        // 閫€鍑轰笓娉ㄦā寮?
        workbench.classList.remove('focus-mode');
        if (ui.toggleFocusBtn) {
            ui.toggleFocusBtn.innerHTML = '<i class="ri-fullscreen-line"></i>';
            ui.toggleFocusBtn.title = '涓撴敞妯″紡';
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
        
        const reply = res.reply || '鏀跺埌';
        
        // 妫€娴嬫槸鍚︽槸鍒涗綔绫诲唴瀹癸紝濡傛灉鏄垯鏄剧ず淇濆瓨閫夐」
        const isCreativeContent = detectCreativeContent(text, reply);
        appendMessage(reply, 'ai', isCreativeContent);
    } catch (e) {
        appendMessage('杩炴帴澶辫触锛岃妫€鏌PI閰嶇疆', 'ai', false);
    }
}

// ===== 妫€娴嬫槸鍚︿负鍒涗綔绫诲唴瀹?=====
function detectCreativeContent(userMessage, aiReply) {
    // 鐢ㄦ埛娑堟伅涓寘鍚垱浣滅浉鍏崇殑鍏抽敭璇?
    const creativeKeywords = [
        '鍒涗綔', '鍐?, '鐢熸垚', '璁捐', '璁惧畾', '澶х翰', '瑙掕壊', '浜虹墿', '涓栫晫瑙?,
        '鏁呬簨', '鎯呰妭', '绔犺妭', '鑳屾櫙', '鎻忚堪', '鎶€鑳?, '鑳藉姏', '閬撳叿', '瑁呭',
        '鍔垮姏', '闃佃惀', '娉曟湳', '鍔熸硶', '绉樼睄', '鍦板浘', '鍦烘櫙', '鐜',
        '甯垜', '缁欐垜', '璇峰啓', '璇峰垱浣?, '璇风敓鎴?, '璇疯璁?
    ];
    
    const lowerUserMsg = userMessage.toLowerCase();
    const hasCreativeIntent = creativeKeywords.some(k => lowerUserMsg.includes(k));
    
    // AI鍥炲闀垮害瓒冲锛堣〃绀烘湁瀹炶川鎬у唴瀹癸級
    const hasSubstantialContent = aiReply.length > 100;
    
    return hasCreativeIntent && hasSubstantialContent;
}

// ===== 鏄剧ず淇濆瓨Copilot鍐呭鍒拌祫鏂欏簱鐨勬彁绀哄璇濇 =====
function showSaveCopilotContentPrompt(content, contentType) {
    const modal = document.getElementById('modal-container');
    if (!modal) return;
    
    // 鍐呭绫诲瀷閰嶇疆
    const typeConfig = {
        outline: { name: '绔犺妭', icon: 'ri-book-open-line', color: '#22c55e' },
        characters: { name: '瑙掕壊', icon: 'ri-user-line', color: '#ec4899' },
        worldbuilding: { name: '涓栫晫瑙?, icon: 'ri-earth-line', color: '#06b6d4' },
        items: { name: '閬撳叿', icon: 'ri-sword-line', color: '#f97316' },
        outline_settings: { name: '澶х翰璁惧畾', icon: 'ri-file-list-3-line', color: '#a855f7' },
        eventlines: { name: '浜嬩欢绾?, icon: 'ri-timeline-view', color: '#8b5cf6' },
        detail_settings: { name: '缁嗙翰璁惧畾', icon: 'ri-file-text-line', color: '#14b8a6' },
        chapter_settings: { name: '绔犵翰璁惧畾', icon: 'ri-book-open-line', color: '#eab308' }
    };
    
    const config = typeConfig[contentType] || { name: contentType, icon: 'ri-folder-line', color: '#666' };
    
    // 灏濊瘯浠庡唴瀹逛腑鎻愬彇鏍囬
    let suggestedTitle = '';
    const titleMatch = content.match(/^(?:#+\s*)?(.+?)[:锛歕n]/);
    if (titleMatch) {
        suggestedTitle = titleMatch[1].trim().slice(0, 30);
    }
    
    // 濡傛灉鏄珷鑺傜被鍨嬶紝妫€娴嬬珷鑺傚彿
    let chapterNum = null;
    if (contentType === 'outline') {
        const chapters = store.projectData.outline || [];
        chapterNum = chapters.length + 1;
        if (!suggestedTitle) {
            suggestedTitle = `绗?{chapterNum}绔燻;
        }
    }
    
    modal.classList.remove('hidden');
    modal.innerHTML = `
        <div style="position: fixed; top: 0; left: 0; right: 0; bottom: 0; background: rgba(0,0,0,0.7); display: flex; align-items: center; justify-content: center; z-index: 1000;">
            <div style="background: var(--bg-panel); border: 1px solid var(--border-color); border-radius: 16px; padding: 30px; width: 600px; max-width: 95%; max-height: 80vh; overflow: hidden; display: flex; flex-direction: column;">
                <h3 style="color: var(--text-primary); margin-bottom: 20px; font-size: 18px; display: flex; align-items: center; gap: 12px;">
                    <i class="${config.icon}" style="color: ${config.color};"></i>
                    淇濆瓨鍒?{config.name}
                </h3>
                
                <div style="margin-bottom: 16px;">
                    <label style="display: block; font-size: 13px; color: var(--text-secondary); margin-bottom: 8px;">鍚嶇О/鏍囬 <span style="color: #ef4444;">*</span></label>
                    <input type="text" id="save-content-title" value="${escapeHtml(suggestedTitle)}" placeholder="璇疯緭鍏ュ悕绉?.."
                        style="width: 100%; background: rgba(0,0,0,0.3); border: 1px solid var(--border-color); padding: 12px; color: var(--text-primary); border-radius: 8px; font-size: 14px;">
                </div>
                
                <div style="margin-bottom: 20px; flex: 1; overflow: hidden; display: flex; flex-direction: column;">
                    <label style="display: block; font-size: 13px; color: var(--text-secondary); margin-bottom: 8px;">鍐呭棰勮 (鍙紪杈?</label>
                    <textarea id="save-content-text" style="flex: 1; min-height: 200px; background: rgba(0,0,0,0.3); border: 1px solid var(--border-color); padding: 12px; color: var(--text-primary); border-radius: 8px; font-size: 14px; line-height: 1.6; resize: none;">${escapeHtml(content)}</textarea>
                </div>
                
                <div style="display: flex; gap: 12px;">
                    <button id="cancel-save-content" style="flex: 1; padding: 12px; background: rgba(255,255,255,0.1); border: 1px solid var(--border-color); color: var(--text-primary); border-radius: 8px; cursor: pointer; font-size: 14px;">鍙栨秷</button>
                    <button id="confirm-save-content" style="flex: 1; padding: 12px; background: ${config.color}; border: none; color: white; border-radius: 8px; cursor: pointer; font-weight: 600; font-size: 14px;">
                        <i class="ri-save-line"></i> 淇濆瓨鍒?{config.name}
                    </button>
                </div>
            </div>
        </div>
    `;
    
    // 鑷姩鑱氱劍鏍囬杈撳叆妗?
    setTimeout(() => {
        const titleInput = document.getElementById('save-content-title');
        if (titleInput) {
            titleInput.focus();
            if (!suggestedTitle) titleInput.select();
        }
    }, 100);
    
    // 鍙栨秷鎸夐挳
    document.getElementById('cancel-save-content')?.addEventListener('click', () => {
        modal.classList.add('hidden');
        modal.innerHTML = '';
    });
    
    // 纭淇濆瓨鎸夐挳
    document.getElementById('confirm-save-content')?.addEventListener('click', async () => {
        const title = document.getElementById('save-content-title')?.value.trim();
        const text = document.getElementById('save-content-text')?.value.trim();
        
        if (!title) {
            showToast('璇疯緭鍏ュ悕绉?鏍囬', 'error');
            return;
        }
        
        if (!text) {
            showToast('鍐呭涓嶈兘涓虹┖', 'error');
            return;
        }
        
        try {
            await saveCopilotContentToProject(contentType, title, text);
            modal.classList.add('hidden');
            modal.innerHTML = '';
            showToast(`宸蹭繚瀛樺埌${config.name}锛氥€?{title}銆?鉁揱);
        } catch (e) {
            showToast('淇濆瓨澶辫触: ' + e.message, 'error');
        }
    });
    
    // 鍥炶溅蹇嵎閿?
    document.getElementById('save-content-title')?.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') {
            document.getElementById('confirm-save-content')?.click();
        }
    });
}

// ===== 淇濆瓨Copilot鍐呭鍒伴」鐩祫鏂欏簱 =====
async function saveCopilotContentToProject(contentType, title, content) {
    // 纭繚椤圭洰鏁版嵁鍒濆鍖?
    if (!store.projectData) {
        store.projectData = {};
    }
    
    // 鏍规嵁绫诲瀷淇濆瓨鍒板搴旂殑璧勬枡搴?
    if (contentType === 'outline') {
        // 淇濆瓨涓虹珷鑺?
        if (!store.projectData.outline) {
            store.projectData.outline = [];
        }
        
        const newChapter = {
            title: title,
            content: content,
            summary: '',
            created_at: new Date().toISOString()
        };
        
        store.projectData.outline.push(newChapter);
        
        // 淇濆瓨鍒版湇鍔″櫒
        await apiCall('/api/project-data/outline', 'POST', {
            data: store.projectData.outline
        });
        
        // 鍒锋柊鍐欎綔妯″潡瀵艰埅
        if (store.currentModule === 'write') {
            renderNavPanel('write');
        }
        
    } else if (contentType === 'characters') {
        // 淇濆瓨涓鸿鑹?
        if (!store.projectData.characters) {
            store.projectData.characters = [];
        }
        
        const newCharacter = {
            id: Date.now().toString(),
            name: title,
            description: content,
            created_at: new Date().toISOString()
        };
        
        store.projectData.characters.push(newCharacter);
        
        await apiCall('/api/project-data/characters', 'POST', {
            data: store.projectData.characters
        });
        
    } else if (contentType === 'worldbuilding') {
        // 淇濆瓨涓轰笘鐣岃璁惧畾
        if (!store.projectData.worldbuilding) {
            store.projectData.worldbuilding = [];
        }
        
        const newWorld = {
            id: Date.now().toString(),
            name: title,
            description: content,
            created_at: new Date().toISOString()
        };
        
        store.projectData.worldbuilding.push(newWorld);
        
        await apiCall('/api/project-data/worldbuilding', 'POST', {
            data: store.projectData.worldbuilding
        });
        
    } else if (contentType === 'items') {
        // 淇濆瓨涓洪亾鍏风墿鍝?
        if (!store.projectData.items) {
            store.projectData.items = [];
        }
        
        const newItem = {
            id: Date.now().toString(),
            name: title,
            description: content,
            created_at: new Date().toISOString()
        };
        
        store.projectData.items.push(newItem);
        
        await apiCall('/api/project-data/items', 'POST', {
            data: store.projectData.items
        });
        
    } else {
        // 鍏朵粬鎵╁睍璧勬枡搴撶被鍨嬶紙鏈湴瀛樺偍锛?
        if (!store.projectData[contentType]) {
            store.projectData[contentType] = [];
        }
        
        const newEntry = {
            id: Date.now().toString(),
            name: title,
            description: content,
            created_at: new Date().toISOString()
        };
        
        store.projectData[contentType].push(newEntry);
        
        // 淇濆瓨鍒版湰鍦板瓨鍌?
        if (typeof saveExtendedKnowledgeData === 'function') {
            saveExtendedKnowledgeData(contentType);
        }
    }
    
    // 鏇存柊@寮曠敤鏁版嵁
    if (typeof updateMentionData === 'function') {
        updateMentionData();
    }
    
    // 鍒锋柊璧勬枡搴撴ā鍧楋紙濡傛灉褰撳墠鍦ㄨ祫鏂欏簱椤甸潰锛?
    if (store.currentModule === 'world') {
        renderKnowledgeNavPanel();
    }
}

// 杈呭姪鍑芥暟锛欻TML杞箟
function escapeHtml(text) {
    if (!text) return '';
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

function appendMessage(text, role, showSaveOptions = false) {
    if (!ui.copilotMsgs) return;
    const div = document.createElement('div');
    div.className = `msg ${role}`;
    
    // 鍒涘缓娑堟伅鍐呭瀹瑰櫒
    const contentDiv = document.createElement('div');
    contentDiv.className = 'msg-content';
    contentDiv.textContent = text;
    div.appendChild(contentDiv);
    
    // 濡傛灉鏄疉I娑堟伅涓旈渶瑕佹樉绀轰繚瀛橀€夐」锛屾坊鍔犲揩鎹锋搷浣滄寜閽?
    if (role === 'ai' && showSaveOptions && text.length > 50) {
        const actionsDiv = document.createElement('div');
        actionsDiv.className = 'msg-actions';
        actionsDiv.style.cssText = 'margin-top: 12px; padding-top: 12px; border-top: 1px solid rgba(255,255,255,0.1); display: flex; gap: 8px; flex-wrap: wrap;';
        actionsDiv.innerHTML = `
            <span style="font-size: 11px; color: var(--text-secondary); margin-right: 8px; line-height: 28px;">馃捑 淇濆瓨鍒拌祫鏂欏簱锛?/span>
            <button class="save-content-btn" data-type="outline" style="padding: 4px 12px; background: rgba(34, 197, 94, 0.2); border: 1px solid rgba(34, 197, 94, 0.4); color: #22c55e; border-radius: 6px; cursor: pointer; font-size: 12px;">
                <i class="ri-book-open-line"></i> 绔犺妭
            </button>
            <button class="save-content-btn" data-type="characters" style="padding: 4px 12px; background: rgba(236, 72, 153, 0.2); border: 1px solid rgba(236, 72, 153, 0.4); color: #ec4899; border-radius: 6px; cursor: pointer; font-size: 12px;">
                <i class="ri-user-line"></i> 瑙掕壊
            </button>
            <button class="save-content-btn" data-type="worldbuilding" style="padding: 4px 12px; background: rgba(6, 182, 212, 0.2); border: 1px solid rgba(6, 182, 212, 0.4); color: #06b6d4; border-radius: 6px; cursor: pointer; font-size: 12px;">
                <i class="ri-earth-line"></i> 涓栫晫瑙?
            </button>
            <button class="save-content-btn" data-type="items" style="padding: 4px 12px; background: rgba(249, 115, 22, 0.2); border: 1px solid rgba(249, 115, 22, 0.4); color: #f97316; border-radius: 6px; cursor: pointer; font-size: 12px;">
                <i class="ri-sword-line"></i> 閬撳叿
            </button>
            <button class="save-content-btn" data-type="outline_settings" style="padding: 4px 12px; background: rgba(168, 85, 247, 0.2); border: 1px solid rgba(168, 85, 247, 0.4); color: #a855f7; border-radius: 6px; cursor: pointer; font-size: 12px;">
                <i class="ri-file-list-3-line"></i> 澶х翰璁惧畾
            </button>
        `;
        
        // 缁戝畾淇濆瓨鎸夐挳浜嬩欢
        actionsDiv.querySelectorAll('.save-content-btn').forEach(btn => {
            btn.addEventListener('click', () => {
                const contentType = btn.dataset.type;
                showSaveCopilotContentPrompt(text, contentType);
            });
        });
        
        div.appendChild(actionsDiv);
    }
    
    ui.copilotMsgs.appendChild(div);
    ui.copilotMsgs.scrollTop = ui.copilotMsgs.scrollHeight;
}

// ===== 宸ュ叿鍑芥暟 =====

async function loadOutline() {
    return [
        { title: '椋庤捣寰湯', content: '' },
        { title: '鍒濆叆姹熸箹', content: '' }
    ];
}

function updateBreadcrumbs(path) {
    if (!ui.breadcrumbs) return;
    ui.breadcrumbs.innerHTML = path.map((p, i) =>
        i === path.length - 1
            ? `<span class="current">${p}</span>`
            : `<span>${p}</span> <i class="ri-arrow-right-s-line"></i>`
    ).join('');
}

// 娉ㄦ剰锛歴etTheme銆乻etAppBackground銆乧learAppBackground鍑芥暟宸插湪涓婃柟瀹氫箟锛堜富棰樿缃儴鍒嗭級锛屼笉瑕佸湪姝ら噸澶嶅畾涔?

async function apiCall(url, method, data) {
    const options = {
        method: method,
        headers: { 'Content-Type': 'application/json' }
    };
    if (data) options.body = JSON.stringify(data);
    const res = await fetch(url, options);
    if (!res.ok) {
        throw new Error(`HTTP ${res.status}`);
    }
    return await res.json();
}

function showToast(msg, type) {
    const t = document.getElementById('toast');
    if (!t) return;
    t.textContent = msg;
    t.classList.remove('hidden');
    t.style.opacity = 1;
    setTimeout(() => {
        t.style.opacity = 0;
        setTimeout(() => t.classList.add('hidden'), 300);
    }, 2500);
}

// 鍏ㄥ眬鏆撮湶 switchModule 浠ヤ究 HTML 涓皟鐢?
window.switchModule = switchModule;

// ===== Copilot 澧炲己鍔熻兘 =====

// 鍙紩鐢ㄧ殑璧勬枡搴撴暟鎹紙浠庨」鐩暟鎹姩鎬佹洿鏂帮級
let mentionData = [];

/**
 * 鏅鸿兘鎼滅储鍖归厤鍑芥暟
 * 鏀寔锛氬叏绉板尮閰嶃€佸墠缂€鍖归厤銆佸寘鍚尮閰嶃€佸唴瀹规悳绱€佺被鍨嬫悳绱?
 * @param {Object} item - 璧勬枡搴撴潯鐩?{type, name, content, details}
 * @param {string} query - 鎼滅储鍏抽敭璇?
 * @returns {Object|null} - 杩斿洖鍖归厤缁撴灉鍜屽緱鍒嗭紝鏈尮閰嶈繑鍥瀗ull
 */
function smartMentionMatch(item, query) {
    if (!query) return { item, score: 0 };
    
    const q = query.toLowerCase().trim();
    const name = (item.name || '').toLowerCase();
    const type = (item.type || '').toLowerCase();
    const content = (item.content || '').toLowerCase();
    const details = (item.details || '').toLowerCase();
    
    let score = 0;
    let matchType = '';
    
    // 1. 瀹屽叏鍖归厤鍚嶇О (鏈€楂樹紭鍏堢骇)
    if (name === q) {
        score = 100;
        matchType = 'exact';
    }
    // 2. 鍚嶇О鍓嶇紑鍖归厤 (楂樹紭鍏堢骇)
    else if (name.startsWith(q)) {
        score = 80 + (q.length / name.length) * 15;
        matchType = 'prefix';
    }
    // 3. 鍚嶇О鍖呭惈鍖归厤
    else if (name.includes(q)) {
        const pos = name.indexOf(q);
        score = 60 - (pos / name.length) * 20;
        matchType = 'contains';
    }
    // 4. 绫诲瀷鍖归厤
    else if (type.includes(q)) {
        score = 40;
        matchType = 'type';
    }
    // 5. 鍐呭/鎻忚堪鍖归厤
    else if (content.includes(q) || details.includes(q)) {
        score = 30;
        matchType = 'content';
    }
    // 6. 澶氬叧閿瘝鍒嗚瘝鍖归厤
    else {
        const keywords = q.split(/\s+/).filter(k => k.length > 0);
        if (keywords.length > 1) {
            const allMatch = keywords.every(k =>
                name.includes(k) || type.includes(k) || content.includes(k)
            );
            if (allMatch) {
                score = 35;
                matchType = 'multi-keyword';
            }
        }
    }
    
    if (score > 0) {
        return { item, score, matchType };
    }
    return null;
}

/**
 * 鎼滅储骞舵帓搴忚祫鏂欏簱鍐呭
 * @param {string} query - 鎼滅储鍏抽敭璇?
 * @returns {Array} - 鎺掑簭鍚庣殑鍖归厤缁撴灉
 */
function searchMentions(query) {
    // 濡傛灉璧勬枡搴撲负绌猴紝杩斿洖绌烘暟缁?
    if (mentionData.length === 0) {
        console.log('[searchMentions] mentionData 涓虹┖');
        return [];
    }
    
    if (!query || query.trim() === '') {
        // 鏃犳悳绱㈣瘝鏃讹紝杩斿洖鍓?0涓父鐢ㄩ」锛堟寜绫诲瀷鍒嗙粍锛?
        const grouped = {};
        mentionData.forEach(item => {
            if (!grouped[item.type]) grouped[item.type] = [];
            if (grouped[item.type].length < 5) {
                grouped[item.type].push(item);
            }
        });
        const result = [];
        Object.values(grouped).forEach(items => result.push(...items));
        return result.slice(0, 20);
    }
    
    const results = [];
    mentionData.forEach(item => {
        const match = smartMentionMatch(item, query);
        if (match) {
            results.push(match);
        }
    });
    
    // 鎸夊緱鍒嗛檷搴忔帓鍒?
    results.sort((a, b) => b.score - a.score);
    
    // 杩斿洖鍓?0涓粨鏋?
    return results.slice(0, 30).map(r => r.item);
}

let selectedMentionIndex = 0;
let currentMentions = [];
let mentionStartPos = -1;

function initCopilotEnhancements() {
    const input = document.getElementById('copilot-input-text');
    const popup = document.getElementById('mention-popup');
    const dragHandle = document.getElementById('copilot-drag-handle');
    const panel = document.getElementById('copilot-panel');

    if (!input || !popup) return;

    // @寮曠敤鐩戝惉
    input.addEventListener('input', (e) => {
        const text = input.value;
        const cursorPos = input.selectionStart;

        // 鏌ユ壘@绗﹀彿
        const atIndex = text.lastIndexOf('@', cursorPos - 1);

        if (atIndex !== -1 && (atIndex === 0 || text[atIndex - 1] === ' ' || text[atIndex - 1] === '\n')) {
            const query = text.substring(atIndex + 1, cursorPos);
            mentionStartPos = atIndex;

            // 浣跨敤鏅鸿兘鎼滅储鍖归厤
            currentMentions = searchMentions(query);
            console.log('[Mention] 鎼滅储缁撴灉:', currentMentions.length, '鏉? mentionData鎬绘暟:', mentionData.length);

            // 鏃犺鏄惁鏈夌粨鏋滈兘鏄剧ず寮圭獥锛堢┖鐘舵€佹椂鏄剧ず鎻愮ず锛?
            renderMentionPopup(currentMentions, query);
            popup.classList.remove('hidden');
            selectedMentionIndex = 0;
            if (currentMentions.length > 0) {
                updateMentionSelection();
            }
        } else {
            popup.classList.add('hidden');
            mentionStartPos = -1;
        }
    });

    // 閿洏瀵艰埅
    input.addEventListener('keydown', (e) => {
        if (popup.classList.contains('hidden')) return;

        if (e.key === 'ArrowDown') {
            e.preventDefault();
            selectedMentionIndex = (selectedMentionIndex + 1) % currentMentions.length;
            updateMentionSelection();
        } else if (e.key === 'ArrowUp') {
            e.preventDefault();
            selectedMentionIndex = (selectedMentionIndex - 1 + currentMentions.length) % currentMentions.length;
            updateMentionSelection();
        } else if (e.key === 'Enter' && !e.shiftKey) {
            if (!popup.classList.contains('hidden')) {
                e.preventDefault();
                insertMention(currentMentions[selectedMentionIndex]);
            }
        } else if (e.key === 'Escape') {
            popup.classList.add('hidden');
        }
    });

    // 鐐瑰嚮閫夋嫨
    popup.addEventListener('click', (e) => {
        const item = e.target.closest('.mention-item');
        if (item) {
            const index = parseInt(item.dataset.index);
            insertMention(currentMentions[index]);
        }
    });

    // 鎷栧姩璋冩暣瀹藉害 - 澧炲己鐗?
    if (dragHandle && panel) {
        let isDragging = false;
        let startX, startWidth;
        
        // 浠巐ocalStorage鎭㈠淇濆瓨鐨勫搴?
        const savedWidth = localStorage.getItem('copilot_panel_width');
        if (savedWidth) {
            const width = parseInt(savedWidth);
            if (width >= 280 && width <= 600) {
                panel.style.width = width + 'px';
            }
        }

        dragHandle.addEventListener('mousedown', (e) => {
            e.preventDefault();
            isDragging = true;
            startX = e.clientX;
            startWidth = panel.offsetWidth;
            dragHandle.classList.add('dragging');
            document.body.classList.add('resizing-copilot');
        });

        document.addEventListener('mousemove', (e) => {
            if (!isDragging) return;
            // 鍚戝乏鎷栧姩澧炲姞瀹藉害锛屽悜鍙虫嫋鍔ㄥ噺灏戝搴?
            const diff = startX - e.clientX;
            const newWidth = Math.max(280, Math.min(600, startWidth + diff));
            panel.style.width = newWidth + 'px';
        });

        document.addEventListener('mouseup', () => {
            if (isDragging) {
                isDragging = false;
                dragHandle.classList.remove('dragging');
                document.body.classList.remove('resizing-copilot');
                // 淇濆瓨瀹藉害鍒發ocalStorage
                localStorage.setItem('copilot_panel_width', panel.offsetWidth);
            }
        });
        
        // 鍙屽嚮閲嶇疆涓洪粯璁ゅ搴?
        dragHandle.addEventListener('dblclick', () => {
            panel.style.width = '320px';
            localStorage.setItem('copilot_panel_width', 320);
            showToast('瀵硅瘽妗嗗凡鎭㈠榛樿瀹藉害');
        });
    }
}

function renderMentionPopup(items, query = '') {
    const popup = document.getElementById('mention-popup');
    
    // 楂樹寒鍖归厤鏂囧瓧鐨勫嚱鏁?
    const highlightMatch = (text, q) => {
        if (!q || !text) return text;
        const lowerText = text.toLowerCase();
        const lowerQ = q.toLowerCase();
        const index = lowerText.indexOf(lowerQ);
        if (index === -1) return text;
        return text.substring(0, index) +
               '<mark style="background: var(--accent-color); color: white; padding: 0 2px; border-radius: 2px;">' +
               text.substring(index, index + q.length) +
               '</mark>' +
               text.substring(index + q.length);
    };
    
    if (items.length === 0) {
        // 鍖哄垎璧勬枡搴撲负绌哄拰鎼滅储鏃犵粨鏋滀袱绉嶆儏鍐?
        const isEmpty = mentionData.length === 0;
        popup.innerHTML = `
            <div style="padding: 16px; color: var(--text-secondary); text-align: center; font-size: 13px;">
                ${isEmpty ? `
                    <div style="margin-bottom: 8px;"><i class="ri-database-2-line" style="font-size: 24px; opacity: 0.5;"></i></div>
                    <div>璧勬枡搴撴殏鏃犲唴瀹?/div>
                    <div style="font-size: 11px; margin-top: 4px; opacity: 0.7;">璇峰厛鍦ㄣ€岃祫鏂欏簱銆嶄腑娣诲姞瑙掕壊銆佽瀹氱瓑鍐呭</div>
                ` : `
                    <div>鏃犲尮閰嶇粨鏋滐紝璇曡瘯鍏朵粬鍏抽敭璇?/div>
                `}
            </div>
        `;
        return;
    }
    
    // 鎸夌被鍨嬪垎缁勬樉绀?
    const grouped = {};
    items.forEach((item, originalIndex) => {
        if (!grouped[item.type]) grouped[item.type] = [];
        grouped[item.type].push({ ...item, originalIndex });
    });
    
    let html = '';
    let globalIndex = 0;
    
    // 濡傛灉鍙湁涓€绉嶇被鍨嬫垨鎼滅储璇嶅瓨鍦紝涓嶅垎缁勬樉绀?
    const typeCount = Object.keys(grouped).length;
    
    if (query && typeCount <= 3) {
        // 鏈夋悳绱㈣瘝鏃讹紝绱у噾鏄剧ず
        html = items.map((item, i) => `
            <div class="mention-item" data-index="${i}" style="padding: 8px 12px; cursor: pointer; border-bottom: 1px solid var(--border-color); transition: background 0.15s;">
                <span class="mention-type" style="font-size: 10px; color: var(--accent-color); background: rgba(var(--accent-rgb), 0.15); padding: 2px 6px; border-radius: 4px; margin-right: 8px;">${item.type}</span>
                <span class="mention-name" style="color: var(--text-primary);">${highlightMatch(item.name, query)}</span>
                ${item.content ? `<span style="font-size: 11px; color: var(--text-secondary); margin-left: 8px; opacity: 0.7; max-width: 150px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; display: inline-block; vertical-align: middle;">${item.content.substring(0, 30)}${item.content.length > 30 ? '...' : ''}</span>` : ''}
            </div>
        `).join('');
    } else {
        // 鏃犳悳绱㈣瘝鎴栫被鍨嬪鏃讹紝鍒嗙粍鏄剧ず
        Object.entries(grouped).forEach(([type, typeItems]) => {
            html += `<div style="padding: 6px 12px; font-size: 11px; color: var(--text-secondary); background: rgba(255,255,255,0.03); font-weight: 600;">${type} (${typeItems.length})</div>`;
            typeItems.forEach(item => {
                html += `
                    <div class="mention-item" data-index="${globalIndex}" style="padding: 8px 12px 8px 24px; cursor: pointer; border-bottom: 1px solid var(--border-color); transition: background 0.15s;">
                        <span class="mention-name" style="color: var(--text-primary);">${highlightMatch(item.name, query)}</span>
                    </div>
                `;
                globalIndex++;
            });
        });
    }
    
    popup.innerHTML = html;
    
    // 閲嶆柊缁戝畾鎮仠鏁堟灉
    popup.querySelectorAll('.mention-item').forEach(item => {
        item.addEventListener('mouseenter', () => {
            popup.querySelectorAll('.mention-item').forEach(el => el.style.background = '');
            item.style.background = 'rgba(255,255,255,0.08)';
            selectedMentionIndex = parseInt(item.dataset.index);
        });
        item.addEventListener('mouseleave', () => {
            item.style.background = '';
        });
    });
}

function updateMentionSelection() {
    const items = document.querySelectorAll('.mention-item');
    items.forEach((item, i) => {
        item.classList.toggle('active', i === selectedMentionIndex);
    });
}

function insertMention(mention) {
    const input = document.getElementById('copilot-input-text');
    const popup = document.getElementById('mention-popup');

    if (!mention || mentionStartPos === -1) return;

    const before = input.value.substring(0, mentionStartPos);
    const after = input.value.substring(input.selectionStart);

    // 鎻掑叆寮曠敤鏍囪
    const mentionTag = `@${mention.name} `;
    input.value = before + mentionTag + after;

    // 瀛樺偍寮曠敤鍐呭渚涘彂閫佹椂浣跨敤
    if (!input.dataset.mentions) {
        input.dataset.mentions = '[]';
    }
    const mentions = JSON.parse(input.dataset.mentions);
    mentions.push(mention);
    input.dataset.mentions = JSON.stringify(mentions);

    popup.classList.add('hidden');
    mentionStartPos = -1;
    input.focus();
}

// 鍙戦€佹秷鎭椂澶勭悊寮曠敤锛堣鐩栧師鏈夌殑sendCopilotMessage锛?
async function sendCopilotMessageWithMentions() {
    const input = document.getElementById('copilot-input-text');
    if (!input) return;

    const text = input.value.trim();
    if (!text) return;

    // 鑾峰彇寮曠敤鍐呭
    let mentions = [];
    try {
        mentions = JSON.parse(input.dataset.mentions || '[]');
    } catch (e) { }

    // 鏋勫缓鍙戦€佺粰AI鐨勬秷鎭?
    let userMessage = text;
    let contextForAI = '';

    if (mentions.length > 0) {
        contextForAI = '\n\n{USER寮曠敤鍐呭}\n';
        mentions.forEach(m => {
            contextForAI += `[${m.type}] ${m.name}: ${m.content}\n`;
        });
        contextForAI += '{/USER寮曠敤鍐呭}';
    }

    // 鏄剧ず鐢ㄦ埛娑堟伅
    appendMessage(text, 'user');
    input.value = '';
    input.dataset.mentions = '[]';

    // 鍙戦€佺粰AI
    try {
        const res = await apiCall('/api/chat', 'POST', {
            message: userMessage + contextForAI,
            session_id: 'copilot'
        });
        appendMessage(res.reply || '鏀跺埌', 'ai');
    } catch (e) {
        appendMessage('杩炴帴澶辫触锛岃妫€鏌PI閰嶇疆', 'ai');
    }
}

// ===== 椤圭洰绠＄悊鍔熻兘 =====

async function loadProjects() {
    try {
        const res = await apiCall('/api/projects', 'GET');
        store.projects = res.projects || [];
        store.currentProjectId = res.current_project_id;

        // 鏌ユ壘褰撳墠椤圭洰鍚嶇О
        const currentProject = store.projects.find(p => p.id === store.currentProjectId);
        if (currentProject) {
            store.currentProjectName = currentProject.name;
        }

        updateProjectSelector();
        await loadCurrentProjectData();
    } catch (e) {
        console.error('Failed to load projects:', e);
    }
}

function updateProjectSelector() {
    // 鏇存柊褰撳墠椤圭洰鍚嶇О鏄剧ず
    if (ui.currentProjectName) {
        ui.currentProjectName.textContent = store.currentProjectName || '閫夋嫨椤圭洰';
    }

    // 鏇存柊涓嬫媺鍒楄〃
    if (ui.projectList) {
        ui.projectList.innerHTML = store.projects.map(p => `
            <div class="project-item ${p.id === store.currentProjectId ? 'active' : ''}" data-id="${p.id}">
                <div>
                    <div class="project-item-name">${p.name}</div>
                    ${p.description ? `<div class="project-item-desc">${p.description}</div>` : ''}
                </div>
            </div>
        `).join('');

        // 缁戝畾鐐瑰嚮浜嬩欢
        ui.projectList.querySelectorAll('.project-item').forEach(item => {
            item.addEventListener('click', () => {
                switchProject(item.dataset.id);
            });
        });
    }
}

function toggleProjectDropdown() {
    if (ui.projectDropdown) {
        ui.projectDropdown.classList.toggle('hidden');
    }
}

async function switchProject(projectId) {
    if (projectId === store.currentProjectId) {
        ui.projectDropdown.classList.add('hidden');
        return;
    }

    try {
        await apiCall(`/api/projects/${projectId}/switch`, 'POST');
        store.currentProjectId = projectId;

        const project = store.projects.find(p => p.id === projectId);
        if (project) {
            store.currentProjectName = project.name;
        }

        updateProjectSelector();
        await loadCurrentProjectData();

        // 鍒锋柊褰撳墠瑙嗗浘
        switchModule(store.currentModule);

        showToast(`宸插垏鎹㈠埌銆?{store.currentProjectName}銆峘);
        ui.projectDropdown.classList.add('hidden');
    } catch (e) {
        showToast('鍒囨崲椤圭洰澶辫触', 'error');
    }
}

async function loadCurrentProjectData() {
    try {
        const [chars, outline, world, items] = await Promise.all([
            apiCall('/api/project-data/characters', 'GET'),
            apiCall('/api/project-data/outline', 'GET'),
            apiCall('/api/project-data/worldbuilding', 'GET'),
            apiCall('/api/project-data/items', 'GET')
        ]);

        // 淇濈暀鐜版湁鐨勮嚜瀹氫箟璧勬枡搴撴暟鎹?
        const existingCustomData = {};
        store.knowledgeCategories.filter(c => !c.builtin).forEach(cat => {
            existingCustomData[cat.key] = store.projectData[cat.key] || [];
        });

        store.projectData = {
            characters: chars.data || [],
            outline: outline.data || [],
            worldbuilding: world.data || [],
            items: items.data || [],
            // 鎵╁睍璧勬枡搴擄紙鐩墠瀛樺偍鍦╨ocalStorage锛?
            eventlines: store.projectData.eventlines || [],
            outline_settings: store.projectData.outline_settings || [],
            detail_settings: store.projectData.detail_settings || [],
            chapter_settings: store.projectData.chapter_settings || [],
            // 鎭㈠鑷畾涔夎祫鏂欏簱鏁版嵁
            ...existingCustomData
        };

        // 浠巐ocalStorage鍔犺浇鎵╁睍璧勬枡搴撴暟鎹?
        loadExtendedKnowledgeData();

        // 鏇存柊@寮曠敤鏁版嵁
        updateMentionData();
    } catch (e) {
        console.error('Failed to load project data:', e);
    }
}

// 鍔犺浇鎵╁睍璧勬枡搴撴暟鎹?
function loadExtendedKnowledgeData() {
    const projectId = store.currentProjectId || 'default';
    
    // 鍔犺浇鍐呯疆鎵╁睍鍒嗙被
    ['eventlines', 'outline_settings', 'detail_settings', 'chapter_settings'].forEach(key => {
        try {
            const saved = localStorage.getItem(`knowledge_${projectId}_${key}`);
            if (saved) {
                store.projectData[key] = JSON.parse(saved);
            }
        } catch (e) {
            console.error(`Failed to load ${key}:`, e);
        }
    });
    
    // 鍔犺浇鑷畾涔夊垎绫绘暟鎹?
    store.knowledgeCategories.filter(c => !c.builtin).forEach(cat => {
        try {
            const saved = localStorage.getItem(`knowledge_${projectId}_${cat.key}`);
            if (saved) {
                store.projectData[cat.key] = JSON.parse(saved);
            }
        } catch (e) {
            console.error(`Failed to load ${cat.key}:`, e);
        }
    });
}

// 淇濆瓨鎵╁睍璧勬枡搴撴暟鎹?
function saveExtendedKnowledgeData(key) {
    const projectId = store.currentProjectId || 'default';
    try {
        localStorage.setItem(`knowledge_${projectId}_${key}`, JSON.stringify(store.projectData[key] || []));
    } catch (e) {
        console.error(`Failed to save ${key}:`, e);
    }
}

function updateMentionData() {
    // 鐢ㄥ綋鍓嶉」鐩暟鎹洿鏂板彲寮曠敤鍒楄〃
    mentionData.length = 0;

    // 瑙掕壊妗ｆ
    (store.projectData.characters || []).forEach(c => {
        mentionData.push({
            type: '瑙掕壊',
            name: c.name,
            content: c.description || '',
            details: c.details || c.personality || ''
        });
    });

    // 绔犺妭澶х翰
    (store.projectData.outline || []).forEach((ch, i) => {
        mentionData.push({
            type: '绔犺妭',
            name: `绗?{i + 1}绔?${ch.title || ''}`,
            content: ch.summary || (ch.content ? ch.content.substring(0, 100) : ''),
            details: ch.content || ''
        });
    });

    // 涓栫晫璁惧畾
    (store.projectData.worldbuilding || []).forEach(w => {
        mentionData.push({
            type: '涓栫晫',
            name: w.name,
            content: w.description || '',
            details: w.details || ''
        });
    });

    // 閬撳叿鐗╁搧
    (store.projectData.items || []).forEach(item => {
        mentionData.push({
            type: '鐗╁搧',
            name: item.name,
            content: item.description || '',
            details: item.details || item.properties || ''
        });
    });
    
    // 娣诲姞鎵╁睍璧勬枡搴撳埌寮曠敤
    // 浜嬩欢绾?
    (store.projectData.eventlines || []).forEach(item => {
        mentionData.push({
            type: '浜嬩欢',
            name: item.name,
            content: item.description || '',
            details: item.details || ''
        });
    });

    // 澶х翰璁惧畾
    (store.projectData.outline_settings || []).forEach(item => {
        mentionData.push({
            type: '澶х翰',
            name: item.name,
            content: item.description || '',
            details: item.details || ''
        });
    });

    // 缁嗙翰璁惧畾
    (store.projectData.detail_settings || []).forEach(item => {
        mentionData.push({
            type: '缁嗙翰',
            name: item.name,
            content: item.description || '',
            details: item.details || ''
        });
    });

    // 绔犵翰璁惧畾
    (store.projectData.chapter_settings || []).forEach(item => {
        mentionData.push({
            type: '绔犵翰',
            name: item.name,
            content: item.description || '',
            details: item.details || ''
        });
    });
    
    // 鑷畾涔夎祫鏂欏簱
    store.knowledgeCategories.filter(c => !c.builtin).forEach(cat => {
        (store.projectData[cat.key] || []).forEach(item => {
            mentionData.push({
                type: cat.name,
                name: item.name,
                content: item.description || '',
                details: item.details || ''
            });
        });
    });
    
    console.log(`[MentionData] 宸叉洿鏂?${mentionData.length} 鏉¤祫鏂欏簱鏉＄洰鍙緵@寮曠敤`);
}

function showCreateProjectDialog() {
    ui.projectDropdown.classList.add('hidden');

    const name = prompt('璇疯緭鍏ユ柊灏忚椤圭洰鍚嶇О锛?);
    if (name && name.trim()) {
        createProject(name.trim());
    }
}

async function createProject(name) {
    try {
        const res = await apiCall('/api/projects', 'POST', {
            name: name,
            description: ''
        });

        if (res.success) {
            showToast(`椤圭洰銆?{name}銆嶅垱寤烘垚鍔焋);
            await loadProjects();
            // 鍒囨崲鍒版柊椤圭洰
            if (res.project && res.project.id) {
                await switchProject(res.project.id);
            }
        }
    } catch (e) {
        showToast('鍒涘缓椤圭洰澶辫触', 'error');
    }
}

// ===== 楂橀璇嶆眹妫€娴嬩笌姝ｅ垯鏇挎崲鍔熻兘 =====

// 榛樿姝ｅ垯鏇挎崲瑙勫垯
const DEFAULT_REGEX_RULES = [
    { id: '1', name: '澶氫綑绌烘牸', pattern: '\\s{2,}', replacement: ' ', enabled: true, description: '灏嗗涓繛缁┖鏍兼浛鎹负鍗曚釜绌烘牸' },
    { id: '2', name: '涓嫳鏂囩┖鏍?, pattern: '([\\u4e00-\\u9fa5])\\s+([\\u4e00-\\u9fa5])', replacement: '$1$2', enabled: true, description: '鍘婚櫎涓枃涔嬮棿鐨勭┖鏍? },
    { id: '3', name: '閲嶅鏍囩偣', pattern: '([銆傦紒锛燂紝銆侊紱锛歖)\\1+', replacement: '$1', enabled: true, description: '鍘婚櫎閲嶅鐨勬爣鐐圭鍙? },
    { id: '4', name: '"鐨?瀛楄繃澶?, pattern: '鐨剓2,}', replacement: '鐨?, enabled: false, description: '灏嗗涓繛缁殑"鐨?鏇挎崲涓哄崟涓? },
    { id: '5', name: '鐪佺暐鍙疯鑼?, pattern: '\\.{3,}|銆倇3,}', replacement: '鈥︹€?, enabled: true, description: '灏嗕笁涓強浠ヤ笂鍙ョ偣鏇挎崲涓虹渷鐣ュ彿' }
];

// 鑾峰彇鐢ㄦ埛淇濆瓨鐨勮鍒?
function getRegexRules() {
    try {
        const saved = localStorage.getItem('regex_replacement_rules');
        if (saved) {
            return JSON.parse(saved);
        }
    } catch (e) {
        console.error('Failed to load regex rules:', e);
    }
    return [...DEFAULT_REGEX_RULES];
}

// 淇濆瓨瑙勫垯
function saveRegexRules(rules) {
    localStorage.setItem('regex_replacement_rules', JSON.stringify(rules));
}

// 鍒濆鍖栬緭鍏ユ楂樺害鎷栧姩璋冩暣鍔熻兘
function initInputResizer() {
    const resizeHandle = document.getElementById('copilot-resize-handle');
    const textarea = document.getElementById('copilot-input-text');
    const copilotInput = document.querySelector('.copilot-input');
    
    if (!resizeHandle || !textarea || !copilotInput) return;
    
    let isDragging = false;
    let startY = 0;
    let startHeight = 0;
    
    // 浠巐ocalStorage鎭㈠淇濆瓨鐨勯珮搴?
    const savedHeight = localStorage.getItem('copilot_input_height');
    if (savedHeight) {
        const height = parseInt(savedHeight);
        if (height >= 60 && height <= 400) {
            textarea.style.height = height + 'px';
        }
    }
    
    resizeHandle.addEventListener('mousedown', (e) => {
        e.preventDefault();
        isDragging = true;
        startY = e.clientY;
        startHeight = textarea.offsetHeight;
        
        resizeHandle.classList.add('dragging');
        document.body.classList.add('resizing-input');
    });
    
    document.addEventListener('mousemove', (e) => {
        if (!isDragging) return;
        
        // 鍚戜笂鎷栧姩澧炲姞楂樺害锛屽悜涓嬫嫋鍔ㄥ噺灏戦珮搴?
        const deltaY = startY - e.clientY;
        let newHeight = startHeight + deltaY;
        
        // 闄愬埗楂樺害鑼冨洿
        newHeight = Math.max(60, Math.min(400, newHeight));
        
        textarea.style.height = newHeight + 'px';
    });
    
    document.addEventListener('mouseup', () => {
        if (isDragging) {
            isDragging = false;
            resizeHandle.classList.remove('dragging');
            document.body.classList.remove('resizing-input');
            
            // 淇濆瓨楂樺害鍒發ocalStorage
            localStorage.setItem('copilot_input_height', textarea.offsetHeight);
        }
    });
    
    // 瑙︽懜璁惧鏀寔
    resizeHandle.addEventListener('touchstart', (e) => {
        e.preventDefault();
        const touch = e.touches[0];
        isDragging = true;
        startY = touch.clientY;
        startHeight = textarea.offsetHeight;
        
        resizeHandle.classList.add('dragging');
    });
    
    document.addEventListener('touchmove', (e) => {
        if (!isDragging) return;
        
        const touch = e.touches[0];
        const deltaY = startY - touch.clientY;
        let newHeight = startHeight + deltaY;
        
        newHeight = Math.max(60, Math.min(400, newHeight));
        textarea.style.height = newHeight + 'px';
    });
    
    document.addEventListener('touchend', () => {
        if (isDragging) {
            isDragging = false;
            resizeHandle.classList.remove('dragging');
            
            localStorage.setItem('copilot_input_height', textarea.offsetHeight);
        }
    });
    
    // 鍙屽嚮閲嶇疆涓洪粯璁ら珮搴?
    resizeHandle.addEventListener('dblclick', () => {
        textarea.style.height = '80px';
        localStorage.setItem('copilot_input_height', 80);
        showToast('杈撳叆妗嗗凡鎭㈠榛樿楂樺害');
    });
}

// 鍒濆鍖栨椂璋冪敤
document.addEventListener('DOMContentLoaded', () => {
    init();
    initCopilotEnhancements();
    initInputResizer();  // 鍒濆鍖栬緭鍏ユ鎷栧姩璋冩暣

    // 鏇挎崲鍙戦€佹寜閽簨浠?
    const sendBtn = document.getElementById('copilot-send-btn');
    if (sendBtn) {
        sendBtn.addEventListener('click', sendCopilotMessageWithMentions);
    }

    const input = document.getElementById('copilot-input-text');
    if (input) {
        input.addEventListener('keydown', (e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
                const popup = document.getElementById('mention-popup');
                if (popup && popup.classList.contains('hidden')) {
                    e.preventDefault();
                    sendCopilotMessageWithMentions();
                }
            }
        });
    }
});

