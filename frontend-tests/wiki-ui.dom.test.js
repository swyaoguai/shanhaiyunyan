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

beforeAll(() => {
  loadBrowserScript('novel_agent/web/static/app-wiki.js');
});

beforeEach(() => {
  document.body.innerHTML = '<div id="main-view"><div id="wiki-content"></div><div id="wiki-stats"></div></div>';
  localStorage.clear();
  vi.restoreAllMocks();
});

describe('wiki UI polish', () => {
  it('hides internal metadata headings from the readable page body', () => {
    const page = {
      title: '定情之物',
      body: [
        '# 定情之物',
        '一件不起眼的小物成为二人专属信物。',
        '',
        '## id',
        'subplot_a',
        '',
        '## thread_id',
        'subplot_a',
        '',
        '## description',
        '一件不起眼的小物成为二人专属信物。',
      ].join('\n'),
    };

    const clean = window.WikiModule.__test.cleanWikiBodyForReading(page);

    expect(clean).not.toContain('thread_id');
    expect(clean).not.toContain('subplot_a');
    expect(clean).not.toContain('# 定情之物');
    expect(clean).toContain('## 简介');
  });

  it('uses Chinese labels for wiki page types', () => {
    expect(window.WikiModule.__test.getPageTypeLabel('custom')).toBe('自定义');
    expect(window.WikiModule.__test.getPageTypeLabel('plot')).toBe('剧情');
    expect(window.WikiModule.__test.getPageTypeLabel('world')).toBe('世界观');
  });

  it('renders graph as a node canvas with category controls', async () => {
    global.fetch = vi.fn(async () => ({
      json: async () => ({
        success: true,
        data: {
          nodes: [
            { id: '亚恒', label: '亚恒', type: 'character', degree: 2, tags: [] },
            { id: '玄铁令', label: '玄铁令', type: 'concept', degree: 1, tags: ['物品'] },
          ],
          edges: [
            { source: '亚恒', target: '玄铁令', weight: 1, signals: { explicit_link: 1 } },
          ],
          statistics: { nodes: 2, edges: 1, avg_degree: 1, isolated_count: 0 },
        },
      }),
    }));

    await window.WikiModule.showGraph();

    expect(document.getElementById('wiki-graph-canvas')).not.toBeNull();
    expect(document.querySelector('[data-wiki-graph-node="亚恒"]')).not.toBeNull();
    expect(document.body.textContent).toContain('角色');
    expect(document.body.textContent).toContain('物件');
  });
});
