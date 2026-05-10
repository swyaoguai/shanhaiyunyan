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
  loadBrowserScript('novel_agent/web/static/app-chapters.js');
  loadBrowserScript('novel_agent/web/static/continuous_write.js');
});

beforeEach(() => {
  document.body.innerHTML = '<div id="nav-list-container"></div>';
  vi.restoreAllMocks();
  window.formatChapterDisplay = (chapterNumber, title) => `第${chapterNumber}章 ${title || ''}`.trim();
  window.store = {
    currentProjectId: 'proj-collab',
    projectData: {
      chapters: [
        { chapter_number: 123, title: '雨夜', content: '正文' },
        { chapter_number: 124, title: '异象', content: '正文' }
      ],
      chapter_settings: []
    },
    knowledgeCategories: []
  };
  window.showCollaborativeImportDialog = vi.fn();
});

describe('collaborative chapter navigation', () => {
  it('renders saved chapter numbers instead of list positions', () => {
    window.renderMultiAgentWriteNavPanel();

    const chapterTitles = Array.from(document.querySelectorAll('.nav-chapter-item .chapter-title'))
      .map((item) => item.textContent);

    expect(chapterTitles).toEqual(['第123章 雨夜', '第124章 异象']);
  });
});
