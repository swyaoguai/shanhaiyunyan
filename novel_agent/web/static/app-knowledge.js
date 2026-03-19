/**
 * 文思Agent - 资料库管理模块
 * 包含：资料库分类、知识条目CRUD、设定管理
 */

// ===== 资料库导航面板 =====

function renderKnowledgeNavPanel() {
    ui.navList.innerHTML = '';
    
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
        div.addEventListener('click', () => {
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
    
    // 添加新资料库按钮
    const addBtn = document.createElement('div');
    addBtn.className = 'list-item';
    addBtn.style.cssText = 'margin-top: 12px; color: var(--accent-color); border: 1px dashed var(--border-color); border-radius: 8px;';
    addBtn.innerHTML = `
        <i class="ri-add-line"></i>
        <span>添加新资料库</span>
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

// ===== 设定管理功能 =====

let currentSettingType = null;

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
    
    modal.innerHTML = `
        <div style="position: fixed; top: 0; left: 0; right: 0; bottom: 0; background: rgba(0,0,0,0.6); display: flex; align-items: center; justify-content: center; z-index: 1000;">
            <div style="background: var(--bg-panel); border: 1px solid var(--border-color); border-radius: 16px; padding: 30px; width: 500px; max-width: 90%;">
                <h3 style="color: var(--text-primary); margin-bottom: 24px; font-size: 18px;">
                    <i class="${category.icon}" style="margin-right: 8px;"></i>
                    添加${category.name}
                </h3>
                
                <div style="margin-bottom: 20px;">
                    <label style="display: block; font-size: 13px; color: var(--text-secondary); margin-bottom: 8px;">名称 <span style="color: #ef4444;">*</span></label>
                    <input type="text" id="new-setting-name" placeholder="例如：林逸风、仙灵剑..."
                        style="width: 100%; background: rgba(0,0,0,0.3); border: 1px solid var(--border-color); padding: 12px; color: var(--text-primary); border-radius: 8px; font-size: 14px;">
                </div>
                
                <div style="margin-bottom: 24px;">
                    <label style="display: block; font-size: 13px; color: var(--text-secondary); margin-bottom: 8px;">描述</label>
                    <textarea id="new-setting-description" rows="4" placeholder="简要描述..."
                        style="width: 100%; background: rgba(0,0,0,0.3); border: 1px solid var(--border-color); padding: 12px; color: var(--text-primary); border-radius: 8px; font-size: 14px; resize: vertical;"></textarea>
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
        document.getElementById('new-setting-name').focus();
    }, 100);
    
    // 取消
    document.getElementById('cancel-add-setting').addEventListener('click', () => {
        modal.classList.add('hidden');
        modal.innerHTML = '';
    });
    
    // 确认
    document.getElementById('confirm-add-setting').addEventListener('click', () => {
        const name = document.getElementById('new-setting-name').value.trim();
        const description = document.getElementById('new-setting-description').value.trim();
        
        if (!name) {
            showToast('请输入名称', 'error');
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
        showToast(`「${name}」已创建`);
        
        // 刷新并打开编辑器
        loadDatabase(currentSettingType);
    });
    
    // 回车确认
    document.getElementById('new-setting-name').addEventListener('keydown', (e) => {
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
                <h2 style="color: var(--text-primary); font-size: 18px;">${category.name} (${data.length})</h2>
                <button id="add-new-item-btn" style="padding: 8px 16px; background: var(--accent-color); border: none; color: white; border-radius: 6px; cursor: pointer; font-size: 13px;">
                    <i class="ri-add-line"></i> 添加条目
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
                    <button class="edit-card-btn" title="编辑" style="background: none; border: none; color: var(--text-secondary); cursor: pointer; padding: 4px;">
                        <i class="ri-edit-line"></i>
                    </button>
                    <button class="delete-card-btn" title="删除" style="background: none; border: none; color: #ef4444; cursor: pointer; padding: 4px;">
                        <i class="ri-delete-bin-line"></i>
                    </button>
                </div>
            </div>
            <div style="font-size: 13px; color: var(--text-secondary); line-height: 1.6; max-height: 60px; overflow: hidden;">
                ${item.description || '暂无描述，点击编辑添加'}
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
    // 从资料库分类中查找配置
    const category = store.knowledgeCategories.find(c => c.id === typeId);
    if (!category) return;

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
                <div style="margin-bottom: 20px;">
                    <label style="display: block; font-size: 12px; color: var(--text-secondary); margin-bottom: 8px;">名称</label>
                    <input type="text" id="setting-name" value="${item.name || ''}"
                        style="width: 100%; background: rgba(0,0,0,0.2); border: 1px solid var(--border-color); padding: 12px; color: var(--text-primary); border-radius: 8px; font-size: 16px;">
                </div>
                
                <div style="margin-bottom: 20px;">
                    <label style="display: block; font-size: 12px; color: var(--text-secondary); margin-bottom: 8px;">描述</label>
                    <textarea id="setting-description" rows="4"
                        style="width: 100%; background: rgba(0,0,0,0.2); border: 1px solid var(--border-color); padding: 12px; color: var(--text-primary); border-radius: 8px; font-size: 14px; resize: vertical;">${item.description || ''}</textarea>
                </div>
                
                <div>
                    <label style="display: block; font-size: 12px; color: var(--text-secondary); margin-bottom: 8px;">详细信息</label>
                    <textarea id="setting-details" rows="8" placeholder="在这里添加更多详细信息..."
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
        showToast(`「${name}」已保存`);
        loadDatabase(typeId);
    });
}

function deleteSetting(typeId, index) {
    // 从资料库分类中查找配置
    const category = store.knowledgeCategories.find(c => c.id === typeId);
    if (!category) return;

    const item = store.projectData[category.key][index];
    if (!item) return;

    if (confirm(`确定要删除「${item.name}」吗？`)) {
        store.projectData[category.key].splice(index, 1);
        saveSettingData(category.key);
        loadDatabase(typeId);
        showToast(`已删除`);
    }
}

async function saveSettingData(dataKey) {
    // 判断是否是扩展资料库（本地存储）
    const builtinServerKeys = ['characters', 'outline', 'worldbuilding', 'items'];
    
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
}

// 加载扩展资料库数据
function getExtendedKnowledgeProjectId() {
    return store.currentProject || store.currentProjectId || 'default';
}

function loadExtendedKnowledgeData() {
    const projectId = getExtendedKnowledgeProjectId();
    
    // 加载内置扩展分类
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
    
    // 加载自定义分类数据
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
renderKnowledgeNavPanel = function() {
    originalRenderKnowledgeNavPanel();
    
    // 在添加新资料库按钮之前插入导入按钮
    const addBtn = ui.navList.querySelector('.list-item:last-child');
    if (addBtn) {
        const importBtn = document.createElement('div');
        importBtn.className = 'list-item';
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

console.log('[app-knowledge.js] 资料库模块已加载');

