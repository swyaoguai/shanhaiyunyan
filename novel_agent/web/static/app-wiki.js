/**
 * Wiki 知识系统前端模块
 * 
 * 功能：
 * - Wiki 页面浏览（按类型分组）
 * - 页面搜索（文本搜索 + 多阶段检索）
 * - 知识图谱可视化
 * - Lint 质量检查
 * - Review 审核管理
 * - 页面 CRUD
 */

(function () {
    'use strict';

    const WIKI_API = '/api/v1/wiki';
    let currentPage = null;
    let allPages = [];

    // ===== 模块注册 =====
    if (typeof window !== 'undefined') {
        window.WikiModule = {
            init: initWikiModule,
            render: renderWikiView,
        };
    }

    function initWikiModule() {
        console.log('[Wiki] 模块初始化');
    }

    // ===== 主渲染 =====
    async function renderWikiView() {
        const container = document.getElementById('main-view');
        if (!container) return;

        container.innerHTML = `
            <div class="wiki-container" style="padding: 20px; max-width: 1200px; margin: 0 auto;">
                <div class="wiki-header" style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px;">
                    <h2 style="margin: 0;">📖 Wiki 知识系统</h2>
                    <div style="display: flex; gap: 8px;">
                        <input type="text" id="wiki-search-input" placeholder="搜索页面..." 
                            style="padding: 8px 12px; border: 1px solid var(--border-color, #333); 
                            border-radius: 6px; background: var(--bg-secondary, #1a1a2e); 
                            color: var(--text-primary, #fff); width: 250px;">
                        <button onclick="WikiModule.search()" class="btn btn-primary" 
                            style="padding: 8px 16px; border-radius: 6px;">🔍 搜索</button>
                        <button onclick="WikiModule.showLint()" class="btn btn-secondary" 
                            style="padding: 8px 16px; border-radius: 6px;">🔍 Lint检查</button>
                        <button onclick="WikiModule.showGraph()" class="btn btn-secondary" 
                            style="padding: 8px 16px; border-radius: 6px;">🕸️ 知识图谱</button>
                        <button onclick="WikiModule.createPage()" class="btn btn-primary" 
                            style="padding: 8px 16px; border-radius: 6px;">+ 新建页面</button>
                    </div>
                </div>
                <div id="wiki-stats" style="margin-bottom: 16px;"></div>
                <div id="wiki-content">
                    <div style="text-align: center; padding: 40px; color: var(--text-secondary, #888);">
                        加载中...
                    </div>
                </div>
            </div>
        `;

        await loadPages();
    }

    // ===== 加载页面列表 =====
    async function loadPages(pageType) {
        try {
            let url = `${WIKI_API}/pages`;
            if (pageType) url += `?page_type=${pageType}`;
            
            const resp = await fetch(url);
            const data = await resp.json();
            
            if (data.success) {
                allPages = data.data;
                renderPageList(allPages);
                renderStats(data.total);
            }
        } catch (e) {
            console.error('[Wiki] 加载页面失败:', e);
            document.getElementById('wiki-content').innerHTML = 
                '<div style="color: #f44; padding: 20px;">加载失败: ' + e.message + '</div>';
        }
    }

    function renderStats(total) {
        const statsEl = document.getElementById('wiki-stats');
        if (!statsEl) return;
        
        const typeCounts = {};
        allPages.forEach(p => {
            typeCounts[p.page_type] = (typeCounts[p.page_type] || 0) + 1;
        });
        
        const typeButtons = Object.entries(typeCounts).map(([type, count]) => 
            `<button onclick="WikiModule.filterType('${type}')" 
                style="padding: 4px 12px; border-radius: 12px; border: 1px solid var(--border-color, #444); 
                background: var(--bg-secondary, #1a1a2e); color: var(--text-primary, #fff); cursor: pointer; font-size: 12px;">
                ${type} (${count})
            </button>`
        ).join(' ');
        
        statsEl.innerHTML = `
            <div style="display: flex; align-items: center; gap: 12px; flex-wrap: wrap;">
                <span style="color: var(--text-secondary, #888);">共 ${total} 个页面</span>
                <button onclick="WikiModule.loadPages()" 
                    style="padding: 4px 12px; border-radius: 12px; border: 1px solid var(--accent-color, #4a9eff); 
                    background: transparent; color: var(--accent-color, #4a9eff); cursor: pointer; font-size: 12px;">
                    全部
                </button>
                ${typeButtons}
            </div>
        `;
    }

    function renderPageList(pages) {
        const content = document.getElementById('wiki-content');
        if (!content) return;
        
        if (!pages.length) {
            content.innerHTML = '<div style="text-align: center; padding: 40px; color: var(--text-secondary, #888);">暂无页面</div>';
            return;
        }
        
        const typeIcons = {
            character: '👤', world: '🌍', plot: '📖', chapter: '📄',
            constraint: '⚠️', concept: '💡', source: '📚', custom: '📝',
            index: '📋', overview: '📊', log: '📋', purpose: '🎯', schema: '📐',
        };
        
        content.innerHTML = `
            <div style="display: grid; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); gap: 12px;">
                ${pages.map(p => `
                    <div onclick="WikiModule.viewPage('${p.title.replace(/'/g, "\\'")}')" 
                        style="padding: 16px; border: 1px solid var(--border-color, #333); 
                        border-radius: 8px; cursor: pointer; background: var(--bg-secondary, #1a1a2e);
                        transition: border-color 0.2s;"
                        onmouseover="this.style.borderColor='var(--accent-color, #4a9eff)'" 
                        onmouseout="this.style.borderColor='var(--border-color, #333)'">
                        <div style="display: flex; align-items: center; gap: 8px; margin-bottom: 8px;">
                            <span style="font-size: 20px;">${typeIcons[p.page_type] || '📝'}</span>
                            <strong style="font-size: 14px;">${p.title}</strong>
                            <span style="margin-left: auto; font-size: 11px; color: var(--text-secondary, #888); 
                                padding: 2px 8px; border-radius: 10px; background: var(--bg-tertiary, #222);">
                                ${p.page_type}
                            </span>
                        </div>
                        <div style="font-size: 12px; color: var(--text-secondary, #888); margin-bottom: 8px;">
                            ${p.word_count} 字 · ${p.links_out?.length || 0} 个链接
                        </div>
                        ${p.tags?.length ? `
                            <div style="display: flex; gap: 4px; flex-wrap: wrap;">
                                ${p.tags.slice(0, 5).map(t => 
                                    `<span style="font-size: 10px; padding: 2px 6px; border-radius: 8px; 
                                    background: var(--accent-bg, rgba(74,158,255,0.1)); color: var(--accent-color, #4a9eff);">${t}</span>`
                                ).join('')}
                            </div>
                        ` : ''}
                    </div>
                `).join('')}
            </div>
        `;
    }

    // ===== 查看页面详情 =====
    async function viewPage(title) {
        try {
            const resp = await fetch(`${WIKI_API}/pages/${encodeURIComponent(title)}`);
            const data = await resp.json();
            
            if (!data.success) throw new Error(data.detail || '获取失败');
            
            currentPage = data.data;
            renderPageDetail(currentPage);
        } catch (e) {
            console.error('[Wiki] 获取页面失败:', e);
        }
    }

    function renderPageDetail(page) {
        const content = document.getElementById('wiki-content');
        if (!content) return;
        
        // 简单 Markdown 渲染
        let bodyHtml = page.body
            .replace(/^### (.+)$/gm, '<h3>$1</h3>')
            .replace(/^## (.+)$/gm, '<h2 style="margin-top: 16px;">$1</h2>')
            .replace(/^# (.+)$/gm, '<h1 style="margin-top: 20px;">$1</h1>')
            .replace(/\[\[([^\]]+)\]\]/g, '<a href="javascript:void(0)" onclick="WikiModule.viewPage(\'$1\')" style="color: var(--accent-color, #4a9eff); text-decoration: underline;">$1</a>')
            .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
            .replace(/\n/g, '<br>');
        
        content.innerHTML = `
            <div style="max-width: 800px;">
                <div class="app-back-row">
                    <button onclick="WikiModule.loadPages()" type="button" class="app-back-button">
                        <i class="ri-arrow-left-line"></i>
                        <span>返回列表</span>
                    </button>
                </div>
                
                <div style="padding: 24px; border: 1px solid var(--border-color, #333); border-radius: 12px; 
                    background: var(--bg-secondary, #1a1a2e);">
                    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px;">
                        <h2 style="margin: 0;">${page.title}</h2>
                        <div style="display: flex; gap: 8px;">
                            <span style="font-size: 12px; padding: 4px 10px; border-radius: 10px; 
                                background: var(--bg-tertiary, #222);">${page.page_type}</span>
                            <button onclick="WikiModule.editPage('${page.title.replace(/'/g, "\\'")}')" 
                                style="padding: 4px 12px; border-radius: 6px; border: 1px solid var(--border-color, #444); 
                                background: transparent; color: var(--text-primary, #fff); cursor: pointer; font-size: 12px;">
                                ✏️ 编辑
                            </button>
                            <button onclick="WikiModule.deletePage('${page.title.replace(/'/g, "\\'")}')" 
                                style="padding: 4px 12px; border-radius: 6px; border: 1px solid #f44; 
                                background: transparent; color: #f44; cursor: pointer; font-size: 12px;">
                                🗑️ 删除
                            </button>
                        </div>
                    </div>
                    
                    <div style="font-size: 12px; color: var(--text-secondary, #888); margin-bottom: 16px;">
                        ${page.word_count} 字 · 创建于 ${page.created_at || '-'} · 更新于 ${page.updated_at || '-'}
                    </div>
                    
                    ${page.tags?.length ? `
                        <div style="display: flex; gap: 4px; margin-bottom: 16px; flex-wrap: wrap;">
                            ${page.tags.map(t => 
                                `<span style="font-size: 11px; padding: 2px 8px; border-radius: 10px; 
                                background: var(--accent-bg, rgba(74,158,255,0.1)); color: var(--accent-color, #4a9eff);">${t}</span>`
                            ).join('')}
                        </div>
                    ` : ''}
                    
                    <div style="line-height: 1.8; font-size: 14px;">${bodyHtml}</div>
                    
                    ${(page.links_out?.length || page.links_in?.length) ? `
                        <div style="margin-top: 24px; padding-top: 16px; border-top: 1px solid var(--border-color, #333);">
                            ${page.links_out?.length ? `
                                <div style="margin-bottom: 8px;">
                                    <strong style="font-size: 12px; color: var(--text-secondary, #888);">链接到 →</strong>
                                    <div style="display: flex; gap: 4px; flex-wrap: wrap; margin-top: 4px;">
                                        ${page.links_out.map(l => 
                                            `<a href="javascript:void(0)" onclick="WikiModule.viewPage('${l.replace(/'/g, "\\'")}')"
                                                style="font-size: 12px; padding: 2px 8px; border-radius: 10px; 
                                                background: var(--bg-tertiary, #222); color: var(--accent-color, #4a9eff); 
                                                text-decoration: none;">${l}</a>`
                                        ).join('')}
                                    </div>
                                </div>
                            ` : ''}
                            ${page.links_in?.length ? `
                                <div>
                                    <strong style="font-size: 12px; color: var(--text-secondary, #888);">被引用 ←</strong>
                                    <div style="display: flex; gap: 4px; flex-wrap: wrap; margin-top: 4px;">
                                        ${page.links_in.map(l => 
                                            `<a href="javascript:void(0)" onclick="WikiModule.viewPage('${l.replace(/'/g, "\\'")}')"
                                                style="font-size: 12px; padding: 2px 8px; border-radius: 10px; 
                                                background: var(--bg-tertiary, #222); color: var(--accent-color, #4a9eff); 
                                                text-decoration: none;">${l}</a>`
                                        ).join('')}
                                    </div>
                                </div>
                            ` : ''}
                        </div>
                    ` : ''}
                </div>
            </div>
        `;
    }

    // ===== 搜索 =====
    async function search() {
        const input = document.getElementById('wiki-search-input');
        const query = input?.value?.trim();
        if (!query) return;
        
        try {
            const resp = await fetch(`${WIKI_API}/search/text?q=${encodeURIComponent(query)}&top_k=20`);
            const data = await resp.json();
            
            if (data.success) {
                renderPageList(data.data.map(p => ({
                    title: p.title,
                    page_type: p.page_type,
                    tags: p.tags,
                    word_count: p.summary?.length || 0,
                    links_out: [],
                })));
            }
        } catch (e) {
            console.error('[Wiki] 搜索失败:', e);
        }
    }

    function filterType(type) {
        const filtered = allPages.filter(p => p.page_type === type);
        renderPageList(filtered);
    }

    // ===== 知识图谱 =====
    async function showGraph() {
        const content = document.getElementById('wiki-content');
        if (!content) return;
        
        content.innerHTML = '<div style="text-align: center; padding: 40px;">加载图谱数据...</div>';
        
        try {
            const resp = await fetch(`${WIKI_API}/graph`);
            const data = await resp.json();
            
            if (!data.success) throw new Error('获取图谱失败');
            
            const { nodes, edges, statistics } = data.data;
            
            // 简单的图谱可视化（文本形式）
            content.innerHTML = `
                <div style="padding: 20px;">
                    <div class="app-back-row">
                        <button onclick="WikiModule.loadPages()" type="button" class="app-back-button">
                            <i class="ri-arrow-left-line"></i>
                            <span>返回列表</span>
                        </button>
                    </div>
                    
                    <h3>🕸️ 知识图谱</h3>
                    
                    <div style="display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; margin-bottom: 24px;">
                        <div style="padding: 16px; border-radius: 8px; background: var(--bg-secondary, #1a1a2e); text-align: center;">
                            <div style="font-size: 24px; font-weight: bold; color: var(--accent-color, #4a9eff);">${statistics.nodes}</div>
                            <div style="font-size: 12px; color: var(--text-secondary, #888);">节点</div>
                        </div>
                        <div style="padding: 16px; border-radius: 8px; background: var(--bg-secondary, #1a1a2e); text-align: center;">
                            <div style="font-size: 24px; font-weight: bold; color: var(--accent-color, #4a9eff);">${statistics.edges}</div>
                            <div style="font-size: 12px; color: var(--text-secondary, #888);">连接</div>
                        </div>
                        <div style="padding: 16px; border-radius: 8px; background: var(--bg-secondary, #1a1a2e); text-align: center;">
                            <div style="font-size: 24px; font-weight: bold; color: var(--accent-color, #4a9eff);">${statistics.avg_degree?.toFixed(1) || 0}</div>
                            <div style="font-size: 12px; color: var(--text-secondary, #888);">平均度数</div>
                        </div>
                        <div style="padding: 16px; border-radius: 8px; background: var(--bg-secondary, #1a1a2e); text-align: center;">
                            <div style="font-size: 24px; font-weight: bold; color: ${statistics.isolated_count > 0 ? '#f44' : '#4a4'};">${statistics.isolated_count}</div>
                            <div style="font-size: 12px; color: var(--text-secondary, #888);">孤立页面</div>
                        </div>
                    </div>
                    
                    <h4>连接关系 (${edges.length})</h4>
                    <div style="max-height: 400px; overflow-y: auto;">
                        ${edges.slice(0, 100).map(e => `
                            <div style="padding: 8px 12px; border-bottom: 1px solid var(--border-color, #222); font-size: 13px;">
                                <a href="javascript:void(0)" onclick="WikiModule.viewPage('${e.source.replace(/'/g, "\\'")}')"
                                    style="color: var(--accent-color, #4a9eff); text-decoration: none;">${e.source}</a>
                                <span style="color: var(--text-secondary, #888);"> → </span>
                                <a href="javascript:void(0)" onclick="WikiModule.viewPage('${e.target.replace(/'/g, "\\'")}')"
                                    style="color: var(--accent-color, #4a9eff); text-decoration: none;">${e.target}</a>
                                <span style="float: right; font-size: 11px; color: var(--text-secondary, #666);">
                                    权重: ${e.weight} · ${Object.keys(e.signals).join(', ')}
                                </span>
                            </div>
                        `).join('')}
                    </div>
                </div>
            `;
        } catch (e) {
            content.innerHTML = `<div style="color: #f44; padding: 20px;">加载图谱失败: ${e.message}</div>`;
        }
    }

    // ===== Lint 检查 =====
    async function showLint() {
        const content = document.getElementById('wiki-content');
        if (!content) return;
        
        content.innerHTML = '<div style="text-align: center; padding: 40px;">运行 Lint 检查...</div>';
        
        try {
            const resp = await fetch(`${WIKI_API}/lint`);
            const data = await resp.json();
            
            if (!data.success) throw new Error('Lint 检查失败');
            
            const d = data.data;
            content.innerHTML = `
                <div style="padding: 20px;">
                    <div class="app-back-row">
                        <button onclick="WikiModule.loadPages()" type="button" class="app-back-button">
                            <i class="ri-arrow-left-line"></i>
                            <span>返回列表</span>
                        </button>
                    </div>
                    
                    <h3>🔍 Lint 质量检查报告</h3>
                    
                    <div style="display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; margin-bottom: 24px;">
                        <div style="padding: 16px; border-radius: 8px; background: var(--bg-secondary, #1a1a2e); text-align: center;">
                            <div style="font-size: 24px; font-weight: bold;">${d.total_pages}</div>
                            <div style="font-size: 12px; color: var(--text-secondary, #888);">总页面</div>
                        </div>
                        <div style="padding: 16px; border-radius: 8px; background: var(--bg-secondary, #1a1a2e); text-align: center;">
                            <div style="font-size: 24px; font-weight: bold;">${d.total_links}</div>
                            <div style="font-size: 12px; color: var(--text-secondary, #888);">总链接</div>
                        </div>
                        <div style="padding: 16px; border-radius: 8px; background: var(--bg-secondary, #1a1a2e); text-align: center;">
                            <div style="font-size: 24px; font-weight: bold; color: ${d.isolated_count > 0 ? '#fa0' : '#4a4'};">${d.isolated_count}</div>
                            <div style="font-size: 12px; color: var(--text-secondary, #888);">孤立页面</div>
                        </div>
                        <div style="padding: 16px; border-radius: 8px; background: var(--bg-secondary, #1a1a2e); text-align: center;">
                            <div style="font-size: 24px; font-weight: bold; color: ${d.dead_link_count > 0 ? '#f44' : '#4a4'};">${d.dead_link_count}</div>
                            <div style="font-size: 12px; color: var(--text-secondary, #888);">死链接</div>
                        </div>
                    </div>
                    
                    ${d.issues.length ? `
                        <h4>问题列表 (${d.issues.length})</h4>
                        <div style="max-height: 400px; overflow-y: auto;">
                            ${d.issues.map(i => `
                                <div style="padding: 12px; border: 1px solid var(--border-color, #333); 
                                    border-radius: 8px; margin-bottom: 8px; background: var(--bg-secondary, #1a1a2e);">
                                    <div style="display: flex; align-items: center; gap: 8px; margin-bottom: 4px;">
                                        <span style="font-size: 11px; padding: 2px 8px; border-radius: 10px; 
                                            background: ${i.severity === 'critical' ? '#f44' : i.severity === 'high' ? '#fa0' : i.severity === 'medium' ? '#4a9eff' : '#888'}22; 
                                            color: ${i.severity === 'critical' ? '#f44' : i.severity === 'high' ? '#fa0' : i.severity === 'medium' ? '#4a9eff' : '#888'};">
                                            ${i.severity}
                                        </span>
                                        <span style="font-size: 12px; color: var(--text-secondary, #888);">${i.type}</span>
                                        <a href="javascript:void(0)" onclick="WikiModule.viewPage('${i.page.replace(/'/g, "\\'")}')"
                                            style="color: var(--accent-color, #4a9eff); text-decoration: none; font-size: 13px;">${i.page}</a>
                                    </div>
                                    <div style="font-size: 13px;">${i.description}</div>
                                    ${i.suggestion ? `<div style="font-size: 12px; color: var(--text-secondary, #888); margin-top: 4px;">💡 ${i.suggestion}</div>` : ''}
                                </div>
                            `).join('')}
                        </div>
                    ` : '<div style="text-align: center; padding: 40px; color: #4a4;">✅ 没有发现问题</div>'}
                </div>
            `;
        } catch (e) {
            content.innerHTML = `<div style="color: #f44; padding: 20px;">Lint 检查失败: ${e.message}</div>`;
        }
    }

    // ===== 创建页面 =====
    function createPage() {
        const content = document.getElementById('wiki-content');
        if (!content) return;
        
        content.innerHTML = `
            <div style="max-width: 600px; padding: 20px;">
                <div class="app-back-row">
                    <button onclick="WikiModule.loadPages()" type="button" class="app-back-button">
                        <i class="ri-arrow-left-line"></i>
                        <span>返回列表</span>
                    </button>
                </div>
                
                <h3>新建 Wiki 页面</h3>
                
                <div style="margin-bottom: 12px;">
                    <label style="display: block; font-size: 12px; color: var(--text-secondary, #888); margin-bottom: 4px;">标题</label>
                    <input type="text" id="wiki-new-title" placeholder="页面标题" 
                        style="width: 100%; padding: 8px 12px; border: 1px solid var(--border-color, #333); 
                        border-radius: 6px; background: var(--bg-tertiary, #222); color: var(--text-primary, #fff);">
                </div>
                
                <div style="margin-bottom: 12px;">
                    <label style="display: block; font-size: 12px; color: var(--text-secondary, #888); margin-bottom: 4px;">类型</label>
                    <select id="wiki-new-type" style="width: 100%; padding: 8px 12px; border: 1px solid var(--border-color, #333); 
                        border-radius: 6px; background: var(--bg-tertiary, #222); color: var(--text-primary, #fff);">
                        <option value="character">角色</option>
                        <option value="world">世界观</option>
                        <option value="plot">剧情</option>
                        <option value="chapter">章节摘要</option>
                        <option value="constraint">约束</option>
                        <option value="concept">概念</option>
                        <option value="custom" selected>自定义</option>
                    </select>
                </div>
                
                <div style="margin-bottom: 12px;">
                    <label style="display: block; font-size: 12px; color: var(--text-secondary, #888); margin-bottom: 4px;">标签（逗号分隔）</label>
                    <input type="text" id="wiki-new-tags" placeholder="标签1, 标签2" 
                        style="width: 100%; padding: 8px 12px; border: 1px solid var(--border-color, #333); 
                        border-radius: 6px; background: var(--bg-tertiary, #222); color: var(--text-primary, #fff);">
                </div>
                
                <div style="margin-bottom: 16px;">
                    <label style="display: block; font-size: 12px; color: var(--text-secondary, #888); margin-bottom: 4px;">内容</label>
                    <textarea id="wiki-new-body" rows="10" placeholder="Markdown 内容..." 
                        style="width: 100%; padding: 8px 12px; border: 1px solid var(--border-color, #333); 
                        border-radius: 6px; background: var(--bg-tertiary, #222); color: var(--text-primary, #fff); 
                        font-family: monospace; resize: vertical;"></textarea>
                </div>
                
                <button onclick="WikiModule.submitCreate()" class="btn btn-primary" 
                    style="padding: 10px 24px; border-radius: 6px;">创建页面</button>
            </div>
        `;
    }

    async function submitCreate() {
        const title = document.getElementById('wiki-new-title')?.value?.trim();
        const pageType = document.getElementById('wiki-new-type')?.value;
        const tags = document.getElementById('wiki-new-tags')?.value?.split(',').map(t => t.trim()).filter(Boolean);
        const body = document.getElementById('wiki-new-body')?.value;
        
        if (!title) { alert('请输入标题'); return; }
        
        try {
            const resp = await fetch(`${WIKI_API}/pages`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ title, page_type: pageType, body: body || '', tags: tags || [] }),
            });
            const data = await resp.json();
            
            if (data.success) {
                viewPage(title);
            } else {
                alert('创建失败: ' + (data.detail || '未知错误'));
            }
        } catch (e) {
            alert('创建失败: ' + e.message);
        }
    }

    // ===== 编辑页面 =====
    async function editPage(title) {
        try {
            const resp = await fetch(`${WIKI_API}/pages/${encodeURIComponent(title)}`);
            const data = await resp.json();
            if (!data.success) throw new Error('获取失败');
            
            const page = data.data;
            const content = document.getElementById('wiki-content');
            
            content.innerHTML = `
                <div style="max-width: 800px; padding: 20px;">
                    <div style="margin-bottom: 16px;">
                        <button onclick="WikiModule.viewPage('${title.replace(/'/g, "\\'")}')"
                            style="padding: 6px 12px; border-radius: 6px; border: 1px solid var(--border-color, #444); 
                            background: transparent; color: var(--text-primary, #fff); cursor: pointer;">
                            ← 取消
                        </button>
                    </div>
                    
                    <h3>编辑: ${title}</h3>
                    
                    <div style="margin-bottom: 12px;">
                        <label style="display: block; font-size: 12px; color: var(--text-secondary, #888); margin-bottom: 4px;">标签</label>
                        <input type="text" id="wiki-edit-tags" value="${(page.tags || []).join(', ')}" 
                            style="width: 100%; padding: 8px 12px; border: 1px solid var(--border-color, #333); 
                            border-radius: 6px; background: var(--bg-tertiary, #222); color: var(--text-primary, #fff);">
                    </div>
                    
                    <div style="margin-bottom: 16px;">
                        <label style="display: block; font-size: 12px; color: var(--text-secondary, #888); margin-bottom: 4px;">内容</label>
                        <textarea id="wiki-edit-body" rows="15" 
                            style="width: 100%; padding: 8px 12px; border: 1px solid var(--border-color, #333); 
                            border-radius: 6px; background: var(--bg-tertiary, #222); color: var(--text-primary, #fff); 
                            font-family: monospace; resize: vertical;">${page.body || ''}</textarea>
                    </div>
                    
                    <button onclick="WikiModule.submitEdit('${title.replace(/'/g, "\\'")}')" class="btn btn-primary" 
                        style="padding: 10px 24px; border-radius: 6px;">保存</button>
                </div>
            `;
        } catch (e) {
            alert('加载失败: ' + e.message);
        }
    }

    async function submitEdit(title) {
        const body = document.getElementById('wiki-edit-body')?.value;
        const tags = document.getElementById('wiki-edit-tags')?.value?.split(',').map(t => t.trim()).filter(Boolean);
        
        try {
            const resp = await fetch(`${WIKI_API}/pages/${encodeURIComponent(title)}`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ body, tags }),
            });
            const data = await resp.json();
            
            if (data.success) {
                viewPage(title);
            } else {
                alert('保存失败: ' + (data.detail || '未知错误'));
            }
        } catch (e) {
            alert('保存失败: ' + e.message);
        }
    }

    // ===== 删除页面 =====
    async function deletePage(title) {
        if (!confirm(`确定删除页面 "${title}" 吗？`)) return;
        
        try {
            const resp = await fetch(`${WIKI_API}/pages/${encodeURIComponent(title)}`, { method: 'DELETE' });
            const data = await resp.json();
            
            if (data.success) {
                loadPages();
            } else {
                alert('删除失败');
            }
        } catch (e) {
            alert('删除失败: ' + e.message);
        }
    }

    // ===== 导出到全局 =====
    window.WikiModule = {
        init: initWikiModule,
        render: renderWikiView,
        loadPages,
        search,
        filterType,
        viewPage,
        showGraph,
        showLint,
        createPage,
        submitCreate,
        editPage,
        submitEdit,
        deletePage,
    };

    console.log('[app-wiki.js] Wiki知识系统模块已加载');
})();
