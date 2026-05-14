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
  window.renderNavPanel = vi.fn();
  window.showToast = vi.fn();
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

  it('does not show chapter setting rows as saved正文 chapters before approval', () => {
    window.store.projectData.chapters = [];
    window.store.projectData.chapter_settings = [
      { chapter_number: 1, name: '新婚夜', description: '章纲，不是正文' }
    ];

    expect(window.getMultiAgentChapters()).toEqual([]);

    window.renderMultiAgentWriteNavPanel();
    const chapterTitles = Array.from(document.querySelectorAll('.nav-chapter-item .chapter-title'))
      .map((item) => item.textContent);

    expect(chapterTitles).toEqual([]);
    expect(window.store.projectData.chapters).toEqual([]);
  });

  it('filters legacy placeholder rows without shifting saved chapter edit targets', () => {
    window.store.projectData.chapters = [
      {
        chapter_number: 1,
        title: '章纲占位',
        content: '',
        source: 'chapter_settings',
        created_from: 'chapter_settings_placeholder'
      },
      { chapter_number: 2, title: '雨夜', content: '正文' }
    ];
    window.apiCall = vi.fn().mockResolvedValue({});
    window.prompt = vi.fn().mockReturnValue('雨夜改');

    window.editChapterTitle(0);

    expect(window.store.projectData.chapters[0].title).toBe('章纲占位');
    expect(window.store.projectData.chapters[1].title).toBe('雨夜改');
    expect(window.apiCall).toHaveBeenCalledWith('/api/project-data/chapters', 'POST', {
      data: [{ chapter_number: 2, title: '雨夜改', content: '正文' }]
    });
  });
});
