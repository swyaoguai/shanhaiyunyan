// @vitest-environment jsdom

import { readFileSync } from 'node:fs';
import path from 'node:path';
import { beforeAll, beforeEach, describe, expect, it, vi } from 'vitest';

const ROOT = process.cwd();

function loadBrowserScript(relativePath) {
  const absolutePath = path.join(ROOT, relativePath);
  const source = readFileSync(absolutePath, 'utf8');
  window.eval(source);
}

function resetAuxGlobals() {
  window.NovelAgentApp = {
    core: {
      ui: {
        navList: document.getElementById('nav-list-container'),
        workspace: document.getElementById('main-view')
      },
      switchModule: vi.fn()
    }
  };
  window.ui = window.NovelAgentApp.core.ui;
  window.switchModule = window.NovelAgentApp.core.switchModule;
  window.apiCall = vi.fn();
  window.showToast = vi.fn();
  window.updateBreadcrumbs = vi.fn();
  window.escapeHtml = (value) =>
    String(value ?? '')
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
  window.makeElementActivatable = vi.fn();
  window.confirm = vi.fn(() => true);
}

beforeAll(() => {
  loadBrowserScript('novel_agent/web/static/app-aux-memory.js');
});

beforeEach(() => {
  document.body.innerHTML = `
    <div id="nav-list-container"></div>
    <div id="main-view"></div>
  `;
  vi.restoreAllMocks();
  resetAuxGlobals();
  window.auxMemoryState.categories = [];
  window.auxMemoryState.items = [];
  window.auxMemoryState.totalItems = 0;
  window.auxMemoryState.currentCategoryId = '';
  window.auxMemoryState.selectedItemId = '';
  window.auxMemoryState.selectedItemIds = [];
  window.auxMemoryState.searchQuery = '';
  window.auxMemoryState.enabledOnly = false;
  window.auxMemoryState.typeFilter = '';
  window.auxMemoryState.itemLimit = 200;
});

describe('aux-memory DOM regressions', () => {
  it('renders nav and center panels with extracted layout sections', () => {
    window.auxMemoryState.categories = [
      { id: 'cat-a', name: '分类A', enabled: true }
    ];
    window.auxMemoryState.items = [
      {
        id: 'item-1',
        category_id: 'cat-a',
        summary: '记忆摘要一',
        details: '记忆详情一',
        memory_type: 'fact',
        score: 0.8,
        enabled: true,
        tags: ['线索']
      }
    ];
    window.auxMemoryState.totalItems = 1;
    window.auxMemoryState.selectedItemId = 'item-1';

    window.renderAuxMemoryNavPanel();
    window.renderAuxMemoryCenter();

    expect(document.getElementById('nav-list-container').textContent).toContain('全部记忆');
    expect(document.getElementById('nav-list-container').textContent).toContain('分类A');
    expect(document.getElementById('main-view').textContent).toContain('条目详情');
    expect(document.getElementById('main-view').textContent).toContain('新增记忆条目');
    expect(document.getElementById('main-view').textContent).toContain('分类管理');
    expect(document.querySelector('[data-aux-item="item-1"]')).not.toBeNull();
    expect(document.getElementById('aux-edit-summary')?.value).toBe('记忆摘要一');
  });

  it('updates selected count and select-all state after rendering', () => {
    window.auxMemoryState.items = [
      { id: 'item-1', category_id: '', summary: '一', details: '', memory_type: 'fact', score: 0.5, enabled: true, tags: [] },
      { id: 'item-2', category_id: '', summary: '二', details: '', memory_type: 'plot', score: 0.6, enabled: false, tags: [] }
    ];
    window.auxMemoryState.totalItems = 2;
    window.auxMemoryState.selectedItemId = 'item-1';
    window.auxMemoryState.selectedItemIds = ['item-1'];

    window.renderAuxMemoryCenter();

    const countText = document.getElementById('aux-selected-count-text');
    const selectAll = document.getElementById('aux-select-all-visible');

    expect(countText?.textContent).toContain('已选 1 条');
    expect(selectAll?.checked).toBe(false);
    expect(selectAll?.indeterminate).toBe(true);
  });

  it('binds item selection and checkbox batch selection after rerender', () => {
    window.auxMemoryState.items = [
      { id: 'item-1', category_id: '', summary: '一', details: '', memory_type: 'fact', score: 0.5, enabled: true, tags: [] },
      { id: 'item-2', category_id: '', summary: '二', details: '', memory_type: 'plot', score: 0.6, enabled: false, tags: [] }
    ];
    window.auxMemoryState.totalItems = 2;
    window.auxMemoryState.selectedItemId = 'item-1';

    window.renderAuxMemoryCenter();

    document.querySelector('[data-aux-item="item-2"]')?.dispatchEvent(new MouseEvent('click', { bubbles: true }));
    expect(window.auxMemoryState.selectedItemId).toBe('item-2');

    const checkbox = document.querySelector('[data-aux-item-check="item-2"]');
    checkbox.checked = true;
    checkbox.dispatchEvent(new Event('change', { bubbles: true }));

    expect(window.auxMemoryState.selectedItemIds).toContain('item-2');
    expect(document.getElementById('aux-selected-count-text')?.textContent).toContain('已选 1 条');
  });
});
