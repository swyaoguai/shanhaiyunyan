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
  loadBrowserScript('novel_agent/web/static/app-wiki.js');
  loadBrowserScript('novel_agent/web/static/iw-editor.js');
});

beforeEach(() => {
  document.body.innerHTML = '';
  localStorage.clear();
  vi.restoreAllMocks();
});

describe('back button visibility', () => {
  it('keeps the shared back button styling prominent', () => {
    const css = readFileSync(path.join(ROOT, 'novel_agent/web/static/style.css'), 'utf8');

    expect(css).toContain('button.app-back-button');
    expect(css).toContain('min-height: 42px');
    expect(css).toContain('app-back-button--floating');
    expect(css).toContain('font-weight: 700');
  });

  it('renders wiki detail navigation with the shared prominent back button', () => {
    document.body.innerHTML = '<div id="main-view"><div id="wiki-content"></div></div>';

    window.WikiModule.createPage();

    const backButton = document.querySelector('#wiki-content .app-back-button');
    expect(backButton).not.toBeNull();
    expect(backButton.textContent).toContain('返回列表');
    expect(backButton.querySelector('.ri-arrow-left-line')).not.toBeNull();
  });

  it('makes infinite-write editor return actions visible as text buttons', () => {
    const workspace = document.createElement('div');
    document.body.appendChild(workspace);

    window.ui = { workspace };
    window.infiniteWriteState = {
      chapters: [
        {
          chapter_number: 1,
          title: '测试章节',
          content: '测试正文',
          word_count: 4
        }
      ]
    };
    window.updateBreadcrumbs = vi.fn();
    window.setInfiniteWriteActiveView = vi.fn();
    window.saveInfiniteWriteData = vi.fn();
    window.renderInfiniteWriteNavPanel = vi.fn();
    window.loadInfiniteWriteDataForCurrentProject = vi.fn();

    window.showInfiniteWriteChapterEditor(window.infiniteWriteState.chapters[0]);

    const headerBackButton = document.getElementById('close-iw-editor');
    const floatingBackButton = document.getElementById('iw-open-panel-fab');

    expect(headerBackButton.classList.contains('app-back-button')).toBe(true);
    expect(headerBackButton.textContent).toContain('返回创作面板');
    expect(floatingBackButton.classList.contains('app-back-button--floating')).toBe(true);
    expect(floatingBackButton.textContent).toContain('返回创作面板');
  });
});
