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
    status: 200,
    headers: { get: () => 'application/json' },
    json: () => Promise.resolve(data)
  });
}

function flushPromises() {
  return new Promise(resolve => setTimeout(resolve, 0));
}

beforeAll(() => {
  loadBrowserScript('novel_agent/web/static/app-utils.js');
  loadBrowserScript('novel_agent/web/static/app-backup-resources.js');
});

beforeEach(() => {
  document.body.innerHTML = '<div id="settings-content"></div>';
  vi.restoreAllMocks();
  window.showToast = vi.fn();
});

describe('backup resources page', () => {
  it('unwraps auto-backup status and saves toggle through config endpoint', async () => {
    const fetchMock = vi.fn((url, options = {}) => {
      const text = String(url);
      if (text.includes('/backup/list')) {
        return jsonResponse({ backups: [] });
      }
      if (text.includes('/auto-backup/status')) {
        return jsonResponse({
          success: true,
          data: {
            enabled: true,
            schedule: 'daily',
            next_backup_time: '2026-05-11T02:00:00'
          }
        });
      }
      if (text.includes('/auto-backup/config')) {
        return jsonResponse({ success: true, data: { enabled: JSON.parse(options.body).enabled } });
      }
      return jsonResponse({});
    });
    vi.stubGlobal('fetch', fetchMock);

    await window.loadBackupSettings();

    expect(document.body.textContent).toContain('已启用');
    expect(document.body.textContent).toContain('daily');
    const toggle = document.getElementById('auto-backup-toggle');
    expect(toggle.checked).toBe(true);

    toggle.checked = false;
    toggle.dispatchEvent(new Event('change', { bubbles: true }));
    await flushPromises();
    await flushPromises();

    const configCall = fetchMock.mock.calls.find(([url]) => String(url).includes('/auto-backup/config'));
    expect(configCall).toBeTruthy();
    expect(configCall[0]).toBe('/api/v1/auto-backup/config');
    expect(configCall[1].method).toBe('PUT');
    expect(JSON.parse(configCall[1].body)).toEqual({ enabled: false });
    expect(window.showToast).toHaveBeenCalledWith('自动备份已禁用');
  });
});

