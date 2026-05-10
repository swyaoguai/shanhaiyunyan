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

  it('buffers protocol-shaped streaming chunks instead of leaking JSON fragments', () => {
    const filter = window.createCopilotStreamTextFilter();

    expect(filter.push('{"type":"llm_chunk","agent":"Worldbuilder","content":"')).toBe('');
    expect(filter.push('道","seed":"abc"}')).toBe('');
    expect(filter.push('\n\n真正给用户看的回复。')).toBe('真正给用户看的回复。');
    expect(filter.flush()).toBe('');
  });

  it('removes complete protocol payloads when visible text follows in the same stream chunk', () => {
    const filter = window.createCopilotStreamTextFilter();

    expect(filter.push('{"type":"llm_chunk","agent":"Worldbuilder","delta":"内"}\n真正给用户看的回复。')).toBe('真正给用户看的回复。');
    expect(filter.flush()).toBe('');
  });

  it('extracts visible content from complete structured stream chunks', () => {
    const filter = window.createCopilotStreamTextFilter();

    expect(filter.push('{"type":"chunk","content":"第一行\\n第二行"}')).toBe('第一行\n第二行');
    expect(filter.flush()).toBe('');
  });

  it('does not show llm_chunk workflow progress as user-visible status', () => {
    const aiDiv = window.createStreamMessage();

    window.appendStreamWorkflowProgress(aiDiv, {
      type: 'llm_chunk',
      current_agent: 'Worldbuilder',
      last_progress: '"seed":"abc"'
    });

    expect(aiDiv.querySelector('.copilot-progress-trace-line')).toBeNull();
  });

  it('renders raw structured payloads as a readable code block', () => {
    window.appendMessage('{"continents":["中原大陆"],"events":["开端"]}', 'ai');

    const code = document.querySelector('.msg.ai .msg-content pre code');
    expect(code).not.toBeNull();
    expect(code?.textContent).toContain('"continents"');
    expect(code?.textContent).toContain('"中原大陆"');
  });

  it('keeps assistant bubbles wide enough for structured content', () => {
    const css = readFileSync(path.join(ROOT, 'novel_agent/web/static/style.css'), 'utf8');

    expect(css).toMatch(/\.msg\.ai\s*\{[\s\S]*min-width:\s*min\(260px,\s*90%\);/);
    expect(css).toMatch(/\.msg-content pre code\s*\{[\s\S]*white-space:\s*pre-wrap;/);
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

  it('keeps broad creation briefs out of the plot field on contract cards', () => {
    window.appendMessage(window.renderCreationContractCard({
      contract_id: 'contract-3',
      user_confirmed: false,
      scope: {
        novel_type: '古代言情',
        theme: '古代甜宠',
        protagonist: '',
        plot_idea: '',
        ai_autonomy_requested: true,
        target_word_count: 50000,
        volume_count: 1,
        chapters_per_volume: 17,
        total_chapters: 17
      },
      constraints: { style: [], quality_rules: ['避免AI腔'] },
      deliverables: [],
      task_graph: []
    }), 'ai');

    const cardText = document.querySelector('.copilot-contract-card')?.textContent || '';
    expect(cardText).toContain('类型古代言情');
    expect(cardText).toContain('主题古代甜宠');
    expect(cardText).toContain('主角由助手自主设定');
    expect(cardText).toContain('剧情由助手自主构思');
    expect(cardText).not.toContain('我想写一本');
  });
});
