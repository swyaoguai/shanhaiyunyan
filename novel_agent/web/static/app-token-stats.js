/**
 * 山海·云烟 - Token消耗统计模块
 * 当前页面只展示当前项目范围内的 Token 使用量。
 */

const TOKEN_STATS_VIEWS = [
    { id: 'hourly', label: '24小时', icon: 'ri-time-line' },
    { id: 'week', label: '一周', icon: 'ri-calendar-week-line' },
    { id: 'month', label: '一月', icon: 'ri-calendar-2-line' },
    { id: 'models', label: '按模型', icon: 'ri-robot-line' }
];

const TOKEN_STATS_CARD_COLORS = [
    ['rgba(99, 102, 241, 0.12)', 'rgba(99, 102, 241, 0.24)', '#818cf8'],
    ['rgba(34, 197, 94, 0.12)', 'rgba(34, 197, 94, 0.24)', '#4ade80'],
    ['rgba(251, 146, 60, 0.12)', 'rgba(251, 146, 60, 0.24)', '#fb923c'],
    ['rgba(14, 165, 233, 0.12)', 'rgba(14, 165, 233, 0.24)', '#38bdf8']
];

const tokenStatsState = {
    currentView: 'hourly',
    filterModel: '',
    availableModels: [],
    scope: 'all'
};

function tokenStatsEscape(value) {
    if (typeof escapeHtml === 'function') {
        return escapeHtml(value);
    }
    return String(value ?? '')
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#039;');
}

function formatTokenNumber(value) {
    return Math.round(Number(value || 0)).toLocaleString();
}

function buildTokenStatsUrl(path, extraParams = {}) {
    const params = new URLSearchParams();
    if (tokenStatsState.filterModel) {
        params.set('model', tokenStatsState.filterModel);
    }
    params.set('scope', tokenStatsState.scope || 'all');
    Object.entries(extraParams).forEach(([key, value]) => {
        if (value !== undefined && value !== null && value !== '') {
            params.set(key, value);
        }
    });
    const query = params.toString();
    return normalizeApiUrl(`${path}${query ? `?${query}` : ''}`);
}

async function fetchTokenStatsJson(path, extraParams = {}) {
    const res = await fetch(buildTokenStatsUrl(path, extraParams));
    if (!res.ok) {
        throw new Error(`HTTP ${res.status}`);
    }
    return res.json();
}

async function loadTokenStatsFilters() {
    try {
        const res = await fetch(buildTokenStatsUrl('/api/v1/token-stats/filters'));
        if (!res.ok) {
            throw new Error(`HTTP ${res.status}`);
        }
        const data = await res.json();
        tokenStatsState.availableModels = data.models || [];
        if (
            tokenStatsState.filterModel &&
            !tokenStatsState.availableModels.includes(tokenStatsState.filterModel)
        ) {
            tokenStatsState.filterModel = '';
        }
    } catch (e) {
        console.error('加载筛选选项失败:', e);
        tokenStatsState.availableModels = [];
    }
}

function renderTokenStatsCards(summary) {
    const cards = [
        ['总Token', summary.total_tokens],
        ['输入Token', summary.tokens_in],
        ['输出Token', summary.tokens_out],
        ['调用次数', summary.call_count]
    ];

    return `
        <div style="display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 16px; margin-bottom: 20px;">
            ${cards.map(([label, value], index) => {
                const [bg, border, color] = TOKEN_STATS_CARD_COLORS[index];
                return `
                    <div class="stat-card" style="background: ${bg}; border: 1px solid ${border}; border-radius: 8px; padding: 20px; text-align: center; min-width: 0;">
                        <div style="font-size: 28px; font-weight: 700; color: ${color}; word-break: break-word;">${formatTokenNumber(value)}</div>
                        <div style="font-size: 12px; color: var(--text-secondary); margin-top: 6px;">${label}</div>
                    </div>
                `;
            }).join('')}
        </div>
    `;
}

function renderTokenStatsMeta(summary) {
    return `
        <div style="display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 16px;">
            <div style="padding: 14px; background: rgba(255,255,255,0.02); border-radius: 8px;">
                <div style="font-size: 13px; color: var(--text-secondary);">平均每次Token</div>
                <div style="font-size: 18px; font-weight: 600; color: var(--text-primary); margin-top: 4px;">${formatTokenNumber(summary.avg_tokens_per_call)}</div>
            </div>
            <div style="padding: 14px; background: rgba(255,255,255,0.02); border-radius: 8px;">
                <div style="font-size: 13px; color: var(--text-secondary);">成功率</div>
                <div style="font-size: 18px; font-weight: 600; color: var(--text-primary); margin-top: 4px;">${Number(summary.success_rate || 0).toFixed(1)}%</div>
            </div>
            <div style="padding: 14px; background: rgba(255,255,255,0.02); border-radius: 8px;">
                <div style="font-size: 13px; color: var(--text-secondary);">平均响应时间</div>
                <div style="font-size: 18px; font-weight: 600; color: var(--text-primary); margin-top: 4px;">${Number(summary.avg_duration || 0).toFixed(2)}s</div>
            </div>
        </div>
    `;
}

function renderTokenStatsEmpty(label = '暂无数据') {
    return `
        <div style="text-align: center; padding: 40px; color: var(--text-secondary);">
            <i class="ri-inbox-line" style="font-size: 32px; opacity: 0.5;"></i>
            <p style="margin-top: 12px;">${label}</p>
        </div>
    `;
}

function renderTokenStatsHeader() {
    const projectName = tokenStatsEscape(store.currentProjectName || '当前项目');

    return `
        <div class="token-stats-header" style="display: flex; justify-content: space-between; align-items: flex-start; gap: 16px; margin-bottom: 24px;">
            <div>
                <h2 style="color: var(--text-primary); font-size: 20px; display: flex; align-items: center; gap: 10px; margin: 0;">
                    <i class="ri-coin-line"></i>
                    Token 消耗统计
                </h2>
                <div style="color: var(--text-secondary); font-size: 13px; margin-top: 8px;">当前范围：${tokenStatsState.scope === 'current' ? `当前项目 · ${projectName}` : '全部项目'}</div>
            </div>
            <div class="token-stats-filters" style="display: flex; gap: 12px; align-items: center; flex-wrap: wrap; justify-content: flex-end;">
                <select id="filter-scope" style="padding: 8px 12px; border-radius: 8px; border: 1px solid var(--border-color); background: var(--bg-secondary); color: var(--text-primary); min-width: 130px;">
                    <option value="all" ${tokenStatsState.scope !== 'current' ? 'selected' : ''}>全部项目</option>
                    <option value="current" ${tokenStatsState.scope === 'current' ? 'selected' : ''}>当前项目</option>
                </select>
                <select id="filter-model" style="padding: 8px 12px; border-radius: 8px; border: 1px solid var(--border-color); background: var(--bg-secondary); color: var(--text-primary); min-width: 190px;">
                    <option value="">全部模型</option>
                    ${tokenStatsState.availableModels.map(model => {
                        const safeModel = tokenStatsEscape(model);
                        return `<option value="${safeModel}" ${tokenStatsState.filterModel === model ? 'selected' : ''}>${safeModel}</option>`;
                    }).join('')}
                </select>
                <button id="cleanup-token-stats" style="padding: 8px 14px; border-radius: 8px; border: 1px solid rgba(59, 130, 246, 0.45); background: rgba(59, 130, 246, 0.1); color: #60a5fa; cursor: pointer; display: flex; align-items: center; gap: 6px; font-size: 13px;" title="清理已删除项目留下的统计记录">
                    <i class="ri-filter-3-line"></i> 清理
                </button>
                <button id="reset-token-stats" style="padding: 8px 16px; border-radius: 8px; border: 1px solid rgba(239, 68, 68, 0.5); background: rgba(239, 68, 68, 0.1); color: #ef4444; cursor: pointer; display: flex; align-items: center; gap: 6px; font-size: 13px;" title="清空全部统计数据">
                    <i class="ri-delete-bin-line"></i> 重置
                </button>
            </div>
        </div>
    `;
}

function renderTokenStatsTabs() {
    return `
        <div class="token-stats-tabs" style="display: flex; gap: 8px; margin-bottom: 24px; border-bottom: 1px solid var(--border-color); padding-bottom: 12px; flex-wrap: wrap;">
            ${TOKEN_STATS_VIEWS.map(view => {
                const active = tokenStatsState.currentView === view.id;
                return `
                    <button class="tab-btn ${active ? 'active' : ''}" data-view="${view.id}" style="padding: 8px 16px; border: none; background: ${active ? 'var(--accent-color)' : 'transparent'}; color: ${active ? 'white' : 'var(--text-secondary)'}; border-radius: 6px; cursor: pointer; font-size: 13px;">
                        <i class="${view.icon}"></i> ${view.label}
                    </button>
                `;
            }).join('')}
        </div>
    `;
}

async function renderTokenStats() {
    if (!TOKEN_STATS_VIEWS.some(view => view.id === tokenStatsState.currentView)) {
        tokenStatsState.currentView = 'hourly';
    }

    updateBreadcrumbs([store.currentProjectName || '我的项目', 'Token统计']);
    await loadTokenStatsFilters();

    ui.workspace.innerHTML = `
        <div class="token-stats-container" style="padding: 30px; max-width: 1200px; margin: 0 auto;">
            ${renderTokenStatsHeader()}
            ${renderTokenStatsTabs()}
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

    document.querySelectorAll('.tab-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            tokenStatsState.currentView = btn.dataset.view;
            renderTokenStats();
        });
    });

    document.getElementById('filter-scope').addEventListener('change', async event => {
        tokenStatsState.scope = event.target.value === 'current' ? 'current' : 'all';
        tokenStatsState.filterModel = '';
        await loadTokenStatsFilters();
        renderTokenStats();
    });

    document.getElementById('filter-model').addEventListener('change', event => {
        tokenStatsState.filterModel = event.target.value;
        loadTokenStatsContent();
    });

    document.getElementById('cleanup-token-stats').addEventListener('click', async () => {
        try {
            const res = await fetch(normalizeApiUrl('/api/token-stats/cleanup-orphans'), { method: 'POST' });
            const result = await res.json();
            if (result.success) {
                showToast(`已清理 ${result.deleted_count || 0} 条无效项目统计记录`, 'success');
                await loadTokenStatsFilters();
                await loadTokenStatsContent();
            } else {
                showToast('清理失败: ' + (result.error || '未知错误'), 'error');
            }
        } catch (e) {
            showToast('清理失败: ' + e.message, 'error');
        }
    });

    document.getElementById('reset-token-stats').addEventListener('click', async () => {
        if (!(await window.showConfirmDialog('确定要清空全部Token统计数据吗？此操作不可恢复。'))) {
            return;
        }

        try {
            const res = await fetch(normalizeApiUrl('/api/token-stats/reset'), { method: 'POST' });
            const result = await res.json();
            if (result.success) {
                showToast(`已重置全部统计数据，共清空 ${result.deleted_count || 0} 条记录`, 'success');
                await loadTokenStatsFilters();
                await loadTokenStatsContent();
            } else {
                showToast('重置失败: ' + (result.error || '未知错误'), 'error');
            }
        } catch (e) {
            showToast('重置失败: ' + e.message, 'error');
        }
    });

    await loadTokenStatsContent();
}

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
            case 'week':
                await renderTokenStatsPeriod(container, 7, '近7天Token统计', 'ri-calendar-week-line');
                break;
            case 'month':
                await renderTokenStatsPeriod(container, 30, '近30天Token统计', 'ri-calendar-2-line');
                break;
            case 'models':
                await renderTokenStatsByModel(container);
                break;
            case 'hourly':
            default:
                await renderTokenStatsHourly(container);
                break;
        }
    } catch (e) {
        console.error('加载Token统计失败:', e);
        container.innerHTML = `
            <div style="text-align: center; padding: 40px; color: var(--text-secondary);">
                <i class="ri-error-warning-line" style="font-size: 40px; opacity: 0.5;"></i>
                <p style="margin-top: 12px;">加载失败: ${tokenStatsEscape(e.message)}</p>
                <button onclick="loadTokenStatsContent()" style="margin-top: 12px; padding: 8px 16px; background: var(--accent-color); border: none; color: white; border-radius: 6px; cursor: pointer;">重试</button>
            </div>
        `;
    }
}

async function renderTokenStatsHourly(container) {
    const [summary, hourly] = await Promise.all([
        fetchTokenStatsJson('/api/token-stats/summary', { days: 1 }),
        fetchTokenStatsJson('/api/token-stats/hourly', { hours: 24 })
    ]);
    const hourlyData = hourly.data || [];
    const maxTokens = Math.max(...hourlyData.map(item => item.total_tokens || 0), 1);

    container.innerHTML = `
        ${renderTokenStatsCards(summary)}
        <div style="background: rgba(255,255,255,0.03); border: 1px solid var(--border-color); border-radius: 8px; padding: 24px; margin-bottom: 20px;">
            <h3 style="color: var(--text-primary); font-size: 15px; margin-bottom: 20px; display: flex; align-items: center; gap: 8px;">
                <i class="ri-line-chart-line"></i> 24小时Token消耗趋势
            </h3>
            <div style="position: relative; height: 300px; padding-left: 50px; padding-bottom: 30px;">
                <div style="position: absolute; left: 0; top: 0; height: calc(100% - 30px); display: flex; flex-direction: column; justify-content: space-between; font-size: 11px; color: var(--text-secondary);">
                    <span>${formatTokenNumber(maxTokens)}</span>
                    <span>${formatTokenNumber(maxTokens * 0.75)}</span>
                    <span>${formatTokenNumber(maxTokens * 0.5)}</span>
                    <span>${formatTokenNumber(maxTokens * 0.25)}</span>
                    <span>0</span>
                </div>
                <div style="display: flex; align-items: flex-end; gap: 2px; height: calc(100% - 30px); padding: 0 10px;">
                    ${hourlyData.map((item, index) => {
                        const heightPercent = maxTokens > 0 ? item.total_tokens / maxTokens * 100 : 0;
                        const hourLabel = item.hour ? item.hour.split(' ')[1] : `${index}:00`;
                        return `
                            <div style="flex: 1; min-width: 10px; display: flex; flex-direction: column; align-items: center;">
                                <div style="position: relative; width: 100%; height: ${heightPercent}%; min-height: ${item.total_tokens > 0 ? '4px' : '0'}; background: linear-gradient(to top, #2563eb, #60a5fa); border-radius: 4px 4px 0 0; cursor: pointer;" title="${tokenStatsEscape(hourLabel)}: ${formatTokenNumber(item.total_tokens)} tokens"></div>
                            </div>
                        `;
                    }).join('')}
                </div>
                <div style="display: flex; justify-content: space-between; font-size: 10px; color: var(--text-secondary); padding: 8px 10px 0;">
                    ${hourlyData.filter((_, index) => index % 4 === 0).map(item => `<span>${tokenStatsEscape(item.hour ? item.hour.split(' ')[1] : '')}</span>`).join('')}
                </div>
            </div>
        </div>
        ${renderHourlyTable(hourlyData)}
        <div style="background: rgba(255,255,255,0.03); border: 1px solid var(--border-color); border-radius: 8px; padding: 20px; margin-top: 20px;">
            ${renderTokenStatsMeta(summary)}
        </div>
    `;
}

function renderHourlyTable(hourlyData) {
    return `
        <div style="background: rgba(255,255,255,0.03); border: 1px solid var(--border-color); border-radius: 8px; padding: 24px;">
            <h3 style="color: var(--text-primary); font-size: 15px; margin-bottom: 16px;">24小时明细</h3>
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
                        ${hourlyData.slice().reverse().map(item => `
                            <tr style="border-bottom: 1px solid rgba(255,255,255,0.05);">
                                <td style="padding: 10px 8px; color: var(--text-primary);">${tokenStatsEscape(item.hour || '-')}</td>
                                <td style="padding: 10px 8px; text-align: right; color: #818cf8; font-weight: 500;">${formatTokenNumber(item.total_tokens)}</td>
                                <td style="padding: 10px 8px; text-align: right; color: #4ade80;">${formatTokenNumber(item.tokens_in)}</td>
                                <td style="padding: 10px 8px; text-align: right; color: #fb923c;">${formatTokenNumber(item.tokens_out)}</td>
                                <td style="padding: 10px 8px; text-align: right; color: var(--text-secondary);">${formatTokenNumber(item.call_count)}</td>
                            </tr>
                        `).join('')}
                    </tbody>
                </table>
            </div>
        </div>
    `;
}

async function renderTokenStatsPeriod(container, days, title, icon) {
    const [summary, daily] = await Promise.all([
        fetchTokenStatsJson('/api/token-stats/summary', { days }),
        fetchTokenStatsJson('/api/token-stats/daily', { days })
    ]);
    const rows = daily.data || [];
    const maxTokens = Math.max(...rows.map(item => item.total_tokens || 0), 1);

    container.innerHTML = `
        ${renderTokenStatsCards(summary)}
        <div style="background: rgba(255,255,255,0.03); border: 1px solid var(--border-color); border-radius: 8px; padding: 24px;">
            <h3 style="color: var(--text-primary); font-size: 15px; margin-bottom: 20px; display: flex; align-items: center; gap: 8px;">
                <i class="${icon}"></i> ${title}
            </h3>
            <div style="display: flex; flex-direction: column; gap: 14px;">
                ${rows.map(item => {
                    const widthPercent = maxTokens > 0 ? item.total_tokens / maxTokens * 100 : 0;
                    return `
                        <div style="background: rgba(255,255,255,0.02); border-radius: 8px; padding: 16px;">
                            <div style="display: flex; justify-content: space-between; align-items: center; gap: 12px; margin-bottom: 10px;">
                                <span style="font-size: 14px; font-weight: 500; color: var(--text-primary);">${tokenStatsEscape(item.date || '-')}</span>
                                <span style="font-size: 12px; font-weight: 600; color: #60a5fa;">${formatTokenNumber(item.total_tokens)} tokens</span>
                            </div>
                            <div style="height: 24px; background: rgba(255,255,255,0.05); border-radius: 6px; overflow: hidden; margin-bottom: 10px;">
                                <div style="height: 100%; width: ${widthPercent}%; background: linear-gradient(90deg, #2563eb, #14b8a6); border-radius: 6px;"></div>
                            </div>
                            <div style="display: flex; justify-content: space-between; gap: 12px; font-size: 12px; color: var(--text-secondary);">
                                <span>输入 ${formatTokenNumber(item.tokens_in)} / 输出 ${formatTokenNumber(item.tokens_out)}</span>
                                <span>调用 ${formatTokenNumber(item.call_count)} 次 / 成功率 ${Number(item.success_rate || 0).toFixed(1)}%</span>
                            </div>
                        </div>
                    `;
                }).join('')}
            </div>
            ${rows.length === 0 ? renderTokenStatsEmpty() : ''}
        </div>
        <div style="background: rgba(255,255,255,0.03); border: 1px solid var(--border-color); border-radius: 8px; padding: 20px; margin-top: 20px;">
            ${renderTokenStatsMeta(summary)}
        </div>
    `;
}

async function renderTokenStatsByModel(container) {
    const data = await fetchTokenStatsJson('/api/token-stats/by-model', { days: 30 });
    const modelData = data.data || [];
    const totalTokens = modelData.reduce((sum, item) => sum + (item.total_tokens || 0), 0);

    container.innerHTML = `
        <div style="background: rgba(255,255,255,0.03); border: 1px solid var(--border-color); border-radius: 8px; padding: 24px;">
            <h3 style="color: var(--text-primary); font-size: 15px; margin-bottom: 20px; display: flex; align-items: center; gap: 8px;">
                <i class="ri-robot-line"></i> 按模型统计（近30天）
            </h3>
            <div style="display: grid; gap: 16px;">
                ${modelData.map((item, index) => {
                    const colors = ['#2563eb', '#10b981', '#f59e0b', '#ec4899', '#8b5cf6', '#06b6d4'];
                    const color = colors[index % colors.length];
                    const percent = totalTokens > 0 ? item.total_tokens / totalTokens * 100 : 0;
                    return `
                        <div style="background: rgba(255,255,255,0.02); border-radius: 8px; padding: 20px; border-left: 4px solid ${color};">
                            <div style="display: flex; justify-content: space-between; align-items: flex-start; gap: 16px; margin-bottom: 12px;">
                                <div style="min-width: 0;">
                                    <div style="font-size: 15px; font-weight: 600; color: var(--text-primary); word-break: break-word;">${tokenStatsEscape(item.model || '未知模型')}</div>
                                    <div style="font-size: 11px; color: var(--text-secondary); margin-top: 4px;">占比 ${percent.toFixed(1)}%</div>
                                </div>
                                <div style="text-align: right;">
                                    <div style="font-size: 20px; font-weight: 700; color: ${color};">${formatTokenNumber(item.total_tokens)}</div>
                                    <div style="font-size: 11px; color: var(--text-secondary);">tokens</div>
                                </div>
                            </div>
                            <div style="display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 12px; font-size: 12px;">
                                <div>
                                    <div style="color: var(--text-secondary);">输入Token</div>
                                    <div style="color: var(--text-primary); font-weight: 500; margin-top: 2px;">${formatTokenNumber(item.tokens_in)}</div>
                                </div>
                                <div>
                                    <div style="color: var(--text-secondary);">输出Token</div>
                                    <div style="color: var(--text-primary); font-weight: 500; margin-top: 2px;">${formatTokenNumber(item.tokens_out)}</div>
                                </div>
                                <div>
                                    <div style="color: var(--text-secondary);">调用次数</div>
                                    <div style="color: var(--text-primary); font-weight: 500; margin-top: 2px;">${formatTokenNumber(item.call_count)}</div>
                                </div>
                                <div>
                                    <div style="color: var(--text-secondary);">成功率</div>
                                    <div style="color: ${item.success_rate >= 90 ? '#22c55e' : item.success_rate >= 70 ? '#f59e0b' : '#ef4444'}; font-weight: 500; margin-top: 2px;">${Number(item.success_rate || 0).toFixed(1)}%</div>
                                </div>
                            </div>
                        </div>
                    `;
                }).join('')}
            </div>
            ${modelData.length === 0 ? renderTokenStatsEmpty() : ''}
        </div>
    `;
}

window.renderTokenStats = renderTokenStats;
window.loadTokenStatsContent = loadTokenStatsContent;

console.log('[app-token-stats.js] Token统计模块已加载');
