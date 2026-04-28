/**
 * 文思Agent - Token消耗统计模块
 * 提供Token使用量的可视化统计界面
 */

// Agent英文名到中文名的映射
const AGENT_DISPLAY_NAMES = {
    // 主要Agent
    'Communicator': '沟通助手',
    'Worldbuilder': '世界观构建',
    'Outliner': '大纲规划',
    'ChapterWriter': '章节撰写',
    'Polisher': '文字润色',
    'Evaluator': '质量评估',
    'ContinuousWriter': '无限续写',
    // 备用映射
    'Router': '智能路由',
    'RouterAgent': '智能路由',
    'Writer': '写作',
    'DefaultHandler': '默认处理',
    'default': '默认处理',
    'Default': '默认处理',
    // 对话相关
    'Chat': '对话助手',
    'ChatAgent': '对话助手',
    'ChatbotAgent': '智能对话',
    'Chatbot': '智能对话',
    // 其他可能的名称
    'Assistant': '助手',
    'Unknown': '未知',
    'unknown': '未知',
    'System': '系统',
    'system': '系统'
};

// 获取Agent的中文显示名称
function getAgentDisplayName(agentName) {
    return AGENT_DISPLAY_NAMES[agentName] || agentName;
}

// Token统计状态
const tokenStatsState = {
    currentView: 'summary',  // summary | daily | weekly | hourly | models | agents
    filterModel: '',
    filterAgent: '',
    availableModels: [],
    availableAgents: []
};

// 加载筛选选项
async function loadTokenStatsFilters() {
    try {
        const res = await fetch(normalizeApiUrl('/api/v1/token-stats/filters'));
        const data = await res.json();
        tokenStatsState.availableModels = data.models || [];
        tokenStatsState.availableAgents = data.agents || [];
    } catch (e) {
        console.error('加载筛选选项失败:', e);
    }
}

// 渲染Token统计主页面
async function renderTokenStats() {
    updateBreadcrumbs([store.currentProjectName || '我的项目', 'Token统计']);
    
    // 加载筛选选项
    await loadTokenStatsFilters();
    
    // 渲染主界面
    ui.workspace.innerHTML = `
        <div class="token-stats-container" style="padding: 30px; max-width: 1200px; margin: 0 auto;">
            <div class="token-stats-header" style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 24px;">
                <h2 style="color: var(--text-primary); font-size: 20px; display: flex; align-items: center; gap: 10px; margin: 0;">
                    <i class="ri-coin-line"></i>
                    Token 消耗统计
                </h2>
                <div class="token-stats-filters" style="display: flex; gap: 12px; align-items: center;">
                    <select id="filter-model" style="padding: 8px 12px; border-radius: 8px; border: 1px solid var(--border-color); background: var(--bg-secondary); color: var(--text-primary); min-width: 160px;">
                        <option value="">全部模型</option>
                        ${tokenStatsState.availableModels.map(m => `<option value="${m}" ${tokenStatsState.filterModel === m ? 'selected' : ''}>${m}</option>`).join('')}
                    </select>
                    <select id="filter-agent" style="padding: 8px 12px; border-radius: 8px; border: 1px solid var(--border-color); background: var(--bg-secondary); color: var(--text-primary); min-width: 160px;">
                        <option value="">全部Agent</option>
                        ${tokenStatsState.availableAgents.map(a => `<option value="${a}" ${tokenStatsState.filterAgent === a ? 'selected' : ''}>${getAgentDisplayName(a)}</option>`).join('')}
                    </select>
                    <button id="reset-token-stats" style="padding: 8px 16px; border-radius: 8px; border: 1px solid rgba(239, 68, 68, 0.5); background: rgba(239, 68, 68, 0.1); color: #ef4444; cursor: pointer; display: flex; align-items: center; gap: 6px; font-size: 13px;" title="清空所有统计数据">
                        <i class="ri-delete-bin-line"></i> 重置
                    </button>
                </div>
            </div>
            
            <!-- 视图切换标签 -->
            <div class="token-stats-tabs" style="display: flex; gap: 8px; margin-bottom: 24px; border-bottom: 1px solid var(--border-color); padding-bottom: 12px;">
                <button class="tab-btn ${tokenStatsState.currentView === 'summary' ? 'active' : ''}" data-view="summary" style="padding: 8px 16px; border: none; background: ${tokenStatsState.currentView === 'summary' ? 'var(--accent-color)' : 'transparent'}; color: ${tokenStatsState.currentView === 'summary' ? 'white' : 'var(--text-secondary)'}; border-radius: 6px; cursor: pointer; font-size: 13px;">
                    <i class="ri-dashboard-line"></i> 概览
                </button>
                <button class="tab-btn ${tokenStatsState.currentView === 'hourly' ? 'active' : ''}" data-view="hourly" style="padding: 8px 16px; border: none; background: ${tokenStatsState.currentView === 'hourly' ? 'var(--accent-color)' : 'transparent'}; color: ${tokenStatsState.currentView === 'hourly' ? 'white' : 'var(--text-secondary)'}; border-radius: 6px; cursor: pointer; font-size: 13px;">
                    <i class="ri-time-line"></i> 24小时
                </button>
                <button class="tab-btn ${tokenStatsState.currentView === 'weekly' ? 'active' : ''}" data-view="weekly" style="padding: 8px 16px; border: none; background: ${tokenStatsState.currentView === 'weekly' ? 'var(--accent-color)' : 'transparent'}; color: ${tokenStatsState.currentView === 'weekly' ? 'white' : 'var(--text-secondary)'}; border-radius: 6px; cursor: pointer; font-size: 13px;">
                    <i class="ri-calendar-2-line"></i> 每周
                </button>
                <button class="tab-btn ${tokenStatsState.currentView === 'models' ? 'active' : ''}" data-view="models" style="padding: 8px 16px; border: none; background: ${tokenStatsState.currentView === 'models' ? 'var(--accent-color)' : 'transparent'}; color: ${tokenStatsState.currentView === 'models' ? 'white' : 'var(--text-secondary)'}; border-radius: 6px; cursor: pointer; font-size: 13px;">
                    <i class="ri-robot-line"></i> 按模型
                </button>
                <button class="tab-btn ${tokenStatsState.currentView === 'agents' ? 'active' : ''}" data-view="agents" style="padding: 8px 16px; border: none; background: ${tokenStatsState.currentView === 'agents' ? 'var(--accent-color)' : 'transparent'}; color: ${tokenStatsState.currentView === 'agents' ? 'white' : 'var(--text-secondary)'}; border-radius: 6px; cursor: pointer; font-size: 13px;">
                    <i class="ri-user-settings-line"></i> 按Agent
                </button>
            </div>
            
            <!-- 内容区域 -->
            <div id="token-stats-content" style="min-height: 400px;">
                <div style="display: flex; justify-content: center; align-items: center; height: 200px; color: var(--text-secondary);">
                    <i class="ri-loader-4-line" style="font-size: 24px; animation: spin 1s linear infinite;"></i>
                    <span style="margin-left: 10px;">加载中...</span>
                </div>
            </div>
        </div>
        <style>
            @keyframes spin {
                from { transform: rotate(0deg); }
                to { transform: rotate(360deg); }
            }
        </style>
    `;
    
    // 绑定事件
    document.querySelectorAll('.tab-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            tokenStatsState.currentView = btn.dataset.view;
            renderTokenStats();
        });
    });
    
    document.getElementById('filter-model').addEventListener('change', (e) => {
        tokenStatsState.filterModel = e.target.value;
        loadTokenStatsContent();
    });
    
    document.getElementById('filter-agent').addEventListener('change', (e) => {
        tokenStatsState.filterAgent = e.target.value;
        loadTokenStatsContent();
    });
    
    // 重置按钮
    document.getElementById('reset-token-stats').addEventListener('click', async () => {
        if (!confirm('确定要清空所有Token统计数据吗？\n\n⚠️ 此操作不可恢复！所有历史统计数据将被永久删除。')) {
            return;
        }
        
        try {
            // 使用专门的reset API，确保清空所有数据
            const res = await fetch('/api/token-stats/reset', { method: 'POST' });
            const result = await res.json();
            if (result.success) {
                showToast(`✅ 已重置统计数据，共清空 ${result.deleted_count || 0} 条记录`, 'success');
                // 重新加载筛选选项（因为模型和Agent列表可能已清空）
                await loadTokenStatsFilters();
                // 重新加载内容
                loadTokenStatsContent();
            } else {
                showToast('重置失败: ' + (result.error || '未知错误'), 'error');
            }
        } catch (e) {
            showToast('重置失败: ' + e.message, 'error');
        }
    });
    
    // 加载内容
    loadTokenStatsContent();
}

// 加载统计内容
async function loadTokenStatsContent() {
    const container = document.getElementById('token-stats-content');
    if (!container) return;
    
    container.innerHTML = `
        <div style="display: flex; justify-content: center; align-items: center; height: 200px; color: var(--text-secondary);">
            <i class="ri-loader-4-line" style="font-size: 24px; animation: spin 1s linear infinite;"></i>
            <span style="margin-left: 10px;">加载中...</span>
        </div>
    `;
    
    try {
        switch (tokenStatsState.currentView) {
            case 'summary':
                await renderTokenStatsSummary(container);
                break;
            case 'hourly':
                await renderTokenStatsHourly(container);
                break;
            case 'weekly':
                await renderTokenStatsWeekly(container);
                break;
            case 'models':
                await renderTokenStatsByModel(container);
                break;
            case 'agents':
                await renderTokenStatsByAgent(container);
                break;
        }
    } catch (e) {
        console.error('加载Token统计失败:', e);
        container.innerHTML = `
            <div style="text-align: center; padding: 40px; color: var(--text-secondary);">
                <i class="ri-error-warning-line" style="font-size: 40px; opacity: 0.5;"></i>
                <p style="margin-top: 12px;">加载失败: ${e.message}</p>
                <button onclick="loadTokenStatsContent()" style="margin-top: 12px; padding: 8px 16px; background: var(--accent-color); border: none; color: white; border-radius: 6px; cursor: pointer;">重试</button>
            </div>
        `;
    }
}

// 构建查询参数
function buildQueryParams() {
    const params = new URLSearchParams();
    if (tokenStatsState.filterModel) {
        params.append('model', tokenStatsState.filterModel);
    }
    if (tokenStatsState.filterAgent) {
        params.append('agent_name', tokenStatsState.filterAgent);
    }
    return params.toString() ? '?' + params.toString() : '';
}

// 渲染概览
async function renderTokenStatsSummary(container) {
    const res = await fetch('/api/token-stats/summary' + buildQueryParams() + (buildQueryParams() ? '&' : '?') + 'days=30');
    const summary = await res.json();
    
    // 同时加载今日数据
    const todayRes = await fetch('/api/token-stats/summary' + buildQueryParams() + (buildQueryParams() ? '&' : '?') + 'days=1');
    const today = await todayRes.json();
    
    container.innerHTML = `
        <!-- 今日统计 -->
        <div style="margin-bottom: 24px;">
            <h3 style="color: var(--text-primary); font-size: 15px; margin-bottom: 16px; display: flex; align-items: center; gap: 8px;">
                <i class="ri-sun-line"></i> 今日统计
            </h3>
            <div style="display: grid; grid-template-columns: repeat(4, 1fr); gap: 16px;">
                <div class="stat-card" style="background: linear-gradient(135deg, rgba(99, 102, 241, 0.1), rgba(139, 92, 246, 0.1)); border: 1px solid rgba(99, 102, 241, 0.2); border-radius: 12px; padding: 20px; text-align: center;">
                    <div style="font-size: 28px; font-weight: bold; color: #818cf8;">${(today.total_tokens || 0).toLocaleString()}</div>
                    <div style="font-size: 12px; color: var(--text-secondary); margin-top: 6px;">总Token</div>
                </div>
                <div class="stat-card" style="background: linear-gradient(135deg, rgba(34, 197, 94, 0.1), rgba(16, 185, 129, 0.1)); border: 1px solid rgba(34, 197, 94, 0.2); border-radius: 12px; padding: 20px; text-align: center;">
                    <div style="font-size: 28px; font-weight: bold; color: #4ade80;">${(today.tokens_in || 0).toLocaleString()}</div>
                    <div style="font-size: 12px; color: var(--text-secondary); margin-top: 6px;">输入Token</div>
                </div>
                <div class="stat-card" style="background: linear-gradient(135deg, rgba(251, 146, 60, 0.1), rgba(249, 115, 22, 0.1)); border: 1px solid rgba(251, 146, 60, 0.2); border-radius: 12px; padding: 20px; text-align: center;">
                    <div style="font-size: 28px; font-weight: bold; color: #fb923c;">${(today.tokens_out || 0).toLocaleString()}</div>
                    <div style="font-size: 12px; color: var(--text-secondary); margin-top: 6px;">输出Token</div>
                </div>
                <div class="stat-card" style="background: linear-gradient(135deg, rgba(236, 72, 153, 0.1), rgba(219, 39, 119, 0.1)); border: 1px solid rgba(236, 72, 153, 0.2); border-radius: 12px; padding: 20px; text-align: center;">
                    <div style="font-size: 28px; font-weight: bold; color: #f472b6;">${today.call_count || 0}</div>
                    <div style="font-size: 12px; color: var(--text-secondary); margin-top: 6px;">调用次数</div>
                </div>
            </div>
        </div>
        
        <!-- 30天统计 -->
        <div style="margin-bottom: 24px;">
            <h3 style="color: var(--text-primary); font-size: 15px; margin-bottom: 16px; display: flex; align-items: center; gap: 8px;">
                <i class="ri-calendar-check-line"></i> 近30天统计
            </h3>
            <div style="display: grid; grid-template-columns: repeat(4, 1fr); gap: 16px;">
                <div class="stat-card" style="background: rgba(255,255,255,0.03); border: 1px solid var(--border-color); border-radius: 12px; padding: 20px; text-align: center;">
                    <div style="font-size: 28px; font-weight: bold; color: var(--accent-color);">${(summary.total_tokens || 0).toLocaleString()}</div>
                    <div style="font-size: 12px; color: var(--text-secondary); margin-top: 6px;">总Token消耗</div>
                </div>
                <div class="stat-card" style="background: rgba(255,255,255,0.03); border: 1px solid var(--border-color); border-radius: 12px; padding: 20px; text-align: center;">
                    <div style="font-size: 28px; font-weight: bold; color: #10b981;">${summary.call_count || 0}</div>
                    <div style="font-size: 12px; color: var(--text-secondary); margin-top: 6px;">总调用次数</div>
                </div>
                <div class="stat-card" style="background: rgba(255,255,255,0.03); border: 1px solid var(--border-color); border-radius: 12px; padding: 20px; text-align: center;">
                    <div style="font-size: 28px; font-weight: bold; color: #f59e0b;">${Math.round(summary.avg_tokens_per_call || 0).toLocaleString()}</div>
                    <div style="font-size: 12px; color: var(--text-secondary); margin-top: 6px;">平均每次Token</div>
                </div>
                <div class="stat-card" style="background: rgba(255,255,255,0.03); border: 1px solid var(--border-color); border-radius: 12px; padding: 20px; text-align: center;">
                    <div style="font-size: 28px; font-weight: bold; color: #8b5cf6;">${summary.success_rate?.toFixed(1) || 0}%</div>
                    <div style="font-size: 12px; color: var(--text-secondary); margin-top: 6px;">成功率</div>
                </div>
            </div>
        </div>
        
        <!-- 附加信息 -->
        <div style="background: rgba(255,255,255,0.03); border: 1px solid var(--border-color); border-radius: 12px; padding: 20px;">
            <h3 style="color: var(--text-primary); font-size: 15px; margin-bottom: 16px; display: flex; align-items: center; gap: 8px;">
                <i class="ri-information-line"></i> 附加信息
            </h3>
            <div style="display: grid; grid-template-columns: repeat(3, 1fr); gap: 16px;">
                <div style="padding: 12px; background: rgba(255,255,255,0.02); border-radius: 8px;">
                    <div style="font-size: 13px; color: var(--text-secondary);">使用模型数</div>
                    <div style="font-size: 18px; font-weight: 600; color: var(--text-primary); margin-top: 4px;">${summary.model_count || 0}</div>
                </div>
                <div style="padding: 12px; background: rgba(255,255,255,0.02); border-radius: 8px;">
                    <div style="font-size: 13px; color: var(--text-secondary);">活跃Agent数</div>
                    <div style="font-size: 18px; font-weight: 600; color: var(--text-primary); margin-top: 4px;">${summary.agent_count || 0}</div>
                </div>
                <div style="padding: 12px; background: rgba(255,255,255,0.02); border-radius: 8px;">
                    <div style="font-size: 13px; color: var(--text-secondary);">平均响应时间</div>
                    <div style="font-size: 18px; font-weight: 600; color: var(--text-primary); margin-top: 4px;">${summary.avg_duration || 0}s</div>
                </div>
            </div>
        </div>
    `;
}

// 渲染24小时曲线图
async function renderTokenStatsHourly(container) {
    const res = await fetch('/api/token-stats/hourly' + buildQueryParams() + (buildQueryParams() ? '&' : '?') + 'hours=24');
    const data = await res.json();
    const hourlyData = data.data || [];
    
    // 计算最大值用于缩放
    const maxTokens = Math.max(...hourlyData.map(h => h.total_tokens || 0), 1);
    
    container.innerHTML = `
        <div style="background: rgba(255,255,255,0.03); border: 1px solid var(--border-color); border-radius: 12px; padding: 24px;">
            <h3 style="color: var(--text-primary); font-size: 15px; margin-bottom: 20px; display: flex; align-items: center; gap: 8px;">
                <i class="ri-line-chart-line"></i> 24小时Token消耗趋势
            </h3>
            
            <!-- 图例 -->
            <div style="display: flex; gap: 20px; margin-bottom: 20px; font-size: 12px;">
                <div style="display: flex; align-items: center; gap: 6px;">
                    <div style="width: 12px; height: 12px; background: linear-gradient(135deg, #818cf8, #6366f1); border-radius: 2px;"></div>
                    <span style="color: var(--text-secondary);">总Token</span>
                </div>
                <div style="display: flex; align-items: center; gap: 6px;">
                    <div style="width: 12px; height: 12px; background: linear-gradient(135deg, #4ade80, #22c55e); border-radius: 2px;"></div>
                    <span style="color: var(--text-secondary);">输入Token</span>
                </div>
                <div style="display: flex; align-items: center; gap: 6px;">
                    <div style="width: 12px; height: 12px; background: linear-gradient(135deg, #fb923c, #f97316); border-radius: 2px;"></div>
                    <span style="color: var(--text-secondary);">输出Token</span>
                </div>
            </div>
            
            <!-- 图表区域 -->
            <div style="position: relative; height: 300px; padding-left: 50px; padding-bottom: 30px;">
                <!-- Y轴刻度 -->
                <div style="position: absolute; left: 0; top: 0; height: calc(100% - 30px); display: flex; flex-direction: column; justify-content: space-between; font-size: 11px; color: var(--text-secondary);">
                    <span>${maxTokens.toLocaleString()}</span>
                    <span>${Math.round(maxTokens * 0.75).toLocaleString()}</span>
                    <span>${Math.round(maxTokens * 0.5).toLocaleString()}</span>
                    <span>${Math.round(maxTokens * 0.25).toLocaleString()}</span>
                    <span>0</span>
                </div>
                
                <!-- 图表主体 -->
                <div style="display: flex; align-items: flex-end; gap: 2px; height: calc(100% - 30px); padding: 0 10px;">
                    ${hourlyData.map((h, i) => {
                        const heightPercent = maxTokens > 0 ? (h.total_tokens / maxTokens * 100) : 0;
                        const hourLabel = h.hour ? h.hour.split(' ')[1] : `${i}:00`;
                        return `
                            <div style="flex: 1; display: flex; flex-direction: column; align-items: center; gap: 4px;">
                                <div class="bar-tooltip" style="position: relative; width: 100%; min-width: 20px; height: ${heightPercent}%; min-height: ${h.total_tokens > 0 ? '4px' : '0'}; background: linear-gradient(to top, #6366f1, #818cf8); border-radius: 4px 4px 0 0; transition: all 0.3s; cursor: pointer;" title="${hourLabel}: ${h.total_tokens.toLocaleString()} tokens">
                                </div>
                            </div>
                        `;
                    }).join('')}
                </div>
                
                <!-- X轴刻度 -->
                <div style="display: flex; justify-content: space-between; font-size: 10px; color: var(--text-secondary); padding: 8px 10px 0;">
                    ${hourlyData.filter((_, i) => i % 4 === 0).map(h => `<span>${h.hour ? h.hour.split(' ')[1] : ''}</span>`).join('')}
                </div>
            </div>
        </div>
        
        <!-- 数据表格 -->
        <div style="background: rgba(255,255,255,0.03); border: 1px solid var(--border-color); border-radius: 12px; padding: 24px; margin-top: 20px;">
            <h3 style="color: var(--text-primary); font-size: 15px; margin-bottom: 16px;">详细数据</h3>
            <div style="max-height: 300px; overflow-y: auto;">
                <table style="width: 100%; border-collapse: collapse; font-size: 13px;">
                    <thead style="position: sticky; top: 0; background: var(--bg-primary);">
                        <tr style="border-bottom: 1px solid var(--border-color);">
                            <th style="text-align: left; padding: 10px 8px; color: var(--text-secondary); font-weight: 500;">时间</th>
                            <th style="text-align: right; padding: 10px 8px; color: var(--text-secondary); font-weight: 500;">总Token</th>
                            <th style="text-align: right; padding: 10px 8px; color: var(--text-secondary); font-weight: 500;">输入</th>
                            <th style="text-align: right; padding: 10px 8px; color: var(--text-secondary); font-weight: 500;">输出</th>
                            <th style="text-align: right; padding: 10px 8px; color: var(--text-secondary); font-weight: 500;">调用次数</th>
                        </tr>
                    </thead>
                    <tbody>
                        ${hourlyData.slice().reverse().map(h => `
                            <tr style="border-bottom: 1px solid rgba(255,255,255,0.05);">
                                <td style="padding: 10px 8px; color: var(--text-primary);">${h.hour || '-'}</td>
                                <td style="padding: 10px 8px; text-align: right; color: #818cf8; font-weight: 500;">${(h.total_tokens || 0).toLocaleString()}</td>
                                <td style="padding: 10px 8px; text-align: right; color: #4ade80;">${(h.tokens_in || 0).toLocaleString()}</td>
                                <td style="padding: 10px 8px; text-align: right; color: #fb923c;">${(h.tokens_out || 0).toLocaleString()}</td>
                                <td style="padding: 10px 8px; text-align: right; color: var(--text-secondary);">${h.call_count || 0}</td>
                            </tr>
                        `).join('')}
                    </tbody>
                </table>
            </div>
        </div>
    `;
}

// 渲染每周统计
async function renderTokenStatsWeekly(container) {
    const res = await fetch('/api/token-stats/weekly' + buildQueryParams() + (buildQueryParams() ? '&' : '?') + 'weeks=8');
    const data = await res.json();
    const weeklyData = data.data || [];
    
    const maxTokens = Math.max(...weeklyData.map(w => w.total_tokens || 0), 1);
    
    container.innerHTML = `
        <div style="background: rgba(255,255,255,0.03); border: 1px solid var(--border-color); border-radius: 12px; padding: 24px;">
            <h3 style="color: var(--text-primary); font-size: 15px; margin-bottom: 20px; display: flex; align-items: center; gap: 8px;">
                <i class="ri-calendar-2-line"></i> 每周Token消耗
            </h3>
            
            <div style="display: flex; flex-direction: column; gap: 16px;">
                ${weeklyData.map(w => {
                    const widthPercent = maxTokens > 0 ? (w.total_tokens / maxTokens * 100) : 0;
                    return `
                        <div style="background: rgba(255,255,255,0.02); border-radius: 8px; padding: 16px;">
                            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px;">
                                <span style="font-size: 14px; font-weight: 500; color: var(--text-primary);">${w.week || '-'}</span>
                                <span style="font-size: 11px; color: var(--text-secondary);">${w.week_start || ''} ~ ${w.week_end || ''}</span>
                            </div>
                            <div style="height: 24px; background: rgba(255,255,255,0.05); border-radius: 6px; overflow: hidden; margin-bottom: 10px;">
                                <div style="height: 100%; width: ${widthPercent}%; background: linear-gradient(90deg, #10b981, #14b8a6); border-radius: 6px;"></div>
                            </div>
                            <div style="display: flex; justify-content: space-between; font-size: 12px;">
                                <span style="color: var(--text-secondary);">调用 ${w.call_count || 0} 次 | 成功率 ${w.success_rate?.toFixed(1) || 0}%</span>
                                <span style="font-weight: 600; color: #10b981;">${(w.total_tokens || 0).toLocaleString()} tokens</span>
                            </div>
                        </div>
                    `;
                }).join('')}
            </div>
            
            ${weeklyData.length === 0 ? `
                <div style="text-align: center; padding: 40px; color: var(--text-secondary);">
                    <i class="ri-inbox-line" style="font-size: 32px; opacity: 0.5;"></i>
                    <p style="margin-top: 12px;">暂无数据</p>
                </div>
            ` : ''}
        </div>
    `;
}

// 渲染按模型统计
async function renderTokenStatsByModel(container) {
    const res = await fetch('/api/token-stats/by-model' + buildQueryParams() + (buildQueryParams() ? '&' : '?') + 'days=30');
    const data = await res.json();
    const modelData = data.data || [];
    
    const totalTokens = modelData.reduce((sum, m) => sum + (m.total_tokens || 0), 0);
    
    container.innerHTML = `
        <div style="background: rgba(255,255,255,0.03); border: 1px solid var(--border-color); border-radius: 12px; padding: 24px;">
            <h3 style="color: var(--text-primary); font-size: 15px; margin-bottom: 20px; display: flex; align-items: center; gap: 8px;">
                <i class="ri-robot-line"></i> 按模型统计（近30天）
            </h3>
            
            <div style="display: grid; gap: 16px;">
                ${modelData.map((m, i) => {
                    const colors = ['#6366f1', '#10b981', '#f59e0b', '#ec4899', '#8b5cf6', '#06b6d4'];
                    const color = colors[i % colors.length];
                    const percent = totalTokens > 0 ? (m.total_tokens / totalTokens * 100) : 0;
                    return `
                        <div style="background: rgba(255,255,255,0.02); border-radius: 10px; padding: 20px; border-left: 4px solid ${color};">
                            <div style="display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 12px;">
                                <div>
                                    <div style="font-size: 15px; font-weight: 600; color: var(--text-primary);">${m.model || '未知模型'}</div>
                                    <div style="font-size: 11px; color: var(--text-secondary); margin-top: 4px;">占比 ${percent.toFixed(1)}%</div>
                                </div>
                                <div style="text-align: right;">
                                    <div style="font-size: 20px; font-weight: bold; color: ${color};">${(m.total_tokens || 0).toLocaleString()}</div>
                                    <div style="font-size: 11px; color: var(--text-secondary);">tokens</div>
                                </div>
                            </div>
                            <div style="display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; font-size: 12px;">
                                <div>
                                    <div style="color: var(--text-secondary);">输入Token</div>
                                    <div style="color: var(--text-primary); font-weight: 500; margin-top: 2px;">${(m.tokens_in || 0).toLocaleString()}</div>
                                </div>
                                <div>
                                    <div style="color: var(--text-secondary);">输出Token</div>
                                    <div style="color: var(--text-primary); font-weight: 500; margin-top: 2px;">${(m.tokens_out || 0).toLocaleString()}</div>
                                </div>
                                <div>
                                    <div style="color: var(--text-secondary);">调用次数</div>
                                    <div style="color: var(--text-primary); font-weight: 500; margin-top: 2px;">${m.call_count || 0}</div>
                                </div>
                                <div>
                                    <div style="color: var(--text-secondary);">成功率</div>
                                    <div style="color: ${m.success_rate >= 90 ? '#22c55e' : m.success_rate >= 70 ? '#f59e0b' : '#ef4444'}; font-weight: 500; margin-top: 2px;">${m.success_rate?.toFixed(1) || 0}%</div>
                                </div>
                            </div>
                        </div>
                    `;
                }).join('')}
            </div>
            
            ${modelData.length === 0 ? `
                <div style="text-align: center; padding: 40px; color: var(--text-secondary);">
                    <i class="ri-inbox-line" style="font-size: 32px; opacity: 0.5;"></i>
                    <p style="margin-top: 12px;">暂无数据</p>
                </div>
            ` : ''}
        </div>
    `;
}

// 渲染按Agent统计
async function renderTokenStatsByAgent(container) {
    const res = await fetch('/api/token-stats/by-agent' + buildQueryParams() + (buildQueryParams() ? '&' : '?') + 'days=30');
    const data = await res.json();
    const agentData = data.data || [];
    
    const totalTokens = agentData.reduce((sum, a) => sum + (a.total_tokens || 0), 0);
    
    container.innerHTML = `
        <div style="background: rgba(255,255,255,0.03); border: 1px solid var(--border-color); border-radius: 12px; padding: 24px;">
            <h3 style="color: var(--text-primary); font-size: 15px; margin-bottom: 20px; display: flex; align-items: center; gap: 8px;">
                <i class="ri-user-settings-line"></i> 按Agent统计（近30天）
            </h3>
            
            <table style="width: 100%; border-collapse: collapse; font-size: 13px;">
                <thead>
                    <tr style="border-bottom: 2px solid var(--border-color);">
                        <th style="text-align: left; padding: 12px 8px; color: var(--text-secondary); font-weight: 500;">Agent名称</th>
                        <th style="text-align: right; padding: 12px 8px; color: var(--text-secondary); font-weight: 500;">总Token</th>
                        <th style="text-align: right; padding: 12px 8px; color: var(--text-secondary); font-weight: 500;">输入</th>
                        <th style="text-align: right; padding: 12px 8px; color: var(--text-secondary); font-weight: 500;">输出</th>
                        <th style="text-align: right; padding: 12px 8px; color: var(--text-secondary); font-weight: 500;">调用次数</th>
                        <th style="text-align: right; padding: 12px 8px; color: var(--text-secondary); font-weight: 500;">成功率</th>
                        <th style="text-align: right; padding: 12px 8px; color: var(--text-secondary); font-weight: 500;">平均耗时</th>
                    </tr>
                </thead>
                <tbody>
                    ${agentData.map(a => `
                        <tr style="border-bottom: 1px solid rgba(255,255,255,0.05);">
                            <td style="padding: 14px 8px;">
                                <div style="display: flex; align-items: center; gap: 8px;">
                                    <div style="width: 32px; height: 32px; background: linear-gradient(135deg, var(--accent-color), #8b5cf6); border-radius: 8px; display: flex; align-items: center; justify-content: center;">
                                        <i class="ri-robot-line" style="color: white; font-size: 14px;"></i>
                                    </div>
                                    <span style="font-weight: 500; color: var(--text-primary);">${getAgentDisplayName(a.agent_name) || '-'}</span>
                                </div>
                            </td>
                            <td style="padding: 14px 8px; text-align: right; font-weight: 600; color: var(--accent-color);">${(a.total_tokens || 0).toLocaleString()}</td>
                            <td style="padding: 14px 8px; text-align: right; color: #4ade80;">${(a.tokens_in || 0).toLocaleString()}</td>
                            <td style="padding: 14px 8px; text-align: right; color: #fb923c;">${(a.tokens_out || 0).toLocaleString()}</td>
                            <td style="padding: 14px 8px; text-align: right; color: var(--text-secondary);">${a.call_count || 0}</td>
                            <td style="padding: 14px 8px; text-align: right; color: ${a.success_rate >= 90 ? '#22c55e' : a.success_rate >= 70 ? '#f59e0b' : '#ef4444'};">${a.success_rate?.toFixed(1) || 0}%</td>
                            <td style="padding: 14px 8px; text-align: right; color: var(--text-secondary);">${a.avg_duration || 0}s</td>
                        </tr>
                    `).join('')}
                </tbody>
            </table>
            
            ${agentData.length === 0 ? `
                <div style="text-align: center; padding: 40px; color: var(--text-secondary);">
                    <i class="ri-inbox-line" style="font-size: 32px; opacity: 0.5;"></i>
                    <p style="margin-top: 12px;">暂无数据</p>
                </div>
            ` : ''}
        </div>
    `;
}

// 全局暴露函数
window.renderTokenStats = renderTokenStats;
window.loadTokenStatsContent = loadTokenStatsContent;

console.log('[app-token-stats.js] Token统计模块已加载');