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
    const SYSTEM_PAGE_TYPES = new Set(['index', 'purpose', 'schema', 'log']);
    const HIDDEN_BODY_HEADINGS = new Set([
        'id', 'uuid', 'slug', 'thread_id', 'thread_title', 'thread_type',
        'created_at', 'updated_at', 'created', 'updated', 'metadata',
        'source', 'sources', 'raw', 'raw_data', 'status', 'name'
    ]);
    const TYPE_LABELS = {
        character: '角色',
        world: '世界观',
        plot: '剧情',
        chapter: '章节摘要',
        constraint: '约束',
        concept: '概念',
        source: '来源',
        query: '查询',
        synthesis: '综合分析',
        comparison: '对比分析',
        custom: '自定义',
        index: '目录',
        overview: '概览',
        log: '日志',
        purpose: '创作目标',
        schema: '结构规则',
    };
    const TYPE_ICONS = {
        character: 'ri-user-3-line',
        world: 'ri-earth-line',
        plot: 'ri-route-line',
        chapter: 'ri-file-list-3-line',
        constraint: 'ri-alert-line',
        concept: 'ri-lightbulb-line',
        source: 'ri-book-read-line',
        custom: 'ri-draft-line',
        index: 'ri-book-open-line',
        overview: 'ri-bar-chart-box-line',
        log: 'ri-file-history-line',
        purpose: 'ri-focus-3-line',
        schema: 'ri-ruler-2-line',
    };
    const BODY_HEADING_LABELS = {
        description: '简介',
        summary: '摘要',
        conflict: '冲突',
        goal: '目标',
        goals: '目标',
        participants: '相关角色',
        key_events: '关键事件',
        appearing_characters: '出场角色',
        ending_hook: '结尾钩子',
        notes: '备注',
        details: '详细设定',
        relationships: '关系',
        abilities: '技能/能力',
        inventory: '持有物/道具',
        development_history: '成长记录',
    };
    const GRAPH_CATEGORIES = {
        all: { label: '全部', color: '#8aa4ff' },
        character: { label: '角色', color: '#5572d8' },
        location: { label: '地点', color: '#7cc66c' },
        item: { label: '物件', color: '#f0c35a' },
        faction: { label: '势力', color: '#ea6666' },
        event: { label: '事件', color: '#6bb9d6' },
        power: { label: '功法', color: '#42a36f' },
        clue: { label: '线索', color: '#ff885a' },
    };
    const RELATION_LABELS = {
        explicit_link: '引用',
        backlink: '反链',
        tag_overlap: '同标签',
        shared_tag: '同标签',
        entity_overlap: '同实体',
        co_occurrence: '共现',
        semantic: '语义相关',
        related: '相关',
    };

    let currentPage = null;
    let allPages = [];
    let wikiState = {
        showSystemPages: false,
        activeGraphType: 'all',
        graphScope: 'all',
        graphData: null,
        selectedGraphNode: '',
    };

    if (typeof window !== 'undefined') {
        window.WikiModule = {
            init: initWikiModule,
            render: renderWikiView,
        };
    }

    function initWikiModule() {
        console.log('[Wiki] 模块初始化');
    }

    function isWikiRenderCurrent(renderToken) {
        if (!renderToken) return true;
        const moduleId = renderToken.moduleId || 'wiki';
        const guard = window.NovelAgentApp?.core?.isCurrentModuleRender;
        if (typeof guard === 'function') {
            return guard(moduleId, renderToken);
        }
        return ['wiki', 'aux-memory', 'knowledge-workbench'].includes(window.store?.currentModule);
    }

    async function renderWikiView(renderToken = null) {
        const container = document.getElementById('main-view');
        if (!container) return;

        container.innerHTML = `
            <div class="wiki-container" style="padding: 24px; max-width: 1280px; margin: 0 auto;">
                <div class="wiki-header" style="display: flex; justify-content: space-between; align-items: center; gap: 16px; margin-bottom: 22px;">
                    <h2 style="margin: 0; color: var(--text-primary); display: flex; align-items: center; gap: 10px;">
                        <i class="ri-book-open-line" style="color: #8ab4ff;"></i>
                        Wiki 知识系统
                    </h2>
                    <div style="display: flex; gap: 8px; align-items: center; flex-wrap: wrap;">
                        <input type="text" id="wiki-search-input" placeholder="搜索页面..."
                            style="padding: 10px 12px; border: 1px solid var(--border-color, #333);
                            border-radius: 8px; background: rgba(0,0,0,0.22);
                            color: var(--text-primary, #fff); width: 260px;">
                        <button onclick="WikiModule.search()" class="btn btn-primary"
                            style="padding: 9px 16px; border-radius: 8px;"><i class="ri-search-line"></i> 搜索</button>
                        <button onclick="WikiModule.showLint()" class="btn btn-secondary"
                            style="padding: 9px 16px; border-radius: 8px;"><i class="ri-search-eye-line"></i> 检查</button>
                        <button onclick="WikiModule.showGraph()" class="btn btn-secondary"
                            style="padding: 9px 16px; border-radius: 8px;"><i class="ri-bubble-chart-line"></i> 知识图谱</button>
                        <button onclick="WikiModule.createPage()" class="btn btn-primary"
                            style="padding: 9px 16px; border-radius: 8px;"><i class="ri-add-line"></i> 新建页面</button>
                    </div>
                </div>
                <div id="wiki-stats" style="margin-bottom: 16px;"></div>
                <div id="wiki-content">
                    <div style="text-align: center; padding: 40px; color: var(--text-secondary, #888);">加载中...</div>
                </div>
            </div>
        `;

        const input = document.getElementById('wiki-search-input');
        input?.addEventListener('keydown', (event) => {
            if (event.key === 'Enter') search();
        });

        await loadPages(undefined, renderToken);
    }

    async function loadPages(pageType, renderToken = null) {
        try {
            let url = `${WIKI_API}/pages`;
            if (pageType) url += `?page_type=${encodeURIComponent(pageType)}`;

            const resp = await fetch(url);
            const data = await resp.json();
            if (!isWikiRenderCurrent(renderToken)) return;

            if (data.success) {
                allPages = data.data || [];
                renderPageList(getVisiblePages(allPages));
                renderStats(data.total || allPages.length);
            }
        } catch (e) {
            console.error('[Wiki] 加载页面失败:', e);
            const content = document.getElementById('wiki-content');
            if (content) {
                content.innerHTML = `<div style="color: #ef4444; padding: 20px;">加载失败: ${escapeHtml(e.message)}</div>`;
            }
        }
    }

    function renderStats(total) {
        const statsEl = document.getElementById('wiki-stats');
        if (!statsEl) return;

        const visiblePages = getVisiblePages(allPages);
        const typeCounts = {};
        visiblePages.forEach(p => {
            typeCounts[p.page_type] = (typeCounts[p.page_type] || 0) + 1;
        });

        const typeButtons = Object.entries(typeCounts)
            .sort(([left], [right]) => getPageTypeLabel(left).localeCompare(getPageTypeLabel(right), 'zh-Hans-CN'))
            .map(([type, count]) => `
                <button onclick="WikiModule.filterType('${escapeJsString(type)}')"
                    style="padding: 5px 12px; border-radius: 999px; border: 1px solid var(--border-color, #444);
                    background: rgba(255,255,255,0.04); color: var(--text-primary, #fff); cursor: pointer; font-size: 12px;">
                    ${getPageTypeLabel(type)} (${count})
                </button>
            `).join('');

        statsEl.innerHTML = `
            <div style="display: flex; align-items: center; gap: 10px; flex-wrap: wrap;">
                <span style="color: var(--text-secondary, #888);">共 ${visiblePages.length} 个创作页面</span>
                ${total !== visiblePages.length ? `<span style="color: var(--text-secondary, #888); font-size: 12px;">已隐藏 ${total - visiblePages.length} 个系统页</span>` : ''}
                <button onclick="WikiModule.loadPages()"
                    style="padding: 5px 12px; border-radius: 999px; border: 1px solid var(--accent-color, #4a9eff);
                    background: rgba(74,158,255,0.1); color: var(--accent-color, #4a9eff); cursor: pointer; font-size: 12px;">
                    全部
                </button>
                ${typeButtons}
                <button onclick="WikiModule.toggleSystemPages()"
                    style="padding: 5px 12px; border-radius: 999px; border: 1px solid var(--border-color, #444);
                    background: ${wikiState.showSystemPages ? 'rgba(74,158,255,0.14)' : 'rgba(255,255,255,0.03)'};
                    color: var(--text-secondary, #a5adbd); cursor: pointer; font-size: 12px;">
                    ${wikiState.showSystemPages ? '隐藏系统页' : '显示系统页'}
                </button>
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

        content.innerHTML = `
            <div style="display: grid; grid-template-columns: repeat(auto-fill, minmax(320px, 1fr)); gap: 14px;">
                ${pages.map(p => `
                    <button onclick="WikiModule.viewPage('${escapeJsString(p.title)}')"
                        style="text-align: left; padding: 18px; min-height: 104px; border: 1px solid var(--border-color, #333);
                        border-radius: 10px; cursor: pointer; background: rgba(18, 20, 42, 0.72);
                        color: var(--text-primary, #fff); transition: border-color 0.2s, transform 0.2s;"
                        onmouseover="this.style.borderColor='var(--accent-color, #4a9eff)'; this.style.transform='translateY(-1px)'"
                        onmouseout="this.style.borderColor='var(--border-color, #333)'; this.style.transform='translateY(0)'">
                        <div style="display: flex; align-items: flex-start; gap: 10px; margin-bottom: 10px;">
                            <i class="${getPageTypeIcon(p.page_type)}" style="font-size: 21px; color: #b6c6ff; margin-top: 1px;"></i>
                            <strong style="font-size: 15px; line-height: 1.35; overflow: hidden; text-overflow: ellipsis;">${escapeHtml(p.title || '未命名页面')}</strong>
                            <span style="margin-left: auto; font-size: 11px; color: var(--text-secondary, #a5adbd);
                                padding: 2px 8px; border-radius: 999px; background: rgba(255,255,255,0.06); white-space: nowrap;">
                                ${getPageTypeLabel(p.page_type)}
                            </span>
                        </div>
                        <div style="font-size: 12px; color: var(--text-secondary, #a5adbd); margin-bottom: 8px;">
                            ${Number(p.word_count || 0)} 字 · ${(p.links_out || []).length} 个链接
                        </div>
                        ${p.tags?.length ? `
                            <div style="display: flex; gap: 4px; flex-wrap: wrap;">
                                ${p.tags.slice(0, 4).map(t => `
                                    <span style="font-size: 10px; padding: 2px 6px; border-radius: 999px;
                                    background: rgba(74,158,255,0.12); color: #8ab4ff;">${escapeHtml(localizeTag(t))}</span>
                                `).join('')}
                            </div>
                        ` : ''}
                    </button>
                `).join('')}
            </div>
        `;
    }

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

        const cleanBody = cleanWikiBodyForReading(page);
        const bodyHtml = markdownToHtml(cleanBody || '暂无正文内容。');

        content.innerHTML = `
            <div style="max-width: 860px;">
                <div class="app-back-row">
                    <button onclick="WikiModule.loadPages()" type="button" class="app-back-button">
                        <i class="ri-arrow-left-line"></i>
                        <span>返回列表</span>
                    </button>
                </div>

                <article style="padding: 26px 28px; border: 1px solid var(--border-color, #333); border-radius: 12px;
                    background: rgba(18, 20, 42, 0.78); color: var(--text-primary, #fff);">
                    <header style="display: flex; justify-content: space-between; align-items: flex-start; gap: 14px; margin-bottom: 18px;">
                        <div>
                            <div style="display: flex; align-items: center; gap: 8px; margin-bottom: 8px;">
                                <span style="font-size: 12px; padding: 3px 9px; border-radius: 999px; background: rgba(255,255,255,0.06); color: var(--text-secondary, #a5adbd);">
                                    ${getPageTypeLabel(page.page_type)}
                                </span>
                                ${SYSTEM_PAGE_TYPES.has(page.page_type) ? '<span style="font-size: 12px; color: #f59e0b;">系统页</span>' : ''}
                            </div>
                            <h2 style="margin: 0; font-size: 24px; line-height: 1.3;">${escapeHtml(page.title)}</h2>
                            <div style="font-size: 12px; color: var(--text-secondary, #a5adbd); margin-top: 8px;">
                                ${Number(page.word_count || 0)} 字 · ${formatDate(page.updated_at) ? `更新于 ${formatDate(page.updated_at)}` : '暂无更新时间'}
                            </div>
                        </div>
                        <div style="display: flex; gap: 8px; flex-shrink: 0;">
                            <button onclick="WikiModule.editPage('${escapeJsString(page.title)}')"
                                style="padding: 7px 12px; border-radius: 7px; border: 1px solid var(--border-color, #444);
                                background: rgba(255,255,255,0.04); color: var(--text-primary, #fff); cursor: pointer; font-size: 12px;">
                                <i class="ri-edit-line"></i> 编辑
                            </button>
                            <button onclick="WikiModule.deletePage('${escapeJsString(page.title)}')"
                                style="padding: 7px 12px; border-radius: 7px; border: 1px solid #ef4444;
                                background: transparent; color: #ef4444; cursor: pointer; font-size: 12px;">
                                <i class="ri-delete-bin-line"></i> 删除
                            </button>
                        </div>
                    </header>

                    ${page.tags?.length ? `
                        <div style="display: flex; gap: 5px; margin-bottom: 18px; flex-wrap: wrap;">
                            ${page.tags.map(t => `
                                <span style="font-size: 11px; padding: 2px 8px; border-radius: 999px;
                                background: rgba(74,158,255,0.12); color: #8ab4ff;">${escapeHtml(localizeTag(t))}</span>
                            `).join('')}
                        </div>
                    ` : ''}

                    <div class="wiki-readable-body" style="line-height: 1.85; font-size: 15px;">${bodyHtml}</div>

                    ${renderPageRelations(page)}
                </article>
            </div>
        `;
    }

    function renderPageRelations(page) {
        if (!(page.links_out?.length || page.links_in?.length)) return '';
        return `
            <div style="margin-top: 26px; padding-top: 18px; border-top: 1px solid var(--border-color, #333);">
                ${page.links_out?.length ? `
                    <div style="margin-bottom: 12px;">
                        <strong style="font-size: 12px; color: var(--text-secondary, #a5adbd);">关联到</strong>
                        <div style="display: flex; gap: 6px; flex-wrap: wrap; margin-top: 6px;">
                            ${page.links_out.map(l => relationPill(l)).join('')}
                        </div>
                    </div>
                ` : ''}
                ${page.links_in?.length ? `
                    <div>
                        <strong style="font-size: 12px; color: var(--text-secondary, #a5adbd);">被引用</strong>
                        <div style="display: flex; gap: 6px; flex-wrap: wrap; margin-top: 6px;">
                            ${page.links_in.map(l => relationPill(l)).join('')}
                        </div>
                    </div>
                ` : ''}
            </div>
        `;
    }

    function relationPill(title) {
        return `
            <a href="javascript:void(0)" onclick="WikiModule.viewPage('${escapeJsString(title)}')"
                style="font-size: 12px; padding: 3px 9px; border-radius: 999px;
                background: rgba(255,255,255,0.06); color: #8ab4ff; text-decoration: none;">
                ${escapeHtml(title)}
            </a>
        `;
    }

    async function search() {
        const input = document.getElementById('wiki-search-input');
        const query = input?.value?.trim();
        if (!query) return;

        try {
            const resp = await fetch(`${WIKI_API}/search/text?q=${encodeURIComponent(query)}&top_k=20`);
            const data = await resp.json();

            if (data.success) {
                renderPageList(getVisiblePages((data.data || []).map(p => ({
                    title: p.title,
                    page_type: p.page_type,
                    tags: p.tags,
                    word_count: p.summary?.length || 0,
                    links_out: [],
                }))));
            }
        } catch (e) {
            console.error('[Wiki] 搜索失败:', e);
        }
    }

    function filterType(type) {
        const filtered = getVisiblePages(allPages).filter(p => p.page_type === type);
        renderPageList(filtered);
    }

    function toggleSystemPages() {
        wikiState.showSystemPages = !wikiState.showSystemPages;
        renderStats(allPages.length);
        renderPageList(getVisiblePages(allPages));
    }

    async function showGraph() {
        const content = document.getElementById('wiki-content');
        if (!content) return;

        content.innerHTML = '<div style="text-align: center; padding: 40px; color: var(--text-secondary, #888);">加载图谱数据...</div>';

        try {
            const resp = await fetch(`${WIKI_API}/graph`);
            const data = await resp.json();

            if (!data.success) throw new Error('获取图谱失败');

            wikiState.graphData = data.data;
            wikiState.selectedGraphNode = '';
            renderGraphView(data.data);
        } catch (e) {
            content.innerHTML = `<div style="color: #ef4444; padding: 20px;">加载图谱失败: ${escapeHtml(e.message)}</div>`;
        }
    }

    function renderGraphView(graphData) {
        const content = document.getElementById('wiki-content');
        if (!content) return;
        const nodes = Array.isArray(graphData?.nodes) ? graphData.nodes : [];
        const edges = Array.isArray(graphData?.edges) ? graphData.edges : [];
        const visibleNodes = getGraphFilteredNodes(nodes);
        const visibleIds = new Set(visibleNodes.map(node => node.id));
        const visibleEdges = edges.filter(edge => visibleIds.has(edge.source) && visibleIds.has(edge.target));
        const layout = buildGraphLayout(visibleNodes, visibleEdges);
        const selectedNode = visibleNodes.find(node => node.id === wikiState.selectedGraphNode) || null;
        const statistics = graphData?.statistics || {};

        content.innerHTML = `
            <div style="display: grid; grid-template-columns: 292px minmax(0, 1fr); gap: 18px; min-height: 680px;">
                <aside style="border: 1px solid var(--border-color, #333); border-radius: 14px; background: rgba(255,255,255,0.03); overflow: hidden;">
                    <div style="padding: 16px; border-bottom: 1px solid var(--border-color, #333); display: flex; align-items: center; justify-content: space-between;">
                        <strong style="color: var(--text-primary, #fff);">图谱文件</strong>
                        <button onclick="WikiModule.showGraph()" title="刷新"
                            style="width: 34px; height: 34px; border-radius: 10px; border: 1px solid var(--border-color, #444); background: transparent; color: var(--text-primary, #fff); cursor: pointer;">
                            <i class="ri-refresh-line"></i>
                        </button>
                    </div>
                    <div style="padding: 14px;">
                        <button style="width: 100%; text-align: left; padding: 14px; border: 1px solid var(--accent-color, #4a9eff); border-radius: 10px; background: rgba(74,158,255,0.12); color: var(--text-primary, #fff); cursor: default;">
                            <div style="font-weight: 700; margin-bottom: 8px;">当前项目图谱</div>
                            <div style="font-size: 12px; color: var(--text-secondary, #a5adbd);">${nodes.length} 实体 · ${edges.length} 关系</div>
                            <div style="font-size: 12px; color: var(--text-secondary, #a5adbd); margin-top: 6px;">基于 Wiki 页面和双向链接生成</div>
                        </button>
                        <div style="margin-top: 16px; display: grid; grid-template-columns: 1fr 1fr; gap: 8px;">
                            ${graphStatBox(statistics.nodes ?? nodes.length, '实体')}
                            ${graphStatBox(statistics.edges ?? edges.length, '关系')}
                            ${graphStatBox(Number(statistics.avg_degree || 0).toFixed(1), '平均连接')}
                            ${graphStatBox(statistics.isolated_count || 0, '孤立页')}
                        </div>
                    </div>
                </aside>

                <section style="border: 1px solid var(--border-color, #333); border-radius: 14px; background: rgba(255,255,255,0.025); overflow: hidden;">
                    <div style="padding: 16px 18px; border-bottom: 1px solid var(--border-color, #333); display: flex; align-items: center; justify-content: space-between; gap: 12px;">
                        <div style="display: flex; align-items: center; gap: 12px;">
                            <button onclick="WikiModule.loadPages()" type="button" class="app-back-button" style="min-height: 36px; padding: 7px 12px;">
                                <i class="ri-arrow-left-line"></i>
                                <span>返回列表</span>
                            </button>
                            <h3 style="margin: 0; color: var(--text-primary, #fff);">知识图谱</h3>
                        </div>
                        <button onclick="WikiModule.createPage()" class="btn btn-primary" style="padding: 8px 14px; border-radius: 8px;">
                            <i class="ri-add-line"></i> 新建页面
                        </button>
                    </div>

                    <div style="padding: 14px 18px; border-bottom: 1px solid var(--border-color, #333);">
                        <div style="display: flex; align-items: center; gap: 10px; flex-wrap: wrap; margin-bottom: 12px;">
                            <span style="font-size: 13px; color: var(--text-secondary, #a5adbd);">分析范围</span>
                            ${graphScopeButton('all', '全部实体')}
                            ${graphScopeButton('linked', '有关系')}
                            ${graphScopeButton('isolated', '孤立页')}
                        </div>
                        <div style="display: flex; align-items: center; gap: 8px; flex-wrap: wrap;">
                            ${Object.entries(GRAPH_CATEGORIES).map(([key, meta]) => graphCategoryButton(key, meta)).join('')}
                        </div>
                    </div>

                    <div style="display: grid; grid-template-columns: minmax(0, 1fr) 260px; min-height: 520px;">
                        <div id="wiki-graph-canvas" style="position: relative; min-height: 560px; background:
                            radial-gradient(circle at 45% 45%, rgba(74,158,255,0.10), transparent 34%),
                            linear-gradient(180deg, rgba(255,255,255,0.02), rgba(0,0,0,0.04)); overflow: hidden;">
                            ${visibleNodes.length ? renderGraphSvg(visibleEdges, layout) + renderGraphNodes(visibleNodes, layout) : renderGraphEmpty()}
                            <div style="position: absolute; left: 50%; bottom: 18px; transform: translateX(-50%); display: flex; gap: 12px; align-items: center; padding: 8px 12px; border-radius: 999px; background: rgba(10,12,24,0.72); border: 1px solid var(--border-color, #333);">
                                ${Object.entries(GRAPH_CATEGORIES).filter(([key]) => key !== 'all').map(([key, meta]) => `
                                    <span style="display: inline-flex; align-items: center; gap: 5px; font-size: 11px; color: var(--text-secondary, #a5adbd);">
                                        <span style="width: 12px; height: 12px; border-radius: 4px; background: ${meta.color};"></span>${meta.label}
                                    </span>
                                `).join('')}
                            </div>
                        </div>
                        <aside style="border-left: 1px solid var(--border-color, #333); padding: 16px; background: rgba(0,0,0,0.08);">
                            ${renderGraphInspector(selectedNode, visibleEdges)}
                        </aside>
                    </div>
                </section>
            </div>
        `;
    }

    function graphStatBox(value, label) {
        return `
            <div style="padding: 10px; border-radius: 10px; background: rgba(0,0,0,0.18); border: 1px solid var(--border-color, #333);">
                <div style="font-size: 18px; font-weight: 800; color: #8ab4ff;">${escapeHtml(value)}</div>
                <div style="font-size: 11px; color: var(--text-secondary, #a5adbd);">${label}</div>
            </div>
        `;
    }

    function graphScopeButton(scope, label) {
        const active = (wikiState.graphScope || 'all') === scope;
        return `
            <button onclick="WikiModule.setGraphScope('${scope}')"
                style="padding: 8px 16px; border-radius: 999px; border: 1px solid ${active ? 'var(--accent-color, #4a9eff)' : 'var(--border-color, #444)'};
                background: ${active ? 'rgba(74,158,255,0.18)' : 'transparent'}; color: ${active ? '#ffffff' : 'var(--text-secondary, #a5adbd)'};
                cursor: pointer;">${label}</button>
        `;
    }

    function graphCategoryButton(key, meta) {
        const active = wikiState.activeGraphType === key;
        return `
            <button onclick="WikiModule.filterGraphType('${key}')"
                style="padding: 8px 14px; border-radius: 999px; border: 1px solid ${active ? meta.color : 'var(--border-color, #444)'};
                background: ${active ? `${meta.color}33` : 'rgba(255,255,255,0.02)'};
                color: ${active ? '#ffffff' : 'var(--text-primary, #fff)'}; cursor: pointer;">
                ${meta.label}
            </button>
        `;
    }

    function renderGraphSvg(edges, layout) {
        return `
            <svg viewBox="0 0 100 100" preserveAspectRatio="none" style="position: absolute; inset: 0; width: 100%; height: 100%; pointer-events: none;">
                <defs>
                    <marker id="wiki-arrow" markerWidth="5" markerHeight="5" refX="4" refY="2.5" orient="auto">
                        <path d="M0,0 L5,2.5 L0,5 Z" fill="rgba(150,160,185,0.58)"></path>
                    </marker>
                </defs>
                ${edges.map(edge => {
                    const source = layout.get(edge.source);
                    const target = layout.get(edge.target);
                    if (!source || !target) return '';
                    const midX = (source.x + target.x) / 2;
                    const midY = (source.y + target.y) / 2;
                    const label = getRelationLabel(edge);
                    return `
                        <path d="M ${source.x} ${source.y} Q ${midX} ${midY - 6} ${target.x} ${target.y}"
                            fill="none" stroke="rgba(150,160,185,0.45)" stroke-width="${Math.max(0.4, Math.min(1.2, Number(edge.weight || 1) / 2))}"
                            marker-end="url(#wiki-arrow)"></path>
                        ${label ? `<text x="${midX}" y="${midY - 3}" text-anchor="middle" style="font-size: 2.2px; fill: rgba(190,196,210,0.64);">${escapeHtml(label)}</text>` : ''}
                    `;
                }).join('')}
            </svg>
        `;
    }

    function renderGraphNodes(nodes, layout) {
        return nodes.map(node => {
            const pos = layout.get(node.id);
            if (!pos) return '';
            const category = getGraphCategory(node);
            const meta = GRAPH_CATEGORIES[category] || GRAPH_CATEGORIES.clue;
            const active = wikiState.selectedGraphNode === node.id;
            const size = Math.max(42, Math.min(70, 42 + Number(node.degree || 0) * 4));
            return `
                <div data-wiki-graph-node="${escapeAttributeValue(node.id)}"
                    oncontextmenu="WikiModule.openGraphNodeMenu(event, '${escapeJsString(node.id)}')"
                    style="position: absolute; left: ${pos.x}%; top: ${pos.y}%; transform: translate(-50%, -50%); text-align: center; z-index: ${active ? 4 : 2};">
                    <button onclick="WikiModule.selectGraphNode('${escapeJsString(node.id)}')"
                        title="${escapeAttributeValue(node.label || node.id)}"
                        style="width: ${size}px; height: ${size}px; border-radius: 999px; border: ${active ? '3px' : '2px'} solid ${active ? '#ffffff' : meta.color};
                        background: ${meta.color}; box-shadow: ${active ? `0 0 0 8px ${meta.color}33` : `0 10px 24px ${meta.color}22`};
                        cursor: pointer; color: white;"></button>
                    <div style="max-width: 104px; margin-top: 6px; color: var(--text-primary, #fff); font-size: 12px; font-weight: 650; line-height: 1.25; text-shadow: 0 2px 8px rgba(0,0,0,0.45);">
                        ${escapeHtml(node.label || node.id)}
                    </div>
                </div>
            `;
        }).join('');
    }

    function renderGraphInspector(node, edges) {
        if (!node) {
            return `
                <div style="color: var(--text-secondary, #a5adbd);">
                    <h4 style="margin: 0 0 10px; color: var(--text-primary, #fff);">节点详情</h4>
                    <p style="font-size: 13px; line-height: 1.6;">点击任意节点查看关联，也可以右键节点打开操作菜单。</p>
                </div>
            `;
        }
        const related = edges
            .filter(edge => edge.source === node.id || edge.target === node.id)
            .slice(0, 8)
            .map(edge => edge.source === node.id ? edge.target : edge.source);
        const category = getGraphCategory(node);
        const meta = GRAPH_CATEGORIES[category] || GRAPH_CATEGORIES.clue;
        return `
            <div>
                <div style="display: flex; align-items: center; gap: 8px; margin-bottom: 12px;">
                    <span style="width: 14px; height: 14px; border-radius: 5px; background: ${meta.color};"></span>
                    <span style="font-size: 12px; color: var(--text-secondary, #a5adbd);">${meta.label}</span>
                </div>
                <h4 style="margin: 0 0 8px; color: var(--text-primary, #fff); line-height: 1.35;">${escapeHtml(node.label || node.id)}</h4>
                <div style="font-size: 12px; color: var(--text-secondary, #a5adbd); margin-bottom: 14px;">${getPageTypeLabel(node.type)} · ${node.degree || 0} 个连接</div>
                <div style="display: flex; flex-direction: column; gap: 8px; margin-bottom: 16px;">
                    <button onclick="WikiModule.viewPage('${escapeJsString(node.id)}')" style="padding: 9px 12px; border-radius: 8px; border: 1px solid var(--accent-color, #4a9eff); background: rgba(74,158,255,0.14); color: var(--text-primary, #fff); cursor: pointer; text-align: left;">
                        <i class="ri-file-text-line"></i> 打开页面
                    </button>
                    <button onclick="WikiModule.editPage('${escapeJsString(node.id)}')" style="padding: 9px 12px; border-radius: 8px; border: 1px solid var(--border-color, #444); background: transparent; color: var(--text-primary, #fff); cursor: pointer; text-align: left;">
                        <i class="ri-edit-line"></i> 编辑
                    </button>
                    <button onclick="WikiModule.addGraphNodeToWorldbook('${escapeJsString(node.id)}')" style="padding: 9px 12px; border-radius: 8px; border: 1px solid var(--border-color, #444); background: transparent; color: var(--text-primary, #fff); cursor: pointer; text-align: left;">
                        <i class="ri-add-line"></i> 添加到世界书
                    </button>
                </div>
                <div style="font-size: 12px; color: var(--text-secondary, #a5adbd); margin-bottom: 8px;">关联节点</div>
                <div style="display: flex; flex-direction: column; gap: 6px;">
                    ${related.length ? related.map(title => `
                        <button onclick="WikiModule.selectGraphNode('${escapeJsString(title)}')" style="padding: 7px 9px; border-radius: 8px; border: 1px solid var(--border-color, #333); background: rgba(255,255,255,0.03); color: var(--text-primary, #fff); cursor: pointer; text-align: left; font-size: 12px;">
                            ${escapeHtml(title)}
                        </button>
                    `).join('') : '<span style="font-size: 12px; color: var(--text-secondary, #a5adbd);">暂无直接关联</span>'}
                </div>
            </div>
        `;
    }

    function renderGraphEmpty() {
        return '<div style="position: absolute; inset: 0; display: flex; align-items: center; justify-content: center; color: var(--text-secondary, #a5adbd);">暂无可显示的图谱节点</div>';
    }

    function setGraphScope(scope) {
        wikiState.graphScope = scope;
        wikiState.selectedGraphNode = '';
        renderGraphView(wikiState.graphData);
    }

    function filterGraphType(type) {
        wikiState.activeGraphType = type;
        wikiState.selectedGraphNode = '';
        renderGraphView(wikiState.graphData);
    }

    function selectGraphNode(id) {
        wikiState.selectedGraphNode = id;
        renderGraphView(wikiState.graphData);
    }

    function openGraphNodeMenu(event, title) {
        event.preventDefault();
        document.getElementById('wiki-graph-node-menu')?.remove();
        const menu = document.createElement('div');
        menu.id = 'wiki-graph-node-menu';
        menu.style.cssText = `
            position: fixed; left: ${event.clientX}px; top: ${event.clientY}px; z-index: 2000;
            min-width: 190px; padding: 8px; border-radius: 10px; border: 1px solid var(--border-color, #333);
            background: var(--bg-panel, #171b2c); box-shadow: 0 18px 40px rgba(0,0,0,0.28);
        `;
        menu.innerHTML = `
            <button data-action="open" style="${menuButtonStyle()}"><i class="ri-file-text-line"></i> 打开页面</button>
            <button data-action="edit" style="${menuButtonStyle()}"><i class="ri-edit-line"></i> 编辑</button>
            <button data-action="worldbook" style="${menuButtonStyle()}"><i class="ri-add-line"></i> 添加到世界书</button>
        `;
        menu.querySelector('[data-action="open"]')?.addEventListener('click', () => {
            menu.remove();
            viewPage(title);
        });
        menu.querySelector('[data-action="edit"]')?.addEventListener('click', () => {
            menu.remove();
            editPage(title);
        });
        menu.querySelector('[data-action="worldbook"]')?.addEventListener('click', () => {
            menu.remove();
            addGraphNodeToWorldbook(title);
        });
        document.body.appendChild(menu);
        setTimeout(() => {
            document.addEventListener('click', () => menu.remove(), { once: true });
        }, 0);
    }

    function menuButtonStyle() {
        return 'width: 100%; display: flex; align-items: center; gap: 8px; padding: 9px 10px; border: 0; border-radius: 8px; background: transparent; color: var(--text-primary, #fff); cursor: pointer; text-align: left;';
    }

    function addGraphNodeToWorldbook(title) {
        const queue = JSON.parse(localStorage.getItem('wiki_worldbook_queue') || '[]');
        if (!queue.includes(title)) queue.push(title);
        localStorage.setItem('wiki_worldbook_queue', JSON.stringify(queue));
        if (typeof showToast === 'function') {
            showToast(`「${title}」已加入世界书待整理清单`);
        } else {
            alert(`「${title}」已加入世界书待整理清单`);
        }
    }

    async function showLint() {
        const content = document.getElementById('wiki-content');
        if (!content) return;

        content.innerHTML = '<div style="text-align: center; padding: 40px; color: var(--text-secondary, #888);">正在检查 Wiki 质量...</div>';

        try {
            const resp = await fetch(`${WIKI_API}/lint`);
            const data = await resp.json();

            if (!data.success) throw new Error('检查失败');

            const d = data.data || {};
            content.innerHTML = `
                <div style="padding: 20px;">
                    <div class="app-back-row">
                        <button onclick="WikiModule.loadPages()" type="button" class="app-back-button">
                            <i class="ri-arrow-left-line"></i>
                            <span>返回列表</span>
                        </button>
                    </div>

                    <h3 style="margin-top: 0;">Wiki 质量检查</h3>

                    <div style="display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; margin-bottom: 24px;">
                        ${graphStatBox(d.total_pages || 0, '总页面')}
                        ${graphStatBox(d.total_links || 0, '总链接')}
                        ${graphStatBox(d.isolated_count || 0, '孤立页面')}
                        ${graphStatBox(d.dead_link_count || 0, '死链接')}
                    </div>

                    ${Array.isArray(d.issues) && d.issues.length ? `
                        <h4>问题列表 (${d.issues.length})</h4>
                        <div style="max-height: 440px; overflow-y: auto;">
                            ${d.issues.map(issue => `
                                <div style="padding: 12px; border: 1px solid var(--border-color, #333);
                                    border-radius: 8px; margin-bottom: 8px; background: rgba(255,255,255,0.03);">
                                    <div style="display: flex; align-items: center; gap: 8px; margin-bottom: 5px;">
                                        <span style="font-size: 11px; padding: 2px 8px; border-radius: 999px;
                                            background: ${getSeverityColor(issue.severity)}22;
                                            color: ${getSeverityColor(issue.severity)};">
                                            ${getSeverityLabel(issue.severity)}
                                        </span>
                                        <span style="font-size: 12px; color: var(--text-secondary, #888);">${escapeHtml(localizeIssueType(issue.type))}</span>
                                        <a href="javascript:void(0)" onclick="WikiModule.viewPage('${escapeJsString(issue.page || '')}')"
                                            style="color: #8ab4ff; text-decoration: none; font-size: 13px;">${escapeHtml(issue.page || '未知页面')}</a>
                                    </div>
                                    <div style="font-size: 13px;">${escapeHtml(issue.description || '')}</div>
                                    ${issue.suggestion ? `<div style="font-size: 12px; color: var(--text-secondary, #888); margin-top: 5px;">建议：${escapeHtml(issue.suggestion)}</div>` : ''}
                                </div>
                            `).join('')}
                        </div>
                    ` : '<div style="text-align: center; padding: 40px; color: #4ade80;">没有发现需要处理的问题</div>'}
                </div>
            `;
        } catch (e) {
            content.innerHTML = `<div style="color: #ef4444; padding: 20px;">检查失败: ${escapeHtml(e.message)}</div>`;
        }
    }

    function createPage() {
        const content = document.getElementById('wiki-content');
        if (!content) return;

        content.innerHTML = `
            <div style="max-width: 640px; padding: 20px;">
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

    async function editPage(title) {
        try {
            const resp = await fetch(`${WIKI_API}/pages/${encodeURIComponent(title)}`);
            const data = await resp.json();
            if (!data.success) throw new Error('获取失败');

            const page = data.data;
            const content = document.getElementById('wiki-content');

            content.innerHTML = `
                <div style="max-width: 800px; padding: 20px;">
                    <div class="app-back-row">
                        <button onclick="WikiModule.viewPage('${escapeJsString(title)}')" type="button" class="app-back-button">
                            <i class="ri-arrow-left-line"></i>
                            <span>取消编辑</span>
                        </button>
                    </div>

                    <h3>编辑: ${escapeHtml(title)}</h3>

                    <div style="margin-bottom: 12px;">
                        <label style="display: block; font-size: 12px; color: var(--text-secondary, #888); margin-bottom: 4px;">标签</label>
                        <input type="text" id="wiki-edit-tags" value="${escapeAttributeValue((page.tags || []).join(', '))}"
                            style="width: 100%; padding: 8px 12px; border: 1px solid var(--border-color, #333);
                            border-radius: 6px; background: var(--bg-tertiary, #222); color: var(--text-primary, #fff);">
                    </div>

                    <div style="margin-bottom: 16px;">
                        <label style="display: block; font-size: 12px; color: var(--text-secondary, #888); margin-bottom: 4px;">内容</label>
                        <textarea id="wiki-edit-body" rows="15"
                            style="width: 100%; padding: 8px 12px; border: 1px solid var(--border-color, #333);
                            border-radius: 6px; background: var(--bg-tertiary, #222); color: var(--text-primary, #fff);
                            font-family: monospace; resize: vertical;">${escapeHtml(page.body || '')}</textarea>
                    </div>

                    <button onclick="WikiModule.submitEdit('${escapeJsString(title)}')" class="btn btn-primary"
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

    function getVisiblePages(pages) {
        const source = Array.isArray(pages) ? pages : [];
        if (wikiState.showSystemPages) return source;
        return source.filter(page => !SYSTEM_PAGE_TYPES.has(page.page_type));
    }

    function getPageTypeLabel(type) {
        return TYPE_LABELS[type] || type || '页面';
    }

    function getPageTypeIcon(type) {
        return TYPE_ICONS[type] || 'ri-draft-line';
    }

    function localizeTag(tag) {
        return getPageTypeLabel(tag) !== tag ? getPageTypeLabel(tag) : String(tag || '');
    }

    function cleanWikiBodyForReading(page) {
        const title = normalizeText(page?.title || '');
        const body = String(page?.body || '').replace(/\r\n/g, '\n');
        const lines = body.split('\n');
        const result = [];
        let skipping = false;
        let skipLevel = 0;

        for (const line of lines) {
            const heading = line.match(/^(#{1,6})\s+(.+?)\s*$/);
            if (heading) {
                const level = heading[1].length;
                const rawLabel = stripMarkdown(heading[2]).trim();
                const key = normalizeKey(rawLabel);
                const isDuplicateTitle = level === 1 && normalizeText(rawLabel) === title;
                const shouldHide = HIDDEN_BODY_HEADINGS.has(key) || isDuplicateTitle;

                if (shouldHide) {
                    skipping = true;
                    skipLevel = level;
                    continue;
                }
                if (skipping && level <= skipLevel) {
                    skipping = false;
                }
                if (!skipping) {
                    result.push(`${heading[1]} ${BODY_HEADING_LABELS[key] || rawLabel}`);
                }
                continue;
            }

            if (skipping) continue;
            result.push(line);
        }

        return result.join('\n').replace(/\n{3,}/g, '\n\n').trim();
    }

    function markdownToHtml(markdown) {
        const lines = String(markdown || '').split('\n');
        const html = [];
        let inList = false;

        function closeList() {
            if (inList) {
                html.push('</ul>');
                inList = false;
            }
        }

        for (const line of lines) {
            const trimmed = line.trim();
            if (!trimmed) {
                closeList();
                html.push('<div style="height: 10px;"></div>');
                continue;
            }
            const heading = trimmed.match(/^(#{1,6})\s+(.+)$/);
            if (heading) {
                closeList();
                const level = Math.min(3, heading[1].length + 1);
                const marginTop = heading[1].length === 1 ? 4 : 18;
                html.push(`<h${level} style="margin: ${marginTop}px 0 8px; line-height: 1.35;">${renderInlineMarkdown(heading[2])}</h${level}>`);
                continue;
            }
            const bullet = trimmed.match(/^[-*]\s+(.+)$/);
            if (bullet) {
                if (!inList) {
                    html.push('<ul style="margin: 8px 0 12px 20px; padding: 0;">');
                    inList = true;
                }
                html.push(`<li style="margin: 4px 0;">${renderInlineMarkdown(bullet[1])}</li>`);
                continue;
            }
            closeList();
            html.push(`<p style="margin: 8px 0;">${renderInlineMarkdown(trimmed)}</p>`);
        }
        closeList();
        return html.join('');
    }

    function renderInlineMarkdown(text) {
        return escapeHtml(text)
            .replace(/\[\[([^\]]+)\]\]/g, (_, title) => {
                const cleanTitle = title.trim();
                return `<a href="javascript:void(0)" onclick="WikiModule.viewPage('${escapeJsString(cleanTitle)}')" style="color: #8ab4ff; text-decoration: none; border-bottom: 1px solid rgba(138,180,255,0.5);">${escapeHtml(cleanTitle)}</a>`;
            })
            .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
    }

    function getGraphFilteredNodes(nodes) {
        const source = Array.isArray(nodes) ? nodes : [];
        let filtered = wikiState.activeGraphType === 'all'
            ? source
            : source.filter(node => getGraphCategory(node) === wikiState.activeGraphType);
        const scope = wikiState.graphScope || 'all';
        if (scope === 'linked') {
            filtered = filtered.filter(node => Number(node.degree || 0) > 0);
        } else if (scope === 'isolated') {
            filtered = filtered.filter(node => Number(node.degree || 0) === 0);
        }
        return filtered.slice(0, 80);
    }

    function buildGraphLayout(nodes, edges) {
        const layout = new Map();
        if (!nodes.length) return layout;
        const center = nodes.reduce((best, node) => Number(node.degree || 0) > Number(best.degree || 0) ? node : best, nodes[0]);
        layout.set(center.id, { x: 50, y: 52 });

        const rest = nodes.filter(node => node.id !== center.id);
        const relatedIds = new Set();
        edges.forEach(edge => {
            if (edge.source === center.id) relatedIds.add(edge.target);
            if (edge.target === center.id) relatedIds.add(edge.source);
        });
        rest.sort((a, b) => {
            const ar = relatedIds.has(a.id) ? 0 : 1;
            const br = relatedIds.has(b.id) ? 0 : 1;
            if (ar !== br) return ar - br;
            return Number(b.degree || 0) - Number(a.degree || 0);
        });

        rest.forEach((node, index) => {
            const ring = index < 18 ? 1 : 2;
            const ringIndex = ring === 1 ? index : index - 18;
            const ringCount = ring === 1 ? Math.min(18, rest.length) : Math.max(1, rest.length - 18);
            const angle = (-Math.PI / 2) + (2 * Math.PI * ringIndex / ringCount);
            const radiusX = ring === 1 ? 31 : 42;
            const radiusY = ring === 1 ? 29 : 39;
            layout.set(node.id, {
                x: Math.max(8, Math.min(92, 50 + Math.cos(angle) * radiusX)),
                y: Math.max(10, Math.min(90, 52 + Math.sin(angle) * radiusY)),
            });
        });
        return layout;
    }

    function getGraphCategory(node) {
        const type = String(node?.type || '').toLowerCase();
        const haystack = `${node?.label || ''} ${(node?.tags || []).join(' ')}`.toLowerCase();
        if (type === 'character') return 'character';
        if (haystack.match(/地点|location|城|宫|山|谷|地|门|宗$/)) return 'location';
        if (haystack.match(/物件|物品|道具|item|法宝|令|剑|灯|药|信物/)) return 'item';
        if (haystack.match(/势力|阵营|faction|宗门|王朝|家族/)) return 'faction';
        if (haystack.match(/功法|技能|能力|power|术|诀|法$/)) return 'power';
        if (type === 'plot' || type === 'chapter' || haystack.match(/事件|章节|chapter|夜|章$/)) return 'event';
        return 'clue';
    }

    function getRelationLabel(edge) {
        const signals = edge?.signals || {};
        const firstKey = Object.keys(signals)[0];
        return RELATION_LABELS[firstKey] || RELATION_LABELS[edge?.type] || '相关';
    }

    function getSeverityColor(severity) {
        const value = String(severity || '').toLowerCase();
        if (value === 'critical') return '#ef4444';
        if (value === 'high') return '#f59e0b';
        if (value === 'medium') return '#60a5fa';
        return '#94a3b8';
    }

    function getSeverityLabel(severity) {
        const labels = { critical: '严重', high: '较高', medium: '中等', low: '提示' };
        return labels[String(severity || '').toLowerCase()] || '提示';
    }

    function localizeIssueType(type) {
        const labels = {
            dead_link: '死链接',
            isolated_page: '孤立页面',
            missing_frontmatter: '缺少元数据',
            duplicate_title: '标题重复',
            empty_page: '空页面',
        };
        return labels[String(type || '')] || type || '问题';
    }

    function normalizeKey(value) {
        return String(value || '').trim().toLowerCase().replace(/[\s-]+/g, '_');
    }

    function normalizeText(value) {
        return String(value || '').replace(/\s+/g, '').toLowerCase();
    }

    function stripMarkdown(value) {
        return String(value || '').replace(/[*`#]/g, '');
    }

    function formatDate(value) {
        const text = String(value || '').trim();
        if (!text) return '';
        return text.replace('T', ' ').slice(0, 16);
    }

    function escapeHtml(value) {
        return String(value ?? '')
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#39;');
    }

    function escapeAttributeValue(value) {
        return escapeHtml(value);
    }

    function escapeJsString(value) {
        return String(value ?? '')
            .replace(/\\/g, '\\\\')
            .replace(/'/g, "\\'")
            .replace(/\n/g, '\\n')
            .replace(/\r/g, '');
    }

    window.WikiModule = {
        init: initWikiModule,
        render: renderWikiView,
        loadPages,
        search,
        filterType,
        toggleSystemPages,
        viewPage,
        showGraph,
        setGraphScope,
        filterGraphType,
        selectGraphNode,
        openGraphNodeMenu,
        addGraphNodeToWorldbook,
        showLint,
        createPage,
        submitCreate,
        editPage,
        submitEdit,
        deletePage,
        __test: {
            cleanWikiBodyForReading,
            getPageTypeLabel,
            getGraphCategory,
        },
    };

    console.log('[app-wiki.js] Wiki知识系统模块已加载');
})();
