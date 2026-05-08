// @vitest-environment jsdom

import { readFileSync } from 'node:fs';
import path from 'node:path';
import { beforeAll, beforeEach, describe, expect, it } from 'vitest';

const ROOT = process.cwd();

function loadBrowserScript(relativePath) {
  const absolutePath = path.join(ROOT, relativePath);
  const source = readFileSync(absolutePath, 'utf8');
  window.eval(source);
}

beforeAll(() => {
  loadBrowserScript('novel_agent/web/static/app-utils.js');
  loadBrowserScript('novel_agent/web/static/app-core.js');
});

beforeEach(() => {
  document.body.innerHTML = '<div id="copilot-messages"></div>';
  window.initUIReferences();
});

describe('copilot stream rendering', () => {
  it('keeps streamed chunks as raw text nodes', () => {
    const aiDiv = window.createStreamMessage();
    const content = aiDiv.querySelector('.msg-content');

    content.appendChild(document.createTextNode('<角色>\n第二行'));

    expect(content.textContent).toBe('<角色>\n第二行');
    expect(content.innerHTML).toBe('&lt;角色&gt;\n第二行');
  });

  it('preserves line breaks while an AI message is streaming', () => {
    const css = readFileSync(path.join(ROOT, 'novel_agent/web/static/style.css'), 'utf8');

    expect(css).toMatch(/\.msg\.ai\.streaming\s+\.msg-content\s*\{[\s\S]*white-space:\s*pre-wrap;/);
  });

  it('shows workflow progress without markdown heading markers', () => {
    window.showInlineStatusFromWorkflow({
      current_agent: 'Worldbuilder',
      status: 'running',
      last_progress: '### 世界观阶段\n正在生成世界观设定...'
    });

    expect(document.querySelector('.copilot-inline-status-text')?.textContent).toBe('世界观阶段 正在生成世界观设定...');
    expect(document.body.textContent).not.toContain('###');
  });

  it('keeps workflow progress visible in the streaming message', () => {
    const aiDiv = window.createStreamMessage();

    window.appendStreamWorkflowProgress(aiDiv, {
      last_progress: '### 世界观阶段\n正在生成世界观设定...'
    });

    expect(aiDiv.querySelector('.copilot-progress-trace-line')?.textContent).toBe('世界观阶段 正在生成世界观设定...');
    expect(aiDiv.textContent).not.toContain('###');
  });

  it('parses double-encoded contract payloads from restored cards', () => {
    const wrapper = document.createElement('div');
    wrapper.innerHTML = `
      <div class="copilot-contract-card" data-contract-id="contract-1">
        <button
          class="copilot-contract-confirm-btn"
          data-contract-confirm="{&amp;quot;contract_id&amp;quot;:&amp;quot;contract-1&amp;quot;,&amp;quot;scope&amp;quot;:{&amp;quot;novel_type&amp;quot;:&amp;quot;玄幻&amp;quot;}}">
          确认当前任务并开始
        </button>
      </div>
    `;

    const payload = window.parseCreationContractFromButton(
      wrapper.querySelector('.copilot-contract-confirm-btn')
    );

    expect(payload.contract_id).toBe('contract-1');
    expect(payload.scope.novel_type).toBe('玄幻');
  });

  it('falls back to the runtime contract when button payload is corrupted', () => {
    window.store.pendingCreationContract = {
      contract_id: 'contract-2',
      scope: { novel_type: '科幻' }
    };
    const wrapper = document.createElement('div');
    wrapper.innerHTML = `
      <div class="copilot-contract-card" data-contract-id="contract-2">
        <button class="copilot-contract-confirm-btn" data-contract-confirm="{bad json">
          确认当前任务并开始
        </button>
      </div>
    `;

    const payload = window.parseCreationContractFromButton(
      wrapper.querySelector('.copilot-contract-confirm-btn')
    );

    expect(payload.contract_id).toBe('contract-2');
    expect(payload.scope.novel_type).toBe('科幻');
  });
});
