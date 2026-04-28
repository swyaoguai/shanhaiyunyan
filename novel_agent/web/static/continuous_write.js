/**
 * 无限续写功能模块（独立版本）
 * 与多Agent写作完全分离，有独立的数据存储
 */

// ===== 无限续写状态 =====
function createInfiniteWriteProjectState() {
    return {
        sessionId: 'infinite_' + Date.now(),
        chapters: [],
        currentChapter: 0,
        totalWords: 0,
        selectedModel: '',
        selectedApiConfigId: '',
        summaryInterval: 10,
        pendingSummaries: [],
        enableTrendsFusion: false,
        selectedTrendsPlatforms: ['toutiao', 'douyin'],
        config: {
            wordsPerChapter: 2500,
            autoSaveToKB: true
        },
        continuationContext: null,
        showMemoryPreview: false,
        mainPanelCollapsed: false,
        activeView: 'panel',
        activeChapterNumber: null
    };
}

const INFINITE_WRITE_LEGACY_STORAGE_KEY = 'infinite_write_data';
const INFINITE_WRITE_LEGACY_MODEL_KEY = 'infinite_write_model';

const infiniteWriteState = {
    isRunning: false,
    globalApiConfig: null,
    apiConfigs: [],
    activeConfigId: '',
    showTrends: true,
    ...createInfiniteWriteProjectState()
};

function getInfiniteWriteStorageKey(projectId = store?.currentProjectId || '') {
    return projectId ? `infinite_write_data_${projectId}` : INFINITE_WRITE_LEGACY_STORAGE_KEY;
}

function getInfiniteWriteModelStorageKey(projectId = store?.currentProjectId || '') {
    return projectId ? `infinite_write_model_${projectId}` : INFINITE_WRITE_LEGACY_MODEL_KEY;
}

function applyInfiniteWriteProjectState(data = {}) {
    const defaults = createInfiniteWriteProjectState();
    infiniteWriteState.sessionId = data.sessionId || defaults.sessionId;
    infiniteWriteState.chapters = Array.isArray(data.chapters) ? data.chapters : defaults.chapters;
    infiniteWriteState.currentChapter = data.currentChapter || defaults.currentChapter;
    infiniteWriteState.totalWords = data.totalWords || defaults.totalWords;
    infiniteWriteState.selectedModel = data.selectedModel || defaults.selectedModel;
    infiniteWriteState.selectedApiConfigId = data.selectedApiConfigId || defaults.selectedApiConfigId;
    infiniteWriteState.summaryInterval = data.summaryInterval || defaults.summaryInterval;
    infiniteWriteState.pendingSummaries = Array.isArray(data.pendingSummaries) ? data.pendingSummaries : defaults.pendingSummaries;
    infiniteWriteState.enableTrendsFusion = Boolean(data.enableTrendsFusion);
    infiniteWriteState.selectedTrendsPlatforms = Array.isArray(data.selectedTrendsPlatforms) && data.selectedTrendsPlatforms.length > 0
        ? data.selectedTrendsPlatforms
        : defaults.selectedTrendsPlatforms;
    infiniteWriteState.config = {
        ...defaults.config,
        ...(data.config || {})
    };
    infiniteWriteState.continuationContext = data.continuationContext && typeof data.continuationContext === 'object'
        ? data.continuationContext
        : defaults.continuationContext;
    infiniteWriteState.showMemoryPreview = Boolean(data.showMemoryPreview);
    infiniteWriteState.mainPanelCollapsed = Boolean(data.mainPanelCollapsed);
    infiniteWriteState.activeView = data.activeView === 'chapter' ? 'chapter' : 'panel';
    infiniteWriteState.activeChapterNumber = typeof data.activeChapterNumber === 'number'
        ? data.activeChapterNumber
        : null;
}

function loadInfiniteWriteDataForCurrentProject() {
    const projectId = store?.currentProjectId || '';
    const storageKey = getInfiniteWriteStorageKey(projectId);
    let raw = localStorage.getItem(storageKey);

    if (!raw) {
        const legacyRaw = localStorage.getItem(INFINITE_WRITE_LEGACY_STORAGE_KEY);
        if (legacyRaw) {
            raw = legacyRaw;
            if (projectId) {
                localStorage.setItem(storageKey, legacyRaw);
                localStorage.removeItem(INFINITE_WRITE_LEGACY_STORAGE_KEY);
            }
        }
    }

    let parsed = {};
    if (raw) {
        try {
            parsed = JSON.parse(raw) || {};
        } catch (e) {
            console.error('[InfiniteWrite] 解析项目存储失败:', e);
        }
    }

    if (!parsed.selectedModel) {
        parsed.selectedModel = localStorage.getItem(getInfiniteWriteModelStorageKey(projectId))
            || localStorage.getItem(INFINITE_WRITE_LEGACY_MODEL_KEY)
            || '';
    }

    applyInfiniteWriteProjectState(parsed);

    if (infiniteWriteState.activeView === 'chapter') {
        const chapterExists = infiniteWriteState.chapters.some((chapter) => chapter.chapter_number === infiniteWriteState.activeChapterNumber);
        if (!chapterExists) {
            infiniteWriteState.activeView = 'panel';
            infiniteWriteState.activeChapterNumber = null;
        }
    }
}

function clearInfiniteWriteDataForProject(projectId = store?.currentProjectId || '') {
    localStorage.removeItem(getInfiniteWriteStorageKey(projectId));
    localStorage.removeItem(getInfiniteWriteModelStorageKey(projectId));
}

function setInfiniteWriteActiveView(view, chapterNumber = null) {
    infiniteWriteState.activeView = view === 'chapter' ? 'chapter' : 'panel';
    infiniteWriteState.activeChapterNumber = infiniteWriteState.activeView === 'chapter' && typeof chapterNumber === 'number'
        ? chapterNumber
        : null;
}

async function loadInfiniteWriteContinuationContext() {
    if (!infiniteWriteState.sessionId || infiniteWriteState.chapters.length === 0) {
        infiniteWriteState.continuationContext = null;
        return null;
    }

    try {
        const response = await apiCall(`/api/continuous-write/session/${encodeURIComponent(infiniteWriteState.sessionId)}/context`, 'GET');
        infiniteWriteState.continuationContext = response?.context || null;
        saveInfiniteWriteData();
        return infiniteWriteState.continuationContext;
    } catch (e) {
        console.warn('[InfiniteWrite] 加载续写上下文失败:', e);
        return infiniteWriteState.continuationContext || null;
    }
}

function renderInfiniteWriteCharacterAnchors() {
    const context = infiniteWriteState.continuationContext;
    const characterStates = context?.character_states && typeof context.character_states === 'object'
        ? Object.values(context.character_states)
        : [];
    const contextSummary = String(context?.context_summary || '').trim();

    if (characterStates.length === 0 && !contextSummary) {
        return '';
    }

    const cards = characterStates
        .sort((a, b) => Number(b?.last_chapter || 0) - Number(a?.last_chapter || 0))
        .slice(0, 6)
        .map((item) => {
            const notes = Array.isArray(item?.notes) ? item.notes : [];
            return `
                <div style="padding: 12px 14px; border-radius: 10px; background: rgba(255,255,255,0.04); border: 1px solid rgba(255,255,255,0.08);">
                    <div style="font-size: 14px; color: var(--text-primary); font-weight: 600;">${escapeHtml(item?.name || '未命名角色')}</div>
                    <div style="margin-top: 6px; font-size: 12px; color: var(--text-secondary); line-height: 1.6;">
                        ${item?.last_chapter ? `<div>最近出现：第${escapeHtml(String(item.last_chapter))}章</div>` : ''}
                        ${item?.status ? `<div>当前状态：${escapeHtml(String(item.status))}</div>` : ''}
                        ${item?.location ? `<div>当前位置：${escapeHtml(String(item.location))}</div>` : ''}
                        ${notes.length > 0 ? `<div>最近表现：${escapeHtml(String(notes[notes.length - 1]))}</div>` : ''}
                    </div>
                </div>
            `;
        }).join('');

    return `
        <div style="background: rgba(255,255,255,0.03); border: 1px solid var(--border-color); border-radius: 12px; padding: 20px; margin-bottom: 24px;">
            <h3 style="margin-bottom: 12px; font-size: 15px; color: var(--text-primary); display: flex; align-items: center; gap: 8px;">
                <i class="ri-user-star-line" style="color: #60a5fa;"></i>
                人物和设定锚点
            </h3>
            <div style="font-size: 13px; color: var(--text-secondary); line-height: 1.7; margin-bottom: 14px;">
                这里展示系统当前记住的人物状态和最近剧情，能帮你判断续写有没有跑偏。
            </div>
            ${contextSummary ? `<div style="padding: 12px 14px; border-radius: 10px; background: rgba(96, 165, 250, 0.08); border: 1px solid rgba(96, 165, 250, 0.2); color: var(--text-secondary); font-size: 12px; line-height: 1.7; margin-bottom: 14px;">${escapeHtml(contextSummary)}</div>` : ''}
            ${cards ? `<div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 12px;">${cards}</div>` : ''}
        </div>
    `;
}

function toggleInfiniteWriteMemoryPreview(force = null) {
    const next = typeof force === 'boolean'
        ? force
        : !Boolean(infiniteWriteState.showMemoryPreview);
    infiniteWriteState.showMemoryPreview = next;
    const panel = document.getElementById('iw-memory-preview-panel');
    const btn = document.getElementById('iw-memory-preview-toggle');
    if (panel) {
        panel.style.display = next ? '' : 'none';
    }
    if (btn) {
        btn.textContent = next ? '收起系统记忆' : '先看系统记忆';
    }
    saveInfiniteWriteData();
}

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
    loadInfiniteWriteDataForCurrentProject();

    const navList = document.getElementById('nav-list-container');
    if (!navList) return;
    
    navList.innerHTML = '';
    
    // 创作入口
    const startEntry = document.createElement('div');
    startEntry.className = `list-item ${infiniteWriteState.activeView === 'panel' ? 'active' : ''}`;
    startEntry.style.cssText = 'background: linear-gradient(135deg, rgba(139, 92, 246, 0.15), rgba(99, 102, 241, 0.1)); border: 1px solid rgba(139, 92, 246, 0.3); margin: 4px 8px; border-radius: 8px;';
    startEntry.innerHTML = `
        <i class="ri-play-circle-line" style="color: #8b5cf6;"></i>
        <span style="font-weight: 500;">创作面板</span>
    `;
    window.makeElementActivatable(startEntry, () => {
        startEntry.click();
    }, { bindClick: false });
    startEntry.addEventListener('click', () => {
        if (typeof window.confirmLeaveInfiniteWriteEditor === 'function' &&
            !window.confirmLeaveInfiniteWriteEditor('切换到创作面板')) {
            return;
        }
        setInfiniteWriteActiveView('panel');
        saveInfiniteWriteData();
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

    loadInfiniteWriteDataForCurrentProject();
    
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
        <div class="iw-nav-chapter list-item ${infiniteWriteState.activeView === 'chapter' && infiniteWriteState.activeChapterNumber === ch.chapter_number ? 'active' : ''}" data-chapter="${index}" style="padding: 10px 12px; cursor: pointer; display: flex; align-items: center; gap: 8px;">
            <i class="ri-file-text-line" style="opacity: 0.5;"></i>
            <span style="flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: 12px;">
                ${formatChapterDisplay(ch.chapter_number, ch.title)}
            </span>
            <span class="iw-nav-word-count" style="color: var(--text-secondary); font-size: 10px; flex-shrink: 0;">
                ${(ch.word_count || 0).toLocaleString()}字
            </span>
            <div class="item-actions" style="display: flex; gap: 4px; opacity: 0; transition: opacity 0.2s; flex-shrink: 0;">
                <button class="edit-btn" title="编辑" style="background: none; border: none; color: var(--text-secondary); cursor: pointer; padding: 4px;">
                    <i class="ri-edit-line"></i>
                </button>
                <button class="delete-btn" title="删除" style="background: none; border: none; color: #ef4444; cursor: pointer; padding: 4px;">
                    <i class="ri-delete-bin-line"></i>
                </button>
            </div>
        </div>
    `).join('');
    
    // 绑定点击事件
    container.querySelectorAll('.iw-nav-chapter').forEach(item => {
        window.makeElementActivatable(item, () => {
            item.click();
        }, {
            allowWhen: (event) => !event.target.closest('.item-actions'),
            bindClick: false
        });

        item.addEventListener('mouseenter', () => {
            const actions = item.querySelector('.item-actions');
            const wordCount = item.querySelector('.iw-nav-word-count');
            if (actions) actions.style.opacity = '1';
            if (wordCount) wordCount.style.display = 'none';
        });

        item.addEventListener('mouseleave', () => {
            const actions = item.querySelector('.item-actions');
            const wordCount = item.querySelector('.iw-nav-word-count');
            if (actions) actions.style.opacity = '0';
            if (wordCount) wordCount.style.display = '';
        });

        item.addEventListener('click', (e) => {
            if (e.target.closest('.item-actions')) {
                return;
            }
            if (typeof window.confirmLeaveInfiniteWriteEditor === 'function' &&
                !window.confirmLeaveInfiniteWriteEditor('切换章节')) {
                return;
            }
            const index = parseInt(item.dataset.chapter);
            const chapter = infiniteWriteState.chapters[index];
            if (chapter) {
                setInfiniteWriteActiveView('chapter', chapter.chapter_number);
                saveInfiniteWriteData();
                showInfiniteWriteChapterPreview(chapter);
            }
        });

        item.querySelector('.edit-btn')?.addEventListener('click', (e) => {
            e.stopPropagation();
            const index = parseInt(item.dataset.chapter);
            const chapter = infiniteWriteState.chapters[index];
            if (chapter) {
                showInfiniteWriteChapterPreview(chapter);
            }
        });

        item.querySelector('.delete-btn')?.addEventListener('click', async (e) => {
            e.stopPropagation();
            const index = parseInt(item.dataset.chapter);
            const chapter = infiniteWriteState.chapters[index];
            if (!chapter) return;
            const confirmed = confirm(`确定要删除「第${chapter.chapter_number}章 ${chapter.title || ''}」吗？\n\n此操作不可恢复！`);
            if (!confirmed) return;
            if (typeof window.deleteIWChapterByNumber === 'function') {
                await window.deleteIWChapterByNumber(chapter.chapter_number, { confirmed: true });
            }
        });
    });
}

// ===== 多Agent写作导航面板 =====
const COLLAB_TRACE_FILTERS_STORAGE_KEY = 'collab_trace_filters';
const COLLAB_TRACE_NAMED_FILTERS_STORAGE_KEY = 'collab_trace_named_filters';

const multiAgentWriteState = {
    activeView: 'chapters',
    collabTraceFilters: {
        stage: 'all',
        type: 'all'
    },
    collabTraceExpandedEventIds: []
};

window.multiAgentWriteState = multiAgentWriteState;

function setMultiAgentWriteActiveView(view) {
    const normalized = String(view || '').trim();
    if (['status', 'chapters', 'knowledge'].includes(normalized)) {
        multiAgentWriteState.activeView = normalized;
    } else {
        multiAgentWriteState.activeView = 'chapters';
    }
}

function getCollabTaskStatusMeta(status) {
    const normalized = String(status || 'pending').trim().toLowerCase() || 'pending';
    const meta = {
        pending: { label: '待处理', color: '#94a3b8', bg: 'rgba(148, 163, 184, 0.16)' },
        claimed: { label: '已认领', color: '#60a5fa', bg: 'rgba(96, 165, 250, 0.16)' },
        running: { label: '执行中', color: '#a78bfa', bg: 'rgba(167, 139, 250, 0.18)' },
        blocked: { label: '阻塞', color: '#f59e0b', bg: 'rgba(245, 158, 11, 0.16)' },
        review_required: { label: '待复核', color: '#fb7185', bg: 'rgba(251, 113, 133, 0.16)' },
        completed: { label: '已完成', color: '#22c55e', bg: 'rgba(34, 197, 94, 0.16)' },
        failed: { label: '失败', color: '#ef4444', bg: 'rgba(239, 68, 68, 0.16)' },
        aborted: { label: '已中止', color: '#f97316', bg: 'rgba(249, 115, 22, 0.16)' }
    };
    return meta[normalized] || {
        label: normalized,
        color: 'var(--text-secondary)',
        bg: 'rgba(255,255,255,0.08)'
    };
}

function normalizeCollabRuntimeTaskPool(taskPool) {
    if (!taskPool || typeof taskPool !== 'object') {
        return {
            metadata: {},
            tasks: [],
            statusCount: {}
        };
    }
    const tasks = Array.isArray(taskPool.tasks) ? taskPool.tasks.filter((item) => item && typeof item === 'object') : [];
    const statusCount = {};
    tasks.forEach((task) => {
        const key = String(task.status || 'pending').trim() || 'pending';
        statusCount[key] = (statusCount[key] || 0) + 1;
    });
    return {
        metadata: taskPool.metadata && typeof taskPool.metadata === 'object' ? taskPool.metadata : {},
        tasks,
        statusCount
    };
}

function normalizeCollabExecutionTraceEvent(event) {
    if (!event || typeof event !== 'object') {
        return null;
    }
    const normalized = { ...event };
    if (!normalized.timestamp && normalized.created_at) {
        normalized.timestamp = normalized.created_at;
    }
    delete normalized.created_at;
    return normalized;
}

function normalizeCollabExecutionTrace(trace) {
    if (!trace || typeof trace !== 'object') {
        return {
            status: 'idle',
            events: []
        };
    }
    return {
        status: String(trace.status || 'idle').trim() || 'idle',
        events: Array.isArray(trace.events)
            ? trace.events
                .map((item) => normalizeCollabExecutionTraceEvent(item))
                .filter((item) => item && typeof item === 'object')
            : []
    };
}

function getCollabTraceEventTypeLabel(type) {
    const key = String(type || '').trim();
    const labels = {
        contract_confirmation: '合同确认',
        contract_rejection: '合同拒绝',
        task_registered: '任务注册',
        task_started: '任务开始',
        task_completed: '任务完成',
        task_failed: '任务失败',
        task_fallback_started: '回退启动',
        project_ready_execution_cycle: '项目调度批次'
    };
    return labels[key] || (key || '未知事件');
}

function getCollabTraceStageMeta(event) {
    const type = String(event?.type || event?.event || '').trim();
    const taskType = String(event?.task_type || '').trim();

    if (type === 'contract_confirmation' || type === 'contract_rejection') {
        return { key: 'contract_init', label: '合同/初始化' };
    }
    if (type === 'project_ready_execution_cycle') {
        return { key: 'project_dispatch', label: '项目调度' };
    }
    if (taskType === 'build_world') {
        return { key: 'build_world', label: '世界观构建' };
    }
    if (taskType === 'build_outline') {
        return { key: 'build_outline', label: '大纲生成' };
    }
    if (taskType === 'write_chapter') {
        return { key: 'write_chapter', label: '章节写作' };
    }
    if (taskType === 'summary_orchestrate') {
        return { key: 'summary_orchestrate', label: '阶段总结' };
    }
    if (taskType === 'context_plan') {
        return { key: 'context_plan', label: '上下文规划' };
    }
    if (taskType === 'content_read') {
        return { key: 'content_read', label: '内容读取' };
    }
    if (taskType === 'evaluate_chapter') {
        return { key: 'evaluate_chapter', label: '章节评估' };
    }
    if (taskType === 'polish_chapter') {
        return { key: 'polish_chapter', label: '章节润色' };
    }
    if (taskType === 'expand_content') {
        return { key: 'expand_content', label: '内容补足' };
    }
    return { key: 'other', label: '其他阶段' };
}

function buildCollabTraceFilterOptions(events) {
    const normalizedEvents = Array.isArray(events) ? events : [];
    const stageMap = new Map();
    const typeMap = new Map();

    normalizedEvents.forEach((event) => {
        const stageMeta = getCollabTraceStageMeta(event);
        if (stageMeta.key && !stageMap.has(stageMeta.key)) {
            stageMap.set(stageMeta.key, stageMeta.label);
        }
        const type = String(event?.type || event?.event || '').trim();
        if (type && !typeMap.has(type)) {
            typeMap.set(type, getCollabTraceEventTypeLabel(type));
        }
    });

    return {
        stageOptions: Array.from(stageMap.entries()).map(([value, label]) => ({ value, label })),
        typeOptions: Array.from(typeMap.entries()).map(([value, label]) => ({ value, label }))
    };
}

function loadCollabTraceFiltersFromStorage() {
    try {
        const raw = localStorage.getItem(COLLAB_TRACE_FILTERS_STORAGE_KEY);
        if (!raw) {
            return null;
        }
        const parsed = JSON.parse(raw);
        if (!parsed || typeof parsed !== 'object') {
            return null;
        }
        return {
            stage: String(parsed.stage || 'all').trim() || 'all',
            type: String(parsed.type || 'all').trim() || 'all'
        };
    } catch (e) {
        console.warn('[CollabTrace] 读取过滤条件失败:', e);
        return null;
    }
}

function saveCollabTraceFiltersToStorage(filters = {}) {
    try {
        localStorage.setItem(COLLAB_TRACE_FILTERS_STORAGE_KEY, JSON.stringify({
            stage: String(filters.stage || 'all').trim() || 'all',
            type: String(filters.type || 'all').trim() || 'all'
        }));
    } catch (e) {
        console.warn('[CollabTrace] 保存过滤条件失败:', e);
    }
}

function loadCollabTraceNamedFiltersFromStorage() {
    try {
        const raw = localStorage.getItem(COLLAB_TRACE_NAMED_FILTERS_STORAGE_KEY);
        if (!raw) {
            return [];
        }
        const parsed = JSON.parse(raw);
        if (!Array.isArray(parsed)) {
            return [];
        }
        return parsed
            .filter((item) => item && typeof item === 'object')
            .map((item) => ({
                id: String(item.id || '').trim() || `template_${Date.now()}`,
                name: String(item.name || '').trim(),
                filters: {
                    stage: String(item.filters?.stage || 'all').trim() || 'all',
                    type: String(item.filters?.type || 'all').trim() || 'all'
                },
                updated_at: String(item.updated_at || '').trim()
            }))
            .filter((item) => item.name);
    } catch (e) {
        console.warn('[CollabTrace] 读取命名过滤模板失败:', e);
        return [];
    }
}

function saveCollabTraceNamedFiltersToStorage(templates = []) {
    try {
        localStorage.setItem(COLLAB_TRACE_NAMED_FILTERS_STORAGE_KEY, JSON.stringify(
            Array.isArray(templates) ? templates : []
        ));
    } catch (e) {
        console.warn('[CollabTrace] 保存命名过滤模板失败:', e);
    }
}

function getCollabTraceNamedFilters() {
    return loadCollabTraceNamedFiltersFromStorage();
}

function saveCollabTraceNamedFilter(name, filters = {}) {
    const normalizedName = String(name || '').trim();
    if (!normalizedName) {
        return getCollabTraceNamedFilters();
    }
    const normalizedFilters = {
        stage: String(filters.stage || 'all').trim() || 'all',
        type: String(filters.type || 'all').trim() || 'all'
    };
    const current = getCollabTraceNamedFilters();
    const existing = current.find((item) => item.name === normalizedName);
    const nextItem = {
        id: existing?.id || `template_${Date.now()}`,
        name: normalizedName,
        filters: normalizedFilters,
        updated_at: new Date().toISOString()
    };
    const nextTemplates = existing
        ? current.map((item) => item.name === normalizedName ? nextItem : item)
        : [nextItem, ...current];
    saveCollabTraceNamedFiltersToStorage(nextTemplates);
    return getCollabTraceNamedFilters();
}

function deleteCollabTraceNamedFilter(templateId) {
    const normalizedId = String(templateId || '').trim();
    if (!normalizedId) {
        return getCollabTraceNamedFilters();
    }
    const nextTemplates = getCollabTraceNamedFilters().filter((item) => item.id !== normalizedId);
    saveCollabTraceNamedFiltersToStorage(nextTemplates);
    return getCollabTraceNamedFilters();
}

function renameCollabTraceNamedFilter(templateId, nextName) {
    const normalizedId = String(templateId || '').trim();
    const normalizedName = String(nextName || '').trim();
    if (!normalizedId || !normalizedName) {
        return getCollabTraceNamedFilters();
    }
    const current = getCollabTraceNamedFilters();
    const duplicate = current.find((item) => item.id !== normalizedId && item.name === normalizedName);
    if (duplicate) {
        return null;
    }
    const renamed = current.map((item) => item.id === normalizedId
        ? {
            ...item,
            name: normalizedName,
            updated_at: new Date().toISOString()
        }
        : item);
    saveCollabTraceNamedFiltersToStorage(renamed);
    return getCollabTraceNamedFilters();
}

function moveCollabTraceNamedFilter(templateId, direction) {
    const normalizedId = String(templateId || '').trim();
    const normalizedDirection = String(direction || '').trim().toLowerCase();
    if (!normalizedId || !['up', 'down'].includes(normalizedDirection)) {
        return getCollabTraceNamedFilters();
    }
    const current = getCollabTraceNamedFilters();
    const currentIndex = current.findIndex((item) => item.id === normalizedId);
    if (currentIndex < 0) {
        return current;
    }
    const targetIndex = normalizedDirection === 'up'
        ? currentIndex - 1
        : currentIndex + 1;
    if (targetIndex < 0 || targetIndex >= current.length) {
        return current;
    }
    const nextTemplates = current.slice();
    const [moved] = nextTemplates.splice(currentIndex, 1);
    nextTemplates.splice(targetIndex, 0, moved);
    saveCollabTraceNamedFiltersToStorage(nextTemplates);
    return getCollabTraceNamedFilters();
}

function renderCollabTraceNamedFilters(templates = [], options = {}) {
    const stageOptions = Array.isArray(options.stageOptions) ? options.stageOptions : [];
    const typeOptions = Array.isArray(options.typeOptions) ? options.typeOptions : [];
    if (!Array.isArray(templates) || templates.length === 0) {
        return `
            <div style="font-size: 12px; color: var(--text-secondary);">
                暂无已保存模板，可将当前过滤条件保存为命名模板后复用。
            </div>
        `;
    }
    return `
        <div style="display: flex; flex-direction: column; gap: 10px;">
            ${templates.map((template) => {
                const stageLabel = template.filters.stage === 'all'
                    ? '全部阶段'
                    : (stageOptions.find((item) => item.value === template.filters.stage)?.label || template.filters.stage);
                const typeLabel = template.filters.type === 'all'
                    ? '全部事件'
                    : (typeOptions.find((item) => item.value === template.filters.type)?.label || template.filters.type);
                return `
                    <div class="collab-trace-template-card" data-template-id="${escapeHtml(template.id)}" style="padding: 12px; border-radius: 10px; background: rgba(255,255,255,0.04); border: 1px solid var(--border-color);">
                        <div style="display: flex; align-items: flex-start; justify-content: space-between; gap: 10px; margin-bottom: 8px;">
                            <div style="min-width: 0; flex: 1;">
                                <div class="collab-trace-template-name" style="font-size: 13px; font-weight: 600; color: var(--text-primary);">${escapeHtml(template.name)}</div>
                                <div style="margin-top: 4px; font-size: 11px; color: var(--text-secondary);">
                                    最近更新：${escapeHtml(template.updated_at || '未记录')}
                                </div>
                            </div>
                            <div style="display: flex; flex-wrap: wrap; justify-content: flex-end; gap: 8px;">
                                <button type="button" class="collab-trace-template-move-up-btn" data-template-id="${escapeHtml(template.id)}" style="padding: 6px 10px; border-radius: 8px; border: 1px solid var(--border-color); background: rgba(255,255,255,0.05); color: var(--text-secondary); cursor: pointer; font-size: 12px; font-weight: 600;">
                                    上移
                                </button>
                                <button type="button" class="collab-trace-template-move-down-btn" data-template-id="${escapeHtml(template.id)}" style="padding: 6px 10px; border-radius: 8px; border: 1px solid var(--border-color); background: rgba(255,255,255,0.05); color: var(--text-secondary); cursor: pointer; font-size: 12px; font-weight: 600;">
                                    下移
                                </button>
                                <button type="button" class="collab-trace-template-rename-btn" data-template-id="${escapeHtml(template.id)}" data-template-name="${escapeHtml(template.name)}" style="padding: 6px 10px; border-radius: 8px; border: 1px solid rgba(245, 158, 11, 0.35); background: rgba(245, 158, 11, 0.12); color: #fcd34d; cursor: pointer; font-size: 12px; font-weight: 600;">
                                    重命名
                                </button>
                                <button type="button" class="collab-trace-template-apply-btn" data-template-id="${escapeHtml(template.id)}" style="padding: 6px 10px; border-radius: 8px; border: 1px solid rgba(99, 102, 241, 0.35); background: rgba(99, 102, 241, 0.16); color: #c7d2fe; cursor: pointer; font-size: 12px; font-weight: 600;">
                                    应用
                                </button>
                                <button type="button" class="collab-trace-template-delete-btn" data-template-id="${escapeHtml(template.id)}" style="padding: 6px 10px; border-radius: 8px; border: 1px solid rgba(239, 68, 68, 0.35); background: rgba(239, 68, 68, 0.12); color: #fca5a5; cursor: pointer; font-size: 12px; font-weight: 600;">
                                    删除
                                </button>
                            </div>
                        </div>
                        <div style="display: flex; flex-wrap: wrap; gap: 8px;">
                            <span style="display: inline-flex; align-items: center; gap: 6px; padding: 4px 8px; border-radius: 999px; background: rgba(99, 102, 241, 0.10); color: #c7d2fe; font-size: 12px;">
                                <strong>阶段</strong>
                                <span>${escapeHtml(stageLabel)}</span>
                            </span>
                            <span style="display: inline-flex; align-items: center; gap: 6px; padding: 4px 8px; border-radius: 999px; background: rgba(34, 197, 94, 0.10); color: #bbf7d0; font-size: 12px;">
                                <strong>事件</strong>
                                <span>${escapeHtml(typeLabel)}</span>
                            </span>
                        </div>
                    </div>
                `;
            }).join('')}
        </div>
    `;
}

function getCollabTraceFilters() {
    const current = multiAgentWriteState.collabTraceFilters;
    const persisted = loadCollabTraceFiltersFromStorage();
    if ((!current || typeof current !== 'object') && persisted) {
        multiAgentWriteState.collabTraceFilters = persisted;
    } else if ((!current || typeof current !== 'object') && !persisted) {
        multiAgentWriteState.collabTraceFilters = { stage: 'all', type: 'all' };
    } else if (persisted) {
        multiAgentWriteState.collabTraceFilters = {
            stage: String(current?.stage || persisted.stage || 'all').trim() || 'all',
            type: String(current?.type || persisted.type || 'all').trim() || 'all'
        };
    }
    return {
        stage: String(multiAgentWriteState.collabTraceFilters?.stage || 'all').trim() || 'all',
        type: String(multiAgentWriteState.collabTraceFilters?.type || 'all').trim() || 'all'
    };
}

function setCollabTraceFilters(filters = {}) {
    const current = getCollabTraceFilters();
    multiAgentWriteState.collabTraceFilters = {
        stage: String(filters.stage || current.stage || 'all').trim() || 'all',
        type: String(filters.type || current.type || 'all').trim() || 'all'
    };
    saveCollabTraceFiltersToStorage(multiAgentWriteState.collabTraceFilters);
    return getCollabTraceFilters();
}

function getCollabTraceExpandedEventIds() {
    return Array.isArray(multiAgentWriteState.collabTraceExpandedEventIds)
        ? multiAgentWriteState.collabTraceExpandedEventIds
        : [];
}

function toggleCollabTraceExpandedEventId(eventId) {
    const normalized = String(eventId || '').trim();
    if (!normalized) {
        return getCollabTraceExpandedEventIds();
    }
    const current = new Set(getCollabTraceExpandedEventIds());
    if (current.has(normalized)) {
        current.delete(normalized);
    } else {
        current.add(normalized);
    }
    multiAgentWriteState.collabTraceExpandedEventIds = Array.from(current);
    return getCollabTraceExpandedEventIds();
}

function clearCollabTraceExpandedEventIds() {
    multiAgentWriteState.collabTraceExpandedEventIds = [];
}

function buildCollabTraceQuickFilters(events) {
    const normalizedEvents = Array.isArray(events) ? events : [];
    const availableStages = new Set();
    const availableTypes = new Set();

    normalizedEvents.forEach((event) => {
        const stageMeta = getCollabTraceStageMeta(event);
        if (stageMeta.key) {
            availableStages.add(stageMeta.key);
        }
        const type = String(event?.type || event?.event || '').trim();
        if (type) {
            availableTypes.add(type);
        }
    });

    const presets = [
        { key: 'all', label: '查看全部', filters: { stage: 'all', type: 'all' } },
        { key: 'summary_orchestrate', label: '只看阶段总结', filters: { stage: 'summary_orchestrate', type: 'all' } },
        { key: 'project_dispatch', label: '只看项目调度', filters: { stage: 'project_dispatch', type: 'all' } },
        { key: 'task_completed', label: '只看任务完成', filters: { stage: 'all', type: 'task_completed' } },
        { key: 'task_failed', label: '只看任务失败', filters: { stage: 'all', type: 'task_failed' } }
    ];

    return presets.filter((preset) => {
        const stage = String(preset.filters.stage || 'all').trim();
        const type = String(preset.filters.type || 'all').trim();
        if (stage !== 'all' && !availableStages.has(stage)) {
            return false;
        }
        if (type !== 'all' && !availableTypes.has(type)) {
            return false;
        }
        return true;
    });
}

function filterCollabExecutionEvents(events, filters = {}) {
    const normalizedEvents = Array.isArray(events) ? events : [];
    const stageFilter = String(filters.stage || 'all').trim() || 'all';
    const typeFilter = String(filters.type || 'all').trim() || 'all';

    return normalizedEvents.filter((event) => {
        const stageMeta = getCollabTraceStageMeta(event);
        const eventType = String(event?.type || event?.event || '').trim();
        if (stageFilter !== 'all' && stageMeta.key !== stageFilter) {
            return false;
        }
        if (typeFilter !== 'all' && eventType !== typeFilter) {
            return false;
        }
        return true;
    });
}

function buildCollabTraceStats(events) {
    const normalizedEvents = Array.isArray(events) ? events : [];
    const stageMap = new Map();
    const typeMap = new Map();

    normalizedEvents.forEach((event) => {
        const stageMeta = getCollabTraceStageMeta(event);
        stageMap.set(stageMeta.label, (stageMap.get(stageMeta.label) || 0) + 1);

        const typeLabel = getCollabTraceEventTypeLabel(String(event?.type || event?.event || '').trim());
        typeMap.set(typeLabel, (typeMap.get(typeLabel) || 0) + 1);
    });

    const sortByCountDesc = (a, b) => {
        if (b[1] !== a[1]) {
            return b[1] - a[1];
        }
        return String(a[0]).localeCompare(String(b[0]), 'zh-CN');
    };

    return {
        stageStats: Array.from(stageMap.entries())
            .sort(sortByCountDesc)
            .map(([label, count]) => ({ label, count })),
        typeStats: Array.from(typeMap.entries())
            .sort(sortByCountDesc)
            .map(([label, count]) => ({ label, count }))
    };
}

function renderCollabTraceFilterBreadcrumbs(filters = {}, options = {}) {
    const normalizedFilters = {
        stage: String(filters.stage || 'all').trim() || 'all',
        type: String(filters.type || 'all').trim() || 'all'
    };
    const stageOptions = Array.isArray(options.stageOptions) ? options.stageOptions : [];
    const typeOptions = Array.isArray(options.typeOptions) ? options.typeOptions : [];
    const stageLabel = normalizedFilters.stage === 'all'
        ? '全部阶段'
        : (stageOptions.find((item) => item.value === normalizedFilters.stage)?.label || normalizedFilters.stage);
    const typeLabel = normalizedFilters.type === 'all'
        ? '全部事件'
        : (typeOptions.find((item) => item.value === normalizedFilters.type)?.label || normalizedFilters.type);

    return `
        <div id="collab-execution-filter-breadcrumbs" style="display: flex; flex-wrap: wrap; align-items: center; gap: 8px;">
            <span style="font-size: 12px; color: var(--text-secondary);">当前筛选：</span>
            <span class="collab-trace-filter-breadcrumb" data-kind="stage" style="display: inline-flex; align-items: center; gap: 6px; padding: 6px 10px; border-radius: 999px; background: rgba(99, 102, 241, 0.12); color: #c7d2fe; font-size: 12px;">
                <strong style="font-weight: 600;">阶段</strong>
                <span>${escapeHtml(stageLabel)}</span>
            </span>
            <span class="collab-trace-filter-breadcrumb" data-kind="type" style="display: inline-flex; align-items: center; gap: 6px; padding: 6px 10px; border-radius: 999px; background: rgba(34, 197, 94, 0.12); color: #bbf7d0; font-size: 12px;">
                <strong style="font-weight: 600;">事件</strong>
                <span>${escapeHtml(typeLabel)}</span>
            </span>
        </div>
    `;
}

function renderCollabExecutionTimeline(events, filters = {}) {
    if (!Array.isArray(events) || events.length === 0) {
        return `
            <div style="padding: 18px; border: 1px dashed var(--border-color); border-radius: 12px; color: var(--text-secondary); font-size: 13px;">
                暂无协作执行事件。
            </div>
        `;
    }

    const filteredEvents = filterCollabExecutionEvents(events, filters);
    const latestMatchedEvent = filteredEvents[filteredEvents.length - 1] || null;
    if (filteredEvents.length === 0) {
        return `
            <div style="padding: 18px; border: 1px dashed var(--border-color); border-radius: 12px; color: var(--text-secondary); font-size: 13px;">
                当前筛选条件下没有匹配事件，请切换阶段或事件类型后重试。
            </div>
        `;
    }

    return `
        <div style="display: flex; flex-direction: column; gap: 12px;">
            ${filteredEvents.slice().reverse().slice(0, 24).map((event, index) => {
                const isLatestMatch = latestMatchedEvent === event;
                const type = String(event.type || event.event || 'event').trim();
                const taskType = String(event.task_type || '').trim();
                const title = String(event.title || '').trim();
                const taskId = String(event.task_id || '').trim();
                const agent = String(event.agent || event.assigned_agent || '').trim();
                const status = String(event.status || '').trim();
                const at = String(event.timestamp || '').trim();
                const stageMeta = getCollabTraceStageMeta(event);
                const headline = title || taskType || getCollabTraceEventTypeLabel(type) || '未命名事件';
                const details = [
                    `阶段：${stageMeta.label}`,
                    agent ? `执行智能体：${agent}` : '',
                    status ? `状态：${getCollabTaskStatusMeta(status).label}` : '',
                    taskId ? `任务ID：${taskId}` : ''
                ].filter(Boolean).join(' · ');
                const traceItemId = `collab-trace-event-${index}`;
                const traceExpandId = taskId || `${type}:${taskType}:${at}:${index}`;
                const isExpanded = getCollabTraceExpandedEventIds().includes(traceExpandId);
                const detailPayload = {
                    type,
                    title,
                    task_type: taskType,
                    task_id: taskId,
                    agent,
                    status,
                    timestamp: at,
                    stage: stageMeta.label
                };
                return `
                    <div id="${escapeHtml(traceItemId)}" class="collab-trace-item ${isLatestMatch ? 'is-latest-match' : ''}" data-trace-stage="${escapeHtml(stageMeta.key)}" data-trace-type="${escapeHtml(type)}" style="position: relative; padding: 14px 16px 14px 22px; background: ${isLatestMatch ? 'rgba(99, 102, 241, 0.10)' : 'rgba(255,255,255,0.03)'}; border: 1px solid ${isLatestMatch ? 'rgba(99, 102, 241, 0.35)' : 'var(--border-color)'}; border-radius: 12px; box-shadow: ${isLatestMatch ? '0 0 0 1px rgba(99, 102, 241, 0.12) inset' : 'none'};">
                        <span style="position: absolute; left: 10px; top: 20px; width: 8px; height: 8px; border-radius: 999px; background: var(--accent-color);"></span>
                        <div style="display: flex; align-items: center; justify-content: space-between; gap: 12px; margin-bottom: 6px;">
                            <div style="display: flex; align-items: center; gap: 8px; min-width: 0;">
                                <div style="font-size: 14px; font-weight: 600; color: var(--text-primary);">${escapeHtml(headline)}</div>
                                ${isLatestMatch ? '<span class="collab-latest-match-badge" style="display: inline-flex; align-items: center; gap: 4px; padding: 2px 8px; border-radius: 999px; background: rgba(99, 102, 241, 0.18); color: #c7d2fe; font-size: 11px; font-weight: 600; white-space: nowrap;">最近匹配</span>' : ''}
                            </div>
                            <div style="display: flex; align-items: center; gap: 8px;">
                                <div style="font-size: 11px; color: var(--text-secondary);">${escapeHtml(getCollabTraceEventTypeLabel(type))}</div>
                                <button type="button" class="collab-trace-expand-btn" data-trace-expand-id="${escapeHtml(traceExpandId)}" style="padding: 6px 10px; border-radius: 8px; border: 1px solid var(--border-color); background: rgba(255,255,255,0.05); color: var(--text-secondary); cursor: pointer; font-size: 12px; font-weight: 600;">
                                    ${isExpanded ? '收起详情' : '展开详情'}
                                </button>
                            </div>
                        </div>
                        ${details ? `<div style="font-size: 12px; color: var(--text-secondary); margin-bottom: 4px;">${escapeHtml(details)}</div>` : ''}
                        ${at ? `<div style="font-size: 11px; color: var(--text-secondary); opacity: 0.8;">${escapeHtml(at)}</div>` : ''}
                        ${isExpanded ? `
                            <div class="collab-trace-item-details" style="margin-top: 10px; padding: 12px; border-radius: 10px; background: rgba(0,0,0,0.16); border: 1px dashed var(--border-color);">
                                <div style="font-size: 12px; color: var(--text-secondary); margin-bottom: 6px;">事件详情</div>
                                <pre style="margin: 0; white-space: pre-wrap; word-break: break-word; font-size: 12px; color: var(--text-secondary);">${escapeHtml(JSON.stringify(detailPayload, null, 2))}</pre>
                            </div>
                        ` : ''}
                    </div>
                `;
            }).join('')}
        </div>
    `;
}

function normalizeProjectReadyExecution(projectReadyExecution) {
    if (!projectReadyExecution || typeof projectReadyExecution !== 'object') {
        return {
            stopReason: '',
            stoppedOnTaskType: '',
            chapterTasksExecuted: 0,
            executedTaskCount: 0,
            maxTasks: 0,
            maxChapterTasks: 0,
            updatedAt: ''
        };
    }
    return {
        stopReason: String(projectReadyExecution.stop_reason || '').trim(),
        stoppedOnTaskType: String(projectReadyExecution.stopped_on_task_type || '').trim(),
        chapterTasksExecuted: Number(projectReadyExecution.chapter_tasks_executed || 0) || 0,
        executedTaskCount: Number(projectReadyExecution.executed_task_count || 0) || 0,
        maxTasks: Number(projectReadyExecution.max_tasks || 0) || 0,
        maxChapterTasks: Number(projectReadyExecution.max_chapter_tasks || 0) || 0,
        updatedAt: String(projectReadyExecution.updated_at || '').trim()
    };
}

function getProjectReadyStopReasonLabel(reason) {
    const key = String(reason || '').trim();
    const labels = {
        unsupported_task_type: '碰到了当前还不支持自动处理的任务',
        max_tasks_reached: '这一轮任务先跑到上限了',
        max_chapter_tasks_reached: '这一轮连续写章先跑满了',
        fallback_triggered: '系统判断这一轮需要先回退处理',
        review_required: '这一步需要你先确认'
    };
    return labels[key] || (key || '暂时没有卡住');
}

function getProjectReadyTaskTypeLabel(taskType) {
    const key = String(taskType || '').trim();
    const labels = {
        build_world: '世界观设定',
        build_outline: '大纲规划',
        write_chapter: '章节写作',
        summary_orchestrate: '阶段总结',
        build_character: '角色设定',
        detail_outlining: '细纲补全',
        chapter_settings: '章纲设定'
    };
    return labels[key] || (key || '未记录');
}

function buildCollabAgentOutputSummaries(tasks) {
    if (!Array.isArray(tasks) || tasks.length === 0) {
        return [];
    }
    const latestByAgent = new Map();
    tasks.forEach((task) => {
        const status = String(task.status || '').trim();
        const agent = String(task.assigned_agent || '').trim();
        const title = String(task.title || task.task_type || '').trim();
        const resultRef = String(task.result_ref || '').trim();
        if (status !== 'completed' || !agent || !title) {
            return;
        }
        const metadata = task.metadata && typeof task.metadata === 'object' ? task.metadata : {};
        latestByAgent.set(agent, {
            agent,
            title,
            resultRef,
            resultKind: String(metadata.result_kind || '').trim(),
            summaryRange: Array.isArray(metadata.summary_range) ? metadata.summary_range : [],
            taskType: String(task.task_type || '').trim()
        });
    });
    return Array.from(latestByAgent.values());
}

function getCollabNextStepSuggestion(projectReadyExecution, nextReadyTasks) {
    const stopReason = String(projectReadyExecution?.stopReason || '').trim();
    const stoppedOnTaskType = String(projectReadyExecution?.stoppedOnTaskType || '').trim();
    if (stopReason === 'review_required') {
        return '建议先回到上一步确认内容，再继续往下推进。';
    }
    if (stopReason === 'fallback_triggered') {
        return `建议先处理「${getProjectReadyTaskTypeLabel(stoppedOnTaskType)}」的回退问题，再继续执行。`;
    }
    if (stopReason === 'max_chapter_tasks_reached') {
        return '建议先看一下刚写完的章节和阶段总结，确认没跑偏，再继续下一批章节。';
    }
    if (stopReason === 'max_tasks_reached') {
        return '这一轮任务已经跑完上限，建议先看当前产出，再决定要不要继续下一轮。';
    }
    if (Array.isArray(nextReadyTasks) && nextReadyTasks.length > 0) {
        return `下一步最适合推进：${String(nextReadyTasks[0].title || nextReadyTasks[0].task_type || '未命名任务').trim()}。`;
    }
    return '当前没有必须立刻处理的动作，可以先看最近产出，再决定下一步。';
}

function getCollabNextReadyTasks(tasks) {
    if (!Array.isArray(tasks) || tasks.length === 0) {
        return [];
    }
    const completedTaskIds = new Set(
        tasks
            .filter((task) => String(task.status || '').trim() === 'completed')
            .map((task) => String(task.task_id || task.id || '').trim())
            .filter(Boolean)
    );
    return tasks.filter((task) => {
        const status = String(task.status || 'pending').trim();
        if (status !== 'pending') {
            return false;
        }
        const dependsOn = Array.isArray(task.depends_on) ? task.depends_on : [];
        return dependsOn.every((dep) => completedTaskIds.has(String(dep || '').trim()));
    });
}

function showCollabTaskDetail(task) {
    const modal = document.getElementById('modal-container');
    if (!modal || !task || typeof task !== 'object') return;

    const title = String(task.title || task.task_type || '未命名任务').trim();
    const taskType = String(task.task_type || '未分类任务').trim();
    const statusMeta = getCollabTaskStatusMeta(task.status);
    const metadata = task.metadata && typeof task.metadata === 'object' ? task.metadata : {};
    const inputs = task.inputs && typeof task.inputs === 'object' ? task.inputs : {};
    const dependsOn = Array.isArray(task.depends_on) ? task.depends_on : [];
    const candidateAgents = Array.isArray(task.candidate_agents) ? task.candidate_agents : [];
    const resultRef = String(task.result_ref || '').trim();
    const assignedAgent = String(task.assigned_agent || '').trim();
    const displayAgent = assignedAgent
        ? (typeof getAgentDisplayName === 'function' ? getAgentDisplayName(assignedAgent) : assignedAgent)
        : '系统还没分配';
    const taskGoal = title || getProjectReadyTaskTypeLabel(taskType) || '未命名任务';
    const dependencyText = dependsOn.length ? dependsOn.join('、') : '没有前置任务';
    const candidateText = candidateAgents.length ? candidateAgents.join('、') : '系统会自动分配';
    const resultText = resultRef || '这一步暂时还没产出文件';
    const summaryHints = [];
    if (typeof inputs.chapter_number === 'number') {
        summaryHints.push(`目标章节：第${inputs.chapter_number}章`);
    }
    if (Array.isArray(metadata.summary_range) && metadata.summary_range.length === 2) {
        summaryHints.push(`涉及范围：第${metadata.summary_range[0]}-${metadata.summary_range[1]}章`);
    }
    if (metadata.result_kind) {
        summaryHints.push(`产物类型：${metadata.result_kind}`);
    }
    const summaryText = summaryHints.length ? summaryHints.join('；') : '这一步主要围绕当前任务素材继续往下推进。';

    modal.classList.remove('hidden');
    modal.innerHTML = `
        <div style="position: fixed; inset: 0; background: rgba(0,0,0,0.68); display: flex; align-items: center; justify-content: center; z-index: 1000; padding: 20px;">
            <div style="width: 760px; max-width: 100%; max-height: 88vh; overflow: auto; background: var(--bg-panel); border: 1px solid var(--border-color); border-radius: 16px; padding: 22px;">
                <div style="display: flex; align-items: center; justify-content: space-between; gap: 12px; margin-bottom: 16px;">
                    <div>
                        <div style="font-size: 18px; font-weight: 700; color: var(--text-primary);">${escapeHtml(title)}</div>
                        <div style="margin-top: 6px; font-size: 12px; color: var(--text-secondary);">${escapeHtml(taskType)}</div>
                    </div>
                    <button id="collab-task-detail-close" type="button" style="background: none; border: none; color: var(--text-secondary); font-size: 24px; cursor: pointer;">
                        <i class="ri-close-line"></i>
                    </button>
                </div>

                <div style="display: flex; flex-wrap: wrap; gap: 10px; margin-bottom: 16px;">
                    <span style="padding: 6px 10px; border-radius: 999px; background: ${statusMeta.bg}; color: ${statusMeta.color}; font-size: 12px; font-weight: 600;">${escapeHtml(statusMeta.label)}</span>
                    <span style="padding: 6px 10px; border-radius: 999px; background: rgba(255,255,255,0.06); color: var(--text-secondary); font-size: 12px;">重试 ${Number(task.retry_count || 0) || 0}</span>
                    <span style="padding: 6px 10px; border-radius: 999px; background: rgba(255,255,255,0.06); color: var(--text-secondary); font-size: 12px;">负责方：${escapeHtml(displayAgent)}</span>
                </div>

                <div style="display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 14px; margin-bottom: 16px;">
                    <div style="padding: 14px; border-radius: 12px; border: 1px solid var(--border-color); background: rgba(255,255,255,0.03);">
                        <div style="font-size: 13px; font-weight: 600; color: var(--text-primary); margin-bottom: 8px;">这一步要做什么</div>
                        <div style="font-size: 12px; color: var(--text-secondary); line-height: 1.8;">${escapeHtml(taskGoal)}</div>
                    </div>
                    <div style="padding: 14px; border-radius: 12px; border: 1px solid var(--border-color); background: rgba(255,255,255,0.03);">
                        <div style="font-size: 13px; font-weight: 600; color: var(--text-primary); margin-bottom: 8px;">现在由谁来做</div>
                        <div style="font-size: 12px; color: var(--text-secondary); line-height: 1.8;">${escapeHtml(displayAgent)}</div>
                    </div>
                </div>

                <div style="display: grid; gap: 14px;">
                    <div style="padding: 14px; border-radius: 12px; border: 1px solid var(--border-color); background: rgba(255,255,255,0.03);">
                        <div style="font-size: 13px; font-weight: 600; color: var(--text-primary); margin-bottom: 8px;">这一步带了什么信息</div>
                        <div style="margin-bottom: 8px; font-size: 12px; color: var(--text-secondary); line-height: 1.8;">${escapeHtml(summaryText)}</div>
                        <pre style="margin: 0; white-space: pre-wrap; word-break: break-word; font-size: 12px; color: var(--text-secondary);">${escapeHtml(JSON.stringify(inputs, null, 2) || '{}')}</pre>
                    </div>
                    <div style="padding: 14px; border-radius: 12px; border: 1px solid var(--border-color); background: rgba(255,255,255,0.03);">
                        <div style="font-size: 13px; font-weight: 600; color: var(--text-primary); margin-bottom: 8px;">前面要先完成什么</div>
                        <div style="font-size: 12px; color: var(--text-secondary); line-height: 1.8;">${escapeHtml(dependencyText)}</div>
                        <div style="margin-top: 10px; font-size: 12px; color: var(--text-secondary);">如果还没到你想看的那一步，通常是前置任务还没完成。</div>
                    </div>
                    <div style="padding: 14px; border-radius: 12px; border: 1px solid var(--border-color); background: rgba(255,255,255,0.03);">
                        <div style="font-size: 13px; font-weight: 600; color: var(--text-primary); margin-bottom: 8px;">系统原本打算交给谁</div>
                        <div style="font-size: 12px; color: var(--text-secondary); line-height: 1.8;">${escapeHtml(candidateText)}</div>
                    </div>
                    <div style="padding: 14px; border-radius: 12px; border: 1px solid var(--border-color); background: rgba(255,255,255,0.03);">
                        <div style="font-size: 13px; font-weight: 600; color: var(--text-primary); margin-bottom: 8px;">这一步刚产出了什么</div>
                        <div style="font-size: 12px; color: var(--text-secondary); line-height: 1.8; word-break: break-all;">${escapeHtml(resultText)}</div>
                    </div>
                    <div style="padding: 14px; border-radius: 12px; border: 1px solid var(--border-color); background: rgba(255,255,255,0.03);">
                        <div style="font-size: 13px; font-weight: 600; color: var(--text-primary); margin-bottom: 8px;">运行细节</div>
                        <pre style="margin: 0; white-space: pre-wrap; word-break: break-word; font-size: 12px; color: var(--text-secondary);">${escapeHtml(JSON.stringify(metadata, null, 2) || '{}')}</pre>
                    </div>
                </div>
            </div>
        </div>
    `;

    const close = () => {
        modal.classList.add('hidden');
        modal.innerHTML = '';
    };
    modal.querySelector('#collab-task-detail-close')?.addEventListener('click', close);
    modal.firstElementChild?.addEventListener('click', (event) => {
        if (event.target === event.currentTarget) {
            close();
        }
    });
}

function renderCollabTaskPoolWorkspace(taskPool = window.store?.currentTaskPool, collabExecutionTrace = window.store?.collabExecutionTrace, projectReadyExecution = window.store?.projectReadyExecution) {
    const workspace = document.getElementById('main-view');
    if (!workspace) return null;

    const normalizedPool = normalizeCollabRuntimeTaskPool(taskPool);
    const normalizedTrace = normalizeCollabExecutionTrace(collabExecutionTrace);
    const normalizedProjectReady = normalizeProjectReadyExecution(projectReadyExecution);
    const currentFilters = getCollabTraceFilters();
    const filterOptions = buildCollabTraceFilterOptions(normalizedTrace.events);
    const filteredEvents = filterCollabExecutionEvents(normalizedTrace.events, currentFilters);
    const traceStats = buildCollabTraceStats(filteredEvents);
    const latestMatchedEvent = filteredEvents[filteredEvents.length - 1] || null;
    const nextReadyTasks = getCollabNextReadyTasks(normalizedPool.tasks);
    const recentOutputs = buildCollabAgentOutputSummaries(normalizedPool.tasks);
    const nextStepSuggestion = getCollabNextStepSuggestion(normalizedProjectReady, nextReadyTasks);
    const statusEntries = Object.entries(normalizedPool.statusCount || {});
    const quickFilters = buildCollabTraceQuickFilters(normalizedTrace.events);
    const namedFilters = getCollabTraceNamedFilters();

    if (typeof updateBreadcrumbs === 'function') {
        updateBreadcrumbs(['多Agent创作', '协作状态流']);
    }

    const taskCardsHtml = normalizedPool.tasks.length
        ? normalizedPool.tasks.slice(0, 12).map((task) => {
            const statusMeta = getCollabTaskStatusMeta(task.status);
            const taskId = String(task.task_id || task.id || '').trim();
            const taskTitle = String(task.title || task.task_type || '未命名任务').trim();
            const taskType = String(task.task_type || '未分类').trim();
            const assignedAgent = String(task.assigned_agent || '').trim();
            const resultRef = String(task.result_ref || '').trim();
            return `
                <div class="collab-task-card" data-task-id="${escapeHtml(taskId)}"
                    style="padding: 14px; border-radius: 12px; border: 1px solid var(--border-color); background: rgba(255,255,255,0.03);">
                    <div style="display: flex; align-items: center; justify-content: space-between; gap: 10px; margin-bottom: 8px;">
                        <div style="font-size: 14px; font-weight: 600; color: var(--text-primary); min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">
                            ${escapeHtml(taskTitle)}
                        </div>
                        <span style="padding: 4px 8px; border-radius: 999px; background: ${statusMeta.bg}; color: ${statusMeta.color}; font-size: 11px; font-weight: 600; white-space: nowrap;">
                            ${escapeHtml(statusMeta.label)}
                        </span>
                    </div>
                    <div style="font-size: 12px; color: var(--text-secondary); line-height: 1.7;">
                        <div>类型：${escapeHtml(taskType)}</div>
                        <div>执行智能体：${escapeHtml(assignedAgent || '待认领')}</div>
                    </div>
                    <div style="display: flex; flex-wrap: wrap; gap: 8px; margin-top: 12px;">
                        <button type="button" class="collab-task-detail-btn" data-task-id="${escapeHtml(taskId)}"
                            style="padding: 6px 10px; border-radius: 8px; border: 1px solid var(--border-color); background: rgba(255,255,255,0.05); color: var(--text-primary); cursor: pointer; font-size: 12px; font-weight: 600;">
                            任务详情
                        </button>
                        ${resultRef ? `
                            <button type="button" class="collab-task-result-preview-btn" data-result-path="${escapeHtml(resultRef)}"
                                style="padding: 6px 10px; border-radius: 8px; border: 1px solid rgba(99, 102, 241, 0.35); background: rgba(99, 102, 241, 0.16); color: #c7d2fe; cursor: pointer; font-size: 12px; font-weight: 600;">
                                预览产物
                            </button>
                        ` : ''}
                    </div>
                </div>
            `;
        }).join('')
        : `
            <div style="padding: 18px; border: 1px dashed var(--border-color); border-radius: 12px; color: var(--text-secondary); font-size: 13px;">
                当前任务池为空，等待合同确认或任务初始化。
            </div>
        `;

    const nextReadyHtml = nextReadyTasks.length
        ? nextReadyTasks.slice(0, 8).map((task) => `
            <div style="padding: 10px 12px; border-radius: 10px; background: rgba(255,255,255,0.04); border: 1px solid var(--border-color); font-size: 12px; color: var(--text-secondary);">
                <div style="color: var(--text-primary); font-weight: 600; margin-bottom: 4px;">${escapeHtml(String(task.title || task.task_type || '未命名任务').trim())}</div>
                <div>建议交给：${escapeHtml(Array.isArray(task.candidate_agents) && task.candidate_agents.length ? task.candidate_agents.join('、') : '待分配')}</div>
            </div>
        `).join('')
        : `
            <div style="padding: 14px; border-radius: 10px; border: 1px dashed var(--border-color); color: var(--text-secondary); font-size: 12px;">
                当前没有可以立刻接着做的任务。
            </div>
        `;

    const recentOutputsHtml = recentOutputs.length
        ? recentOutputs.map((item) => `
            <div style="padding: 12px; border-radius: 12px; border: 1px solid var(--border-color); background: rgba(255,255,255,0.04);">
                <div style="font-size: 13px; font-weight: 700; color: var(--text-primary); margin-bottom: 6px;">${escapeHtml(getAgentDisplayName(item.agent) || item.agent)}</div>
                <div style="font-size: 12px; color: var(--text-secondary); line-height: 1.8;">
                    <div>刚完成：${escapeHtml(item.title)}</div>
                    <div>产物类型：${escapeHtml(item.resultKind || getProjectReadyTaskTypeLabel(item.taskType) || '未标记')}</div>
                    <div>产物位置：${escapeHtml(item.resultRef || '暂无')}</div>
                </div>
            </div>
        `).join('')
        : '<div style="padding: 14px; border-radius: 10px; border: 1px dashed var(--border-color); color: var(--text-secondary); font-size: 12px;">还没有可展示的最近产出。</div>';

    const stageStatsHtml = traceStats.stageStats.length
        ? traceStats.stageStats.slice(0, 6).map((item) => `
            <span style="display: inline-flex; align-items: center; gap: 6px; padding: 6px 10px; border-radius: 999px; background: rgba(99, 102, 241, 0.10); color: #c7d2fe; font-size: 12px;">
                <strong>${escapeHtml(item.label)}</strong>
                <span>${item.count}</span>
            </span>
        `).join('')
        : '<span style="font-size: 12px; color: var(--text-secondary);">暂无阶段统计</span>';

    const typeStatsHtml = traceStats.typeStats.length
        ? traceStats.typeStats.slice(0, 6).map((item) => `
            <span style="display: inline-flex; align-items: center; gap: 6px; padding: 6px 10px; border-radius: 999px; background: rgba(34, 197, 94, 0.10); color: #bbf7d0; font-size: 12px;">
                <strong>${escapeHtml(item.label)}</strong>
                <span>${item.count}</span>
            </span>
        `).join('')
        : '<span style="font-size: 12px; color: var(--text-secondary);">暂无事件统计</span>';
    const latestMatchedHtml = latestMatchedEvent
        ? (() => {
            const stageMeta = getCollabTraceStageMeta(latestMatchedEvent);
            const typeLabel = getCollabTraceEventTypeLabel(String(latestMatchedEvent.type || latestMatchedEvent.event || '').trim());
            const headline = String(latestMatchedEvent.title || latestMatchedEvent.task_type || typeLabel || '未命名事件').trim();
            return `
                <div id="collab-execution-latest-match" style="padding: 12px; border-radius: 12px; background: rgba(99, 102, 241, 0.10); border: 1px solid rgba(99, 102, 241, 0.24); color: var(--text-secondary); font-size: 12px;">
                    <div style="font-size: 12px; color: #c7d2fe; margin-bottom: 6px;">最近匹配</div>
                    <div style="font-size: 14px; color: var(--text-primary); font-weight: 600;">${escapeHtml(headline)}</div>
                    <div style="margin-top: 4px;">阶段：${escapeHtml(stageMeta.label)} · 事件：${escapeHtml(typeLabel)}</div>
                </div>
            `;
        })()
        : `
            <div id="collab-execution-latest-match" style="padding: 12px; border-radius: 12px; background: rgba(255,255,255,0.04); border: 1px dashed var(--border-color); color: var(--text-secondary); font-size: 12px;">
                暂无最近匹配事件
            </div>
        `;
    const timelineStatsHtml = `
        <div id="collab-execution-timeline-stats" style="display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px;">
            <div style="padding: 12px; border-radius: 12px; background: rgba(255,255,255,0.04); border: 1px solid var(--border-color); color: var(--text-secondary); font-size: 12px;">
                <div>原始事件数：${normalizedTrace.events.length}</div>
                <div style="margin-top: 4px;">当前匹配数：${filteredEvents.length}</div>
            </div>
            <div style="padding: 12px; border-radius: 12px; background: rgba(255,255,255,0.04); border: 1px solid var(--border-color); color: var(--text-secondary); font-size: 12px; line-height: 1.8;">
                <div>阶段统计：${traceStats.stageStats.length ? traceStats.stageStats.map((item) => `${item.label} ${item.count}`).join(' / ') : '暂无阶段统计'}</div>
                <div>事件统计：${traceStats.typeStats.length ? traceStats.typeStats.map((item) => `${item.label} ${item.count}`).join(' / ') : '暂无事件统计'}</div>
            </div>
        </div>
    `;

    workspace.innerHTML = `
        <div style="padding: 24px; max-width: 1200px; margin: 0 auto; display: flex; flex-direction: column; gap: 20px;">
            <div style="display: flex; align-items: center; justify-content: space-between; gap: 16px; flex-wrap: wrap;">
                <div>
                    <h2 style="margin: 0; color: var(--text-primary); font-size: 22px; display: flex; align-items: center; gap: 10px;">
                        <i class="ri-flow-chart"></i>
                        创作进度
                    </h2>
                    <div style="margin-top: 8px; color: var(--text-secondary); font-size: 13px;">
                        这里用大白话告诉你：现在写到哪、谁刚做完、卡在哪、下一步最适合做什么。
                    </div>
                </div>
                <button type="button" id="collab-status-refresh-btn"
                    style="padding: 10px 14px; border-radius: 8px; border: 1px solid var(--border-color); background: rgba(255,255,255,0.08); color: var(--text-primary); cursor: pointer;">
                    <i class="ri-refresh-line"></i> 刷新状态
                </button>
            </div>

            <div style="display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 14px;">
                <div style="padding: 16px; border-radius: 14px; background: rgba(99, 102, 241, 0.10); border: 1px solid rgba(99, 102, 241, 0.24);">
                    <div style="font-size: 12px; color: #c7d2fe; margin-bottom: 6px;">任务池总数</div>
                    <div style="font-size: 28px; font-weight: 700; color: var(--text-primary);">${normalizedPool.tasks.length}</div>
                </div>
                <div style="padding: 16px; border-radius: 14px; background: rgba(34, 197, 94, 0.10); border: 1px solid rgba(34, 197, 94, 0.24);">
                    <div style="font-size: 12px; color: #bbf7d0; margin-bottom: 6px;">执行事件数</div>
                    <div style="font-size: 28px; font-weight: 700; color: var(--text-primary);">${normalizedTrace.events.length}</div>
                </div>
                <div style="padding: 16px; border-radius: 14px; background: rgba(245, 158, 11, 0.10); border: 1px solid rgba(245, 158, 11, 0.24);">
                    <div style="font-size: 12px; color: #fde68a; margin-bottom: 6px;">批次执行任务</div>
                    <div style="font-size: 28px; font-weight: 700; color: var(--text-primary);">${normalizedProjectReady.executedTaskCount}</div>
                </div>
                <div style="padding: 16px; border-radius: 14px; background: rgba(244, 114, 182, 0.10); border: 1px solid rgba(244, 114, 182, 0.24);">
                    <div style="font-size: 12px; color: #fbcfe8; margin-bottom: 6px;">当前轨迹状态</div>
                    <div style="font-size: 20px; font-weight: 700; color: var(--text-primary);">${escapeHtml(normalizedTrace.status || 'idle')}</div>
                </div>
            </div>

            <div style="padding: 18px; border-radius: 14px; border: 1px solid var(--border-color); background: rgba(255,255,255,0.03);">
                <div style="display: flex; align-items: center; justify-content: space-between; gap: 12px; margin-bottom: 12px; flex-wrap: wrap;">
                    <div style="font-size: 15px; color: var(--text-primary); font-weight: 600;">运行态摘要</div>
                    <div style="display: flex; flex-wrap: wrap; gap: 8px;">
                        ${statusEntries.length ? statusEntries.map(([status, count]) => {
                            const statusMeta = getCollabTaskStatusMeta(status);
                            return `<span style="padding: 6px 10px; border-radius: 999px; background: ${statusMeta.bg}; color: ${statusMeta.color}; font-size: 12px; font-weight: 600;">${escapeHtml(statusMeta.label)} · ${count}</span>`;
                        }).join('') : '<span style="font-size: 12px; color: var(--text-secondary);">暂无状态数据</span>'}
                    </div>
                </div>
                <div style="display: grid; grid-template-columns: 1.2fr 0.8fr; gap: 14px;">
                    <div>
                        <div style="font-size: 13px; color: var(--text-secondary); margin-bottom: 10px;">正式任务池</div>
                        <div style="display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px;">
                            ${taskCardsHtml}
                        </div>
                    </div>
                    <div>
                        <div style="font-size: 13px; color: var(--text-secondary); margin-bottom: 10px;">下一步建议</div>
                        <div style="display: flex; flex-direction: column; gap: 10px;">
                            <div style="padding: 10px 12px; border-radius: 10px; background: rgba(99, 102, 241, 0.10); border: 1px solid rgba(99, 102, 241, 0.24); font-size: 12px; color: var(--text-secondary); line-height: 1.7;">
                                ${escapeHtml(nextStepSuggestion)}
                            </div>
                            ${nextReadyHtml}
                        </div>
                    </div>
                </div>
            </div>

            <div style="padding: 18px; border-radius: 14px; border: 1px solid var(--border-color); background: rgba(255,255,255,0.03);">
                <div style="font-size: 15px; color: var(--text-primary); font-weight: 600; margin-bottom: 12px;">各执行助手最近产出</div>
                <div style="display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 12px;">
                    ${recentOutputsHtml}
                </div>
            </div>

            <div style="padding: 18px; border-radius: 14px; border: 1px solid var(--border-color); background: rgba(255,255,255,0.03);">
                <div style="display: flex; align-items: center; justify-content: space-between; gap: 12px; margin-bottom: 14px; flex-wrap: wrap;">
                    <div style="font-size: 15px; color: var(--text-primary); font-weight: 600;">进度筛选</div>
                    <div style="display: flex; flex-wrap: wrap; gap: 8px;">
                        ${quickFilters.map((preset) => `
                            <button type="button" class="collab-trace-quick-filter-btn" data-stage="${escapeHtml(preset.filters.stage)}" data-type="${escapeHtml(preset.filters.type)}"
                                style="padding: 6px 10px; border-radius: 999px; border: 1px solid var(--border-color); background: rgba(255,255,255,0.05); color: var(--text-secondary); cursor: pointer; font-size: 12px;">
                                ${escapeHtml(preset.label)}
                            </button>
                        `).join('')}
                    </div>
                </div>
                <div style="display: grid; grid-template-columns: 1fr 1fr auto; gap: 12px; margin-bottom: 12px;">
                    <select id="collab-trace-stage-filter" style="padding: 10px 12px; border-radius: 8px; background: rgba(0,0,0,0.25); border: 1px solid var(--border-color); color: var(--text-primary);">
                        <option value="all">全部阶段</option>
                        ${filterOptions.stageOptions.map((item) => `<option value="${escapeHtml(item.value)}" ${currentFilters.stage === item.value ? 'selected' : ''}>${escapeHtml(item.label)}</option>`).join('')}
                    </select>
                    <select id="collab-trace-type-filter" style="padding: 10px 12px; border-radius: 8px; background: rgba(0,0,0,0.25); border: 1px solid var(--border-color); color: var(--text-primary);">
                        <option value="all">全部事件</option>
                        ${filterOptions.typeOptions.map((item) => `<option value="${escapeHtml(item.value)}" ${currentFilters.type === item.value ? 'selected' : ''}>${escapeHtml(item.label)}</option>`).join('')}
                    </select>
                    <button type="button" id="collab-trace-reset-btn"
                        style="padding: 10px 14px; border-radius: 8px; border: 1px solid var(--border-color); background: rgba(255,255,255,0.08); color: var(--text-primary); cursor: pointer;">
                        重置
                    </button>
                </div>
                <div style="margin-bottom: 12px;">
                    ${renderCollabTraceFilterBreadcrumbs(currentFilters, filterOptions)}
                </div>
                <div style="margin-bottom: 12px;">${timelineStatsHtml}</div>
                <div style="margin-bottom: 12px;">${latestMatchedHtml}</div>
                <div style="display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 12px;">${stageStatsHtml}</div>
                <div style="display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 16px;">${typeStatsHtml}</div>
                ${renderCollabExecutionTimeline(normalizedTrace.events, currentFilters)}
            </div>

            <div style="padding: 18px; border-radius: 14px; border: 1px solid var(--border-color); background: rgba(255,255,255,0.03);">
                <div style="font-size: 15px; color: var(--text-primary); font-weight: 600; margin-bottom: 12px;">当前卡在哪</div>
                <div style="display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 12px; font-size: 13px; color: var(--text-secondary);">
                    <div>卡住原因：<strong style="color: var(--text-primary);">${escapeHtml(getProjectReadyStopReasonLabel(normalizedProjectReady.stopReason))}</strong></div>
                    <div>卡在这一步：<strong style="color: var(--text-primary);">${escapeHtml(getProjectReadyTaskTypeLabel(normalizedProjectReady.stoppedOnTaskType))}</strong></div>
                    <div>这一轮已写章节：<strong style="color: var(--text-primary);">${normalizedProjectReady.chapterTasksExecuted}</strong></div>
                    <div>最近更新时间：<strong style="color: var(--text-primary);">${escapeHtml(normalizedProjectReady.updatedAt || '未记录')}</strong></div>
                </div>
            </div>

            <div style="padding: 18px; border-radius: 14px; border: 1px solid var(--border-color); background: rgba(255,255,255,0.03);">
                <div style="display: flex; align-items: center; justify-content: space-between; gap: 12px; margin-bottom: 14px; flex-wrap: wrap;">
                    <div style="font-size: 15px; color: var(--text-primary); font-weight: 600;">命名过滤模板</div>
                    <div style="font-size: 12px; color: var(--text-secondary);">保存当前筛选条件，供后续快速复用。</div>
                </div>
                <div style="display: grid; grid-template-columns: 1fr auto; gap: 12px; margin-bottom: 14px;">
                    <input id="collab-trace-template-name" type="text" placeholder="例如：项目调度模板"
                        style="padding: 10px 12px; border-radius: 8px; background: rgba(0,0,0,0.25); border: 1px solid var(--border-color); color: var(--text-primary);">
                    <button type="button" id="collab-trace-template-save-btn"
                        style="padding: 10px 14px; border-radius: 8px; border: 1px solid rgba(34, 197, 94, 0.35); background: rgba(34, 197, 94, 0.14); color: #bbf7d0; cursor: pointer; font-weight: 600;">
                        保存当前模板
                    </button>
                </div>
                ${renderCollabTraceNamedFilters(namedFilters, filterOptions)}
            </div>
        </div>
    `;

    workspace.querySelectorAll('.collab-task-detail-btn').forEach((item) => {
        item.addEventListener('click', () => {
            const taskId = String(item.dataset.taskId || '').trim();
            const task = normalizedPool.tasks.find((entry) => String(entry.task_id || entry.id || '').trim() === taskId);
            if (task) {
                showCollabTaskDetail(task);
            }
        });
    });

    workspace.querySelectorAll('.collab-task-result-preview-btn').forEach((button) => {
        button.addEventListener('click', async () => {
            const resultPath = String(button.dataset.resultPath || '').trim();
            if (!resultPath || typeof window.previewCollabResultFile !== 'function') {
                return;
            }
            await window.previewCollabResultFile(resultPath);
        });
    });

    workspace.querySelectorAll('.collab-trace-expand-btn').forEach((button) => {
        button.addEventListener('click', () => {
            const expandId = String(button.dataset.traceExpandId || '').trim();
            toggleCollabTraceExpandedEventId(expandId);
            renderCollabTaskPoolWorkspace(taskPool, collabExecutionTrace, projectReadyExecution);
        });
    });

    workspace.querySelectorAll('.collab-trace-quick-filter-btn').forEach((button) => {
        button.addEventListener('click', () => {
            setCollabTraceFilters({
                stage: String(button.dataset.stage || 'all'),
                type: String(button.dataset.type || 'all')
            });
            clearCollabTraceExpandedEventIds();
            renderCollabTaskPoolWorkspace(taskPool, collabExecutionTrace, projectReadyExecution);
        });
    });

    workspace.querySelector('#collab-trace-stage-filter')?.addEventListener('change', (event) => {
        setCollabTraceFilters({ stage: event.target.value, type: getCollabTraceFilters().type });
        clearCollabTraceExpandedEventIds();
        renderCollabTaskPoolWorkspace(taskPool, collabExecutionTrace, projectReadyExecution);
    });

    workspace.querySelector('#collab-trace-type-filter')?.addEventListener('change', (event) => {
        setCollabTraceFilters({ stage: getCollabTraceFilters().stage, type: event.target.value });
        clearCollabTraceExpandedEventIds();
        renderCollabTaskPoolWorkspace(taskPool, collabExecutionTrace, projectReadyExecution);
    });

    workspace.querySelector('#collab-trace-reset-btn')?.addEventListener('click', () => {
        setCollabTraceFilters({ stage: 'all', type: 'all' });
        clearCollabTraceExpandedEventIds();
        renderCollabTaskPoolWorkspace(taskPool, collabExecutionTrace, projectReadyExecution);
    });

    workspace.querySelector('#collab-status-refresh-btn')?.addEventListener('click', async () => {
        if (typeof window.refreshNovelCollabRuntime === 'function') {
            const runtime = await window.refreshNovelCollabRuntime({ force: true });
            renderCollabTaskPoolWorkspace(runtime.taskPool, runtime.collabExecutionTrace, runtime.projectReadyExecution);
            if (typeof window.renderMultiAgentWriteNavPanel === 'function') {
                window.renderMultiAgentWriteNavPanel();
            }
            if (typeof showToast === 'function') {
                showToast('协作状态已刷新', 'success');
            }
        }
    });

    workspace.querySelector('#collab-trace-template-save-btn')?.addEventListener('click', () => {
        const nameInput = workspace.querySelector('#collab-trace-template-name');
        const templateName = String(nameInput?.value || '').trim();
        if (!templateName) {
            if (typeof showToast === 'function') {
                showToast('请输入模板名称', 'warning');
            }
            return;
        }
        saveCollabTraceNamedFilter(templateName, getCollabTraceFilters());
        renderCollabTaskPoolWorkspace(taskPool, collabExecutionTrace, projectReadyExecution);
    });

    workspace.querySelectorAll('.collab-trace-template-apply-btn').forEach((button) => {
        button.addEventListener('click', () => {
            const templateId = String(button.dataset.templateId || '').trim();
            const template = getCollabTraceNamedFilters().find((item) => item.id === templateId);
            if (!template) return;
            setCollabTraceFilters(template.filters);
            clearCollabTraceExpandedEventIds();
            renderCollabTaskPoolWorkspace(taskPool, collabExecutionTrace, projectReadyExecution);
        });
    });

    workspace.querySelectorAll('.collab-trace-template-delete-btn').forEach((button) => {
        button.addEventListener('click', () => {
            deleteCollabTraceNamedFilter(String(button.dataset.templateId || '').trim());
            renderCollabTaskPoolWorkspace(taskPool, collabExecutionTrace, projectReadyExecution);
        });
    });

    workspace.querySelectorAll('.collab-trace-template-rename-btn').forEach((button) => {
        button.addEventListener('click', () => {
            const templateId = String(button.dataset.templateId || '').trim();
            const currentName = String(button.dataset.templateName || '').trim();
            const nextName = typeof window.prompt === 'function'
                ? window.prompt('请输入新的模板名称', currentName)
                : currentName;
            if (!nextName) return;
            const renamed = renameCollabTraceNamedFilter(templateId, nextName);
            if (renamed === null && typeof showToast === 'function') {
                showToast('模板名称已存在', 'warning');
            }
            renderCollabTaskPoolWorkspace(taskPool, collabExecutionTrace, projectReadyExecution);
        });
    });

    workspace.querySelectorAll('.collab-trace-template-move-up-btn').forEach((button) => {
        button.addEventListener('click', () => {
            moveCollabTraceNamedFilter(String(button.dataset.templateId || '').trim(), 'up');
            renderCollabTaskPoolWorkspace(taskPool, collabExecutionTrace, projectReadyExecution);
        });
    });

    workspace.querySelectorAll('.collab-trace-template-move-down-btn').forEach((button) => {
        button.addEventListener('click', () => {
            moveCollabTraceNamedFilter(String(button.dataset.templateId || '').trim(), 'down');
            renderCollabTaskPoolWorkspace(taskPool, collabExecutionTrace, projectReadyExecution);
        });
    });

    return {
        taskPool: normalizedPool,
        collabExecutionTrace: normalizedTrace,
        projectReadyExecution: normalizedProjectReady
    };
}

async function openCollabTaskPoolWorkspace() {
    setMultiAgentWriteActiveView('status');
    if (typeof window.refreshNovelCollabRuntime === 'function') {
        const runtime = await window.refreshNovelCollabRuntime({ force: true });
        renderCollabTaskPoolWorkspace(runtime.taskPool, runtime.collabExecutionTrace, runtime.projectReadyExecution);
        if (typeof window.renderMultiAgentWriteNavPanel === 'function') {
            window.renderMultiAgentWriteNavPanel();
        }
        return;
    }
    renderCollabTaskPoolWorkspace();
}

function openMultiAgentKnowledgeWorkspace() {
    setMultiAgentWriteActiveView('knowledge');
    if (typeof showEmptyWorld === 'function') {
        showEmptyWorld();
    }
    if (typeof window.renderMultiAgentWriteNavPanel === 'function') {
        window.renderMultiAgentWriteNavPanel();
    }
}

function renderMultiAgentWriteNavPanel() {
    const navList = document.getElementById('nav-list-container');
    if (!navList) return;

    navList.innerHTML = '';

    // 标签页切换：章节 / 资料库
    const tabGroup = document.createElement('div');
    tabGroup.className = 'nav-tab-group';
    tabGroup.innerHTML = `
        <button type="button" class="nav-tab-btn active" data-tab="chapters">
            <i class="ri-file-text-line"></i>
            <span>章节</span>
        </button>
        <button type="button" class="nav-tab-btn" data-tab="knowledge">
            <i class="ri-database-2-line"></i>
            <span>资料库</span>
        </button>
    `;
    navList.appendChild(tabGroup);

    // 章节面板容器
    const chaptersPanel = document.createElement('div');
    chaptersPanel.className = 'nav-panel-section';
    chaptersPanel.id = 'nav-chapters-panel';

    // 章节面板内容
    const chaptersContent = document.createElement('div');
    chaptersContent.className = 'nav-panel-section-content';

    // 导入小说按钮
    const importCard = document.createElement('div');
    importCard.className = 'nav-action-card';
    importCard.innerHTML = `
        <i class="ri-upload-cloud-2-line"></i>
        <span>导入小说文件</span>
    `;
    importCard.addEventListener('click', () => {
        if (typeof showCollaborativeImportDialog === 'function') {
            showCollaborativeImportDialog();
        }
    });
    chaptersContent.appendChild(importCard);

    // 章节列表
    const chapters = (window.store && window.store.projectData && window.store.projectData.outline) || [];

    if (chapters.length === 0) {
        const emptyHint = document.createElement('div');
        emptyHint.className = 'nav-empty-hint';
        emptyHint.innerHTML = `
            <p>暂无章节</p>
            <p class="hint-sub">点击上方 + 添加章节</p>
        `;
        chaptersContent.appendChild(emptyHint);
    } else {
        chapters.forEach((ch, index) => {
            const chapterItem = document.createElement('div');
            chapterItem.className = 'nav-chapter-item';
            chapterItem.innerHTML = `
                <i class="ri-file-text-line chapter-icon"></i>
                <span class="chapter-title">${formatChapterDisplay(index + 1, ch.title)}</span>
                <div class="chapter-actions">
                    <button class="edit-btn" title="编辑"><i class="ri-edit-line"></i></button>
                    <button class="delete-btn" title="删除"><i class="ri-delete-bin-line"></i></button>
                </div>
            `;

            chapterItem.querySelector('.edit-btn').addEventListener('click', (e) => {
                e.stopPropagation();
                if (typeof editChapterTitle === 'function') {
                    editChapterTitle(index);
                }
            });

            chapterItem.querySelector('.delete-btn').addEventListener('click', (e) => {
                e.stopPropagation();
                if (typeof deleteChapter === 'function') {
                    deleteChapter(index);
                }
            });

            chapterItem.addEventListener('click', () => {
                setMultiAgentWriteActiveView('chapters');
                document.querySelectorAll('.nav-chapter-item').forEach(el => el.classList.remove('active'));
                chapterItem.classList.add('active');
                if (typeof openChapterEditor === 'function') {
                    openChapterEditor(index);
                }
            });

            chaptersContent.appendChild(chapterItem);
        });
    }

    chaptersPanel.appendChild(chaptersContent);
    navList.appendChild(chaptersPanel);

    // 资料库面板容器
    const knowledgePanel = document.createElement('div');
    knowledgePanel.className = 'nav-panel-section collapsed';
    knowledgePanel.id = 'nav-knowledge-panel';

    // 资料库面板内容
    const knowledgeContent = document.createElement('div');
    knowledgeContent.className = 'nav-panel-section-content';

    // 内置资料库分类
    const builtinCategories = (window.store && window.store.knowledgeCategories) || [];
    builtinCategories.filter(c => c.builtin).forEach(cat => {
        const count = (window.store && window.store.projectData && window.store.projectData[cat.key] && window.store.projectData[cat.key].length) || 0;
        const kbItem = document.createElement('div');
        kbItem.className = 'nav-knowledge-item';
        kbItem.innerHTML = `
            <i class="${cat.icon}"></i>
            <span>${cat.name}</span>
            <span class="kb-count">(${count})</span>
        `;
        kbItem.addEventListener('click', () => {
            document.querySelectorAll('.nav-knowledge-item').forEach(el => el.classList.remove('active'));
            kbItem.classList.add('active');
            if (typeof loadDatabase === 'function') {
                loadDatabase(cat.id);
            }
        });
        knowledgeContent.appendChild(kbItem);
    });

    // 自定义资料库分类
    const customCategories = builtinCategories.filter(c => !c.builtin);
    if (customCategories.length > 0) {
        const customSection = document.createElement('div');
        customSection.style.cssText = 'margin-top: 8px; padding-top: 8px; border-top: 1px solid var(--border-color);';
        customSection.innerHTML = `<span style="font-size: 10px; color: var(--text-secondary); opacity: 0.7; padding: 0 12px;">自定义</span>`;
        customCategories.forEach(cat => {
            const count = (window.store && window.store.projectData && window.store.projectData[cat.key] && window.store.projectData[cat.key].length) || 0;
            const kbItem = document.createElement('div');
            kbItem.className = 'nav-knowledge-item';
            kbItem.innerHTML = `
                <i class="${cat.icon}"></i>
                <span>${cat.name}</span>
                <span class="kb-count">(${count})</span>
            `;
            kbItem.addEventListener('click', () => {
                document.querySelectorAll('.nav-knowledge-item').forEach(el => el.classList.remove('active'));
                kbItem.classList.add('active');
                if (typeof loadDatabase === 'function') {
                    loadDatabase(cat.id);
                }
            });
            customSection.appendChild(kbItem);
        });
        knowledgeContent.appendChild(customSection);
    }

    // 添加新资料库按钮
    const addKbBtn = document.createElement('div');
    addKbBtn.className = 'nav-knowledge-item';
    addKbBtn.style.cssText = 'margin-top: 8px; color: var(--accent-color); border: 1px dashed var(--border-color);';
    addKbBtn.innerHTML = `
        <i class="ri-add-line"></i>
        <span>添加新资料库</span>
    `;
    addKbBtn.addEventListener('click', () => {
        if (typeof showAddKnowledgeCategoryDialog === 'function') {
            showAddKnowledgeCategoryDialog();
        }
    });
    knowledgeContent.appendChild(addKbBtn);

    knowledgePanel.appendChild(knowledgeContent);
    navList.appendChild(knowledgePanel);

    // 标签页切换逻辑
    tabGroup.querySelectorAll('.nav-tab-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            const tab = btn.dataset.tab;
            tabGroup.querySelectorAll('.nav-tab-btn').forEach(b => b.classList.remove('active'));
            btn.classList.add('active');

            if (tab === 'chapters') {
                chaptersPanel.classList.remove('collapsed');
                knowledgePanel.classList.add('collapsed');
            } else {
                chaptersPanel.classList.add('collapsed');
                knowledgePanel.classList.remove('collapsed');
            }
        });
    });
}

// ===== 加载无限续写章节列表 =====
async function loadInfiniteWriteChapterList() {
    const container = document.getElementById('infinite-write-chapter-list');
    if (!container) return;
    
    try {
        loadInfiniteWriteDataForCurrentProject();
        
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
                    ${formatChapterDisplay(ch.chapter_number, ch.title)}
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

    if (typeof window.renderKnowledgeNavPanel === 'function') {
        window.renderKnowledgeNavPanel({ append: true, showSectionTitle: true });
    }
}

// ===== 无限续写界面 =====
async function renderInfiniteWriteInterface() {
    loadInfiniteWriteDataForCurrentProject();
    setInfiniteWriteActiveView('panel');

    if (typeof updateBreadcrumbs === 'function') {
        updateBreadcrumbs(['仪表盘', '无限续写']);
    }
    
    const workspace = document.getElementById('main-view');
    if (!workspace) return;
    
    // 先加载全局API配置
    await loadGlobalApiConfigForInfiniteWrite();
    await loadInfiniteWriteContinuationContext();

    const resolvedConfigId = resolveInfiniteWriteApiConfigId(
        infiniteWriteState.selectedApiConfigId || infiniteWriteState.activeConfigId
    );
    if (resolvedConfigId !== infiniteWriteState.selectedApiConfigId) {
        infiniteWriteState.selectedApiConfigId = resolvedConfigId;
    }
    
    // 获取保存的模型或使用全局配置的模型
    let savedModel = infiniteWriteState.selectedModel || '';
    if (!savedModel && infiniteWriteState.globalApiConfig) {
        savedModel = infiniteWriteState.globalApiConfig.model || '';
    }
    
    // 检查全局配置状态
    const globalConfigured = infiniteWriteState.globalApiConfig && infiniteWriteState.globalApiConfig.is_configured;
    const globalModel = infiniteWriteState.globalApiConfig?.model || '';
    
    workspace.innerHTML = `
        <div style="position: relative; min-height: 100%; padding: 30px 20px 90px;">
            <button id="iw-toggle-panel-fab" class="icon-btn" style="position: absolute; right: 24px; bottom: 24px; width: 52px; height: 52px; border-radius: 999px; display: flex; align-items: center; justify-content: center; box-shadow: 0 16px 32px rgba(0,0,0,0.35); background: rgba(139, 92, 246, 0.18) !important; border: 1px solid rgba(139, 92, 246, 0.35) !important; color: #c4b5fd;" title="${infiniteWriteState.mainPanelCollapsed ? '展开创作面板' : '折叠创作面板'}">
                <i class="ri-layout-right-2-line" style="font-size: 20px;"></i>
            </button>
            <div style="max-width: 900px; margin: 0 auto;">
            <!-- 标题 -->
            <div style="text-align: center; margin-bottom: 30px;">
                <h1 style="font-size: 28px; color: var(--text-primary); margin-bottom: 10px; display: flex; align-items: center; justify-content: center; gap: 12px;">
                    <i class="ri-infinity-line" style="color: #8b5cf6;"></i>
                    无限续写
                </h1>
                <p style="color: var(--text-secondary); font-size: 14px;">独立创作模式，拥有专属章节列表和统计数据</p>
            </div>
            
            <!-- 主面板内容区域 -->
            <div id="iw-main-panel-content" style="${infiniteWriteState.mainPanelCollapsed ? 'display: none;' : ''}">
            
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
                                const isSelected = cfg.id === resolvedConfigId;
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
                                ${renderInfiniteWriteModelOptions(resolvedConfigId, savedModel)}
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

            ${renderInfiniteWriteCharacterAnchors()}
            
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
                    <button id="iw-memory-preview-toggle" style="padding: 14px 20px; background: rgba(96, 165, 250, 0.16); border: 1px solid rgba(96, 165, 250, 0.38); color: #93c5fd; border-radius: 8px; cursor: pointer; font-weight: 500;">
                        ${infiniteWriteState.showMemoryPreview ? '收起系统记忆' : '先看系统记忆'}
                    </button>
                    <button id="iw-import-btn-inline" style="padding: 14px 20px; background: rgba(34, 197, 94, 0.18); border: 1px solid rgba(34, 197, 94, 0.4); color: #22c55e; border-radius: 8px; cursor: pointer; font-weight: 500;">
                        <i class="ri-upload-cloud-2-line"></i> 导入小说
                    </button>
                    <button id="iw-export-txt" title="下载为 TXT 文件" style="padding: 14px 20px; background: rgba(59, 130, 246, 0.16); border: 1px solid rgba(59, 130, 246, 0.38); color: #93c5fd; border-radius: 8px; cursor: pointer; font-weight: 500;">
                        <i class="ri-file-text-line"></i> 下载 TXT
                    </button>
                    <button id="iw-export-md" title="下载为 Markdown 文件" style="padding: 14px 20px; background: rgba(14, 165, 233, 0.16); border: 1px solid rgba(14, 165, 233, 0.38); color: #7dd3fc; border-radius: 6px; cursor: pointer; font-weight: 500;">
                        <i class="ri-markdown-line"></i> 下载 MD
                    </button>
                    <button id="iw-export-docx" title="下载为 DOCX 文件" style="padding: 14px 20px; background: rgba(99, 102, 241, 0.16); border: 1px solid rgba(99, 102, 241, 0.38); color: #c7d2fe; border-radius: 8px; cursor: pointer; font-weight: 500;">
                        <i class="ri-file-word-line"></i> 下载 DOCX
                    </button>
                    <button id="iw-finish-btn" title="将当前章节迁移到协作项目" style="padding: 14px 20px; background: linear-gradient(135deg, #8b5cf6, #6366f1); border: none; color: white; border-radius: 8px; cursor: pointer; font-weight: 500;">
                        <i class="ri-flag-line"></i> 迁移到协作
                    </button>
                    <button id="iw-reset-btn" style="padding: 14px 20px; background: rgba(239, 68, 68, 0.2); border: 1px solid rgba(239, 68, 68, 0.4); color: #ef4444; border-radius: 8px; cursor: pointer; font-weight: 500;">
                        <i class="ri-refresh-line"></i> 重置
                    </button>
                </div>
                <div id="iw-memory-preview-panel" style="${infiniteWriteState.showMemoryPreview ? '' : 'display: none;'} margin-top: 16px;">
                    ${renderInfiniteWriteCharacterAnchors() || '<div style="padding: 14px; color: var(--text-secondary); font-size: 13px; border: 1px dashed var(--border-color); border-radius: 8px;">当前还没有可展示的系统记忆。</div>'}
                </div>
            </div>
            
            <!-- 待确认总结区域 -->
            <div id="iw-pending-summaries" style="display: none; background: rgba(100, 180, 255, 0.1); border: 1px solid rgba(100, 180, 255, 0.3); border-radius: 12px; padding: 20px; margin-bottom: 24px;">
                <h3 style="margin-bottom: 12px; font-size: 15px; color: #7dd3fc; display: flex; align-items: center; gap: 8px;">
                    <i class="ri-file-list-3-line"></i>
                    剧情总结待确认
                </h3>
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
                    <li><strong>独立数据</strong>：与多Agent创作模式完全分离，有专属章节列表和统计</li>
                    <li><strong>模型自选</strong>：可以选择不同的模型进行创作</li>
                    <li><strong>自动总结</strong>：每${infiniteWriteState.summaryInterval}章自动生成剧情总结</li>
                    <li><strong>自动向量化</strong>：配置向量模型后，保存章节时自动存入知识库</li>
                    <li><strong>剧情追踪</strong>：自动提取剧情约束，防止逻辑矛盾（如角色复活）</li>
                    <li><strong>热点灵感</strong>：获取实时热点，激发创作灵感</li>
                    <li><strong>文件下载</strong>：可直接下载为 TXT、MD、DOCX 文件</li>
                    <li><strong>协作迁移</strong>：可将当前章节迁移到协作项目继续编辑</li>
                </ul>
            </div>
            
            </div><!-- 主面板内容区域结束 -->
            <div id="iw-main-panel-collapsed-hint" style="${infiniteWriteState.mainPanelCollapsed ? '' : 'display: none;'} max-width: 900px; margin: 0 auto; padding: 40px 32px; border: 1px dashed rgba(139, 92, 246, 0.35); border-radius: 16px; background: rgba(255,255,255,0.03); text-align: center;">
                <div style="font-size: 18px; color: var(--text-primary); margin-bottom: 8px;">创作面板已折叠</div>
                <div style="font-size: 13px; color: var(--text-secondary);">左侧章节仍可直接编辑，点击右下角悬浮按钮可重新展开配置与续写控制。</div>
            </div>
            </div>
        </div>
    `;
    
    // 绑定主面板折叠按钮事件
    const toggleMainPanelBtn = document.getElementById('iw-toggle-panel-fab');
    if (toggleMainPanelBtn) {
        toggleMainPanelBtn.addEventListener('click', () => {
            infiniteWriteState.mainPanelCollapsed = !infiniteWriteState.mainPanelCollapsed;
            const mainPanelContent = document.getElementById('iw-main-panel-content');
            const collapsedHint = document.getElementById('iw-main-panel-collapsed-hint');
            if (mainPanelContent) {
                mainPanelContent.style.display = infiniteWriteState.mainPanelCollapsed ? 'none' : '';
            }
            if (collapsedHint) {
                collapsedHint.style.display = infiniteWriteState.mainPanelCollapsed ? '' : 'none';
            }
            toggleMainPanelBtn.title = infiniteWriteState.mainPanelCollapsed ? '展开创作面板' : '折叠创作面板';
            saveInfiniteWriteData();
        });
    }
    
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
                saveTrendsVisibility(e.target.checked);
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
        // 加载所有API配置，并兼容回读旧版全局配置接口中的模型字段
        const [configsData, globalData] = await Promise.all([
            apiCall('/api/api-configs', 'GET'),
            apiCall('/api/global-config', 'GET').catch(() => null)
        ]);
        infiniteWriteState.apiConfigs = configsData.configs || [];
        infiniteWriteState.activeConfigId = configsData.active_config_id || '';
        
        // 获取当前激活的配置
        const activeConfig = infiniteWriteState.apiConfigs.find(c => c.id === infiniteWriteState.activeConfigId);
        const resolvedGlobalModel = configsData.active_model || globalData?.model || (activeConfig?.models?.[0]) || '';
        
        // 构建兼容的全局配置对象
        infiniteWriteState.globalApiConfig = {
            is_configured: Boolean(globalData?.is_configured || (infiniteWriteState.apiConfigs.length > 0 && activeConfig)),
            model: resolvedGlobalModel,
            api_base: activeConfig?.api_base || globalData?.api_base || ''
        };
        
        // 如果没有选中的API配置，使用激活的配置
        if (!infiniteWriteState.selectedApiConfigId && infiniteWriteState.activeConfigId) {
            infiniteWriteState.selectedApiConfigId = infiniteWriteState.activeConfigId;
        }

        const resolvedConfigId = resolveInfiniteWriteApiConfigId(infiniteWriteState.selectedApiConfigId);
        if (resolvedConfigId !== infiniteWriteState.selectedApiConfigId) {
            infiniteWriteState.selectedApiConfigId = resolvedConfigId;
        }
        
        console.log('[InfiniteWrite] API配置已加载', infiniteWriteState.apiConfigs.length, '个配置，当前激活', infiniteWriteState.activeConfigId);
    } catch (e) {
        console.error('[InfiniteWrite] 加载API配置失败:', e);
        infiniteWriteState.globalApiConfig = null;
        infiniteWriteState.apiConfigs = [];
    }
}

// ===== 渲染模型选项 =====
function resolveInfiniteWriteApiConfigId(preferredConfigId = infiniteWriteState.selectedApiConfigId) {
    const targetId = String(preferredConfigId || '').trim();
    if (targetId && infiniteWriteState.apiConfigs.some(config => config.id === targetId)) {
        return targetId;
    }

    const activeId = String(infiniteWriteState.activeConfigId || '').trim();
    if (activeId && infiniteWriteState.apiConfigs.some(config => config.id === activeId)) {
        return activeId;
    }

    return infiniteWriteState.apiConfigs[0]?.id || '';
}

function renderInfiniteWriteModelOptions(configId, selectedModel) {
    const resolvedConfigId = resolveInfiniteWriteApiConfigId(configId);
    const config = infiniteWriteState.apiConfigs.find(c => c.id === resolvedConfigId);
    if (!config || !Array.isArray(config.models) || config.models.length === 0) {
        const globalModel = infiniteWriteState.globalApiConfig?.model || '';
        if (globalModel) {
            return `<option value="${escapeHtml(globalModel)}" ${globalModel === selectedModel ? 'selected' : ''}>${escapeHtml(globalModel)}（全局模型）</option>`;
        }
        return '<option value="">-- 当前配置未添加模型，且全局模型也未设置 --</option>';
    }
    return config.models.map(model => `
        <option value="${escapeHtml(model)}" ${model === selectedModel ? 'selected' : ''}>${escapeHtml(model)}</option>
    `).join('');
}

// ===== 获取当前选择的API配置ID =====
function getSelectedApiConfigIdForInfiniteWrite() {
    const select = document.getElementById('iw-api-config-select');
    if (select && select.value) {
        return select.value;
    }
    
    if (infiniteWriteState.selectedApiConfigId) {
        return resolveInfiniteWriteApiConfigId(infiniteWriteState.selectedApiConfigId);
    }
    
    return resolveInfiniteWriteApiConfigId(infiniteWriteState.activeConfigId);
}

// ===== 绑定事件 =====
function bindInfiniteWriteEvents() {
    // API配置选择
    const apiConfigSelect = document.getElementById('iw-api-config-select');
    if (apiConfigSelect) {
        // 【修复】初始化时，如果没有选中的API配置，使用当前下拉框的值
        const resolvedConfigId = resolveInfiniteWriteApiConfigId(apiConfigSelect.value || infiniteWriteState.selectedApiConfigId);
        if (resolvedConfigId && infiniteWriteState.selectedApiConfigId !== resolvedConfigId) {
            infiniteWriteState.selectedApiConfigId = resolvedConfigId;
            apiConfigSelect.value = resolvedConfigId;
            console.log('[InfiniteWrite] 初始化API配置ID:', apiConfigSelect.value);
        }
        
        apiConfigSelect.addEventListener('change', (e) => {
            const configId = e.target.value;
            infiniteWriteState.selectedApiConfigId = configId;
            
            // 更新模型列表
            const modelSelect = document.getElementById('iw-model-input');
            if (modelSelect) {
                modelSelect.innerHTML = renderInfiniteWriteModelOptions(configId, '');
                // 自动回退到当前下拉框可用的首个模型，包括全局模型回退项
                infiniteWriteState.selectedModel = modelSelect.value || '';
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

    const memoryPreviewBtn = document.getElementById('iw-memory-preview-toggle');
    if (memoryPreviewBtn) {
        memoryPreviewBtn.addEventListener('click', () => toggleInfiniteWriteMemoryPreview());
    }

    const exportTxtBtn = document.getElementById('iw-export-txt');
    if (exportTxtBtn) {
        exportTxtBtn.addEventListener('click', () => exportInfiniteWriteFile('txt'));
    }

    const exportMdBtn = document.getElementById('iw-export-md');
    if (exportMdBtn) {
        exportMdBtn.addEventListener('click', () => exportInfiniteWriteFile('md'));
    }

    const exportDocxBtn = document.getElementById('iw-export-docx');
    if (exportDocxBtn) {
        exportDocxBtn.addEventListener('click', () => exportInfiniteWriteFile('docx'));
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
                    storyContext += `${formatChapterDisplay(lastChapter.chapter_number, lastChapter.title)}\n`;
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
                `${formatChapterDisplay(ch.chapter_number, ch.title)}\n${ch.content || ''}`
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
    const exists = infiniteWriteState.pendingSummaries.some(
        (item) => item.timestamp === summary.timestamp
    );
    if (!exists) {
        infiniteWriteState.pendingSummaries.push(summary);
    }
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
        saveInfiniteWriteData();
        
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
    clearInfiniteWriteDataForProject();
    setInfiniteWriteActiveView('panel');
    
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
        setInfiniteWriteActiveView('chapter', chapter.chapter_number);
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

        if (typeof window.showInfiniteWriteChapterEditor === 'function') {
            window.showInfiniteWriteChapterEditor(chapter);
        }
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
            projectId: store?.currentProjectId,
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
        config: infiniteWriteState.config,
        mainPanelCollapsed: infiniteWriteState.mainPanelCollapsed,
        activeView: infiniteWriteState.activeView,
        activeChapterNumber: infiniteWriteState.activeChapterNumber
    };
    
    const payload = JSON.stringify(data);
    console.log('[InfiniteWrite] save: chapters =', data.chapters?.length || 0, 'totalWords =', data.totalWords || 0, 'payloadBytes =', payload.length);
    localStorage.setItem(getInfiniteWriteStorageKey(), payload);
    localStorage.setItem(getInfiniteWriteModelStorageKey(), infiniteWriteState.selectedModel);
}

function getInfiniteWriteExportTitle() {
    return getDefaultProjectName().replace(/\s+/g, ' ').trim() || '无限续写';
}

function getInfiniteWriteExportFilename(format) {
    const baseName = getInfiniteWriteExportTitle().replace(/[<>:"/\\|?*]/g, '_');
    return `${baseName}.${format}`;
}

function buildInfiniteWriteExportPayload() {
    const chapters = Array.isArray(infiniteWriteState.chapters)
        ? [...infiniteWriteState.chapters]
            .filter((chapter) => chapter && Number(chapter.chapter_number) > 0 && (chapter.content || '').trim())
            .sort((a, b) => Number(a.chapter_number || 0) - Number(b.chapter_number || 0))
            .map((chapter) => ({
                chapter_number: Number(chapter.chapter_number || 0),
                title: chapter.title || '',
                content: chapter.content || ''
            }))
        : [];

    return {
        title: getInfiniteWriteExportTitle(),
        chapters
    };
}

async function exportInfiniteWriteFile(format) {
    const payload = buildInfiniteWriteExportPayload();
    if (!payload.chapters.length) {
        showToast('当前没有可导出的章节', 'error');
        return;
    }

    try {
        const response = await fetch(`/api/continuous-write/export?format=${encodeURIComponent(format)}`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(payload)
        });

        if (!response.ok) {
            const result = await response.json().catch(() => ({}));
            throw new Error(result.detail || result.error || '导出失败');
        }

        const blob = await response.blob();
        const url = URL.createObjectURL(blob);
        const anchor = document.createElement('a');
        anchor.href = url;
        anchor.download = getInfiniteWriteExportFilename(format);
        document.body.appendChild(anchor);
        anchor.click();
        document.body.removeChild(anchor);
        URL.revokeObjectURL(url);
        showToast(`已导出 ${format.toUpperCase()} 文件`);
    } catch (e) {
        showToast(e.message || '导出失败', 'error');
    }
}

// ===== 导出函数供全局使用 =====
window.renderMultiAgentWriteNavPanel = renderMultiAgentWriteNavPanel;
window.renderCollabTaskPoolWorkspace = renderCollabTaskPoolWorkspace;
window.openCollabTaskPoolWorkspace = openCollabTaskPoolWorkspace;
window.renderInfiniteWriteNavPanel = renderInfiniteWriteNavPanel;
window.loadInfiniteWriteChapterList = loadInfiniteWriteChapterList;
window.loadInfiniteWriteNavChapterList = loadInfiniteWriteNavChapterList;
window.loadInfiniteWriteDataForCurrentProject = loadInfiniteWriteDataForCurrentProject;
window.renderInfiniteWriteInterface = renderInfiniteWriteInterface;
window.showInfiniteWriteChapterPreview = showInfiniteWriteChapterPreview;
window.showInfiniteWriteChapterPreviewWithConfirm = showInfiniteWriteChapterPreviewWithConfirm;
window.deleteInfiniteWriteChapterFrom = deleteInfiniteWriteChapterFrom;
window.regenerateInfiniteWriteChapter = regenerateInfiniteWriteChapter;
window.setInfiniteWriteActiveView = setInfiniteWriteActiveView;
window.exportInfiniteWriteFile = exportInfiniteWriteFile;

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
                        迁移到协作项目
                    </h2>
                    <p style="margin: 8px 0 0 0; font-size: 13px; color: var(--text-secondary);">
                        将无限续写的章节写入协作项目，文件下载请使用上方的 TXT / MD / DOCX 按钮
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
                            <i class="ri-share-forward-line"></i> 迁移方式
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
                            <input type="checkbox" id="finish-clear-data" style="width: 18px; height: 18px; cursor: pointer;">
                            <div>
                                <div style="font-weight: 500; color: var(--text-primary);">迁移后清空无限续写数据</div>
                                <div style="font-size: 12px; color: var(--text-secondary); margin-top: 4px;">
                                    <i class="ri-information-line"></i> 不勾选则保留无限续写数据，两个模式独立管理
                                </div>
                            </div>
                        </label>
                    </div>
                </div>
                
                <div style="padding: 16px 20px; border-top: 1px solid var(--border-color); display: flex; gap: 12px;">
                    <button id="finish-cancel-btn" style="flex: 1; padding: 12px; background: rgba(255,255,255,0.1); border: 1px solid var(--border-color); color: var(--text-primary); border-radius: 8px; cursor: pointer; font-size: 14px;">
                        取消
                    </button>
                    <button id="finish-confirm-btn" style="flex: 1; padding: 12px; background: linear-gradient(135deg, #8b5cf6, #6366f1); border: none; color: white; border-radius: 8px; cursor: pointer; font-weight: 600; font-size: 14px;">
                        <i class="ri-share-forward-line"></i> 确认迁移
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
    const sourceProjectId = typeof getActiveProjectId === 'function'
        ? (getActiveProjectId() || '')
        : (store.currentProjectId || '');
    
    if (confirmBtn) {
        confirmBtn.disabled = true;
        confirmBtn.innerHTML = '<i class="ri-loader-4-line" style="animation: spin 1s linear infinite;"></i> 保存中...';
    }
    
    try {
        const isNewProject = document.querySelector('input[name="finish-option"]:checked')?.value === 'new';
        const clearData = document.getElementById('finish-clear-data')?.checked ?? false;
        const projectName = document.getElementById('finish-project-name')?.value?.trim() || getDefaultProjectName();
        
        let targetProjectId = typeof getActiveProjectId === 'function'
            ? getActiveProjectId()
            : store.currentProjectId;
        
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
        if (targetProjectId !== store.currentProjectId) {
            await apiCall(`/api/projects/${targetProjectId}/switch`, 'POST');
            if (typeof setActiveProjectId === 'function') {
                setActiveProjectId(targetProjectId);
            } else {
                store.currentProjectId = targetProjectId;
            }
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
            applyInfiniteWriteProjectState(createInfiniteWriteProjectState());
            clearInfiniteWriteDataForProject(sourceProjectId);
        }
        
        // 刷新项目选择器
        updateProjectSelector();
        
        // 关闭弹窗
        modal.classList.add('hidden');
        modal.innerHTML = '';
        
        // 显示成功消息
        showToast(`🎉 已迁移到协作项目！${isNewProject ? `新项目「${projectName}」已创建` : '章节已追加到当前项目'}${clearData ? '，无限续写数据已清空' : '，无限续写数据保留'}`, 'success');
        
        // 刷新界面
        if (isNewProject) {
            // 切换到新项目后刷新
            if (typeof loadCurrentProjectData === 'function') {
                await loadCurrentProjectData();
            }
        }
        
        // 刷新无限续写界面，切换到目标项目后加载该项目自己的独立续写数据
        loadInfiniteWriteDataForCurrentProject();
        renderInfiniteWriteInterface();
        loadInfiniteWriteNavChapterList();
        
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
window.loadInfiniteWriteContinuationContext = loadInfiniteWriteContinuationContext;
window.renderInfiniteWriteCharacterAnchors = renderInfiniteWriteCharacterAnchors;
window.toggleInfiniteWriteMemoryPreview = toggleInfiniteWriteMemoryPreview;
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

