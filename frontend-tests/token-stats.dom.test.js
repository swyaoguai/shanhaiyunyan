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

function jsonResponse(data) {
  return Promise.resolve({
    ok: true,
    json: () => Promise.resolve(data)
  });
}

beforeAll(() => {
  loadBrowserScript('novel_agent/web/static/app-utils.js');
  loadBrowserScript('novel_agent/web/static/app-core.js');
  loadBrowserScript('novel_agent/web/static/app-token-stats.js');
});

beforeEach(() => {
  document.body.innerHTML = `
    <div id="breadcrumbs"></div>
    <main id="main-view"></main>
  `;
  vi.restoreAllMocks();
  window.initUIReferences();
  window.store.currentProjectName = '测试项目';
  window.showToast = vi.fn();
  window.confirm = vi.fn(() => true);
});

describe('token stats page', () => {
  it('shows current-project model statistics without any agent selector or agent tab', async () => {
    const fetchMock = vi.fn(url => {
      const text = String(url);
      if (text.includes('/token-stats/filters')) {
        return jsonResponse({ models: ['gpt-4', 'deepseek-chat'], agents: ['RouterAgent'] });
      }
      if (text.includes('/token-stats/summary')) {
        return jsonResponse({
          total_tokens: 300,
          tokens_in: 120,
          tokens_out: 180,
          call_count: 2,
          avg_tokens_per_call: 150,
          success_rate: 100,
          avg_duration: 1.2
        });
      }
      if (text.includes('/token-stats/hourly')) {
        return jsonResponse({
          data: [
            { hour: '2026-05-06 10:00', total_tokens: 300, tokens_in: 120, tokens_out: 180, call_count: 2 }
          ]
        });
      }
      if (text.includes('/token-stats/daily')) {
        return jsonResponse({ data: [] });
      }
      if (text.includes('/token-stats/by-model')) {
        return jsonResponse({ data: [] });
      }
      return jsonResponse({});
    });
    vi.stubGlobal('fetch', fetchMock);

    await window.renderTokenStats();

    expect(document.getElementById('filter-model')).not.toBeNull();
    expect(document.getElementById('filter-agent')).toBeNull();
    expect(document.querySelector('[data-view="agents"]')).toBeNull();
    expect(document.body.textContent).toContain('当前项目：测试项目');
    expect(document.body.textContent).toContain('24小时');
    expect(document.body.textContent).toContain('一周');
    expect(document.body.textContent).toContain('一月');
    expect(document.body.textContent).toContain('按模型');
    expect(document.body.textContent).not.toContain('按Agent');

    const urls = fetchMock.mock.calls.map(([url]) => String(url));
    expect(urls.some(url => url.includes('/token-stats/summary') && url.includes('days=1'))).toBe(true);
    expect(urls.some(url => url.includes('/token-stats/hourly') && url.includes('hours=24'))).toBe(true);
    expect(urls.every(url => !url.includes('agent_name'))).toBe(true);
  });
});
