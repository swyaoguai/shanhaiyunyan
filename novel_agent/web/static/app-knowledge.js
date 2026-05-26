/**
 * 山海·云烟 - 资料库管理模块
 * 包含：资料库分类、知识条目CRUD、设定管理
 */

// ===== 资料库导航面板 =====

function renderKnowledgeNavPanel(options = {}) {
    const appendMode = Boolean(options && options.append);
    const showSectionTitle = Boolean(options && options.showSectionTitle);

    if (!appendMode) {
        ui.navList.innerHTML = '';
    }

    if (showSectionTitle) {
        const separator = document.createElement('div');
        separator.style.cssText = 'height: 1px; background: var(--border-color); margin: 12px 8px;';
        ui.navList.appendChild(separator);

        const title = document.createElement('div');
        title.style.cssText = 'font-size: 11px; color: var(--text-secondary); padding: 8px 12px; opacity: 0.7;';
        title.textContent = '资料库';
        ui.navList.appendChild(title);
    }

    // 内置资料库分类
    const builtinCategories = store.knowledgeCategories.filter(c => c.builtin);

    builtinCategories.forEach(cat => {
        const count = getKnowledgeCategoryCount(cat);
        const div = document.createElement('div');
        div.className = 'list-item';
        div.innerHTML = `
            <i class="${cat.icon}"></i>
            <span>${cat.name}</span>
            <span style="margin-left:auto; font-size:11px; opacity:0.6;">(${count})</span>
        `;
        window.makeElementActivatable(div, () => {
            ui.navList.querySelectorAll('.list-item').forEach(el => el.classList.remove('active'));
            div.classList.add('active');
            loadDatabase(cat.id);
        });
        ui.navList.appendChild(div);
    });

    // 自定义资料库分类
    const customCategories = store.knowledgeCategories.filter(c => !c.builtin);

    if (customCategories.length > 0) {
        // 分隔线
        const separator = document.createElement('div');
        separator.style.cssText = 'height: 1px; background: var(--border-color); margin: 12px 8px;';
        ui.navList.appendChild(separator);

        // 自定义分类标题
        const customTitle = document.createElement('div');
        customTitle.style.cssText = 'font-size: 11px; color: var(--text-secondary); padding: 8px 12px; opacity: 0.7;';
        customTitle.textContent = '自定义资料库';
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
                <button class="delete-category-btn" title="删除分类" style="background: none; border: none; color: #ef4444; cursor: pointer; padding: 4px; opacity: 0; transition: opacity 0.2s;">
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

            window.makeElementActivatable(div, (e) => {
                if (!e.target.closest('.delete-category-btn')) {
                    ui.navList.querySelectorAll('.list-item').forEach(el => el.classList.remove('active'));
                    div.classList.add('active');
                    loadDatabase(cat.id);
                }
            }, {
                allowWhen: (event) => !event.target.closest('.delete-category-btn')
            });
            ui.navList.appendChild(div);
        });
    }

    // 添加新资料库按钮
    const addBtn = document.createElement('div');
    addBtn.className = 'list-item';
    addBtn.style.cssText = 'margin-top: 12px; color: var(--accent-color); border: 1px dashed var(--border-color); border-radius: 8px;';
    addBtn.innerHTML = `
        <i class="ri-add-line"></i>
        <span>添加新资料库</span>
    `;
    window.makeElementActivatable(addBtn, showAddKnowledgeCategoryDialog);
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
                    添加新资料库
                </h3>

                <div style="margin-bottom: 20px;">
                    <label style="display: block; font-size: 13px; color: var(--text-secondary); margin-bottom: 8px;">资料库名称</label>
                    <input type="text" id="new-category-name" placeholder="例如：势力阵营、技能体系..."
                        style="width: 100%; background: rgba(0,0,0,0.3); border: 1px solid var(--border-color); padding: 12px; color: var(--text-primary); border-radius: 8px; font-size: 14px;">
                </div>

                <div style="margin-bottom: 24px;">
                    <label style="display: block; font-size: 13px; color: var(--text-secondary); margin-bottom: 8px;">选择图标</label>
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
                    <button id="cancel-add-category" style="flex: 1; padding: 12px; background: rgba(255,255,255,0.1); border: 1px solid var(--border-color); color: var(--text-primary); border-radius: 8px; cursor: pointer;">取消</button>
                    <button id="confirm-add-category" style="flex: 1; padding: 12px; background: var(--accent-color); border: none; color: white; border-radius: 8px; cursor: pointer; font-weight: 600;">创建</button>
                </div>
            </div>
        </div>
    `;

    let selectedIcon = 'ri-folder-line';

    // 图标选择
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

    // 取消
    document.getElementById('cancel-add-category').addEventListener('click', () => {
        modal.classList.add('hidden');
        modal.innerHTML = '';
    });

    // 确认
    document.getElementById('confirm-add-category').addEventListener('click', () => {
        const name = document.getElementById('new-category-name').value.trim();
        if (!name) {
            showToast('请输入资料库名称', 'error');
            return;
        }

        addKnowledgeCategory(name, selectedIcon);
        modal.classList.add('hidden');
        modal.innerHTML = '';
    });
}

function addKnowledgeCategory(name, icon) {
    // 生成唯一ID和key
    const id = `db-custom-${Date.now()}`;
    const key = `custom_${Date.now()}`;

    // 添加到分类列表
    store.knowledgeCategories.push({
        id: id,
        key: key,
        name: name,
        icon: icon,
        builtin: false
    });

    // 初始化数据
    store.projectData[key] = [];

    // 保存到本地存储
    saveKnowledgeCategories();

    // 刷新导航
    renderKnowledgeNavPanel();

    showToast(`资料库「${name}」创建成功`);
}

async function deleteKnowledgeCategory(categoryId) {
    const category = store.knowledgeCategories.find(c => c.id === categoryId);
    if (!category) return;

    const count = (store.projectData[category.key] || []).length;

    if (await window.showConfirmDialog(`确定要删除资料库「${category.name}」吗？\n\n该分类下有 ${count} 条内容将被一并删除，此操作不可恢复！`)) {
        // 删除分类
        store.knowledgeCategories = store.knowledgeCategories.filter(c => c.id !== categoryId);

        // 删除数据
        delete store.projectData[category.key];

        // 保存
        saveKnowledgeCategories();

        // 刷新导航
        renderKnowledgeNavPanel();
        showEmptyWorld();

        showToast(`资料库「${category.name}」已删除`);
    }
}

function saveKnowledgeCategories() {
    // 只保存自定义的分类
    const customCategories = store.knowledgeCategories.filter(c => !c.builtin);
    localStorage.setItem('custom_knowledge_categories', JSON.stringify(customCategories));
    if (typeof syncKnowledgeCategoriesToProjectState === 'function') {
        void syncKnowledgeCategoriesToProjectState();
    }
}

function loadKnowledgeCategories() {
    try {
        const saved = localStorage.getItem('custom_knowledge_categories');
        if (saved) {
            const customCategories = JSON.parse(saved);
            // 添加到分类列表
            customCategories.forEach(cat => {
                if (!store.knowledgeCategories.find(c => c.id === cat.id)) {
                    store.knowledgeCategories.push(cat);
                    // 初始化数据
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

async function syncKnowledgeCategoriesToProjectState() {
    if (typeof apiCall !== 'function') return;
    const projectId = getExtendedKnowledgeProjectId();
    if (!projectId || projectId === 'default') return;
    try {
        const customCategories = store.knowledgeCategories.filter(c => !c.builtin);
        await apiCall('/api/project-state/knowledge_categories', 'POST', {
            data: customCategories
        });
    } catch (e) {
        console.warn('Failed to sync knowledge categories to project state:', e);
    }
}

function isServerBackedCustomKnowledgeKey(key) {
    return /^custom_[A-Za-z0-9_-]{1,80}$/.test(String(key || '').trim());
}

function isServerBackedKnowledgeKey(key) {
    const serverKeys = [
        'characters',
        'outline',
        'chapters',
        'worldbuilding',
        'items',
        'eventlines',
        'outline_settings',
        'detail_settings',
        'chapter_settings',
        'chapter_summary'
    ];
    const dataKey = String(key || '').trim();
    return serverKeys.includes(dataKey) || isServerBackedCustomKnowledgeKey(dataKey);
}

// ===== 设定管理功能 =====

let currentSettingType = null;
let knowledgeSourceFilter = 'all';
const KNOWLEDGE_SOURCE_FILTERS = [
    { key: 'all', label: '全部来源' },
    { key: 'multi_agent', label: '多Agent' },
    { key: 'infinite_write', label: '无限续写' },
    { key: 'manual_import', label: '手动导入' },
    { key: 'manual', label: '手动创建' },
    { key: 'unknown', label: '未标记' },
];
const KNOWLEDGE_SOURCE_LABELS = Object.fromEntries(KNOWLEDGE_SOURCE_FILTERS.map(item => [item.key, item.label]));
let knowledgeWorkbenchState = {
    activeNodeId: '',
    searchQuery: '',
    searchResults: [],
    activeNode: null,
    activeNeighbors: { incoming: [], outgoing: [] },
    similarNodes: [],
    recentNodes: [],
    currentType: '',
    viewMode: 'browse',
    showGraph: false
};

const BUILTIN_KNOWLEDGE_SCHEMAS = {
    outline: {
        summaryKeys: ['summary', 'story_synopsis', 'conflicts', 'selling_points'],
        fields: [
            { key: 'title', label: '大纲标题', type: 'text', required: true },
            { key: 'summary', label: '全书大纲内容', type: 'textarea', rows: 16 },
            { key: 'volume_plan', label: '分卷规划', type: 'textarea', rows: 8 },
            { key: 'story_synopsis', label: '故事梗概', type: 'textarea', rows: 5 },
            { key: 'conflicts', label: '矛盾冲突', type: 'textarea', rows: 4 },
            { key: 'selling_points', label: '小说卖点', type: 'textarea', rows: 4 },
        ],
    },
    characters: {
        summaryKeys: ['role', 'identity', 'abilities', 'inventory', 'development_history'],
        fields: [
            { key: 'name', label: '姓名', type: 'text', required: true },
            { key: 'role', label: '角色定位', type: 'select', options: ['主角', '配角', '反派', '导师', '盟友', '其他'] },
            { key: 'identity', label: '身份', type: 'text' },
            { key: 'description', label: '一句话简介', type: 'textarea', rows: 3 },
            { key: 'personality', label: '性格标签', type: 'list', placeholder: '每行一个，或用逗号分隔' },
            { key: 'abilities', label: '技能/能力', type: 'list', placeholder: '每行一个，或用逗号分隔' },
            { key: 'inventory', label: '持有物/道具', type: 'list', placeholder: '每行一个，或用逗号分隔' },
            { key: 'development_history', label: '成长记录', type: 'event_list', rows: 5, placeholder: '例如：第4章 领悟御风术' },
            { key: 'goals', label: '目标', type: 'list', placeholder: '每行一个，或用逗号分隔' },
            { key: 'relationships', label: '人物关系', type: 'relation_map', placeholder: '格式：对象：关系，每行一条' },
            { key: 'notes', label: '备注', type: 'textarea', rows: 3 },
        ],
    },
    worldbuilding: {
        summaryKeys: ['kind', 'description', 'details'],
        fields: [
            { key: 'name', label: '条目名称', type: 'text', required: true },
            { key: 'kind', label: '类型', type: 'select', options: [
                { value: 'world', label: '世界' }, { value: 'rule', label: '规则' },
                { value: 'faction', label: '势力' }, { value: 'location', label: '地点' },
                { value: 'event', label: '事件' }, { value: 'item', label: '物品' },
                { value: 'theme', label: '主题' },
                { value: 'power_system', label: '力量体系' }, { value: 'geography', label: '地理环境' },
                { value: 'history', label: '历史背景' }, { value: 'culture', label: '文化习俗' },
                { value: 'magic_system', label: '魔法体系' }, { value: 'technology_level', label: '科技水平' },
                { value: 'timeline', label: '时间线' }, { value: 'requirements', label: '创作要求' },
                { value: 'other', label: '其他' }
            ] },
            { key: 'description', label: '摘要', type: 'textarea', rows: 3 },
            { key: 'details', label: '备注', type: 'textarea', rows: 4 },
        ],
    },
    items: {
        summaryKeys: ['item_type', 'status', 'owner', 'effects'],
        fields: [
            { key: 'name', label: '名称', type: 'text', required: true },
            { key: 'item_type', label: '类别', type: 'select', options: ['未分类', '武器', '法宝', '道具', '装备', '资源', '线索', '其他'] },
            { key: 'description', label: '简介', type: 'textarea', rows: 3 },
            { key: 'effects', label: '能力/作用', type: 'list', placeholder: '每行一个效果或限制' },
            { key: 'status', label: '状态', type: 'select', options: ['未登场', '已出现', '已获得', '已消耗', '遗失', '封存'] },
            { key: 'owner', label: '当前持有者', type: 'text' },
            { key: 'acquired_chapter', label: '获得章节', type: 'number' },
            { key: 'details', label: '详细设定', type: 'textarea', rows: 3 },
            { key: 'history', label: '流转记录', type: 'event_list', rows: 4, placeholder: '例如：第6章 谢昭从密室取得玄铁令' },
            { key: 'notes', label: '备注', type: 'textarea', rows: 3 },
        ],
    },
    eventlines: {
        summaryKeys: ['participants', 'conflict', 'status'],
        fields: [
            { key: 'name', label: '事件线名称', type: 'text', required: true },
            { key: 'participants', label: '涉及角色', type: 'list', placeholder: '每行一个，或用逗号分隔' },
            { key: 'conflict', label: '核心冲突', type: 'textarea', rows: 3 },
            { key: 'status', label: '状态', type: 'select', options: ['规划中', '推进中', '已回收', '搁置'] },
            { key: 'notes', label: '备注', type: 'textarea', rows: 3 },
        ],
    },
    chapter_summary: {
        summaryKeys: ['summary_text', 'key_events', 'ending_hook'],
        fields: [
            { key: 'chapter_number', label: '章节号', type: 'number' },
            { key: 'summary_text', label: '章节摘要', type: 'textarea', rows: 3 },
            { key: 'key_events', label: '关键事件', type: 'list', placeholder: '每行一个，或用逗号分隔' },
            { key: 'appearing_characters', label: '出场角色', type: 'list', placeholder: '每行一个，或用逗号分隔' },
            { key: 'ending_hook', label: '结尾钩子', type: 'textarea', rows: 2 },
        ],
    },
    detail_settings: {
        summaryKeys: ['chapter_range', 'scene_goal', 'conflict'],
        fields: [
            { key: 'name', label: '细纲名称', type: 'text', required: true },
            { key: 'chapter_range', label: '章节范围', type: 'text' },
            { key: 'scene_goal', label: '场景目标', type: 'textarea', rows: 3 },
            { key: 'conflict', label: '本段冲突', type: 'textarea', rows: 3 },
            { key: 'notes', label: '备注', type: 'textarea', rows: 3 },
        ],
    },
    chapter_settings: {
        summaryKeys: ['chapter_number', 'chapter_goal', 'ending_hook'],
        fields: [
            { key: 'name', label: '章纲名称', type: 'text', required: true },
            { key: 'chapter_number', label: '章节号', type: 'number' },
            { key: 'chapter_goal', label: '本章目标', type: 'textarea', rows: 3 },
            { key: 'key_event', label: '关键事件', type: 'textarea', rows: 3 },
            { key: 'ending_hook', label: '结尾钩子', type: 'textarea', rows: 3 },
            { key: 'notes', label: '备注', type: 'textarea', rows: 3 },
        ],
    },
};

function getKnowledgeSchema(categoryOrKey) {
    const key = typeof categoryOrKey === 'string' ? categoryOrKey : categoryOrKey?.key;
    return BUILTIN_KNOWLEDGE_SCHEMAS[key] || null;
}

function getKnowledgeTemplateFields(category) {
    const schema = getKnowledgeSchema(category);
    return schema?.fields || [
        { key: 'name', label: '名称', type: 'text', required: true },
        { key: 'description', label: '描述', type: 'textarea', rows: 4 },
        { key: 'details', label: '详细信息', type: 'textarea', rows: 8 },
    ];
}

function getKnowledgeFreeformFields(category) {
    const categoryName = String(category?.name || '条目').trim() || '条目';
    return [
        { key: 'title', label: `${categoryName}标题`, type: 'text', required: true },
        { key: 'content', label: '自定义内容', type: 'textarea', rows: 16, required: true, placeholder: '按你的习惯直接写内容，不需要套固定字段。' },
        { key: 'notes', label: '备注', type: 'textarea', rows: 3 },
    ];
}

function isFilledSchemaValue(value) {
    if (Array.isArray(value)) return value.length > 0;
    if (value && typeof value === 'object') return Object.keys(value).length > 0;
    if (typeof value === 'number') return Number.isFinite(value) && value !== 0;
    return String(value ?? '').trim().length > 0;
}

function getSchemaFieldLabel(fields, key, fallback = '内容') {
    const field = (fields || []).find(item => item && item.key === key);
    return String(field?.label || fallback).replace(/\s*\*$/, '').trim() || fallback;
}

function getKnowledgeItemDisplayName(item, category = null) {
    if (!item || typeof item !== 'object') return '';
    const fields = category ? getKnowledgeTemplateFields(category) : [];
    const requiredKey = fields.find(field => field?.required && isFilledSchemaValue(item[field.key]))?.key;
    const candidates = [
        item.name,
        item.title,
        item.world_name,
        item.chapter_title,
        item.summary_title,
        requiredKey ? item[requiredKey] : '',
    ];
    const named = candidates.map(value => String(value ?? '').trim()).find(Boolean);
    if (named) return named;
    if (isFilledSchemaValue(item.chapter_number)) return `第${item.chapter_number}章摘要`;
    const summary = String(item.summary_text || item.summary || item.description || item.content || item.details || '').trim();
    return summary ? summary.slice(0, 24) : '';
}

function validateKnowledgeValues(fields, values, category, mode = 'template') {
    const activeFields = Array.isArray(fields) ? fields : [];
    for (const field of activeFields) {
        if (!field?.required) continue;
        if (!isFilledSchemaValue(values?.[field.key])) {
            return { ok: false, message: `请输入${getSchemaFieldLabel(activeFields, field.key)}` };
        }
    }

    const displayName = getKnowledgeItemDisplayName(values, category);
    if (displayName) return { ok: true, displayName };

    if (mode === 'template' && category?.key === 'chapter_summary') {
        return { ok: false, message: '请输入章节号或章节摘要' };
    }
    return { ok: false, message: '请输入标题或内容' };
}

function buildFreeformKnowledgeItem(category, values) {
    const title = String(values?.title || '').trim();
    const content = String(values?.content || '').trim();
    const notes = String(values?.notes || '').trim();
    const item = {
        title,
        name: title,
        content,
        raw_content: content,
        description: content,
        details: content,
        notes,
        manual_mode: 'freeform',
        source_mode: 'manual',
        source_type: 'manual_knowledge',
        tags: ['source:manual'],
    };

    if (category?.key === 'outline') {
        item.summary = content;
        item.global_outline = content;
    } else if (category?.key === 'chapter_summary') {
        item.summary_text = content;
    }

    return item;
}

function isMeaningfulOutlineText(value) {
    const text = String(value || '').trim();
    return text && text !== '待生成' && text !== '待生成。';
}

function getFirstOutlineText(items, keys) {
    for (const item of items) {
        if (!item || typeof item !== 'object') continue;
        for (const key of keys) {
            const text = String(item[key] || '').trim();
            if (isMeaningfulOutlineText(text)) return text;
        }
    }
    return '';
}

function normalizeOutlineCompareText(value) {
    return String(value || '')
        .replace(/\s+/g, '')
        .replace(/[【】《》「」『』，。；：、,.!！?？:;"'“”‘’()[\]{}\-—_]/g, '')
        .toLowerCase();
}

function outlineTextsMatch(left, right) {
    const leftText = normalizeOutlineCompareText(left);
    const rightText = normalizeOutlineCompareText(right);
    return Boolean(leftText && rightText && leftText === rightText);
}

function formatOutlineVolumePlanFromVolumes(volumes) {
    if (!Array.isArray(volumes) || !volumes.length) return '';
    const lines = ['【分卷规划】'];
    volumes.forEach((volume, index) => {
        if (!volume || typeof volume !== 'object') return;
        const number = volume.volume_number || volume.number || index + 1;
        const rawTitle = String(volume.volume_title || volume.title || volume.name || `第${number}卷`).trim();
        lines.push(rawTitle.startsWith('第') ? rawTitle : `第${number}卷：${rawTitle}`);
        [
            ['本卷概述', volume.volume_summary || volume.summary || volume.description],
            ['核心冲突', volume.core_conflict || volume.conflict],
            ['主角成长', volume.protagonist_growth || volume.character_growth],
            ['本卷高潮', volume.volume_climax || volume.climax],
            ['关键事件', volume.key_events || volume.story_beats || volume.major_events],
        ].forEach(([label, value]) => {
            const text = Array.isArray(value)
                ? value
                    .filter(Boolean)
                    .map(entry => typeof entry === 'object' ? JSON.stringify(entry) : String(entry))
                    .join('；')
                : String(value || '').trim();
            if (isMeaningfulOutlineText(text)) {
                lines.push(`- ${label}：${text}`);
            }
        });
        lines.push('');
    });
    return lines.join('\n').trim();
}

function getOutlineVolumePlan(items) {
    const existing = getFirstOutlineText(items, ['volume_plan']);
    const globalOutline = getFirstOutlineText(items, ['global_outline', 'standard_outline', 'full_outline']);
    if (existing && !outlineTextsMatch(existing, globalOutline)) return existing;
    for (const item of items) {
        if (!item || typeof item !== 'object') continue;
        const volumePlan = formatOutlineVolumePlanFromVolumes(item.volumes);
        if (volumePlan) return volumePlan;
    }
    const volumeRows = items.filter(item => item && typeof item === 'object' && (
        item.volume_number || item.volume_title || item.volume_summary
    ));
    return formatOutlineVolumePlanFromVolumes(volumeRows);
}

function buildOutlineOverviewItem(rows) {
    const items = Array.isArray(rows)
        ? rows.filter(item => item && typeof item === 'object')
        : [];
    if (!items.length) return null;

    const sourceItem = items.length === 1 ? items[0] : {};
    const manuallyEditable = Boolean(sourceItem && sourceItem.manual_mode);
    const globalOutline = getFirstOutlineText(items, ['global_outline', 'standard_outline', 'full_outline']);
    const summary = globalOutline || getFirstOutlineText(items, ['summary', 'description', 'content']);
    const volumePlan = getOutlineVolumePlan(items);

    return {
        id: sourceItem.id || 'outline-overview',
        title: sourceItem.title || sourceItem.name || '主线大纲',
        name: sourceItem.name || sourceItem.title || '主线大纲',
        summary: summary || '暂无大纲内容。',
        content: sourceItem.content || sourceItem.raw_content || summary || '',
        raw_content: sourceItem.raw_content || sourceItem.content || '',
        volume_plan: volumePlan,
        story_synopsis: getFirstOutlineText(items, ['story_synopsis', 'synopsis']) || '主线蓝图，章节目标另存为章纲或细纲。',
        conflicts: getFirstOutlineText(items, ['conflicts', 'main_conflict']),
        selling_points: getFirstOutlineText(items, ['selling_points']),
        notes: sourceItem.notes || '',
        manual_mode: sourceItem.manual_mode || '',
        readonly: !manuallyEditable,
    };
}

function getKnowledgeCategoryData(category) {
    if (!category) return [];
    const data = store.projectData[category.key] || [];
    if (category.key === 'outline') {
        const overview = buildOutlineOverviewItem(data);
        return overview ? [overview] : [];
    }
    return data;
}

function normalizeKnowledgeSourceMode(value) {
    const raw = String(value || '').trim().toLowerCase().replace(/\s+/g, '_').replace(/-/g, '_');
    const aliases = {
        copilot: 'multi_agent',
        copilot_chat: 'multi_agent',
        multiagent: 'multi_agent',
        continuous_write: 'infinite_write',
        file_import: 'manual_import',
        import: 'manual_import',
    };
    return aliases[raw] || raw;
}

function getKnowledgeItemSourceMode(item) {
    if (!item || typeof item !== 'object') return 'unknown';
    const direct = normalizeKnowledgeSourceMode(item.source_mode || item.mode_source);
    if (direct) return direct;
    const tags = Array.isArray(item.tags) ? item.tags : [];
    const sourceTag = tags.find(tag => String(tag || '').toLowerCase().startsWith('source:'));
    if (sourceTag) return normalizeKnowledgeSourceMode(String(sourceTag).slice('source:'.length)) || 'unknown';
    const sourceText = normalizeKnowledgeSourceMode(item.source || item.source_type);
    if (['copilot_auto_save', 'copilot_chat', 'contract_confirmation'].includes(sourceText)) return 'multi_agent';
    if (sourceText === 'infinite_write') return 'infinite_write';
    if (item.source_file) return 'manual_import';
    return 'unknown';
}

function ensureKnowledgeSourceTag(item, sourceMode = 'manual') {
    const mode = normalizeKnowledgeSourceMode(sourceMode) || 'manual';
    const next = { ...(item || {}) };
    next.source_mode = next.source_mode || mode;
    next.source_type = next.source_type || (mode === 'manual' ? 'manual_knowledge' : mode);
    const tags = Array.isArray(next.tags) ? next.tags.slice() : [];
    if (!tags.some(tag => String(tag || '').toLowerCase().startsWith('source:'))) {
        tags.push(`source:${mode}`);
    }
    next.tags = tags;
    return next;
}

function getKnowledgeFilteredItems(items) {
    const source = Array.isArray(items) ? items : [];
    if (knowledgeSourceFilter === 'all') return source;
    return source.filter(item => getKnowledgeItemSourceMode(item) === knowledgeSourceFilter);
}

function renderKnowledgeSourceFilters(items) {
    const source = Array.isArray(items) ? items : [];
    const counts = {};
    source.forEach(item => {
        const mode = getKnowledgeItemSourceMode(item);
        counts[mode] = (counts[mode] || 0) + 1;
    });
    return `
        <div style="display:flex; flex-wrap:wrap; gap:6px; margin-bottom:16px;">
            ${KNOWLEDGE_SOURCE_FILTERS.map(item => {
                const active = knowledgeSourceFilter === item.key;
                const count = item.key === 'all' ? source.length : (counts[item.key] || 0);
                return `
                    <button type="button" class="knowledge-source-filter" data-source="${item.key}"
                        style="padding:5px 10px;border-radius:999px;border:1px solid ${active ? 'var(--accent-color)' : 'var(--border-color)'};
                        background:${active ? 'color-mix(in srgb, var(--accent-color) 14%, transparent)' : 'rgba(255,255,255,0.03)'};
                        color:${active ? 'var(--accent-color)' : 'var(--text-secondary)'};cursor:pointer;font-size:12px;">
                        ${item.label} (${count})
                    </button>
                `;
            }).join('')}
        </div>
    `;
}

function bindKnowledgeSourceFilters(typeId) {
    document.querySelectorAll('.knowledge-source-filter').forEach(btn => {
        btn.addEventListener('click', () => {
            knowledgeSourceFilter = btn.dataset.source || 'all';
            loadDatabase(typeId);
        });
    });
}

function getKnowledgeCategoryCount(category) {
    return getKnowledgeCategoryData(category).length;
}

function localizeGeneratedSchemaLabels(value) {
    return String(value ?? '')
        .replace(/(^|[；;，,\n]\s*)levels\s*[:：]\s*/gi, '$1境界层级：')
        .replace(/(^|[；;，,\n]\s*)cultivation\s+method\s*[:：]\s*/gi, '$1修炼方式：')
        .replace(/(^|[；;，,\n]\s*)special\s+abilities\s*[:：]\s*/gi, '$1特殊能力：')
        .replace(/(^|[；;，,\n]\s*)limitations\s*[:：]\s*/gi, '$1限制与代价：')
        .replace(/(^|[；;，,\n]\s*)power\s+system\s*[:：]\s*/gi, '$1力量体系：');
}

function formatListEntryValue(value) {
    if (value === null || value === undefined) return '';
    if (typeof value !== 'object') return String(value);
    const chapter = value.chapter_number || value.chapter || '';
    const title = String(value.title || value.name || value.event || value.description || value.detail || '').trim();
    const description = String(value.description || value.detail || value.notes || '').trim();
    const prefix = chapter ? `第${chapter}章 ` : '';
    if (title && description && description !== title) {
        return `${prefix}${title}：${description}`;
    }
    return `${prefix}${title || JSON.stringify(value)}`.trim();
}

function formatSchemaFieldValue(field, value) {
    if (value === null || value === undefined) return '';
    if (field.type === 'list') {
        return localizeGeneratedSchemaLabels(Array.isArray(value) ? value.map(formatListEntryValue).join('\n') : value);
    }
    if (field.type === 'event_list') {
        return localizeGeneratedSchemaLabels(Array.isArray(value) ? value.map(formatListEntryValue).join('\n') : value);
    }
    if (field.type === 'relation_map') {
        if (typeof value === 'string') return localizeGeneratedSchemaLabels(value);
        if (value && typeof value === 'object') {
            return localizeGeneratedSchemaLabels(
                Object.entries(value).map(([target, relation]) => `${target}：${relation}`).join('\n')
            );
        }
    }
    return localizeGeneratedSchemaLabels(value);
}

function escapeAttributeValue(value) {
    return String(value ?? '')
        .replace(/&/g, '&amp;')
        .replace(/"/g, '&quot;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;');
}

function getKnowledgeItemName(item, fallback = '未命名条目') {
    if (!item || typeof item !== 'object') return fallback;
    const candidates = [item.name, item.title, item.world_name, item.chapter_title, item.summary_title, item.id];
    const name = candidates.map(value => String(value ?? '').trim()).find(Boolean);
    if (name) return name;
    if (isFilledSchemaValue(item.chapter_number)) return `第${item.chapter_number}章摘要`;
    return fallback;
}

function parseSchemaFieldValue(field, rawValue) {
    const text = String(rawValue ?? '').trim();
    if (field.type === 'number') {
        if (!text) return 0;
        const parsed = Number.parseInt(text, 10);
        return Number.isFinite(parsed) ? parsed : 0;
    }
    if (field.type === 'list') {
        return text
            ? text.split(/[\n,，、]+/).map(item => item.trim()).filter(Boolean)
            : [];
    }
    if (field.type === 'event_list') {
        if (!text) return [];
        return text
            .split(/\n+/)
            .map(line => line.trim())
            .filter(Boolean)
            .map(line => {
                const chapterMatch = line.match(/^第?(\d+)章?\s*[：:、\-—]?\s*(.*)$/);
                const titleText = (chapterMatch ? chapterMatch[2] : line).trim();
                return {
                    chapter_number: chapterMatch ? Number.parseInt(chapterMatch[1], 10) : 0,
                    event_type: 'note',
                    title: titleText.split(/[：:]/)[0].trim().slice(0, 40) || titleText.slice(0, 40),
                    description: titleText,
                };
            });
    }
    if (field.type === 'relation_map') {
        return text;
    }
    return text;
}

function buildSchemaFieldHtml(field, value, prefix) {
    const fieldId = `${prefix}-${field.key}`;
    const label = field.required ? `${field.label} <span style="color: #ef4444;">*</span>` : field.label;
    const commonStyle = 'width: 100%; background: rgba(0,0,0,0.2); border: 1px solid var(--border-color); padding: 12px; color: var(--text-primary); border-radius: 8px; font-size: 14px;';
    const renderedValue = formatSchemaFieldValue(field, value);
    const placeholder = field.placeholder || '';
    if (field.type === 'textarea' || field.type === 'list' || field.type === 'event_list' || field.type === 'relation_map') {
        return `
            <div style="margin-bottom: 20px;">
                <label style="display: block; font-size: 12px; color: var(--text-secondary); margin-bottom: 8px;">${label}</label>
                <textarea id="${fieldId}" rows="${field.rows || 4}" placeholder="${placeholder}"
                    style="${commonStyle} resize: vertical; line-height: 1.6;">${escapeHtml(renderedValue)}</textarea>
            </div>
        `;
    }
    if (field.type === 'select') {
        const options = (field.options || []).map(option => {
            const optVal = typeof option === 'object' ? option.value : option;
            const optLabel = typeof option === 'object' ? option.label : option;
            const selected = String(optVal) === renderedValue ? 'selected' : '';
            return `<option value="${optVal}" ${selected}>${optLabel}</option>`;
        }).join('');
        return `
            <div style="margin-bottom: 20px;">
                <label style="display: block; font-size: 12px; color: var(--text-secondary); margin-bottom: 8px;">${label}</label>
                <select id="${fieldId}" style="${commonStyle}">
                    ${options}
                </select>
            </div>
        `;
    }
    const inputType = field.type === 'number' ? 'number' : 'text';
    return `
        <div style="margin-bottom: 20px;">
            <label style="display: block; font-size: 12px; color: var(--text-secondary); margin-bottom: 8px;">${label}</label>
            <input type="${inputType}" id="${fieldId}" value="${escapeAttributeValue(renderedValue)}" placeholder="${escapeAttributeValue(placeholder)}"
                style="${commonStyle}">
        </div>
    `;
}

function collectSchemaFormValues(fields, prefix) {
    const item = {};
    fields.forEach(field => {
        const el = document.getElementById(`${prefix}-${field.key}`);
        if (!el) return;
        item[field.key] = parseSchemaFieldValue(field, el.value);
    });
    return item;
}

function buildKnowledgeItemSummary(item, category) {
    const schema = getKnowledgeSchema(category);
    if (!schema) {
        return item.description || item.details || '暂无描述，点击编辑添加';
    }
    const lines = [];
    for (const key of schema.summaryKeys || []) {
        let value = item[key];
        if (value === null || value === undefined || value === '') continue;
        const field = (schema.fields || []).find(f => f.key === key);
        if (field && field.type === 'select' && typeof value === 'string') {
            const opt = (field.options || []).find(o => typeof o === 'object' ? o.value === value : false);
            if (opt) value = opt.label;
        }
        const text = localizeGeneratedSchemaLabels(
            Array.isArray(value) ? value.map(formatListEntryValue).join('、') : (typeof value === 'object' ? JSON.stringify(value) : String(value))
        );
        if (text.trim()) lines.push(text.trim());
        if (lines.length >= 3) break;
    }
    return localizeGeneratedSchemaLabels(lines.join('｜') || item.description || item.details || '暂无摘要，点击编辑补充结构化信息');
}

function renderKnowledgeWorkbench() {
    // 如果处于合并的"知识中心"模式，重新渲染导航面板以保留 Tab
    if (typeof auxMemoryState !== 'undefined' && auxMemoryState.subView === 'workbench'
        && typeof renderAuxMemoryNavPanel === 'function') {
        renderAuxMemoryNavPanel();
    } else {
        ui.navList.innerHTML = '';
    }
    ui.workspace.innerHTML = `
        <div style="display:grid; grid-template-columns: 280px minmax(0,1fr) 320px; height: 100%; min-height: 0; gap: 0;">
            <div id="kw-sidebar" style="border-right: 1px solid var(--border-color); padding: 16px; overflow: auto;"></div>
            <div id="kw-viewer" style="padding: 20px; overflow: auto;"></div>
            <div id="kw-relations" style="border-left: 1px solid var(--border-color); padding: 16px; overflow: auto;"></div>
        </div>
    `;
    renderKnowledgeWorkbenchSidebar();
    renderKnowledgeWorkbenchViewer();
    renderKnowledgeWorkbenchRelationPanel();
}

function renderKnowledgeWorkbenchSidebar() {
    const el = document.getElementById('kw-sidebar');
    if (!el) return;
    const categories = store.knowledgeCategories || [];
    el.innerHTML = `
        <div style="display:flex; gap:8px; margin-bottom:12px;">
            <input id="kw-search-input" type="text" placeholder="搜索节点..." value="${escapeAttributeValue(knowledgeWorkbenchState.searchQuery)}" style="flex:1; background: rgba(0,0,0,0.2); border:1px solid var(--border-color); color:var(--text-primary); border-radius:8px; padding:10px;">
            <button id="kw-search-btn" style="padding:10px 12px; background:var(--accent-color); color:white; border:none; border-radius:8px; cursor:pointer;"><i class="ri-search-line"></i></button>
        </div>
        <div style="font-size:12px; color:var(--text-secondary); margin-bottom:8px;">最近访问</div>
        <div id="kw-recent-list"></div>
        <div style="margin-top:16px; font-size:12px; color:var(--text-secondary); margin-bottom:8px;">节点类型</div>
        <div id="kw-type-list"></div>
        <div style="margin-top:16px; font-size:12px; color:var(--text-secondary); margin-bottom:8px;">搜索结果</div>
        <div id="kw-result-list"></div>
    `;
    document.getElementById('kw-search-btn')?.addEventListener('click', performKnowledgeSearch);
    document.getElementById('kw-search-input')?.addEventListener('keydown', (e) => { if (e.key === 'Enter') performKnowledgeSearch(); });
    document.getElementById('kw-type-list').innerHTML = categories.map(cat => `<button class="kw-type-btn" data-type="${cat.key}" style="display:block; width:100%; text-align:left; margin:4px 0; padding:8px 10px; background:rgba(255,255,255,0.03); border:1px solid var(--border-color); color:var(--text-primary); border-radius:8px; cursor:pointer;">${cat.name}</button>`).join('');
    document.querySelectorAll('.kw-type-btn').forEach(btn => btn.addEventListener('click', () => {
        knowledgeWorkbenchState.currentType = btn.dataset.type;
        performKnowledgeSearch();
    }));
    renderKnowledgeWorkbenchRecentList();
}

function renderKnowledgeWorkbenchRecentList() {
    const el = document.getElementById('kw-recent-list');
    if (!el) return;
    const items = knowledgeWorkbenchState.recentNodes.slice(0, 8);
    el.innerHTML = items.length ? items.map(node => `<button class="kw-node-btn" data-node-id="${node.id}" style="display:block; width:100%; text-align:left; margin:4px 0; padding:8px 10px; background:rgba(255,255,255,0.03); border:1px solid var(--border-color); color:var(--text-primary); border-radius:8px; cursor:pointer;">${node.title}</button>`).join('') : '<div style="font-size:12px; color:var(--text-secondary);">暂无最近访问</div>';
    el.querySelectorAll('.kw-node-btn').forEach(btn => btn.addEventListener('click', () => loadKnowledgeNode(btn.dataset.nodeId)));
}

async function performKnowledgeSearch() {
    const input = document.getElementById('kw-search-input');
    if (!input) return;
    knowledgeWorkbenchState.searchQuery = input.value.trim();
    const params = new URLSearchParams({ q: knowledgeWorkbenchState.searchQuery || ' ' , limit: '20' });
    if (knowledgeWorkbenchState.currentType) params.set('node_type', knowledgeWorkbenchState.currentType);
    const res = await apiCall(`/api/knowledge-base/search?${params.toString()}`, 'GET');
    knowledgeWorkbenchState.searchResults = Array.isArray(res?.results) ? res.results : [];
    renderKnowledgeWorkbenchSidebar();
    renderKnowledgeWorkbenchSearchResults();
}

function renderKnowledgeWorkbenchSearchResults() {
    const el = document.getElementById('kw-result-list');
    if (!el) return;
    const items = knowledgeWorkbenchState.searchResults;
    el.innerHTML = items.length ? items.map(node => `<button class="kw-node-btn" data-node-id="${node.id}" style="display:block; width:100%; text-align:left; margin:4px 0; padding:8px 10px; background:rgba(255,255,255,0.03); border:1px solid var(--border-color); color:var(--text-primary); border-radius:8px; cursor:pointer;"><div style="font-weight:600;">${node.title}</div><div style="font-size:12px; color:var(--text-secondary);">${node.summary || ''}</div></button>`).join('') : '<div style="font-size:12px; color:var(--text-secondary);">暂无结果</div>';
    el.querySelectorAll('.kw-node-btn').forEach(btn => btn.addEventListener('click', () => loadKnowledgeNode(btn.dataset.nodeId)));
}

async function loadKnowledgeNode(nodeId) {
    if (!nodeId) return;
    const res = await apiCall(`/api/knowledge-base/node/${encodeURIComponent(nodeId)}`, 'GET');
    knowledgeWorkbenchState.activeNode = res?.node || null;
    knowledgeWorkbenchState.activeNeighbors = res?.neighbors || { incoming: [], outgoing: [] };
    if (knowledgeWorkbenchState.activeNode) {
        knowledgeWorkbenchState.activeNodeId = knowledgeWorkbenchState.activeNode.id;
        knowledgeWorkbenchState.recentNodes = [knowledgeWorkbenchState.activeNode, ...knowledgeWorkbenchState.recentNodes.filter(n => n.id !== knowledgeWorkbenchState.activeNode.id)].slice(0, 20);
        await loadSimilarNodes(knowledgeWorkbenchState.activeNode);
    } else {
        knowledgeWorkbenchState.similarNodes = [];
    }
    renderKnowledgeWorkbenchViewer();
    renderKnowledgeWorkbenchRelationPanel();
    renderKnowledgeWorkbenchSidebar();
}

function renderKnowledgeWorkbenchViewer() {
    const el = document.getElementById('kw-viewer');
    if (!el) return;
    const node = knowledgeWorkbenchState.activeNode;
    if (!node) {
        el.innerHTML = '<div class="empty-state"><i class="ri-node-tree"></i><h2>搜索并选择一个知识节点</h2></div>';
        return;
    }
    const links = Array.isArray(node.links_out) ? node.links_out : [];
    const isEditing = knowledgeWorkbenchState.viewMode === 'edit';
    const structured = node.metadata || {};
    const textAreaValue = escapeHtml(JSON.stringify(structured, null, 2));
    const typeSchema = getKnowledgeSchema(node.type) || null;
    const structuredFields = typeSchema?.fields || [];
    const structuredFieldHtml = isEditing && structuredFields.length ? `
        <div style="margin-top:16px; padding:16px; border:1px solid var(--border-color); border-radius:12px; background:rgba(255,255,255,0.02);">
            <div style="font-weight:600; margin-bottom:12px;">结构化字段</div>
            ${structuredFields.map((field) => {
                const currentValue = structured[field.key] ?? '';
                const fieldId = `kw-field-${field.key}`;
                const commonStyle = 'width:100%; padding:10px 12px; border:1px solid var(--border-color); border-radius:8px; background:rgba(0,0,0,0.2); color:var(--text-primary);';
                if (field.type === 'textarea' || field.type === 'list' || field.type === 'relation_map') {
                    return `<div style="margin-bottom:12px;"><div style="font-size:12px; color:var(--text-secondary); margin-bottom:6px;">${field.label}</div><textarea id="${fieldId}" rows="${field.rows || 3}" style="${commonStyle}">${escapeHtml(Array.isArray(currentValue) ? currentValue.join('\n') : String(currentValue || ''))}</textarea></div>`;
                }
                if (field.type === 'select') {
                    const options = (field.options || []).map((opt) => {
                        const optValue = typeof opt === 'object' ? opt.value : opt;
                        const optLabel = typeof opt === 'object' ? opt.label : opt;
                        const selected = String(optValue) === String(currentValue) ? 'selected' : '';
                        return `<option value="${escapeAttributeValue(optValue)}" ${selected}>${escapeHtml(optLabel)}</option>`;
                    }).join('');
                    return `<div style="margin-bottom:12px;"><div style="font-size:12px; color:var(--text-secondary); margin-bottom:6px;">${field.label}</div><select id="${fieldId}" style="${commonStyle}">${options}</select></div>`;
                }
                const inputType = field.type === 'number' ? 'number' : 'text';
                return `<div style="margin-bottom:12px;"><div style="font-size:12px; color:var(--text-secondary); margin-bottom:6px;">${field.label}</div><input id="${fieldId}" type="${inputType}" value="${escapeAttributeValue(currentValue)}" style="${commonStyle}"></div>`;
            }).join('')}
        </div>
    ` : '';
    el.innerHTML = `
        <div style="max-width: 900px; margin: 0 auto;">
            <div style="display:flex; align-items:center; justify-content:space-between; gap:10px; margin-bottom:16px;">
                <div style="display:flex; align-items:center; gap:10px;"><h2 style="margin:0;">${node.title}</h2><span style="padding:2px 8px; border:1px solid var(--border-color); border-radius:999px; font-size:12px; color:var(--text-secondary);">${node.type || ''}</span></div>
                <button id="kw-toggle-edit" style="padding:8px 12px; border:none; border-radius:8px; background:var(--accent-color); color:white; cursor:pointer;">${isEditing ? '浏览模式' : '编辑模式'}</button>
            </div>
            <div style="color:var(--text-secondary); margin-bottom:16px;">${node.summary || ''}</div>
            <div id="kw-view-display" style="${isEditing ? 'display:none;' : ''}">
                <div style="padding:16px; background:rgba(255,255,255,0.03); border:1px solid var(--border-color); border-radius:12px; margin-bottom:16px;">${renderMarkdown(node.summary || '')}</div>
                <div style="display:flex; flex-wrap:wrap; gap:8px; margin-bottom:16px;">${links.map(link => `<button class="kw-link-chip" data-node-ref="${escapeAttributeValue(link.replace(/^\[\[|\]\]$/g, ''))}" style="padding:6px 10px; border:1px solid var(--border-color); border-radius:999px; background:rgba(255,255,255,0.03); color:var(--text-primary); cursor:pointer;">${link}</button>`).join('')}</div>
                <pre style="white-space:pre-wrap; background:rgba(0,0,0,0.2); padding:16px; border-radius:12px; border:1px solid var(--border-color);">${escapeHtml(JSON.stringify(structured, null, 2))}</pre>
            </div>
            <div id="kw-view-editor" style="${isEditing ? '' : 'display:none;'}">
                <input id="kw-edit-title" value="${escapeAttributeValue(node.title || '')}" style="width:100%; margin-bottom:12px; padding:12px; border:1px solid var(--border-color); background:rgba(0,0,0,0.2); color:var(--text-primary); border-radius:8px;">
                <textarea id="kw-edit-summary" rows="6" style="width:100%; margin-bottom:12px; padding:12px; border:1px solid var(--border-color); background:rgba(0,0,0,0.2); color:var(--text-primary); border-radius:8px;">${escapeHtml(node.summary || '')}</textarea>
                <textarea id="kw-edit-metadata" rows="16" style="width:100%; margin-bottom:12px; padding:12px; border:1px solid var(--border-color); background:rgba(0,0,0,0.2); color:var(--text-primary); border-radius:8px;">${textAreaValue}</textarea>
                <button id="kw-save-node" style="padding:10px 14px; border:none; border-radius:8px; background:var(--accent-color); color:white; cursor:pointer;">保存节点</button>
            </div>
        </div>
    `;
    document.getElementById('kw-toggle-edit')?.addEventListener('click', () => {
        knowledgeWorkbenchState.viewMode = isEditing ? 'browse' : 'edit';
        renderKnowledgeWorkbenchViewer();
    });
    el.querySelectorAll('.kw-link-chip').forEach(btn => btn.addEventListener('click', () => loadKnowledgeNode(btn.dataset.nodeRef)));
    document.getElementById('kw-save-node')?.addEventListener('click', async () => {
        const title = String(document.getElementById('kw-edit-title')?.value || '').trim();
        const summary = String(document.getElementById('kw-edit-summary')?.value || '').trim();
        const metadataRaw = String(document.getElementById('kw-edit-metadata')?.value || '').trim();
        if (!title) { showToast('标题不能为空', 'error'); return; }
        let metadata = {};
        try { metadata = metadataRaw ? JSON.parse(metadataRaw) : {}; } catch (e) { showToast('元数据JSON格式错误', 'error'); return; }
        structuredFields.forEach((field) => {
            const elField = document.getElementById(`kw-field-${field.key}`);
            if (!elField) return;
            const raw = String(elField.value || '').trim();
            if (field.type === 'list') {
                metadata[field.key] = raw ? raw.split(/[\n,，、]+/).map(item => item.trim()).filter(Boolean) : [];
            } else if (field.type === 'number') {
                metadata[field.key] = raw ? Number(raw) : 0;
            } else {
                metadata[field.key] = raw;
            }
        });
        const nodeType = String(node.type || '').trim();
        if (nodeType === 'chapter_summary') {
            metadata.summary_text = summary;
            metadata.title = title;
        }
        try {
            await apiCall('/api/knowledge-base/update-node', 'POST', {
                node_id: node.id,
                title,
                summary,
                metadata
            });
            showToast('节点已保存', 'success');
            knowledgeWorkbenchState.viewMode = 'browse';
            await loadKnowledgeNode(node.id);
        } catch (e) {
            showToast(`保存失败: ${e.message}`, 'error');
        }
    });
}

function renderKnowledgeWorkbenchRelationPanel() {
    const el = document.getElementById('kw-relations');
    if (!el) return;
    const n = knowledgeWorkbenchState.activeNeighbors || { incoming: [], outgoing: [] };
    const incoming = Array.isArray(n.incoming) ? n.incoming : [];
    const outgoing = Array.isArray(n.outgoing) ? n.outgoing : [];
    const similar = Array.isArray(knowledgeWorkbenchState.similarNodes) ? knowledgeWorkbenchState.similarNodes : [];
    el.innerHTML = `
        <div style="display:flex; align-items:center; justify-content:space-between; margin-bottom:12px;">
            <div style="font-size:14px; font-weight:600;">关系浏览</div>
            <button id="kw-toggle-graph" style="padding:6px 10px; border:1px solid var(--border-color); background:rgba(255,255,255,0.03); color:var(--text-primary); border-radius:8px; cursor:pointer;">${knowledgeWorkbenchState.showGraph ? '隐藏图谱' : '显示图谱'}</button>
        </div>
        <div style="margin-bottom:16px;"><div style="font-size:12px; color:var(--text-secondary); margin-bottom:8px;">反向链接</div>${incoming.length ? incoming.map(item => `<button class="kw-node-btn" data-node-id="${item.id}" style="display:block; width:100%; text-align:left; margin:4px 0; padding:8px 10px; background:rgba(255,255,255,0.03); border:1px solid var(--border-color); color:var(--text-primary); border-radius:8px; cursor:pointer;">${item.title}</button>`).join('') : '<div style="font-size:12px; color:var(--text-secondary);">暂无</div>'}</div>
        <div style="margin-bottom:16px;"><div style="font-size:12px; color:var(--text-secondary); margin-bottom:8px;">出链</div>${outgoing.length ? outgoing.map(link => `<button class="kw-node-btn" data-node-id="${String(link).replace(/^\[\[|\]\]$/g, '')}" style="display:block; width:100%; text-align:left; margin:4px 0; padding:8px 10px; background:rgba(255,255,255,0.03); border:1px solid var(--border-color); color:var(--text-primary); border-radius:8px; cursor:pointer;">${link}</button>`).join('') : '<div style="font-size:12px; color:var(--text-secondary);">暂无</div>'}</div>
        <div><div style="font-size:12px; color:var(--text-secondary); margin-bottom:8px;">相似节点</div>${similar.length ? similar.map(item => `<button class="kw-node-btn" data-node-id="${item.id}" style="display:block; width:100%; text-align:left; margin:4px 0; padding:8px 10px; background:rgba(255,255,255,0.03); border:1px solid var(--border-color); color:var(--text-primary); border-radius:8px; cursor:pointer;"><div style="font-weight:600;">${item.title}</div><div style="font-size:12px; color:var(--text-secondary);">${item.summary || ''}</div></button>`).join('') : '<div style="font-size:12px; color:var(--text-secondary);">暂无</div>'}</div>
        <div id="kw-graph-panel" style="margin-top:16px; ${knowledgeWorkbenchState.showGraph ? '' : 'display:none;'}"></div>
    `;
    el.querySelectorAll('.kw-node-btn').forEach(btn => btn.addEventListener('click', () => loadKnowledgeNode(btn.dataset.nodeId)));
    document.getElementById('kw-toggle-graph')?.addEventListener('click', () => {
        knowledgeWorkbenchState.showGraph = !knowledgeWorkbenchState.showGraph;
        renderKnowledgeWorkbenchRelationPanel();
    });
    if (knowledgeWorkbenchState.showGraph) {
        renderKnowledgeGraphView(document.getElementById('kw-graph-panel'));
    }
}

async function loadSimilarNodes(node) {
    const query = [node.title, node.summary, ...(node.links_out || [])].filter(Boolean).join(' ');
    if (!query) {
        knowledgeWorkbenchState.similarNodes = [];
        return;
    }
    try {
        const res = await apiCall(`/api/knowledge-base/search?q=${encodeURIComponent(query)}&limit=8`, 'GET');
        const results = Array.isArray(res?.results) ? res.results : [];
        knowledgeWorkbenchState.similarNodes = results.filter(item => item.id !== node.id).slice(0, 5);
    } catch (_) {
        knowledgeWorkbenchState.similarNodes = [];
    }
}

function renderKnowledgeGraphView(container) {
    const el = container || document.getElementById('kw-graph-panel');
    if (!el) return;
    const node = knowledgeWorkbenchState.activeNode;
    if (!node) {
        el.innerHTML = '<div class="kw-graph-empty">暂无图谱数据</div>';
        return;
    }
    const relations = [];
    (knowledgeWorkbenchState.activeNeighbors?.incoming || []).slice(0, 5).forEach(item => relations.push({ title: item.title, id: item.id, kind: 'incoming' }));
    (knowledgeWorkbenchState.activeNeighbors?.outgoing || []).slice(0, 5).forEach(item => relations.push({ title: String(item).replace(/^\[\[|\]\]$/g, ''), id: String(item).replace(/^\[\[|\]\]$/g, ''), kind: 'outgoing' }));
    (knowledgeWorkbenchState.similarNodes || []).slice(0, 5).forEach(item => relations.push({ title: item.title, id: item.id, kind: 'similar' }));
    const nodesHtml = relations.slice(0, 10).map((item, index) => {
        const x = 20 + (index % 3) * 95;
        const y = 20 + Math.floor(index / 3) * 72;
        const color = item.kind === 'incoming' ? '#10b981' : item.kind === 'outgoing' ? '#3b82f6' : '#f59e0b';
        return `<button class="kw-node-btn" data-node-id="${item.id}" style="position:absolute; left:${x}px; top:${y}px; width:88px; min-height:44px; padding:8px; border-radius:12px; border:1px solid ${color}; background:${color}22; color:var(--text-primary); cursor:pointer; font-size:12px; overflow:hidden; text-overflow:ellipsis;">${item.title}</button>`;
    }).join('');
    el.innerHTML = `
        <div style="font-size:12px; color:var(--text-secondary); margin-bottom:8px;">图谱预览</div>
        <div style="position:relative; height:280px; border:1px solid var(--border-color); border-radius:12px; background:rgba(255,255,255,0.02); overflow:hidden;">
            <div style="position:absolute; left:50%; top:50%; transform:translate(-50%,-50%); width:100px; height:50px; display:flex; align-items:center; justify-content:center; border-radius:14px; border:1px solid var(--accent-color); background:rgba(59,130,246,0.18); color:var(--text-primary); font-weight:600;">${node.title}</div>
            ${nodesHtml}
        </div>
    `;
    el.querySelectorAll('.kw-node-btn').forEach(btn => btn.addEventListener('click', () => loadKnowledgeNode(btn.dataset.nodeId)));
}

function addNewSetting() {
    // 根据当前选中的资料库类型添加
    const category = store.knowledgeCategories.find(c => c.id === currentSettingType);
    if (!category) {
        showToast('请先选择一个资料库类别', 'warning');
        return;
    }

    showAddSettingDialog(category);
}

function showAddSettingDialog(category) {
    const modal = document.getElementById('modal-container');
    modal.classList.remove('hidden');
    const templateFields = getKnowledgeTemplateFields(category);
    const freeformFields = getKnowledgeFreeformFields(category);

    modal.innerHTML = `
        <div style="position: fixed; top: 0; left: 0; right: 0; bottom: 0; background: rgba(0,0,0,0.6); display: flex; align-items: center; justify-content: center; z-index: 1000;">
            <div style="background: var(--bg-panel); border: 1px solid var(--border-color); border-radius: 16px; padding: 30px; width: 720px; max-width: 95%; max-height: 90vh; overflow-y: auto;">
                <h3 style="color: var(--text-primary); margin-bottom: 24px; font-size: 18px;">
                    <i class="${category.icon}" style="margin-right: 8px;"></i>
                    添加${category.name}
                </h3>
                <div style="display:flex; gap:8px; margin-bottom:20px;">
                    <label style="flex:1; cursor:pointer;">
                        <input type="radio" name="new-setting-mode" value="freeform" checked style="accent-color: var(--accent-color);">
                        <span style="margin-left:6px; color:var(--text-primary);">自由内容</span>
                    </label>
                    <label style="flex:1; cursor:pointer;">
                        <input type="radio" name="new-setting-mode" value="template" style="accent-color: var(--accent-color);">
                        <span style="margin-left:6px; color:var(--text-primary);">结构化模板</span>
                    </label>
                </div>
                <div id="new-setting-freeform-section">
                    ${freeformFields.map(field => buildSchemaFieldHtml(field, '', 'new-setting-freeform')).join('')}
                </div>
                <div id="new-setting-template-section" style="display:none;">
                    ${templateFields.map(field => buildSchemaFieldHtml(field, '', 'new-setting-template')).join('')}
                </div>

                <div style="display: flex; gap: 12px;">
                    <button id="cancel-add-setting" style="flex: 1; padding: 12px; background: rgba(255,255,255,0.1); border: 1px solid var(--border-color); color: var(--text-primary); border-radius: 8px; cursor: pointer;">取消</button>
                    <button id="confirm-add-setting" style="flex: 1; padding: 12px; background: var(--accent-color); border: none; color: white; border-radius: 8px; cursor: pointer; font-weight: 600;">创建</button>
                </div>
            </div>
        </div>
    `;

    // 自动聚焦输入框
    setTimeout(() => {
        document.getElementById('new-setting-freeform-title')?.focus();
    }, 100);

    function syncModeSections() {
        const mode = document.querySelector('input[name="new-setting-mode"]:checked')?.value || 'freeform';
        const freeformSection = document.getElementById('new-setting-freeform-section');
        const templateSection = document.getElementById('new-setting-template-section');
        if (freeformSection) freeformSection.style.display = mode === 'freeform' ? '' : 'none';
        if (templateSection) templateSection.style.display = mode === 'template' ? '' : 'none';
    }
    modal.querySelectorAll('input[name="new-setting-mode"]').forEach(input => {
        input.addEventListener('change', syncModeSections);
    });
    syncModeSections();

    // 取消
    document.getElementById('cancel-add-setting').addEventListener('click', () => {
        modal.classList.add('hidden');
        modal.innerHTML = '';
    });

    // 确认
    document.getElementById('confirm-add-setting').addEventListener('click', async () => {
        const mode = document.querySelector('input[name="new-setting-mode"]:checked')?.value || 'freeform';
        const activeFields = mode === 'template' ? templateFields : freeformFields;
        const rawValues = collectSchemaFormValues(
            activeFields,
            mode === 'template' ? 'new-setting-template' : 'new-setting-freeform'
        );
        const validation = validateKnowledgeValues(activeFields, rawValues, category, mode);
        if (!validation.ok) {
            showToast(validation.message, 'error');
            return;
        }
        const newItem = mode === 'template'
            ? ensureKnowledgeSourceTag({ ...rawValues, manual_mode: 'template' }, 'manual')
            : ensureKnowledgeSourceTag(buildFreeformKnowledgeItem(category, rawValues), 'manual');
        const name = validation.displayName || getKnowledgeItemDisplayName(newItem, category);

        newItem.id = Date.now().toString();
        newItem.created_at = new Date().toISOString();
        if (!newItem.description) {
            newItem.description = buildKnowledgeItemSummary(newItem, category);
        }

        if (!store.projectData[category.key]) {
            store.projectData[category.key] = [];
        }
        store.projectData[category.key].push(newItem);

        // 等待保存完成
        await saveSettingData(category.key);

        modal.classList.add('hidden');
        modal.innerHTML = '';
        showToast(`「${name}」已创建`);

        // 刷新右侧工作区
        loadDatabase(currentSettingType);

        // 刷新左侧导航面板
        renderKnowledgeNavPanel();
        if (store.currentModule === 'write' && window.renderMultiAgentWriteNavPanel) {
            window.renderMultiAgentWriteNavPanel();
        }
    });

    // 回车确认
    document.getElementById('new-setting-freeform-title')?.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') {
            document.getElementById('confirm-add-setting').click();
        }
    });
    document.getElementById('new-setting-template-name')?.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') {
            document.getElementById('confirm-add-setting').click();
        }
    });
    document.getElementById('new-setting-template-title')?.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') {
            document.getElementById('confirm-add-setting').click();
        }
    });
}

async function loadDatabase(typeId) {
    currentSettingType = typeId;

    // 从资料库分类中查找配置
    const category = store.knowledgeCategories.find(c => c.id === typeId);
    if (!category) return;

    updateBreadcrumbs(['资料库', category.name]);

    const data = getKnowledgeCategoryData(category);
    const visibleData = getKnowledgeFilteredItems(data);
    const isReadOnlyOutline = category.key === 'outline';

    if (data.length === 0) {
        ui.workspace.innerHTML = `
            <div style="display: flex; flex-direction: column; align-items: center; justify-content: center; height: 100%; color: var(--text-secondary);">
                <i class="${category.icon}" style="font-size: 48px; opacity: 0.3; margin-bottom: 16px;"></i>
                <p>暂无${category.name}内容</p>
                <button id="add-first-setting" style="margin-top: 20px; padding: 10px 24px; background: var(--accent-color); border: none; color: white; border-radius: 8px; cursor: pointer;">
                    <i class="ri-add-line"></i> 添加第一条${category.name}
                </button>
            </div>
        `;
        document.getElementById('add-first-setting').addEventListener('click', addNewSetting);
        return;
    }

    ui.workspace.innerHTML = `
        <div style="padding: 24px;">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px;">
                <div style="display: flex; align-items: center; gap: 12px;">
                    <h2 style="color: var(--text-primary); font-size: 18px;">${category.name} (${visibleData.length}/${data.length})</h2>
                    <label style="display: ${isReadOnlyOutline ? 'none' : 'flex'}; align-items: center; gap: 6px; cursor: pointer; font-size: 13px; color: var(--text-secondary);">
                        <input type="checkbox" id="select-all-items" style="cursor: pointer; accent-color: var(--accent-color);">
                        全选
                    </label>
                </div>
                <div style="display: flex; align-items: center; gap: 8px;">
                    <button id="batch-delete-btn" style="padding: 8px 16px; background: #ef4444; border: none; color: white; border-radius: 6px; cursor: pointer; font-size: 13px; display: none;">
                        <i class="ri-delete-bin-line"></i> 批量删除 (<span id="batch-delete-count">0</span>)
                    </button>
                    <button id="add-new-item-btn" style="display: ${isReadOnlyOutline ? 'none' : 'inline-flex'}; padding: 8px 16px; background: var(--accent-color); border: none; color: white; border-radius: 6px; cursor: pointer; font-size: 13px;">
                        <i class="ri-add-line"></i> 添加条目
                    </button>
                </div>
            </div>
            ${renderKnowledgeSourceFilters(data)}
            <div class="card-grid" id="setting-grid" style="display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 16px;">
            </div>
        </div>
    `;

    document.getElementById('add-new-item-btn')?.addEventListener('click', addNewSetting);
    bindKnowledgeSourceFilters(typeId);

    const grid = document.getElementById('setting-grid');
    const selectedIndices = new Set();
    if (!visibleData.length) {
        grid.innerHTML = '<div style="grid-column:1/-1;text-align:center;padding:36px;color:var(--text-secondary);">当前来源筛选下暂无内容</div>';
        return;
    }

    function updateBatchUI() {
        const count = selectedIndices.size;
        const batchBtn = document.getElementById('batch-delete-btn');
        const countSpan = document.getElementById('batch-delete-count');
        if (batchBtn) batchBtn.style.display = count > 0 ? 'inline-flex' : 'none';
        if (countSpan) countSpan.textContent = count;
        const selectAllCb = document.getElementById('select-all-items');
        if (selectAllCb) selectAllCb.checked = count === visibleData.length && visibleData.length > 0;
    }

    document.getElementById('select-all-items')?.addEventListener('change', (e) => {
        const checked = e.target.checked;
        selectedIndices.clear();
        if (checked) visibleData.forEach(item => selectedIndices.add(data.indexOf(item)));
        grid.querySelectorAll('.item-checkbox').forEach(cb => { cb.checked = checked; });
        grid.querySelectorAll('.meta-card').forEach((card, i) => {
            card.style.outline = checked ? '2px solid var(--accent-color)' : 'none';
        });
        updateBatchUI();
    });

    document.getElementById('batch-delete-btn')?.addEventListener('click', async () => {
        const count = selectedIndices.size;
        if (count === 0) return;
        const names = [...selectedIndices].map(i => getKnowledgeItemName(store.projectData[category.key][i], '')).filter(Boolean);
        const preview = names.length <= 5 ? names.map(n => `「${n}」`).join('、') : names.slice(0, 5).map(n => `「${n}」`).join('、') + ` 等${names.length}条`;
        if (!(await window.showConfirmDialog(`确定要删除 ${preview} 吗？共 ${count} 条`))) return;
        const sorted = [...selectedIndices].sort((a, b) => b - a);
        sorted.forEach(i => store.projectData[category.key].splice(i, 1));
        await saveSettingData(category.key);
        loadDatabase(typeId);
        renderKnowledgeNavPanel();
        if (store.currentModule === 'write' && window.renderMultiAgentWriteNavPanel) {
            window.renderMultiAgentWriteNavPanel();
        }
        showToast(`已删除 ${count} 条`);
    });

    visibleData.forEach((item) => {
        const index = data.indexOf(item);
        const card = document.createElement('div');
        card.className = 'meta-card';
        card.style.cssText = 'padding: 20px; cursor: pointer; position: relative;';
        card.innerHTML = `
            <div style="display: flex; justify-content: space-between; align-items: start; margin-bottom: 12px;">
                <div style="display: flex; align-items: start; gap: 10px; flex: 1; min-width: 0;">
                    <input type="checkbox" class="item-checkbox" data-index="${index}" style="display: ${isReadOnlyOutline ? 'none' : 'inline-block'}; cursor: pointer; margin-top: 3px; accent-color: var(--accent-color); flex-shrink: 0;">
                    <div style="font-weight: 600; font-size: 15px; color: var(--text-primary); overflow: hidden; text-overflow: ellipsis;">${getKnowledgeItemName(item)}</div>
                </div>
                <div class="card-actions" style="display: flex; gap: 4px; flex-shrink: 0;">
                    <button class="edit-card-btn" title="编辑" style="background: none; border: none; color: var(--text-secondary); cursor: pointer; padding: 4px;">
                        <i class="ri-edit-line"></i>
                    </button>
                    <button class="delete-card-btn" title="删除" style="display: ${isReadOnlyOutline ? 'none' : 'inline-block'}; background: none; border: none; color: #ef4444; cursor: pointer; padding: 4px;">
                        <i class="ri-delete-bin-line"></i>
                    </button>
                </div>
            </div>
            <div style="font-size: 13px; color: var(--text-secondary); line-height: 1.6; max-height: 60px; overflow: hidden;">
                ${buildKnowledgeItemSummary(item, category)}
            </div>
            <div style="margin-top:10px;font-size:11px;color:var(--text-secondary);">
                ${KNOWLEDGE_SOURCE_LABELS[getKnowledgeItemSourceMode(item)] || '未标记'}
            </div>
        `;

        card.querySelector('.item-checkbox')?.addEventListener('change', (e) => {
            e.stopPropagation();
            if (e.target.checked) {
                selectedIndices.add(index);
                card.style.outline = '2px solid var(--accent-color)';
            } else {
                selectedIndices.delete(index);
                card.style.outline = 'none';
            }
            updateBatchUI();
        });

        card.addEventListener('click', (e) => {
            if (!e.target.closest('.card-actions') && !e.target.closest('.item-checkbox')) {
                openSettingEditor(typeId, index);
            }
        });

        card.querySelector('.edit-card-btn').addEventListener('click', (e) => {
            e.stopPropagation();
            openSettingEditor(typeId, index);
        });

        card.querySelector('.delete-card-btn')?.addEventListener('click', (e) => {
            e.stopPropagation();
            deleteSetting(typeId, index);
        });

        grid.appendChild(card);
    });
}

function openSettingEditor(typeId, index) {
    // 从资料库分类中查找配置
    const category = store.knowledgeCategories.find(c => c.id === typeId);
    if (!category) return;
    const templateFields = getKnowledgeTemplateFields(category);
    const freeformFields = getKnowledgeFreeformFields(category);

    const data = getKnowledgeCategoryData(category);
    const item = data[index];
    if (!item) return;
    const isReadOnlyOutline = category.key === 'outline' && item.readonly;
    const initialMode = item.manual_mode === 'freeform' ? 'freeform' : 'template';
    const freeformItem = {
        title: item.title || item.name || getKnowledgeItemName(item, ''),
        content: item.content || item.raw_content || item.summary || item.summary_text || item.description || item.details || '',
        notes: item.notes || '',
    };

    updateBreadcrumbs(['资料库', category.name, getKnowledgeItemName(item)]);

    ui.workspace.innerHTML = `
        <div style="max-width: 800px; margin: 0 auto; padding: 24px;">
            <div class="app-back-row" style="justify-content: space-between; margin-bottom: 24px;">
                <button id="back-to-list" type="button" class="app-back-button">
                    <i class="ri-arrow-left-line"></i>
                    <span>返回列表</span>
                </button>
                <button id="save-setting-btn" style="padding: 8px 20px; background: var(--accent-color); border: none; color: white; border-radius: 6px; cursor: pointer;">
                    <i class="${isReadOnlyOutline ? 'ri-arrow-left-line' : 'ri-save-line'}"></i> ${isReadOnlyOutline ? '返回' : '保存'}
                </button>
            </div>

            <div style="background: rgba(255,255,255,0.03); border: 1px solid var(--border-color); border-radius: 12px; padding: 24px;">
                <div style="display:${isReadOnlyOutline ? 'none' : 'flex'}; gap:8px; margin-bottom:20px;">
                    <label style="flex:1; cursor:pointer;">
                        <input type="radio" name="setting-mode" value="freeform" ${initialMode === 'freeform' ? 'checked' : ''} style="accent-color: var(--accent-color);">
                        <span style="margin-left:6px; color:var(--text-primary);">自由内容</span>
                    </label>
                    <label style="flex:1; cursor:pointer;">
                        <input type="radio" name="setting-mode" value="template" ${initialMode === 'template' ? 'checked' : ''} style="accent-color: var(--accent-color);">
                        <span style="margin-left:6px; color:var(--text-primary);">结构化模板</span>
                    </label>
                </div>
                <div id="setting-freeform-section">
                    ${freeformFields.map(field => buildSchemaFieldHtml(field, freeformItem[field.key], 'setting-freeform')).join('')}
                </div>
                <div id="setting-template-section">
                    ${templateFields.map(field => buildSchemaFieldHtml(field, item[field.key], 'setting-template')).join('')}
                </div>
            </div>
        </div>
    `;

    document.getElementById('back-to-list').addEventListener('click', () => loadDatabase(typeId));

    function syncModeSections() {
        const mode = document.querySelector('input[name="setting-mode"]:checked')?.value || initialMode;
        const freeformSection = document.getElementById('setting-freeform-section');
        const templateSection = document.getElementById('setting-template-section');
        if (freeformSection) freeformSection.style.display = mode === 'freeform' ? '' : 'none';
        if (templateSection) templateSection.style.display = mode === 'template' ? '' : 'none';
    }
    document.querySelectorAll('input[name="setting-mode"]').forEach(input => {
        input.addEventListener('change', syncModeSections);
    });
    syncModeSections();

    document.getElementById('save-setting-btn').addEventListener('click', async () => {
        if (isReadOnlyOutline) {
            loadDatabase(typeId);
            return;
        }
        const mode = document.querySelector('input[name="setting-mode"]:checked')?.value || initialMode;
        const activeFields = mode === 'template' ? templateFields : freeformFields;
        const rawValues = collectSchemaFormValues(
            activeFields,
            mode === 'template' ? 'setting-template' : 'setting-freeform'
        );
        const validation = validateKnowledgeValues(activeFields, rawValues, category, mode);
        if (!validation.ok) {
            showToast(validation.message, 'error');
            return;
        }
        const nextValues = mode === 'template'
            ? ensureKnowledgeSourceTag({ ...rawValues, manual_mode: 'template' }, 'manual')
            : ensureKnowledgeSourceTag(buildFreeformKnowledgeItem(category, rawValues), 'manual');
        const name = validation.displayName || getKnowledgeItemDisplayName(nextValues, category);

        store.projectData[category.key][index] = {
            ...store.projectData[category.key][index],
            ...nextValues,
            description: nextValues.description || buildKnowledgeItemSummary(nextValues, category),
        };
        store.projectData[category.key][index] = ensureKnowledgeSourceTag(store.projectData[category.key][index], 'manual');
        store.projectData[category.key][index].updated_at = new Date().toISOString();

        await saveSettingData(category.key);
        showToast(`「${name}」已保存`);
        loadDatabase(typeId);
        renderKnowledgeNavPanel();
        if (store.currentModule === 'write' && window.renderMultiAgentWriteNavPanel) {
            window.renderMultiAgentWriteNavPanel();
        }
    });
}

async function deleteSetting(typeId, index) {
    // 从资料库分类中查找配置
    const category = store.knowledgeCategories.find(c => c.id === typeId);
    if (!category) return;
    if (category.key === 'outline') {
        showToast('全书大纲总览不能在这里删除；单章目标请在章纲设定中管理。', 'info');
        return;
    }

    const item = store.projectData[category.key][index];
    if (!item) return;

    if (await window.showConfirmDialog(`确定要删除「${getKnowledgeItemName(item)}」吗？`)) {
        store.projectData[category.key].splice(index, 1);
        await saveSettingData(category.key);
        loadDatabase(typeId);
        renderKnowledgeNavPanel();
        if (store.currentModule === 'write' && window.renderMultiAgentWriteNavPanel) {
            window.renderMultiAgentWriteNavPanel();
        }
        showToast(`已删除`);
    }
}

async function saveSettingData(dataKey) {
    if (Array.isArray(store.projectData[dataKey])) {
        store.projectData[dataKey] = store.projectData[dataKey].map(item => {
            if (!item || typeof item !== 'object') return item;
            if (getKnowledgeItemSourceMode(item) !== 'unknown') return item;
            return ensureKnowledgeSourceTag(item, item.source_file ? 'manual_import' : 'manual');
        });
    }

    if (isServerBackedKnowledgeKey(dataKey)) {
        // 服务器存储
        try {
            await apiCall(`/api/project-data/${dataKey}`, 'POST', {
                data: store.projectData[dataKey]
            });
            if (isServerBackedCustomKnowledgeKey(dataKey)) {
                saveExtendedKnowledgeData(dataKey);
            }
        } catch (e) {
            console.error(`Failed to save ${dataKey}:`, e);
            if (isServerBackedCustomKnowledgeKey(dataKey)) {
                saveExtendedKnowledgeData(dataKey);
            }
        }
    } else {
        // 本地存储（扩展资料库）
        saveExtendedKnowledgeData(dataKey);
    }

    // 更新@引用数据
    updateMentionData();

    // 刷新左侧导航面板的计数
    if (typeof renderKnowledgeNavPanel === 'function') {
        renderKnowledgeNavPanel();
    }

    // 如果当前在多Agent创作模式，也刷新其导航面板
    if (store.currentModule === 'write' && typeof window.renderMultiAgentWriteNavPanel === 'function') {
        window.renderMultiAgentWriteNavPanel();
    }
}

// 加载扩展资料库数据
function getExtendedKnowledgeProjectId() {
    if (typeof getActiveProjectId === 'function') {
        return getActiveProjectId() || 'default';
    }
    return store.currentProjectId || 'default';
}

function loadExtendedKnowledgeData() {
    const projectId = getExtendedKnowledgeProjectId();

    // 仅加载自定义分类数据。内置资料库统一走项目后端接口。
    store.knowledgeCategories.filter(c => !c.builtin).forEach(cat => {
        if (Array.isArray(store.projectData[cat.key]) && store.projectData[cat.key].length > 0) {
            return;
        }
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

// 保存扩展资料库数据
function saveExtendedKnowledgeData(key) {
    const projectId = getExtendedKnowledgeProjectId();
    try {
        localStorage.setItem(`knowledge_${projectId}_${key}`, JSON.stringify(store.projectData[key] || []));
    } catch (e) {
        console.error(`Failed to save ${key}:`, e);
    }
}

// ===== 文件导入功能 =====

function showImportFileDialog() {
    const modal = document.getElementById('modal-container');
    modal.classList.remove('hidden');

    // 获取所有分类用于选择
    const categories = store.knowledgeCategories || [];

    modal.innerHTML = `
        <div style="position: fixed; top: 0; left: 0; right: 0; bottom: 0; background: rgba(0,0,0,0.6); display: flex; align-items: center; justify-content: center; z-index: 1000;">
            <div style="background: var(--bg-panel); border: 1px solid var(--border-color); border-radius: 16px; padding: 30px; width: 600px; max-width: 95%; max-height: 90vh; overflow-y: auto;">
                <h3 style="color: var(--text-primary); margin-bottom: 24px; font-size: 18px;">
                    <i class="ri-file-upload-line" style="margin-right: 8px; color: var(--accent-color);"></i>
                    导入文件到资料库
                </h3>

                <div style="margin-bottom: 20px;">
                    <label style="display: block; font-size: 13px; color: var(--text-secondary); margin-bottom: 8px;">
                        选择文件 <span style="color: #ef4444;">*</span>
                        <span style="font-size: 11px; color: var(--text-secondary); margin-left: 8px;">支持 .txt, .md 格式（UTF-8编码）</span>
                    </label>
                    <div id="file-drop-zone" style="border: 2px dashed var(--border-color); border-radius: 12px; padding: 40px; text-align: center; cursor: pointer; transition: all 0.3s;">
                        <input type="file" id="import-file-input" accept=".txt,.md" style="display: none;" multiple>
                        <i class="ri-file-text-line" style="font-size: 48px; color: var(--text-secondary); opacity: 0.5;"></i>
                        <p style="color: var(--text-secondary); margin-top: 12px;">点击选择文件或拖拽到此处</p>
                        <p id="selected-files-info" style="color: var(--accent-color); margin-top: 8px; font-size: 13px;"></p>
                    </div>
                </div>

                <div style="margin-bottom: 20px;">
                    <label style="display: block; font-size: 13px; color: var(--text-secondary); margin-bottom: 8px;">
                        导入到分类 <span style="color: #ef4444;">*</span>
                    </label>
                    <div style="display: flex; gap: 10px;">
                        <select id="import-target-category" style="flex: 1; background: rgba(0,0,0,0.3); border: 1px solid var(--border-color); padding: 12px; color: var(--text-primary); border-radius: 8px; font-size: 14px;">
                            <option value="">-- 选择现有分类 --</option>
                            ${categories.map(cat => `<option value="${cat.id}" data-key="${cat.key}">${cat.name}</option>`).join('')}
                        </select>
                        <button id="create-new-category-btn" style="padding: 12px 16px; background: rgba(255,255,255,0.1); border: 1px solid var(--border-color); color: var(--text-primary); border-radius: 8px; cursor: pointer; white-space: nowrap;">
                            <i class="ri-add-line"></i> 新建分类
                        </button>
                    </div>
                    <div id="new-category-form" style="display: none; margin-top: 12px; padding: 16px; background: rgba(0,0,0,0.2); border-radius: 8px;">
                        <div style="display: flex; gap: 10px; margin-bottom: 12px;">
                            <input type="text" id="new-category-name-input" placeholder="输入新分类名称"
                                style="flex: 1; background: rgba(0,0,0,0.3); border: 1px solid var(--border-color); padding: 10px; color: var(--text-primary); border-radius: 6px; font-size: 13px;">
                            <button id="confirm-new-category" style="padding: 10px 16px; background: var(--accent-color); border: none; color: white; border-radius: 6px; cursor: pointer;">
                                <i class="ri-check-line"></i> 确定
                            </button>
                        </div>
                        <div style="display: flex; flex-wrap: wrap; gap: 8px;">
                            ${['ri-folder-line', 'ri-bookmark-line', 'ri-flag-line', 'ri-star-line', 'ri-map-pin-line', 'ri-lightbulb-line', 'ri-magic-line', 'ri-sword-line']
                                .map((icon, i) => `
                                    <div class="icon-option-small ${i === 0 ? 'selected' : ''}" data-icon="${icon}"
                                        style="width: 32px; height: 32px; display: flex; align-items: center; justify-content: center; border: 2px solid ${i === 0 ? 'var(--accent-color)' : 'var(--border-color)'}; border-radius: 6px; cursor: pointer;">
                                        <i class="${icon}" style="font-size: 14px;"></i>
                                    </div>
                                `).join('')}
                        </div>
                    </div>
                </div>

                <div style="margin-bottom: 20px;">
                    <label style="display: block; font-size: 13px; color: var(--text-secondary); margin-bottom: 8px;">
                        分割模式
                    </label>
                    <div style="display: flex; gap: 12px;">
                        <label style="display: flex; align-items: center; gap: 6px; cursor: pointer; padding: 10px 16px; background: rgba(0,0,0,0.2); border: 1px solid var(--border-color); border-radius: 8px;">
                            <input type="radio" name="split-mode" value="none" checked style="accent-color: var(--accent-color);">
                            <span style="color: var(--text-primary); font-size: 13px;">整文件</span>
                        </label>
                        <label style="display: flex; align-items: center; gap: 6px; cursor: pointer; padding: 10px 16px; background: rgba(0,0,0,0.2); border: 1px solid var(--border-color); border-radius: 8px;">
                            <input type="radio" name="split-mode" value="chapter" style="accent-color: var(--accent-color);">
                            <span style="color: var(--text-primary); font-size: 13px;">按章节</span>
                        </label>
                        <label style="display: flex; align-items: center; gap: 6px; cursor: pointer; padding: 10px 16px; background: rgba(0,0,0,0.2); border: 1px solid var(--border-color); border-radius: 8px;">
                            <input type="radio" name="split-mode" value="paragraph" style="accent-color: var(--accent-color);">
                            <span style="color: var(--text-primary); font-size: 13px;">按段落</span>
                        </label>
                    </div>
                    <p style="margin-top: 8px; font-size: 12px; color: var(--text-secondary);">
                        <i class="ri-information-line"></i> 整文件：一个文件作为一条资料；按章节：识别#标题或第X章自动分割；按段落：每个段落作为单独条目
                    </p>
                </div>

                <div style="display: flex; gap: 12px;">
                    <button id="cancel-import" style="flex: 1; padding: 12px; background: rgba(255,255,255,0.1); border: 1px solid var(--border-color); color: var(--text-primary); border-radius: 8px; cursor: pointer;">取消</button>
                    <button id="confirm-import" style="flex: 1; padding: 12px; background: var(--accent-color); border: none; color: white; border-radius: 8px; cursor: pointer; font-weight: 600;">
                        <i class="ri-upload-line"></i> 开始导入
                    </button>
                </div>
            </div>
        </div>
    `;

    let selectedFiles = [];
    let selectedIcon = 'ri-folder-line';
    let newCategoryCreated = null;

    const fileInput = document.getElementById('import-file-input');
    const dropZone = document.getElementById('file-drop-zone');
    const filesInfo = document.getElementById('selected-files-info');
    const categorySelect = document.getElementById('import-target-category');

    // 文件选择
    dropZone.addEventListener('click', () => fileInput.click());

    fileInput.addEventListener('change', (e) => {
        selectedFiles = Array.from(e.target.files);
        updateFilesInfo();
    });

    // 拖拽支持
    dropZone.addEventListener('dragover', (e) => {
        e.preventDefault();
        dropZone.style.borderColor = 'var(--accent-color)';
        dropZone.style.background = 'rgba(59,130,246,0.1)';
    });

    dropZone.addEventListener('dragleave', () => {
        dropZone.style.borderColor = 'var(--border-color)';
        dropZone.style.background = 'transparent';
    });

    dropZone.addEventListener('drop', (e) => {
        e.preventDefault();
        dropZone.style.borderColor = 'var(--border-color)';
        dropZone.style.background = 'transparent';

        const files = Array.from(e.dataTransfer.files).filter(f =>
            f.name.endsWith('.txt') || f.name.endsWith('.md')
        );
        if (files.length > 0) {
            selectedFiles = files;
            updateFilesInfo();
        } else {
            showToast('请选择 .txt 或 .md 文件', 'error');
        }
    });

    function updateFilesInfo() {
        if (selectedFiles.length > 0) {
            filesInfo.innerHTML = `已选择 ${selectedFiles.length} 个文件: ${selectedFiles.map(f => f.name).join(', ')}`;
        } else {
            filesInfo.innerHTML = '';
        }
    }

    // 新建分类
    const newCategoryBtn = document.getElementById('create-new-category-btn');
    const newCategoryForm = document.getElementById('new-category-form');

    newCategoryBtn.addEventListener('click', () => {
        newCategoryForm.style.display = newCategoryForm.style.display === 'none' ? 'block' : 'none';
    });

    // 图标选择
    document.querySelectorAll('.icon-option-small').forEach(opt => {
        opt.addEventListener('click', () => {
            document.querySelectorAll('.icon-option-small').forEach(o => {
                o.style.borderColor = 'var(--border-color)';
                o.classList.remove('selected');
            });
            opt.style.borderColor = 'var(--accent-color)';
            opt.classList.add('selected');
            selectedIcon = opt.dataset.icon;
        });
    });

    // 确认新建分类
    document.getElementById('confirm-new-category').addEventListener('click', async () => {
        const name = document.getElementById('new-category-name-input').value.trim();
        if (!name) {
            showToast('请输入分类名称', 'error');
            return;
        }

        // 创建分类
        newCategoryCreated = addKnowledgeCategory(name, selectedIcon);

        // 刷新下拉框
        const updatedCategories = store.knowledgeCategories || [];
        categorySelect.innerHTML = '<option value="">-- 选择现有分类 --</option>' +
            updatedCategories.map(cat => `<option value="${cat.id}" data-key="${cat.key}">${cat.name}</option>`).join('');

        // 选中新建的分类
        const newCat = updatedCategories.find(c => c.name === name);
        if (newCat) {
            categorySelect.value = newCat.id;
        }

        newCategoryForm.style.display = 'none';
        showToast(`分类「${name}」已创建`);
    });

    // 取消
    document.getElementById('cancel-import').addEventListener('click', () => {
        modal.classList.add('hidden');
        modal.innerHTML = '';
    });

    // 确认导入
    document.getElementById('confirm-import').addEventListener('click', async () => {
        if (selectedFiles.length === 0) {
            showToast('请选择要导入的文件', 'error');
            return;
        }

        const categoryId = categorySelect.value;
        if (!categoryId) {
            showToast('请选择目标分类', 'error');
            return;
        }

        const category = store.knowledgeCategories.find(c => c.id === categoryId);
        if (!category) {
            showToast('分类不存在', 'error');
            return;
        }

        const splitMode = document.querySelector('input[name="split-mode"]:checked').value;

        const btn = document.getElementById('confirm-import');
        btn.disabled = true;
        btn.innerHTML = '<i class="ri-loader-4-line"></i> 导入中...';

        try {
            let totalImported = 0;

            for (const file of selectedFiles) {
                // 读取文件内容
                const content = await readFileAsText(file);

                // 调用后端API解析
                const result = await apiCall('/api/knowledge-base/import-file', 'POST', {
                    content: content,
                    filename: file.name,
                    category_id: categoryId,
                    category_key: category.key,
                    split_mode: splitMode
                });

                if (result.success && result.items && result.items.length > 0) {
                    // 添加到本地数据
                    if (!store.projectData[category.key]) {
                        store.projectData[category.key] = [];
                    }
                    store.projectData[category.key].push(...(result.items || []).map(item => ensureKnowledgeSourceTag(item, 'manual_import')));
                    totalImported += result.items.length;
                }
            }

            // 保存数据
            saveSettingData(category.key);

            modal.classList.add('hidden');
            modal.innerHTML = '';

            showToast(`成功导入 ${totalImported} 条资料`, 'success');

            // 刷新显示
            renderKnowledgeNavPanel();
            if (currentSettingType === categoryId) {
                loadDatabase(categoryId);
            }
            if (store.currentModule === 'write' && window.renderMultiAgentWriteNavPanel) {
                window.renderMultiAgentWriteNavPanel();
            }

        } catch (e) {
            showToast('导入失败: ' + e.message, 'error');
        } finally {
            btn.disabled = false;
            btn.innerHTML = '<i class="ri-upload-line"></i> 开始导入';
        }
    });
}

// 读取文件为文本
function readFileAsText(file) {
    return new Promise((resolve, reject) => {
        const reader = new FileReader();
        reader.onload = (e) => resolve(e.target.result);
        reader.onerror = () => reject(new Error('读取文件失败'));
        reader.readAsText(file, 'UTF-8');
    });
}

// 修改renderKnowledgeNavPanel添加导入按钮
const originalRenderKnowledgeNavPanel = renderKnowledgeNavPanel;
renderKnowledgeNavPanel = function(options = {}) {
    originalRenderKnowledgeNavPanel(options);

    // 在添加新资料库按钮之前插入导入按钮
    const addBtn = ui.navList.querySelector('.list-item:last-child');
    const hasImportBtn = ui.navList.querySelector('.knowledge-import-entry');
    if (addBtn && !hasImportBtn) {
        const importBtn = document.createElement('div');
        importBtn.className = 'list-item knowledge-import-entry';
        importBtn.style.cssText = 'color: #10b981; border: 1px dashed rgba(16,185,129,0.5); border-radius: 8px; margin-bottom: 8px;';
        importBtn.innerHTML = `
            <i class="ri-file-upload-line"></i>
            <span>导入文件</span>
        `;
        importBtn.addEventListener('click', showImportFileDialog);
        ui.navList.insertBefore(importBtn, addBtn);
    }
};

// 全局暴露资料库函数
window.renderKnowledgeNavPanel = renderKnowledgeNavPanel;
window.showAddKnowledgeCategoryDialog = showAddKnowledgeCategoryDialog;
window.addKnowledgeCategory = addKnowledgeCategory;
window.deleteKnowledgeCategory = deleteKnowledgeCategory;
window.saveKnowledgeCategories = saveKnowledgeCategories;
window.syncKnowledgeCategoriesToProjectState = syncKnowledgeCategoriesToProjectState;
window.loadKnowledgeCategories = loadKnowledgeCategories;
window.isServerBackedCustomKnowledgeKey = isServerBackedCustomKnowledgeKey;
window.isServerBackedKnowledgeKey = isServerBackedKnowledgeKey;
window.addNewSetting = addNewSetting;
window.showAddSettingDialog = showAddSettingDialog;
window.loadDatabase = loadDatabase;
window.openSettingEditor = openSettingEditor;
window.deleteSetting = deleteSetting;
window.saveSettingData = saveSettingData;
window.loadExtendedKnowledgeData = loadExtendedKnowledgeData;
window.saveExtendedKnowledgeData = saveExtendedKnowledgeData;
window.showImportFileDialog = showImportFileDialog;
window.renderKnowledgeGraphView = renderKnowledgeGraphView;
window.renderKnowledgeWorkbench = renderKnowledgeWorkbench;
window.getKnowledgeItemSourceMode = getKnowledgeItemSourceMode;
window.getKnowledgeFilteredItems = getKnowledgeFilteredItems;

console.log('[app-knowledge.js] 资料库模块已加载');

