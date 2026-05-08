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

function flushPromises() {
  return new Promise((resolve) => setTimeout(resolve, 0));
}

beforeAll(() => {
  loadBrowserScript('novel_agent/web/static/app-utils.js');
  loadBrowserScript('novel_agent/web/static/app-project.js');
});

beforeEach(() => {
  document.body.innerHTML = `
    <div id="modal-container" class="hidden"></div>
    <span id="current-project-name"></span>
  `;
  vi.restoreAllMocks();
  window.store = {
    projects: [],
    currentProjectId: null,
    currentModule: 'dashboard',
    knowledgeCategories: [],
    projectData: {}
  };
  window.showToast = vi.fn();
  window.switchModule = vi.fn();
  window.apiCall = vi.fn(async (url, method, body) => {
    if (url === '/api/projects' && method === 'POST') {
      return { project: { id: 'project-1', name: body.name } };
    }
    if (url === '/api/projects/project-1/switch' && method === 'POST') {
      return { success: true };
    }
    if (url.startsWith('/api/project-data/')) {
      return { data: [] };
    }
    throw new Error(`Unexpected API call: ${method || 'GET'} ${url}`);
  });
});

describe('create project dialog', () => {
  it('starts with no selected or prefilled genre and blocks empty genre submission', async () => {
    window.showCreateProjectDialog();

    const preset = document.getElementById('new-project-genre-preset');
    const genreInput = document.getElementById('new-project-genre');

    expect(preset?.tagName).toBe('SELECT');
    expect(document.getElementById('new-project-genre-options')).toBeNull();
    expect(genreInput?.getAttribute('list')).toBeNull();
    expect(preset?.textContent).toContain('都市现代');
    expect(preset?.textContent).toContain('自定义分类');
    expect(preset.value).toBe('');
    expect(genreInput.value).toBe('');

    document.getElementById('new-project-name').value = '测试项目';
    document.getElementById('confirm-create-project').click();
    await flushPromises();

    expect(window.showToast).toHaveBeenCalledWith('请选择小说分类或输入自定义分类', 'error');
    expect(window.apiCall).not.toHaveBeenCalledWith(
      '/api/projects',
      'POST',
      expect.anything()
    );
  });

  it('submits a manually selected preset genre', async () => {
    window.showCreateProjectDialog();

    const preset = document.getElementById('new-project-genre-preset');
    const genreInput = document.getElementById('new-project-genre');

    preset.value = '都市现代';
    preset.dispatchEvent(new Event('change', { bubbles: true }));
    expect(genreInput.value).toBe('');

    document.getElementById('new-project-name').value = '测试项目';
    document.getElementById('confirm-create-project').click();
    await flushPromises();
    await flushPromises();

    expect(window.apiCall).toHaveBeenCalledWith('/api/projects', 'POST', {
      name: '测试项目',
      description: '',
      novel_type: '都市现代',
      genre: '都市现代'
    });
  });

  it('submits a manually typed custom genre', async () => {
    window.showCreateProjectDialog();

    const preset = document.getElementById('new-project-genre-preset');
    const genreInput = document.getElementById('new-project-genre');

    genreInput.value = '赛博修仙';
    genreInput.dispatchEvent(new Event('input', { bubbles: true }));
    expect(preset.value).toBe('__custom__');

    document.getElementById('new-project-name').value = '测试项目';
    document.getElementById('confirm-create-project').click();
    await flushPromises();
    await flushPromises();

    expect(window.apiCall).toHaveBeenCalledWith('/api/projects', 'POST', {
      name: '测试项目',
      description: '',
      novel_type: '赛博修仙',
      genre: '赛博修仙'
    });
  });
});
