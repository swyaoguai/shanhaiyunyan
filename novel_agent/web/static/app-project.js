/**
 * 山海·云烟 - 项目管理模块
 * 包含：项目加载、切换、创建、导出
 */

// ===== 项目管理功能 =====

const PROJECT_GENRE_PRESETS = [
    '玄幻奇幻',
    '武侠仙侠',
    '科幻未来',
    '都市现代',
    '历史军事',
    '言情青春',
    '悬疑推理',
    '惊悚恐怖',
    '游戏竞技',
    '其他类型'
];

function getProjectGenreValue() {
    const customInput = document.getElementById('new-project-genre');
    const presetSelect = document.getElementById('new-project-genre-preset');
    const customValue = customInput?.value.trim() || '';
    const presetValue = presetSelect?.value || '';

    return customValue || (presetValue && presetValue !== '__custom__' ? presetValue : '');
}

function bindProjectGenreControls() {
    const customInput = document.getElementById('new-project-genre');
    const presetSelect = document.getElementById('new-project-genre-preset');
    if (!customInput || !presetSelect) return;

    presetSelect.addEventListener('change', () => {
        if (presetSelect.value === '__custom__') {
            customInput.focus();
            return;
        }
        customInput.value = '';
    });

    customInput.addEventListener('input', () => {
        const value = customInput.value.trim();
        presetSelect.value = value ? '__custom__' : '';
    });
}

function getActiveProjectId() {
    return store.currentProjectId || null;
}

function setActiveProjectId(projectId) {
    const normalizedProjectId = projectId || null;
    store.currentProjectId = normalizedProjectId;
    // 兼容旧代码读取，但主状态字段统一为 currentProjectId
    store.currentProject = normalizedProjectId;
}

function isCustomProjectDataKey(key) {
    if (typeof isServerBackedCustomKnowledgeKey === 'function') {
        return isServerBackedCustomKnowledgeKey(key);
    }
    return /^custom_[A-Za-z0-9_-]{1,80}$/.test(String(key || '').trim());
}

async function loadCustomProjectDataFromServer() {
    const categories = Array.isArray(store.knowledgeCategories) ? store.knowledgeCategories : [];
    const customCategories = categories.filter(cat => cat && !cat.builtin && isCustomProjectDataKey(cat.key));
    for (const cat of customCategories) {
        try {
            const response = await apiCall(`/api/project-data/${cat.key}`);
            store.projectData[cat.key] = Array.isArray(response.data) ? response.data : [];
        } catch (e) {
            if (!Array.isArray(store.projectData[cat.key])) {
                store.projectData[cat.key] = [];
            }
            console.warn(`Failed to load custom project data ${cat.key}:`, e);
        }
    }
}

async function loadProjects() {
    try {
        const data = await apiCall('/api/projects');
        store.projects = data.projects || [];
        // 后端返回的是 current_project_id，不是 current_project
        const currentProjectId = data.current_project_id || data.current_project || null;
        setActiveProjectId(currentProjectId);
        updateProjectSelector();
        if (currentProjectId && typeof loadCurrentProjectData === 'function') {
            await loadCurrentProjectData();
        }
    } catch (e) {
        console.error('Failed to load projects:', e);
        store.projects = [];
        // 加载失败时也要更新界面
        updateProjectSelector();
    }
}

function updateProjectSelector() {
    // 更新项目名称显示
    const projectNameEl = document.getElementById('current-project-name');
    
    const activeProjectId = getActiveProjectId();
    const currentProject = store.projects.find(p => p.id === activeProjectId);
    const projectName = currentProject ? currentProject.name : (store.projects.length > 0 ? '选择项目' : '无项目');
    
    // 更新全局状态中的项目名
    store.currentProjectName = projectName;
    
    if (projectNameEl) {
        projectNameEl.textContent = projectName;
    }
    
    // 兼容旧的 project-selector 元素（如果存在）
    const selector = document.getElementById('project-selector');
    if (selector) {
        selector.innerHTML = `
            <span style="max-width: 150px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">${escapeHtml(projectName)}</span>
            <i class="ri-arrow-down-s-line"></i>
        `;
    }
}

function toggleProjectDropdown() {
    let dropdown = document.getElementById('project-dropdown');
    const trigger = document.getElementById('project-current');
    
    if (dropdown && !dropdown.classList.contains('hidden')) {
        dropdown.classList.add('hidden');
        trigger?.setAttribute('aria-expanded', 'false');
        return;
    }
    
    if (!dropdown) {
        dropdown = document.createElement('div');
        dropdown.id = 'project-dropdown';
        dropdown.style.cssText = `
            position: absolute;
            top: 100%;
            left: 0;
            right: 0;
            background: var(--bg-panel);
            border: 1px solid var(--border-color);
            border-radius: 8px;
            box-shadow: 0 8px 32px rgba(0,0,0,0.3);
            max-height: 400px;
            overflow-y: auto;
            z-index: 100;
            margin-top: 4px;
        `;
        
        const container = document.getElementById('project-selector').parentElement;
        container.style.position = 'relative';
        container.appendChild(dropdown);
    }
    
    const activeProjectId = getActiveProjectId();
    dropdown.innerHTML = `
        <div style="padding: 8px;">
            <div style="padding: 8px 12px; color: var(--text-secondary); font-size: 12px; text-transform: uppercase; letter-spacing: 1px;">
                我的项目
            </div>
            ${store.projects.map(project => `
                <div class="project-item" data-id="${project.id}"
                    style="padding: 12px 16px; cursor: pointer; display: flex; align-items: center; gap: 12px; border-radius: 6px; transition: background 0.15s;
                    ${project.id === activeProjectId ? 'background: var(--accent-color);' : ''}">
                    <i class="ri-book-3-line" style="font-size: 18px; color: ${project.id === activeProjectId ? 'white' : 'var(--accent-color)'};"></i>
                    <div style="flex: 1; overflow: hidden;">
                        <div style="color: ${project.id === activeProjectId ? 'white' : 'var(--text-primary)'}; font-size: 14px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;">
                            ${escapeHtml(project.name)}
                        </div>
                        <div style="color: ${project.id === activeProjectId ? 'rgba(255,255,255,0.7)' : 'var(--text-secondary)'}; font-size: 12px;">
                            ${project.chapters_count || 0} 章 · ${project.word_count || 0} 字
                        </div>
                    </div>
                    ${project.id === activeProjectId ? '<i class="ri-check-line" style="color: white;"></i>' : ''}
                    <button class="delete-project-btn" data-id="${project.id}" data-name="${escapeHtml(project.name)}"
                        style="padding: 6px 8px; background: transparent; border: none; color: ${project.id === activeProjectId ? 'rgba(255,255,255,0.7)' : 'var(--text-secondary)'}; cursor: pointer; border-radius: 4px; transition: all 0.15s; opacity: 0.6;"
                        onmouseover="this.style.opacity='1'; this.style.background='rgba(239,68,68,0.2)'; this.style.color='#ef4444';"
                        onmouseout="this.style.opacity='0.6'; this.style.background='transparent'; this.style.color='${project.id === activeProjectId ? 'rgba(255,255,255,0.7)' : 'var(--text-secondary)'}';"
                        title="删除项目">
                        <i class="ri-delete-bin-line" style="font-size: 14px;"></i>
                    </button>
                </div>
            `).join('')}
            <div style="border-top: 1px solid var(--border-color); margin-top: 8px; padding-top: 8px;">
                <div id="create-project-btn" style="padding: 12px 16px; cursor: pointer; display: flex; align-items: center; gap: 12px; border-radius: 6px; transition: background 0.15s;">
                    <i class="ri-add-circle-line" style="font-size: 18px; color: var(--accent-color);"></i>
                    <span style="color: var(--text-primary); font-size: 14px;">创建新项目</span>
                </div>
            </div>
        </div>
    `;
    
    // 绑定项目切换事件
    dropdown.querySelectorAll('.project-item').forEach(item => {
        item.addEventListener('click', () => {
            switchProject(item.dataset.id);
            dropdown.classList.add('hidden');
        });
        item.addEventListener('mouseenter', () => {
            if (item.dataset.id !== activeProjectId) {
                item.style.background = 'rgba(255,255,255,0.1)';
            }
        });
        item.addEventListener('mouseleave', () => {
            if (item.dataset.id !== activeProjectId) {
                item.style.background = '';
            }
        });
    });
    
    // 绑定创建项目事件
    dropdown.querySelector('#create-project-btn').addEventListener('click', () => {
        dropdown.classList.add('hidden');
        showCreateProjectDialog();
    });
    
    // 绑定删除项目事件
    dropdown.querySelectorAll('.delete-project-btn').forEach(btn => {
        btn.addEventListener('click', (e) => {
            e.stopPropagation(); // 阻止冒泡，避免触发项目切换
            const projectId = btn.dataset.id;
            const projectName = btn.dataset.name;
            dropdown.classList.add('hidden');
            showDeleteProjectDialog(projectId, projectName);
        });
    });
    
    dropdown.classList.remove('hidden');
    trigger?.setAttribute('aria-expanded', 'true');
    
    // 点击外部关闭
    setTimeout(() => {
        document.addEventListener('click', function closeDropdown(e) {
            if (!dropdown.contains(e.target) && e.target.id !== 'project-selector') {
                dropdown.classList.add('hidden');
                trigger?.setAttribute('aria-expanded', 'false');
                document.removeEventListener('click', closeDropdown);
            }
        });
    }, 0);
}

async function switchProject(projectId) {
    if (projectId === getActiveProjectId()) return;
    
    try {
        showToast('正在切换项目...');
        
        await apiCall(`/api/projects/${projectId}/switch`, 'POST');
        setActiveProjectId(projectId);
        if (typeof markCopilotHistoryStale === 'function') {
            markCopilotHistoryStale(projectId);
        }
        
        // 重新加载项目数据
        await loadCurrentProjectData();
        
        updateProjectSelector();
        
        // 刷新当前视图
        if (typeof switchModule === 'function') {
            switchModule(store.currentModule || 'dashboard');
        }
        
        const project = store.projects.find(p => p.id === projectId);
        showToast(`已切换到「${project?.name || '新项目'}」`);
        
    } catch (e) {
        showToast('切换项目失败: ' + e.message, 'error');
    }
}

async function loadCurrentProjectData() {
    try {
        const activeProjectId = getActiveProjectId();
        if (!activeProjectId) {
            store.projectData = {
                outline: [],
                chapters: [],
                worldbuilding: [],
                characters: [],
                items: [],
                eventlines: [],
                outline_settings: [],
                detail_settings: [],
                chapter_settings: [],
                chapter_summary: []
            };
            if (typeof updateMentionData === 'function') {
                updateMentionData();
            }
            return;
        }

        // 加载大纲
        const outlineData = await apiCall('/api/project-data/outline');
        store.projectData.outline = outlineData.data || [];

        // 加载独立章节正文。大纲删除不应影响这里。
        const chaptersData = await apiCall('/api/project-data/chapters');
        store.projectData.chapters = Array.isArray(chaptersData.data) ? chaptersData.data : [];
        
        // 加载世界观
        const worldData = await apiCall('/api/project-data/worldbuilding');
        store.projectData.worldbuilding = Array.isArray(worldData.data) ? worldData.data : [];
        
        // 加载角色
        const charData = await apiCall('/api/project-data/characters');
        store.projectData.characters = charData.data || [];
        
        // 加载物品
        const itemData = await apiCall('/api/project-data/items');
        store.projectData.items = itemData.data || [];

        // 加载其他内置资料库
        const eventlineData = await apiCall('/api/project-data/eventlines');
        store.projectData.eventlines = Array.isArray(eventlineData.data) ? eventlineData.data : [];

        const detailSettingsData = await apiCall('/api/project-data/detail_settings');
        store.projectData.detail_settings = Array.isArray(detailSettingsData.data) ? detailSettingsData.data : [];

        const chapterSettingsData = await apiCall('/api/project-data/chapter_settings');
        store.projectData.chapter_settings = Array.isArray(chapterSettingsData.data) ? chapterSettingsData.data : [];

        const chapterSummaryData = await apiCall('/api/project-data/chapter_summary');
        store.projectData.chapter_summary = Array.isArray(chapterSummaryData.data) ? chapterSummaryData.data : [];

        // outline_settings 迁移：降级为自定义分类
        try {
            const outlineSettingsData = await apiCall('/api/project-data/outline_settings');
            const osData = Array.isArray(outlineSettingsData.data) ? outlineSettingsData.data : [];
            store.projectData.outline_settings = osData;
            if (osData.length > 0) {
                const existsCat = store.knowledgeCategories.find(c => c.key === 'outline_settings');
                if (!existsCat) {
                    store.knowledgeCategories.push({
                        id: 'db-outline-legacy', key: 'outline_settings',
                        name: '大纲笔记', icon: 'ri-file-list-3-line', builtin: false
                    });
                }
            }
        } catch (_e) {
            store.projectData.outline_settings = [];
        }

        await loadCustomProjectDataFromServer();

        // 加载扩展资料库（localStorage 备份，仅在项目文件没有数据时使用）
        if (typeof loadExtendedKnowledgeData === 'function') {
            loadExtendedKnowledgeData();
        }
        if (typeof syncKnowledgeCategoriesToProjectState === 'function') {
            await syncKnowledgeCategoriesToProjectState();
        }
        if (typeof loadCopilotAutoSavePreference === 'function') {
            await loadCopilotAutoSavePreference();
        }
        if (typeof loadCopilotCreativeModePreference === 'function') {
            await loadCopilotCreativeModePreference();
        }

        // 更新提及数据
        if (typeof updateMentionData === 'function') {
            updateMentionData();
        }

    } catch (e) {
        console.error('Failed to load project data:', e);
    }
}

function showCreateProjectDialog() {
    const modal = document.getElementById('modal-container');
    modal.classList.remove('hidden');
    
    modal.innerHTML = `
        <div style="position: fixed; top: 0; left: 0; right: 0; bottom: 0; background: rgba(0,0,0,0.6); display: flex; align-items: center; justify-content: center; z-index: 1000;">
            <div style="background: var(--bg-panel); border: 1px solid var(--border-color); border-radius: 16px; padding: 30px; width: 500px; max-width: 90%;">
                <h3 style="color: var(--text-primary); margin-bottom: 24px; font-size: 18px;">
                    <i class="ri-add-circle-line" style="margin-right: 8px; color: var(--accent-color);"></i>
                    创建新项目
                </h3>
                
                <div style="margin-bottom: 20px;">
                    <label style="display: block; font-size: 13px; color: var(--text-secondary); margin-bottom: 8px;">项目名称</label>
                    <input type="text" id="new-project-name" placeholder="例如：我的第一本小说"
                        style="width: 100%; background: rgba(0,0,0,0.3); border: 1px solid var(--border-color); padding: 12px; color: var(--text-primary); border-radius: 8px; font-size: 14px;">
                </div>
                
                <div style="margin-bottom: 20px;">
                    <label style="display: block; font-size: 13px; color: var(--text-secondary); margin-bottom: 8px;">项目描述 (可选)</label>
                    <textarea id="new-project-desc" rows="3" placeholder="简要描述你的小说..."
                        style="width: 100%; background: rgba(0,0,0,0.3); border: 1px solid var(--border-color); padding: 12px; color: var(--text-primary); border-radius: 8px; font-size: 14px; resize: vertical;"></textarea>
                </div>
                
                <div style="margin-bottom: 24px;">
                    <label style="display: block; font-size: 13px; color: var(--text-secondary); margin-bottom: 8px;">小说分类 <span style="color: #ef4444;">*</span></label>
                    <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 10px;">
                        <select id="new-project-genre-preset" aria-label="选择小说分类预设"
                            style="width: 100%; background: rgba(0,0,0,0.3); border: 1px solid var(--border-color); padding: 12px; color: var(--text-primary); border-radius: 8px; font-size: 14px; cursor: pointer;">
                            <option value="">请选择小说分类</option>
                            ${PROJECT_GENRE_PRESETS.map(genre => `<option value="${escapeHtml(genre)}">${escapeHtml(genre)}</option>`).join('')}
                            <option value="__custom__">自定义分类</option>
                        </select>
                        <input type="text" id="new-project-genre" placeholder="自定义分类，例如：修仙副本爽文"
                            style="width: 100%; background: rgba(0,0,0,0.3); border: 1px solid var(--border-color); padding: 12px; color: var(--text-primary); border-radius: 8px; font-size: 14px;">
                    </div>
                </div>
                
                <div style="display: flex; gap: 12px;">
                    <button id="cancel-create-project" style="flex: 1; padding: 12px; background: rgba(255,255,255,0.1); border: 1px solid var(--border-color); color: var(--text-primary); border-radius: 8px; cursor: pointer;">取消</button>
                    <button id="confirm-create-project" style="flex: 1; padding: 12px; background: var(--accent-color); border: none; color: white; border-radius: 8px; cursor: pointer; font-weight: 600;">创建</button>
                </div>
            </div>
        </div>
    `;
    
    // 自动聚焦
    setTimeout(() => {
        document.getElementById('new-project-name').focus();
    }, 100);

    bindProjectGenreControls();
    
    // 取消
    document.getElementById('cancel-create-project').addEventListener('click', () => {
        modal.classList.add('hidden');
        modal.innerHTML = '';
    });
    
    // 确认创建
    document.getElementById('confirm-create-project').addEventListener('click', async () => {
        const name = document.getElementById('new-project-name').value.trim();
        const desc = document.getElementById('new-project-desc').value.trim();
        const genre = getProjectGenreValue();

        if (!name) {
            showToast('请输入项目名称', 'error');
            return;
        }
        if (!genre) {
            showToast('请选择小说分类或输入自定义分类', 'error');
            document.getElementById('new-project-genre-preset')?.focus();
            return;
        }

        try {
            const result = await apiCall('/api/projects', 'POST', {
                name: name,
                description: desc,
                novel_type: genre,
                genre: genre
            });
            
            // 添加到项目列表并切换
            store.projects.push(result.project);
            await switchProject(result.project.id);
            
            modal.classList.add('hidden');
            modal.innerHTML = '';
            showToast(`项目「${name}」创建成功！`);
            
        } catch (e) {
            showToast('创建项目失败: ' + e.message, 'error');
        }
    });
    
    // 回车确认
    document.getElementById('new-project-name').addEventListener('keydown', (e) => {
        if (e.key === 'Enter') {
            document.getElementById('confirm-create-project').click();
        }
    });
}

// 导出项目
async function exportProject(format = 'markdown') {
    try {
        showToast('正在导出项目...');
        
        const response = await fetch(`/api/projects/export?format=${format}`, {
            method: 'GET'
        });
        
        if (!response.ok) {
            throw new Error('导出失败');
        }
        
        const blob = await response.blob();
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        
        const project = store.projects.find(p => p.id === getActiveProjectId());
        const projectName = project?.name || 'novel';
        const ext = format === 'markdown' ? 'md' : format === 'txt' ? 'txt' : 'epub';
        a.download = `${projectName}.${ext}`;
        
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
        
        showToast('导出成功！');
        
    } catch (e) {
        showToast('导出失败: ' + e.message, 'error');
    }
}

// 显示删除项目确认对话框
function showDeleteProjectDialog(projectId, projectName) {
    const project = store.projects.find(p => p.id === projectId);
    if (!project) return;
    
    // 检查是否是最后一个项目
    if (store.projects.length <= 1) {
        showToast('无法删除最后一个项目', 'error');
        return;
    }
    
    const modal = document.getElementById('modal-container');
    modal.classList.remove('hidden');
    
    modal.innerHTML = `
        <div style="position: fixed; top: 0; left: 0; right: 0; bottom: 0; background: rgba(0,0,0,0.6); display: flex; align-items: center; justify-content: center; z-index: 1000;">
            <div style="background: var(--bg-panel); border: 1px solid var(--border-color); border-radius: 16px; padding: 30px; width: 450px; max-width: 90%;">
                <div style="display: flex; align-items: center; gap: 12px; margin-bottom: 20px;">
                    <div style="width: 48px; height: 48px; background: rgba(239,68,68,0.15); border-radius: 12px; display: flex; align-items: center; justify-content: center;">
                        <i class="ri-delete-bin-line" style="font-size: 24px; color: #ef4444;"></i>
                    </div>
                    <div>
                        <h3 style="color: var(--text-primary); margin: 0; font-size: 18px;">删除项目</h3>
                        <p style="color: var(--text-secondary); margin: 4px 0 0 0; font-size: 13px;">此操作不可恢复</p>
                    </div>
                </div>
                
                <div style="background: rgba(239,68,68,0.1); border: 1px solid rgba(239,68,68,0.2); border-radius: 8px; padding: 16px; margin-bottom: 20px;">
                    <p style="color: var(--text-primary); margin: 0 0 8px 0; font-size: 14px;">
                        确定要删除项目「<strong style="color: #ef4444;">${escapeHtml(projectName)}</strong>」吗？
                    </p>
                    <p style="color: var(--text-secondary); margin: 0; font-size: 13px;">
                        <i class="ri-error-warning-line" style="margin-right: 4px;"></i>
                        所有章节、世界观设定、角色设定等数据都将被永久删除！
                    </p>
                </div>
                
                <div style="margin-bottom: 24px;">
                    <label style="display: block; font-size: 13px; color: var(--text-secondary); margin-bottom: 8px;">
                        请输入项目名称以确认删除：
                    </label>
                    <input type="text" id="delete-confirm-input" placeholder="${escapeHtml(projectName)}"
                        style="width: 100%; background: rgba(0,0,0,0.3); border: 1px solid var(--border-color); padding: 12px; color: var(--text-primary); border-radius: 8px; font-size: 14px;">
                </div>
                
                <div style="display: flex; gap: 12px;">
                    <button id="cancel-delete-project" style="flex: 1; padding: 12px; background: rgba(255,255,255,0.1); border: 1px solid var(--border-color); color: var(--text-primary); border-radius: 8px; cursor: pointer; font-size: 14px;">取消</button>
                    <button id="confirm-delete-project" disabled style="flex: 1; padding: 12px; background: #ef4444; border: none; color: white; border-radius: 8px; cursor: not-allowed; font-weight: 600; font-size: 14px; opacity: 0.5; transition: all 0.15s;">确认删除</button>
                </div>
            </div>
        </div>
    `;
    
    const confirmInput = document.getElementById('delete-confirm-input');
    const confirmBtn = document.getElementById('confirm-delete-project');
    
    // 自动聚焦
    setTimeout(() => {
        confirmInput.focus();
    }, 100);
    
    // 输入验证
    confirmInput.addEventListener('input', () => {
        const isMatch = confirmInput.value.trim() === projectName;
        confirmBtn.disabled = !isMatch;
        confirmBtn.style.opacity = isMatch ? '1' : '0.5';
        confirmBtn.style.cursor = isMatch ? 'pointer' : 'not-allowed';
    });
    
    // 取消
    document.getElementById('cancel-delete-project').addEventListener('click', () => {
        modal.classList.add('hidden');
        modal.innerHTML = '';
    });
    
    // 确认删除
    confirmBtn.addEventListener('click', async () => {
        if (confirmBtn.disabled) return;
        
        confirmBtn.disabled = true;
        confirmBtn.innerHTML = '<i class="ri-loader-4-line ri-spin" style="margin-right: 6px;"></i>删除中...';
        
        try {
            await deleteProject(projectId);
            modal.classList.add('hidden');
            modal.innerHTML = '';
        } catch (e) {
            confirmBtn.disabled = false;
            confirmBtn.innerHTML = '确认删除';
            showToast('删除失败: ' + e.message, 'error');
        }
    });
    
    // ESC关闭
    const handleEsc = (e) => {
        if (e.key === 'Escape') {
            modal.classList.add('hidden');
            modal.innerHTML = '';
            document.removeEventListener('keydown', handleEsc);
        }
    };
    document.addEventListener('keydown', handleEsc);
}

// 删除项目
async function deleteProject(projectId) {
    const project = store.projects.find(p => p.id === projectId);
    if (!project) return;
    
    await apiCall(`/api/projects/${projectId}`, 'DELETE');
    
    store.projects = store.projects.filter(p => p.id !== projectId);
    
    // 如果删除的是当前项目，切换到第一个可用项目
    if (projectId === getActiveProjectId()) {
        if (store.projects.length > 0) {
            await switchProject(store.projects[0].id);
        } else {
            setActiveProjectId(null);
            store.projectData = {
                outline: [],
                chapters: [],
                worldbuilding: [],
                characters: [],
                items: [],
                eventlines: [],
                outline_settings: [],
                detail_settings: [],
                chapter_settings: [],
                chapter_summary: []
            };
            updateProjectSelector();
            if (typeof showEmptyEditor === 'function') {
                showEmptyEditor();
            }
        }
    }
    
    showToast(`项目「${project.name}」已删除`);
}

// 全局暴露项目管理函数
window.loadProjects = loadProjects;
window.updateProjectSelector = updateProjectSelector;
window.toggleProjectDropdown = toggleProjectDropdown;
window.switchProject = switchProject;
window.loadCurrentProjectData = loadCurrentProjectData;
window.showCreateProjectDialog = showCreateProjectDialog;
window.exportProject = exportProject;
window.deleteProject = deleteProject;
window.showDeleteProjectDialog = showDeleteProjectDialog;

console.log('[app-project.js] 项目管理模块已加载');

