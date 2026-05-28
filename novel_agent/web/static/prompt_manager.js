/**
 * 提示词管理模块
 * 用于管理和编辑各Agent的提示词配置
 */
(function() {
'use strict';

console.log('[PromptManager] 开始加载提示词管理模块...');

// 存储当前提示词数据
var promptsData = {
    agents: [],
    currentAgent: null,
    currentTask: null,
    showAdvanced: false
};

// 使用全局 showToast 或创建本地版本
var showToast = typeof window.showToast === 'function' ? window.showToast : function(msg, type) {
    var t = document.getElementById('toast');
    if (!t) return;
    t.textContent = msg;
    t.classList.remove('hidden');
    t.style.opacity = 1;
    setTimeout(function() {
        t.style.opacity = 0;
        setTimeout(function() { t.classList.add('hidden'); }, 300);
    }, 2500);
};

function promptApiUrl(agentType, taskName) {
    const base = `/api/prompts/${encodeURIComponent(String(agentType || ''))}`;
    const taskPart = taskName === undefined ? '' : `/${encodeURIComponent(String(taskName || ''))}`;
    const url = `${base}${taskPart}?include_advanced=${promptsData.showAdvanced ? 'true' : 'false'}`;
    return typeof normalizeApiUrl === 'function' ? normalizeApiUrl(url) : url;
}

/**
 * 加载提示词管理设置页面
 */
async function loadPromptSettings() {
    const workspace = document.getElementById('main-view');
    const breadcrumbs = document.getElementById('breadcrumbs');
    
    if (breadcrumbs) {
        breadcrumbs.innerHTML = '<span>设置</span> <i class="ri-arrow-right-s-line"></i> <span class="current">提示词管理</span>';
    }
    
    workspace.innerHTML = `
        <div style="max-width: 1100px; margin: 40px auto; padding: 0 20px;">
            <h2 style="margin-bottom: 16px; color: var(--text-primary); display: flex; align-items: center; gap: 12px;">
                <i class="ri-file-text-line"></i>
                提示词管理
            </h2>
            <p style="color: var(--text-secondary); margin-bottom: 24px; line-height: 1.6;">
                这里只显示会直接影响创作结果的核心AI Agent。系统内部流程节点已隐藏，避免误改影响稳定性。
            </p>
            <div style="display: flex; align-items: center; justify-content: space-between; gap: 12px; margin-bottom: 20px; padding: 14px 16px; background: rgba(255,255,255,0.03); border: 1px solid var(--border-color); border-radius: 10px;">
                <div>
                    <div style="font-size: 14px; color: var(--text-primary); font-weight: 600;">高级 / 开发者模式</div>
                    <div style="font-size: 12px; color: var(--text-secondary); margin-top: 4px;">开启后可查看部分内部辅助 Agent 的提示词入口，请谨慎修改。</div>
                </div>
                <label style="display: inline-flex; align-items: center; gap: 8px; color: var(--text-primary); cursor: pointer; user-select: none;">
                    <input id="prompt-advanced-toggle" type="checkbox" ${promptsData.showAdvanced ? 'checked' : ''} style="accent-color: var(--accent-color);">
                    <span style="font-size: 13px;">显示高级 Agent</span>
                </label>
            </div>
            
            <div style="display: grid; grid-template-columns: 280px 1fr; gap: 24px; min-height: 500px;">
                <!-- 左侧：Agent列表 -->
                <div style="background: rgba(255,255,255,0.03); border: 1px solid var(--border-color); border-radius: 12px; overflow: hidden;">
                    <div style="padding: 16px; border-bottom: 1px solid var(--border-color); font-weight: 600; color: var(--text-primary);">
                        <i class="ri-brain-line" style="margin-right: 8px;"></i>
                        Agent 列表
                    </div>
                    <div id="prompt-agent-list" style="max-height: 500px; overflow-y: auto;">
                        <div style="padding: 20px; text-align: center; color: var(--text-secondary);">
                            <i class="ri-loader-4-line" style="font-size: 24px;"></i>
                            <p style="margin-top: 8px;">加载中...</p>
                        </div>
                    </div>
                </div>
                
                <!-- 右侧：提示词编辑区 -->
                <div id="prompt-editor-area" style="background: rgba(255,255,255,0.03); border: 1px solid var(--border-color); border-radius: 12px; overflow: hidden;">
                    <div style="display: flex; align-items: center; justify-content: center; height: 100%; color: var(--text-secondary);">
                        <div style="text-align: center;">
                            <i class="ri-arrow-left-line" style="font-size: 48px; opacity: 0.3;"></i>
                            <p style="margin-top: 16px;">从左侧选择一个Agent查看提示词</p>
                        </div>
                    </div>
                </div>
            </div>
            
            <!-- 使用说明 -->
            <div style="margin-top: 24px; background: rgba(100,180,255,0.1); border: 1px solid rgba(100,180,255,0.3); border-radius: 12px; padding: 20px;">
                <h3 style="margin-bottom: 12px; font-size: 14px; color: #7dd3fc;">💡 提示词模板变量说明</h3>
                <ul style="font-size: 13px; color: var(--text-secondary); line-height: 1.8; padding-left: 20px; margin: 0;">
                    <li><code>{novel_type}</code> - 小说类型（如玄幻、都市等）</li>
                    <li><code>{theme}</code> - 小说主题</li>
                    <li><code>{chapter_number}</code> - 章节编号</li>
                    <li><code>{chapter_title}</code> - 章节标题</li>
                    <li><code>{word_count}</code> - 目标字数</li>
                    <li><code>{context}</code> - 上下文内容</li>
                    <li><code>{requirements}</code> - 用户需求</li>
                </ul>
            </div>
        </div>
    `;
    
    // 加载Agent列表
    const advancedToggle = document.getElementById('prompt-advanced-toggle');
    if (advancedToggle) {
        advancedToggle.addEventListener('change', async function() {
            promptsData.showAdvanced = !!advancedToggle.checked;
            promptsData.currentAgent = null;
            await loadAgentList();
            const editorArea = document.getElementById('prompt-editor-area');
            if (editorArea) {
                editorArea.innerHTML = `
                    <div style="display: flex; align-items: center; justify-content: center; height: 100%; color: var(--text-secondary);">
                        <div style="text-align: center;">
                            <i class="ri-arrow-left-line" style="font-size: 48px; opacity: 0.3;"></i>
                            <p style="margin-top: 16px;">从左侧选择一个Agent查看提示词</p>
                        </div>
                    </div>
                `;
            }
        });
    }
    await loadAgentList();
}

/**
 * 加载Agent列表
 */
async function loadAgentList() {
    const listContainer = document.getElementById('prompt-agent-list');
    
    try {
        console.log('[PromptManager] 正在加载Agent列表...');
        const response = await fetch(normalizeApiUrl(`/api/v1/prompts?include_advanced=${promptsData.showAdvanced ? 'true' : 'false'}`));
        console.log('[PromptManager] API响应状态:', response.status);
        
        if (!response.ok) {
            throw new Error(`HTTP错误: ${response.status}`);
        }
        
        const data = await response.json();
        console.log('[PromptManager] API返回数据:', data);
        
        if (!data.success) {
            throw new Error(data.error || '加载失败');
        }
        
        promptsData.agents = data.agents || [];
        
        // 渲染Agent列表
        listContainer.innerHTML = data.agents.map(agent => `
            <div class="prompt-agent-item" data-agent="${agent.name}" 
                style="padding: 14px 16px; border-bottom: 1px solid var(--border-color); cursor: pointer; transition: background 0.2s;">
                <div style="display: flex; align-items: center; gap: 10px;">
                    <i class="${getAgentIcon(agent.name)}" style="font-size: 18px; color: var(--accent-color);"></i>
                    <div>
                        <div style="font-weight: 500; color: var(--text-primary);">${agent.display_name || agent.name}</div>
                        <div style="font-size: 11px; color: var(--text-secondary); margin-top: 2px;">
                            ${agent.task_count || 0} 个任务提示词
                            ${agent.visibility === 'advanced' ? '<span style="color: #a78bfa; margin-left: 4px;">🛠 高级</span>' : ''}
                            ${agent.has_custom ? '<span style="color: #f59e0b; margin-left: 4px;">✎ 已自定义</span>' : ''}
                        </div>
                    </div>
                </div>
            </div>
        `).join('');
        
        // 绑定点击事件
        listContainer.querySelectorAll('.prompt-agent-item').forEach(item => {
            item.addEventListener('click', () => {
                // 移除其他选中状态
                listContainer.querySelectorAll('.prompt-agent-item').forEach(el => {
                    el.style.background = '';
                });
                item.style.background = 'rgba(255,255,255,0.08)';
                
                // 加载该Agent的提示词
                loadAgentPrompts(item.dataset.agent);
            });
            
            // 悬停效果
            item.addEventListener('mouseenter', () => {
                if (item.dataset.agent !== promptsData.currentAgent) {
                    item.style.background = 'rgba(255,255,255,0.05)';
                }
            });
            item.addEventListener('mouseleave', () => {
                if (item.dataset.agent !== promptsData.currentAgent) {
                    item.style.background = '';
                }
            });
        });
        
    } catch (e) {
        listContainer.innerHTML = `
            <div style="padding: 20px; text-align: center; color: #ef4444;">
                <i class="ri-error-warning-line" style="font-size: 24px;"></i>
                <p style="margin-top: 8px;">加载失败: ${e.message}</p>
                <button onclick="loadAgentList()" style="margin-top: 12px; padding: 8px 16px; background: var(--accent-color); border: none; color: white; border-radius: 6px; cursor: pointer;">重试</button>
            </div>
        `;
    }
}

/**
 * 根据Agent名称获取图标
 */
function getAgentIcon(agentName) {
    const icons = {
        'router': 'ri-route-line',
        'Router': 'ri-route-line',
        'communicator': 'ri-chat-3-line',
        'worldbuilder': 'ri-earth-line',
        'outliner': 'ri-file-list-3-line',
        'CharacterBuilder': 'ri-user-star-line',
        'EventlineBuilder': 'ri-route-line',
        'DetailOutlineBuilder': 'ri-node-tree',
        'ChapterSettingBuilder': 'ri-book-open-line',
        'short_story': 'ri-draft-line',
        'chapter_writer': 'ri-quill-pen-line',
        'polisher': 'ri-magic-line',
        'evaluator': 'ri-checkbox-circle-line',
        'continuous_writer': 'ri-infinity-line',
        'ContentExpansion': 'ri-text-spacing',
        'SummaryOrchestrator': 'ri-list-ordered',
        'copilot': 'ri-sparkling-fill'
    };
    return icons[agentName] || 'ri-robot-line';
}

/**
 * 加载指定Agent的提示词
 */
async function loadAgentPrompts(agentType) {
    promptsData.currentAgent = agentType;
    const editorArea = document.getElementById('prompt-editor-area');
    
    editorArea.innerHTML = `
        <div style="display: flex; align-items: center; justify-content: center; height: 100%; color: var(--text-secondary);">
            <div style="text-align: center;">
                <i class="ri-loader-4-line" style="font-size: 32px;"></i>
                <p style="margin-top: 12px;">加载提示词...</p>
            </div>
        </div>
    `;
    
    try {
        const response = await fetch(promptApiUrl(agentType));
        const data = await response.json();
        
        if (!data.success) {
            throw new Error(data.error || '加载失败');
        }
        
        renderPromptEditor(data);
        
    } catch (e) {
        editorArea.innerHTML = `
            <div style="display: flex; align-items: center; justify-content: center; height: 100%; color: #ef4444;">
                <div style="text-align: center;">
                    <i class="ri-error-warning-line" style="font-size: 32px;"></i>
                    <p style="margin-top: 12px;">加载失败: ${e.message}</p>
                </div>
            </div>
        `;
    }
}

/**
 * 渲染提示词编辑器
 */
function renderPromptEditor(data) {
    const editorArea = document.getElementById('prompt-editor-area');
    const agentType = data.agent_type;
    
    editorArea.innerHTML = `
        <div style="display: flex; flex-direction: column; height: 100%;">
            <!-- 头部 -->
            <div style="padding: 16px 20px; border-bottom: 1px solid var(--border-color); background: rgba(0,0,0,0.1);">
                <div style="display: flex; justify-content: space-between; align-items: center;">
                    <h3 style="color: var(--text-primary); margin: 0; font-size: 16px;">
                        <i class="${getAgentIcon(agentType)}" style="margin-right: 8px;"></i>
                        ${getAgentDisplayName(agentType)}
                    </h3>
                    <button id="reload-prompts-btn" style="padding: 6px 12px; background: rgba(255,255,255,0.1); border: 1px solid var(--border-color); color: var(--text-primary); border-radius: 6px; cursor: pointer; font-size: 12px;">
                        <i class="ri-refresh-line"></i> 刷新
                    </button>
                </div>
            </div>
            
            <!-- 标签页 -->
            <div style="display: flex; border-bottom: 1px solid var(--border-color);">
                <div class="prompt-tab active" data-tab="system" style="padding: 12px 20px; cursor: pointer; border-bottom: 2px solid var(--accent-color); color: var(--text-primary); font-size: 14px;">
                    系统提示词
                </div>
                <div class="prompt-tab" data-tab="tasks" style="padding: 12px 20px; cursor: pointer; border-bottom: 2px solid transparent; color: var(--text-secondary); font-size: 14px;">
                    任务提示词 (${data.tasks ? data.tasks.length : 0})
                </div>
            </div>
            
            <!-- 内容区 -->
            <div id="prompt-tab-content" style="flex: 1; overflow-y: auto; padding: 20px;">
                ${renderSystemPromptTab(data.system_prompt, agentType, data.has_custom && data.has_custom.system)}
            </div>
        </div>
    `;
    
    // 绑定刷新按钮
    document.getElementById('reload-prompts-btn').addEventListener('click', () => {
        loadAgentPrompts(agentType);
    });
    
    // 绑定标签页切换
    editorArea.querySelectorAll('.prompt-tab').forEach(tab => {
        tab.addEventListener('click', () => {
            editorArea.querySelectorAll('.prompt-tab').forEach(t => {
                t.classList.remove('active');
                t.style.borderBottomColor = 'transparent';
                t.style.color = 'var(--text-secondary)';
            });
            tab.classList.add('active');
            tab.style.borderBottomColor = 'var(--accent-color)';
            tab.style.color = 'var(--text-primary)';
            
            const contentArea = document.getElementById('prompt-tab-content');
            if (tab.dataset.tab === 'system') {
                contentArea.innerHTML = renderSystemPromptTab(data.system_prompt, agentType, data.has_custom && data.has_custom.system);
                bindSystemPromptEvents(agentType);
            } else {
                contentArea.innerHTML = renderTasksPromptTab(data.tasks, agentType, data.has_custom);
                bindTasksPromptEvents(agentType, data.tasks);
            }
        });
    });
    
    // 初始绑定事件
    bindSystemPromptEvents(agentType);
}

/**
 * 渲染系统提示词标签页
 */
function renderSystemPromptTab(systemPrompt, agentType, isCustom) {
    return `
        <div>
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px;">
                <label style="font-size: 13px; color: var(--text-secondary);">
                    系统提示词 (System Prompt)
                    ${isCustom ? '<span style="color: #f59e0b; margin-left: 8px;">✎ 已自定义</span>' : ''}
                </label>
                <div style="display: flex; gap: 8px;">
                    <button id="reset-system-prompt" style="padding: 6px 12px; background: rgba(239, 68, 68, 0.15); border: 1px solid rgba(239, 68, 68, 0.4); color: #ef4444; border-radius: 6px; cursor: pointer; font-size: 12px;">
                        <i class="ri-arrow-go-back-line"></i> 恢复默认提示词
                    </button>
                    <button id="save-system-prompt" style="padding: 6px 16px; background: var(--accent-color); border: none; color: white; border-radius: 6px; cursor: pointer; font-size: 12px; font-weight: 500;">
                        <i class="ri-save-line"></i> 保存
                    </button>
                </div>
            </div>
            <textarea id="system-prompt-editor" rows="20" 
                style="width: 100%; background: rgba(0,0,0,0.3); border: 1px solid var(--border-color); padding: 16px; color: var(--text-primary); border-radius: 8px; font-size: 14px; line-height: 1.6; resize: vertical; font-family: 'Consolas', 'Monaco', monospace;"
                placeholder="输入系统提示词...">${escapeHtml(systemPrompt || '')}</textarea>
            <p style="font-size: 11px; color: var(--text-secondary); margin-top: 8px;">
                💡 系统提示词定义了Agent的角色和行为规范，会在每次对话开始时发送给AI模型。
            </p>
        </div>
    `;
}

/**
 * 渲染任务提示词标签页
 */
function renderTasksPromptTab(tasks, agentType, hasCustomMap) {
    const taskList = Array.isArray(tasks) ? tasks : [];
    const taskCards = taskList.length === 0
        ? `
            <div style="text-align: center; padding: 40px; color: var(--text-secondary);">
                <i class="ri-file-list-line" style="font-size: 48px; opacity: 0.3;"></i>
                <p style="margin-top: 16px;">该Agent没有定义任务提示词</p>
            </div>
        `
        : taskList.map(task => {
            const hasDefault = task.has_default !== false;
            const hasCustom = Boolean(hasCustomMap && hasCustomMap[task.name]);
            const resetButton = hasDefault || hasCustom
                ? `
                    <button class="reset-task-btn" data-reset-label="${hasDefault ? '恢复默认提示词' : '删除自定义提示词'}" style="padding: 6px 12px; background: rgba(239, 68, 68, 0.15); border: 1px solid rgba(239, 68, 68, 0.4); color: #ef4444; border-radius: 6px; cursor: pointer; font-size: 12px;">
                        <i class="ri-arrow-go-back-line"></i> ${hasDefault ? '恢复默认提示词' : '删除自定义提示词'}
                    </button>
                `
                : '';
            return `
            <div class="task-prompt-card" data-task="${escapeAttributeValue(task.name)}"
                style="background: rgba(0,0,0,0.2); border: 1px solid var(--border-color); border-radius: 10px; overflow: hidden;">
                <div style="padding: 14px 16px; border-bottom: 1px solid var(--border-color); display: flex; justify-content: space-between; align-items: center; cursor: pointer;" onclick="toggleTaskCard(this)">
                    <div style="display: flex; align-items: center; gap: 10px;">
                        <i class="ri-arrow-right-s-line task-arrow" style="transition: transform 0.2s;"></i>
                        <span style="font-weight: 500; color: var(--text-primary);">${escapeHtml(task.display_name || task.name)}</span>
                        ${hasCustom ? '<span style="color: #f59e0b; font-size: 11px; margin-left: 8px;">✎ 已自定义</span>' : ''}
                    </div>
                    <span style="font-size: 11px; color: var(--text-secondary);">${escapeHtml(task.description || '')}</span>
                </div>
                <div class="task-content" style="display: none; padding: 16px;">
                    <textarea class="task-prompt-editor" rows="10"
                        style="width: 100%; background: rgba(0,0,0,0.2); border: 1px solid var(--border-color); padding: 12px; color: var(--text-primary); border-radius: 6px; font-size: 13px; line-height: 1.5; resize: vertical; font-family: 'Consolas', 'Monaco', monospace;"
                        placeholder="输入任务提示词...">${escapeHtml(task.prompt || '')}</textarea>
                    <div style="display: flex; justify-content: flex-end; gap: 8px; margin-top: 12px;">
                        ${resetButton}
                        <button class="save-task-btn" style="padding: 6px 16px; background: var(--accent-color); border: none; color: white; border-radius: 6px; cursor: pointer; font-size: 12px; font-weight: 500;">
                            <i class="ri-save-line"></i> 保存
                        </button>
                    </div>
                </div>
            </div>
        `;
        }).join('');

    return `
        <div style="display: flex; flex-direction: column; gap: 16px;">
            <div style="display: flex; justify-content: space-between; align-items: center; gap: 12px;">
                <div style="font-size: 13px; color: var(--text-secondary);">任务提示词</div>
                <button id="add-task-prompt-btn" style="padding: 8px 14px; background: var(--accent-color); border: none; color: white; border-radius: 6px; cursor: pointer; font-size: 12px; font-weight: 500; white-space: nowrap;">
                    <i class="ri-add-line"></i> 新增任务提示词
                </button>
            </div>
            ${taskCards}
        </div>
    `;
}

/**
 * 切换任务卡片展开/收起
 */
function toggleTaskCard(header) {
    const card = header.parentElement;
    const content = card.querySelector('.task-content');
    const arrow = card.querySelector('.task-arrow');
    
    if (content.style.display === 'none') {
        content.style.display = 'block';
        arrow.style.transform = 'rotate(90deg)';
    } else {
        content.style.display = 'none';
        arrow.style.transform = 'rotate(0deg)';
    }
}

/**
 * 绑定系统提示词事件
 */
function bindSystemPromptEvents(agentType) {
    const saveBtn = document.getElementById('save-system-prompt');
    const resetBtn = document.getElementById('reset-system-prompt');
    const editor = document.getElementById('system-prompt-editor');
    
    if (saveBtn && editor) {
        saveBtn.addEventListener('click', async () => {
            const content = editor.value;
            saveBtn.innerHTML = '<i class="ri-loader-4-line"></i> 保存中...';
            saveBtn.disabled = true;
            
            try {
            const response = await fetch(promptApiUrl(agentType, 'system'), {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ content })
                });
                const data = await response.json();
                
                if (data.success) {
                    showToast('系统提示词已保存 ✓');
                    // 刷新
                    loadAgentPrompts(agentType);
                } else {
                    throw new Error(data.error || '保存失败');
                }
            } catch (e) {
                showToast('保存失败: ' + e.message, 'error');
            } finally {
                saveBtn.innerHTML = '<i class="ri-save-line"></i> 保存';
                saveBtn.disabled = false;
            }
        });
    }
    
    if (resetBtn) {
        resetBtn.addEventListener('click', async () => {
            if (!(await window.showConfirmDialog('确定要恢复默认系统提示词吗？\n\n您的自定义修改将被删除。'))) {
                return;
            }          
            resetBtn.innerHTML = '<i class="ri-loader-4-line"></i> 恢复中...';
            resetBtn.disabled = true;
            
            try {
            const response = await fetch(promptApiUrl(agentType, 'system'), {
                    method: 'DELETE'
                });
                const data = await response.json();
                
                if (data.success) {
                    showToast('已恢复默认系统提示词');
                    loadAgentPrompts(agentType);
                } else {
                    throw new Error(data.error || '恢复失败');
                }
            } catch (e) {
                showToast('恢复失败: ' + e.message, 'error');
            } finally {
                resetBtn.innerHTML = '<i class="ri-arrow-go-back-line"></i> 恢复默认提示词';
                resetBtn.disabled = false;
            }
        });
    }
}

/**
 * 绑定任务提示词事件
 */
function bindTasksPromptEvents(agentType, tasks) {
    const addTaskBtn = document.getElementById('add-task-prompt-btn');
    if (addTaskBtn) {
        addTaskBtn.addEventListener('click', () => showAddTaskPromptDialog(agentType));
    }

    document.querySelectorAll('.task-prompt-card').forEach(card => {
        const taskName = card.dataset.task;
        const saveBtn = card.querySelector('.save-task-btn');
        const resetBtn = card.querySelector('.reset-task-btn');
        const editor = card.querySelector('.task-prompt-editor');
        
        if (saveBtn && editor) {
            saveBtn.addEventListener('click', async () => {
                const content = editor.value;
                saveBtn.innerHTML = '<i class="ri-loader-4-line"></i> 保存中...';
                saveBtn.disabled = true;
                
                try {
                    const response = await fetch(promptApiUrl(agentType, taskName), {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ content })
                    });
                    const data = await response.json();
                    
                    if (data.success) {
                        showToast(`任务提示词「${taskName}」已保存 ✓`);
                        loadAgentPrompts(agentType);
                    } else {
                        throw new Error(data.error || '保存失败');
                    }
                } catch (e) {
                    showToast('保存失败: ' + e.message, 'error');
                } finally {
                    saveBtn.innerHTML = '<i class="ri-save-line"></i> 保存';
                    saveBtn.disabled = false;
                }
            });
        }
        
        if (resetBtn) {
            resetBtn.addEventListener('click', async () => {
                const resetLabel = resetBtn.dataset.resetLabel || '恢复默认提示词';
                const isRestore = resetLabel.includes('恢复');
                const confirmText = isRestore
                    ? `确定要恢复默认提示词「${taskName}」吗？\n\n您的自定义修改将被删除。`
                    : `确定要删除自定义提示词「${taskName}」吗？`;
                if (!(await window.showConfirmDialog(confirmText))) {
                    return;
                }
                
                resetBtn.innerHTML = '<i class="ri-loader-4-line"></i> 恢复中...';
                resetBtn.disabled = true;
                
                try {
                    const response = await fetch(promptApiUrl(agentType, taskName), {
                        method: 'DELETE'
                    });
                    const data = await response.json();
                    
                    if (data.success) {
                        showToast(isRestore ? `已恢复默认提示词「${taskName}」` : `已删除自定义提示词「${taskName}」`);
                        loadAgentPrompts(agentType);
                    } else {
                        throw new Error(data.error || '恢复失败');
                    }
                } catch (e) {
                    showToast('恢复失败: ' + e.message, 'error');
                } finally {
                    resetBtn.innerHTML = `<i class="ri-arrow-go-back-line"></i> ${resetLabel}`;
                    resetBtn.disabled = false;
                }
            });
        }
    });
}

function showAddTaskPromptDialog(agentType) {
    const modal = document.getElementById('modal-container');
    if (!modal) {
        showToast('无法打开弹窗', 'error');
        return;
    }

    modal.classList.remove('hidden');
    modal.innerHTML = `
        <div style="position: fixed; inset: 0; background: rgba(0,0,0,0.6); display: flex; align-items: center; justify-content: center; z-index: 1000;">
            <div style="background: var(--bg-panel); border: 1px solid var(--border-color); border-radius: 14px; padding: 24px; width: 680px; max-width: 94%; max-height: 90vh; overflow-y: auto;">
                <h3 style="color: var(--text-primary); margin: 0 0 20px; font-size: 18px; display: flex; align-items: center; gap: 8px;">
                    <i class="ri-file-add-line"></i>
                    新增任务提示词
                </h3>
                <div style="margin-bottom: 16px;">
                    <label style="display: block; font-size: 12px; color: var(--text-secondary); margin-bottom: 8px;">任务名称</label>
                    <input id="new-task-prompt-name" type="text" placeholder="例如：custom_revision 或 角色成长检查"
                        style="width: 100%; background: rgba(0,0,0,0.3); border: 1px solid var(--border-color); padding: 12px; color: var(--text-primary); border-radius: 8px; font-size: 14px;">
                </div>
                <div style="margin-bottom: 20px;">
                    <label style="display: block; font-size: 12px; color: var(--text-secondary); margin-bottom: 8px;">提示词内容</label>
                    <textarea id="new-task-prompt-content" rows="12" placeholder="输入该任务的完整提示词..."
                        style="width: 100%; background: rgba(0,0,0,0.3); border: 1px solid var(--border-color); padding: 12px; color: var(--text-primary); border-radius: 8px; font-size: 13px; line-height: 1.5; resize: vertical; font-family: 'Consolas', 'Monaco', monospace;"></textarea>
                </div>
                <div style="display: flex; justify-content: flex-end; gap: 10px;">
                    <button id="cancel-add-task-prompt" style="padding: 10px 16px; background: rgba(255,255,255,0.08); border: 1px solid var(--border-color); color: var(--text-primary); border-radius: 8px; cursor: pointer;">取消</button>
                    <button id="confirm-add-task-prompt" style="padding: 10px 18px; background: var(--accent-color); border: none; color: white; border-radius: 8px; cursor: pointer; font-weight: 600;">
                        <i class="ri-save-line"></i> 保存
                    </button>
                </div>
            </div>
        </div>
    `;

    const closeModal = () => {
        modal.classList.add('hidden');
        modal.innerHTML = '';
    };

    document.getElementById('cancel-add-task-prompt')?.addEventListener('click', closeModal);
    document.getElementById('confirm-add-task-prompt')?.addEventListener('click', async () => {
        const taskName = document.getElementById('new-task-prompt-name')?.value.trim() || '';
        const content = document.getElementById('new-task-prompt-content')?.value || '';

        if (!/^[\w\u4e00-\u9fff.-]{1,80}$/.test(taskName)) {
            showToast('任务名称只能包含中英文、数字、下划线、短横线和点号', 'error');
            return;
        }
        if (!content.trim()) {
            showToast('请输入提示词内容', 'error');
            return;
        }

        const confirmBtn = document.getElementById('confirm-add-task-prompt');
        if (confirmBtn) {
            confirmBtn.innerHTML = '<i class="ri-loader-4-line"></i> 保存中...';
            confirmBtn.disabled = true;
        }

        try {
            const response = await fetch(promptApiUrl(agentType, taskName), {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ content })
            });
            const data = await response.json();
            if (!data.success) {
                throw new Error(data.error || data.detail || '保存失败');
            }
            closeModal();
            showToast(`任务提示词「${taskName}」已创建 ✓`);
            loadAgentPrompts(agentType);
            loadAgentList();
        } catch (e) {
            showToast('保存失败: ' + e.message, 'error');
        } finally {
            if (confirmBtn) {
                confirmBtn.innerHTML = '<i class="ri-save-line"></i> 保存';
                confirmBtn.disabled = false;
            }
        }
    });

    setTimeout(() => document.getElementById('new-task-prompt-name')?.focus(), 50);
}

/**
 * 获取Agent显示名称
 */
function getAgentDisplayName(agentType) {
    const names = {
        'communicator': '创作沟通助手',
        'worldbuilder': '世界观设定师',
        'outliner': '全书大纲规划师',
        'CharacterBuilder': '角色构建师',
        'EventlineBuilder': '事件线构建师',
        'DetailOutlineBuilder': '细纲构建师',
        'ChapterSettingBuilder': '章纲设定师',
        'short_story': '短篇创作流程',
        'chapter_writer': '章节正文写手',
        'polisher': '正文润色师',
        'evaluator': '质检评估师',
        'continuous_writer': '无限续写正文写手',
        'ContentExpansion': '正文扩写师',
        'SummaryOrchestrator': '摘要编排器',
        'copilot': '山海·云烟创作助手'
    };
    return names[agentType] || agentType;
}

/**
 * HTML转义
 */
function escapeHtml(text) {
    if (!text) return '';
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

function escapeAttributeValue(value) {
    return String(value ?? '')
        .replace(/&/g, '&amp;')
        .replace(/"/g, '&quot;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;');
}

// 导出到全局
window.loadPromptSettings = loadPromptSettings;
window.toggleTaskCard = toggleTaskCard;
window.showAddTaskPromptDialog = showAddTaskPromptDialog;

console.log('[PromptManager] 提示词管理模块已完成加载并导出到全局');

})(); // IIFE 结束
