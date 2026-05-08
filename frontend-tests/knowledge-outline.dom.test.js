// @vitest-environment jsdom

import { readFileSync } from 'node:fs';
import path from 'node:path';
import { describe, expect, it } from 'vitest';

const ROOT = process.cwd();

function loadKnowledgeHelpers() {
  const source = readFileSync(path.join(ROOT, 'novel_agent/web/static/app-knowledge.js'), 'utf8');
  const factory = new Function(`${source}; return { buildOutlineOverviewItem };`);
  return factory();
}

describe('outline knowledge overview', () => {
  it('does not expand placeholder chapter rows into pending outline text', () => {
    const { buildOutlineOverviewItem } = loadKnowledgeHelpers();
    const item = buildOutlineOverviewItem([
      { chapter_number: 1, title: '第1章', summary: '待生成', content: '' },
      { chapter_number: 2, title: '第2章', summary: '待生成', content: '' },
    ]);

    expect(item.summary).toBe('暂无大纲内容。');
    expect(item.summary).not.toContain('【当前章节规划】');
    expect(item.summary).not.toContain('待生成');
    expect(item.volume_plan).toBe('');
  });

  it('renders volume-level plans without chapter lists', () => {
    const { buildOutlineOverviewItem } = loadKnowledgeHelpers();
    const item = buildOutlineOverviewItem([
      {
        title: '主线大纲',
        global_outline: '书名：《山海·云烟》',
        volumes: [
          {
            volume_number: 1,
            volume_title: '秘境初啼',
            volume_summary: '吴迪入秘境，获得噬器能力。',
            chapters: [{ title: '第1章 不应出现' }],
          },
        ],
      },
    ]);

    expect(item.summary).toBe('书名：《山海·云烟》');
    expect(item.volume_plan).toContain('第1卷：秘境初啼');
    expect(item.volume_plan).toContain('吴迪入秘境，获得噬器能力。');
    expect(item.volume_plan).not.toContain('第1章 不应出现');
  });
});
