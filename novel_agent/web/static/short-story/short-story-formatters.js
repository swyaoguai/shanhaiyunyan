/**
 * 山海·云烟 - 短篇创作格式化与派生辅助
 */

function renderShortStoryModelOptions(configId, selectedModel) {
    const config = shortStoryState.apiConfigs.find((item) => item.id === configId);
    if (!config || !Array.isArray(config.models) || config.models.length === 0) {
        if (shortStoryState.globalModel) {
            return `<option value="${escapeHtml(shortStoryState.globalModel)}" ${shortStoryState.globalModel === selectedModel ? 'selected' : ''}>${escapeHtml(shortStoryState.globalModel)}（全局模型）</option>`;
        }
        return '<option value="">-- 请先在该配置中添加模型 --</option>';
    }

    return config.models.map((model) => `
        <option value="${escapeHtml(model)}" ${model === selectedModel ? 'selected' : ''}>${escapeHtml(model)}</option>
    `).join('');
}

function getShortStoryStageLabel(stage) {
    const labels = {
        awaiting_keywords: '等待素材',
        analyzing_source_input: '识别素材',
        generating_fusion_options: '生成方案',
        awaiting_fusion_selection: '选择方案',
        generating_synopsis: '生成导语',
        awaiting_synopsis_selection: '选择导语',
        generating_outline: '生成大纲',
        awaiting_outline_confirm: '确认大纲',
        writing_content: '创作正文',
        quality_checking: '质量检查',
        coherence_reviewing: '通篇复审',
        generating_titles: '生成书名',
        awaiting_title_selection: '选择书名',
        assembling_output: '组装成稿',
        completed: '已完成'
    };

    return labels[stage] || '未开始';
}

function getSelectedApiConfigIdForShortStory() {
    const select = document.getElementById('short-story-api-config');
    if (select && select.value) {
        return select.value;
    }
    return shortStoryState.selectedApiConfigId || shortStoryState.activeConfigId || '';
}

function getCurrentShortStoryWorkflow() {
    return shortStoryState.workflow || null;
}

function getCurrentShortStoryStage() {
    return getCurrentShortStoryWorkflow()?.state || 'awaiting_keywords';
}

function isShortStoryPlaceholderBlueprint(blueprint = {}) {
    return Boolean(blueprint?.is_placeholder)
        || (
            !String(blueprint?.summary || '').trim()
            && !String(blueprint?.characters || '').trim()
            && !String(blueprint?.core_event || '').trim()
            && !String(blueprint?.narrative_function || '').trim()
            && !String(blueprint?.emotion_point || '').trim()
        );
}

function getShortStorySectionsMeta() {
    return [
        { id: 'fusion', step: 1, title: '创意方案', icon: 'ri-magic-line', stages: ['awaiting_keywords', 'analyzing_source_input', 'generating_fusion_options', 'awaiting_fusion_selection'] },
        { id: 'synopsis', step: 2, title: '导语生成', icon: 'ri-chat-quote-line', stages: ['generating_synopsis', 'awaiting_synopsis_selection'] },
        { id: 'outline', step: 3, title: '大纲确认', icon: 'ri-git-branch-line', stages: ['generating_outline', 'awaiting_outline_confirm'] },
        { id: 'chapter', step: 4, title: '正文创作', icon: 'ri-book-open-line', stages: ['writing_content'] },
        { id: 'quality', step: 5, title: '质量检查', icon: 'ri-shield-check-line', stages: ['quality_checking'] },
        { id: 'coherence', step: 6, title: '通篇复审', icon: 'ri-search-eye-line', stages: ['coherence_reviewing'] },
        { id: 'title', step: 7, title: '书名生成', icon: 'ri-font-size-2', stages: ['generating_titles', 'awaiting_title_selection'] },
        { id: 'assemble', step: 8, title: '成稿组装', icon: 'ri-file-paper-2-line', stages: ['assembling_output', 'completed'] }
    ];
}

function getShortStoryCurrentSectionId(stage = getCurrentShortStoryStage()) {
    const current = getShortStorySectionsMeta().find((item) => item.stages.includes(stage));
    return current ? current.id : 'fusion';
}

function getShortStoryProgressSummary(workflow) {
    if (!workflow) {
        return { completed: 0, total: getShortStorySectionsMeta().length };
    }

    const completed = [
        Boolean(workflow.selected_fusion),
        Boolean(workflow.selected_synopsis),
        Boolean(workflow.outline_confirmed),
        (workflow.chapters || []).length >= (workflow.planned_chapters || 1),
        Boolean(workflow.quality_report),
        Boolean(workflow.coherence_report),
        Boolean(workflow.selected_title),
        Boolean(workflow.final_output)
    ].filter(Boolean).length;

    return { completed, total: getShortStorySectionsMeta().length };
}

function getShortStorySectionStatus(sectionId, workflow, currentSectionId) {
    if (!workflow) {
        return sectionId === 'fusion' ? 'active' : 'pending';
    }

    const doneMap = {
        fusion: Boolean(workflow.selected_fusion),
        synopsis: Boolean(workflow.selected_synopsis),
        outline: Boolean(workflow.outline_confirmed),
        chapter: (workflow.chapters || []).length >= (workflow.planned_chapters || 1),
        quality: Boolean(workflow.quality_report),
        coherence: Boolean(workflow.coherence_report),
        title: Boolean(workflow.selected_title),
        assemble: Boolean(workflow.final_output)
    };

    if (doneMap[sectionId]) {
        return 'done';
    }
    if (sectionId === currentSectionId) {
        return 'active';
    }
    return 'pending';
}

function getShortStorySectionBadge(sectionId, workflow, currentSectionId) {
    const status = getShortStorySectionStatus(sectionId, workflow, currentSectionId);
    if (status === 'done') return '已完成';
    if (status === 'active') return '进行中';
    return '待处理';
}

function formatShortStorySavedTime() {
    if (!shortStoryState.draftSavedAt) return '未保存草稿';

    const diff = Date.now() - shortStoryState.draftSavedAt;
    if (diff < 60_000) return '刚刚自动保存';

    const minutes = Math.floor(diff / 60_000);
    if (minutes < 60) return `${minutes} 分钟前自动保存`;
    return '已保存草稿';
}

function isShortStoryActionLoading(actionName) {
    return shortStoryState.loadingAction === actionName;
}

function getShortStoryButtonLabel(actionName, defaultLabel, loadingLabel) {
    if (!isShortStoryActionLoading(actionName)) {
        return defaultLabel;
    }

    return `<i class="ri-loader-4-line short-story-loading-spinner" aria-hidden="true"></i><span>${loadingLabel}</span>`;
}

function getShortStoryLoadingMeta(actionName = shortStoryState.loadingAction) {
    if (!actionName) {
        return null;
    }

    const elapsedSeconds = shortStoryState.loadingStartedAt
        ? Math.max(1, Math.floor((Date.now() - shortStoryState.loadingStartedAt) / 1000))
        : 0;
    const elapsedText = elapsedSeconds ? `已持续 ${elapsedSeconds} 秒` : '';
    const batchProgress = shortStoryState.batchGenerationProgress || null;

    const chapterMatch = actionName.match(/^generate-chapter-(\d+)$/);
    if (chapterMatch) {
        return {
            text: `正在生成第${chapterMatch[1]}章正文...`,
            hint: elapsedText ? `生成完成后会自动写入对应章节编辑区。${elapsedText}` : '生成完成后会自动写入对应章节编辑区。'
        };
    }

    const saveChapterMatch = actionName.match(/^save-chapter-(\d+)$/);
    if (saveChapterMatch) {
        return {
            text: `正在保存第${saveChapterMatch[1]}章...`,
            hint: '保存完成后会继续保留当前编辑内容。'
        };
    }

    const synopsisSelectionMatch = actionName.match(/^select-synopsis-(\d+)$/);
    if (synopsisSelectionMatch) {
        return {
            text: `正在确认第${synopsisSelectionMatch[1]}条导语...`,
            hint: '确认后将自动进入大纲生成阶段。'
        };
    }

    const fusionSelectionMatch = actionName.match(/^select-fusion-(\d+)$/);
    if (fusionSelectionMatch) {
        return {
            text: `正在确认第${fusionSelectionMatch[1]}个创意方案...`,
            hint: '确认后将自动进入导语生成阶段。'
        };
    }

    const titleSelectionMatch = actionName.match(/^select-title-(\d+)$/);
    if (titleSelectionMatch) {
        return {
            text: `正在确认第${titleSelectionMatch[1]}个书名...`,
            hint: '确认后会自动进入成稿组装。'
        };
    }

    const actionMeta = {
        'generate-fusion': {
            text: '正在识别素材并生成方案...',
            hint: '系统会自动拆解输入，并给出 3 个不同风格的创意方案。'
        },
        'generate-synopsis': {
            text: '正在生成导语...',
            hint: '系统会按已选创意方案一次产出 5 条候选导语。'
        },
        'generate-outline': {
            text: '正在生成大纲...',
            hint: '系统会基于已选导语拆出章节蓝图。'
        },
        'confirm-outline': {
            text: '正在确认大纲...',
            hint: '确认后会解锁正文创作区域。'
        },
        'revise-outline': {
            text: '正在重生成大纲...',
            hint: '系统会结合你的反馈重新规划章节结构。'
        },
        'generate-all-chapters': {
            text: batchProgress?.currentChapter
                ? `正在生成第${batchProgress.currentChapter}章正文...`
                : '正在生成正文...',
            hint: batchProgress
                ? `当前批次 ${batchProgress.completed}/${batchProgress.total}，系统会按章节顺序补全全部剩余正文。${elapsedText}`.trim()
                : (elapsedText ? `系统会按章节顺序补全全部剩余正文。${elapsedText}` : '系统会按章节顺序补全全部剩余正文。')
        },
        'resume-all-chapters': {
            text: batchProgress?.currentChapter
                ? `正在从第${batchProgress.currentChapter}章继续生成...`
                : '正在继续生成正文...',
            hint: batchProgress
                ? `当前批次 ${batchProgress.completed}/${batchProgress.total}，系统会从失败章节继续补全剩余正文。${elapsedText}`.trim()
                : (elapsedText ? `系统会从失败章节继续补全剩余正文。${elapsedText}` : '系统会从失败章节继续补全剩余正文。')
        },
        'generate-quality': {
            text: '正在生成质检报告...',
            hint: '系统会检查正文质量并给出修订建议。'
        },
        'commit-quality': {
            text: '正在提交质检结果...',
            hint: '提交后流程会进入复审阶段。'
        },
        'generate-coherence': {
            text: '正在生成复审报告...',
            hint: '系统会复查结构、角色一致性和收束效果。'
        },
        'commit-coherence': {
            text: '正在提交复审结果...',
            hint: '提交后流程会进入书名阶段。'
        },
        'generate-titles': {
            text: '正在生成书名...',
            hint: '系统会按当前成稿给出 5 个候选书名。'
        },
        'assemble': {
            text: '正在组装成稿...',
            hint: '系统会整理标签、书名和正文，生成最终成稿。'
        }
    };

    return actionMeta[actionName] || {
        text: '正在处理中...',
        hint: '请稍候，完成后界面会自动刷新。'
    };
}

function getShortStoryRepairPlaceholderNumbers(workflow = getCurrentShortStoryWorkflow()) {
    if (!Array.isArray(workflow?.repair_placeholder_numbers)) {
        return [];
    }
    return workflow.repair_placeholder_numbers
        .map((item) => Number(item))
        .filter((item) => Number.isFinite(item) && item > 0)
        .sort((a, b) => a - b);
}

function getShortStoryOutlineRepairChecklist(workflow = getCurrentShortStoryWorkflow(), outlineText = null) {
    const repairNumbers = getShortStoryRepairPlaceholderNumbers(workflow);
    if (repairNumbers.length === 0) {
        return [];
    }

    const parser = typeof parseShortStoryBlueprintsFromOutline === 'function'
        ? parseShortStoryBlueprintsFromOutline
        : (() => []);
    const parsedBlueprints = parser(
        outlineText == null ? (workflow?.outline_text || '') : outlineText
    );
    const parsedNumbers = new Set(
        parsedBlueprints
            .map((item) => Number(item?.chapter_number || 0))
            .filter((item) => Number.isFinite(item) && item > 0)
    );

    return repairNumbers.map((chapterNumber) => ({
        chapter_number: chapterNumber,
        recovered: parsedNumbers.has(chapterNumber)
    }));
}

function renderShortStoryOutlineRepairChecklist(workflow = getCurrentShortStoryWorkflow(), outlineText = null) {
    const checklist = getShortStoryOutlineRepairChecklist(workflow, outlineText);
    if (checklist.length === 0) {
        return '';
    }

    const recoveredCount = checklist.filter((item) => item.recovered).length;
    return `
        <div class="short-story-outline-checklist-card">
            <div class="short-story-outline-checklist-head">
                <strong>缺失章节检查清单</strong>
                <span class="short-story-outline-checklist-summary">已补回 ${recoveredCount}/${checklist.length} 章</span>
            </div>
            <div class="short-story-outline-checklist-items">
                ${checklist.map((item) => `
                    <div class="short-story-outline-checklist-item ${item.recovered ? 'is-done' : 'is-pending'}">
                        <span>第 ${item.chapter_number} 章</span>
                        <strong>${item.recovered ? '已补回' : '待补回'}</strong>
                    </div>
                `).join('')}
            </div>
        </div>
    `;
}

function canShortStoryForceAdvance(reportText) {
    return Boolean((reportText || '').trim());
}

function getShortStoryExportFilename(format) {
    const workflow = getCurrentShortStoryWorkflow();
    const title = (workflow?.selected_title || 'short_story').replace(/[<>:\"/\\\\|?*]+/g, '_').trim() || 'short_story';
    const ext = format === 'md' ? 'md' : format === 'docx' ? 'docx' : 'txt';
    return `${title}.${ext}`;
}

function getShortStoryDeliverableTags(workflow) {
    const items = [];
    const mainCategory = String(workflow?.story_tags?.main_category || workflow?.category || '').trim();
    const allTags = Array.isArray(workflow?.story_tags?.all_tags) ? workflow.story_tags.all_tags : [];

    [mainCategory, ...allTags].forEach((item) => {
        const value = String(item || '').trim();
        if (value && !items.includes(value)) {
            items.push(value);
        }
    });

    return items;
}

function cleanShortStoryDeliverableBlock(text, options = {}) {
    const chapterNumber = Number(options.chapterNumber);
    const stripStyleHint = Boolean(options.stripStyleHint);
    const lines = String(text || '').replace(/\r\n?/g, '\n').split('\n');
    const cleaned = [];
    let previousBlank = false;
    const chapterHeadingPattern = Number.isFinite(chapterNumber)
        ? new RegExp(`^\\s*(?:#+\\s*)?(?:${chapterNumber}\\s*[.、:：-].*|第?\\s*[一二三四五六七八九十百零\\d]+\\s*章(?:\\s*[：:、.\\-]\\s*.*)?)\\s*$`)
        : null;

    lines.forEach((rawLine, index) => {
        let line = String(rawLine || '').trim();
        if (!line) {
            if (cleaned.length > 0 && !previousBlank) {
                cleaned.push('');
                previousBlank = true;
            }
            return;
        }

        line = line.replace(/^#+\s*/, '');
        line = line.replace(/\*\*([^*]+)\*\*/g, '$1');
        if (stripStyleHint) {
            line = line.replace(/[（(][^）)]*向[）)]/g, '');
        }
        line = line.trim();
        if (!line) {
            return;
        }
        if (/^[\\*_\-`~#\s]+$/.test(line)) {
            return;
        }
        if (line === '导语' || line === '正文') {
            return;
        }
        if (index === 0 && chapterHeadingPattern?.test(line)) {
            return;
        }

        cleaned.push(line);
        previousBlank = false;
    });

    while (cleaned.length > 0 && !cleaned[cleaned.length - 1]) {
        cleaned.pop();
    }

    return cleaned.join('\n').trim();
}

function buildCleanFinalOutputFromRaw(finalOutput) {
    const lines = String(finalOutput || '').replace(/\r\n?/g, '\n').split('\n');
    let title = '';
    const tags = [];
    const synopsisLines = [];
    const chapters = [];
    let currentSection = '';
    let currentChapter = null;

    const pushTag = (value) => {
        String(value || '')
            .split(/[、,，|]/)
            .map((item) => item.trim())
            .filter(Boolean)
            .forEach((item) => {
                if (!tags.includes(item)) {
                    tags.push(item);
                }
            });
    };

    const pushChapter = () => {
        if (currentChapter && currentChapter.lines.length > 0) {
            chapters.push({
                chapterNumber: currentChapter.chapterNumber,
                content: currentChapter.lines.join('\n').trim()
            });
        }
        currentChapter = null;
    };

    lines.forEach((rawLine) => {
        let line = String(rawLine || '').trim();
        if (!line) {
            if (currentChapter?.lines?.length && currentChapter.lines[currentChapter.lines.length - 1] !== '') {
                currentChapter.lines.push('');
            } else if (currentSection === 'synopsis' && synopsisLines.length > 0 && synopsisLines[synopsisLines.length - 1] !== '') {
                synopsisLines.push('');
            }
            return;
        }

        line = line.replace(/\*\*([^*]+)\*\*/g, '$1').replace(/^#+\s*/, '').replace(/《([^》]+)》/g, '$1').trim();
        if (!line || /^\\?[*_`~#-]+$/.test(line) || /^---+$/.test(line) || line === '（全文完）') {
            return;
        }

        const mainCategoryMatch = line.match(/^主分类：(.+)$/);
        if (mainCategoryMatch) {
            pushTag(mainCategoryMatch[1]);
            return;
        }
        const contentTagsMatch = line.match(/^内容标签：(.+)$/);
        if (contentTagsMatch) {
            pushTag(contentTagsMatch[1]);
            return;
        }
        if (/^词条标签：/.test(line)) {
            return;
        }
        if (line === '导语') {
            pushChapter();
            currentSection = 'synopsis';
            return;
        }
        if (line === '正文') {
            pushChapter();
            currentSection = 'body';
            return;
        }

        const chapterMatch = line.match(/^(\d+)\.\s*(.*)$/);
        if (chapterMatch) {
            pushChapter();
            currentSection = 'body';
            currentChapter = {
                chapterNumber: Number(chapterMatch[1]),
                lines: []
            };
            return;
        }

        if (!title) {
            title = line;
            return;
        }

        if (currentSection === 'synopsis') {
            const synopsisLine = line.replace(/[（(][^）)]*向[）)]/g, '').trim();
            if (synopsisLine) {
                synopsisLines.push(synopsisLine);
            }
            return;
        }

        if (currentChapter) {
            currentChapter.lines.push(line.replace(/\\\*/g, '').trimEnd());
        }
    });

    pushChapter();

    const result = [];
    if (title) {
        result.push(title);
    }
    if (tags.length > 0) {
        result.push(`标签：${tags.join('、')}`);
    }
    const synopsis = synopsisLines.join('\n').replace(/\n{3,}/g, '\n\n').trim();
    if (synopsis) {
        result.push(`导语：${synopsis}`);
    }
    if (result.length > 0 && chapters.length > 0) {
        result.push('');
    }
    chapters.forEach((chapter) => {
        result.push(`${chapter.chapterNumber}.`);
        if (chapter.content) {
            result.push(chapter.content);
        }
        result.push('');
    });

    while (result.length > 0 && !result[result.length - 1]) {
        result.pop();
    }

    return result.join('\n').replace(/\n{3,}/g, '\n\n').trim();
}

function getCleanFinalOutput(workflow) {
    const rawClean = buildCleanFinalOutputFromRaw(workflow?.final_output || '');
    if (rawClean) {
        return rawClean;
    }

    const title = String(workflow?.selected_title || '').trim().replace(/^《|》$/g, '');
    const tags = getShortStoryDeliverableTags(workflow);
    const synopsis = cleanShortStoryDeliverableBlock(workflow?.selected_synopsis || '', { stripStyleHint: true });
    const chapters = Array.isArray(workflow?.chapters) ? workflow.chapters : [];
    const lines = [];

    if (title) {
        lines.push(title);
    }
    if (tags.length > 0) {
        lines.push(`标签：${tags.join('、')}`);
    }
    if (synopsis) {
        lines.push(`导语：${synopsis}`);
    }
    if (lines.length > 0 && chapters.length > 0) {
        lines.push('');
    }

    chapters.forEach((chapter) => {
        const chapterNumber = Number(chapter?.chapter_number);
        if (!Number.isFinite(chapterNumber)) {
            return;
        }
        lines.push(`${chapterNumber}.`);
        const content = cleanShortStoryDeliverableBlock(chapter?.content || '', { chapterNumber });
        if (content) {
            lines.push(...content.split('\n'));
        }
        lines.push('');
    });

    while (lines.length > 0 && !lines[lines.length - 1]) {
        lines.pop();
    }

    if (lines.length > 0) {
        return lines.join('\n').trim();
    }

    return cleanShortStoryDeliverableBlock(workflow?.final_output || '');
}

window.renderShortStoryModelOptions = renderShortStoryModelOptions;
window.getShortStoryStageLabel = getShortStoryStageLabel;
window.getSelectedApiConfigIdForShortStory = getSelectedApiConfigIdForShortStory;
window.getCurrentShortStoryWorkflow = getCurrentShortStoryWorkflow;
window.getCurrentShortStoryStage = getCurrentShortStoryStage;
window.isShortStoryPlaceholderBlueprint = isShortStoryPlaceholderBlueprint;
window.getShortStorySectionsMeta = getShortStorySectionsMeta;
window.getShortStoryCurrentSectionId = getShortStoryCurrentSectionId;
window.getShortStoryProgressSummary = getShortStoryProgressSummary;
window.getShortStorySectionStatus = getShortStorySectionStatus;
window.getShortStorySectionBadge = getShortStorySectionBadge;
window.formatShortStorySavedTime = formatShortStorySavedTime;
window.isShortStoryActionLoading = isShortStoryActionLoading;
window.getShortStoryButtonLabel = getShortStoryButtonLabel;
window.getShortStoryLoadingMeta = getShortStoryLoadingMeta;
window.getShortStoryRepairPlaceholderNumbers = getShortStoryRepairPlaceholderNumbers;
window.getShortStoryOutlineRepairChecklist = getShortStoryOutlineRepairChecklist;
window.renderShortStoryOutlineRepairChecklist = renderShortStoryOutlineRepairChecklist;
window.canShortStoryForceAdvance = canShortStoryForceAdvance;
window.getShortStoryExportFilename = getShortStoryExportFilename;
window.getCleanFinalOutput = getCleanFinalOutput;
