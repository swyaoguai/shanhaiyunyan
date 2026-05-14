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
  loadBrowserScript('novel_agent/web/static/app-utils.js');
  loadBrowserScript('novel_agent/web/static/app-nav.js');
});

beforeEach(() => {
  document.body.innerHTML = '<main id="main-view"></main><div id="breadcrumbs"></div>';
  window.ui = {
    workspace: document.getElementById('main-view'),
    breadcrumbs: document.getElementById('breadcrumbs')
  };
  window.showToast = vi.fn();
});

describe('about feedback page', () => {
  it('renders support email and log actions', () => {
    window.renderFeedbackPage();

    expect(document.body.textContent).toContain('swjiarui@126.com');
    expect(document.querySelector('a[href="mailto:swjiarui@126.com"]')).not.toBeNull();
    expect(document.getElementById('copy-support-logs')).not.toBeNull();
    expect(document.getElementById('export-support-logs')).not.toBeNull();
  });

  it('copies support logs from diagnostics api', async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, 'clipboard', {
      value: { writeText },
      configurable: true
    });
    vi.stubGlobal('fetch', vi.fn(() => Promise.resolve({
      ok: true,
      text: () => Promise.resolve('support log text')
    })));

    window.renderFeedbackPage();
    document.getElementById('copy-support-logs').click();

    await vi.waitFor(() => {
      expect(writeText).toHaveBeenCalledWith('support log text');
    });
    expect(fetch).toHaveBeenCalledWith('/api/v1/diagnostics/logs', { cache: 'no-store' });
    expect(window.showToast).toHaveBeenCalledWith('后台日志已复制', 'success');
  });
});
