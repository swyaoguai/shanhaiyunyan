// @vitest-environment jsdom

import { readFileSync } from 'node:fs';
import path from 'node:path';
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest';

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
});

beforeEach(() => {
  vi.useFakeTimers();
  vi.restoreAllMocks();
  window.resetAppRuntimeLifecycleForTests();
});

afterEach(() => {
  window.resetAppRuntimeLifecycleForTests();
  vi.useRealTimers();
});

describe('packaged app runtime lifecycle', () => {
  it('sends heartbeats and a close beacon when packaged shutdown is enabled', async () => {
    const fetchMock = vi.fn(url => {
      const text = String(url);
      if (text.includes('/api/app/runtime')) {
        return jsonResponse({
          close_shutdown_enabled: true,
          heartbeat_interval_ms: 2000
        });
      }
      return jsonResponse({ ok: true });
    });
    const sendBeacon = vi.fn(() => true);

    vi.stubGlobal('fetch', fetchMock);
    Object.defineProperty(window.navigator, 'sendBeacon', {
      value: sendBeacon,
      configurable: true
    });

    await window.initAppRuntimeLifecycle();

    expect(fetchMock.mock.calls.some(([url]) => String(url).includes('/api/app/runtime'))).toBe(true);
    expect(fetchMock.mock.calls.some(([url]) => String(url).includes('/api/app/window-heartbeat'))).toBe(true);

    fetchMock.mockClear();
    await vi.advanceTimersByTimeAsync(2000);
    expect(fetchMock.mock.calls.some(([url]) => String(url).includes('/api/app/window-heartbeat'))).toBe(true);

    window.dispatchEvent(new Event('pagehide'));

    expect(sendBeacon).toHaveBeenCalledTimes(1);
    expect(String(sendBeacon.mock.calls[0][0])).toContain('/api/app/window-closed');
  });

  it('does nothing when packaged shutdown is disabled', async () => {
    const fetchMock = vi.fn(url => {
      if (String(url).includes('/api/app/runtime')) {
        return jsonResponse({ close_shutdown_enabled: false });
      }
      return jsonResponse({ ok: true });
    });
    const sendBeacon = vi.fn(() => true);

    vi.stubGlobal('fetch', fetchMock);
    Object.defineProperty(window.navigator, 'sendBeacon', {
      value: sendBeacon,
      configurable: true
    });

    await window.initAppRuntimeLifecycle();
    await vi.advanceTimersByTimeAsync(5000);
    window.dispatchEvent(new Event('pagehide'));

    expect(fetchMock.mock.calls.filter(([url]) => String(url).includes('/api/app/window-heartbeat'))).toHaveLength(0);
    expect(sendBeacon).not.toHaveBeenCalled();
  });
});
