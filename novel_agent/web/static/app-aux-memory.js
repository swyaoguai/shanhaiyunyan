/**
 * 长期记忆中心（稳定版）
 */

function getAppCore() {
    return (window.NovelAgentApp && window.NovelAgentApp.core) || {};
}

function getCoreUi() {
    return getAppCore().ui || window.ui || {};
}

function getCoreSwitchModule() {
    return getAppCore().switchModule || window.switchModule || function () {};
}

const AUX_TYPES = [
    { value: 'preference', label: '偏好' },
    { value: 'fact', label: '事实' },
    { value: 'constraint', label: '约束' },
    { value: 'style', label: '风格' },
    { value: 'plot', label: '情节' },
    { value: 'other', label: '其他' }
];

const AUX_LIMITS = [100, 200, 500, 1000, 2000];

const auxMemoryState = {
    subView: 'memory',  // 'memory' | 'workbench'
    categories: [],
    items: [],
    totalItems: 0,
    currentCategoryId: '',
    selectedItemId: '',
    selectedItemIds: [],
    searchQuery: '',
    enabledOnly: false,
    typeFilter: '',
    itemLimit: 200,
    viewMode: 'tree',
    graphScope: 'current',
    graphViewport: { scale: 1, offsetX: 0, offsetY: 0 },
    graphDrag: { active: false, nodeId: '', startX: 0, startY: 0, startOffsetX: 0, startOffsetY: 0 },
    graphPan: { active: false, startX: 0, startY: 0, startOffsetX: 0, startOffsetY: 0 }
};

function auxCurrentItem() {
    return auxMemoryState.items.find((i) => i.id === auxMemoryState.selectedItemId) || null;
}

function auxCategoryName(categoryId) {
    if (!categoryId) return '未分类';
    const cat = auxMemoryState.categories.find((c) => c.id === categoryId);
    return cat?.name || '未知分类';
}

function auxTypeLabel(memoryType) {
    const row = AUX_TYPES.find((x) => x.value === String(memoryType || ''));
    return row?.label || String(memoryType || 'other');
}

function auxClampedInt(value, min, max, fallback) {
    const parsed = Number.parseInt(value, 10);
    const safe = Number.isFinite(parsed) ? parsed : fallback;
    return Math.max(min, Math.min(max, safe));
}

function auxSelectedSet() {
    return new Set((auxMemoryState.selectedItemIds || []).map((x) => String(x || '')).filter(Boolean));
}

function auxVisibleIds() {
    return auxMemoryState.items.map((x) => String(x.id || '')).filter(Boolean);
}

function auxNodeColor(item) {
    if (!item) return '#64748b';
    const enabledColor = item.enabled ? '#22c55e' : '#f59e0b';
    const typeColors = {
        preference: '#8b5cf6',
        fact: '#06b6d4',
        constraint: '#ef4444',
        style: '#ec4899',
        plot: '#f97316',
        other: '#64748b'
    };
    return typeColors[String(item.memory_type || 'other')] || enabledColor;
}

function auxGraphItems() {
    const nodes = auxMemoryState.items.slice(0, 24);
    if (auxMemoryState.graphScope === 'global') return nodes;
    if (!auxMemoryState.currentCategoryId) return nodes;
    return nodes.filter((item) => String(item.category_id || '') === String(auxMemoryState.currentCategoryId));
}

function auxGraphLinks(items) {
    const links = [];
    const byCategory = new Map();
    const byType = new Map();
    items.forEach((item) => {
        const cat = String(item.category_id || '');
        const type = String(item.memory_type || 'other');
        if (cat) {
            if (!byCategory.has(cat)) byCategory.set(cat, []);
            byCategory.get(cat).push(item);
        }
        if (!byType.has(type)) byType.set(type, []);
        byType.get(type).push(item);
    });
    byCategory.forEach((rows) => {
        if (rows.length < 2) return;
        for (let i = 1; i < rows.length; i += 1) {
            links.push({ from: rows[i - 1], to: rows[i], kind: 'category' });
        }
    });
    byType.forEach((rows) => {
        if (rows.length < 2) return;
        for (let i = 1; i < rows.length; i += 1) {
            links.push({ from: rows[i - 1], to: rows[i], kind: 'type' });
        }
    });
    return links.slice(0, 32);
}

function auxGraphNodeLayout(items) {
    const radius = 34;
    return items.map((item, index) => {
        const angle = (index / Math.max(1, items.length)) * Math.PI * 2;
        return {
            item,
            x: 50 + Math.cos(angle) * radius,
            y: 50 + Math.sin(angle) * radius,
            angle,
            radius
        };
    });
}

function auxSyncSelection() {
    const visible = new Set(auxVisibleIds());
    auxMemoryState.selectedItemIds = Array.from(auxSelectedSet()).filter((id) => visible.has(id));
    if (auxMemoryState.selectedItemId && !visible.has(String(auxMemoryState.selectedItemId))) {
        auxMemoryState.selectedItemId = '';
    }
}

function auxTypeOptions(selected, includeAll = false) {
    const opts = includeAll ? [{ value: '', label: '全部类型' }, ...AUX_TYPES] : AUX_TYPES;
    const value = String(selected || '');
    return opts
        .map((o) => `<option value="${escapeHtml(o.value)}" ${o.value === value ? 'selected' : ''}>${escapeHtml(o.label)}</option>`)
        .join('');
}

function auxCategoryOptions(selected, withEmpty = true, emptyLabel = '不指定分类') {
    const value = String(selected || '');
    const rows = [];
    if (withEmpty) rows.push(`<option value="" ${value ? '' : 'selected'}>${escapeHtml(emptyLabel)}</option>`);
    auxMemoryState.categories.forEach((c) => {
        rows.push(`<option value="${escapeHtml(c.id)}" ${c.id === value ? 'selected' : ''}>${escapeHtml(c.name || '未命名分类')}</option>`);
    });
    return rows.join('');
}

async function auxLoadCategories() {
    const res = await apiCall('/api/aux-memory/categories', 'GET');
    auxMemoryState.categories = Array.isArray(res.categories) ? res.categories : [];
}

async function auxLoadItems() {
    const q = new URLSearchParams();
    if (auxMemoryState.currentCategoryId) q.set('category_id', auxMemoryState.currentCategoryId);
    if (auxMemoryState.searchQuery.trim()) q.set('query', auxMemoryState.searchQuery.trim());
    if (auxMemoryState.enabledOnly) q.set('enabled_only', 'true');
    if (auxMemoryState.typeFilter) q.set('memory_type', auxMemoryState.typeFilter);
    q.set('limit', String(auxClampedInt(auxMemoryState.itemLimit, 20, 2000, 200)));
    q.set('offset', '0');
    const res = await apiCall(`/api/aux-memory/items?${q.toString()}`, 'GET');
    auxMemoryState.items = Array.isArray(res.items) ? res.items : [];
    auxMemoryState.totalItems = Number(res.total || auxMemoryState.items.length || 0);
    if (!auxMemoryState.selectedItemId && auxMemoryState.items.length > 0) {
        auxMemoryState.selectedItemId = auxMemoryState.items[0].id || '';
    }
    auxSyncSelection();
}

async function refreshAuxMemoryData() {
    await Promise.all([auxLoadCategories(), auxLoadItems()]);
}

function renderAuxMemoryNavPanel() {
    const ui = getCoreUi();
    if (!ui.navList) return;
    ui.navList.innerHTML = '';

    const isMemory = auxMemoryState.subView !== 'workbench';
    const isWorkbench = auxMemoryState.subView === 'workbench';

    // === 子视图切换 tabs ===
    const tabBar = document.createElement('div');
    tabBar.style.cssText = 'display:flex;gap:4px;margin-bottom:12px;padding:4px;background:rgba(255,255,255,0.03);border-radius:10px;border:1px solid var(--border-color);';
    const tabStyle = (active) => `flex:1;padding:8px 0;border:none;border-radius:8px;cursor:pointer;font-size:13px;font-weight:500;text-align:center;transition:all 0.2s;${
        active
            ? 'background:var(--accent-color);color:#fff;box-shadow:0 2px 8px rgba(99,102,241,0.25);'
            : 'background:transparent;color:var(--text-secondary);'
    }`;

    const memoryTab = document.createElement('button');
    memoryTab.type = 'button';
    memoryTab.style.cssText = tabStyle(isMemory);
    memoryTab.innerHTML = '<i class="ri-brain-line" style="margin-right:4px;"></i>长期记忆';
    memoryTab.addEventListener('click', () => auxSwitchToMemory());

    const workbenchTab = document.createElement('button');
    workbenchTab.type = 'button';
    workbenchTab.style.cssText = tabStyle(isWorkbench);
    workbenchTab.innerHTML = '<i class="ri-node-tree" style="margin-right:4px;"></i>知识工作台';
    workbenchTab.addEventListener('click', () => auxSwitchToWorkbench());

    tabBar.appendChild(memoryTab);
    tabBar.appendChild(workbenchTab);
    ui.navList.appendChild(tabBar);

    if (isWorkbench) {
        // 知识工作台子视图 - 不渲染记忆分类，直接显示提示
        const hint = document.createElement('div');
        hint.style.cssText = 'padding:12px;color:var(--text-secondary);font-size:12px;line-height:1.6;';
        hint.textContent = '在工作区搜索并浏览知识图谱节点，查看节点关系和相似内容。';
        ui.navList.appendChild(hint);
        return;
    }

    // === 长期记忆子视图 ===
    const allRow = document.createElement('div');
    allRow.className = `list-item ${auxMemoryState.currentCategoryId ? '' : 'active'}`;
    allRow.dataset.auxCat = '';
    allRow.innerHTML = `<i class="ri-brain-line"></i><span>全部记忆</span><span style="margin-left:auto;opacity:.65;font-size:11px;">(${auxMemoryState.totalItems || auxMemoryState.items.length})</span>`;
    window.makeElementActivatable(allRow, () => {
        allRow.click();
    }, { bindClick: false });
    ui.navList.appendChild(allRow);

    auxMemoryState.categories.forEach((c) => {
        const row = document.createElement('div');
        row.className = `list-item ${auxMemoryState.currentCategoryId === c.id ? 'active' : ''}`;
        row.dataset.auxCat = c.id;
        row.style.cssText = 'display:flex;align-items:center;gap:6px;';
        row.innerHTML = `<i class="ri-folder-3-line"></i><span style="flex:1;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">${escapeHtml(c.name || '未命名分类')}</span><button data-aux-cat-toggle="${escapeHtml(c.id)}" style="border:none;background:transparent;cursor:pointer;color:${c.enabled ? '#22c55e' : 'var(--text-secondary)'};"><i class="${c.enabled ? 'ri-toggle-line' : 'ri-toggle-fill'}"></i></button><button data-aux-cat-del="${escapeHtml(c.id)}" style="border:none;background:transparent;cursor:pointer;color:#ef4444;"><i class="ri-delete-bin-line"></i></button>`;
        window.makeElementActivatable(row, () => {
            row.click();
        }, {
            allowWhen: (event) => !event.target.closest('[data-aux-cat-toggle], [data-aux-cat-del]'),
            bindClick: false
        });
        ui.navList.appendChild(row);
    });

    const add = document.createElement('div');
    add.id = 'aux-add-cat-nav';
    add.className = 'list-item';
    add.style.cssText = 'margin-top:12px;border:1px dashed var(--border-color);border-radius:8px;color:var(--accent-color);';
    add.innerHTML = '<i class="ri-add-line"></i><span>新建分类</span>';
    window.makeElementActivatable(add, () => {
        add.click();
    }, { bindClick: false });
    ui.navList.appendChild(add);
}

// === 子视图切换函数 ===
function auxSwitchToWorkbench() {
    auxMemoryState.subView = 'workbench';
    renderAuxMemoryNavPanel();
    const coreUi = getCoreUi();
    if (coreUi.workspace && typeof renderKnowledgeWorkbench === 'function') {
        renderKnowledgeWorkbench();
    }
    if (typeof updateBreadcrumbs === 'function') {
        updateBreadcrumbs(['知识中心', '知识工作台']);
    }
}

function auxSwitchToMemory() {
    auxMemoryState.subView = 'memory';
    renderAuxMemoryNavPanel();
    initAuxMemoryCenter();
}

function auxUpdateSelectionUi() {
    auxSyncSelection();
    const text = document.getElementById('aux-selected-count-text');
    if (text) text.textContent = `已选 ${auxMemoryState.selectedItemIds.length} 条`;
    const allBox = document.getElementById('aux-select-all-visible');
    if (allBox) {
        const visible = auxMemoryState.items.length;
        const selected = auxMemoryState.selectedItemIds.length;
        allBox.checked = visible > 0 && selected === visible;
        allBox.indeterminate = selected > 0 && selected < visible;
    }
}

const AUX_PANEL_STYLE = 'border:1px solid var(--border-color);border-radius:12px;padding:12px;background:rgba(255,255,255,.02);';
const AUX_FIELD_STYLE = 'width:100%;background:rgba(0,0,0,.25);border:1px solid var(--border-color);padding:8px;border-radius:8px;color:var(--text-primary);';
const AUX_SELECT_STYLE = 'background:rgba(0,0,0,.25);border:1px solid var(--border-color);padding:8px;border-radius:8px;color:var(--text-primary);';
const AUX_GHOST_BUTTON_STYLE = 'padding:6px 10px;border:1px solid var(--border-color);border-radius:8px;background:transparent;color:var(--text-primary);cursor:pointer;';
const AUX_PRIMARY_BUTTON_STYLE = 'padding:8px 10px;border:none;border-radius:8px;background:var(--accent-color);color:#fff;cursor:pointer;';
const AUX_SUCCESS_BUTTON_STYLE = 'padding:8px;border:none;border-radius:8px;background:#22c55e;color:#fff;cursor:pointer;';
const AUX_WARNING_BUTTON_STYLE = 'padding:8px;border:none;border-radius:8px;background:#f59e0b;color:#fff;cursor:pointer;';
const AUX_DANGER_BUTTON_STYLE = 'padding:8px;border:none;border-radius:8px;background:#ef4444;color:#fff;cursor:pointer;';

function auxRenderItemRow(item, selectedSet) {
    const id = String(item.id || '');
    const active = auxMemoryState.selectedItemId === item.id;
    const checked = selectedSet.has(id);
    return `<div data-aux-item="${escapeHtml(id)}" style="padding:10px;border:1px solid var(--border-color);border-radius:10px;margin-bottom:8px;background:${active ? 'rgba(59,130,246,.16)' : 'rgba(255,255,255,.02)'};cursor:pointer;">
        <div style="display:flex;gap:8px;align-items:center;">
            <input type="checkbox" data-aux-item-check="${escapeHtml(id)}" ${checked ? 'checked' : ''} title="勾选后可批量操作">
            <span style="flex:1;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;color:var(--text-primary);font-size:13px;">${escapeHtml(item.summary || '（无摘要）')}</span>
            <span style="font-size:11px;color:${item.enabled ? '#22c55e' : '#f59e0b'};">${item.enabled ? '启用' : '停用'}</span>
        </div>
        <div style="display:flex;justify-content:space-between;font-size:11px;color:var(--text-secondary);margin-top:6px;">
            <span>${escapeHtml(auxCategoryName(item.category_id))} / ${escapeHtml(auxTypeLabel(item.memory_type))}</span>
            <span>score ${Number(item.score ?? 0.5).toFixed(2)}</span>
        </div>
    </div>`;
}

function auxRenderDetailPanel(selected) {
    if (!selected) {
        return '<div style="color:var(--text-secondary);font-size:13px;">请先在左侧选择一个条目。</div>';
    }
    return `<input id="aux-edit-summary" value="${escapeHtml(selected.summary || '')}" placeholder="摘要" style="${AUX_FIELD_STYLE}margin-bottom:8px;">
        <textarea id="aux-edit-details" rows="4" placeholder="详情" style="${AUX_FIELD_STYLE}resize:vertical;margin-bottom:8px;">${escapeHtml(selected.details || '')}</textarea>
        <div style="display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:8px;margin-bottom:8px;">
            <select id="aux-edit-category" style="${AUX_SELECT_STYLE}">${auxCategoryOptions(selected.category_id || '', true, '未分类')}</select>
            <select id="aux-edit-type" style="${AUX_SELECT_STYLE}">${auxTypeOptions(selected.memory_type || 'preference')}</select>
            <input id="aux-edit-score" type="number" min="0" max="1" step="0.01" value="${Number(selected.score ?? 0.5).toFixed(2)}" style="${AUX_SELECT_STYLE}">
        </div>
        <input id="aux-edit-tags" value="${escapeHtml((selected.tags || []).join(', '))}" placeholder="标签，逗号分隔" style="${AUX_FIELD_STYLE}margin-bottom:8px;">
        <label style="display:flex;align-items:center;gap:8px;color:var(--text-primary);font-size:13px;margin-bottom:8px;"><input id="aux-edit-enabled" type="checkbox" ${selected.enabled ? 'checked' : ''}>启用条目</label>
        <div style="display:flex;gap:8px;"><button id="aux-save-item" style="flex:1;${AUX_PRIMARY_BUTTON_STYLE}">保存条目</button><button id="aux-del-item" style="padding:8px 12px;${AUX_DANGER_BUTTON_STYLE}">删除条目</button></div>`;
}

function auxRenderCreatePanel() {
    return `
        <div style="border-top:1px solid var(--border-color);padding-top:12px;">
            <h4 style="margin:0 0 8px 0;color:var(--text-primary);">新增记忆条目</h4>
            <input id="aux-new-summary" placeholder="摘要（必填）" style="${AUX_FIELD_STYLE}margin-bottom:8px;">
            <textarea id="aux-new-details" rows="3" placeholder="详情（可选）" style="${AUX_FIELD_STYLE}resize:vertical;margin-bottom:8px;"></textarea>
            <div style="display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:8px;margin-bottom:8px;">
                <select id="aux-new-category" style="${AUX_SELECT_STYLE}">${auxCategoryOptions(auxMemoryState.currentCategoryId || '', true, '不指定分类')}</select>
                <select id="aux-new-type" style="${AUX_SELECT_STYLE}">${auxTypeOptions('preference')}</select>
                <input id="aux-new-score" type="number" min="0" max="1" step="0.01" value="0.60" style="${AUX_SELECT_STYLE}">
            </div>
            <input id="aux-new-tags" placeholder="标签，逗号分隔" style="${AUX_FIELD_STYLE}margin-bottom:8px;">
            <label style="display:flex;align-items:center;gap:8px;color:var(--text-primary);font-size:13px;margin-bottom:8px;"><input id="aux-new-enabled" type="checkbox" checked>创建后立即启用</label>
            <button id="aux-create-item" style="width:100%;${AUX_SUCCESS_BUTTON_STYLE}">新增条目</button>
        </div>
        <div style="border-top:1px solid var(--border-color);padding-top:12px;">
            <h4 style="margin:0 0 8px 0;color:var(--text-primary);">分类管理</h4>
            <input id="aux-new-cat-name" placeholder="分类名称（必填）" style="${AUX_FIELD_STYLE}margin-bottom:8px;">
            <button id="aux-create-cat" style="width:100%;${AUX_SUCCESS_BUTTON_STYLE}margin-bottom:8px;">创建分类</button>
            <button id="aux-toggle-cur-cat" style="width:100%;${AUX_WARNING_BUTTON_STYLE}margin-bottom:8px;">切换当前分类启停</button>
            <button id="aux-del-cur-cat" style="width:100%;${AUX_DANGER_BUTTON_STYLE}">删除当前分类</button>
        </div>`;
}

function auxRenderTreeMode(rowsHtml, detailHtml) {
    return `<div style="height:100%;display:grid;grid-template-columns:minmax(440px,1.2fr) minmax(360px,1fr);gap:12px;">
        <section style="display:grid;grid-template-rows:auto auto auto 1fr;gap:8px;min-height:0;${AUX_PANEL_STYLE}">
            <div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap;">
                <input id="aux-search" value="${escapeHtml(auxMemoryState.searchQuery)}" placeholder="搜索摘要/详情/标签" style="flex:1;min-width:220px;${AUX_FIELD_STYLE}">
                <button id="aux-search-btn" style="${AUX_PRIMARY_BUTTON_STYLE}"><i class="ri-search-line"></i></button>
                <button id="aux-search-clear" style="${AUX_GHOST_BUTTON_STYLE}">清空</button>
                <button id="aux-view-tree" style="padding:6px 10px;border:1px solid var(--accent-color);border-radius:8px;background:rgba(59,130,246,.16);color:var(--text-primary);cursor:pointer;">树状图</button>
                <button id="aux-view-graph" style="padding:6px 10px;border:1px solid var(--border-color);border-radius:8px;background:transparent;color:var(--text-primary);cursor:pointer;">图谱</button>
            </div>
            <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;">
                <label style="display:flex;align-items:center;gap:8px;color:var(--text-primary);font-size:13px;"><input id="aux-only-enabled" type="checkbox" ${auxMemoryState.enabledOnly ? 'checked' : ''}>仅启用条目</label>
                <select id="aux-filter-type" style="${AUX_SELECT_STYLE}">${auxTypeOptions(auxMemoryState.typeFilter, true)}</select>
            </div>
            <div style="display:grid;gap:8px;color:var(--text-secondary);font-size:12px;">
                <div style="display:flex;justify-content:space-between;flex-wrap:wrap;gap:8px;">
                    <span>当前显示 ${auxMemoryState.items.length} 条 / 总计 ${auxMemoryState.totalItems || auxMemoryState.items.length} 条</span>
                    <div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap;">
                        <label style="display:flex;align-items:center;gap:6px;color:var(--text-primary);"><input id="aux-select-all-visible" type="checkbox">全选当前列表</label>
                        <button id="aux-clear-selection" style="${AUX_GHOST_BUTTON_STYLE}">清空选择</button>
                    </div>
                </div>
                <div style="display:flex;justify-content:space-between;flex-wrap:wrap;gap:8px;">
                    <div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap;">
                        <span id="aux-selected-count-text">已选 ${auxMemoryState.selectedItemIds.length} 条</span>
                        <label style="display:flex;align-items:center;gap:6px;">加载上限<select id="aux-limit" style="background:rgba(0,0,0,.25);border:1px solid var(--border-color);padding:4px 8px;border-radius:8px;color:var(--text-primary);">${AUX_LIMITS.map((n) => `<option value="${n}" ${auxMemoryState.itemLimit === n ? 'selected' : ''}>${n}</option>`).join('')}</select></label>
                    </div>
                    <div style="display:flex;gap:8px;flex-wrap:wrap;">
                        <button id="aux-batch-enable" style="padding:6px 10px;border:none;border-radius:8px;background:#10b981;color:#fff;cursor:pointer;">批量启用选中</button>
                        <button id="aux-batch-disable" style="padding:6px 10px;border:none;border-radius:8px;background:#f59e0b;color:#fff;cursor:pointer;">批量停用选中</button>
                        <button id="aux-batch-delete" style="padding:6px 10px;border:none;border-radius:8px;background:#ef4444;color:#fff;cursor:pointer;">删除选中</button>
                        <button id="aux-clear-filtered" style="padding:6px 10px;border:none;border-radius:8px;background:#991b1b;color:#fff;cursor:pointer;">一键清空当前筛选</button>
                    </div>
                </div>
            </div>
            <div id="aux-item-list" class="scrollbar-custom" style="overflow:auto;min-height:0;">${rowsHtml || '<div style="padding:16px;color:var(--text-secondary);text-align:center;">暂无匹配条目</div>'}</div>
        </section>
        <section style="overflow:auto;${AUX_PANEL_STYLE}display:grid;gap:12px;align-content:start;">
            <div><h3 style="margin:0 0 8px 0;color:var(--text-primary);font-size:16px;">条目详情</h3>${detailHtml}</div>
            <div id="aux-create-area">${auxRenderCreatePanel()}</div>
        </section>
    </div>`;
}

function auxRenderGraphMode(detailHtml) {
    const nodes = auxGraphItems();
    const selected = auxCurrentItem();
    const center = selected || nodes[0] || null;
    const links = auxGraphLinks(nodes);
    const layout = auxGraphNodeLayout(nodes);
    const viewport = auxMemoryState.graphViewport || { scale: 1, offsetX: 0, offsetY: 0 };
    const itemsHtml = center ? layout.map(({ item, x, y }) => {
        const active = center && item.id === center.id;
        const color = auxNodeColor(item);
        return `<button data-aux-item="${escapeHtml(String(item.id || ''))}" title="${escapeHtml(item.summary || '')}" data-graph-node="${escapeHtml(String(item.id || ''))}" style="position:absolute;left:${x}%;top:${y}%;transform:translate(-50%,-50%);width:104px;min-height:46px;padding:8px;border-radius:14px;border:1px solid ${active ? 'var(--accent-color)' : color};background:${active ? 'rgba(59,130,246,.22)' : `${color}22`};color:var(--text-primary);cursor:pointer;font-size:12px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;box-shadow:${active ? '0 0 0 3px rgba(59,130,246,.16)' : 'none'};user-select:none;touch-action:none;'>${escapeHtml(item.summary || '未命名')}</button>`;
    }).join('') : '<div style="position:absolute;inset:0;display:flex;align-items:center;justify-content:center;color:var(--text-secondary);">暂无匹配条目</div>';

    const linkHtml = links.map((link) => {
        const fromLayout = layout.find((x) => x.item.id === link.from.id);
        const toLayout = layout.find((x) => x.item.id === link.to.id);
        if (!fromLayout || !toLayout) return '';
        const color = link.kind === 'category' ? '#22c55e' : '#60a5fa';
        return `<line x1="${fromLayout.x}%" y1="${fromLayout.y}%" x2="${toLayout.x}%" y2="${toLayout.y}%" stroke="${color}" stroke-width="1.5" stroke-opacity="0.5"></line>`;
    }).join('');

    const scopeLabel = auxMemoryState.graphScope === 'global' ? '全局图谱' : '当前分类图谱';

    return `<div style="height:100%;display:grid;grid-template-columns:minmax(440px,1.2fr) minmax(360px,1fr);gap:12px;">
        <section style="display:grid;grid-template-rows:auto auto auto 1fr;gap:8px;min-height:0;${AUX_PANEL_STYLE}">
            <div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap;">
                <input id="aux-search" value="${escapeHtml(auxMemoryState.searchQuery)}" placeholder="搜索摘要/详情/标签" style="flex:1;min-width:220px;${AUX_FIELD_STYLE}">
                <button id="aux-search-btn" style="${AUX_PRIMARY_BUTTON_STYLE}"><i class="ri-search-line"></i></button>
                <button id="aux-search-clear" style="${AUX_GHOST_BUTTON_STYLE}">清空</button>
                <button id="aux-view-tree" style="padding:6px 10px;border:1px solid var(--border-color);border-radius:8px;background:transparent;color:var(--text-primary);cursor:pointer;">树状图</button>
                <button id="aux-view-graph" style="padding:6px 10px;border:1px solid var(--accent-color);border-radius:8px;background:rgba(59,130,246,.16);color:var(--text-primary);cursor:pointer;">图谱</button>
            </div>
            <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;">
                <label style="display:flex;align-items:center;gap:8px;color:var(--text-primary);font-size:13px;"><input id="aux-only-enabled" type="checkbox" ${auxMemoryState.enabledOnly ? 'checked' : ''}>仅启用条目</label>
                <select id="aux-filter-type" style="${AUX_SELECT_STYLE}">${auxTypeOptions(auxMemoryState.typeFilter, true)}</select>
            </div>
            <div style="display:grid;gap:8px;color:var(--text-secondary);font-size:12px;">
                <div style="display:flex;justify-content:space-between;flex-wrap:wrap;gap:8px;">
                    <span>当前显示 ${auxMemoryState.items.length} 条 / 总计 ${auxMemoryState.totalItems || auxMemoryState.items.length} 条</span>
                    <div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap;">
                        <span style="padding:4px 8px;border:1px solid var(--border-color);border-radius:999px;color:var(--text-primary);">${scopeLabel}</span>
                        <label style="display:flex;align-items:center;gap:6px;color:var(--text-primary);"><input id="aux-select-all-visible" type="checkbox">全选当前列表</label>
                        <button id="aux-clear-selection" style="${AUX_GHOST_BUTTON_STYLE}">清空选择</button>
                    </div>
                </div>
                <div style="display:flex;justify-content:space-between;flex-wrap:wrap;gap:8px;">
                    <div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap;">
                        <span id="aux-selected-count-text">已选 ${auxMemoryState.selectedItemIds.length} 条</span>
                        <label style="display:flex;align-items:center;gap:6px;">加载上限<select id="aux-limit" style="background:rgba(0,0,0,.25);border:1px solid var(--border-color);padding:4px 8px;border-radius:8px;color:var(--text-primary);">${AUX_LIMITS.map((n) => `<option value="${n}" ${auxMemoryState.itemLimit === n ? 'selected' : ''}>${n}</option>`).join('')}</select></label>
                        <button id="aux-graph-scope" style="padding:6px 10px;border:1px solid var(--border-color);border-radius:8px;background:transparent;color:var(--text-primary);cursor:pointer;">${auxMemoryState.graphScope === 'global' ? '全局图谱' : '当前分类图谱'}</button>
                    </div>
                    <div style="display:flex;gap:8px;flex-wrap:wrap;">
                        <button id="aux-batch-enable" style="padding:6px 10px;border:none;border-radius:8px;background:#10b981;color:#fff;cursor:pointer;">批量启用选中</button>
                        <button id="aux-batch-disable" style="padding:6px 10px;border:none;border-radius:8px;background:#f59e0b;color:#fff;cursor:pointer;">批量停用选中</button>
                        <button id="aux-batch-delete" style="padding:6px 10px;border:none;border-radius:8px;background:#ef4444;color:#fff;cursor:pointer;">删除选中</button>
                        <button id="aux-clear-filtered" style="padding:6px 10px;border:none;border-radius:8px;background:#991b1b;color:#fff;cursor:pointer;">一键清空当前筛选</button>
                    </div>
                </div>
            </div>
            <div id="aux-item-list" class="scrollbar-custom" style="overflow:auto;min-height:0;">${nodes.length ? nodes.map((item) => auxRenderItemRow(item, auxSelectedSet())).join('') : '<div style="padding:16px;color:var(--text-secondary);text-align:center;">暂无匹配条目</div>'}</div>
        </section>
        <section style="overflow:auto;${AUX_PANEL_STYLE}display:grid;gap:12px;align-content:start;">
            <div><h3 style="margin:0 0 8px 0;color:var(--text-primary);font-size:16px;">图谱预览</h3><div id="aux-graph-shell" style="position:relative;min-height:360px;border:1px solid var(--border-color);border-radius:16px;background:radial-gradient(circle at center, rgba(59,130,246,.14), rgba(255,255,255,.02) 58%, rgba(0,0,0,.08));overflow:hidden;cursor:grab;"><svg viewBox="0 0 100 100" preserveAspectRatio="none" style="position:absolute;inset:0;width:100%;height:100%;pointer-events:none;transform:translate(${viewport.offsetX}px, ${viewport.offsetY}px) scale(${viewport.scale});transform-origin:center;">${linkHtml}</svg><div style="position:absolute;left:50%;top:50%;transform:translate(-50%,-50%) scale(${viewport.scale});width:120px;height:56px;display:flex;align-items:center;justify-content:center;border-radius:18px;border:1px solid var(--accent-color);background:rgba(59,130,246,.22);color:var(--text-primary);font-weight:600;text-align:center;padding:0 10px;z-index:2;pointer-events:none;">${escapeHtml(center?.summary || center?.details || '中心节点')}</div><div id="aux-graph-nodes" style="position:absolute;inset:0;transform:translate(${viewport.offsetX}px, ${viewport.offsetY}px) scale(${viewport.scale});transform-origin:center;">${itemsHtml}</div></div></div>
            <div><h3 style="margin:0 0 8px 0;color:var(--text-primary);font-size:16px;">条目详情</h3>${detailHtml}</div>
            <div id="aux-create-area">${auxRenderCreatePanel()}</div>
        </section>
    </div>`;
}

function auxRenderCenter() {
    const ui = getCoreUi();
    if (!ui.workspace) return;
    const currentName = auxMemoryState.currentCategoryId ? auxCategoryName(auxMemoryState.currentCategoryId) : '全部记忆';
    updateBreadcrumbs(['知识中心', currentName]);

    const selected = auxCurrentItem();
    const selectedSet = auxSelectedSet();
    const rows = auxMemoryState.items.map((item) => auxRenderItemRow(item, selectedSet)).join('');
    const detailHtml = auxRenderDetailPanel(selected);

    ui.workspace.innerHTML = auxMemoryState.viewMode === 'graph'
        ? auxRenderGraphMode(detailHtml)
        : auxRenderTreeMode(rows, detailHtml);

    auxBindEvents();
    auxUpdateSelectionUi();
}

function auxParseTags(raw) {
    if (!raw) return [];
    return [...new Set(String(raw).split(/[，,\s]+/).map((x) => x.trim()).filter(Boolean))].slice(0, 20);
}

async function auxSelectCategory(categoryId) {
    auxMemoryState.currentCategoryId = String(categoryId || '');
    auxMemoryState.selectedItemId = '';
    auxMemoryState.selectedItemIds = [];
    await auxLoadItems();
    renderAuxMemoryNavPanel();
    auxRenderCenter();
}

function auxBindEvents() {
    document.querySelectorAll('[data-aux-cat]').forEach((row) => {
        row.addEventListener('click', async (event) => {
            if (event.target.closest('[data-aux-cat-toggle]') || event.target.closest('[data-aux-cat-del]')) return;
            await auxSelectCategory(row.dataset.auxCat || '');
        });
    });

    document.querySelectorAll('[data-aux-cat-toggle]').forEach((btn) => {
        btn.addEventListener('click', async (event) => {
            event.stopPropagation();
            await auxToggleCategory(btn.dataset.auxCatToggle || '');
        });
    });

    document.querySelectorAll('[data-aux-cat-del]').forEach((btn) => {
        btn.addEventListener('click', async (event) => {
            event.stopPropagation();
            await auxDeleteCategory(btn.dataset.auxCatDel || '');
        });
    });

    const navAdd = document.getElementById('aux-add-cat-nav');
    if (navAdd) navAdd.addEventListener('click', () => document.getElementById('aux-new-cat-name')?.focus());

    const searchBtn = document.getElementById('aux-search-btn');
    const searchInput = document.getElementById('aux-search');
    const searchClear = document.getElementById('aux-search-clear');
    if (searchBtn) searchBtn.addEventListener('click', auxApplyFilters);
    if (searchInput) searchInput.addEventListener('keydown', async (e) => { if (e.key === 'Enter') { e.preventDefault(); await auxApplyFilters(); } });
    if (searchClear) searchClear.addEventListener('click', async () => { auxMemoryState.searchQuery = ''; if (searchInput) searchInput.value = ''; await auxLoadItems(); auxRenderCenter(); });

    const onlyEnabled = document.getElementById('aux-only-enabled');
    if (onlyEnabled) onlyEnabled.addEventListener('change', async () => { auxMemoryState.enabledOnly = Boolean(onlyEnabled.checked); await auxLoadItems(); auxRenderCenter(); });
    const filterType = document.getElementById('aux-filter-type');
    if (filterType) filterType.addEventListener('change', async () => { auxMemoryState.typeFilter = String(filterType.value || ''); await auxLoadItems(); auxRenderCenter(); });

    const treeBtn = document.getElementById('aux-view-tree');
    if (treeBtn) treeBtn.addEventListener('click', () => {
        auxMemoryState.viewMode = 'tree';
        auxRenderCenter();
    });
    const graphBtn = document.getElementById('aux-view-graph');
    if (graphBtn) graphBtn.addEventListener('click', () => {
        auxMemoryState.viewMode = 'graph';
        auxRenderCenter();
    });

    const graphScopeBtn = document.getElementById('aux-graph-scope');
    if (graphScopeBtn) graphScopeBtn.addEventListener('click', () => {
        auxMemoryState.graphScope = auxMemoryState.graphScope === 'global' ? 'current' : 'global';
        auxRenderCenter();
    });

    const graphShell = document.getElementById('aux-graph-shell');
    if (graphShell) {
        let movedNodeId = '';
        let nodeMap = new Map();
        const syncMap = () => {
            nodeMap = new Map();
            document.querySelectorAll('[data-graph-node]').forEach((node) => nodeMap.set(node.dataset.graphNode, node));
        };
        syncMap();

        graphShell.addEventListener('wheel', (event) => {
            if (auxMemoryState.viewMode !== 'graph') return;
            event.preventDefault();
            const delta = event.deltaY < 0 ? 0.1 : -0.1;
            auxMemoryState.graphViewport.scale = Math.max(0.5, Math.min(2.2, Number((auxMemoryState.graphViewport.scale + delta).toFixed(2))));
            auxRenderCenter();
        }, { passive: false });

        graphShell.addEventListener('mousedown', (event) => {
            if (auxMemoryState.viewMode !== 'graph') return;
            const node = event.target.closest('[data-graph-node]');
            if (node) {
                movedNodeId = node.dataset.graphNode || '';
                auxMemoryState.graphDrag = {
                    active: true,
                    nodeId: movedNodeId,
                    startX: event.clientX,
                    startY: event.clientY,
                    startOffsetX: auxMemoryState.graphViewport.offsetX,
                    startOffsetY: auxMemoryState.graphViewport.offsetY
                };
                graphShell.style.cursor = 'grabbing';
                return;
            }
            auxMemoryState.graphPan = {
                active: true,
                startX: event.clientX,
                startY: event.clientY,
                startOffsetX: auxMemoryState.graphViewport.offsetX,
                startOffsetY: auxMemoryState.graphViewport.offsetY
            };
            graphShell.style.cursor = 'grabbing';
        });

        window.addEventListener('mousemove', (event) => {
            if (auxMemoryState.viewMode !== 'graph') return;
            if (auxMemoryState.graphDrag.active) {
                const dx = event.clientX - auxMemoryState.graphDrag.startX;
                const dy = event.clientY - auxMemoryState.graphDrag.startY;
                auxMemoryState.graphViewport.offsetX = auxMemoryState.graphDrag.startOffsetX + dx;
                auxMemoryState.graphViewport.offsetY = auxMemoryState.graphDrag.startOffsetY + dy;
                auxRenderCenter();
                return;
            }
            if (auxMemoryState.graphPan.active) {
                const dx = event.clientX - auxMemoryState.graphPan.startX;
                const dy = event.clientY - auxMemoryState.graphPan.startY;
                auxMemoryState.graphViewport.offsetX = auxMemoryState.graphPan.startOffsetX + dx;
                auxMemoryState.graphViewport.offsetY = auxMemoryState.graphPan.startOffsetY + dy;
                auxRenderCenter();
            }
        });

        window.addEventListener('mouseup', () => {
            if (auxMemoryState.graphDrag.active || auxMemoryState.graphPan.active) {
                auxMemoryState.graphDrag.active = false;
                auxMemoryState.graphDrag.nodeId = '';
                auxMemoryState.graphPan.active = false;
                graphShell.style.cursor = 'grab';
            }
        });

        graphShell.querySelectorAll('[data-graph-node]').forEach((node) => {
            node.addEventListener('dblclick', () => {
                const targetId = node.dataset.graphNode || '';
                const target = auxMemoryState.items.find((item) => String(item.id || '') === targetId);
                if (target) {
                    auxMemoryState.selectedItemId = target.id;
                    auxRenderCenter();
                }
            });
            node.addEventListener('click', () => {
                const targetId = node.dataset.graphNode || '';
                const target = auxMemoryState.items.find((item) => String(item.id || '') === targetId);
                if (target) {
                    auxMemoryState.selectedItemId = target.id;
                    auxRenderCenter();
                }
            });
        });

        graphShell.addEventListener('touchstart', (event) => {
            if (auxMemoryState.viewMode !== 'graph') return;
            const touch = event.touches[0];
            auxMemoryState.graphPan = {
                active: true,
                startX: touch.clientX,
                startY: touch.clientY,
                startOffsetX: auxMemoryState.graphViewport.offsetX,
                startOffsetY: auxMemoryState.graphViewport.offsetY
            };
        }, { passive: true });

        window.addEventListener('touchmove', (event) => {
            if (!auxMemoryState.graphPan.active || auxMemoryState.viewMode !== 'graph') return;
            const touch = event.touches[0];
            const dx = touch.clientX - auxMemoryState.graphPan.startX;
            const dy = touch.clientY - auxMemoryState.graphPan.startY;
            auxMemoryState.graphViewport.offsetX = auxMemoryState.graphPan.startOffsetX + dx;
            auxMemoryState.graphViewport.offsetY = auxMemoryState.graphPan.startOffsetY + dy;
            auxRenderCenter();
        }, { passive: true });

        window.addEventListener('touchend', () => {
            auxMemoryState.graphPan.active = false;
            if (graphShell) graphShell.style.cursor = 'grab';
        });
    }

    const list = document.getElementById('aux-item-list');
    if (list) {
        list.addEventListener('click', (event) => {
            if (event.target.closest('[data-aux-item-check]')) return;
            const row = event.target.closest('[data-aux-item]');
            if (!row) return;
            auxMemoryState.selectedItemId = row.dataset.auxItem || '';
            auxRenderCenter();
        });

        list.addEventListener('change', (event) => {
            const checkbox = event.target.closest('[data-aux-item-check]');
            if (!checkbox) return;
            const id = String(checkbox.dataset.auxItemCheck || '').trim();
            if (!id) return;
            const selected = auxSelectedSet();
            if (checkbox.checked) selected.add(id); else selected.delete(id);
            auxMemoryState.selectedItemIds = Array.from(selected);
            auxUpdateSelectionUi();
        });
    }

    const selectAll = document.getElementById('aux-select-all-visible');
    if (selectAll) selectAll.addEventListener('change', () => { auxMemoryState.selectedItemIds = selectAll.checked ? auxVisibleIds() : []; auxRenderCenter(); });
    const clearSelection = document.getElementById('aux-clear-selection');
    if (clearSelection) clearSelection.addEventListener('click', () => { auxMemoryState.selectedItemIds = []; auxRenderCenter(); });

    const limit = document.getElementById('aux-limit');
    if (limit) limit.addEventListener('change', async () => { auxMemoryState.itemLimit = auxClampedInt(limit.value, 20, 2000, 200); await auxLoadItems(); auxRenderCenter(); });

    const batchEnable = document.getElementById('aux-batch-enable');
    if (batchEnable) batchEnable.addEventListener('click', async () => { await auxBatchSetEnabled(true); });
    const batchDisable = document.getElementById('aux-batch-disable');
    if (batchDisable) batchDisable.addEventListener('click', async () => { await auxBatchSetEnabled(false); });
    const batchDelete = document.getElementById('aux-batch-delete');
    if (batchDelete) batchDelete.addEventListener('click', async () => { await auxBatchDelete(); });
    const clearFiltered = document.getElementById('aux-clear-filtered');
    if (clearFiltered) clearFiltered.addEventListener('click', async () => { await auxClearFiltered(); });

    const createItem = document.getElementById('aux-create-item');
    if (createItem) createItem.addEventListener('click', async () => { await auxCreateItem(); });
    const saveItem = document.getElementById('aux-save-item');
    if (saveItem) saveItem.addEventListener('click', async () => { await auxSaveItem(); });
    const delItem = document.getElementById('aux-del-item');
    if (delItem) delItem.addEventListener('click', async () => { await auxDeleteItem(); });

    const createCat = document.getElementById('aux-create-cat');
    if (createCat) createCat.addEventListener('click', async () => { await auxCreateCategory(); });
    const toggleCurCat = document.getElementById('aux-toggle-cur-cat');
    if (toggleCurCat) toggleCurCat.addEventListener('click', async () => { await auxToggleCurrentCategory(); });
    const delCurCat = document.getElementById('aux-del-cur-cat');
    if (delCurCat) delCurCat.addEventListener('click', async () => { await auxDeleteCurrentCategory(); });
}

async function auxApplyFilters() {
    auxMemoryState.searchQuery = document.getElementById('aux-search')?.value?.trim() || '';
    await auxLoadItems();
    auxRenderCenter();
}

async function auxCreateCategory() {
    const name = document.getElementById('aux-new-cat-name')?.value?.trim() || '';
    if (!name) return showToast('请输入分类名称', 'warning');
    try {
        const res = await apiCall('/api/aux-memory/categories', 'POST', { name, description: '', summary: '', enabled: true, user_id: '' });
        auxMemoryState.currentCategoryId = res.category?.id || '';
        auxMemoryState.selectedItemId = '';
        auxMemoryState.selectedItemIds = [];
        await refreshAuxMemoryData();
        renderAuxMemoryNavPanel();
        auxRenderCenter();
        showToast('分类已创建', 'success');
    } catch (e) {
        showToast(`创建分类失败: ${e.message}`, 'error');
    }
}

async function auxToggleCategory(categoryId) {
    const cat = auxMemoryState.categories.find((c) => c.id === categoryId);
    if (!cat) return showToast('分类不存在', 'warning');
    try {
        await apiCall(`/api/aux-memory/categories/${cat.id}`, 'PATCH', { enabled: !cat.enabled, user_id: '' });
        await auxLoadCategories();
        renderAuxMemoryNavPanel();
        auxRenderCenter();
        showToast(`分类已${cat.enabled ? '停用' : '启用'}`, 'success');
    } catch (e) {
        showToast(`切换分类失败: ${e.message}`, 'error');
    }
}

async function auxDeleteCategory(categoryId) {
    const cat = auxMemoryState.categories.find((c) => c.id === categoryId);
    if (!cat) return showToast('分类不存在', 'warning');
    if (!confirm(`确定删除分类「${cat.name || '未命名'}」吗？\n该分类下条目会一起删除，不可恢复。`)) return;
    try {
        await apiCall(`/api/aux-memory/categories/${cat.id}`, 'DELETE');
        if (auxMemoryState.currentCategoryId === cat.id) auxMemoryState.currentCategoryId = '';
        auxMemoryState.selectedItemId = '';
        auxMemoryState.selectedItemIds = [];
        await refreshAuxMemoryData();
        renderAuxMemoryNavPanel();
        auxRenderCenter();
        showToast('分类已删除', 'success');
    } catch (e) {
        showToast(`删除分类失败: ${e.message}`, 'error');
    }
}

async function auxToggleCurrentCategory() {
    if (!auxMemoryState.currentCategoryId) return showToast('请先选择分类', 'warning');
    await auxToggleCategory(auxMemoryState.currentCategoryId);
}

async function auxDeleteCurrentCategory() {
    if (!auxMemoryState.currentCategoryId) return showToast('请先选择分类', 'warning');
    await auxDeleteCategory(auxMemoryState.currentCategoryId);
}

async function auxCreateItem() {
    const summary = document.getElementById('aux-new-summary')?.value?.trim() || '';
    if (!summary) return showToast('请填写摘要', 'warning');
    const payload = {
        category_id: document.getElementById('aux-new-category')?.value || auxMemoryState.currentCategoryId || '',
        summary,
        details: document.getElementById('aux-new-details')?.value || '',
        memory_type: document.getElementById('aux-new-type')?.value || 'preference',
        score: Math.max(0, Math.min(1, Number.parseFloat(document.getElementById('aux-new-score')?.value || '0.6') || 0.6)),
        enabled: Boolean(document.getElementById('aux-new-enabled')?.checked),
        tags: auxParseTags(document.getElementById('aux-new-tags')?.value || ''),
        user_id: '',
        source_resource_id: '',
        extra: {}
    };
    try {
        const res = await apiCall('/api/aux-memory/items', 'POST', payload);
        auxMemoryState.selectedItemId = res.item?.id || '';
        auxMemoryState.selectedItemIds = [];
        await refreshAuxMemoryData();
        renderAuxMemoryNavPanel();
        auxRenderCenter();
        showToast('条目已创建', 'success');
    } catch (e) {
        showToast(`创建条目失败: ${e.message}`, 'error');
    }
}

async function auxSaveItem() {
    const cur = auxCurrentItem();
    if (!cur) return showToast('请先选择条目', 'warning');
    const summary = document.getElementById('aux-edit-summary')?.value?.trim() || '';
    if (!summary) return showToast('摘要不能为空', 'warning');
    const payload = {
        category_id: document.getElementById('aux-edit-category')?.value || '',
        summary,
        details: document.getElementById('aux-edit-details')?.value || '',
        memory_type: document.getElementById('aux-edit-type')?.value || 'preference',
        score: Math.max(0, Math.min(1, Number.parseFloat(document.getElementById('aux-edit-score')?.value || '0.5') || 0.5)),
        enabled: Boolean(document.getElementById('aux-edit-enabled')?.checked),
        tags: auxParseTags(document.getElementById('aux-edit-tags')?.value || ''),
        user_id: '',
        source_resource_id: cur.source_resource_id || '',
        extra: cur.extra || {}
    };
    try {
        await apiCall(`/api/aux-memory/items/${cur.id}`, 'PATCH', payload);
        await refreshAuxMemoryData();
        renderAuxMemoryNavPanel();
        auxRenderCenter();
        showToast('条目已保存', 'success');
    } catch (e) {
        showToast(`保存条目失败: ${e.message}`, 'error');
    }
}

async function auxDeleteItem() {
    const cur = auxCurrentItem();
    if (!cur) return showToast('请先选择条目', 'warning');
    if (!confirm('确定删除该条目吗？删除后不可恢复。')) return;
    try {
        await apiCall(`/api/aux-memory/items/${cur.id}`, 'DELETE');
        auxMemoryState.selectedItemId = '';
        auxMemoryState.selectedItemIds = auxMemoryState.selectedItemIds.filter((x) => x !== cur.id);
        await refreshAuxMemoryData();
        renderAuxMemoryNavPanel();
        auxRenderCenter();
        showToast('条目已删除', 'success');
    } catch (e) {
        showToast(`删除条目失败: ${e.message}`, 'error');
    }
}

function auxSelectedVisibleIds() {
    const selected = auxSelectedSet();
    return auxMemoryState.items.map((x) => String(x.id || '')).filter((id) => selected.has(id));
}

async function auxBatchSetEnabled(enabled) {
    const ids = auxSelectedVisibleIds();
    if (ids.length === 0) return showToast('请先勾选要操作的条目', 'warning');
    try {
        const res = await apiCall('/api/aux-memory/items/batch-update', 'POST', { item_ids: ids, enabled: Boolean(enabled) });
        await auxLoadItems();
        auxRenderCenter();
        showToast(`批量${enabled ? '启用' : '停用'}完成：更新 ${Number(res.updated || 0)} 条`, 'success');
    } catch (e) {
        showToast(`批量操作失败: ${e.message}`, 'error');
    }
}

async function auxBatchDelete() {
    const ids = auxSelectedVisibleIds();
    if (ids.length === 0) return showToast('请先勾选要删除的条目', 'warning');
    if (!confirm(`确定删除已选 ${ids.length} 条记忆吗？该操作不可恢复。`)) return;
    try {
        const res = await apiCall('/api/aux-memory/items/batch-delete', 'POST', { item_ids: ids });
        auxMemoryState.selectedItemIds = [];
        if (ids.includes(auxMemoryState.selectedItemId)) auxMemoryState.selectedItemId = '';
        await refreshAuxMemoryData();
        renderAuxMemoryNavPanel();
        auxRenderCenter();
        showToast(`批量删除完成：已删除 ${Number(res.deleted || 0)} 条`, 'success');
    } catch (e) {
        showToast(`批量删除失败: ${e.message}`, 'error');
    }
}

function auxClearScopeText() {
    const scopes = [];
    if (auxMemoryState.currentCategoryId) scopes.push(`分类: ${auxCategoryName(auxMemoryState.currentCategoryId)}`);
    if (auxMemoryState.searchQuery.trim()) scopes.push(`关键词: ${auxMemoryState.searchQuery.trim()}`);
    if (auxMemoryState.enabledOnly) scopes.push('仅启用条目');
    if (auxMemoryState.typeFilter) scopes.push(`类型: ${auxTypeLabel(auxMemoryState.typeFilter)}`);
    return scopes.length > 0 ? scopes.join('；') : '全部长期记忆';
}

async function auxClearFiltered() {
    const matched = auxMemoryState.items.length;
    if (matched <= 0) return showToast('当前筛选下没有可清空条目', 'warning');
    const scope = auxClearScopeText();
    if (!confirm(`将清空当前筛选下 ${matched} 条记忆。\n范围：${scope}\n\n删除后不可恢复，是否继续？`)) return;
    if (!confirm('请再次确认：本次将执行永久删除。')) return;
    try {
        const res = await apiCall('/api/aux-memory/items/clear', 'POST', {
            category_id: auxMemoryState.currentCategoryId || '',
            query: auxMemoryState.searchQuery.trim(),
            user_id: null,
            enabled_only: Boolean(auxMemoryState.enabledOnly),
            memory_type: auxMemoryState.typeFilter || ''
        });
        auxMemoryState.selectedItemId = '';
        auxMemoryState.selectedItemIds = [];
        await refreshAuxMemoryData();
        renderAuxMemoryNavPanel();
        auxRenderCenter();
        showToast(`清空完成：已删除 ${Number(res.deleted || 0)} / 匹配 ${Number(res.matched || 0)} 条`, 'success');
    } catch (e) {
        showToast(`清空失败: ${e.message}`, 'error');
    }
}

async function initAuxMemoryCenter() {
    try {
        await refreshAuxMemoryData();
        renderAuxMemoryNavPanel();
        auxRenderCenter();
    } catch (e) {
        showToast(`知识中心初始化失败: ${e.message}`, 'error');
    }
}

window.auxMemoryState = auxMemoryState;
window.renderAuxMemoryNavPanel = renderAuxMemoryNavPanel;
window.renderAuxMemoryCenter = auxRenderCenter;
window.initAuxMemoryCenter = initAuxMemoryCenter;
window.refreshAuxMemoryData = refreshAuxMemoryData;
window.auxSwitchToWorkbench = auxSwitchToWorkbench;
window.auxSwitchToMemory = auxSwitchToMemory;

console.log('[app-aux-memory.js] loaded');
