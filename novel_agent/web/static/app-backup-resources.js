/**
 * 文思Agent - 备份与资料库管理模块
 * 包含：项目备份、自动备份、资料库管理
 */

// ===== 备份管理 =====

async function loadBackupSettings() {
    let content = document.getElementById('settings-content');
    
    if (!content) {
        renderSettings();
        content = document.getElementById('settings-content');
        if (!content) return;
    }
    
    content.innerHTML = `
        <div style="display: flex; align-items: center; justify-content: center; height: 200px;">
            <i class="ri-loader-4-line" style="font-size: 32px; color: var(--accent-color); animation: spin 1s linear infinite;"></i>
        </div>
    `;
    
    try {
        const [backups, autoBackupStatus] = await Promise.all([
            apiCall('/api/backup/list'),
            apiCall('/api/auto-backup/status')
        ]);
        
        content.innerHTML = `
            <div style="max-width: 1000px;">
                <h2 style="color: var(--text-primary); margin-bottom: 24px; font-size: 20px;">
                    <i class="ri-save-line" style="margin-right: 8px; color: var(--accent-color);"></i>
                    备份管理
                </h2>
                
                <!-- 快速操作 -->
                <div class="setting-section" style="background: linear-gradient(135deg, rgba(16,185,129,0.1), rgba(59,130,246,0.1)); border-radius: 12px; padding: 20px; margin-bottom: 20px; border: 1px solid rgba(16,185,129,0.3);">
                    <h3 style="color: var(--text-primary); margin-bottom: 16px; font-size: 15px;">
                        <i class="ri-flashlight-line" style="margin-right: 6px; color: #10b981;"></i>
                        快速操作
                    </h3>
                    <div style="display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px;">
                        <button id="create-backup-btn" style="padding: 14px; background: var(--accent-color); border: none; color: white; border-radius: 8px; cursor: pointer; font-weight: 500;">
                            <i class="ri-save-3-line"></i> 创建备份
                        </button>
                        <button id="import-backup-btn" style="padding: 14px; background: rgba(255,255,255,0.1); border: 1px solid var(--border-color); color: var(--text-primary); border-radius: 8px; cursor: pointer;">
                            <i class="ri-upload-line"></i> 导入备份
                        </button>
                        <button id="auto-backup-settings-btn" style="padding: 14px; background: rgba(255,255,255,0.1); border: 1px solid var(--border-color); color: var(--text-primary); border-radius: 8px; cursor: pointer;">
                            <i class="ri-timer-line"></i> 自动备份设置
                        </button>
                    </div>
                    <input type="file" id="backup-file-input" accept=".zip" style="display: none;">
                </div>
                
                <!-- 自动备份状态 -->
                <div class="setting-section" style="background: rgba(0,0,0,0.2); border-radius: 12px; padding: 20px; margin-bottom: 20px;">
                    <div style="display: flex; justify-content: space-between; align-items: center;">
                        <div>
                            <h3 style="color: var(--text-primary); margin-bottom: 8px; font-size: 15px;">
                                <i class="ri-timer-line" style="margin-right: 6px;"></i>
                                自动备份状态
                            </h3>
                            <p style="color: var(--text-secondary); font-size: 13px;">
                                ${autoBackupStatus.enabled ? 
                                    `<span style="color: #10b981;">✓ 已启用</span> - ${autoBackupStatus.schedule_type || '未设置'}` :
                                    '<span style="color: #6b7280;">未启用</span>'}
                            </p>
                            ${autoBackupStatus.enabled && autoBackupStatus.next_backup ? 
                                `<p style="color: var(--text-secondary); font-size: 12px; margin-top: 4px;">
                                    下次备份: ${new Date(autoBackupStatus.next_backup).toLocaleString('zh-CN')}
                                </p>` : ''}
                        </div>
                        <label style="display: flex; align-items: center; gap: 8px; cursor: pointer;">
                            <input type="checkbox" id="auto-backup-toggle" ${autoBackupStatus.enabled ? 'checked' : ''} style="width: 20px; height: 20px; accent-color: var(--accent-color);">
                            <span style="color: var(--text-secondary); font-size: 13px;">启用自动备份</span>
                        </label>
                    </div>
                </div>
                
                <!-- 备份列表 -->
                <div class="setting-section" style="background: rgba(0,0,0,0.2); border-radius: 12px; padding: 20px;">
                    <h3 style="color: var(--text-primary); margin-bottom: 16px; font-size: 15px;">
                        <i class="ri-file-list-3-line" style="margin-right: 6px;"></i>
                        备份列表 (${backups.backups.length})
                    </h3>
                    
                    ${backups.backups.length === 0 ? `
                        <div style="text-align: center; padding: 40px; color: var(--text-secondary);">
                            <i class="ri-inbox-line" style="font-size: 48px; opacity: 0.5;"></i>
                            <p style="margin-top: 12px;">还没有备份，点击上方"创建备份"开始</p>
                        </div>
                    ` : `
                        <div style="display: grid; gap: 12px;">
                            ${backups.backups.map(backup => `
                                <div class="backup-item" style="background: rgba(255,255,255,0.03); border: 1px solid var(--border-color); border-radius: 10px; padding: 16px;">
                                    <div style="display: flex; justify-content: space-between; align-items: flex-start;">
                                        <div style="flex: 1;">
                                            <div style="display: flex; align-items: center; gap: 10px; margin-bottom: 8px;">
                                                <i class="ri-file-zip-line" style="font-size: 20px; color: var(--accent-color);"></i>
                                                <span style="font-size: 15px; font-weight: 500; color: var(--text-primary);">${backup.filename}</span>
                                            </div>
                                            <div style="display: flex; gap: 16px; color: var(--text-secondary); font-size: 12px;">
                                                <span><i class="ri-time-line"></i> ${new Date(backup.created_at).toLocaleString('zh-CN')}</span>
                                                <span><i class="ri-file-line"></i> ${(backup.size / 1024 / 1024).toFixed(2)} MB</span>
                                                <span><i class="ri-folder-line"></i> ${backup.project_name || '未知项目'}</span>
                                            </div>
                                        </div>
                                        <div style="display: flex; gap: 8px;">
                                            <button class="restore-backup-btn" data-filename="${backup.filename}" style="padding: 8px 12px; background: rgba(16,185,129,0.2); border: 1px solid rgba(16,185,129,0.5); color: #10b981; border-radius: 6px; cursor: pointer; font-size: 12px;">
                                                <i class="ri-refresh-line"></i> 恢复
                                            </button>
                                            <button class="download-backup-btn" data-filename="${backup.filename}" style="padding: 8px 12px; background: rgba(255,255,255,0.1); border: 1px solid var(--border-color); color: var(--text-primary); border-radius: 6px; cursor: pointer; font-size: 12px;">
                                                <i class="ri-download-line"></i> 下载
                                            </button>
                                            <button class="delete-backup-btn" data-filename="${backup.filename}" style="padding: 8px; background: rgba(239,68,68,0.1); border: 1px solid rgba(239,68,68,0.3); color: #ef4444; border-radius: 6px; cursor: pointer;">
                                                <i class="ri-delete-bin-line"></i>
                                            </button>
                                        </div>
                                    </div>
                                </div>
                            `).join('')}
                        </div>
                    `}
                </div>
            </div>
        `;
        
        bindBackupEvents();
        
    } catch (e) {
        content.innerHTML = `
            <div style="text-align: center; padding: 40px; color: var(--text-secondary);">
                <i class="ri-error-warning-line" style="font-size: 48px; color: #ef4444;"></i>
                <p style="margin-top: 16px;">加载备份列表失败: ${e.message}</p>
            </div>
        `;
    }
}

function bindBackupEvents() {
    // 创建备份
    document.getElementById('create-backup-btn')?.addEventListener('click', async () => {
        const btn = document.getElementById('create-backup-btn');
        btn.disabled = true;
        btn.innerHTML = '<i class="ri-loader-4-line ri-spin"></i> 创建中...';
        
        try {
            // 收集localStorage数据
            const localStorageData = {};
            const keysToBackup = [
                'eventlines',
                'outline_settings',
                'detail_settings',
                'chapter_settings',
                'knowledge_categories'
            ];
            
            for (const key of keysToBackup) {
                const value = localStorage.getItem(key);
                if (value) {
                    localStorageData[key] = value;
                }
            }
            
            await apiCall('/api/backup/create', 'POST', {
                include_knowledge_base: true,
                include_aux_memory: true,
                include_resources: true,
                local_storage_data: localStorageData
            });
            
            showToast('备份创建成功');
            loadBackupSettings();
        } catch (e) {
            showToast('创建失败: ' + e.message, 'error');
            btn.disabled = false;
            btn.innerHTML = '<i class="ri-save-3-line"></i> 创建备份';
        }
    });
    
    // 导入备份
    document.getElementById('import-backup-btn')?.addEventListener('click', () => {
        document.getElementById('backup-file-input').click();
    });
    
    document.getElementById('backup-file-input')?.addEventListener('change', async (e) => {
        const file = e.target.files[0];
        if (!file) return;
        
        const formData = new FormData();
        formData.append('file', file);
        
        try {
            showToast('正在导入备份...');
            const response = await fetch('/api/backup/import', {
                method: 'POST',
                body: formData
            });
            
            if (!response.ok) throw new Error('导入失败');
            
            showToast('备份导入成功');
            loadBackupSettings();
        } catch (e) {
            showToast('导入失败: ' + e.message, 'error');
        }
        
        e.target.value = '';
    });
    
    // 自动备份开关
    document.getElementById('auto-backup-toggle')?.addEventListener('change', async (e) => {
        try {
            await apiCall('/api/auto-backup/toggle', 'POST', {
                enabled: e.target.checked
            });
            showToast(e.target.checked ? '自动备份已启用' : '自动备份已禁用');
        } catch (err) {
            showToast('操作失败: ' + err.message, 'error');
            e.target.checked = !e.target.checked;
        }
    });
    
    // 恢复备份
    document.querySelectorAll('.restore-backup-btn').forEach(btn => {
        btn.addEventListener('click', async () => {
            const filename = btn.dataset.filename;
            
            if (!confirm(`确定要恢复备份 "${filename}" 吗？\n\n当前项目数据将被覆盖！`)) {
                return;
            }
            
            btn.disabled = true;
            btn.innerHTML = '<i class="ri-loader-4-line ri-spin"></i>';
            
            try {
                const result = await apiCall('/api/backup/restore', 'POST', { filename });
                
                // 如果备份包含localStorage数据，恢复它
                if (result.local_storage_data) {
                    for (const [key, value] of Object.entries(result.local_storage_data)) {
                        localStorage.setItem(key, value);
                    }
                }
                
                showToast('备份恢复成功');
                setTimeout(() => location.reload(), 1000);
            } catch (e) {
                showToast('恢复失败: ' + e.message, 'error');
                btn.disabled = false;
                btn.innerHTML = '<i class="ri-refresh-line"></i> 恢复';
            }
        });
    });
    
    // 下载备份
    document.querySelectorAll('.download-backup-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            const filename = btn.dataset.filename;
            window.open(`/api/backup/download/${filename}`, '_blank');
        });
    });
    
    // 删除备份
    document.querySelectorAll('.delete-backup-btn').forEach(btn => {
        btn.addEventListener('click', async () => {
            const filename = btn.dataset.filename;
            
            if (!confirm(`确定要删除备份 "${filename}" 吗？`)) {
                return;
            }
            
            try {
                await apiCall(`/api/backup/delete/${filename}`, 'DELETE');
                showToast('备份已删除');
                loadBackupSettings();
            } catch (e) {
                showToast('删除失败: ' + e.message, 'error');
            }
        });
    });
}

// ===== 资料库管理 =====

async function loadResourcesSettings() {
    let content = document.getElementById('settings-content');
    
    if (!content) {
        renderSettings();
        content = document.getElementById('settings-content');
        if (!content) return;
    }
    
    content.innerHTML = `
        <div style="display: flex; align-items: center; justify-content: center; height: 200px;">
            <i class="ri-loader-4-line" style="font-size: 32px; color: var(--accent-color); animation: spin 1s linear infinite;"></i>
        </div>
    `;
    
    try {
        const [resources, stats] = await Promise.all([
            apiCall('/api/resources/list'),
            apiCall('/api/resources/stats')
        ]);
        
        content.innerHTML = `
            <div style="max-width: 1000px;">
                <h2 style="color: var(--text-primary); margin-bottom: 24px; font-size: 20px;">
                    <i class="ri-folder-open-line" style="margin-right: 8px; color: var(--accent-color);"></i>
                    资料库管理
                </h2>
                
                <p style="color: var(--text-secondary); margin-bottom: 20px; font-size: 13px;">
                    管理项目参考资料，包括文档、图片、参考文件等。这些资料可以在创作时作为参考。
                </p>
                
                <!-- 统计信息 -->
                <div class="setting-section" style="background: rgba(0,0,0,0.2); border-radius: 12px; padding: 20px; margin-bottom: 20px;">
                    <h3 style="color: var(--text-primary); margin-bottom: 16px; font-size: 15px;">
                        <i class="ri-bar-chart-line" style="margin-right: 6px;"></i>
                        统计信息
                    </h3>
                    <div style="display: grid; grid-template-columns: repeat(4, 1fr); gap: 16px;">
                        <div style="background: rgba(0,0,0,0.2); padding: 16px; border-radius: 8px; text-align: center;">
                            <div style="font-size: 28px; font-weight: 600; color: var(--accent-color);">${stats.total_count || 0}</div>
                            <div style="font-size: 12px; color: var(--text-secondary); margin-top: 4px;">总文件数</div>
                        </div>
                        <div style="background: rgba(0,0,0,0.2); padding: 16px; border-radius: 8px; text-align: center;">
                            <div style="font-size: 28px; font-weight: 600; color: #10b981;">${stats.by_type?.documents || 0}</div>
                            <div style="font-size: 12px; color: var(--text-secondary); margin-top: 4px;">文档</div>
                        </div>
                        <div style="background: rgba(0,0,0,0.2); padding: 16px; border-radius: 8px; text-align: center;">
                            <div style="font-size: 28px; font-weight: 600; color: #f59e0b;">${stats.by_type?.images || 0}</div>
                            <div style="font-size: 12px; color: var(--text-secondary); margin-top: 4px;">图片</div>
                        </div>
                        <div style="background: rgba(0,0,0,0.2); padding: 16px; border-radius: 8px; text-align: center;">
                            <div style="font-size: 28px; font-weight: 600; color: #ec4899;">${(stats.total_size / 1024 / 1024).toFixed(1)}</div>
                            <div style="font-size: 12px; color: var(--text-secondary); margin-top: 4px;">总大小 (MB)</div>
                        </div>
                    </div>
                </div>
                
                <!-- 上传区域 -->
                <div class="setting-section" style="background: linear-gradient(135deg, rgba(16,185,129,0.1), rgba(59,130,246,0.1)); border-radius: 12px; padding: 20px; margin-bottom: 20px; border: 1px solid rgba(16,185,129,0.3);">
                    <h3 style="color: var(--text-primary); margin-bottom: 16px; font-size: 15px;">
                        <i class="ri-upload-cloud-line" style="margin-right: 6px; color: #10b981;"></i>
                        上传资料
                    </h3>
                    <div style="display: flex; gap: 12px; align-items: flex-end;">
                        <div style="flex: 1;">
                            <label style="display: block; font-size: 13px; color: var(--text-secondary); margin-bottom: 8px;">选择文件</label>
                            <input type="file" id="resource-file-input" multiple style="width: 100%; padding: 10px; background: rgba(0,0,0,0.3); border: 1px solid var(--border-color); color: var(--text-primary); border-radius: 8px;">
                        </div>
                        <button id="upload-resource-btn" style="padding: 12px 24px; background: var(--accent-color); border: none; color: white; border-radius: 8px; cursor: pointer; font-weight: 500;">
                            <i class="ri-upload-line"></i> 上传
                        </button>
                    </div>
                </div>
                
                <!-- 资料列表 -->
                <div class="setting-section" style="background: rgba(0,0,0,0.2); border-radius: 12px; padding: 20px;">
                    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px;">
                        <h3 style="color: var(--text-primary); font-size: 15px; margin: 0;">
                            <i class="ri-file-list-3-line" style="margin-right: 6px;"></i>
                            资料列表
                        </h3>
                        <div style="display: flex; gap: 8px;">
                            <select id="resource-type-filter" style="padding: 8px 12px; background: rgba(0,0,0,0.3); border: 1px solid var(--border-color); color: var(--text-primary); border-radius: 6px; font-size: 13px;">
                                <option value="all">全部类型</option>
                                <option value="documents">文档</option>
                                <option value="images">图片</option>
                                <option value="references">参考资料</option>
                                <option value="other">其他</option>
                            </select>
                            <input type="text" id="resource-search-input" placeholder="搜索资料..." style="padding: 8px 12px; background: rgba(0,0,0,0.3); border: 1px solid var(--border-color); color: var(--text-primary); border-radius: 6px; font-size: 13px; width: 200px;">
                        </div>
                    </div>
                    
                    ${resources.resources.length === 0 ? `
                        <div style="text-align: center; padding: 40px; color: var(--text-secondary);">
                            <i class="ri-inbox-line" style="font-size: 48px; opacity: 0.5;"></i>
                            <p style="margin-top: 12px;">还没有上传资料</p>
                        </div>
                    ` : `
                        <div id="resources-list" style="display: grid; gap: 12px;">
                            ${resources.resources.map(resource => `
                                <div class="resource-item" data-type="${resource.type}" data-name="${resource.filename.toLowerCase()}" style="background: rgba(255,255,255,0.03); border: 1px solid var(--border-color); border-radius: 10px; padding: 16px;">
                                    <div style="display: flex; justify-content: space-between; align-items: flex-start;">
                                        <div style="flex: 1;">
                                            <div style="display: flex; align-items: center; gap: 10px; margin-bottom: 8px;">
                                                <i class="${getResourceIcon(resource.type)}" style="font-size: 20px; color: ${getResourceColor(resource.type)};"></i>
                                                <span style="font-size: 15px; font-weight: 500; color: var(--text-primary);">${resource.filename}</span>
                                                <span style="background: rgba(59,130,246,0.2); color: #60a5fa; padding: 2px 8px; border-radius: 4px; font-size: 11px;">${resource.type}</span>
                                            </div>
                                            <div style="display: flex; gap: 16px; color: var(--text-secondary); font-size: 12px;">
                                                <span><i class="ri-time-line"></i> ${new Date(resource.created_at).toLocaleString('zh-CN')}</span>
                                                <span><i class="ri-file-line"></i> ${(resource.size / 1024).toFixed(1)} KB</span>
                                            </div>
                                        </div>
                                        <div style="display: flex; gap: 8px;">
                                            <button class="download-resource-btn" data-id="${resource.id}" style="padding: 8px 12px; background: rgba(255,255,255,0.1); border: 1px solid var(--border-color); color: var(--text-primary); border-radius: 6px; cursor: pointer; font-size: 12px;">
                                                <i class="ri-download-line"></i>
                                            </button>
                                            <button class="delete-resource-btn" data-id="${resource.id}" style="padding: 8px; background: rgba(239,68,68,0.1); border: 1px solid rgba(239,68,68,0.3); color: #ef4444; border-radius: 6px; cursor: pointer;">
                                                <i class="ri-delete-bin-line"></i>
                                            </button>
                                        </div>
                                    </div>
                                </div>
                            `).join('')}
                        </div>
                    `}
                </div>
            </div>
        `;
        
        bindResourcesEvents();
        
    } catch (e) {
        content.innerHTML = `
            <div style="text-align: center; padding: 40px; color: var(--text-secondary);">
                <i class="ri-error-warning-line" style="font-size: 48px; color: #ef4444;"></i>
                <p style="margin-top: 16px;">加载资料库失败: ${e.message}</p>
            </div>
        `;
    }
}

function getResourceIcon(type) {
    const icons = {
        'documents': 'ri-file-text-line',
        'images': 'ri-image-line',
        'references': 'ri-book-line',
        'other': 'ri-file-line'
    };
    return icons[type] || 'ri-file-line';
}

function getResourceColor(type) {
    const colors = {
        'documents': '#10b981',
        'images': '#f59e0b',
        'references': '#3b82f6',
        'other': '#6b7280'
    };
    return colors[type] || '#6b7280';
}

function bindResourcesEvents() {
    // 上传资料
    document.getElementById('upload-resource-btn')?.addEventListener('click', async () => {
        const fileInput = document.getElementById('resource-file-input');
        const files = fileInput.files;
        
        if (files.length === 0) {
            showToast('请先选择文件', 'error');
            return;
        }
        
        const btn = document.getElementById('upload-resource-btn');
        btn.disabled = true;
        btn.innerHTML = '<i class="ri-loader-4-line ri-spin"></i> 上传中...';
        
        try {
            const formData = new FormData();
            for (let file of files) {
                formData.append('files', file);
            }
            
            const response = await fetch('/api/resources/upload', {
                method: 'POST',
                body: formData
            });
            
            if (!response.ok) throw new Error('上传失败');
            
            showToast(`成功上传 ${files.length} 个文件`);
            fileInput.value = '';
            loadResourcesSettings();
        } catch (e) {
            showToast('上传失败: ' + e.message, 'error');
        } finally {
            btn.disabled = false;
            btn.innerHTML = '<i class="ri-upload-line"></i> 上传';
        }
    });
    
    // 类型筛选
    document.getElementById('resource-type-filter')?.addEventListener('change', () => {
        filterResources();
    });
    
    // 搜索
    document.getElementById('resource-search-input')?.addEventListener('input', () => {
        filterResources();
    });
    
    // 下载资料
    document.querySelectorAll('.download-resource-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            const id = btn.dataset.id;
            window.open(`/api/resources/download/${id}`, '_blank');
        });
    });
    
    // 删除资料
    document.querySelectorAll('.delete-resource-btn').forEach(btn => {
        btn.addEventListener('click', async () => {
            const id = btn.dataset.id;
            
            if (!confirm('确定要删除这个资料吗？')) {
                return;
            }
            
            try {
                await apiCall(`/api/resources/delete/${id}`, 'DELETE');
                showToast('资料已删除');
                loadResourcesSettings();
            } catch (e) {
                showToast('删除失败: ' + e.message, 'error');
            }
        });
    });
}

function filterResources() {
    const typeFilter = document.getElementById('resource-type-filter')?.value || 'all';
    const searchText = document.getElementById('resource-search-input')?.value.toLowerCase() || '';
    
    document.querySelectorAll('.resource-item').forEach(item => {
        const type = item.dataset.type;
        const name = item.dataset.name;
        
        const typeMatch = typeFilter === 'all' || type === typeFilter;
        const searchMatch = !searchText || name.includes(searchText);
        
        item.style.display = (typeMatch && searchMatch) ? 'block' : 'none';
    });
}

// 全局暴露函数
window.loadBackupSettings = loadBackupSettings;
window.loadResourcesSettings = loadResourcesSettings;

console.log('[app-backup-resources.js] 备份与资料库模块已加载');