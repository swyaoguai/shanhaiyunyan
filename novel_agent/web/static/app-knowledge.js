/**
 * 文思Agent - 资料库管理模块
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
        const count = (store.projectData[cat.key] || []).length;
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

function deleteKnowledgeCategory(categoryId) {
    const category = store.knowledgeCategories.find(c => c.id === categoryId);
    if (!category) return;
    
    const count = (store.projectData[category.key] || []).length;
    
    if (confirm(`确定要删除资料库「${category.name}」吗？\n\n该分类下有 ${count} 条内容将被一并删除，此操作不可恢复！`)) {
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

// ===== 设定管理功能 =====

let currentSettingType = null;
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
        summaryKeys: ['summary', 'arc', 'key_turn'],
        fields: [
            { key: 'title', label: '章节标题', type: 'text', required: true },
            { key: 'summary', label: '章节概要', type: 'textarea', rows: 3 },
            { key: 'arc', label: '故事弧', type: 'text' },
            { key: 'key_turn', label: '关键转折', type: 'textarea', rows: 2 },
            { key: 'hook', label: '结尾钩子', type: 'textarea', rows: 2 },
        ],
    },
    characters: {
        summaryKeys: ['role', 'identity', 'personality', 'goals'],
        fields: [
            { key: 'name', label: '姓名', type: 'text', required: true },
            { key: 'role', label: '角色定位', type: 'select', options: ['主角', '配角', '反派', '导师', '盟友', '其他'] },
            { key: 'identity', label: '身份', type: 'text' },
            { key: 'description', label: '一句话简介', type: 'textarea', rows: 3 },
            { key: 'personality', label: '性格标签', type: 'list', placeholder: '每行一个，或用逗号分隔' },
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
        summaryKeys: ['item_type', 'owner', 'description'],
        fields: [
            { key: 'name', label: '名称', type: 'text', required: true },
            { key: 'item_type', label: '类别', type: 'select', options: ['未分类', '武器', '法宝', '道具', '装备', '资源', '线索', '其他'] },
            { key: 'description', label: '简介', type: 'textarea', rows: 3 },
            { key: 'details', label: '作用', type: 'textarea', rows: 3 },
            { key: 'owner', label: '当前持有者', type: 'text' },
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

function formatSchemaFieldValue(field, value) {
    if (value === null || value === undefined) return '';
    if (field.type === 'list') {
        return Array.isArray(value) ? value.join('\n') : String(value);
    }
    if (field.type === 'relation_map') {
        if (typeof value === 'string') return value;
        if (value && typeof value === 'object') {
            return Object.entries(value).map(([target, relation]) => `${target}：${relation}`).join('\n');
        }
    }
    return String(value);
}

function escapeAttributeValue(value) {
    return String(value ?? '')
        .replace(/&/g, '&amp;')
        .replace(/"/g, '&quot;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;');
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
    if (field.type === 'textarea' || field.type === 'list' || field.type === 'relation_map') {
        return `
            <div style="margin-bottom: 20px;">
                <label style="display: block; font-size: 12px; color: var(--text-secondary); margin-bottom: 8px;">${label}</label>
                <textarea id="${fieldId}" rows="${field.rows || 4}" placeholder="${placeholder}"
                    style="${commonStyle} resize: vertical; line-height: 1.6;">${renderedValue}</textarea>
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
        const text = Array.isArray(value) ? value.join('、') : (typeof value === 'object' ? JSON.stringify(value) : String(value));
        if (text.trim()) lines.push(text.trim());
        if (lines.length >= 3) break;
    }
    return lines.join('｜') || item.description || item.details || '暂无摘要，点击编辑补充结构化信息';
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
    const schema = getKnowledgeSchema(category);
    const fields = schema?.fields || [
        { key: 'name', label: '名称', type: 'text', required: true },
        { key: 'description', label: '描述', type: 'textarea', rows: 4 },
    ];
    
    modal.innerHTML = `
        <div style="position: fixed; top: 0; left: 0; right: 0; bottom: 0; background: rgba(0,0,0,0.6); display: flex; align-items: center; justify-content: center; z-index: 1000;">
            <div style="background: var(--bg-panel); border: 1px solid var(--border-color); border-radius: 16px; padding: 30px; width: 720px; max-width: 95%; max-height: 90vh; overflow-y: auto;">
                <h3 style="color: var(--text-primary); margin-bottom: 24px; font-size: 18px;">
                    <i class="${category.icon}" style="margin-right: 8px;"></i>
                    添加${category.name}
                </h3>
                ${fields.map(field => buildSchemaFieldHtml(field, '', 'new-setting')).join('')}
                
                <div style="display: flex; gap: 12px;">
                    <button id="cancel-add-setting" style="flex: 1; padding: 12px; background: rgba(255,255,255,0.1); border: 1px solid var(--border-color); color: var(--text-primary); border-radius: 8px; cursor: pointer;">取消</button>
                    <button id="confirm-add-setting" style="flex: 1; padding: 12px; background: var(--accent-color); border: none; color: white; border-radius: 8px; cursor: pointer; font-weight: 600;">创建</button>
                </div>
            </div>
        </div>
    `;
    
    // 自动聚焦输入框
    setTimeout(() => {
        document.getElementById('new-setting-name')?.focus();
    }, 100);
    
    // 取消
    document.getElementById('cancel-add-setting').addEventListener('click', () => {
        modal.classList.add('hidden');
        modal.innerHTML = '';
    });
    
    // 确认
    document.getElementById('confirm-add-setting').addEventListener('click', async () => {
        const newItem = collectSchemaFormValues(fields, 'new-setting');
        const name = String(newItem.name || '').trim();

        if (!name) {
            showToast('请输入名称', 'error');
            return;
        }

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
    document.getElementById('new-setting-name')?.addEventListener('keydown', (e) => {
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

    const data = store.projectData[category.key] || [];

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
                    <h2 style="color: var(--text-primary); font-size: 18px;">${category.name} (${data.length})</h2>
                    <label style="display: flex; align-items: center; gap: 6px; cursor: pointer; font-size: 13px; color: var(--text-secondary);">
                        <input type="checkbox" id="select-all-items" style="cursor: pointer; accent-color: var(--accent-color);">
                        全选
                    </label>
                </div>
                <div style="display: flex; align-items: center; gap: 8px;">
                    <button id="batch-delete-btn" style="padding: 8px 16px; background: #ef4444; border: none; color: white; border-radius: 6px; cursor: pointer; font-size: 13px; display: none;">
                        <i class="ri-delete-bin-line"></i> 批量删除 (<span id="batch-delete-count">0</span>)
                    </button>
                    <button id="add-new-item-btn" style="padding: 8px 16px; background: var(--accent-color); border: none; color: white; border-radius: 6px; cursor: pointer; font-size: 13px;">
                        <i class="ri-add-line"></i> 添加条目
                    </button>
                </div>
            </div>
            <div class="card-grid" id="setting-grid" style="display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 16px;">
            </div>
        </div>
    `;

    document.getElementById('add-new-item-btn').addEventListener('click', addNewSetting);

    const grid = document.getElementById('setting-grid');
    const selectedIndices = new Set();

    function updateBatchUI() {
        const count = selectedIndices.size;
        const batchBtn = document.getElementById('batch-delete-btn');
        const countSpan = document.getElementById('batch-delete-count');
        if (batchBtn) batchBtn.style.display = count > 0 ? 'inline-flex' : 'none';
        if (countSpan) countSpan.textContent = count;
        const selectAllCb = document.getElementById('select-all-items');
        if (selectAllCb) selectAllCb.checked = count === data.length && data.length > 0;
    }

    document.getElementById('select-all-items').addEventListener('change', (e) => {
        const checked = e.target.checked;
        selectedIndices.clear();
        if (checked) data.forEach((_, i) => selectedIndices.add(i));
        grid.querySelectorAll('.item-checkbox').forEach(cb => { cb.checked = checked; });
        grid.querySelectorAll('.meta-card').forEach((card, i) => {
            card.style.outline = checked ? '2px solid var(--accent-color)' : 'none';
        });
        updateBatchUI();
    });

    document.getElementById('batch-delete-btn').addEventListener('click', async () => {
        const count = selectedIndices.size;
        if (count === 0) return;
        const names = [...selectedIndices].map(i => store.projectData[category.key][i]?.name).filter(Boolean);
        const preview = names.length <= 5 ? names.map(n => `「${n}」`).join('、') : names.slice(0, 5).map(n => `「${n}」`).join('、') + ` 等${names.length}条`;
        if (!confirm(`确定要删除 ${preview} 吗？共 ${count} 条`)) return;
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

    data.forEach((item, index) => {
        const card = document.createElement('div');
        card.className = 'meta-card';
        card.style.cssText = 'padding: 20px; cursor: pointer; position: relative;';
        card.innerHTML = `
            <div style="display: flex; justify-content: space-between; align-items: start; margin-bottom: 12px;">
                <div style="display: flex; align-items: start; gap: 10px; flex: 1; min-width: 0;">
                    <input type="checkbox" class="item-checkbox" data-index="${index}" style="cursor: pointer; margin-top: 3px; accent-color: var(--accent-color); flex-shrink: 0;">
                    <div style="font-weight: 600; font-size: 15px; color: var(--text-primary); overflow: hidden; text-overflow: ellipsis;">${item.name}</div>
                </div>
                <div class="card-actions" style="display: flex; gap: 4px; flex-shrink: 0;">
                    <button class="edit-card-btn" title="编辑" style="background: none; border: none; color: var(--text-secondary); cursor: pointer; padding: 4px;">
                        <i class="ri-edit-line"></i>
                    </button>
                    <button class="delete-card-btn" title="删除" style="background: none; border: none; color: #ef4444; cursor: pointer; padding: 4px;">
                        <i class="ri-delete-bin-line"></i>
                    </button>
                </div>
            </div>
            <div style="font-size: 13px; color: var(--text-secondary); line-height: 1.6; max-height: 60px; overflow: hidden;">
                ${buildKnowledgeItemSummary(item, category)}
            </div>
        `;

        card.querySelector('.item-checkbox').addEventListener('change', (e) => {
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

        card.querySelector('.delete-card-btn').addEventListener('click', (e) => {
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
    const schema = getKnowledgeSchema(category);
    const fields = schema?.fields || [
        { key: 'name', label: '名称', type: 'text', required: true },
        { key: 'description', label: '描述', type: 'textarea', rows: 4 },
        { key: 'details', label: '详细信息', type: 'textarea', rows: 8 },
    ];

    const item = store.projectData[category.key][index];
    if (!item) return;

    updateBreadcrumbs(['资料库', category.name, item.name]);

    ui.workspace.innerHTML = `
        <div style="max-width: 800px; margin: 0 auto; padding: 24px;">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 24px;">
                <button id="back-to-list" style="background: none; border: none; color: var(--text-secondary); cursor: pointer; display: flex; align-items: center; gap: 8px;">
                    <i class="ri-arrow-left-line"></i> 返回列表
                </button>
                <button id="save-setting-btn" style="padding: 8px 20px; background: var(--accent-color); border: none; color: white; border-radius: 6px; cursor: pointer;">
                    <i class="ri-save-line"></i> 保存
                </button>
            </div>
            
            <div style="background: rgba(255,255,255,0.03); border: 1px solid var(--border-color); border-radius: 12px; padding: 24px;">
                ${fields.map(field => buildSchemaFieldHtml(field, item[field.key], 'setting')).join('')}
            </div>
        </div>
    `;

    document.getElementById('back-to-list').addEventListener('click', () => loadDatabase(typeId));

    document.getElementById('save-setting-btn').addEventListener('click', async () => {
        const nextValues = collectSchemaFormValues(fields, 'setting');
        const name = String(nextValues.name || '').trim();
        if (!name) {
            showToast('名称不能为空', 'error');
            return;
        }

        store.projectData[category.key][index] = {
            ...store.projectData[category.key][index],
            ...nextValues,
            description: nextValues.description || buildKnowledgeItemSummary(nextValues, category),
        };
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

    const item = store.projectData[category.key][index];
    if (!item) return;

    if (confirm(`确定要删除「${item.name}」吗？`)) {
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
    // 判断是否是扩展资料库（本地存储）
    const builtinServerKeys = ['characters', 'outline', 'worldbuilding', 'items', 'eventlines', 'detail_settings', 'chapter_settings', 'chapter_summary'];

    if (builtinServerKeys.includes(dataKey)) {
        // 服务器存储
        try {
            await apiCall(`/api/project-data/${dataKey}`, 'POST', {
                data: store.projectData[dataKey]
            });
        } catch (e) {
            console.error(`Failed to save ${dataKey}:`, e);
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
                    store.projectData[category.key].push(...result.items);
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

console.log('[app-knowledge.js] 资料库模块已加载');

