/**
 * 工作流自动保存模块
 * 负责将工作流生成的文件自动保存到对应的前端数据结构中
 */

// 自动保存处理器映射
const AUTO_SAVE_HANDLERS = {
    'worldbuilding': autoSaveWorldbuilding,
    'outline': autoSaveOutline,
    'chapter': autoSaveChapter,
    'characters': autoSaveCharacters,
    'items': autoSaveItems
};

function dedupeWorkflowFiles(files) {
    const normalizedFiles = Array.isArray(files) ? files : [];
    const seen = new Map();
    normalizedFiles.forEach((file) => {
        if (!file || typeof file !== 'object') return;
        const path = String(file.path || '').trim();
        if (!path) return;
        seen.set(path, {
            path,
            label: String(file.label || file.name || '').trim(),
            kind: String(file.kind || 'file').trim(),
            status: String(file.status || 'created').trim()
        });
    });
    return Array.from(seen.values());
}

function upsertKnowledgeItems(target, items) {
    if (!Array.isArray(target) || !Array.isArray(items)) return;
    items.forEach((item) => {
        const name = String(item && item.name || '').trim();
        if (!name) return;
        const existingIndex = target.findIndex((entry) => String(entry && entry.name || '').trim() === name);
        if (existingIndex >= 0) {
            target[existingIndex] = { ...target[existingIndex], ...item };
        } else {
            target.push(item);
        }
    });
}

function parseWorldbuildingContent(content, file) {
    let parsed = null;
    try {
        parsed = JSON.parse(content);
    } catch (e) {
        console.error('[AutoSave] 世界观数据解析失败', file && file.path, e);
        return [];
    }
    const worldData = parsed && typeof parsed === 'object'
        ? (parsed.world && typeof parsed.world === 'object' ? parsed.world : parsed)
        : null;
    if (!worldData || typeof worldData !== 'object') {
        return [];
    }
    return convertWorldDataToLibraryItems(worldData);
}

function mapWorkflowFileKindToProjectDataKey(fileKind) {
    const normalizedKind = String(fileKind || '').trim();
    const mapping = {
        worldbuilding: 'worldbuilding',
        outline: 'outline',
        chapter: 'outline',
        characters: 'characters',
        items: 'items',
        eventlines: 'eventlines',
        outline_settings: 'outline_settings',
        detail_settings: 'detail_settings',
        chapter_settings: 'chapter_settings'
    };
    return mapping[normalizedKind] || '';
}

async function refreshWorkflowTargetedData(workflow) {
    const normalizedWorkflow = workflow && typeof workflow === 'object' ? workflow : {};
    const workflowFiles = dedupeWorkflowFiles([
        ...(Array.isArray(normalizedWorkflow.created_files) ? normalizedWorkflow.created_files : []),
        ...(Array.isArray(normalizedWorkflow.updated_files) ? normalizedWorkflow.updated_files : [])
    ]);
    const refreshKeys = Array.from(new Set(
        workflowFiles
            .map((file) => mapWorkflowFileKindToProjectDataKey(file.kind))
            .filter(Boolean)
    ));

    if (refreshKeys.length === 0) {
        return false;
    }

    let refreshed = false;
    for (const dataKey of refreshKeys) {
        try {
            const serverData = await apiCall(`/api/project-data/${dataKey}`, 'GET');
            store.projectData[dataKey] = Array.isArray(serverData?.data) ? serverData.data : (serverData?.data || []);
            refreshed = true;
        } catch (e) {
            console.warn(`[AutoSave] 定向刷新 ${dataKey} 失败`, e);
        }
    }

    if (refreshed && typeof updateMentionData === 'function') {
        updateMentionData();
    }
    return refreshed;
}

async function reloadProjectDataAndRefreshView(workflow) {
    const targetedReloaded = await refreshWorkflowTargetedData(workflow);
    if (!targetedReloaded && typeof loadCurrentProjectData === 'function') {
        await loadCurrentProjectData();
    }

    const normalizedWorkflow = workflow && typeof workflow === 'object' ? workflow : {};
    const focusModule = String(normalizedWorkflow.focus_module || '').trim();
    const createdKinds = dedupeWorkflowFiles([
        ...(Array.isArray(normalizedWorkflow.created_files) ? normalizedWorkflow.created_files : []),
        ...(Array.isArray(normalizedWorkflow.updated_files) ? normalizedWorkflow.updated_files : [])
    ]).map((file) => String(file.kind || '').trim());

    const hasChapterOrOutline = createdKinds.includes('chapter') || createdKinds.includes('outline');
    const hasWorldbuilding = createdKinds.includes('worldbuilding');

    if (focusModule === 'world' || (!focusModule && hasWorldbuilding)) {
        // 切换到资料库模块并加载世界观分类
        if (typeof switchModule === 'function') {
            switchModule('world');
        }
        const worldCategory = Array.isArray(store?.knowledgeCategories)
            ? store.knowledgeCategories.find((item) => String(item.key || '').trim() === 'worldbuilding')
            : null;
        if (worldCategory && typeof loadDatabase === 'function') {
            window.setTimeout(() => loadDatabase(worldCategory.id), 80);
        }
    } else if (focusModule === 'write' || (!focusModule && hasChapterOrOutline)) {
        // 切换到创作模块并刷新章节导航面板
        if (typeof switchModule === 'function') {
            switchModule('write');
        }
        // 显式刷新左侧章节列表导航面板
        window.setTimeout(() => {
            if (typeof renderNavPanel === 'function') {
                renderNavPanel('write');
            }
        }, 100);
    } else {
        await refreshCurrentModule();
    }

    // 保底：如果当前已在world模块且有世界观文件更新，确保刷新资料库
    if (!focusModule && hasWorldbuilding && store.currentModule === 'world' && typeof loadDatabase === 'function') {
        const worldCategory = Array.isArray(store?.knowledgeCategories)
            ? store.knowledgeCategories.find((item) => String(item.key || '').trim() === 'worldbuilding')
            : null;
        if (worldCategory) {
            window.setTimeout(() => loadDatabase(worldCategory.id), 80);
        }
    }

    // 保底：如果当前已在write模块且有章节/大纲文件更新，确保刷新导航面板
    if (!focusModule && hasChapterOrOutline && store.currentModule === 'write') {
        window.setTimeout(() => {
            if (typeof renderNavPanel === 'function') {
                renderNavPanel('write');
            }
        }, 120);
    }

    if (typeof maybeFocusWorkflowTarget === 'function') {
        maybeFocusWorkflowTarget(normalizedWorkflow);
    }
}

/**
 * 主入口：处理工作流完成事件
 */
async function handleWorkflowAutoSave(workflow) {
    if (!workflow) {
        return;
    }

    const workflowFiles = dedupeWorkflowFiles([
        ...(Array.isArray(workflow.created_files) ? workflow.created_files : []),
        ...(Array.isArray(workflow.updated_files) ? workflow.updated_files : [])
    ]);

    if (workflowFiles.length === 0) {
        return;
    }

    console.log('[AutoSave] 开始处理工作流文件自动保存', workflow);

    const sessionId = getCurrentCopilotSessionId();
    const savedCount = { success: 0, failed: 0, skipped: 0 };

    for (const file of workflowFiles) {
        try {
            const handler = AUTO_SAVE_HANDLERS[file.kind];
            if (handler) {
                const saved = await handler(file, sessionId);
                if (saved) {
                    savedCount.success++;
                } else {
                    savedCount.skipped++;
                }
            } else {
                console.log(`[AutoSave] 未找到处理器: ${file.kind}`);
                savedCount.skipped++;
            }
        } catch (e) {
            console.error(`[AutoSave] 保存失败: ${file.path}`, e);
            savedCount.failed++;
        }
    }

    if (savedCount.success > 0) {
        await reloadProjectDataAndRefreshView(workflow);
        showToast(`已自动同步 ${savedCount.success} 个文件到对应位置`, 'success');
    }

    if (savedCount.failed > 0) {
        showToast(`${savedCount.failed} 个文件同步失败`, 'warning');
    }
}

/**
 * 自动保存世界观
 */
async function autoSaveWorldbuilding(file, sessionId) {
    console.log('[AutoSave] 处理世界观文件', file);

    try {
        const serverData = await apiCall('/api/project-data/worldbuilding', 'GET');
        if (Array.isArray(serverData?.data) && serverData.data.length > 0) {
            store.projectData.worldbuilding = serverData.data;
            if (typeof updateMentionData === 'function') {
                updateMentionData();
            }
            return true;
        }
    } catch (e) {
        console.warn('[AutoSave] 读取服务端世界观失败，回退到文件解析', e);
    }

    const content = await fetchWorkflowFileContent(file.path, sessionId);
    if (!content) return false;

    const worldItems = parseWorldbuildingContent(content, file);
    if (!worldItems.length) {
        console.warn('[AutoSave] 世界观内容无法转为资料库条目', file.path);
        return false;
    }

    if (!store.projectData.worldbuilding) {
        store.projectData.worldbuilding = [];
    }

    upsertKnowledgeItems(store.projectData.worldbuilding, worldItems);

    await apiCall('/api/project-data/worldbuilding', 'POST', {
        data: store.projectData.worldbuilding
    });

    if (typeof updateMentionData === 'function') {
        updateMentionData();
    }

    console.log('[AutoSave] 世界观保存成功', worldItems.length);
    return true;
}

/**
 * 自动保存大纲
 */
async function autoSaveOutline(file, sessionId) {
    console.log('[AutoSave] 处理大纲文件', file);

    try {
        const serverData = await apiCall('/api/project-data/outline', 'GET');
        if (Array.isArray(serverData?.data) && serverData.data.length > 0) {
            store.projectData.outline = serverData.data;
            if (typeof updateMentionData === 'function') {
                updateMentionData();
            }
            return true;
        }
    } catch (e) {
        console.warn('[AutoSave] 读取服务端大纲失败，回退到文件解析', e);
    }

    const content = await fetchWorkflowFileContent(file.path, sessionId);
    if (!content) return false;

    let outlineData;
    try {
        outlineData = JSON.parse(content);
    } catch (e) {
        console.error('[AutoSave] 大纲数据解析失败', e);
        return;
    }

    // 转换为章节列表格式
    const chapters = convertOutlineToChapters(outlineData);

    // 保存到本地store（追加或替换）
    if (!store.projectData.outline) {
        store.projectData.outline = [];
    }

    // 如果是新大纲，替换；如果是补充，追加
    if (store.projectData.outline.length === 0) {
        store.projectData.outline = chapters;
    } else {
        // 追加新章节
        chapters.forEach(chapter => {
            const exists = store.projectData.outline.some(c => c.title === chapter.title);
            if (!exists) {
                store.projectData.outline.push(chapter);
            }
        });
    }

    // 保存到服务器
    await apiCall('/api/project-data/outline', 'POST', {
        data: store.projectData.outline
    });

    // 更新@引用数据
    if (typeof updateMentionData === 'function') {
        updateMentionData();
    }

    console.log('[AutoSave] 大纲保存成功', chapters.length);
    return true;
}

/**
 * 自动保存章节
 */
async function autoSaveChapter(file, sessionId) {
    console.log('[AutoSave] 处理章节文件', file);

    try {
        const serverData = await apiCall('/api/project-data/outline', 'GET');
        if (Array.isArray(serverData?.data) && serverData.data.length > 0) {
            const existingOutline = serverData.data;
            const previewContent = await fetchWorkflowFileContent(file.path, sessionId);
            const chapterInfo = previewContent ? extractChapterInfo(file, previewContent) : null;
            if (!chapterInfo || (existingOutline[chapterInfo.index || 0] && String(existingOutline[chapterInfo.index || 0].content || '').trim())) {
                store.projectData.outline = existingOutline;
                return true;
            }
        }
    } catch (e) {
        console.warn('[AutoSave] 读取服务端章节失败，回退到文件解析', e);
    }

    const content = await fetchWorkflowFileContent(file.path, sessionId);
    if (!content) return false;

    // 从文件名或内容中提取章节信息
    const chapterInfo = extractChapterInfo(file, content);
    if (!chapterInfo) {
        console.error('[AutoSave] 无法提取章节信息');
        return;
    }

    // 查找或创建章节
    if (!store.projectData.outline) {
        store.projectData.outline = [];
    }

    const chapterIndex = chapterInfo.index || store.projectData.outline.length;
    
    if (chapterIndex < store.projectData.outline.length) {
        // 更新现有章节
        store.projectData.outline[chapterIndex].content = content;
        store.projectData.outline[chapterIndex].updated_at = new Date().toISOString();
    } else {
        // 创建新章节
        store.projectData.outline.push({
            title: chapterInfo.title || `第${chapterIndex + 1}章`,
            content: content,
            summary: chapterInfo.summary || '',
            created_at: new Date().toISOString()
        });
    }

    // 保存到服务器
    await apiCall('/api/project-data/outline', 'POST', {
        data: store.projectData.outline
    });

    console.log('[AutoSave] 章节保存成功', chapterInfo.title);
    return true;
}

/**
 * 自动保存角色
 */
async function autoSaveCharacters(file, sessionId) {
    console.log('[AutoSave] 处理角色文件', file);

    try {
        const serverData = await apiCall('/api/project-data/characters', 'GET');
        if (Array.isArray(serverData?.data) && serverData.data.length > 0) {
            store.projectData.characters = serverData.data;
            if (typeof updateMentionData === 'function') {
                updateMentionData();
            }
            return true;
        }
    } catch (e) {
        console.warn('[AutoSave] 读取服务端角色失败，回退到文件解析', e);
    }

    const content = await fetchWorkflowFileContent(file.path, sessionId);
    if (!content) return false;

    let charactersData;
    try {
        charactersData = JSON.parse(content);
    } catch (e) {
        console.error('[AutoSave] 角色数据解析失败', e);
        return;
    }

    // 确保是数组格式
    const characters = Array.isArray(charactersData) ? charactersData : [charactersData];

    // 保存到本地store
    if (!store.projectData.characters) {
        store.projectData.characters = [];
    }

    // 追加新角色（避免重复）
    characters.forEach(char => {
        const exists = store.projectData.characters.some(c => c.name === char.name);
        if (!exists) {
            store.projectData.characters.push({
                id: Date.now().toString() + Math.random(),
                name: char.name || '未命名角色',
                description: char.description || char.personality || '',
                details: JSON.stringify(char, null, 2),
                created_at: new Date().toISOString()
            });
        }
    });

    // 保存到服务器
    await apiCall('/api/project-data/characters', 'POST', {
        data: store.projectData.characters
    });

    // 更新@引用数据
    if (typeof updateMentionData === 'function') {
        updateMentionData();
    }

    console.log('[AutoSave] 角色保存成功', characters.length);
    return true;
}

/**
 * 自动保存道具物品
 */
async function autoSaveItems(file, sessionId) {
    console.log('[AutoSave] 处理道具文件', file);

    try {
        const serverData = await apiCall('/api/project-data/items', 'GET');
        if (Array.isArray(serverData?.data) && serverData.data.length > 0) {
            store.projectData.items = serverData.data;
            return true;
        }
    } catch (e) {
        console.warn('[AutoSave] 读取服务端道具失败，回退到文件解析', e);
    }

    const content = await fetchWorkflowFileContent(file.path, sessionId);
    if (!content) return false;

    let itemsData;
    try {
        itemsData = JSON.parse(content);
    } catch (e) {
        console.error('[AutoSave] 道具数据解析失败', e);
        return;
    }

    const items = Array.isArray(itemsData) ? itemsData : [itemsData];

    if (!store.projectData.items) {
        store.projectData.items = [];
    }

    items.forEach(item => {
        const exists = store.projectData.items.some(i => i.name === item.name);
        if (!exists) {
            store.projectData.items.push({
                id: Date.now().toString() + Math.random(),
                name: item.name || '未命名道具',
                description: item.description || '',
                details: JSON.stringify(item, null, 2),
                created_at: new Date().toISOString()
            });
        }
    });

    await apiCall('/api/project-data/items', 'POST', {
        data: store.projectData.items
    });

    console.log('[AutoSave] 道具保存成功', items.length);
    return true;
}

/**
 * 辅助函数：获取工作流文件内容
 */
async function fetchWorkflowFileContent(filePath, sessionId) {
    try {
        const res = await apiCall(
            `/api/v1/chat/workflow-file-preview?session_id=${encodeURIComponent(sessionId)}&path=${encodeURIComponent(filePath)}`,
            'GET'
        );
        return res && res.content ? res.content : null;
    } catch (e) {
        console.error('[AutoSave] 读取文件失败', filePath, e);
        return null;
    }
}

/**
 * 辅助函数：转换世界观数据为资料库格式
 */
function convertWorldDataToLibraryItems(worldData) {
    const items = [];
    const timestamp = Date.now();

    // 世界名称和基本信息
    if (worldData.world_name) {
        items.push({
            id: `world_${timestamp}`,
            name: worldData.world_name,
            description: `世界类型：${worldData.world_type || '未指定'}`,
            details: JSON.stringify(worldData, null, 2),
            created_at: new Date().toISOString()
        });
    }

    // 力量体系
    if (worldData.power_system) {
        items.push({
            id: `power_${timestamp + 1}`,
            name: '力量体系',
            description: '世界的力量体系设定',
            details: typeof worldData.power_system === 'string'
                ? worldData.power_system
                : JSON.stringify(worldData.power_system, null, 2),
            created_at: new Date().toISOString()
        });
    }

    // 地理环境
    if (worldData.geography) {
        items.push({
            id: `geo_${timestamp + 2}`,
            name: '地理环境',
            description: '世界的地理环境设定',
            details: typeof worldData.geography === 'string'
                ? worldData.geography
                : JSON.stringify(worldData.geography, null, 2),
            created_at: new Date().toISOString()
        });
    }

    // 历史背景
    if (worldData.history) {
        items.push({
            id: `history_${timestamp + 3}`,
            name: '历史背景',
            description: '世界的历史背景设定',
            details: typeof worldData.history === 'string'
                ? worldData.history
                : JSON.stringify(worldData.history, null, 2),
            created_at: new Date().toISOString()
        });
    }

    // 文化习俗
    if (worldData.culture) {
        items.push({
            id: `culture_${timestamp + 4}`,
            name: '文化习俗',
            description: '世界的文化习俗设定',
            details: typeof worldData.culture === 'string'
                ? worldData.culture
                : JSON.stringify(worldData.culture, null, 2),
            created_at: new Date().toISOString()
        });
    }

    // 势力阵营
    if (worldData.factions && Array.isArray(worldData.factions)) {
        worldData.factions.forEach((faction, index) => {
            items.push({
                id: `faction_${timestamp + 5 + index}`,
                name: faction.name || `势力${index + 1}`,
                description: faction.description || '势力阵营',
                details: typeof faction === 'string'
                    ? faction
                    : JSON.stringify(faction, null, 2),
                created_at: new Date().toISOString()
            });
        });
    }

    return items;
}

/**
 * 辅助函数：转换大纲为章节列表
 */
function convertOutlineToChapters(outlineData) {
    const chapters = [];

    // 处理不同的大纲格式
    if (Array.isArray(outlineData)) {
        // 数组格式
        outlineData.forEach((item, index) => {
            chapters.push({
                title: item.title || item.chapter_title || `第${index + 1}章`,
                summary: item.summary || item.content || '',
                content: '',
                created_at: new Date().toISOString()
            });
        });
    } else if (outlineData.chapters && Array.isArray(outlineData.chapters)) {
        // 对象格式with chapters字段
        outlineData.chapters.forEach((item, index) => {
            chapters.push({
                title: item.title || item.chapter_title || `第${index + 1}章`,
                summary: item.summary || item.content || '',
                content: '',
                created_at: new Date().toISOString()
            });
        });
    }

    return chapters;
}

/**
 * 辅助函数：从文件信息中提取章节信息
 */
function extractChapterInfo(file, content) {
    // 从文件名提取章节号
    const match = file.path.match(/第(\d+)章/);
    const chapterNum = match ? parseInt(match[1]) : null;

    // 从内容中提取标题（第一行）
    const lines = content.split('\n');
    const firstLine = lines[0].trim();
    const title = firstLine.startsWith('#') ? firstLine.replace(/^#+\s*/, '') : firstLine;

    return {
        index: chapterNum ? chapterNum - 1 : null,
        title: title || file.label || `第${chapterNum || '?'}章`,
        summary: ''
    };
}

/**
 * 辅助函数：刷新当前模块显示
 * 先从服务端重新加载项目数据，再刷新UI面板
 */
async function refreshCurrentModule() {
    // 先从服务端重新加载项目数据，确保UI渲染的是最新数据
    if (typeof loadCurrentProjectData === 'function') {
        try {
            await loadCurrentProjectData();
        } catch (e) {
            console.warn('[refreshCurrentModule] 加载项目数据失败', e);
        }
    }

    const currentModule = store.currentModule;
    
    if (currentModule === 'world') {
        // 刷新资料库显示
        if (typeof renderKnowledgeNavPanel === 'function') {
            renderKnowledgeNavPanel();
        }
        // 如果当前有选中的世界观分类，也刷新它
        const worldCategory = Array.isArray(store?.knowledgeCategories)
            ? store.knowledgeCategories.find((item) => String(item.key || '').trim() === 'worldbuilding')
            : null;
        if (worldCategory && typeof loadDatabase === 'function') {
            window.setTimeout(() => loadDatabase(worldCategory.id), 80);
        }
    } else if (currentModule === 'write') {
        // 刷新章节列表导航面板
        if (typeof renderNavPanel === 'function') {
            renderNavPanel('write');
        }
    }
}

// 全局暴露函数
window.handleWorkflowAutoSave = handleWorkflowAutoSave;
window.autoSaveWorldbuilding = autoSaveWorldbuilding;
window.autoSaveOutline = autoSaveOutline;
window.autoSaveChapter = autoSaveChapter;
window.autoSaveCharacters = autoSaveCharacters;
window.autoSaveItems = autoSaveItems;

console.log('[app-workflow-auto-save.js] 工作流自动保存模块已加载');
