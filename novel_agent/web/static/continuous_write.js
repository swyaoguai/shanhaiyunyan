/**
 * 无限续写功能模块（独立版本）
 * 与多Agent写作完全分离，有独立的数据存储
 */

// ===== 无限续写状态 =====
const infiniteWriteState = {
    sessionId: 'infinite_' + Date.now(),
    isRunning: false,
    chapters: [],
    currentChapter: 0,
    totalWords: 0,
    selectedModel: '',
    selectedApiConfigId: '',
    summaryInterval: 10,
    pendingSummaries: [],
    globalApiConfig: null,
    apiConfigs: [],
    activeConfigId: '',
    showTrends: true,
    enableTrendsFusion: false,
    selectedTrendsPlatforms: ['toutiao', 'douyin'],
    config: {
        wordsPerChapter: 2500,
        autoSaveToKB: true
    }
};

// ===== 无限续写导航面板（左侧） =====
const IW_TREND_PLATFORMS = [
    { id: 'toutiao', name: 'Toutiao' },
    { id: 'douyin', name: 'Douyin' },
    { id: 'weibo', name: 'Weibo' },
    { id: 'zhihu', name: 'Zhihu' },
    { id: 'douban', name: 'Douban' },
    { id: 'weread', name: 'WeRead' },
    { id: 'bilibili', name: 'Bilibili' },
    { id: 'netease', name: 'Netease' },
    { id: 'tencent', name: 'Tencent' },
    { id: 'thepaper', name: 'ThePaper' },
    { id: 'gcores', name: 'Gcores' },
    { id: '36kr', name: '36Kr' },
    { id: 'sspai', name: 'SSPAI' },
    { id: 'ifanr', name: 'ifanr' },
    { id: 'juejin', name: 'Juejin' },
    { id: 'smzdm', name: 'SMZDM' }
];

function renderInfiniteWriteTrendPlatformOptions() {
    return IW_TREND_PLATFORMS.map((platform) => `
        <label style="display: flex; align-items: center; gap: 4px; font-size: 12px; cursor: pointer;">
            <input type="checkbox" class="iw-trend-platform" value="${platform.id}" ${infiniteWriteState.selectedTrendsPlatforms.includes(platform.id) ? 'checked' : ''}>
            ${platform.name}
        </label>
    `).join('');
}

function renderInfiniteWriteNavPanel() {
    const navList = document.getElementById('nav-list-container');
    if (!navList) return;
    
    navList.innerHTML = '';
    
    // 创作入口
    const startEntry = document.createElement('div');
    startEntry.className = 'list-item active';
    startEntry.style.cssText = 'background: linear-gradient(135deg, rgba(139, 92, 246, 0.15), rgba(99, 102, 241, 0.1)); border: 1px solid rgba(139, 92, 246, 0.3); margin: 4px 8px; border-radius: 8px;';
    startEntry.innerHTML = `
        <i class="ri-play-circle-line" style="color: #8b5cf6;"></i>
        <span style="font-weight: 500;">创作面板</span>
    `;
    startEntry.addEventListener('click', () => {
        navList.querySelectorAll('.list-item').forEach(el => el.classList.remove('active'));
        startEntry.classList.add('active');
        if (typeof renderInfiniteWriteInterface === 'function') {
            renderInfiniteWriteInterface();
        }
    });
    navList.appendChild(startEntry);
    
    // 分隔线
    const sep = document.createElement('div');
    sep.style.cssText = 'height: 1px; background: var(--border-color); margin: 12px 8px;';
    navList.appendChild(sep);
    
    // 章节列表标题
    const chapterTitle = document.createElement('div');
    chapterTitle.style.cssText = 'font-size: 11px; color: var(--text-secondary); padding: 8px 12px; opacity: 0.7; display: flex; align-items: center; justify-content: space-between;';
    chapterTitle.innerHTML = `
        <span>章节列表</span>
        <span id="iw-nav-total-words" style="font-size: 10px;">${infiniteWriteState.totalWords.toLocaleString()}字</span>
    `;
    navList.appendChild(chapterTitle);
    
    // 章节列表容器
    const chapterList = document.createElement('div');
    chapterList.id = 'iw-nav-chapter-list';
    chapterList.style.cssText = 'max-height: calc(100vh - 300px); overflow-y: auto;';
    navList.appendChild(chapterList);
    
    // 加载章节列表
    loadInfiniteWriteNavChapterList();
}

// ===== 加载导航栏章节列表 =====
function loadInfiniteWriteNavChapterList() {
    const container = document.getElementById('iw-nav-chapter-list');
    if (!container) return;
    
    // 从本地存储加载
    const savedData = localStorage.getItem('infinite_write_data');
    console.log('[InfiniteWrite] nav load: localStorage hit =', !!savedData);
    if (savedData) {
        try {
            const data = JSON.parse(savedData);
            infiniteWriteState.chapters = data.chapters || [];
            infiniteWriteState.totalWords = data.totalWords || 0;
            console.log('[InfiniteWrite] nav load: chapters =', infiniteWriteState.chapters.length, 'totalWords =', infiniteWriteState.totalWords);
        } catch (e) {
            console.error('[InfiniteWrite] 解析存储数据失败:', e);
        }
    }
    
    // 更新总字数显示
    const totalWordsEl = document.getElementById('iw-nav-total-words');
    if (totalWordsEl) {
        totalWordsEl.textContent = infiniteWriteState.totalWords.toLocaleString() + '字';
    }
    
    if (infiniteWriteState.chapters.length === 0) {
        container.innerHTML = `
            <div style="padding: 20px 12px; text-align: center; color: var(--text-secondary); font-size: 11px; opacity: 0.7;">
                <i class="ri-file-text-line" style="font-size: 24px; opacity: 0.3; display: block; margin-bottom: 8px;"></i>
                暂无创作内容<br>
                <span style="font-size: 10px;">点击上方开始创作</span>
            </div>
        `;
        return;
    }
    
    // 渲染章节列表
    container.innerHTML = infiniteWriteState.chapters.map((ch, index) => `
        <div class="iw-nav-chapter list-item" data-chapter="${index}" style="padding: 10px 12px; cursor: pointer;">
            <i class="ri-file-text-line" style="opacity: 0.5;"></i>
            <span style="flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: 12px;">
                第${ch.chapter_number}章 ${ch.title || ''}
            </span>
            <span style="color: var(--text-secondary); font-size: 10px; flex-shrink: 0;">
                ${(ch.word_count || 0).toLocaleString()}字            </span>
        </div>
    `).join('');
    
    // 绑定点击事件
    container.querySelectorAll('.iw-nav-chapter').forEach(item => {
        item.addEventListener('click', () => {
            container.querySelectorAll('.list-item').forEach(el => el.classList.remove('active'));
            item.classList.add('active');
            const index = parseInt(item.dataset.chapter);
            const chapter = infiniteWriteState.chapters[index];
            if (chapter) {
                showInfiniteWriteChapterPreview(chapter);
            }
        });
    });
}

// ===== 多Agent写作导航面板 =====
function renderMultiAgentWriteNavPanel() {
    const navList = document.getElementById('nav-list-container');
    if (!navList) return;
    
    navList.innerHTML = '';
    
    // 章节列表标题
    const chapterTitle = document.createElement('div');
    chapterTitle.style.cssText = 'font-size: 11px; color: var(--text-secondary); padding: 8px 12px; opacity: 0.7;';
    chapterTitle.textContent = '章节大纲（协作模式）';
    navList.appendChild(chapterTitle);

    const importEntry = document.createElement('div');
    importEntry.className = 'list-item';
    importEntry.style.cssText = 'display: flex; align-items: center; gap: 8px; margin: 4px 8px 10px 8px; padding: 10px 12px; border-radius: 8px; border: 1px solid rgba(34, 197, 94, 0.35); background: rgba(34, 197, 94, 0.12); cursor: pointer;';
    importEntry.innerHTML = `
        <i class="ri-upload-cloud-2-line" style="color: #22c55e;"></i>
        <span style="font-size: 12px; color: #22c55e; font-weight: 500;">导入小说文件</span>
    `;
    importEntry.addEventListener('click', () => {
        if (typeof showCollaborativeImportDialog === 'function') {
            showCollaborativeImportDialog();
        }
    });
    navList.appendChild(importEntry);
    
    // 渲染章节列表
    const chapters = (window.store && window.store.projectData && window.store.projectData.outline) || [];
    
    if (chapters.length === 0) {
        const emptyHint = document.createElement('div');
        emptyHint.style.cssText = 'padding: 20px 12px; text-align: center; color: var(--text-secondary); font-size: 12px;';
        emptyHint.innerHTML = `
            <p>暂无章节</p>
            <p style="font-size: 11px; margin-top: 8px; opacity: 0.7;">点击上方 + 添加章节</p>
        `;
        navList.appendChild(emptyHint);
    } else {
        chapters.forEach((ch, index) => {
            const div = document.createElement('div');
            div.className = 'list-item';
            div.style.cssText = 'display: flex; align-items: center; gap: 8px; padding: 10px 12px;';
            div.innerHTML = `
                <i class="ri-file-text-line" style="opacity: 0.6;"></i>
                <span style="flex: 1; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;">第${index + 1}章 ${ch.title || '无标题'}</span>
                <div class="item-actions" style="display: flex; gap: 4px; opacity: 0; transition: opacity 0.2s;">
                    <button class="edit-btn" title="编辑" style="background: none; border: none; color: var(--text-secondary); cursor: pointer; padding: 4px;">
                        <i class="ri-edit-line"></i>
                    </button>
                    <button class="delete-btn" title="删除" style="background: none; border: none; color: #ef4444; cursor: pointer; padding: 4px;">
                        <i class="ri-delete-bin-line"></i>
                    </button>
                </div>
            `;

            div.addEventListener('mouseenter', () => {
                div.querySelector('.item-actions').style.opacity = '1';
            });
            div.addEventListener('mouseleave', () => {
                div.querySelector('.item-actions').style.opacity = '0';
            });

            div.addEventListener('click', (e) => {
                if (!e.target.closest('.item-actions')) {
                    navList.querySelectorAll('.list-item').forEach(el => el.classList.remove('active'));
                    div.classList.add('active');
                    if (typeof openChapterEditor === 'function') {
                        openChapterEditor(index);
                    }
                }
            });

            div.querySelector('.edit-btn').addEventListener('click', (e) => {
                e.stopPropagation();
                if (typeof editChapterTitle === 'function') {
                    editChapterTitle(index);
                }
            });

            div.querySelector('.delete-btn').addEventListener('click', (e) => {
                e.stopPropagation();
                if (typeof deleteChapter === 'function') {
                    deleteChapter(index);
                }
            });

            navList.appendChild(div);
        });
    }
}

// ===== 加载无限续写章节列表 =====
async function loadInfiniteWriteChapterList() {
    const container = document.getElementById('infinite-write-chapter-list');
    if (!container) return;
    
    try {
        // 从本地存储加载
        const savedData = localStorage.getItem('infinite_write_data');
        console.log('[InfiniteWrite] list load: localStorage hit =', !!savedData);
        if (savedData) {
            const data = JSON.parse(savedData);
            infiniteWriteState.chapters = data.chapters || [];
            infiniteWriteState.totalWords = data.totalWords || 0;
            infiniteWriteState.currentChapter = data.currentChapter || 0;
            infiniteWriteState.selectedModel = data.selectedModel || '';
            infiniteWriteState.selectedApiConfigId = data.selectedApiConfigId || '';
            infiniteWriteState.summaryInterval = data.summaryInterval || 10;
            infiniteWriteState.pendingSummaries = data.pendingSummaries || [];
            infiniteWriteState.enableTrendsFusion = data.enableTrendsFusion || false;
            infiniteWriteState.selectedTrendsPlatforms = data.selectedTrendsPlatforms || ['toutiao', 'douyin'];
            console.log('[InfiniteWrite] list load: chapters =', infiniteWriteState.chapters.length, 'totalWords =', infiniteWriteState.totalWords);
        }
        
        if (infiniteWriteState.chapters.length === 0) {
            container.innerHTML = `
                <div style="padding: 12px; text-align: center; color: var(--text-secondary); font-size: 11px; opacity: 0.7;">
                    暂无创作内容
                </div>
            `;
            return;
        }
        
        // 渲染章节列表
        container.innerHTML = infiniteWriteState.chapters.map((ch, index) => `
            <div class="iw-chapter-item list-item" data-chapter="${index}" style="padding: 8px 12px; font-size: 12px; cursor: pointer;">
                <i class="ri-file-text-line" style="opacity: 0.5; margin-right: 6px;"></i>
                <span style="flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">
                    第${ch.chapter_number}章 ${ch.title || ''}
                </span>
                <span style="color: var(--text-secondary); font-size: 10px; margin-left: 4px;">
                    ${(ch.word_count || 0).toLocaleString()}字                </span>
            </div>
        `).join('');
        
        // 绑定点击事件
        container.querySelectorAll('.iw-chapter-item').forEach(item => {
            item.addEventListener('click', () => {
                const index = parseInt(item.dataset.chapter);
                const chapter = infiniteWriteState.chapters[index];
                if (chapter) {
                    showInfiniteWriteChapterPreview(chapter);
                }
            });
        });
        
    } catch (e) {
        console.error('[InfiniteWrite] 加载章节列表失败:', e);
    }
}

// ===== 无限续写界面 =====
async function renderInfiniteWriteInterface() {
    if (typeof updateBreadcrumbs === 'function') {
        updateBreadcrumbs(['仪表盘', '无限续写']);
    }
    
    const workspace = document.getElementById('main-view');
    if (!workspace) return;
    
    // 先加载全局API配置
    await loadGlobalApiConfigForInfiniteWrite();
    
    // 获取保存的模型或使用全局配置的模型
    let savedModel = infiniteWriteState.selectedModel || localStorage.getItem('infinite_write_model') || '';
    if (!savedModel && infiniteWriteState.globalApiConfig) {
        savedModel = infiniteWriteState.globalApiConfig.model || '';
    }
    
    // 检查全局配置状态
    const globalConfigured = infiniteWriteState.globalApiConfig && infiniteWriteState.globalApiConfig.is_configured;
    const globalModel = infiniteWriteState.globalApiConfig?.model || '';
    
    workspace.innerHTML = `
        <div style="max-width: 900px; margin: 0 auto; padding: 30px 20px;">
            <!-- 标题 -->
            <div style="text-align: center; margin-bottom: 30px;">
                <h1 style="font-size: 28px; color: var(--text-primary); margin-bottom: 10px; display: flex; align-items: center; justify-content: center; gap: 12px;">
                    <i class="ri-infinity-line" style="color: #8b5cf6;"></i>
                    无限续写
                </h1>
                <p style="color: var(--text-secondary); font-size: 14px;">基于灵感自动续写，独立于协作创作模式，拥有专属数据存储</p>
            </div>
            
            <!-- 全局API配置状态提示 -->
            ${!globalConfigured ? `
            <div style="background: rgba(239, 68, 68, 0.15); border: 1px solid rgba(239, 68, 68, 0.4); border-radius: 12px; padding: 16px; margin-bottom: 24px;">
                <div style="display: flex; align-items: center; gap: 12px;">
                    <i class="ri-error-warning-line" style="font-size: 24px; color: #ef4444;"></i>
                    <div>
                        <div style="font-weight: 500; color: #ef4444;">全局API未配置</div>
                        <div style="font-size: 13px; color: var(--text-secondary); margin-top: 4px;">
                            请先在 <a href="#" onclick="switchModule('settings'); loadSettingsTab('api'); return false;" style="color: #60a5fa; text-decoration: underline;">设置 > API配置</a> 中配置全局API，无限续写将使用全局API进行创作。                        </div>
                    </div>
                </div>
            </div>
            ` : ''}
            
            <!-- 模型选择和配置 -->
            <div style="background: rgba(255,255,255,0.03); border: 1px solid var(--border-color); border-radius: 12px; padding: 20px; margin-bottom: 24px;">
                <h3 style="margin-bottom: 16px; font-size: 15px; color: var(--text-primary); display: flex; align-items: center; gap: 8px;">
                    <i class="ri-settings-3-line"></i>
                    创作配置
                </h3>
                
                <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 16px; margin-bottom: 16px;">
                    <!-- API配置选择 -->
                    <div>
                        <label style="display: block; font-size: 12px; color: var(--text-secondary); margin-bottom: 8px;">
                            <i class="ri-server-line"></i> 选择API配置
                            ${globalConfigured ? `<span style="color: #10b981; font-size: 11px; margin-left: 8px;">✓ 已配置</span>` : ''}
                        </label>
                        <select id="iw-api-config-select" style="width: 100%; background: rgba(0,0,0,0.3); border: 1px solid var(--border-color); padding: 10px; color: var(--text-primary); border-radius: 6px; font-size: 13px; cursor: pointer;">
                            ${infiniteWriteState.apiConfigs.length === 0 ? '<option value="">-- 请先在设置中添加API配置 --</option>' : ''}
                            ${infiniteWriteState.apiConfigs.map(cfg => {
                                const isActive = cfg.id === infiniteWriteState.activeConfigId;
                                const isSelected = cfg.id === (infiniteWriteState.selectedApiConfigId || infiniteWriteState.activeConfigId);
                                let hostname = '未设置';
                                try { hostname = cfg.api_base ? new URL(cfg.api_base).hostname : '未设置'; } catch(e) {}
                                return `<option value="${cfg.id}" ${isSelected ? 'selected' : ''}>
                                    ${isActive ? '📌 ' : ''}${cfg.name} (${hostname})
                                </option>`;
                            }).join('')}
                        </select>
                    </div>
                    
                    <!-- 模型选择 -->
                    <div>
                        <label style="display: block; font-size: 12px; color: var(--text-secondary); margin-bottom: 8px;">
                            <i class="ri-robot-line"></i> 选择模型
                        </label>
                        <div style="display: flex; gap: 8px;">
                            <select id="iw-model-input" style="flex: 1; background: rgba(0,0,0,0.3); border: 1px solid var(--border-color); padding: 10px; color: var(--text-primary); border-radius: 6px; font-size: 13px;">
                                ${renderInfiniteWriteModelOptions(infiniteWriteState.selectedApiConfigId || infiniteWriteState.activeConfigId, savedModel)}
                            </select>
                            <button id="iw-custom-model-btn" style="padding: 10px 16px; background: rgba(255,255,255,0.1); border: 1px solid var(--border-color); color: var(--text-primary); border-radius: 6px; cursor: pointer; white-space: nowrap;" title="输入自定义模型名">
                                <i class="ri-edit-line"></i>
                            </button>
                        </div>
                        <div id="iw-custom-model-container" style="display: none; margin-top: 8px;">
                            <input type="text" id="iw-custom-model-input" value=""
                                placeholder="输入自定义模型名"
                                style="width: 100%; background: rgba(0,0,0,0.3); border: 1px solid var(--border-color); padding: 10px; color: var(--text-primary); border-radius: 6px; font-size: 13px;">
                        </div>
                    </div>
                </div>
                
                <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 16px;">
                    <!-- 每章字数 -->
                    <div>
                        <label style="display: block; font-size: 12px; color: var(--text-secondary); margin-bottom: 8px;">
                            <i class="ri-text"></i> 每章字数
                        </label>
                        <input type="number" id="iw-words-per-chapter" value="${infiniteWriteState.config.wordsPerChapter}" min="1000" max="5000"
                            style="width: 100%; background: rgba(0,0,0,0.3); border: 1px solid var(--border-color); padding: 10px; color: var(--text-primary); border-radius: 6px; font-size: 13px;">
                    </div>
                    
                    <!-- 总结间隔 -->
                    <div>
                        <label style="display: block; font-size: 12px; color: var(--text-secondary); margin-bottom: 8px;">
                            <i class="ri-file-list-line"></i> 总结间隔（章）                        </label>
                        <select id="iw-summary-interval" style="width: 100%; background: rgba(0,0,0,0.3); border: 1px solid var(--border-color); padding: 10px; color: var(--text-primary); border-radius: 6px; font-size: 13px;">
                            <option value="5" ${infiniteWriteState.summaryInterval === 5 ? 'selected' : ''}>5章</option>
                            <option value="10" ${infiniteWriteState.summaryInterval === 10 ? 'selected' : ''}>10章</option>
                            <option value="15" ${infiniteWriteState.summaryInterval === 15 ? 'selected' : ''}>15章</option>
                            <option value="20" ${infiniteWriteState.summaryInterval === 20 ? 'selected' : ''}>20章</option>
                        </select>
                    </div>
                </div>
            </div>
            
            <!-- 状态卡片 -->
            <div id="iw-status-card" style="background: rgba(255,255,255,0.03); border: 1px solid var(--border-color); border-radius: 12px; padding: 20px; margin-bottom: 24px;">
                <div style="display: flex; align-items: center; gap: 12px;">
                    <div id="iw-status-indicator" style="width: 12px; height: 12px; border-radius: 50%; background: ${infiniteWriteState.chapters.length > 0 ? '#f59e0b' : '#666'};"></div>
                    <span id="iw-status-text" style="color: var(--text-secondary);">
                        ${infiniteWriteState.chapters.length > 0 ? `已创作${infiniteWriteState.chapters.length}章，共${infiniteWriteState.totalWords.toLocaleString()}字` : '尚未开始，请输入故事开头'}
                    </span>
                    <div style="flex: 1;"></div>
                    <span id="iw-chapter-count" style="font-size: 13px; color: var(--text-secondary);"></span>
                </div>
            </div>
            
            <!-- 开始新故事区域（当没有章节时显示） -->
            <div id="iw-start-section" style="${infiniteWriteState.chapters.length > 0 ? 'display: none;' : ''} background: rgba(255,255,255,0.03); border: 1px solid var(--border-color); border-radius: 12px; padding: 24px; margin-bottom: 24px;">
                <h3 style="margin-bottom: 16px; font-size: 16px; color: var(--text-primary); display: flex; align-items: center; gap: 8px;">
                    <i class="ri-lightbulb-line" style="color: #f59e0b;"></i>
                    开始新故事
                </h3>
                
                <div style="margin-bottom: 20px;">
                    <label style="display: block; font-size: 12px; margin-bottom: 8px; color: var(--text-secondary);">
                        故事开头或灵感 <span style="color: #ef4444;">*</span>
                    </label>
                    <textarea id="iw-story-beginning" rows="6" placeholder="输入故事开头、创意灵感或简要设定...

例如：在一个被永恒迷雾笼罩的大陆上，年轻的猎魔人林风第一次踏出了村庄的边界..."
                        style="width: 100%; background: rgba(0,0,0,0.3); border: 1px solid var(--border-color); padding: 14px; color: var(--text-primary); border-radius: 8px; font-size: 14px; line-height: 1.6; resize: vertical;"></textarea>
                </div>
                
                <button id="iw-start-btn" style="width: 100%; padding: 14px; background: linear-gradient(135deg, #8b5cf6, #6366f1); border: none; color: white; border-radius: 8px; cursor: pointer; font-weight: 600; font-size: 15px;">
                    <i class="ri-play-circle-line"></i> 开始创作第一章                </button>
                <button id="iw-import-btn" style="width: 100%; margin-top: 10px; padding: 12px; background: rgba(34, 197, 94, 0.18); border: 1px solid rgba(34, 197, 94, 0.4); color: #22c55e; border-radius: 8px; cursor: pointer; font-weight: 500; font-size: 14px;">
                    <i class="ri-upload-cloud-2-line"></i> 导入已有小说（txt/md/docx）                </button>
            </div>
            
            <!-- 续写控制区域（当有章节时显示） -->
            <div id="iw-control-section" style="${infiniteWriteState.chapters.length === 0 ? 'display: none;' : ''} background: rgba(255,255,255,0.03); border: 1px solid var(--border-color); border-radius: 12px; padding: 24px; margin-bottom: 24px;">
                <h3 style="margin-bottom: 16px; font-size: 16px; color: var(--text-primary); display: flex; align-items: center; gap: 8px;">
                    <i class="ri-tools-line"></i>
                    续写控制
                </h3>
                
                <!-- 添加灵感 -->
                <div style="margin-bottom: 20px; padding: 16px; background: rgba(245, 158, 11, 0.1); border: 1px solid rgba(245, 158, 11, 0.3); border-radius: 8px;">
                    <label style="display: block; font-size: 13px; margin-bottom: 8px; color: #f59e0b; font-weight: 500;">
                        <i class="ri-lightbulb-flash-line"></i> 添加灵感（可选）
                    </label>
                    <textarea id="iw-inspiration" rows="2" placeholder="加入新灵感，会在下一章中自然融入..."
                        style="width: 100%; background: rgba(0,0,0,0.2); border: 1px solid var(--border-color); padding: 10px; color: var(--text-primary); border-radius: 6px; font-size: 13px; resize: vertical;"></textarea>
                </div>
                
                <!-- 剧情纠正 -->
                <div style="margin-bottom: 20px; padding: 16px; background: rgba(239, 68, 68, 0.1); border: 1px solid rgba(239, 68, 68, 0.3); border-radius: 8px;">
                    <label style="display: block; font-size: 13px; margin-bottom: 8px; color: #ef4444; font-weight: 500;">
                        <i class="ri-error-warning-line"></i> 剧情纠正（可选）
                    </label>
                    <textarea id="iw-correction" rows="2" placeholder="如果剧情走向不对，在这里纠正..."
                        style="width: 100%; background: rgba(0,0,0,0.2); border: 1px solid var(--border-color); padding: 10px; color: var(--text-primary); border-radius: 6px; font-size: 13px; resize: vertical;"></textarea>
                </div>
                
                <!-- 操作按钮 -->
                <div style="display: flex; gap: 12px; flex-wrap: wrap;">
                    <button id="iw-continue-btn" style="flex: 1; min-width: 200px; padding: 14px; background: linear-gradient(135deg, #22c55e, #10b981); border: none; color: white; border-radius: 8px; cursor: pointer; font-weight: 600; font-size: 15px;">
                        <i class="ri-play-line"></i> 续写下一章                    </button>
                    <button id="iw-import-btn-inline" style="padding: 14px 20px; background: rgba(34, 197, 94, 0.18); border: 1px solid rgba(34, 197, 94, 0.4); color: #22c55e; border-radius: 8px; cursor: pointer; font-weight: 500;">
                        <i class="ri-upload-cloud-2-line"></i> 导入小说
                    </button>
                    <button id="iw-finish-btn" style="padding: 14px 20px; background: linear-gradient(135deg, #8b5cf6, #6366f1); border: none; color: white; border-radius: 8px; cursor: pointer; font-weight: 500;">
                        <i class="ri-flag-line"></i> 完结故事
                    </button>
                    <button id="iw-reset-btn" style="padding: 14px 20px; background: rgba(239, 68, 68, 0.2); border: 1px solid rgba(239, 68, 68, 0.4); color: #ef4444; border-radius: 8px; cursor: pointer; font-weight: 500;">
                        <i class="ri-refresh-line"></i> 重置
                    </button>
                </div>
            </div>
            
            <!-- 待确认总结区域 -->
            <div id="iw-pending-summaries" style="display: none; background: rgba(100, 180, 255, 0.1); border: 1px solid rgba(100, 180, 255, 0.3); border-radius: 12px; padding: 20px; margin-bottom: 24px;">
                <h3 style="margin-bottom: 12px; font-size: 15px; color: #7dd3fc; display: flex; align-items: center; gap: 8px;">
                    <i class="ri-file-list-3-line"></i>
                    剧情总结待确认                </h3>
                <div id="iw-summary-content"></div>
            </div>
            
            <!-- 章节列表已移至左侧导航面板，此处不再重复显示 -->
            
            <!-- 热点灵感面板 -->
            <div id="iw-trends-container" style="${infiniteWriteState.showTrends ? '' : 'display: none;'} margin-top: 24px;">
                <div style="display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px;">
                    <h3 style="margin: 0; font-size: 16px; color: var(--text-primary); display: flex; align-items: center; gap: 8px;">
                        <i class="ri-fire-fill" style="color: #ef4444;"></i>
                        热点灵感
                    </h3>
                    <label style="display: flex; align-items: center; gap: 6px; font-size: 12px; color: var(--text-secondary); cursor: pointer;">
                        <input type="checkbox" id="iw-trends-toggle" ${infiniteWriteState.showTrends ? 'checked' : ''}
                            style="width: 14px; height: 14px; cursor: pointer;">
                        显示热点
                    </label>
                </div>
                <div id="iw-trends-panel">
                    <!-- 热点面板将在这里渲染 -->
                </div>
            </div>
            
            <!-- 使用提示 -->
            <div style="margin-top: 24px; background: rgba(100,180,255,0.1); border: 1px solid rgba(100,180,255,0.3); border-radius: 12px; padding: 20px;">
                <h3 style="margin-bottom: 12px; font-size: 14px; color: #7dd3fc;">💡 无限续写特点</h3>
                <ul style="font-size: 13px; color: var(--text-secondary); line-height: 1.8; padding-left: 20px; margin: 0;">
                    <li><strong>独立数据</strong>：与协作创作模式完全分离，有专属存储</li>
                    <li><strong>模型自选</strong>：可以选择不同的模型进行创作</li>
                    <li><strong>自动总结</strong>：每${infiniteWriteState.summaryInterval}章自动生成剧情总结</li>
                    <li><strong>自动向量化</strong>：配置向量模型后，保存章节时自动存入知识库</li>
                    <li><strong>剧情追踪</strong>：自动提取剧情约束，防止逻辑矛盾（如角色复活）</li>
                    <li><strong>热点灵感</strong>：获取实时热点，激发创作灵感</li>
                </ul>
            </div>
        </div>
    `;
    
    // 绑定事件
    bindInfiniteWriteEvents();
    
    // 更新左侧导航的章节列表
    loadInfiniteWriteNavChapterList();
    
    // 初始化热点面板
    initInfiniteWriteTrends();
}

// ===== 初始化热点面板 =====
async function initInfiniteWriteTrends() {
    // 加载热点配置
    if (typeof loadTrendsConfig === 'function') {
        await loadTrendsConfig();
    }
    
    // 检查热点服务状态
    if (typeof checkTrendsService === 'function') {
        await checkTrendsService();
    }
    
    // 检查是否在无限续写中显示热点
    if (typeof trendsState !== 'undefined' && trendsState.config) {
        infiniteWriteState.showTrends = trendsState.config.showInInfiniteWrite !== false;
    }
    
    // 渲染热点面板
    if (infiniteWriteState.showTrends && typeof renderTrendsPanel === 'function') {
        renderTrendsPanel('iw-trends-panel', {
            compact: false,
            showToggle: false,
            maxItems: 10,
            onSelect: (title, item) => {
                // 将热点作为灵感添加到输入框
                useHotTrendAsInspiration(title, item);
            }
        });
    }
    
    // 绑定热点开关事件
    const trendsToggle = document.getElementById('iw-trends-toggle');
    if (trendsToggle) {
        trendsToggle.addEventListener('change', (e) => {
            infiniteWriteState.showTrends = e.target.checked;
            const container = document.getElementById('iw-trends-container');
            if (container) {
                container.style.display = e.target.checked ? '' : 'none';
            }
            
            // 保存设置
            if (typeof saveTrendsVisibility === 'function') {
                saveTrendsVisibility(e.target.checked, trendsState?.config?.showInMultiAgent ?? true);
            }
            
            // 如果开启，渲染面板
            if (e.target.checked && typeof renderTrendsPanel === 'function') {
                renderTrendsPanel('iw-trends-panel', {
                    compact: false,
                    showToggle: false,
                    maxItems: 10,
                    onSelect: useHotTrendAsInspiration
                });
            }
        });
    }
}

// ===== 使用热点作为灵感 =====
function useHotTrendAsInspiration(title, item) {
    // 检查是否已开始创作
    if (infiniteWriteState.chapters.length === 0) {
        // 未开始，填入故事开头输入框
        const storyInput = document.getElementById('iw-story-beginning');
        if (storyInput) {
            const currentText = storyInput.value.trim();
            if (currentText) {
                storyInput.value = currentText + '\n\n【热点灵感】' + title;
            } else {
                storyInput.value = '【热点灵感】' + title + '\n\n请基于这个热点话题展开创作...';
            }
            storyInput.focus();
            showToast('热点已添加到故事开头 ✨');
        }
    } else {
        // 已开始创作，填入灵感输入框
        const inspirationInput = document.getElementById('iw-inspiration');
        if (inspirationInput) {
            const currentText = inspirationInput.value.trim();
            if (currentText) {
                inspirationInput.value = currentText + '\n' + title;
            } else {
                inspirationInput.value = title;
            }
            inspirationInput.focus();
            showToast('热点已添加到灵感输入框 ✨');
        }
    }
}

// ===== 加载所有API配置 =====
async function loadGlobalApiConfigForInfiniteWrite() {
    try {
        // 加载所有API配置
        const configsData = await apiCall('/api/api-configs', 'GET');
        infiniteWriteState.apiConfigs = configsData.configs || [];
        infiniteWriteState.activeConfigId = configsData.active_config_id || '';
        
        // 获取当前激活的配置
        const activeConfig = infiniteWriteState.apiConfigs.find(c => c.id === infiniteWriteState.activeConfigId);
        
        // 构建兼容的全局配置对象
        infiniteWriteState.globalApiConfig = {
            is_configured: infiniteWriteState.apiConfigs.length > 0 && activeConfig,
            model: configsData.active_model || (activeConfig?.models?.[0]) || '',
            api_base: activeConfig?.api_base || ''
        };
        
        // 如果没有选中的API配置，使用激活的配置
        if (!infiniteWriteState.selectedApiConfigId && infiniteWriteState.activeConfigId) {
            infiniteWriteState.selectedApiConfigId = infiniteWriteState.activeConfigId;
        }
        
        console.log('[InfiniteWrite] API配置已加载', infiniteWriteState.apiConfigs.length, '个配置，当前激活', infiniteWriteState.activeConfigId);
    } catch (e) {
        console.error('[InfiniteWrite] 加载API配置失败:', e);
        infiniteWriteState.globalApiConfig = null;
        infiniteWriteState.apiConfigs = [];
    }
}

// ===== 渲染模型选项 =====
function renderInfiniteWriteModelOptions(configId, selectedModel) {
    const config = infiniteWriteState.apiConfigs.find(c => c.id === configId);
    if (!config || !config.models || config.models.length === 0) {
        return '<option value="">-- 请先在该配置中添加模型 --</option>';
    }
    return config.models.map(model => `
        <option value="${model}" ${model === selectedModel ? 'selected' : ''}>${model}</option>
    `).join('');
}

// ===== 获取当前选择的API配置ID =====
function getSelectedApiConfigIdForInfiniteWrite() {
    const select = document.getElementById('iw-api-config-select');
    if (select && select.value) {
        return select.value;
    }
    
    if (infiniteWriteState.selectedApiConfigId) {
        return infiniteWriteState.selectedApiConfigId;
    }
    
    return infiniteWriteState.activeConfigId || '';
}

// ===== 绑定事件 =====
function bindInfiniteWriteEvents() {
    // API配置选择
    const apiConfigSelect = document.getElementById('iw-api-config-select');
    if (apiConfigSelect) {
        // 【修复】初始化时，如果没有选中的API配置，使用当前下拉框的值
        if (!infiniteWriteState.selectedApiConfigId && apiConfigSelect.value) {
            infiniteWriteState.selectedApiConfigId = apiConfigSelect.value;
            console.log('[InfiniteWrite] 初始化API配置ID:', apiConfigSelect.value);
        }
        
        apiConfigSelect.addEventListener('change', (e) => {
            const configId = e.target.value;
            infiniteWriteState.selectedApiConfigId = configId;
            
            // 更新模型列表
            const modelSelect = document.getElementById('iw-model-input');
            if (modelSelect) {
                modelSelect.innerHTML = renderInfiniteWriteModelOptions(configId, '');
                // 自动选择第一个模型
                if (modelSelect.options.length > 0 && modelSelect.options[0].value) {
                    infiniteWriteState.selectedModel = modelSelect.options[0].value;
                }
            }
            
            saveInfiniteWriteData();
            
            const config = infiniteWriteState.apiConfigs.find(c => c.id === configId);
            if (config) {
                showToast(`已选择: ${config.name}`);
            }
        });
    }
    
    // 自定义模型按钮
    const customModelBtn = document.getElementById('iw-custom-model-btn');
    if (customModelBtn) {
        customModelBtn.addEventListener('click', () => {
            const container = document.getElementById('iw-custom-model-container');
            if (container) {
                const isVisible = container.style.display !== 'none';
                container.style.display = isVisible ? 'none' : 'block';
                customModelBtn.innerHTML = isVisible ? '<i class="ri-edit-line"></i>' : '<i class="ri-close-line"></i>';
            }
        });
    }
    
    // 模型下拉选择
    const modelSelect = document.getElementById('iw-model-input');
    if (modelSelect && modelSelect.tagName === 'SELECT') {
        // 【修复】初始化时，如果 selectedModel 为空，但下拉框有选中值，则使用下拉框值。
        if (!infiniteWriteState.selectedModel && modelSelect.value) {
            infiniteWriteState.selectedModel = modelSelect.value;
            console.log('[InfiniteWrite] 初始化模型名:', modelSelect.value);
            saveInfiniteWriteData();
        }
        
        modelSelect.addEventListener('change', (e) => {
            infiniteWriteState.selectedModel = e.target.value;
            console.log('[InfiniteWrite] 用户切换模型:', e.target.value);
            saveInfiniteWriteData();
        });
    }
    
    // 自定义模型输入框
    const customModelInput = document.getElementById('iw-custom-model-input');
    if (customModelInput) {
        customModelInput.addEventListener('change', (e) => {
            const value = e.target.value.trim();
            if (value) {
                infiniteWriteState.selectedModel = value;
                // 添加到下拉列表
                const select = document.getElementById('iw-model-input');
                if (select) {
                    const option = document.createElement('option');
                    option.value = value;
                    option.textContent = value;
                    option.selected = true;
                    select.appendChild(option);
                }
                saveInfiniteWriteData();
                showToast(`已选择模型: ${value}`);
            }
        });
    }
    
    // 字数配置
    const wordsInput = document.getElementById('iw-words-per-chapter');
    if (wordsInput) {
        wordsInput.addEventListener('change', (e) => {
            infiniteWriteState.config.wordsPerChapter = parseInt(e.target.value) || 2500;
            saveInfiniteWriteData();
        });
    }
    
    // 总结间隔
    const intervalSelect = document.getElementById('iw-summary-interval');
    if (intervalSelect) {
        intervalSelect.addEventListener('change', (e) => {
            infiniteWriteState.summaryInterval = parseInt(e.target.value) || 10;
            saveInfiniteWriteData();
        });
    }
    
    // 开始创作
    const startBtn = document.getElementById('iw-start-btn');
    if (startBtn) {
        startBtn.addEventListener('click', startInfiniteWrite);
    }

    const importBtn = document.getElementById('iw-import-btn');
    if (importBtn) {
        importBtn.addEventListener('click', showInfiniteWriteImportDialog);
    }

    const importBtnInline = document.getElementById('iw-import-btn-inline');
    if (importBtnInline) {
        importBtnInline.addEventListener('click', showInfiniteWriteImportDialog);
    }
    
    // 续写
    const continueBtn = document.getElementById('iw-continue-btn');
    if (continueBtn) {
        continueBtn.addEventListener('click', continueInfiniteWrite);
    }
    
    // 重置
    const resetBtn = document.getElementById('iw-reset-btn');
    if (resetBtn) {
        resetBtn.addEventListener('click', resetInfiniteWrite);
    }
    
    // 完结故事
    const finishBtn = document.getElementById('iw-finish-btn');
    if (finishBtn) {
        finishBtn.addEventListener('click', showFinishStoryDialog);
    }
}

// ===== 获取当前选择的模型 =====
function getSelectedModelForInfiniteWrite() {
    // 优先使用自定义输入的模型
    const customInput = document.getElementById('iw-custom-model-input');
    if (customInput && customInput.value.trim()) {
        return customInput.value.trim();
    }
    
    // 使用下拉选择的模型
    const select = document.getElementById('iw-model-input');
    if (select && select.value) {
        return select.value;
    }
    
    // 使用保存的模型
    if (infiniteWriteState.selectedModel) {
        return infiniteWriteState.selectedModel;
    }
    
    // 使用全局配置的模型
    if (infiniteWriteState.globalApiConfig && infiniteWriteState.globalApiConfig.model) {
        return infiniteWriteState.globalApiConfig.model;
    }
    
    return '';
}

// ===== 开始创作 =====
async function startInfiniteWrite() {
    const storyBeginning = document.getElementById('iw-story-beginning')?.value.trim();
    const model = getSelectedModelForInfiniteWrite();
    const wordsPerChapter = parseInt(document.getElementById('iw-words-per-chapter')?.value) || 2500;
    
    if (!storyBeginning) {
        showToast('请输入故事开头或灵感', 'error');
        return;
    }
    
    if (!model) {
        showToast('请先在设置中配置全局API，或选择一个模型', 'error');
        return;
    }
    
    const btn = document.getElementById('iw-start-btn');
    
    // 设置运行状态
    infiniteWriteState.isRunning = true;
    
    if (btn) {
        btn.disabled = true;
        btn.innerHTML = '<i class="ri-loader-4-line" style="animation: spin 1s linear infinite;"></i> 正在创作第一章...';
    }
    
    // 更新状态指示器
    updateRunningStatus(true);
    
    try {
        // 重置状态
        infiniteWriteState.sessionId = 'infinite_' + Date.now();
        infiniteWriteState.chapters = [];
        infiniteWriteState.currentChapter = 0;
        infiniteWriteState.totalWords = 0;
        infiniteWriteState.selectedModel = model;
        infiniteWriteState.config.wordsPerChapter = wordsPerChapter;
        
        // 获取选中的API配置ID
        const apiConfigId = getSelectedApiConfigIdForInfiniteWrite();
        
        // 调用后端API
        const result = await apiCall('/api/continuous-write/start', 'POST', {
            story_beginning: storyBeginning,
            session_id: infiniteWriteState.sessionId,
            words_per_chapter: wordsPerChapter,
            model: model,
            api_config_id: apiConfigId,
            enable_trends: infiniteWriteState.enableTrendsFusion,
            trends_platforms: infiniteWriteState.selectedTrendsPlatforms,
            trends_query: storyBeginning.substring(0, 100) // 使用故事开头作为搜索关键词
        });
        
        if (result.success && result.chapter) {
            showToast('第一章创作完成！请预览后确认是否保留 ✨');
            
            // 先显示预览，让用户确认后才保存到章节列表
            showInfiniteWriteChapterPreviewWithConfirm(result.chapter, true);
        } else {
            // 显示详细错误信息
            const errorMsg = result.error || '未知错误';
            showInfiniteWriteError('创作失败', errorMsg);
        }
    } catch (e) {
        console.error('[InfiniteWrite] 开始创作失败:', e);
        showInfiniteWriteError('请求失败', e.message || '未知错误');
    } finally {
        // 恢复运行状态
        infiniteWriteState.isRunning = false;
        updateRunningStatus(false);
        
        // 恢复按钮状态
        const startBtn = document.getElementById('iw-start-btn');
        if (startBtn) {
            startBtn.disabled = false;
            startBtn.innerHTML = '<i class="ri-play-circle-line"></i> 开始创作第一章';
        }
    }
}

function showInfiniteWriteImportDialog() {
    const modal = document.getElementById('modal-container');
    if (!modal) return;

    const hasExisting = Array.isArray(infiniteWriteState.chapters) && infiniteWriteState.chapters.length > 0;
    modal.classList.remove('hidden');
    modal.innerHTML = `
        <div style="position: fixed; inset: 0; background: rgba(0,0,0,0.65); display: flex; align-items: center; justify-content: center; z-index: 1000; padding: 20px;">
            <div style="width: 560px; max-width: 100%; background: var(--bg-panel); border: 1px solid var(--border-color); border-radius: 14px; padding: 24px;">
                <h3 style="margin: 0 0 14px 0; color: var(--text-primary); font-size: 18px; display: flex; align-items: center; gap: 8px;">
                    <i class="ri-upload-cloud-2-line"></i>
                    导入小说到无限续写
                </h3>
                <p style="margin: 0 0 12px 0; color: var(--text-secondary); font-size: 13px; line-height: 1.7;">
                    支持 <code>.txt</code> / <code>.md</code> / <code>.docx</code>，导入后会立即自动整理无限续写记忆。
                </p>
                ${hasExisting ? `
                <div style="margin-bottom: 12px; padding: 10px; border-radius: 8px; background: rgba(239,68,68,0.12); border: 1px solid rgba(239,68,68,0.3); color: #fca5a5; font-size: 12px;">
                    当前已存有 ${infiniteWriteState.chapters.length} 章内容。导入后将切换到新的续写会话。
                </div>` : ''}

                <div style="margin-bottom: 18px;">
                    <label style="display: block; margin-bottom: 6px; font-size: 12px; color: var(--text-secondary);">选择文件</label>
                    <input id="iw-import-file" type="file" accept=".txt,.md,.docx"
                        style="width: 100%; background: rgba(0,0,0,0.2); border: 1px solid var(--border-color); border-radius: 8px; padding: 10px; color: var(--text-primary);">
                </div>

                <div style="display: flex; gap: 10px;">
                    <button id="iw-import-cancel" style="flex: 1; padding: 11px; border-radius: 8px; border: 1px solid var(--border-color); background: rgba(255,255,255,0.1); color: var(--text-primary); cursor: pointer;">取消</button>
                    <button id="iw-import-confirm" style="flex: 1; padding: 11px; border-radius: 8px; border: none; background: linear-gradient(135deg, #22c55e, #16a34a); color: #fff; font-weight: 600; cursor: pointer;">开始导入</button>
                </div>
            </div>
        </div>
    `;

    const closeModal = () => {
        modal.classList.add('hidden');
        modal.innerHTML = '';
    };

    document.getElementById('iw-import-cancel')?.addEventListener('click', closeModal);
    document.getElementById('iw-import-confirm')?.addEventListener('click', async () => {
        const fileInput = document.getElementById('iw-import-file');
        const btn = document.getElementById('iw-import-confirm');
        const file = fileInput?.files?.[0];
        if (!file) {
            showToast('请先选择文件', 'warning');
            return;
        }

        btn.disabled = true;
        btn.innerHTML = '<i class="ri-loader-4-line" style="animation: spin 1s linear infinite;"></i> 导入中...';

        try {
            const nextSessionId = 'infinite_' + Date.now();
            const formData = new FormData();
            formData.append('novel_file', file);
            formData.append('session_id', nextSessionId);

            const response = await apiFormCall('/api/continuous-write/import', formData, 'POST');
            if (!response.success) {
                throw new Error(response.error || '导入失败');
            }

            infiniteWriteState.sessionId = response.session_id || nextSessionId;
            infiniteWriteState.chapters = Array.isArray(response.chapters) ? response.chapters : [];
            infiniteWriteState.currentChapter = response.current_chapter || infiniteWriteState.chapters.length;
            infiniteWriteState.totalWords = response.total_words || 0;
            infiniteWriteState.pendingSummaries = [];
            infiniteWriteState.isRunning = false;

            saveInfiniteWriteData();
            closeModal();
            renderInfiniteWriteInterface();
            showToast(`已导入 ${response.imported_chapters || 0} 章，记忆整理完成`, 'success');
        } catch (e) {
            showToast(`导入失败: ${e.message}`, 'error');
        } finally {
            btn.disabled = false;
            btn.innerHTML = '开始导入';
        }
    });
}

// ===== 续写下一章 =====
async function continueInfiniteWrite() {
    const inspiration = document.getElementById('iw-inspiration')?.value.trim() || '';
    const correction = document.getElementById('iw-correction')?.value.trim() || '';
    const model = getSelectedModelForInfiniteWrite();
    
    if (!model) {
        showToast('请先在设置中配置全局API，或选择一个模型', 'error');
        return;
    }
    
    const btn = document.getElementById('iw-continue-btn');
    const originalBtnHtml = btn ? btn.innerHTML : '';
    
    // 设置运行状态
    infiniteWriteState.isRunning = true;
    
    if (btn) {
        btn.disabled = true;
        btn.innerHTML = '<i class="ri-loader-4-line" style="animation: spin 1s linear infinite;"></i> 续写中...';
    }
    
    // 更新状态指示器
    updateRunningStatus(true);
    
    try {
        // 如果有纠正内容，先添加
        if (correction) {
            try {
                await apiCall('/api/continuous-write/correction', 'POST', {
                    session_id: infiniteWriteState.sessionId,
                    correction: correction
                });
            } catch (e) {
                // 忽略会话不存在错误，后续会重新初始化
                console.log('[InfiniteWrite] 添加纠正时会话可能不存在，继续执行');
            }
        }
        
        // 获取选中的API配置ID
        const apiConfigId = getSelectedApiConfigIdForInfiniteWrite();
        
        // 尝试续写
        let result;
        try {
            result = await apiCall('/api/continuous-write/continue', 'POST', {
                session_id: infiniteWriteState.sessionId,
                inspiration: inspiration,
                model: model,
                api_config_id: apiConfigId,
                enable_trends: infiniteWriteState.enableTrendsFusion,
                trends_platforms: infiniteWriteState.selectedTrendsPlatforms
            });
        } catch (continueError) {
            // 如果会话不存在，尝试重新初始化
            if (continueError.message && (continueError.message.includes('会话不存在') || continueError.message.includes('404'))) {
                console.log('[InfiniteWrite] 会话不存在，尝试重新初始化...');
                showToast('会话已过期，正在恢复会话...', 'info');
                
                // 从现有章节构建上下文
                const lastChapter = infiniteWriteState.chapters[infiniteWriteState.chapters.length - 1];
                const currentChapterCount = infiniteWriteState.chapters.length;
                
                // 构建更完整的上下文，包含最近章节的关键信息
                let storyContext = `【会话恢复 - 续写第${currentChapterCount + 1}章】\n`;
                storyContext += `已完成${currentChapterCount}章，共${infiniteWriteState.totalWords.toLocaleString()}字。\n\n`;
                
                if (lastChapter) {
                    storyContext += `【最近一章摘要】\n`;
                    storyContext += `第${lastChapter.chapter_number}章 ${lastChapter.title || ''}\n`;
                    storyContext += lastChapter.content ? lastChapter.content.substring(0, 1500) : '';
                    storyContext += '\n\n';
                }
                
                if (inspiration) {
                    storyContext += `【新灵感】${inspiration}\n`;
                }
                
                // 重新开始会话，传递当前章节号和完整章节数据以便正确续写
                // 关键修复：传递 recovered_chapters，确保后端有完整上下文
                const startResult = await apiCall('/api/continuous-write/start', 'POST', {
                    story_beginning: storyContext,
                    session_id: infiniteWriteState.sessionId,
                    words_per_chapter: infiniteWriteState.config.wordsPerChapter,
                    model: model,
                    api_config_id: apiConfigId,
                    current_chapter: currentChapterCount,  // 当前章节数
                    recovered_chapters: infiniteWriteState.chapters  // 关键：传递完整章节数据，确保上下文连贯
                });
                
                if (startResult.success && startResult.chapter) {
                    result = startResult;
                    showToast(`会话已恢复，正在创作第${startResult.chapter.chapter_number}章`, 'success');
                } else {
                    throw new Error(startResult.error || '重新初始化失败');
                }
            } else {
                throw continueError;
            }
        }
        
        if (result.success && result.chapter) {
            showToast(`第${result.chapter.chapter_number}章创作完成！请预览后确认是否保留 ✨`);
            
            // 清空输入框
            const inspirationEl = document.getElementById('iw-inspiration');
            const correctionEl = document.getElementById('iw-correction');
            if (inspirationEl) inspirationEl.value = '';
            if (correctionEl) correctionEl.value = '';
            
            // 先显示预览，让用户确认后才保存到章节列表
            showInfiniteWriteChapterPreviewWithConfirm(result.chapter, false);
        } else {
            // 显示详细错误信息
            const errorMsg = result.error || '未知错误';
            showInfiniteWriteError('续写失败', errorMsg);
        }
    } catch (e) {
        console.error('[InfiniteWrite] 续写失败:', e);
        showInfiniteWriteError('请求失败', e.message || '未知错误');
    } finally {
        // 恢复运行状态
        infiniteWriteState.isRunning = false;
        updateRunningStatus(false);
        
        // 恢复按钮状态
        const continueBtn = document.getElementById('iw-continue-btn');
        if (continueBtn) {
            continueBtn.disabled = false;
            continueBtn.innerHTML = '<i class="ri-play-line"></i> 续写下一章';
        }
    }
}

// ===== 更新运行状态指示器 =====
function updateRunningStatus(isRunning) {
    const indicator = document.getElementById('iw-status-indicator');
    const statusText = document.getElementById('iw-status-text');
    
    if (isRunning) {
        if (indicator) {
            indicator.style.background = '#f59e0b';
            indicator.style.animation = 'pulse 1.5s ease-in-out infinite';
        }
        if (statusText) {
            const chapterCount = infiniteWriteState.chapters.length;
            statusText.innerHTML = `<i class="ri-loader-4-line" style="animation: spin 1s linear infinite;"></i> 正在创作第${chapterCount + 1}章...`;
        }
    } else {
        if (indicator) {
            indicator.style.animation = 'none';
            indicator.style.background = infiniteWriteState.chapters.length > 0 ? '#22c55e' : '#666';
        }
        if (statusText) {
            statusText.textContent = infiniteWriteState.chapters.length > 0
                ? `已创作${infiniteWriteState.chapters.length}章，共${infiniteWriteState.totalWords.toLocaleString()}字`
                : '尚未开始，请输入故事开头';
        }
    }
}

// ===== 检查并生成总结 =====
async function checkAndGenerateSummary() {
    const chapterCount = infiniteWriteState.chapters.length;
    const interval = infiniteWriteState.summaryInterval;
    
    // 检查是否到达总结节点
    if (chapterCount > 0 && chapterCount % interval === 0) {
        const startChapter = chapterCount - interval + 1;
        const endChapter = chapterCount;
        
        showToast(`正在生成第${startChapter}-${endChapter}章的剧情总结...`, 'info');
        
        try {
            // 获取这些章节的内容
            const chaptersToSummarize = infiniteWriteState.chapters.slice(-interval);
            const content = chaptersToSummarize.map(ch =>
                `第${ch.chapter_number}章 ${ch.title || ''}\n${ch.content || ''}`
            ).join('\n\n---\n\n');
            
            // 调用API生成总结
            const result = await apiCall('/api/chat', 'POST', {
                message: `请为以下${interval}章内容生成一个简洁的剧情总结，包括：
1. 主要剧情发展
2. 重要角色变化
3. 关键事件
4. 遗留伏笔

章节内容：
${content.substring(0, 8000)}`,
                session_id: 'summary_' + Date.now()
            });
            
            if (result.reply) {
                // 显示待确认总结
                showPendingSummary({
                    startChapter,
                    endChapter,
                    content: result.reply,
                    timestamp: Date.now()
                });
            }
        } catch (e) {
            console.error('[InfiniteWrite] 生成总结失败:', e);
        }
    }
}

// ===== 显示待确认总结 =====
function showPendingSummary(summary) {
    infiniteWriteState.pendingSummaries.push(summary);
    saveInfiniteWriteData();
    
    const container = document.getElementById('iw-pending-summaries');
    const contentEl = document.getElementById('iw-summary-content');
    
    if (!container || !contentEl) return;
    
    container.style.display = 'block';
    
    contentEl.innerHTML = `
        <div style="background: rgba(0,0,0,0.2); border-radius: 8px; padding: 16px; margin-bottom: 12px;">
            <div style="font-weight: 500; color: var(--text-primary); margin-bottom: 8px;">
                第${summary.startChapter}-${summary.endChapter}章剧情总结
            </div>
            <div style="font-size: 13px; color: var(--text-secondary); line-height: 1.6; white-space: pre-wrap;">
                ${summary.content}
            </div>
        </div>
        <div style="display: flex; gap: 12px;">
            <button id="confirm-summary-btn" style="flex: 1; padding: 10px; background: linear-gradient(135deg, #22c55e, #10b981); border: none; color: white; border-radius: 6px; cursor: pointer; font-weight: 500;">
                <i class="ri-check-line"></i> 确认并存入知识库
            </button>
            <button id="edit-summary-btn" style="padding: 10px 20px; background: rgba(255,255,255,0.1); border: 1px solid var(--border-color); color: var(--text-primary); border-radius: 6px; cursor: pointer;">
                <i class="ri-edit-line"></i> 编辑
            </button>
            <button id="skip-summary-btn" style="padding: 10px 20px; background: rgba(239, 68, 68, 0.2); border: 1px solid rgba(239, 68, 68, 0.4); color: #ef4444; border-radius: 6px; cursor: pointer;">
                <i class="ri-close-line"></i> 跳过
            </button>
        </div>
    `;
    
    // 绑定事件
    document.getElementById('confirm-summary-btn')?.addEventListener('click', () => confirmSummary(summary));
    document.getElementById('skip-summary-btn')?.addEventListener('click', () => skipSummary(summary));
    document.getElementById('edit-summary-btn')?.addEventListener('click', () => editSummary(summary));

    const hint = document.createElement('div');
    hint.style.cssText = 'margin-top: 10px; font-size: 12px; color: var(--text-secondary); opacity: 0.85;';
    hint.textContent = '提示：点击“确认并存入知识库”后才会真正写入，跳过不会保存。';
    contentEl.appendChild(hint);
}

// ===== 确认总结并存入知识库 =====
async function confirmSummary(summary) {
    const btn = document.getElementById('confirm-summary-btn');
    if (btn) {
        btn.disabled = true;
        btn.innerHTML = '<i class="ri-loader-4-line"></i> 存储中...';
    }
    
    try {
        // 调用知识库API存储
        const result = await apiCall('/api/knowledge-base/infinite-summary', 'POST', {
            summary: summary.content,
            start_chapter: summary.startChapter,
            end_chapter: summary.endChapter,
            chapter_id: summary.id || ''
        });

        if (!result || result.success !== true) {
            throw new Error((result && result.error) || '知识库存储失败');
        }
        
        // 从待确认列表移除
        infiniteWriteState.pendingSummaries = infiniteWriteState.pendingSummaries.filter(
            s => s.timestamp !== summary.timestamp
        );
        
        showToast('剧情总结已存入知识库 ✨', 'success');
        
        // 隐藏确认区域
        const container = document.getElementById('iw-pending-summaries');
        if (container) container.style.display = 'none';
        
    } catch (e) {
        const msg = (e && e.message) ? e.message : '未知错误';
        if (msg.includes('未配置') || msg.includes('暂不可用') || msg.includes('503')) {
            showToast('知识库未就绪：当前总结仅保留在本地，可稍后重试', 'warning');
        } else {
            showToast('存储失败: ' + msg, 'error');
        }
    } finally {
        if (btn) {
            btn.disabled = false;
            btn.innerHTML = '<i class="ri-check-line"></i> 确认并存入知识库';
        }
    }
}

// ===== 跳过总结 =====
function skipSummary(summary) {
    infiniteWriteState.pendingSummaries = infiniteWriteState.pendingSummaries.filter(
        s => s.timestamp !== summary.timestamp
    );
    saveInfiniteWriteData();
    
    const container = document.getElementById('iw-pending-summaries');
    if (container) container.style.display = 'none';
    
    showToast('已跳过此次总结');
}

// ===== 编辑总结 =====
function editSummary(summary) {
    const contentEl = document.getElementById('iw-summary-content');
    if (!contentEl) return;
    
    contentEl.innerHTML = `
        <div style="margin-bottom: 12px;">
            <div style="font-weight: 500; color: var(--text-primary); margin-bottom: 8px;">
                编辑第${summary.startChapter}-${summary.endChapter}章剧情总结
            </div>
            <textarea id="edit-summary-textarea" rows="10" style="width: 100%; background: rgba(0,0,0,0.3); border: 1px solid var(--border-color); padding: 12px; color: var(--text-primary); border-radius: 8px; font-size: 13px; line-height: 1.6; resize: vertical;">${summary.content}</textarea>
        </div>
        <div style="display: flex; gap: 12px;">
            <button id="save-edited-summary-btn" style="flex: 1; padding: 10px; background: linear-gradient(135deg, #22c55e, #10b981); border: none; color: white; border-radius: 6px; cursor: pointer; font-weight: 500;">
                <i class="ri-save-line"></i> 保存并存入知识库
            </button>
            <button id="cancel-edit-summary-btn" style="padding: 10px 20px; background: rgba(255,255,255,0.1); border: 1px solid var(--border-color); color: var(--text-primary); border-radius: 6px; cursor: pointer;">
                <i class="ri-close-line"></i> 取消
            </button>
        </div>
    `;
    
    document.getElementById('save-edited-summary-btn')?.addEventListener('click', () => {
        const textarea = document.getElementById('edit-summary-textarea');
        if (textarea) {
            summary.content = textarea.value;
            saveInfiniteWriteData();
            confirmSummary(summary);
        }
    });
    
    document.getElementById('cancel-edit-summary-btn')?.addEventListener('click', () => {
        showPendingSummary(summary);
    });
}

// ===== 重置无限续写 =====
function resetInfiniteWrite() {
    if (!confirm('确定要重置吗？\n\n这将清除所有已创作的章节，此操作不可撤销。')) {
        return;
    }
    
    // 重置状态
    infiniteWriteState.sessionId = 'infinite_' + Date.now();
    infiniteWriteState.chapters = [];
    infiniteWriteState.currentChapter = 0;
    infiniteWriteState.totalWords = 0;
    infiniteWriteState.pendingSummaries = [];
    
    // 清除本地存储
    localStorage.removeItem('infinite_write_data');
    
    showToast('已重置，可以开始新故事');
    
    // 刷新界面
    renderInfiniteWriteInterface();
    loadInfiniteWriteChapterList();
}

// ===== 更新界面状态 =====
function updateInfiniteWriteUI() {
    // 更新状态指示器
    const indicator = document.getElementById('iw-status-indicator');
    const statusText = document.getElementById('iw-status-text');
    
    if (indicator) {
        indicator.style.background = infiniteWriteState.chapters.length > 0 ? '#22c55e' : '#666';
    }
    
    if (statusText) {
        statusText.textContent = infiniteWriteState.chapters.length > 0
            ? `已创作${infiniteWriteState.chapters.length}章，共${infiniteWriteState.totalWords.toLocaleString()}字`
            : '尚未开始，请输入故事开头';
    }
    
    // 显示/隐藏区域
    const startSection = document.getElementById('iw-start-section');
    const controlSection = document.getElementById('iw-control-section');
    
    if (startSection) startSection.style.display = infiniteWriteState.chapters.length === 0 ? 'block' : 'none';
    if (controlSection) controlSection.style.display = infiniteWriteState.chapters.length > 0 ? 'block' : 'none';
    
    // 更新左侧导航的总字数和章节列表
    loadInfiniteWriteNavChapterList();
}

// ===== 渲染章节列表 =====
function renderInfiniteWriteChaptersList() {
    const container = document.getElementById('iw-chapters-list');
    if (!container) return;
    
    if (infiniteWriteState.chapters.length === 0) {
        container.innerHTML = '<div style="text-align: center; color: var(--text-secondary); padding: 20px;">暂无章节</div>';
        return;
    }
    
    container.innerHTML = infiniteWriteState.chapters.map(ch => `
        <div class="iw-chapter-card" data-chapter="${ch.chapter_number}" style="background: rgba(255,255,255,0.03); border: 1px solid var(--border-color); border-radius: 8px; padding: 16px; cursor: pointer; transition: all 0.2s;">
            <div style="display: flex; align-items: center; gap: 12px;">
                <span style="font-weight: 600; color: var(--text-primary);">第${ch.chapter_number}章</span>
                <span style="color: var(--text-secondary); font-size: 13px;">${ch.title || ''}</span>
                <div style="flex: 1;"></div>
                <span style="font-size: 12px; color: var(--text-secondary);">${(ch.word_count || 0).toLocaleString()} 字</span>
            </div>
            <p style="margin-top: 10px; font-size: 13px; color: var(--text-secondary); line-height: 1.6; max-height: 40px; overflow: hidden; text-overflow: ellipsis;">
                ${ch.summary || (ch.content ? ch.content.substring(0, 100) : '') || ''}
            </p>
        </div>
    `).join('');
    
    // 绑定点击事件
    container.querySelectorAll('.iw-chapter-card').forEach(card => {
        card.addEventListener('click', () => {
            const chapterNum = parseInt(card.dataset.chapter);
            const chapter = infiniteWriteState.chapters.find(ch => ch.chapter_number === chapterNum);
            if (chapter) {
                showInfiniteWriteChapterPreview(chapter);
            }
        });
        card.addEventListener('mouseenter', () => {
            card.style.borderColor = 'var(--accent-color)';
            card.style.background = 'rgba(139, 92, 246, 0.1)';
        });
        card.addEventListener('mouseleave', () => {
            card.style.borderColor = 'var(--border-color)';
            card.style.background = 'rgba(255,255,255,0.03)';
        });
    });
}

function recomputeInfiniteWriteStats() {
    let total = 0;
    let maxChapter = 0;
    infiniteWriteState.chapters.forEach(ch => {
        total += ch.word_count || 0;
        if (ch.chapter_number && ch.chapter_number > maxChapter) {
            maxChapter = ch.chapter_number;
        }
    });
    infiniteWriteState.totalWords = total;
    infiniteWriteState.currentChapter = maxChapter;
}

async function syncInfiniteWriteSession(deletedChapters = []) {
    try {
        await apiCall('/api/continuous-write/sync', 'POST', {
            session_id: infiniteWriteState.sessionId,
            chapters: infiniteWriteState.chapters,
            current_chapter: infiniteWriteState.currentChapter,
            deleted_chapters: deletedChapters
        });
    } catch (e) {
        console.warn('[InfiniteWrite] 同步会话失败:', e);
    }
}

async function deleteInfiniteWriteChapterFrom(chapterNumber) {
    const idx = infiniteWriteState.chapters.findIndex(ch => ch.chapter_number === chapterNumber);
    if (idx === -1) {
        showToast(`未找到第${chapterNumber}章`, 'error');
        return;
    }
    
    const removed = infiniteWriteState.chapters.slice(idx);
    const removedNumbers = removed.map(ch => ch.chapter_number).filter(n => typeof n === 'number');
    
    infiniteWriteState.chapters = infiniteWriteState.chapters.slice(0, idx);
    recomputeInfiniteWriteStats();
    saveInfiniteWriteData();
    
    updateInfiniteWriteUI();
    renderInfiniteWriteChaptersList();
    loadInfiniteWriteChapterList();
    loadInfiniteWriteNavChapterList();
    
    await syncInfiniteWriteSession(removedNumbers);
    
    showToast(`已删除第${chapterNumber}章及之后的章节`);
}

async function regenerateInfiniteWriteChapter(chapterNumber) {
    const model = getSelectedModelForInfiniteWrite();
    if (!model) {
        showToast('请先在设置中配置全局API，或选择一个模型', 'error');
        return;
    }
    
    const apiConfigId = getSelectedApiConfigIdForInfiniteWrite();
    const inspiration = document.getElementById('iw-inspiration')?.value.trim() || '';
    
    const backup = {
        chapters: [...infiniteWriteState.chapters],
        currentChapter: infiniteWriteState.currentChapter,
        totalWords: infiniteWriteState.totalWords
    };
    
    const idx = infiniteWriteState.chapters.findIndex(ch => ch.chapter_number === chapterNumber);
    if (idx === -1) {
        showToast(`未找到第${chapterNumber}章`, 'error');
        return;
    }
    
    const removed = infiniteWriteState.chapters.slice(idx);
    const removedNumbers = removed.map(ch => ch.chapter_number).filter(n => typeof n === 'number');
    
    infiniteWriteState.chapters = infiniteWriteState.chapters.slice(0, idx);
    recomputeInfiniteWriteStats();
    saveInfiniteWriteData();
    
    updateInfiniteWriteUI();
    renderInfiniteWriteChaptersList();
    loadInfiniteWriteChapterList();
    loadInfiniteWriteNavChapterList();
    
    await syncInfiniteWriteSession(removedNumbers);
    
    try {
        const result = await apiCall('/api/continuous-write/regenerate', 'POST', {
            session_id: infiniteWriteState.sessionId,
            chapter_number: chapterNumber,
            inspiration: inspiration,
            model: model,
            api_config_id: apiConfigId,
            enable_trends: infiniteWriteState.enableTrendsFusion,
            trends_platforms: infiniteWriteState.selectedTrendsPlatforms
        });
        
        if (result.success && result.chapter) {
            showToast(`第${chapterNumber}章已重新生成，请确认后保留✨`);
            const isFirst = chapterNumber === 1;
            showInfiniteWriteChapterPreviewWithConfirm(result.chapter, isFirst);
            return;
        }
        
        throw new Error(result.error || '重新生成失败');
    } catch (e) {
        infiniteWriteState.chapters = backup.chapters;
        infiniteWriteState.currentChapter = backup.currentChapter;
        infiniteWriteState.totalWords = backup.totalWords;
        saveInfiniteWriteData();
        
        updateInfiniteWriteUI();
        renderInfiniteWriteChaptersList();
        loadInfiniteWriteChapterList();
        loadInfiniteWriteNavChapterList();
        
        showInfiniteWriteError('重新生成失败', e.message);
    }
}

async function regeneratePreviewChapter(chapterNumber, isFirstChapter) {
    const model = getSelectedModelForInfiniteWrite();
    if (!model) {
        showToast('请先在设置中配置全局API，或选择一个模型', 'error');
        return;
    }

    const apiConfigId = getSelectedApiConfigIdForInfiniteWrite();
    const inspiration = document.getElementById('iw-inspiration')?.value.trim() || '';

    try {
        const result = await apiCall('/api/continuous-write/regenerate', 'POST', {
            session_id: infiniteWriteState.sessionId,
            chapter_number: chapterNumber,
            inspiration: inspiration,
            model: model,
            api_config_id: apiConfigId,
            enable_trends: infiniteWriteState.enableTrendsFusion,
            trends_platforms: infiniteWriteState.selectedTrendsPlatforms
        });

        if (result.success && result.chapter) {
            showToast(`第${chapterNumber}章已重新生成，请确认后保留✨`);
            showInfiniteWriteChapterPreviewWithConfirm(result.chapter, isFirstChapter);
            return;
        }

        throw new Error(result.error || '重新生成失败');
    } catch (e) {
        showInfiniteWriteError('重新生成失败', e.message);
    }
}

// ===== 显示章节预览（带确认选项，用于新创作的章节） =====
function showInfiniteWriteChapterPreviewWithConfirm(chapter, isFirstChapter = false) {
    console.log('[InfiniteWrite] preview confirm open:', {
        chapterNumber: chapter.chapter_number,
        isFirstChapter: isFirstChapter
    });
    const modal = document.getElementById('modal-container');
    if (!modal) return;
    
    modal.classList.remove('hidden');
    
    modal.innerHTML = `
        <div style="position: fixed; top: 0; left: 0; right: 0; bottom: 0; background: rgba(0,0,0,0.7); display: flex; align-items: center; justify-content: center; z-index: 1000; padding: 20px;">
            <div style="background: var(--bg-panel); border: 1px solid var(--border-color); border-radius: 16px; width: 800px; max-width: 100%; max-height: 90vh; display: flex; flex-direction: column;">
                <div style="padding: 20px; border-bottom: 1px solid var(--border-color); display: flex; align-items: center; gap: 12px;">
                    <div style="background: rgba(245, 158, 11, 0.2); padding: 6px 12px; border-radius: 20px; font-size: 12px; color: #f59e0b;">
                        <i class="ri-eye-line"></i> 预览
                    </div>
                    <h2 style="margin: 0; font-size: 18px; color: var(--text-primary);">
                        第${chapter.chapter_number}章 ${chapter.title || ''}
                    </h2>
                    <span style="font-size: 13px; color: var(--text-secondary);">${(chapter.word_count || 0).toLocaleString()} 字</span>
                    <div style="flex: 1;"></div>
                </div>
                <div style="flex: 1; overflow-y: auto; padding: 24px;">
                    <div style="font-size: 15px; color: var(--text-primary); line-height: 2; white-space: pre-wrap;">${chapter.content || '暂无内容'}</div>
                </div>
                ${chapter.important_events || chapter.new_characters ? `
                <div style="padding: 16px 24px; border-top: 1px solid var(--border-color); background: rgba(0,0,0,0.2);">
                    <div style="font-size: 12px; color: var(--text-secondary);">
                        ${chapter.important_events ? `<p><strong>重要事件：</strong>${chapter.important_events}</p>` : ''}
                        ${chapter.new_characters && chapter.new_characters !== '无' ? `<p><strong>新增角色：</strong>${chapter.new_characters}</p>` : ''}
                    </div>
                </div>
                ` : ''}
                <div style="padding: 16px 24px; border-top: 1px solid var(--border-color); background: rgba(139, 92, 246, 0.05);">
                    <p style="margin: 0 0 12px 0; font-size: 13px; color: var(--text-secondary);">
                        <i class="ri-information-line"></i> 请确认是否保留这一章到无限续写列表。                    </p>
                    <div style="display: flex; gap: 12px; justify-content: flex-end; flex-wrap: wrap;">
                        <button id="iw-discard-btn" style="padding: 10px 20px; background: rgba(239, 68, 68, 0.15); border: 1px solid rgba(239, 68, 68, 0.4); color: #ef4444; border-radius: 8px; cursor: pointer; font-weight: 500;">
                            <i class="ri-delete-bin-line"></i> 放弃本章
                        </button>
                        <button id="iw-keep-btn" style="padding: 10px 20px; background: linear-gradient(135deg, #8b5cf6, #6366f1); border: none; color: white; border-radius: 8px; cursor: pointer; font-weight: 500;">
                            <i class="ri-check-line"></i> 保留到列表                        </button>
                        <button id="iw-regenerate-preview-btn" style="padding: 10px 20px; background: rgba(245, 158, 11, 0.15); border: 1px solid rgba(245, 158, 11, 0.4); color: #f59e0b; border-radius: 8px; cursor: pointer; font-weight: 500;">
                            <i class="ri-refresh-line"></i> 重新生成本章
                        </button>
                    </div>
                </div>
            </div>
        </div>
    `;
    console.log('[InfiniteWrite] preview confirm open:', {
        chapterNumber: chapter.chapter_number,
        isFirstChapter: isFirstChapter
    });
    
    // 放弃本章
    document.getElementById('iw-discard-btn')?.addEventListener('click', () => {
        if (confirm('确定要放弃这一章吗？内容将不会被保存。')) {
            modal.classList.add('hidden');
            modal.innerHTML = '';
            showToast('已放弃本章，可以重新创作');
        }
    });
    
    // 保留到列表
    document.getElementById('iw-keep-btn')?.addEventListener('click', () => {
        // 保存章节到无限续写列表
        infiniteWriteState.chapters.push(chapter);
        infiniteWriteState.currentChapter = chapter.chapter_number;
        infiniteWriteState.totalWords += chapter.word_count || 0;
        saveInfiniteWriteData();
        
        // 更新界面
        updateInfiniteWriteUI();
        renderInfiniteWriteChaptersList();
        loadInfiniteWriteChapterList();
        
        // 检查是否需要生成总结（仅非第一章）
        if (!isFirstChapter) {
            checkAndGenerateSummary();
        }
        
        modal.classList.add('hidden');
        modal.innerHTML = '';
        showToast(`第${chapter.chapter_number}章已保留到列表 ✓`);
    });
    
    // 重新生成本章（预览态）
    document.getElementById('iw-regenerate-preview-btn')?.addEventListener('click', async () => {
        const chapterNumber = chapter.chapter_number;
        console.log('[InfiniteWrite] preview regenerate click:', {
            chapterNumber: chapterNumber,
            isFirstChapter: isFirstChapter
        });
        modal.classList.add('hidden');
        modal.innerHTML = '';
        await regeneratePreviewChapter(chapterNumber, isFirstChapter);
    });
}

// ===== 显示章节预览（用于查看已保存的章节） =====
function showInfiniteWriteChapterPreview(chapter) {
    const modal = document.getElementById('modal-container');
    if (!modal) return;
    
    modal.classList.remove('hidden');
    
    modal.innerHTML = `
        <div style="position: fixed; top: 0; left: 0; right: 0; bottom: 0; background: rgba(0,0,0,0.7); display: flex; align-items: center; justify-content: center; z-index: 1000; padding: 20px;">
            <div style="background: var(--bg-panel); border: 1px solid var(--border-color); border-radius: 16px; width: 800px; max-width: 100%; max-height: 90vh; display: flex; flex-direction: column;">
                <div style="padding: 20px; border-bottom: 1px solid var(--border-color); display: flex; align-items: center; gap: 12px;">
                    <h2 style="margin: 0; font-size: 18px; color: var(--text-primary);">
                        第${chapter.chapter_number}章 ${chapter.title || ''}
                    </h2>
                    <span style="font-size: 13px; color: var(--text-secondary);">${(chapter.word_count || 0).toLocaleString()} 字</span>
                    <div style="flex: 1;"></div>
                    <button id="close-iw-preview" style="background: none; border: none; color: var(--text-secondary); font-size: 24px; cursor: pointer; padding: 4px;">
                        <i class="ri-close-line"></i>
                    </button>
                </div>
                <div style="flex: 1; overflow-y: auto; padding: 24px;">
                    <div style="font-size: 15px; color: var(--text-primary); line-height: 2; white-space: pre-wrap;">${chapter.content || '暂无内容'}</div>
                </div>
                ${chapter.important_events || chapter.new_characters ? `
                <div style="padding: 16px 24px; border-top: 1px solid var(--border-color); background: rgba(0,0,0,0.2);">
                    <div style="font-size: 12px; color: var(--text-secondary);">
                        ${chapter.important_events ? `<p><strong>重要事件：</strong>${chapter.important_events}</p>` : ''}
                        ${chapter.new_characters && chapter.new_characters !== '无' ? `<p><strong>新增角色：</strong>${chapter.new_characters}</p>` : ''}
                    </div>
                </div>
                ` : ''}
                <div style="padding: 16px 24px; border-top: 1px solid var(--border-color); display: flex; gap: 12px; justify-content: flex-end; flex-wrap: wrap;">
                    <div style="display: flex; gap: 12px; flex-wrap: wrap;">
                        <button id="iw-delete-chapter-btn" style="padding: 10px 20px; background: rgba(239, 68, 68, 0.15); border: 1px solid rgba(239, 68, 68, 0.4); color: #ef4444; border-radius: 8px; cursor: pointer; font-weight: 500;">
                            <i class="ri-delete-bin-line"></i> 删除本章及之后章节                        </button>
                        <button id="iw-regenerate-chapter-btn" style="padding: 10px 20px; background: rgba(245, 158, 11, 0.15); border: 1px solid rgba(245, 158, 11, 0.4); color: #f59e0b; border-radius: 8px; cursor: pointer; font-weight: 500;">
                            <i class="ri-refresh-line"></i> 重新生成本章
                        </button>
                    </div>
                </div>
            </div>
        </div>
    `;
    
    document.getElementById('close-iw-preview')?.addEventListener('click', () => {
        modal.classList.add('hidden');
        modal.innerHTML = '';
    });
    
    
    // 删除本章及之后章节
    document.getElementById('iw-delete-chapter-btn')?.addEventListener('click', async () => {
        const confirmed = confirm(`确定要删除第${chapter.chapter_number}章及之后章节吗？\n\n此操作不可撤销。`);
        if (!confirmed) return;
        modal.classList.add('hidden');
        modal.innerHTML = '';
        await deleteInfiniteWriteChapterFrom(chapter.chapter_number);
    });
    
    // 重新生成本章
    document.getElementById('iw-regenerate-chapter-btn')?.addEventListener('click', async () => {
        const confirmed = confirm(`确定要重新生成第${chapter.chapter_number}章吗？\n\n将删除本章及之后章节并重新生成。`);
        if (!confirmed) return;
        modal.classList.add('hidden');
        modal.innerHTML = '';
        await regenerateInfiniteWriteChapter(chapter.chapter_number);
    });
    
    // 点击背景关闭
    modal.addEventListener('click', (e) => {
        if (e.target === modal.firstElementChild) {
            modal.classList.add('hidden');
            modal.innerHTML = '';
        }
    });
}

// ===== 保存章节到项目 =====
async function saveChapterToProject(chapter) {
    try {
        // 获取当前项目的大纲数量
        const outlineRes = await apiCall('/api/project-data/outline', 'GET');
        let outline = outlineRes.data || [];
        console.log('[InfiniteWrite] saveToProject:', {
            projectId: store?.currentProject,
            outlineLen: outline.length,
            chapterNumber: chapter.chapter_number,
            chapterIndex: chapter.chapter_number - 1,
            exists: !!outline[chapter.chapter_number - 1],
            existingTitle: outline[chapter.chapter_number - 1]?.title || ''
        });
        
        const chapterNum = chapter.chapter_number;
        const chapterIndex = chapterNum - 1;
        
        // 准备章节数据
        const chapterData = {
            title: chapter.title || `第${chapterNum}章`,
            summary: chapter.summary || '',
            content: chapter.content || '',
            word_count: chapter.word_count || 0,
            created_from: 'infinite_write',
            created_at: new Date().toISOString()
        };
        
        // 检查章节是否已存在
        if (outline[chapterIndex]) {
            console.log('[InfiniteWrite] saveToProject: chapter exists, ask overwrite');
            // 章节已存在，询问是否覆盖
            const overwrite = confirm(`第${chapterNum}章已存在，是否覆盖？\n\n现有标题：${outline[chapterIndex].title}\n新标题：${chapterData.title}`);
            if (!overwrite) {
                showToast('已取消保存');
                return;
            }
            outline[chapterIndex] = chapterData;
            showToast(`已覆盖第${chapterNum}章`);
        } else {
            // 章节不存在，需要填充中间的空白章节
            while (outline.length < chapterIndex) {
                outline.push({
                    title: `第${outline.length + 1}章`,
                    summary: '',
                    content: '',
                    word_count: 0,
                    placeholder: true
                });
            }
            outline.push(chapterData);
            showToast(`已创建并保存第${chapterNum}章 ✓`);
        }
        
        // 保存到项目
        await apiCall('/api/project-data/outline', 'POST', { data: outline });
        
        // 刷新项目数据
        if (window.store && window.store.projectData) {
            window.store.projectData.outline = outline;
        }
        
    } catch (e) {
        showToast('保存失败: ' + e.message, 'error');
        console.error('[InfiniteWrite] 保存章节到项目失败', e);
    }
}


// ===== 保存数据到本地存储 =====
function saveInfiniteWriteData() {
    const data = {
        sessionId: infiniteWriteState.sessionId,
        chapters: infiniteWriteState.chapters,
        currentChapter: infiniteWriteState.currentChapter,
        totalWords: infiniteWriteState.totalWords,
        selectedModel: infiniteWriteState.selectedModel,
        selectedApiConfigId: infiniteWriteState.selectedApiConfigId,
        summaryInterval: infiniteWriteState.summaryInterval,
        pendingSummaries: infiniteWriteState.pendingSummaries,
        enableTrendsFusion: infiniteWriteState.enableTrendsFusion,
        selectedTrendsPlatforms: infiniteWriteState.selectedTrendsPlatforms,
        config: infiniteWriteState.config
    };
    
    const payload = JSON.stringify(data);
    console.log('[InfiniteWrite] save: chapters =', data.chapters?.length || 0, 'totalWords =', data.totalWords || 0, 'payloadBytes =', payload.length);
    localStorage.setItem('infinite_write_data', payload);
    localStorage.setItem('infinite_write_model', infiniteWriteState.selectedModel);
}

// ===== 导出函数供全局使用 =====
window.renderMultiAgentWriteNavPanel = renderMultiAgentWriteNavPanel;
window.renderInfiniteWriteNavPanel = renderInfiniteWriteNavPanel;
window.loadInfiniteWriteChapterList = loadInfiniteWriteChapterList;
window.loadInfiniteWriteNavChapterList = loadInfiniteWriteNavChapterList;
window.renderInfiniteWriteInterface = renderInfiniteWriteInterface;
window.showInfiniteWriteChapterPreview = showInfiniteWriteChapterPreview;
window.showInfiniteWriteChapterPreviewWithConfirm = showInfiniteWriteChapterPreviewWithConfirm;
window.deleteInfiniteWriteChapterFrom = deleteInfiniteWriteChapterFrom;
window.regenerateInfiniteWriteChapter = regenerateInfiniteWriteChapter;

// 兼容旧版
window.renderWriteNavPanel = renderMultiAgentWriteNavPanel;
window.showContinuousWriteInterface = renderInfiniteWriteInterface;

// ===== 错误提示对话框 =====
function showInfiniteWriteError(title, message) {
    const modal = document.getElementById('modal-container');
    if (!modal) {
        showToast(`${title}: ${message}`, 'error');
        return;
    }
    
    modal.classList.remove('hidden');
    
    // 判断是否是连接错误，给出更详细的提示
    let detailHint = '';
    if (message.toLowerCase().includes('connection') || message.toLowerCase().includes('timeout')) {
        detailHint = `
            <div style="margin-top: 16px; padding: 12px; background: rgba(245, 158, 11, 0.15); border: 1px solid rgba(245, 158, 11, 0.4); border-radius: 8px;">
                <div style="font-weight: 500; color: #f59e0b; margin-bottom: 8px;">
                    <i class="ri-lightbulb-line"></i> 可能的原因
                </div>
                <ul style="font-size: 13px; color: var(--text-secondary); line-height: 1.8; padding-left: 18px; margin: 0;">
                    <li>API服务器暂时不可用或网络不稳定</li>
                    <li>API Key无效或已过期</li>
                    <li>模型名称不正确</li>
                    <li>代理/VPN配置问题</li>
                </ul>
                <div style="margin-top: 12px; font-size: 13px;">
                    <strong>解决方法：</strong>请到 <a href="#" onclick="switchModule('settings'); return false;" style="color: #60a5fa;">设置 > 全局API配置</a> 检查配置是否正确，或尝试更换模型。
                </div>
            </div>
        `;
    }
    
    modal.innerHTML = `
        <div style="position: fixed; top: 0; left: 0; right: 0; bottom: 0; background: rgba(0,0,0,0.7); display: flex; align-items: center; justify-content: center; z-index: 1000; padding: 20px;">
            <div style="background: var(--bg-panel); border: 1px solid rgba(239, 68, 68, 0.5); border-radius: 16px; width: 500px; max-width: 100%; padding: 24px;">
                <div style="display: flex; align-items: center; gap: 12px; margin-bottom: 16px;">
                    <div style="width: 48px; height: 48px; background: rgba(239, 68, 68, 0.2); border-radius: 12px; display: flex; align-items: center; justify-content: center;">
                        <i class="ri-error-warning-line" style="font-size: 24px; color: #ef4444;"></i>
                    </div>
                    <div>
                        <h3 style="margin: 0; font-size: 18px; color: #ef4444;">${title}</h3>
                        <p style="margin: 4px 0 0 0; font-size: 13px; color: var(--text-secondary);">创作过程中发生错误</p>
                    </div>
                </div>
                
                <div style="background: rgba(0,0,0,0.2); border-radius: 8px; padding: 16px; margin-bottom: 16px;">
                    <div style="font-size: 14px; color: var(--text-primary); word-break: break-word;">
                        <code style="background: rgba(239, 68, 68, 0.2); padding: 2px 8px; border-radius: 4px; color: #fca5a5;">${escapeHtml(message)}</code>
                    </div>
                </div>
                
                ${detailHint}
                
                <div style="display: flex; gap: 12px; margin-top: 20px;">
                    <button id="iw-error-close" style="flex: 1; padding: 12px; background: rgba(255,255,255,0.1); border: 1px solid var(--border-color); color: var(--text-primary); border-radius: 8px; cursor: pointer;">
                        关闭
                    </button>
                    <button id="iw-error-retry" style="flex: 1; padding: 12px; background: var(--accent-color); border: none; color: white; border-radius: 8px; cursor: pointer; font-weight: 500;">
                        <i class="ri-refresh-line"></i> 重试
                    </button>
                </div>
            </div>
        </div>
    `;
    
    document.getElementById('iw-error-close')?.addEventListener('click', () => {
        modal.classList.add('hidden');
        modal.innerHTML = '';
    });
    
    document.getElementById('iw-error-retry')?.addEventListener('click', () => {
        modal.classList.add('hidden');
        modal.innerHTML = '';
        // 重试创作
        if (infiniteWriteState.chapters.length === 0) {
            startInfiniteWrite();
        } else {
            continueInfiniteWrite();
        }
    });
}

// ===== 完结故事对话框 =====
function showFinishStoryDialog() {
    if (infiniteWriteState.chapters.length === 0) {
        showToast('还没有创作任何章节，无法完结', 'error');
        return;
    }
    
    const modal = document.getElementById('modal-container');
    if (!modal) return;
    
    modal.classList.remove('hidden');
    
    modal.innerHTML = `
        <div style="position: fixed; top: 0; left: 0; right: 0; bottom: 0; background: rgba(0,0,0,0.7); display: flex; align-items: center; justify-content: center; z-index: 1000; padding: 20px;">
            <div style="background: var(--bg-panel); border: 1px solid var(--border-color); border-radius: 16px; width: 600px; max-width: 100%; max-height: 90vh; overflow: hidden; display: flex; flex-direction: column;">
                <div style="padding: 20px; border-bottom: 1px solid var(--border-color);">
                    <h2 style="margin: 0; font-size: 20px; color: var(--text-primary); display: flex; align-items: center; gap: 10px;">
                        <i class="ri-flag-line" style="color: #8b5cf6;"></i>
                        完结故事
                    </h2>
                    <p style="margin: 8px 0 0 0; font-size: 13px; color: var(--text-secondary);">
                        将所有已创作章节保存到新项目，并清空无限续写数据
                    </p>
                </div>
                
                <div style="flex: 1; overflow-y: auto; padding: 20px;">
                    <!-- 统计信息 -->
                    <div style="background: rgba(139, 92, 246, 0.1); border: 1px solid rgba(139, 92, 246, 0.3); border-radius: 12px; padding: 16px; margin-bottom: 20px;">
                        <div style="display: grid; grid-template-columns: repeat(3, 1fr); gap: 16px; text-align: center;">
                            <div>
                                <div style="font-size: 28px; font-weight: bold; color: #8b5cf6;">${infiniteWriteState.chapters.length}</div>
                                <div style="font-size: 12px; color: var(--text-secondary);">总章节</div>
                            </div>
                            <div>
                                <div style="font-size: 28px; font-weight: bold; color: #10b981;">${infiniteWriteState.totalWords.toLocaleString()}</div>
                                <div style="font-size: 12px; color: var(--text-secondary);">总字数</div>
                            </div>
                            <div>
                                <div style="font-size: 28px; font-weight: bold; color: #f59e0b;">${Math.round(infiniteWriteState.totalWords / Math.max(infiniteWriteState.chapters.length, 1)).toLocaleString()}</div>
                                <div style="font-size: 12px; color: var(--text-secondary);">平均每章</div>
                            </div>
                        </div>
                    </div>
                    
                    <!-- 选项 -->
                    <div style="margin-bottom: 20px;">
                        <label style="display: block; font-size: 14px; color: var(--text-primary); margin-bottom: 8px; font-weight: 500;">
                            <i class="ri-save-line"></i> 保存方式
                        </label>
                        <div style="display: flex; flex-direction: column; gap: 12px;">
                            <label style="display: flex; align-items: flex-start; gap: 12px; padding: 16px; background: rgba(255,255,255,0.03); border: 1px solid var(--border-color); border-radius: 8px; cursor: pointer; transition: all 0.2s;" id="finish-option-new">
                                <input type="radio" name="finish-option" value="new" checked style="margin-top: 4px;">
                                <div>
                                    <div style="font-weight: 500; color: var(--text-primary);">创建新项目</div>
                                    <div style="font-size: 12px; color: var(--text-secondary); margin-top: 4px;">将所有章节保存到一个新的小说项目中</div>
                                </div>
                            </label>
                            <label style="display: flex; align-items: flex-start; gap: 12px; padding: 16px; background: rgba(255,255,255,0.03); border: 1px solid var(--border-color); border-radius: 8px; cursor: pointer; transition: all 0.2s;" id="finish-option-current">
                                <input type="radio" name="finish-option" value="current" style="margin-top: 4px;">
                                <div>
                                    <div style="font-weight: 500; color: var(--text-primary);">追加到当前项目</div>
                                    <div style="font-size: 12px; color: var(--text-secondary); margin-top: 4px;">将章节追加到当前项目「${store.currentProjectName || '未命名'}」的章节列表中</div>
                                </div>
                            </label>
                        </div>
                    </div>
                    
                    <!-- 新项目名称输入 -->
                    <div id="new-project-input-section">
                        <label style="display: block; font-size: 14px; color: var(--text-primary); margin-bottom: 8px; font-weight: 500;">
                            <i class="ri-book-2-line"></i> 新项目名称                        </label>
                        <input type="text" id="finish-project-name"
                            value="${getDefaultProjectName()}"
                            placeholder="输入项目名称..."
                            style="width: 100%; background: rgba(0,0,0,0.3); border: 1px solid var(--border-color); padding: 12px; color: var(--text-primary); border-radius: 8px; font-size: 14px;">
                    </div>
                    
                    <!-- 清除选项 -->
                    <div style="margin-top: 20px; padding: 16px; background: rgba(245, 158, 11, 0.1); border: 1px solid rgba(245, 158, 11, 0.3); border-radius: 8px;">
                        <label style="display: flex; align-items: center; gap: 12px; cursor: pointer;">
                            <input type="checkbox" id="finish-clear-data" checked style="width: 18px; height: 18px; cursor: pointer;">
                            <div>
                                <div style="font-weight: 500; color: var(--text-primary);">保存后清空无限续写数据</div>
                                <div style="font-size: 12px; color: var(--text-secondary); margin-top: 4px;">
                                    <i class="ri-information-line"></i> 建议勾选，以便开始新的创作                                </div>
                            </div>
                        </label>
                    </div>
                </div>
                
                <div style="padding: 16px 20px; border-top: 1px solid var(--border-color); display: flex; gap: 12px;">
                    <button id="finish-cancel-btn" style="flex: 1; padding: 12px; background: rgba(255,255,255,0.1); border: 1px solid var(--border-color); color: var(--text-primary); border-radius: 8px; cursor: pointer; font-size: 14px;">
                        取消
                    </button>
                    <button id="finish-confirm-btn" style="flex: 1; padding: 12px; background: linear-gradient(135deg, #8b5cf6, #6366f1); border: none; color: white; border-radius: 8px; cursor: pointer; font-weight: 600; font-size: 14px;">
                        <i class="ri-save-line"></i> 确认完结
                    </button>
                </div>
            </div>
        </div>
    `;
    
    // 绑定事件
    const optionNew = document.querySelector('input[value="new"]');
    const optionCurrent = document.querySelector('input[value="current"]');
    const newProjectSection = document.getElementById('new-project-input-section');
    
    const updateOptionStyles = () => {
        const newOption = document.getElementById('finish-option-new');
        const currentOption = document.getElementById('finish-option-current');
        if (optionNew.checked) {
            newOption.style.borderColor = 'var(--accent-color)';
            newOption.style.background = 'rgba(139, 92, 246, 0.1)';
            currentOption.style.borderColor = 'var(--border-color)';
            currentOption.style.background = 'rgba(255,255,255,0.03)';
            newProjectSection.style.display = 'block';
        } else {
            currentOption.style.borderColor = 'var(--accent-color)';
            currentOption.style.background = 'rgba(139, 92, 246, 0.1)';
            newOption.style.borderColor = 'var(--border-color)';
            newOption.style.background = 'rgba(255,255,255,0.03)';
            newProjectSection.style.display = 'none';
        }
    };
    
    updateOptionStyles();
    optionNew.addEventListener('change', updateOptionStyles);
    optionCurrent.addEventListener('change', updateOptionStyles);
    
    // 取消按钮
    document.getElementById('finish-cancel-btn')?.addEventListener('click', () => {
        modal.classList.add('hidden');
        modal.innerHTML = '';
    });
    
    // 确认完结按钮
    document.getElementById('finish-confirm-btn')?.addEventListener('click', async () => {
        await executeFinishStory();
    });
}

// 获取默认项目名称
function getDefaultProjectName() {
    const firstChapter = infiniteWriteState.chapters[0];
    if (firstChapter && firstChapter.title) {
        // 使用第一章的标题作为项目名
        return firstChapter.title.replace(/[第一二三四五六七八九十\d]+章\s*/, '').trim() || '我的新小说';
    }
    // 默认使用日期
    const now = new Date();
    return `无限续写_${now.getFullYear()}${String(now.getMonth()+1).padStart(2,'0')}${String(now.getDate()).padStart(2,'0')}`;
}

// 执行完结故事
async function executeFinishStory() {
    const modal = document.getElementById('modal-container');
    const confirmBtn = document.getElementById('finish-confirm-btn');
    
    if (confirmBtn) {
        confirmBtn.disabled = true;
        confirmBtn.innerHTML = '<i class="ri-loader-4-line" style="animation: spin 1s linear infinite;"></i> 保存中...';
    }
    
    try {
        const isNewProject = document.querySelector('input[name="finish-option"]:checked')?.value === 'new';
        const clearData = document.getElementById('finish-clear-data')?.checked ?? true;
        const projectName = document.getElementById('finish-project-name')?.value?.trim() || getDefaultProjectName();
        
        let targetProjectId = store.currentProject;
        
        if (isNewProject) {
            // 创建新项目
            const result = await apiCall('/api/projects', 'POST', {
                name: projectName,
                description: `从无限续写模式导入，共${infiniteWriteState.chapters.length}章，${infiniteWriteState.totalWords.toLocaleString()}字`
            });
            
            if (result.success && result.project) {
                targetProjectId = result.project.id;
                // 添加到项目列表
                store.projects.push(result.project);
            } else {
                throw new Error('创建项目失败');
            }
        }
        
        // 切换到目标项目
        if (targetProjectId !== store.currentProject) {
            await apiCall(`/api/projects/${targetProjectId}/switch`, 'POST');
            store.currentProject = targetProjectId;
            store.currentProjectId = targetProjectId;
        }
        
        // 获取目标项目的现有大纲数
        const outlineRes = await apiCall('/api/project-data/outline', 'GET');
        let outline = outlineRes.data || [];
        const startIndex = outline.length;
        
        // 将无限续写的章节添加到大纲
        for (let i = 0; i < infiniteWriteState.chapters.length; i++) {
            const ch = infiniteWriteState.chapters[i];
            outline.push({
                title: ch.title || `第${startIndex + i + 1}章`,
                summary: ch.summary || '',
                content: ch.content || '',
                word_count: ch.word_count || 0,
                created_from: 'infinite_write',
                created_at: ch.created_at || new Date().toISOString()
            });
        }
        
        // 保存大纲
        await apiCall('/api/project-data/outline', 'POST', { data: outline });
        
        // 更新store
        if (window.store && window.store.projectData) {
            window.store.projectData.outline = outline;
        }
        
        // 清空无限续写数据（如果选中）
        if (clearData) {
            infiniteWriteState.sessionId = 'infinite_' + Date.now();
            infiniteWriteState.chapters = [];
            infiniteWriteState.currentChapter = 0;
            infiniteWriteState.totalWords = 0;
            infiniteWriteState.pendingSummaries = [];
            localStorage.removeItem('infinite_write_data');
        }
        
        // 刷新项目选择器
        updateProjectSelector();
        
        // 关闭弹窗
        modal.classList.add('hidden');
        modal.innerHTML = '';
        
        // 显示成功消息
        showToast(`🎉 故事已完结！${isNewProject ? `新项目「${projectName}」已创建` : '章节已追加到当前项目'}`, 'success');
        
        // 刷新界面
        if (isNewProject) {
            // 切换到新项目后刷新
            if (typeof loadCurrentProjectData === 'function') {
                await loadCurrentProjectData();
            }
        }
        
        // 刷新无限续写界面
        if (clearData) {
            renderInfiniteWriteInterface();
            loadInfiniteWriteNavChapterList();
        }
        
    } catch (e) {
        console.error('[InfiniteWrite] 完结故事失败:', e);
        showToast('完结失败: ' + e.message, 'error');
        
        if (confirmBtn) {
            confirmBtn.disabled = false;
            confirmBtn.innerHTML = '<i class="ri-save-line"></i> 确认完结';
        }
    }
}

// 全局暴露错误提示函数和完结功能
window.showInfiniteWriteError = showInfiniteWriteError;
window.showInfiniteWriteImportDialog = showInfiniteWriteImportDialog;
window.showFinishStoryDialog = showFinishStoryDialog;
window.updateRunningStatus = updateRunningStatus;

// 页面卸载前检查是否有运行中的任务
window.addEventListener('beforeunload', (e) => {
    if (infiniteWriteState.isRunning) {
        e.preventDefault();
        e.returnValue = '有正在进行的创作任务，确定要离开吗？';
        return e.returnValue;
    }
});

console.log('[continuous_write.js] 无限续写模块已加载（独立版本，含错误处理增强）');

