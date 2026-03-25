
/**
 * 文思Agent - 导航和视图渲染模块
 * 包含：导航面板渲染、仪表盘、统计页面、空状态显示
 */

// ===== 渲染：导航面板 =====
function renderNavPanel(moduleId) {
    ui.navList.innerHTML = '';

    switch (moduleId) {
        case 'dashboard':
            ui.navTitle.textContent = '项目概览';
            ui.navActionAdd.style.display = 'none';
            renderNavList([
                { id: 'dash-home', icon: 'ri-home-line', text: '主页', active: store.currentDashboardView === 'home' },
                { id: 'dash-stat', icon: 'ri-pie-chart-line', text: '项目统计', active: store.currentDashboardView === 'stats' },
                { id: 'dash-token', icon: 'ri-coin-line', text: 'Token消耗', active: store.currentDashboardView === 'token' }
            ], (item) => {
                if (item.id === 'dash-home') {
                    store.currentDashboardView = 'home';
                    renderDashboard();
                } else if (item.id === 'dash-stat') {
                    store.currentDashboardView = 'stats';
                    renderStatistics();
                } else if (item.id === 'dash-token') {
                    store.currentDashboardView = 'token';
                    if (typeof renderTokenStats === 'function') {
                        renderTokenStats();
                    } else {
                        console.error('[Nav] renderTokenStats not found');
                        showToast('Token统计模块加载失败', 'error');
                    }
                }
            });
            break;
        
        case 'infinite-write':
            ui.navTitle.textContent = '无限续写';
            ui.navActionAdd.style.display = 'none';
            
            // 渲染无限续写导航面板
            if (typeof renderInfiniteWriteNavPanel === 'function') {
                renderInfiniteWriteNavPanel();
            } else {
                console.error('[Nav] renderInfiniteWriteNavPanel not found');
                ui.navList.innerHTML = `
                    <div style="padding: 16px 12px; color: var(--text-secondary); font-size: 12px; line-height: 1.6;">
                        无限续写导航加载失败，请刷新页面重试。
                    </div>
                `;
            }
            break;

        case 'novel-to-script':
            ui.navTitle.textContent = '小说转剧本';
            ui.navActionAdd.style.display = 'none';
            if (typeof renderNovelToScriptNavPanel === 'function') {
                renderNovelToScriptNavPanel();
            } else {
                console.error('[Nav] renderNovelToScriptNavPanel not found');
                ui.navList.innerHTML = `
                    <div style="padding: 16px 12px; color: var(--text-secondary); font-size: 12px; line-height: 1.6;">
                        小说转剧本导航加载失败，请刷新页面重试。
                    </div>
                `;
            }
            break;

        case 'write':
            ui.navTitle.textContent = '协作创作';
            ui.navActionAdd.style.display = 'block';
            ui.navActionAdd.onclick = addNewChapter;

            // 渲染写作模块导航（协作创作章节列表）
            if (typeof renderMultiAgentWriteNavPanel === 'function') {
                renderMultiAgentWriteNavPanel();
            } else {
                console.error('[Nav] renderMultiAgentWriteNavPanel not found');
                ui.navList.innerHTML = `
                    <div style="padding: 16px 12px; color: var(--text-secondary); font-size: 12px; line-height: 1.6;">
                        协作模式导航加载失败，请刷新页面重试。
                    </div>
                `;
            }
            break;

        case 'world':
            ui.navTitle.textContent = '资料库';
            ui.navActionAdd.style.display = 'block';
            ui.navActionAdd.onclick = addNewSetting;
            renderKnowledgeNavPanel();
            break;

        case 'aux-memory':
            ui.navTitle.textContent = '长期记忆';
            ui.navActionAdd.style.display = 'none';
            if (typeof renderAuxMemoryNavPanel === 'function') {
                renderAuxMemoryNavPanel();
            }
            break;

        case 'settings':
            ui.navTitle.textContent = '偏好设置';
            ui.navActionAdd.style.display = 'none';
            renderNavList([
                { id: 'set-theme', icon: 'ri-palette-line', text: '外观主题', active: true },
                { id: 'set-global-api', icon: 'ri-global-line', text: '全局API配置' },
                { id: 'set-knowledge-base', icon: 'ri-database-2-line', text: '知识库配置' },
                { id: 'set-agent', icon: 'ri-brain-line', text: 'Agent配置' },
                { id: 'set-backup', icon: 'ri-save-line', text: '备份管理' },
                { id: 'set-prompts', icon: 'ri-file-text-line', text: '提示词管理' },
                { id: 'set-skills', icon: 'ri-puzzle-line', text: 'Skills管理' },
                { id: 'set-regex', icon: 'ri-code-line', text: '正则替换规则' }
            ], (item) => {
                if (item.id === 'set-theme') loadThemeSettings();
                if (item.id === 'set-global-api') loadGlobalAPISettings();
                if (item.id === 'set-knowledge-base') loadKnowledgeBaseSettings();
                if (item.id === 'set-agent') loadAgentSettings();
                if (item.id === 'set-backup') loadBackupSettings();
                if (item.id === 'set-prompts') {
                    // 延迟调用确保 prompt_manager.js 已加载，使用重试机制
                    let retryCount = 0;
                    const maxRetries = 10;
                    const checkAndLoad = () => {
                        if (typeof window.loadPromptSettings === 'function') {
                            window.loadPromptSettings();
                        } else if (retryCount < maxRetries) {
                            retryCount++;
                            console.log(`[Settings] 等待 prompt_manager.js 加载... (${retryCount}/${maxRetries})`);
                            setTimeout(checkAndLoad, 100);
                        } else {
                            console.error('[Settings] loadPromptSettings 函数未找到，请检查 prompt_manager.js 是否正确加载');
                            showToast('提示词管理模块加载失败，请刷新页面', 'error');
                        }
                    };
                    setTimeout(checkAndLoad, 50);
                }
                if (item.id === 'set-skills') loadSkillsSettings();
                if (item.id === 'set-regex') loadRegexRulesSettings();
            });
            break;
        
        case 'about':
            ui.navTitle.textContent = '关于';
            ui.navActionAdd.style.display = 'none';
            renderNavList([
                { id: 'about-info', icon: 'ri-information-line', text: '关于作者', active: true },
                { id: 'about-feedback', icon: 'ri-feedback-line', text: '反馈与建议' },
                { id: 'about-version', icon: 'ri-git-branch-line', text: '版本信息' }
            ], (item) => {
                if (item.id === 'about-info') renderAboutPage();
                if (item.id === 'about-feedback') renderFeedbackPage();
                if (item.id === 'about-version') renderVersionPage();
            });
            break;
    }
}

function renderNavList(items, onClick) {
    ui.navList.innerHTML = '';
    items.forEach(item => {
        const div = document.createElement('div');
        div.className = `list-item ${item.active ? 'active' : ''}`;
        // 只在非设置页面显示图标
        const showIcon = item.icon && !item.id?.startsWith('set-');
        div.innerHTML = `
            ${showIcon ? `<i class="${item.icon}"></i>` : ''}
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

// 渲染带操作按钮的列表（用于章节）
function renderNavListWithActions(items, type) {
    ui.navList.innerHTML = '';

    if (items.length === 0) {
        ui.navList.innerHTML = `
            <div style="padding: 20px; text-align: center; color: var(--text-secondary); font-size: 13px;">
                <p>暂无内容</p>
                <p style="font-size: 11px; margin-top: 8px;">点击上方 + 添加</p>
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
                <button class="edit-btn" title="编辑" style="background: none; border: none; color: var(--text-secondary); cursor: pointer; padding: 4px;">
                    <i class="ri-edit-line"></i>
                </button>
                <button class="delete-btn" title="删除" style="background: none; border: none; color: #ef4444; cursor: pointer; padding: 4px;">
                    <i class="ri-delete-bin-line"></i>
                </button>
            </div>
        `;

        // 悬停显示操作按钮
        div.addEventListener('mouseenter', () => {
            div.querySelector('.item-actions').style.opacity = '1';
        });
        div.addEventListener('mouseleave', () => {
            div.querySelector('.item-actions').style.opacity = '0';
        });

        // 点击打开编辑器
        div.addEventListener('click', (e) => {
            if (!e.target.closest('.item-actions')) {
                ui.navList.querySelectorAll('.list-item').forEach(el => el.classList.remove('active'));
                div.classList.add('active');
                if (type === 'chapter') {
                    openChapterEditor(item.index);
                }
            }
        });

        // 编辑按钮
        div.querySelector('.edit-btn').addEventListener('click', (e) => {
            e.stopPropagation();
            if (type === 'chapter') {
                editChapterTitle(item.index);
            }
        });

        // 删除按钮
        div.querySelector('.delete-btn').addEventListener('click', (e) => {
            e.stopPropagation();
            if (type === 'chapter') {
                deleteChapter(item.index);
            }
        });

        ui.navList.appendChild(div);
    });
}


// ===== 渲染：主工作区内容 =====

function renderDashboard() {
    store.currentDashboardView = 'home';
    updateBreadcrumbs([store.currentProjectName || '我的项目', '主页']);

    // 计算统计数据
    const chapters = store.projectData.outline || [];
    const totalWords = chapters.reduce((sum, ch) => sum + (ch.content || '').replace(/\s/g, '').length, 0);
    const chapterCount = chapters.length;
    const writtenChapters = chapters.filter(ch => (ch.content || '').length > 0).length;
    const characterCount = (store.projectData.characters || []).length;
    const settingCount = (store.projectData.worldbuilding || []).length + (store.projectData.items || []).length;

    ui.workspace.innerHTML = `
        <div style="padding: 40px; text-align: center;">
            <div style="font-size: 48px; margin-bottom: 20px;">✨</div>
            <h1 style="color: var(--text-primary); margin-bottom: 10px;">「${store.currentProjectName || '未命名项目'}」</h1>
            <p style="color: var(--text-secondary);">文思如泉涌，创作无极限</p>
            
            <div style="display: flex; gap: 16px; justify-content: center; margin-top: 40px; flex-wrap: wrap;">
                <div class="meta-card" style="width: 140px; height: 100px; align-items: center; justify-content: center;">
                    <div style="font-size: 28px; font-weight: bold; color: var(--accent-color);">${totalWords.toLocaleString()}</div>
                    <div style="font-size: 12px; color: var(--text-secondary);">总字数</div>
                </div>
                <div class="meta-card" style="width: 140px; height: 100px; align-items: center; justify-content: center;">
                    <div style="font-size: 28px; font-weight: bold; color: #10b981;">${chapterCount}</div>
                    <div style="font-size: 12px; color: var(--text-secondary);">章节数</div>
                </div>
                <div class="meta-card" style="width: 140px; height: 100px; align-items: center; justify-content: center;">
                    <div style="font-size: 28px; font-weight: bold; color: #f59e0b;">${characterCount}</div>
                    <div style="font-size: 12px; color: var(--text-secondary);">角色数</div>
                </div>
                <div class="meta-card" style="width: 140px; height: 100px; align-items: center; justify-content: center;">
                    <div style="font-size: 28px; font-weight: bold; color: #8b5cf6;">${settingCount}</div>
                    <div style="font-size: 12px; color: var(--text-secondary);">知识条目</div>
                </div>
            </div>
            
            <div style="margin-top: 40px; display: flex; gap: 12px; justify-content: center;">
                <button onclick="switchModule('write')" style="padding: 12px 24px; background: var(--accent-color); border: none; color: white; border-radius: 8px; cursor: pointer; font-weight: 500;">
                    <i class="ri-quill-pen-line"></i> 开始写作
                </button>
                <button onclick="switchModule('world')" style="padding: 12px 24px; background: rgba(255,255,255,0.1); border: 1px solid var(--border-color); color: var(--text-primary); border-radius: 8px; cursor: pointer;">
                    <i class="ri-book-mark-line"></i> 管理资料库
                </button>
            </div>
            
            ${chapterCount === 0 ? `
            <p style="margin-top: 30px; color: var(--text-secondary); font-size: 13px;">
                💡 提示：点击左侧 <i class="ri-settings-4-line"></i> 设置，进入「全局API配置」配置您的API
            </p>
            ` : ''}
        </div>
    `;
}

// 当前统计视图的状态
let statisticsState = {
    selectedProjectId: '',  // 空表示当前项目
    dataSource: 'all'       // 'all', 'multi-agent', 'infinite-write'
};

// 渲染统计页面
async function renderStatistics() {
    store.currentDashboardView = 'stats';
    
    // 初始化选中项目为当前项目
    if (!statisticsState.selectedProjectId) {
        statisticsState.selectedProjectId = store.currentProject || '';
    }
    
    // 获取选中项目的名称
    const selectedProject = store.projects.find(p => p.id === statisticsState.selectedProjectId);
    const selectedProjectName = selectedProject ? selectedProject.name : (store.currentProjectName || '我的项目');
    
    updateBreadcrumbs([selectedProjectName, '统计']);

    // 根据选中的项目获取数据
    let projectData = store.projectData;
    
    // 如果选中的不是当前项目，需要从API加载该项目的数据
    if (statisticsState.selectedProjectId && statisticsState.selectedProjectId !== store.currentProject) {
        try {
            // 从API获取指定项目的数据
            const [outlineRes, charRes, worldRes, itemRes] = await Promise.all([
                apiCall(`/api/project-data/outline?project_id=${statisticsState.selectedProjectId}`).catch(() => ({ data: [] })),
                apiCall(`/api/project-data/characters?project_id=${statisticsState.selectedProjectId}`).catch(() => ({ data: [] })),
                apiCall(`/api/project-data/worldbuilding?project_id=${statisticsState.selectedProjectId}`).catch(() => ({ data: [] })),
                apiCall(`/api/project-data/items?project_id=${statisticsState.selectedProjectId}`).catch(() => ({ data: [] }))
            ]);
            projectData = {
                outline: outlineRes.data || [],
                characters: charRes.data || [],
                worldbuilding: worldRes.data || [],
                items: itemRes.data || [],
                eventlines: [],
                outline_settings: [],
                detail_settings: []
            };
        } catch (e) {
            console.error('[Statistics] 加载项目数据失败:', e);
            projectData = store.projectData; // 失败时使用当前项目数据
        }
    }

    // 获取多Agent模式的章节数据
    const multiAgentChapters = projectData.outline || [];
    const multiAgentWords = multiAgentChapters.reduce((sum, ch) => sum + (ch.content || '').replace(/\s/g, '').length, 0);
    const multiAgentWrittenChapters = multiAgentChapters.filter(ch => (ch.content || '').length > 0).length;
    
    // 获取无限续写模式的章节数据（按项目存储）
    let infiniteWriteChapters = [];
    let infiniteWriteWords = 0;
    try {
        // 无限续写数据按项目ID存储
        const storageKey = statisticsState.selectedProjectId
            ? `infinite_write_data_${statisticsState.selectedProjectId}`
            : 'infinite_write_data';
        const savedData = localStorage.getItem(storageKey);
        if (savedData) {
            const data = JSON.parse(savedData);
            infiniteWriteChapters = data.chapters || [];
            infiniteWriteWords = data.totalWords || 0;
        }
        // 如果按项目ID找不到，尝试使用旧的通用键（兼容旧数据）
        if (infiniteWriteChapters.length === 0 && statisticsState.selectedProjectId === store.currentProject) {
            const oldData = localStorage.getItem('infinite_write_data');
            if (oldData) {
                const data = JSON.parse(oldData);
                infiniteWriteChapters = data.chapters || [];
                infiniteWriteWords = data.totalWords || 0;
            }
        }
    } catch (e) {
        console.error('[Statistics] 解析无限续写数据失败:', e);
    }
    
    // 根据选中的模式过滤章节数据
    let chapters = [];
    let totalWords = 0;
    let chapterCount = 0;
    let writtenChapters = 0;
    
    if (statisticsState.dataSource === 'all' || statisticsState.dataSource === 'multi-agent') {
        chapters = chapters.concat(multiAgentChapters.map((ch, i) => ({
            ...ch,
            source: 'multi-agent',
            displayNumber: i + 1
        })));
    }
    if (statisticsState.dataSource === 'all' || statisticsState.dataSource === 'infinite-write') {
        chapters = chapters.concat(infiniteWriteChapters.map((ch, i) => ({
            ...ch,
            source: 'infinite-write',
            displayNumber: ch.chapter_number || (i + 1)
        })));
    }
    
    // 根据模式计算统计数据
    if (statisticsState.dataSource === 'all') {
        totalWords = multiAgentWords + infiniteWriteWords;
        chapterCount = multiAgentChapters.length + infiniteWriteChapters.length;
        writtenChapters = multiAgentWrittenChapters + infiniteWriteChapters.length;
    } else if (statisticsState.dataSource === 'multi-agent') {
        totalWords = multiAgentWords;
        chapterCount = multiAgentChapters.length;
        writtenChapters = multiAgentWrittenChapters;
    } else {
        totalWords = infiniteWriteWords;
        chapterCount = infiniteWriteChapters.length;
        writtenChapters = infiniteWriteChapters.length;
    }
    
    const avgWordsPerChapter = writtenChapters > 0 ? Math.round(totalWords / writtenChapters) : 0;
    
    const characterCount = (projectData.characters || []).length;
    const worldCount = (projectData.worldbuilding || []).length;
    const itemCount = (projectData.items || []).length;
    const eventCount = (projectData.eventlines || []).length;
    const outlineSettingCount = (projectData.outline_settings || []).length;
    const detailSettingCount = (projectData.detail_settings || []).length;
    
    // 计算每章字数
    const chapterWordsData = chapters.map((ch, i) => ({
        chapter: ch.displayNumber || (i + 1),
        title: ch.title || `第${ch.displayNumber || (i + 1)}章`,
        words: ch.word_count || (ch.content || '').replace(/\s/g, '').length,
        source: ch.source
    }));
    
    // 按每10章分组计算字数
    const groupedData = [];
    for (let i = 0; i < chapterWordsData.length; i += 10) {
        const group = chapterWordsData.slice(i, i + 10);
        const totalWordsInGroup = group.reduce((sum, ch) => sum + ch.words, 0);
        const startChapter = i + 1;
        const endChapter = Math.min(i + 10, chapterWordsData.length);
        groupedData.push({
            label: `${startChapter}-${endChapter}章`,
            startChapter,
            endChapter,
            totalWords: totalWordsInGroup,
            avgWords: Math.round(totalWordsInGroup / group.length),
            chapterCount: group.length
        });
    }
    
    // 生成曲线图SVG
    const chartWidth = 800;
    const chartHeight = 280;
    const padding = { top: 30, right: 40, bottom: 50, left: 70 };
    const innerWidth = chartWidth - padding.left - padding.right;
    const innerHeight = chartHeight - padding.top - padding.bottom;
    
    const maxGroupWords = groupedData.length > 0 ? Math.max(...groupedData.map(g => g.totalWords)) : 1;
    
    // 生成曲线路径和圆点
    let pathD = '';
    let circles = '';
    let labels = '';
    
    if (groupedData.length > 0) {
        const xStep = groupedData.length > 1 ? innerWidth / (groupedData.length - 1) : innerWidth / 2;
        
        groupedData.forEach((group, i) => {
            const x = groupedData.length > 1 ? padding.left + i * xStep : padding.left + innerWidth / 2;
            const y = padding.top + innerHeight - (group.totalWords / maxGroupWords) * innerHeight;
            
            if (i === 0) {
                pathD = `M ${x} ${y}`;
            } else {
                // 使用贝塞尔曲线使线条更平滑
                const prevX = padding.left + (i - 1) * xStep;
                const prevY = padding.top + innerHeight - (groupedData[i - 1].totalWords / maxGroupWords) * innerHeight;
                const cpX = (prevX + x) / 2;
                pathD += ` C ${cpX} ${prevY}, ${cpX} ${y}, ${x} ${y}`;
            }
            
            // 数据点
            circles += `
                <circle cx="${x}" cy="${y}" r="6" fill="var(--accent-color)" stroke="white" stroke-width="2" style="cursor: pointer;">
                    <title>${group.label}&#10;总字数: ${group.totalWords.toLocaleString()}&#10;平均每章: ${group.avgWords.toLocaleString()}字</title>
                </circle>
            `;
            
            // X轴标签
            labels += `
                <text x="${x}" y="${chartHeight - 15}" text-anchor="middle" fill="var(--text-secondary)" font-size="11">${group.label}</text>
            `;
        });
    }
    
    // 生成Y轴刻度
    let yAxisTicks = '';
    const tickCount = 5;
    for (let i = 0; i <= tickCount; i++) {
        const value = Math.round((maxGroupWords / tickCount) * i);
        const y = padding.top + innerHeight - (i / tickCount) * innerHeight;
        yAxisTicks += `
            <line x1="${padding.left - 5}" y1="${y}" x2="${padding.left}" y2="${y}" stroke="var(--text-secondary)" stroke-width="1"/>
            <text x="${padding.left - 10}" y="${y + 4}" text-anchor="end" fill="var(--text-secondary)" font-size="11">${(value / 10000).toFixed(1)}万</text>
            <line x1="${padding.left}" y1="${y}" x2="${chartWidth - padding.right}" y2="${y}" stroke="var(--border-color)" stroke-width="1" stroke-dasharray="3,3" opacity="0.5"/>
        `;
    }
    
    const chartSVG = groupedData.length > 0 ? `
        <svg width="100%" viewBox="0 0 ${chartWidth} ${chartHeight}" style="max-width: 100%;">
            <!-- 背景网格 -->
            ${yAxisTicks}
            
            <!-- Y轴 -->
            <line x1="${padding.left}" y1="${padding.top}" x2="${padding.left}" y2="${padding.top + innerHeight}" stroke="var(--text-secondary)" stroke-width="1"/>
            
            <!-- X轴 -->
            <line x1="${padding.left}" y1="${padding.top + innerHeight}" x2="${chartWidth - padding.right}" y2="${padding.top + innerHeight}" stroke="var(--text-secondary)" stroke-width="1"/>
            
            <!-- 渐变填充区域 -->
            <defs>
                <linearGradient id="areaGradient" x1="0%" y1="0%" x2="0%" y2="100%">
                    <stop offset="0%" style="stop-color: var(--accent-color); stop-opacity: 0.3"/>
                    <stop offset="100%" style="stop-color: var(--accent-color); stop-opacity: 0.05"/>
                </linearGradient>
            </defs>
            
            <!-- 填充区域 -->
            <path d="${pathD} L ${padding.left + (groupedData.length > 1 ? innerWidth : innerWidth / 2)} ${padding.top + innerHeight} L ${padding.left} ${padding.top + innerHeight} Z" fill="url(#areaGradient)"/>
            
            <!-- 曲线 -->
            <path d="${pathD}" fill="none" stroke="var(--accent-color)" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/>
            
            <!-- 数据点 -->
            ${circles}
            
            <!-- X轴标签 -->
            ${labels}
            
            <!-- Y轴标题 -->
            <text x="15" y="${chartHeight / 2}" text-anchor="middle" fill="var(--text-secondary)" font-size="12" transform="rotate(-90, 15, ${chartHeight / 2})">字数（万）</text>
        </svg>
    ` : '';

    // 生成分组详情卡片
    const groupCardsHTML = groupedData.map((group, i) => `
        <div style="background: rgba(139, 92, 246, 0.1); padding: 12px; border-radius: 8px; border-left: 3px solid var(--accent-color);">
            <div style="font-weight: 600; color: var(--text-primary); font-size: 13px;">${group.label}</div>
            <div style="display: flex; justify-content: space-between; margin-top: 8px;">
                <span style="font-size: 11px; color: var(--text-secondary);">总字数</span>
                <span style="font-size: 12px; color: var(--text-primary); font-weight: 500;">${group.totalWords.toLocaleString()}</span>
            </div>
            <div style="display: flex; justify-content: space-between; margin-top: 4px;">
                <span style="font-size: 11px; color: var(--text-secondary);">平均每章</span>
                <span style="font-size: 12px; color: var(--text-primary);">${group.avgWords.toLocaleString()}</span>
            </div>
        </div>
    `).join('');

    ui.workspace.innerHTML = `
        <div style="padding: 30px; max-width: 1000px; margin: 0 auto;">
            <div style="display: flex; align-items: center; justify-content: space-between; margin-bottom: 30px;">
                <h2 style="color: var(--text-primary); font-size: 20px; display: flex; align-items: center; gap: 10px; margin: 0;">
                    <i class="ri-pie-chart-line"></i>
                    项目统计分析
                </h2>
                
                <!-- 项目筛选 -->
                <div style="display: flex; gap: 8px; align-items: center;">
                    <span style="font-size: 13px; color: var(--text-secondary);">选择项目:</span>
                    <select id="stats-project-select" style="padding: 8px 16px; background: var(--bg-secondary); border: 1px solid var(--border-color); border-radius: 6px; color: var(--text-primary); font-size: 13px; cursor: pointer; min-width: 150px;">
                        ${store.projects.map(p => `
                            <option value="${p.id}" ${p.id === statisticsState.selectedProjectId ? 'selected' : ''}>
                                ${escapeHtml(p.name)}
                            </option>
                        `).join('')}
                    </select>
                </div>
            </div>
            
            <!-- 模式切换按钮 -->
            <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 16px; margin-bottom: 24px;">
                <div id="stats-mode-multi-agent" class="stats-mode-card" style="background: linear-gradient(135deg, rgba(139, 92, 246, 0.15), rgba(99, 102, 241, 0.1)); border: 2px solid ${statisticsState.dataSource === 'multi-agent' || statisticsState.dataSource === 'all' ? '#8b5cf6' : 'rgba(139, 92, 246, 0.3)'}; border-radius: 12px; padding: 20px; cursor: pointer; transition: all 0.2s; ${statisticsState.dataSource === 'multi-agent' ? 'box-shadow: 0 0 20px rgba(139, 92, 246, 0.3);' : ''}">
                    <div style="display: flex; align-items: center; gap: 12px; margin-bottom: 12px;">
                        <div style="width: 40px; height: 40px; background: rgba(139, 92, 246, 0.2); border-radius: 10px; display: flex; align-items: center; justify-content: center;">
                            <i class="ri-quill-pen-line" style="font-size: 20px; color: #8b5cf6;"></i>
                        </div>
                        <div style="flex: 1;">
                            <div style="font-size: 14px; color: var(--text-primary); font-weight: 500;">协作创作模式</div>
                            <div style="font-size: 12px; color: var(--text-secondary);">多Agent协作写作</div>
                        </div>
                        ${statisticsState.dataSource === 'multi-agent' ? '<i class="ri-checkbox-circle-fill" style="font-size: 20px; color: #8b5cf6;"></i>' : '<i class="ri-checkbox-blank-circle-line" style="font-size: 20px; color: var(--text-secondary); opacity: 0.5;"></i>'}
                    </div>
                    <div style="display: flex; gap: 24px;">
                        <div>
                            <div style="font-size: 24px; font-weight: bold; color: #8b5cf6;">${multiAgentChapters.length}</div>
                            <div style="font-size: 11px; color: var(--text-secondary);">章节</div>
                        </div>
                        <div>
                            <div style="font-size: 24px; font-weight: bold; color: #8b5cf6;">${multiAgentWords.toLocaleString()}</div>
                            <div style="font-size: 11px; color: var(--text-secondary);">字数</div>
                        </div>
                    </div>
                </div>
                
                <div id="stats-mode-infinite-write" class="stats-mode-card" style="background: linear-gradient(135deg, rgba(245, 158, 11, 0.15), rgba(251, 146, 60, 0.1)); border: 2px solid ${statisticsState.dataSource === 'infinite-write' || statisticsState.dataSource === 'all' ? '#f59e0b' : 'rgba(245, 158, 11, 0.3)'}; border-radius: 12px; padding: 20px; cursor: pointer; transition: all 0.2s; ${statisticsState.dataSource === 'infinite-write' ? 'box-shadow: 0 0 20px rgba(245, 158, 11, 0.3);' : ''}">
                    <div style="display: flex; align-items: center; gap: 12px; margin-bottom: 12px;">
                        <div style="width: 40px; height: 40px; background: rgba(245, 158, 11, 0.2); border-radius: 10px; display: flex; align-items: center; justify-content: center;">
                            <i class="ri-infinity-line" style="font-size: 20px; color: #f59e0b;"></i>
                        </div>
                        <div style="flex: 1;">
                            <div style="font-size: 14px; color: var(--text-primary); font-weight: 500;">无限续写模式</div>
                            <div style="font-size: 12px; color: var(--text-secondary);">灵感驱动创作</div>
                        </div>
                        ${statisticsState.dataSource === 'infinite-write' ? '<i class="ri-checkbox-circle-fill" style="font-size: 20px; color: #f59e0b;"></i>' : '<i class="ri-checkbox-blank-circle-line" style="font-size: 20px; color: var(--text-secondary); opacity: 0.5;"></i>'}
                    </div>
                    <div style="display: flex; gap: 24px;">
                        <div>
                            <div style="font-size: 24px; font-weight: bold; color: #f59e0b;">${infiniteWriteChapters.length}</div>
                            <div style="font-size: 11px; color: var(--text-secondary);">章节</div>
                        </div>
                        <div>
                            <div style="font-size: 24px; font-weight: bold; color: #f59e0b;">${infiniteWriteWords.toLocaleString()}</div>
                            <div style="font-size: 11px; color: var(--text-secondary);">字数</div>
                        </div>
                    </div>
                </div>
            </div>
            
            <!-- 当前显示模式提示 -->
            <div style="margin-bottom: 20px; padding: 12px 16px; background: rgba(255,255,255,0.03); border: 1px solid var(--border-color); border-radius: 8px; display: flex; align-items: center; justify-content: space-between;">
                <div style="display: flex; align-items: center; gap: 8px;">
                    <i class="ri-filter-3-line" style="color: var(--accent-color);"></i>
                    <span style="font-size: 13px; color: var(--text-secondary);">当前显示:</span>
                    <span style="font-size: 13px; color: var(--text-primary); font-weight: 500;">
                        ${statisticsState.dataSource === 'all' ? '全部模式' : statisticsState.dataSource === 'multi-agent' ? '协作创作模式' : '无限续写模式'}
                    </span>
                </div>
                ${statisticsState.dataSource !== 'all' ? `
                <button id="stats-show-all-btn" style="padding: 6px 12px; background: rgba(255,255,255,0.1); border: 1px solid var(--border-color); border-radius: 6px; color: var(--text-primary); font-size: 12px; cursor: pointer; display: flex; align-items: center; gap: 4px;">
                    <i class="ri-apps-line"></i> 显示全部
                </button>
                ` : ''}
            </div>
            
            <!-- 核心指标卡片 -->
            <div style="display: grid; grid-template-columns: repeat(3, 1fr); gap: 16px; margin-bottom: 30px;">
                <div class="stats-card" style="background: rgba(255,255,255,0.03); border: 1px solid var(--border-color); border-radius: 12px; padding: 20px; text-align: center;">
                    <div style="font-size: 32px; font-weight: bold; color: var(--accent-color);">${totalWords.toLocaleString()}</div>
                    <div style="font-size: 13px; color: var(--text-secondary); margin-top: 6px;">总字数</div>
                </div>
                <div class="stats-card" style="background: rgba(255,255,255,0.03); border: 1px solid var(--border-color); border-radius: 12px; padding: 20px; text-align: center;">
                    <div style="font-size: 32px; font-weight: bold; color: #10b981;">${chapterCount}</div>
                    <div style="font-size: 13px; color: var(--text-secondary); margin-top: 6px;">总章节</div>
                </div>
                <div class="stats-card" style="background: rgba(255,255,255,0.03); border: 1px solid var(--border-color); border-radius: 12px; padding: 20px; text-align: center;">
                    <div style="font-size: 32px; font-weight: bold; color: #f59e0b;">${avgWordsPerChapter.toLocaleString()}</div>
                    <div style="font-size: 13px; color: var(--text-secondary); margin-top: 6px;">平均每章字数</div>
                </div>
            </div>
            
            <!-- 资料库统计 -->
            <div style="background: rgba(255,255,255,0.03); border: 1px solid var(--border-color); border-radius: 12px; padding: 20px; margin-bottom: 20px;">
                <h3 style="color: var(--text-primary); margin-bottom: 16px; font-size: 15px; display: flex; align-items: center; gap: 8px;">
                    <i class="ri-database-2-line"></i>
                    资料库统计
                </h3>
                <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(120px, 1fr)); gap: 12px;">
                    <div style="background: rgba(236, 72, 153, 0.1); padding: 14px; border-radius: 8px; text-align: center;">
                        <div style="font-size: 22px; font-weight: bold; color: #ec4899;">${characterCount}</div>
                        <div style="font-size: 11px; color: var(--text-secondary); margin-top: 4px;">角色档案</div>
                    </div>
                    <div style="background: rgba(6, 182, 212, 0.1); padding: 14px; border-radius: 8px; text-align: center;">
                        <div style="font-size: 22px; font-weight: bold; color: #06b6d4;">${worldCount}</div>
                        <div style="font-size: 11px; color: var(--text-secondary); margin-top: 4px;">世界设定</div>
                    </div>
                    <div style="background: rgba(249, 115, 22, 0.1); padding: 14px; border-radius: 8px; text-align: center;">
                        <div style="font-size: 22px; font-weight: bold; color: #f97316;">${itemCount}</div>
                        <div style="font-size: 11px; color: var(--text-secondary); margin-top: 4px;">道具物品</div>
                    </div>
                    <div style="background: rgba(168, 85, 247, 0.1); padding: 14px; border-radius: 8px; text-align: center;">
                        <div style="font-size: 22px; font-weight: bold; color: #a855f7;">${eventCount}</div>
                        <div style="font-size: 11px; color: var(--text-secondary); margin-top: 4px;">事件线</div>
                    </div>
                    <div style="background: rgba(20, 184, 166, 0.1); padding: 14px; border-radius: 8px; text-align: center;">
                        <div style="font-size: 22px; font-weight: bold; color: #14b8a6;">${outlineSettingCount}</div>
                        <div style="font-size: 11px; color: var(--text-secondary); margin-top: 4px;">大纲设定</div>
                    </div>
                    <div style="background: rgba(234, 179, 8, 0.1); padding: 14px; border-radius: 8px; text-align: center;">
                        <div style="font-size: 22px; font-weight: bold; color: #eab308;">${detailSettingCount}</div>
                        <div style="font-size: 11px; color: var(--text-secondary); margin-top: 4px;">细纲设定</div>
                    </div>
                </div>
            </div>
            
            <!-- 章节字数分布曲线图 -->
            ${groupedData.length > 0 ? `
            <div style="background: rgba(255,255,255,0.03); border: 1px solid var(--border-color); border-radius: 12px; padding: 20px;">
                <h3 style="color: var(--text-primary); margin-bottom: 16px; font-size: 15px; display: flex; align-items: center; gap: 8px;">
                    <i class="ri-line-chart-line"></i>
                    字数分布曲线
                    <span style="font-size: 12px; color: var(--text-secondary); font-weight: normal; margin-left: auto;">每10章统计</span>
                </h3>
                <div style="overflow-x: auto;">
                    ${chartSVG}
                </div>
                
                <!-- 分组详情表格 -->
                <div style="margin-top: 20px; border-top: 1px solid var(--border-color); padding-top: 16px;">
                    <div style="display: grid; grid-template-columns: repeat(auto-fill, minmax(180px, 1fr)); gap: 12px;">
                        ${groupCardsHTML}
                    </div>
                </div>
            </div>
            ` : `
            <div style="background: rgba(255,255,255,0.03); border: 1px solid var(--border-color); border-radius: 12px; padding: 40px; text-align: center;">
                <i class="ri-line-chart-line" style="font-size: 40px; color: var(--text-secondary); opacity: 0.3;"></i>
                <p style="color: var(--text-secondary); margin-top: 12px; font-size: 13px;">暂无章节数据</p>
            </div>
            `}
        </div>
    `;
    
    // 绑定项目切换事件
    document.getElementById('stats-project-select')?.addEventListener('change', (e) => {
        statisticsState.selectedProjectId = e.target.value;
        renderStatistics();
    });
    
    // 绑定模式切换事件
    document.getElementById('stats-mode-multi-agent')?.addEventListener('click', () => {
        if (statisticsState.dataSource === 'multi-agent') {
            statisticsState.dataSource = 'all'; // 再次点击取消选中，显示全部
        } else {
            statisticsState.dataSource = 'multi-agent';
        }
        renderStatistics();
    });
    
    document.getElementById('stats-mode-infinite-write')?.addEventListener('click', () => {
        if (statisticsState.dataSource === 'infinite-write') {
            statisticsState.dataSource = 'all'; // 再次点击取消选中，显示全部
        } else {
            statisticsState.dataSource = 'infinite-write';
        }
        renderStatistics();
    });
    
    // 显示全部按钮
    document.getElementById('stats-show-all-btn')?.addEventListener('click', () => {
        statisticsState.dataSource = 'all';
        renderStatistics();
    });
    
    // 添加悬停效果
    document.querySelectorAll('.stats-mode-card').forEach(card => {
        card.addEventListener('mouseenter', () => {
            card.style.transform = 'translateY(-2px)';
        });
        card.addEventListener('mouseleave', () => {
            card.style.transform = 'translateY(0)';
        });
    });
}

function showEmptyEditor() {
    updateBreadcrumbs(['写作', '选择章节']);
    ui.workspace.innerHTML = `
        <div style="display: flex; align-items: center; justify-content: center; height: 100%; color: var(--text-secondary);">
            <div style="text-align: center;">
                <i class="ri-file-text-line" style="font-size: 48px; opacity: 0.3;"></i>
                <p style="margin-top: 16px;">从左侧选择章节，或先导入已完成小说</p>
                <div style="margin-top: 16px; display: flex; gap: 10px; justify-content: center; flex-wrap: wrap;">
                    <button onclick="showCollaborativeImportDialog && showCollaborativeImportDialog()"
                        style="padding: 10px 14px; border-radius: 8px; border: 1px solid var(--border-color); background: rgba(34,197,94,0.15); color: #22c55e; cursor: pointer;">
                        <i class="ri-upload-cloud-2-line"></i> 导入小说
                    </button>
                    <button onclick="showAddChapterDialog && showAddChapterDialog()"
                        style="padding: 10px 14px; border-radius: 8px; border: 1px solid var(--border-color); background: rgba(255,255,255,0.08); color: var(--text-primary); cursor: pointer;">
                        <i class="ri-add-line"></i> 新建章节
                    </button>
                </div>
            </div>
        </div>
    `;
}

function showEmptyWorld() {
    updateBreadcrumbs(['资料库', '选择类别']);
    ui.workspace.innerHTML = `
        <div style="display: flex; align-items: center; justify-content: center; height: 100%; color: var(--text-secondary);">
            <div style="text-align: center;">
                <i class="ri-book-mark-line" style="font-size: 48px; opacity: 0.3;"></i>
                <p style="margin-top: 16px;">从左侧选择一个资料库类别</p>
            </div>
        </div>
    `;
}

// ===== 关于页面渲染 =====
function renderAboutPage() {
    updateBreadcrumbs(['关于', '关于作者']);
    
    ui.workspace.innerHTML = `
        <div style="padding: 40px; max-width: 700px; margin: 0 auto;">
            <div style="text-align: center; margin-bottom: 40px;">
                <img src="/static/logo.png" alt="文思Agent" style="width: 100px; height: 100px; border-radius: 20px; box-shadow: 0 8px 32px rgba(139, 92, 246, 0.3);">
                <h1 style="color: var(--text-primary); margin-top: 20px; font-size: 28px;">文思Agent</h1>
                <p style="color: var(--text-secondary); margin-top: 8px;">智能小说创作助手</p>
            </div>
            
            <!-- 作者信息卡片 -->
            <div style="background: rgba(139, 92, 246, 0.1); border: 1px solid rgba(139, 92, 246, 0.3); border-radius: 16px; padding: 24px; margin-bottom: 24px;">
                <h3 style="color: var(--text-primary); margin-bottom: 16px; display: flex; align-items: center; gap: 8px;">
                    <i class="ri-user-star-line" style="color: #8b5cf6;"></i>
                    关于作者
                </h3>
                <div style="display: flex; align-items: center; gap: 16px;">
                    <div style="width: 64px; height: 64px; background: linear-gradient(135deg, #8b5cf6, #6366f1); border-radius: 50%; display: flex; align-items: center; justify-content: center;">
                        <i class="ri-user-3-fill" style="font-size: 28px; color: white;"></i>
                    </div>
                    <div>
                        <div style="font-size: 18px; font-weight: 600; color: var(--text-primary);">原来是佳睿</div>
                        <div style="font-size: 13px; color: var(--text-secondary); margin-top: 4px;">AI应用探索者</div>
                    </div>
                </div>
            </div>
            
            <!-- B站链接卡片 -->
            <div style="background: rgba(0, 161, 214, 0.1); border: 1px solid rgba(0, 161, 214, 0.3); border-radius: 16px; padding: 24px; margin-bottom: 24px;">
                <h3 style="color: var(--text-primary); margin-bottom: 16px; display: flex; align-items: center; gap: 8px;">
                    <i class="ri-bilibili-line" style="color: #00a1d6;"></i>
                    关注我的B站
                </h3>
                <p style="color: var(--text-secondary); font-size: 14px; margin-bottom: 16px;">
                    欢迎关注我的B站账号，获取更多AI创作工具的教程和分享！
                </p>
                <a href="https://space.bilibili.com/30232040" target="_blank" rel="noopener noreferrer"
                   style="display: inline-flex; align-items: center; gap: 8px; padding: 12px 24px; background: #00a1d6; color: white; border-radius: 8px; text-decoration: none; font-weight: 500; transition: all 0.2s;">
                    <i class="ri-bilibili-fill"></i>
                    访问我的B站主页
                    <i class="ri-external-link-line"></i>
                </a>
                <div style="margin-top: 12px; font-size: 12px; color: var(--text-secondary);">
                    UID: 30232040
                </div>
            </div>

            <!-- QQ群卡片 -->
            <div style="background: rgba(16, 185, 129, 0.1); border: 1px solid rgba(16, 185, 129, 0.3); border-radius: 16px; padding: 24px; margin-bottom: 24px;">
                <h3 style="color: var(--text-primary); margin-bottom: 16px; display: flex; align-items: center; gap: 8px;">
                    <i class="ri-qq-line" style="color: #10b981;"></i>
                    加入交流群
                </h3>
                <p style="color: var(--text-secondary); font-size: 14px; margin-bottom: 16px;">
                    加入QQ群，与其他创作者交流心得，获取最新动态！
                </p>
                <div style="display: flex; align-items: center; gap: 16px;">
                    <a href="https://qm.qq.com/q/E25rrnPONy" target="_blank" rel="noopener noreferrer"
                       style="display: inline-flex; align-items: center; gap: 8px; padding: 12px 24px; background: #10b981; color: white; border-radius: 8px; text-decoration: none; font-weight: 500; transition: all 0.2s;">
                        <i class="ri-group-line"></i>
                        点击加入QQ群
                        <i class="ri-external-link-line"></i>
                    </a>
                    <div style="font-size: 14px; color: var(--text-primary); font-weight: 500;">
                        群号：760758525
                    </div>
                </div>
            </div>
            
            <!-- 免责声明 -->
            <div style="background: rgba(239, 68, 68, 0.1); border: 1px solid rgba(239, 68, 68, 0.3); border-radius: 16px; padding: 24px;">
                <h3 style="color: var(--text-primary); margin-bottom: 16px; display: flex; align-items: center; gap: 8px;">
                    <i class="ri-alert-line" style="color: #ef4444;"></i>
                    免责声明
                </h3>
                <p style="color: var(--text-secondary); font-size: 14px; line-height: 1.8;">
                    本软件仅供个人学习和研究使用，严禁用于生成任何违反法律法规、违背公序良俗的内容。
                    <br>
                    使用者需对使用本软件产生的所有内容及后果承担全部责任。
                    <br>
                    本软件是免费软件，请勿付费购买，谨防上当受骗！
                </p>
            </div>
        </div>
    `;
}

function renderFeedbackPage() {
    updateBreadcrumbs(['关于', '反馈与建议']);
    
    ui.workspace.innerHTML = `
        <div style="padding: 40px; max-width: 700px; margin: 0 auto;">
            <h2 style="color: var(--text-primary); margin-bottom: 24px; display: flex; align-items: center; gap: 10px;">
                <i class="ri-feedback-line" style="color: var(--accent-color);"></i>
                反馈与建议
            </h2>
            
            <div style="background: rgba(245, 158, 11, 0.1); border: 1px solid rgba(245, 158, 11, 0.3); border-radius: 16px; padding: 24px; margin-bottom: 24px;">
                <h3 style="color: var(--text-primary); margin-bottom: 12px;">💡 提交反馈</h3>
                <p style="color: var(--text-secondary); font-size: 14px; line-height: 1.8;">
                    如果您在使用过程中遇到问题，或者有任何建议和想法，欢迎通过以下方式联系我：
                </p>
                <ul style="color: var(--text-secondary); font-size: 14px; margin-top: 12px; padding-left: 20px; line-height: 2;">
                    <li>在B站视频下方留言评论</li>
                    <li>通过B站私信联系我</li>
                    <li>联系QQ：973389590</li>
                </ul>
            </div>
            
            <div style="background: rgba(139, 92, 246, 0.1); border: 1px solid rgba(139, 92, 246, 0.3); border-radius: 16px; padding: 24px;">
                <h3 style="color: var(--text-primary); margin-bottom: 12px;">🌟 支持项目</h3>
                <p style="color: var(--text-secondary); font-size: 14px; line-height: 1.8;">
                    如果这个项目对您有帮助，欢迎：
                </p>
                <ul style="color: var(--text-secondary); font-size: 14px; margin-top: 12px; padding-left: 20px; line-height: 2;">
                    <li>给B站视频点赞、投币、收藏</li>
                    <li>关注我的B站账号获取更新通知</li>
                    <li>向朋友推荐这个工具</li>
                </ul>
                <div style="margin-top: 20px; text-align: center;">
                    <p style="color: var(--text-secondary); font-size: 14px; margin-bottom: 12px;">或者请作者喝杯咖啡 ☕</p>
                    <img src="/static/赞赏码6.jpg" alt="赞赏码" style="max-width: 200px; border-radius: 12px; box-shadow: 0 4px 12px rgba(0,0,0,0.2);">
                </div>
            </div>
        </div>
    `;
}

function renderVersionPage() {
    updateBreadcrumbs(['关于', '版本信息']);
    
    const version = '1.0.0';
    const buildDate = new Date().toLocaleDateString('zh-CN');
    
    ui.workspace.innerHTML = `
        <div style="padding: 40px; max-width: 700px; margin: 0 auto;">
            <h2 style="color: var(--text-primary); margin-bottom: 24px; display: flex; align-items: center; gap: 10px;">
                <i class="ri-git-branch-line" style="color: var(--accent-color);"></i>
                版本信息
            </h2>
            
            <div style="background: rgba(255,255,255,0.03); border: 1px solid var(--border-color); border-radius: 16px; padding: 24px; margin-bottom: 24px;">
                <div style="display: grid; grid-template-columns: 120px 1fr; gap: 16px; font-size: 14px;">
                    <div style="color: var(--text-secondary);">当前版本</div>
                    <div style="color: var(--text-primary); font-weight: 500;">v${version}</div>
                    
                    <div style="color: var(--text-secondary);">更新日期</div>
                    <div style="color: var(--text-primary);">${buildDate}</div>
                    
                    <div style="color: var(--text-secondary);">运行环境</div>
                    <div style="color: var(--text-primary);">Python 3.10+ / Windows</div>
                </div>
            </div>
            
            <div style="background: rgba(16, 185, 129, 0.1); border: 1px solid rgba(16, 185, 129, 0.3); border-radius: 16px; padding: 24px;">
                <h3 style="color: var(--text-primary); margin-bottom: 16px;">✨ 主要功能</h3>
                <ul style="color: var(--text-secondary); font-size: 14px; padding-left: 20px; line-height: 2;">
                    <li>无限续写模式 - 灵感驱动的自由创作</li>
                    <li>多Agent协作创作 - 智能分工协同</li>
                    <li>知识库管理 - 角色、设定、世界观</li>
                    <li>会话持久化 - 换模型保持连贯</li>
                    <li>热点融合 - 实时话题灵感</li>
                    <li>Token统计 - 精确消耗追踪</li>
                </ul>
            </div>
        </div>
    `;
}

// 全局暴露导航函数
window.renderNavPanel = renderNavPanel;
window.renderNavList = renderNavList;
window.renderNavListWithActions = renderNavListWithActions;
window.renderDashboard = renderDashboard;
window.renderStatistics = renderStatistics;
window.showEmptyEditor = showEmptyEditor;
window.showEmptyWorld = showEmptyWorld;
window.renderAboutPage = renderAboutPage;
window.renderFeedbackPage = renderFeedbackPage;
window.renderVersionPage = renderVersionPage;

console.log('[app-nav.js] 导航模块已加载');
