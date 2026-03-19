/**
 * 热点/热梗搜索模块
 * 提供热点数据获取和展示功能，可集成到无限续写和多Agent模式
 */

// ===== 热点搜索状态 =====
const trendsState = {
    enabled: true,
    loading: false,
    currentPlatform: 'toutiao',  // 默认头条
    trends: [],
    config: {
        enabled: true,
        autoRefresh: false,
        refreshInterval: 300,
        defaultPlatforms: ['douban', 'weread', 'zhihu', 'toutiao', 'bilibili', 'douyin'],
        showInInfiniteWrite: true,
        showInMultiAgent: true
    },
    platforms: [],
    lastFetch: null,
    serviceAvailable: false
};

// ===== 平台图标映射（基于 mcp-trends-hub@1.6.0 实际可用的工具） =====
const platformIcons = {
    // 创作灵感类
    douban: 'ri-douban-fill',
    weread: 'ri-book-open-fill',
    zhihu: 'ri-zhihu-fill',
    gcores: 'ri-gamepad-fill',
    // 热点资讯类
    toutiao: 'ri-newspaper-fill',
    netease: 'ri-netease-cloud-music-fill',
    tencent: 'ri-qq-fill',
    thepaper: 'ri-newspaper-line',
    // 视频娱乐类
    bilibili: 'ri-bilibili-fill',
    douyin: 'ri-tiktok-fill',
    // 科技资讯类
    '36kr': 'ri-article-fill',
    sspai: 'ri-apps-fill',
    ifanr: 'ri-smartphone-fill',
    juejin: 'ri-code-s-slash-fill',
    // 购物生活类
    smzdm: 'ri-shopping-cart-fill'
};

// 平台中文名称映射
const platformNames = {
    // 创作灵感类
    douban: '豆瓣热榜',
    weread: '微信读书',
    zhihu: '知乎热榜',
    gcores: '机核',
    // 热点资讯类
    toutiao: '头条热榜',
    netease: '网易新闻',
    tencent: '腾讯新闻',
    thepaper: '澎湃新闻',
    // 视频娱乐类
    bilibili: 'B站热门',
    douyin: '抖音热点',
    // 科技资讯类
    '36kr': '36氪',
    sspai: '少数派',
    ifanr: '爱范儿',
    juejin: '掘金',
    // 购物生活类
    smzdm: '什么值得买'
};

// ===== 初始化 =====
async function initTrendsModule() {
    await loadTrendsConfig();
    await checkTrendsService();
    await loadTrendsPlatforms();
}

// ===== 加载配置 =====
async function loadTrendsConfig() {
    try {
        const config = await apiCall('/api/trends/config', 'GET');
        trendsState.config = {
            enabled: config.enabled !== false,
            autoRefresh: config.auto_refresh || false,
            refreshInterval: config.refresh_interval || 300,
            defaultPlatforms: config.default_platforms || [],  // 使用空数组作为回退值，不预选任何平台
            showInInfiniteWrite: config.show_in_infinite_write !== false,
            showInMultiAgent: config.show_in_multi_agent !== false
        };
        trendsState.enabled = trendsState.config.enabled;
    } catch (e) {
        console.error('[Trends] 加载配置失败:', e);
    }
}

// ===== 检查服务状态 =====
async function checkTrendsService() {
    try {
        const status = await apiCall('/api/trends/status', 'GET');
        trendsState.serviceAvailable = status.available;
        if (!status.available) {
            console.warn('[Trends] 热点服务不可用:', status.error || status.message);
        }
        return status.available;
    } catch (e) {
        console.error('[Trends] 检查服务状态失败:', e);
        trendsState.serviceAvailable = false;
        return false;
    }
}

// ===== 加载平台列表 =====
async function loadTrendsPlatforms() {
    try {
        const res = await apiCall('/api/trends/platforms', 'GET');
        trendsState.platforms = res.platforms || [];
    } catch (e) {
        console.error('[Trends] 加载平台列表失败:', e);
    }
}

// ===== 获取热点数据 =====
async function fetchTrends(platform = 'toutiao', limit = 20) {
    if (trendsState.loading) return [];  // 返回空数组而不是 undefined

    trendsState.loading = true;
    trendsState.currentPlatform = platform;

    try {
        const res = await apiCall('/api/trends/search', 'POST', {
            platform: platform,
            limit: limit
        });

        if (res.success) {
            trendsState.trends = res.trends || [];
            trendsState.lastFetch = new Date();
            return trendsState.trends;
        } else {
            console.error('[Trends] 获取热点失败:', res.error);
            showToast(`获取${platformNames[platform] || platform}热点失败`, 'error');
            return [];
        }
    } catch (e) {
        console.error('[Trends] 请求热点失败:', e);
        showToast('热点服务连接失败', 'error');
        return [];
    } finally {
        trendsState.loading = false;
    }
}

// ===== 保存配置 =====
async function saveTrendsConfig(config) {
    try {
        await apiCall('/api/trends/config', 'POST', config);
        Object.assign(trendsState.config, config);
        showToast('热点配置已保存');
    } catch (e) {
        console.error('[Trends] 保存配置失败:', e);
        showToast('保存配置失败', 'error');
    }
}

// ===== 保存显示开关 =====
async function saveTrendsVisibility(showInInfiniteWrite, showInMultiAgent) {
    try {
        await apiCall('/api/trends/visibility', 'POST', {
            show_in_infinite_write: showInInfiniteWrite,
            show_in_multi_agent: showInMultiAgent
        });
        trendsState.config.showInInfiniteWrite = showInInfiniteWrite;
        trendsState.config.showInMultiAgent = showInMultiAgent;
        showToast('热点显示设置已保存');
    } catch (e) {
        console.error('[Trends] 保存显示设置失败:', e);
        showToast('保存设置失败', 'error');
    }
}

// ===== 渲染热点面板（可嵌入到其他界面） =====
function renderTrendsPanel(containerId, options = {}) {
    const container = document.getElementById(containerId);
    if (!container) return;

    const {
        compact = false,
        showToggle = true,
        onSelect = null,
        maxItems = 10
    } = options;

    // 如果服务不可用或被禁用
    if (!trendsState.serviceAvailable || !trendsState.enabled) {
        container.innerHTML = `
            <div style="padding: 16px; text-align: center; color: var(--text-secondary); font-size: 13px;">
                <i class="ri-fire-line" style="font-size: 24px; opacity: 0.3; display: block; margin-bottom: 8px;"></i>
                ${!trendsState.serviceAvailable ? '热点服务未连接' : '热点功能已关闭'}
                <div style="margin-top: 8px; font-size: 11px; opacity: 0.7;">
                    ${!trendsState.serviceAvailable ? '请确保MCP服务已启动' : '可在设置中开启'}
                </div>
            </div>
        `;
        return;
    }

    container.innerHTML = `
        <div class="trends-panel" style="background: rgba(255,255,255,0.03); border: 1px solid var(--border-color); border-radius: 12px; overflow: hidden;">
            <!-- 标题栏 -->
            <div style="display: flex; align-items: center; padding: 12px 16px; border-bottom: 1px solid var(--border-color); background: rgba(239, 68, 68, 0.05);">
                <i class="ri-fire-fill" style="color: #ef4444; margin-right: 8px;"></i>
                <span style="font-weight: 500; color: var(--text-primary);">热点灵感</span>
                <div style="flex: 1;"></div>
                ${showToggle ? `
                <label style="display: flex; align-items: center; gap: 6px; font-size: 12px; color: var(--text-secondary); cursor: pointer;">
                    <input type="checkbox" id="trends-toggle-${containerId}" ${trendsState.enabled ? 'checked' : ''} 
                        style="width: 14px; height: 14px; cursor: pointer;">
                    启用
                </label>
                ` : ''}
                <button id="trends-refresh-${containerId}" style="background: none; border: none; color: var(--text-secondary); cursor: pointer; padding: 4px 8px; margin-left: 8px;" title="刷新">
                    <i class="ri-refresh-line"></i>
                </button>
            </div>
            
            <!-- 平台选择（使用用户保存的配置，无硬编码回退） -->
            <div style="display: flex; gap: 8px; padding: 12px 16px; overflow-x: auto; border-bottom: 1px solid var(--border-color);">
                ${(() => {
                    // 优先使用传入的 platforms 选项，然后是用户保存的配置
                    let platforms = options.platforms || trendsState.config?.defaultPlatforms || [];
                    // 如果配置为空，使用几个默认可用的平台
                    if (!platforms || platforms.length === 0) {
                        platforms = ['toutiao', 'zhihu', 'bilibili', 'douyin'];
                    }
                    return platforms.map(p => `
                        <button class="trends-platform-btn ${trendsState.currentPlatform === p ? 'active' : ''}"
                            data-platform="${p}"
                            style="display: flex; align-items: center; gap: 4px; padding: 6px 12px;
                                background: ${trendsState.currentPlatform === p ? 'var(--accent-color)' : 'rgba(255,255,255,0.05)'};
                                border: 1px solid ${trendsState.currentPlatform === p ? 'var(--accent-color)' : 'var(--border-color)'};
                                color: ${trendsState.currentPlatform === p ? 'white' : 'var(--text-secondary)'};
                                border-radius: 6px; cursor: pointer; font-size: 12px; white-space: nowrap;">
                            <i class="${platformIcons[p] || 'ri-fire-line'}"></i>
                            ${compact ? '' : (platformNames[p] || p)}
                        </button>
                    `).join('');
                })()}
            </div>
            
            <!-- 热点列表 -->
            <div id="trends-list-${containerId}" style="max-height: 300px; overflow-y: auto;">
                <div style="padding: 20px; text-align: center; color: var(--text-secondary);">
                    <i class="ri-loader-4-line" style="animation: spin 1s linear infinite;"></i>
                    加载中...
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
    const toggleCheckbox = document.getElementById(`trends-toggle-${containerId}`);
    if (toggleCheckbox) {
        toggleCheckbox.addEventListener('change', (e) => {
            trendsState.enabled = e.target.checked;
            saveTrendsConfig({ enabled: e.target.checked });
            if (e.target.checked) {
                loadTrendsForPanel(containerId, maxItems, onSelect);
            }
        });
    }

    const refreshBtn = document.getElementById(`trends-refresh-${containerId}`);
    if (refreshBtn) {
        refreshBtn.addEventListener('click', () => {
            loadTrendsForPanel(containerId, maxItems, onSelect);
        });
    }

    container.querySelectorAll('.trends-platform-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            const platform = btn.dataset.platform;
            trendsState.currentPlatform = platform;

            // 更新按钮样式
            container.querySelectorAll('.trends-platform-btn').forEach(b => {
                const isActive = b.dataset.platform === platform;
                b.classList.toggle('active', isActive);
                b.style.background = isActive ? 'var(--accent-color)' : 'rgba(255,255,255,0.05)';
                b.style.borderColor = isActive ? 'var(--accent-color)' : 'var(--border-color)';
                b.style.color = isActive ? 'white' : 'var(--text-secondary)';
            });

            loadTrendsForPanel(containerId, maxItems, onSelect);
        });
    });

    // 加载热点数据
    if (trendsState.enabled) {
        loadTrendsForPanel(containerId, maxItems, onSelect);
    }
}

// ===== 加载热点到面板 =====
async function loadTrendsForPanel(containerId, maxItems = 10, onSelect = null) {
    const listContainer = document.getElementById(`trends-list-${containerId}`);
    if (!listContainer) return;

    listContainer.innerHTML = `
        <div style="padding: 20px; text-align: center; color: var(--text-secondary);">
            <i class="ri-loader-4-line" style="animation: spin 1s linear infinite;"></i>
            加载中...
        </div>
    `;

    const trends = await fetchTrends(trendsState.currentPlatform, maxItems);

    // ===== 调试日志：打印原始数据格式 =====
    console.log('[Trends Debug] ===== 原始热点数据 =====');
    console.log('[Trends Debug] trends 类型:', typeof trends);
    console.log('[Trends Debug] trends 是否数组:', Array.isArray(trends));
    console.log('[Trends Debug] trends 长度:', trends ? trends.length : 0);
    if (trends && trends.length > 0) {
        console.log('[Trends Debug] 第一条数据:', JSON.stringify(trends[0], null, 2));
        console.log('[Trends Debug] 第一条 title 类型:', typeof trends[0].title);
        console.log('[Trends Debug] 第一条 title 值:', trends[0].title);
    }

    // 确保 trends 是数组（防御性编程）
    if (!trends || !Array.isArray(trends) || trends.length === 0) {
        listContainer.innerHTML = `
            <div style="padding: 20px; text-align: center; color: var(--text-secondary); font-size: 13px;">
                <i class="ri-emotion-sad-line" style="font-size: 24px; opacity: 0.3; display: block; margin-bottom: 8px;"></i>
                暂无热点数据
            </div>
        `;
        return;
    }

    listContainer.innerHTML = trends.map((item, index) => {
        // ===== 调试日志：打印每条数据的处理过程 =====
        if (index === 0) {
            console.log('[Trends Debug] ===== 第一条数据处理过程 =====');
            console.log('[Trends Debug] item:', item);
            console.log('[Trends Debug] item.title:', item.title);
            console.log('[Trends Debug] extractPlainTitle(item.title):', extractPlainTitle(item.title));
        }
        
        // 使用 extractPlainTitle 确保提取纯文本标题，处理多层 JSON 嵌套
        let title = extractPlainTitle(item.title) ||
                    extractPlainTitle(item.name) ||
                    extractPlainTitle(item.content) ||
                    extractPlainTitle(item);
        
        // ===== 调试日志：打印提取结果 =====
        if (index === 0) {
            console.log('[Trends Debug] 最终 title:', title);
        }
        
        // 如果还是空的，使用默认标题
        if (!title || !title.trim()) {
            title = `热点 ${index + 1}`;
        }
        
        // 同样处理 hot 字段
        let hot = item.hot || item.hotValue || item.heat || '';
        if (typeof hot === 'object') {
            hot = hot.hot || hot.value || '';
        }
        hot = String(hot || '');
        
        const url = item.url || item.link || '';

        // 热度等级（前3名特殊标记）
        const rankClass = index < 3 ? 'hot' : '';
        const rankBg = index === 0 ? '#ef4444' : index === 1 ? '#f97316' : index === 2 ? '#eab308' : 'var(--text-secondary)';

        return `
            <div class="trends-item" data-index="${index}" data-title="${escapeHtml(title)}"
                style="display: flex; align-items: flex-start; gap: 10px; padding: 10px 16px;
                    cursor: pointer; transition: background 0.2s; border-bottom: 1px solid rgba(255,255,255,0.03);"
                onmouseover="this.style.background='rgba(255,255,255,0.05)'"
                onmouseout="this.style.background='transparent'">
                <span style="min-width: 20px; height: 20px; display: flex; align-items: center; justify-content: center;
                    background: ${rankBg}; color: white; border-radius: 4px; font-size: 11px; font-weight: 600;">
                    ${index + 1}
                </span>
                <div style="flex: 1; min-width: 0;">
                    <div style="font-size: 13px; color: var(--text-primary); line-height: 1.4;
                        overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">
                        ${escapeHtml(title)}
                    </div>
                </div>
                <button class="trends-use-btn" data-title="${escapeHtml(title)}"
                    style="padding: 4px 10px; background: rgba(139, 92, 246, 0.2); border: 1px solid rgba(139, 92, 246, 0.4);
                        color: #a78bfa; border-radius: 4px; cursor: pointer; font-size: 11px; white-space: nowrap;"
                    title="使用此热点作为灵感">
                    使用
                </button>
            </div>
        `;
    }).join('');

    // 绑定点击事件
    listContainer.querySelectorAll('.trends-item').forEach(item => {
        item.addEventListener('click', (e) => {
            if (e.target.closest('.trends-use-btn')) return;
            const title = item.dataset.title;
            if (onSelect) {
                onSelect(title, trendsState.trends[parseInt(item.dataset.index)]);
            }
        });
    });

    listContainer.querySelectorAll('.trends-use-btn').forEach(btn => {
        btn.addEventListener('click', (e) => {
            e.stopPropagation();
            const title = btn.dataset.title;
            if (onSelect) {
                const index = btn.closest('.trends-item').dataset.index;
                onSelect(title, trendsState.trends[parseInt(index)]);
            } else {
                // 默认行为：复制到剪贴板
                navigator.clipboard.writeText(title).then(() => {
                    showToast('已复制热点内容');
                }).catch(() => {
                    showToast('复制失败', 'error');
                });
            }
        });
    });
}

// ===== 渲染热点设置面板（用于设置页面） =====
function renderTrendsSettings() {
    return `
        <div style="background: rgba(255,255,255,0.03); border: 1px solid var(--border-color); border-radius: 12px; padding: 24px; margin-bottom: 20px;">
            <h3 style="margin: 0 0 20px 0; font-size: 16px; color: var(--text-primary); display: flex; align-items: center; gap: 10px;">
                <i class="ri-fire-fill" style="color: #ef4444;"></i>
                热点/热梗搜索
            </h3>
            
            <!-- 服务状态 -->
            <div id="trends-service-status" style="margin-bottom: 20px; padding: 12px 16px; background: rgba(0,0,0,0.2); border-radius: 8px;">
                <div style="display: flex; align-items: center; gap: 8px;">
                    <div id="trends-status-indicator" style="width: 10px; height: 10px; border-radius: 50%; background: #666;"></div>
                    <span id="trends-status-text" style="font-size: 13px; color: var(--text-secondary);">检查服务状态...</span>
                </div>
            </div>
            
            <!-- 开关设置 -->
            <div style="display: grid; gap: 16px;">
                <label style="display: flex; align-items: center; justify-content: space-between; padding: 12px 16px; background: rgba(0,0,0,0.2); border-radius: 8px; cursor: pointer;">
                    <div>
                        <div style="font-size: 14px; color: var(--text-primary);">启用热点搜索</div>
                        <div style="font-size: 12px; color: var(--text-secondary); margin-top: 4px;">开启后可在创作时获取实时热点灵感</div>
                    </div>
                    <input type="checkbox" id="trends-enabled" ${trendsState.config.enabled ? 'checked' : ''} 
                        style="width: 20px; height: 20px; cursor: pointer;">
                </label>
                
                <label style="display: flex; align-items: center; justify-content: space-between; padding: 12px 16px; background: rgba(0,0,0,0.2); border-radius: 8px; cursor: pointer;">
                    <div>
                        <div style="font-size: 14px; color: var(--text-primary);">无限续写中显示</div>
                        <div style="font-size: 12px; color: var(--text-secondary); margin-top: 4px;">在无限续写界面显示热点面板</div>
                    </div>
                    <input type="checkbox" id="trends-show-infinite" ${trendsState.config.showInInfiniteWrite ? 'checked' : ''} 
                        style="width: 20px; height: 20px; cursor: pointer;">
                </label>
                
                <label style="display: flex; align-items: center; justify-content: space-between; padding: 12px 16px; background: rgba(0,0,0,0.2); border-radius: 8px; cursor: pointer;">
                    <div>
                        <div style="font-size: 14px; color: var(--text-primary);">协作创作中显示</div>
                        <div style="font-size: 12px; color: var(--text-secondary); margin-top: 4px;">在协作创作界面显示热点面板</div>
                    </div>
                    <input type="checkbox" id="trends-show-multi" ${trendsState.config.showInMultiAgent ? 'checked' : ''} 
                        style="width: 20px; height: 20px; cursor: pointer;">
                </label>
            </div>
            
            <!-- 保存按钮 -->
            <button id="save-trends-settings" style="margin-top: 20px; width: 100%; padding: 12px; 
                background: var(--accent-color); border: none; color: white; border-radius: 8px; 
                cursor: pointer; font-weight: 500; font-size: 14px;">
                <i class="ri-save-line"></i> 保存热点设置
            </button>
        </div>
    `;
}

// 注意：bindTrendsSettingsEvents 已移至 app-settings.js 中，包含完整的保存逻辑

// ===== 创建热点选择弹窗 =====
function showTrendsModal(onSelect) {
    const modal = document.getElementById('modal-container');
    if (!modal) return;

    modal.classList.remove('hidden');

    modal.innerHTML = `
        <div style="position: fixed; top: 0; left: 0; right: 0; bottom: 0; background: rgba(0,0,0,0.7); 
            display: flex; align-items: center; justify-content: center; z-index: 1000; padding: 20px;">
            <div style="background: var(--bg-panel); border: 1px solid var(--border-color); border-radius: 16px; 
                width: 600px; max-width: 100%; max-height: 80vh; display: flex; flex-direction: column;">
                <div style="padding: 20px; border-bottom: 1px solid var(--border-color); display: flex; align-items: center;">
                    <i class="ri-fire-fill" style="color: #ef4444; font-size: 24px; margin-right: 12px;"></i>
                    <div>
                        <h2 style="margin: 0; font-size: 18px; color: var(--text-primary);">选择热点灵感</h2>
                        <p style="margin: 4px 0 0 0; font-size: 13px; color: var(--text-secondary);">点击热点将其作为创作灵感</p>
                    </div>
                    <div style="flex: 1;"></div>
                    <button id="close-trends-modal" style="background: none; border: none; color: var(--text-secondary); 
                        font-size: 24px; cursor: pointer; padding: 4px;">
                        <i class="ri-close-line"></i>
                    </button>
                </div>
                <div id="trends-modal-content" style="flex: 1; overflow: hidden; padding: 0;">
                    <!-- 热点面板将在这里渲染 -->
                </div>
            </div>
        </div>
    `;

    // 关闭按钮
    document.getElementById('close-trends-modal')?.addEventListener('click', () => {
        modal.classList.add('hidden');
        modal.innerHTML = '';
    });

    // 点击背景关闭
    modal.addEventListener('click', (e) => {
        if (e.target === modal.firstElementChild) {
            modal.classList.add('hidden');
            modal.innerHTML = '';
        }
    });

    // 渲染热点面板
    renderTrendsPanel('trends-modal-content', {
        compact: false,
        showToggle: false,
        maxItems: 20,
        onSelect: (title, item) => {
            if (onSelect) {
                onSelect(title, item);
            }
            modal.classList.add('hidden');
            modal.innerHTML = '';
        }
    });
}

// ===== 辅助函数 =====

/**
 * 从可能嵌套的 JSON 字符串或对象中提取纯文本标题
 * 这是关键的数据清理函数，确保显示的是纯文本而非 JSON 格式
 */
function extractPlainTitle(value, depth = 0) {
    // 防止无限递归
    if (depth > 10) {
        return typeof value === 'string' ? value : String(value || '');
    }
    
    if (value === null || value === undefined) {
        return '';
    }
    
    // 字符串处理
    if (typeof value === 'string') {
        value = value.trim();
        if (!value) return '';
        
        // 清理 XML/HTML 标签，如 <title>xxx</title>
        if (value.includes('<') && value.includes('>')) {
            // 尝试提取标签内容
            const tagMatch = value.match(/^<(\w+)>([\s\S]*)<\/\1>$/);
            if (tagMatch) {
                return extractPlainTitle(tagMatch[2].trim(), depth + 1);
            }
            // 通用标签清理
            const cleaned = value.replace(/<[^>]+>/g, '').trim();
            if (cleaned) {
                return cleaned;
            }
        }
        
        // 检测并解析 JSON 字符串
        if ((value.startsWith('{') && value.endsWith('}')) ||
            (value.startsWith('[') && value.endsWith(']'))) {
            try {
                const parsed = JSON.parse(value);
                return extractPlainTitle(parsed, depth + 1);
            } catch (e) {
                // 不是有效 JSON，返回原值
            }
        }
        
        return value;
    }
    
    // 对象处理 - 提取 title/name/content 字段
    if (typeof value === 'object' && !Array.isArray(value)) {
        for (const key of ['title', 'name', 'content', 'text']) {
            if (value[key]) {
                const result = extractPlainTitle(value[key], depth + 1);
                if (result) {
                    return result;
                }
            }
        }
        // 没有找到标题字段，返回空
        return '';
    }
    
    // 数组处理 - 取第一个元素
    if (Array.isArray(value) && value.length > 0) {
        return extractPlainTitle(value[0], depth + 1);
    }
    
    // 其他类型转字符串
    return String(value || '');
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// ===== 全局暴露 =====
window.trendsState = trendsState;
window.initTrendsModule = initTrendsModule;
window.loadTrendsConfig = loadTrendsConfig;
window.checkTrendsService = checkTrendsService;
window.fetchTrends = fetchTrends;
window.saveTrendsConfig = saveTrendsConfig;
window.saveTrendsVisibility = saveTrendsVisibility;
window.renderTrendsPanel = renderTrendsPanel;
window.renderTrendsSettings = renderTrendsSettings;
window.showTrendsModal = showTrendsModal;

console.log('[app-trends.js] 热点搜索模块已加载');
