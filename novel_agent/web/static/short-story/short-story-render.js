/**
 * 山海·云烟 - 短篇创作渲染层
 */

function renderShortStoryLoadingBanner() {
    const meta = getShortStoryLoadingMeta();
    if (!meta) {
        return '';
    }

    return `
        <div class="short-story-loading-banner" role="status" aria-live="polite">
            <div class="short-story-loading-icon">
                <i class="ri-loader-4-line short-story-loading-spinner" aria-hidden="true"></i>
            </div>
            <div class="short-story-loading-copy">
                <div id="short-story-loading-title" class="short-story-loading-title">${meta.text}</div>
                <div id="short-story-loading-hint" class="short-story-loading-hint">${meta.hint}</div>
            </div>
        </div>
    `;
}

function renderShortStoryRawOutput(summaryText, content) {
    if (!content) return '';

    return `
        <details class="short-story-detail">
            <summary>${summaryText}</summary>
            <pre class="short-story-raw">${escapeHtml(content)}</pre>
        </details>
    `;
}

function resolveShortStoryCategory(value, fallback = '其他') {
    if (typeof normalizeShortStoryCategory === 'function') {
        return normalizeShortStoryCategory(value, fallback);
    }
    const fallbackText = String(fallback || '其他').replace(/\s+/g, ' ').trim() || '其他';
    const category = String(value || '').replace(/\s+/g, ' ').trim();
    return (category || fallbackText).slice(0, 32) || '其他';
}

function getShortStoryMainCategoryOptions() {
    const categories = Array.isArray(window.SHORT_STORY_MAIN_CATEGORIES)
        ? window.SHORT_STORY_MAIN_CATEGORIES
        : ['其他'];
    return categories.map((item) => resolveShortStoryCategory(item)).filter(Boolean);
}

function renderShortStoryCategoryField(categoryDraft) {
    const category = resolveShortStoryCategory(categoryDraft);
    return `
        <input id="short-story-category" list="short-story-category-options" type="text" maxlength="32" value="${escapeHtml(category)}" placeholder="输入或选择主分类" class="short-story-field" autocomplete="off">
        <datalist id="short-story-category-options">
            ${getShortStoryMainCategoryOptions().map((item) => `<option value="${escapeHtml(item)}"></option>`).join('')}
        </datalist>
    `;
}

function renderShortStorySection(meta, workflow, currentSectionId, actionsHtml, bodyHtml, noteHtml = '') {
    const status = getShortStorySectionStatus(meta.id, workflow, currentSectionId);
    const collapsed = isShortStorySectionCollapsed(meta.id, currentSectionId);
    const isCurrent = meta.id === currentSectionId;
    const isHighlighted = shortStoryState.highlightSection === meta.id;

    return `
        <section
            id="short-story-section-${meta.id}"
            class="short-story-section ${status}${collapsed ? ' collapsed' : ''}${isHighlighted ? ' highlighted' : ''}"
            data-section-id="${meta.id}"
            data-status="${status}"
        >
            <div class="short-story-section-head">
                <div class="short-story-section-title-wrap">
                    <div class="short-story-section-index">${meta.step}</div>
                    <div class="short-story-section-title-block">
                        <div class="short-story-section-name">
                            <i class="${meta.icon}"></i>
                            <span>${meta.title}</span>
                        </div>
                        <div class="short-story-section-status">${getShortStorySectionBadge(meta.id, workflow, currentSectionId)}</div>
                    </div>
                </div>
                <div class="short-story-section-toolbar">
                    ${actionsHtml || ''}
                    <button
                        type="button"
                        class="short-story-section-toggle"
                        data-toggle-section="${meta.id}"
                        ${isCurrent ? 'disabled' : ''}
                    >
                        <i class="${collapsed ? 'ri-add-line' : 'ri-subtract-line'}"></i>
                        <span>${isCurrent ? '当前步骤' : (collapsed ? '展开' : '收起')}</span>
                    </button>
                </div>
            </div>
            ${noteHtml ? `<div class="short-story-note">${noteHtml}</div>` : ''}
            ${collapsed ? '' : `<div class="short-story-section-body">${bodyHtml}</div>`}
        </section>
    `;
}

function renderShortStoryPartialChapterResume() {
    const partial = shortStoryState.partialChapterGeneration;
    const failedChapter = Number(partial?.failedChapter || 0);
    if (!failedChapter) {
        return '';
    }

    const generatedCount = Number(partial?.generatedCount || 0);
    const error = String(partial?.error || '').trim();
    const chapterLabel = `第 ${failedChapter} 章`;
    const summary = generatedCount > 0
        ? `批量生成已完成前 ${generatedCount} 章，${chapterLabel} 起中断。`
        : `${chapterLabel} 生成失败。`;

    return `
        <div class="short-story-warning-card">
            <div class="short-story-warning-text">${escapeHtml(summary)}</div>
            ${error ? `<div class="short-story-warning-text">原因：${escapeHtml(error)}</div>` : ''}
            <div class="short-story-action-row">
                <button id="short-story-resume-all-chapters" class="short-story-btn short-story-btn-warm" ${isShortStoryActionLoading('resume-all-chapters') ? 'disabled' : ''}>
                    ${getShortStoryButtonLabel('resume-all-chapters', `从第${failedChapter}章继续生成`, '继续生成中...')}
                </button>
            </div>
        </div>
    `;
}

function renderShortStoryScrollTools() {
    return `
        <div class="short-story-scroll-tools" aria-label="短篇页滚动快捷操作">
            <button type="button" id="short-story-scroll-top" class="short-story-scroll-btn short-story-btn" aria-label="回到顶部">
                <i class="ri-arrow-up-line" aria-hidden="true"></i>
                <span>回顶</span>
            </button>
            <button type="button" id="short-story-scroll-bottom" class="short-story-scroll-btn short-story-btn short-story-btn-warm" aria-label="跳到底部">
                <i class="ri-arrow-down-line" aria-hidden="true"></i>
                <span>置底</span>
            </button>
        </div>
    `;
}

function getShortStorySynopsisCards() {
    const workflow = getCurrentShortStoryWorkflow();
    if (!workflow || !Array.isArray(workflow.synopsis_candidates)) {
        return '';
    }

    return workflow.synopsis_candidates.map((item) => `
        <article class="short-story-choice-card ${workflow.selected_synopsis_index === item.index ? 'selected synopsis' : ''}">
            <div class="short-story-choice-head">
                <div>
                    <div class="short-story-choice-title">导语 ${item.index}</div>
                    <div class="short-story-choice-meta">${item.style ? escapeHtml(item.style) : '待选择风格'}</div>
                </div>
                <button
                    class="short-story-select-synopsis short-story-btn ${workflow.selected_synopsis_index === item.index ? 'short-story-btn-selected' : ''}"
                    data-selection="${item.index}"
                    ${isShortStoryActionLoading(`select-synopsis-${item.index}`) ? 'disabled' : ''}
                >
                    ${getShortStoryButtonLabel(`select-synopsis-${item.index}`, workflow.selected_synopsis_index === item.index ? '已选中' : '选择', '提交中...')}
                </button>
            </div>
            <div class="short-story-choice-content">${escapeHtml(item.content)}</div>
        </article>
    `).join('');
}

function getShortStoryFusionCards() {
    const workflow = getCurrentShortStoryWorkflow();
    if (!workflow || !Array.isArray(workflow.fusion_candidates)) {
        return '';
    }

    return workflow.fusion_candidates.map((item) => `
        <article class="short-story-choice-card ${workflow.selected_fusion_index === item.index ? 'selected fusion' : ''}">
            <div class="short-story-choice-head">
                <div>
                    <div class="short-story-choice-title">${escapeHtml(item.title || `方案 ${item.index}`)}</div>
                    <div class="short-story-choice-meta">${escapeHtml(item.route || '不同故事方向')}</div>
                </div>
                <button
                    class="short-story-select-fusion short-story-btn ${workflow.selected_fusion_index === item.index ? 'short-story-btn-selected short-story-btn-warm' : ''}"
                    data-selection="${item.index}"
                    ${isShortStoryActionLoading(`select-fusion-${item.index}`) ? 'disabled' : ''}
                >
                    ${getShortStoryButtonLabel(`select-fusion-${item.index}`, workflow.selected_fusion_index === item.index ? '已选中' : '选择本案', '提交中...')}
                </button>
            </div>
            ${item.hook ? `<div class="short-story-choice-content short-story-choice-content-compact"><strong>钩子：</strong>${escapeHtml(item.hook)}</div>` : ''}
            ${item.borrowed_structure ? `<div class="short-story-choice-content short-story-choice-content-compact"><strong>借鉴骨架：</strong>${escapeHtml(item.borrowed_structure)}</div>` : ''}
            ${item.refresh_plan ? `<div class="short-story-choice-content short-story-choice-content-compact"><strong>内容换新：</strong>${escapeHtml(item.refresh_plan)}</div>` : ''}
            <div class="short-story-choice-content">${escapeHtml(item.premise || item.content || '')}</div>
        </article>
    `).join('');
}

function renderShortStoryInputAnalysisSummary(workflow) {
    const analysis = workflow?.input_analysis || {};
    const summary = String(analysis?.summary || '').trim();
    const confidence = Number(workflow?.input_confidence || 0);
    const detectedTypes = Array.isArray(workflow?.detected_material_types) ? workflow.detected_material_types.filter(Boolean) : [];
    const keywords = Array.isArray(workflow?.keywords) ? workflow.keywords.filter(Boolean) : [];

    if (!summary && confidence <= 0 && detectedTypes.length === 0 && keywords.length === 0) {
        return '';
    }

    const confidenceLabel = confidence > 0 ? `${Math.round(confidence * 100)}%` : '待识别';
    const confidenceNote = confidence > 0 && confidence < 0.75
        ? '<div class="short-story-warning-text">这次系统抓得还不够准，建议先看一眼下方 3 个方案，再决定要不要重写输入。</div>'
        : '';

    return `
        <div class="short-story-panel">
            <div class="short-story-panel-title">系统理解结果</div>
            ${summary ? `<div class="short-story-review-tip">系统理解：${escapeHtml(summary)}</div>` : ''}
            <div class="short-story-hero-chips">
                <span class="short-story-chip">识别把握：${escapeHtml(confidenceLabel)}</span>
                ${detectedTypes.map((item) => `<span class="short-story-chip">素材类型：${escapeHtml(item)}</span>`).join('')}
            </div>
            ${keywords.length > 0 ? `<div class="short-story-review-tip">抓到的重点：${escapeHtml(keywords.join('、'))}</div>` : ''}
            ${confidenceNote}
        </div>
    `;
}

function getShortStorySuggestedSourceInput(workflow) {
    const rawInput = String(workflow?.raw_input || '').trim();
    const analysis = workflow?.input_analysis || {};
    const detectedTypes = Array.isArray(workflow?.detected_material_types) ? workflow.detected_material_types.filter(Boolean) : [];
    const keywords = Array.isArray(workflow?.keywords) ? workflow.keywords.filter(Boolean) : [];
    const borrowedHighlights = Array.isArray(analysis?.borrowed_highlights) ? analysis.borrowed_highlights.filter(Boolean) : [];
    const constraints = Array.isArray(analysis?.constraints) ? analysis.constraints.filter(Boolean) : [];
    const summary = String(analysis?.summary || '').trim();

    if (!rawInput && !summary && keywords.length === 0) {
        return '';
    }

    const parts = [];
    if (detectedTypes.length > 0) {
        parts.push(`素材类型：${detectedTypes.join('、')}`);
    }
    if (summary) {
        parts.push(`创作目标：${summary}`);
    }
    if (keywords.length > 0) {
        parts.push(`关键词：${keywords.join('、')}`);
    }
    if (borrowedHighlights.length > 0) {
        parts.push(`参考保留：${borrowedHighlights.join('、')}`);
    }
    if (constraints.length > 0) {
        parts.push(`额外要求：${constraints.join('、')}`);
    }
    if (rawInput) {
        parts.push(`原始素材：${rawInput}`);
    }
    return parts.join('\n');
}

function getShortStoryChapterEditors() {
    const workflow = getCurrentShortStoryWorkflow();
    if (!workflow || !Array.isArray(workflow.chapter_blueprints) || workflow.chapter_blueprints.length === 0) {
        return `
            <div class="short-story-empty">
                先生成并确认大纲，章节编辑区才会出现。
            </div>
        `;
    }

    const chapterMap = new Map((workflow.chapters || []).map((item) => [item.chapter_number, item]));
    const canGenerate = ['writing_content', 'quality_checking', 'coherence_reviewing', 'generating_titles', 'awaiting_title_selection', 'assembling_output', 'completed'].includes(workflow.state);

    return workflow.chapter_blueprints.map((blueprint) => {
        const chapter = chapterMap.get(blueprint.chapter_number) || {};
        const content = chapter.content || '';
        const chapterAction = `generate-chapter-${blueprint.chapter_number}`;
        const saveAction = `save-chapter-${blueprint.chapter_number}`;
        const isPlaceholder = isShortStoryPlaceholderBlueprint(blueprint);

        return `
            <article id="short-story-chapter-${blueprint.chapter_number}" class="short-story-chapter-card">
                <div class="short-story-chapter-top">
                    <div class="short-story-chapter-heading">
                        <div class="short-story-choice-title">第${blueprint.chapter_number}章</div>
                        <div class="short-story-choice-meta">${escapeHtml(blueprint.title || `第${blueprint.chapter_number}章`)}</div>
                    </div>
                    <div class="short-story-chapter-actions">
                        <button class="short-story-generate-chapter short-story-btn short-story-btn-primary" data-chapter="${blueprint.chapter_number}" ${canGenerate && !isShortStoryActionLoading(chapterAction) && !isPlaceholder ? '' : 'disabled'}>
                            ${getShortStoryButtonLabel(chapterAction, '生成本章', '生成中...')}
                        </button>
                        <button class="short-story-save-chapter short-story-btn" data-chapter="${blueprint.chapter_number}" ${!isShortStoryActionLoading(saveAction) && !isPlaceholder ? '' : 'disabled'}>
                            ${getShortStoryButtonLabel(saveAction, '保存编辑', '保存中...')}
                        </button>
                    </div>
                </div>
                ${renderShortStoryChapterMeta(blueprint)}
                <textarea class="short-story-chapter-content short-story-field short-story-textarea short-story-editor" data-chapter="${blueprint.chapter_number}" rows="12" placeholder="${isPlaceholder ? '当前章节缺少有效蓝图，请先回到大纲阶段补全规划。' : '点击“生成本章”后会写入正文，也可以手动修改。'}" ${isPlaceholder ? 'readonly' : ''}>${escapeHtml(content)}</textarea>
            </article>
        `;
    }).join('');
}

function renderShortStoryChapterMeta(blueprint = {}) {
    const isPlaceholder = isShortStoryPlaceholderBlueprint(blueprint);
    return `
        <div class="short-story-chapter-meta">
            ${isPlaceholder ? '<div class="short-story-warning-text">本章缺少有效章节蓝图，当前摘要/角色/事件信息不可作为可靠参考。建议回到大纲阶段重新生成或手动补全后，再重写本章。</div>' : ''}
            <div><strong>摘要：</strong>${escapeHtml(blueprint.summary || '待补充')}</div>
            <div><strong>出场角色：</strong>${escapeHtml(blueprint.characters || '待补充')}</div>
            <div><strong>核心事件：</strong>${escapeHtml(blueprint.core_event || '待补充')}</div>
            <div><strong>叙事功能：</strong>${escapeHtml(blueprint.narrative_function || '待补充')}</div>
            ${blueprint.emotion_point ? `<div><strong>情绪节点：</strong>${escapeHtml(blueprint.emotion_point)}</div>` : ''}
        </div>
    `;
}

function getShortStoryTitleCards() {
    const workflow = getCurrentShortStoryWorkflow();
    if (!workflow || !Array.isArray(workflow.title_candidates)) {
        return '';
    }

    return workflow.title_candidates.map((item) => `
        <article class="short-story-choice-card ${workflow.selected_title_index === item.index ? 'selected title' : ''}">
            <div class="short-story-choice-head">
                <div>
                    <div class="short-story-choice-title">《${escapeHtml(item.title)}》</div>
                    <div class="short-story-choice-meta">${escapeHtml(item.category || '未分类')}</div>
                    ${item.explanation ? `<div class="short-story-choice-content short-story-choice-content-compact">${escapeHtml(item.explanation)}</div>` : ''}
                </div>
                <button
                    class="short-story-select-title short-story-btn ${workflow.selected_title_index === item.index ? 'short-story-btn-selected short-story-btn-warm' : ''}"
                    data-selection="${item.index}"
                    ${isShortStoryActionLoading(`select-title-${item.index}`) ? 'disabled' : ''}
                >
                    ${getShortStoryButtonLabel(`select-title-${item.index}`, workflow.selected_title_index === item.index ? '已选中' : '选择', '提交中...')}
                </button>
            </div>
        </article>
    `).join('');
}

function renderShortStoryNavPanel() {
    const navList = document.getElementById('nav-list-container');
    if (!navList) return;

    const workflow = getCurrentShortStoryWorkflow();
    const chapters = workflow?.chapter_blueprints || [];
    navList.innerHTML = '';

    const panelEntry = document.createElement('button');
    panelEntry.type = 'button';
    panelEntry.className = `list-item short-story-nav-entry ${shortStoryState.activeView !== 'final' ? 'active' : ''}`;
    panelEntry.innerHTML = `
        <i class="ri-draft-line short-story-nav-entry-icon"></i>
        <span class="list-item-strong">创作面板</span>
    `;
    panelEntry.addEventListener('click', () => {
        shortStoryState.activeView = 'panel';
        saveShortStoryData();
        renderShortStoryInterface();
    });
    navList.appendChild(panelEntry);

    const settingsEntry = document.createElement('button');
    settingsEntry.type = 'button';
    settingsEntry.className = 'list-item short-story-nav-entry short-story-nav-entry--secondary short-story-nav-settings';
    settingsEntry.innerHTML = `
        <i class="ri-settings-4-line short-story-nav-entry-icon"></i>
        <span class="list-item-label">短篇设置</span>
    `;
    settingsEntry.addEventListener('click', () => {
        if (typeof switchModule === 'function') {
            switchModule('settings');
        }
        if (typeof loadSettingsTab === 'function') {
            loadSettingsTab('api');
        }
    });
    navList.appendChild(settingsEntry);

    const status = document.createElement('div');
    status.className = 'short-story-nav-status';
    status.innerHTML = `
        <div class="short-story-nav-status-title">当前进度</div>
        <div>阶段：${getShortStoryStageLabel(workflow?.state)}</div>
        <div>方案：${workflow?.fusion_candidates?.length || 0} / 3</div>
        <div>导语：${workflow?.synopsis_candidates?.length || 0} / 5</div>
        <div>章节：${workflow?.chapters?.length || 0} / ${workflow?.planned_chapters || 0}</div>
        <div>书名：${workflow?.title_candidates?.length || 0} / 5</div>
    `;
    navList.appendChild(status);

    if (workflow?.final_output && workflow?.selected_title) {
        const finalEntry = document.createElement('button');
        finalEntry.type = 'button';
        finalEntry.className = `list-item short-story-nav-entry short-story-nav-entry--secondary ${shortStoryState.activeView === 'final' ? 'active' : ''}`;
        finalEntry.innerHTML = `
            <i class="ri-book-2-line short-story-nav-entry-icon"></i>
            <span class="list-item-label">${escapeHtml(workflow.selected_title)}</span>
        `;
        finalEntry.addEventListener('click', () => {
            shortStoryState.activeView = 'final';
            saveShortStoryData();
            renderShortStoryInterface();
        });
        navList.appendChild(finalEntry);
    }

    if (chapters.length > 0) {
        const title = document.createElement('div');
        title.className = 'nav-section-label';
        title.textContent = '章节跳转';
        navList.appendChild(title);

        chapters.forEach((chapter) => {
            const item = document.createElement('button');
            item.type = 'button';
            item.className = 'list-item short-story-nav-chapter';
            item.innerHTML = `
                <i class="ri-book-open-line list-item-icon-muted"></i>
                <span class="list-item-label">第${chapter.chapter_number}章 ${escapeHtml(chapter.title || '')}</span>
            `;
            item.addEventListener('click', () => {
                shortStoryState.activeView = 'panel';
                shortStoryState.collapsedSections.chapter = false;
                shortStoryState.highlightSection = 'chapter';
                saveShortStoryData();
                renderShortStoryInterface().then(() => {
                    document.getElementById(`short-story-chapter-${chapter.chapter_number}`)?.scrollIntoView({ behavior: 'smooth', block: 'start' });
                    if (shortStoryHighlightTimer) {
                        clearTimeout(shortStoryHighlightTimer);
                    }
                    shortStoryHighlightTimer = setTimeout(() => {
                        shortStoryState.highlightSection = '';
                        saveShortStoryData();
                        document.getElementById('short-story-section-chapter')?.classList.remove('highlighted');
                    }, 2200);
                });
            });
            navList.appendChild(item);
        });
    }
}

async function renderShortStoryInterface() {
    await hydrateShortStoryProjectState();
    await loadGlobalApiConfigForShortStory();
    saveShortStoryData();

    const workflow = getCurrentShortStoryWorkflow();
    const activeView = shortStoryState.activeView === 'final' && workflow?.final_output ? 'final' : 'panel';
    if (shortStoryState.activeView !== activeView) {
        shortStoryState.activeView = activeView;
        saveShortStoryData();
    }

    const stage = getCurrentShortStoryStage();
    const currentSectionId = getShortStoryCurrentSectionId(stage);
    const focusedSectionId = shortStoryState.highlightSection || currentSectionId;
    const progress = getShortStoryProgressSummary(workflow);
    const hasWorkflow = Boolean(workflow);
    const sourceDraft = workflow?.raw_input || shortStoryState.draftSourceInput || shortStoryState.draftKeywords || '';
    const totalWordDraft = workflow?.target_total_words || shortStoryState.draftTotalWords || 5000;
    const recommendedChapterWords = getRecommendedShortStoryChapterWords(totalWordDraft);
    const chapterWordDraft = workflow?.chapter_word_target || (shortStoryState.draftChapterWordsCustomized ? shortStoryState.draftChapterWords : recommendedChapterWords);
    const categoryDraft = resolveShortStoryCategory(workflow?.category || workflow?.tone || shortStoryState.draftCategory);
    const plannedChapterCount = Number(workflow?.planned_chapters || 0);
    const actualOutlineChapterCount = Array.isArray(workflow?.chapter_blueprints) ? workflow.chapter_blueprints.length : 0;
    const existingChapterCount = Array.isArray(workflow?.chapters) ? workflow.chapters.length : 0;
    const hasCompleteDraft = plannedChapterCount > 0 && existingChapterCount >= plannedChapterCount;
    const hasPlaceholderBlueprints = Array.isArray(workflow?.chapter_blueprints)
        && workflow.chapter_blueprints.some((item) => isShortStoryPlaceholderBlueprint(item));
    const hasOutlineCountMismatch = plannedChapterCount > 0
        && actualOutlineChapterCount > 0
        && actualOutlineChapterCount !== plannedChapterCount;

    const flags = {
        hasWorkflow,
        canGenerateFusion: !workflow || ['analyzing_source_input', 'generating_fusion_options', 'awaiting_fusion_selection'].includes(stage),
        canGenerateSynopsis: ['generating_synopsis', 'awaiting_synopsis_selection'].includes(stage),
        canGenerateOutline: stage === 'generating_outline',
        canConfirmOutline: stage === 'awaiting_outline_confirm',
        canWriteContent: ['writing_content', 'quality_checking', 'coherence_reviewing', 'generating_titles', 'awaiting_title_selection', 'assembling_output', 'completed'].includes(stage),
        canQualityCheck: hasCompleteDraft && !hasPlaceholderBlueprints && ['writing_content', 'quality_checking', 'coherence_reviewing', 'generating_titles', 'awaiting_title_selection', 'assembling_output', 'completed'].includes(stage),
        canCoherenceReview: !hasPlaceholderBlueprints && ['coherence_reviewing', 'generating_titles', 'awaiting_title_selection', 'assembling_output', 'completed'].includes(stage),
        canGenerateTitles: ['generating_titles', 'awaiting_title_selection', 'assembling_output', 'completed'].includes(stage),
        canAssemble: ['assembling_output', 'completed'].includes(stage),
        hasPlaceholderBlueprints
    };

    if (activeView === 'final' && workflow?.selected_title) {
        updateBreadcrumbs(['短篇创作', workflow.selected_title]);
        ui.workspace.innerHTML = renderShortStoryFinalView(workflow);
        bindShortStoryEvents();
        renderShortStoryNavPanel();
        return;
    }

    updateBreadcrumbs(['短篇创作', '创作面板']);
    ui.workspace.innerHTML = `
        <div class="short-story-page">
            ${renderShortStoryScrollTools()}
            <div class="short-story-hero">
                <div class="short-story-hero-main">
                    <div class="short-story-kicker">固定创作流程</div>
                    <h1 class="short-story-title"><i class="ri-draft-line"></i>短篇创作</h1>
                    <div class="short-story-subtitle">按"统一输入 → 3个创意方案 → 导语 → 大纲 → 正文 → 质检 → 复审 → 书名 → 成稿"顺序推进。</div>
                    <div class="short-story-hero-chips">
                        <span class="short-story-chip">当前阶段：${escapeHtml(getShortStoryStageLabel(workflow?.state))}</span>
                        <span class="short-story-chip">主分类：${escapeHtml(categoryDraft)}</span>
                        <span class="short-story-chip">计划章节：${workflow?.planned_chapters || 0}</span>
                        <span class="short-story-chip">已写章节：${workflow?.chapters?.length || 0}</span>
                        <span class="short-story-chip">${formatShortStorySavedTime()}</span>
                    </div>
                </div>
                <div class="short-story-hero-side">
                    <div class="short-story-side-label">流程进度</div>
                    <div class="short-story-progress-number">${progress.completed}<span>/${progress.total}</span></div>
                    <div class="short-story-progress-bar">
                        <div class="short-story-progress-fill" style="width: ${(progress.completed / Math.max(progress.total, 1)) * 100}%;"></div>
                    </div>
                    <div class="short-story-side-note">${shortStoryState.loadingAction ? `当前操作：${getShortStoryLoadingMeta()?.text || '正在处理中...'}` : `当前聚焦步骤：${getShortStorySectionsMeta().find((item) => item.id === focusedSectionId)?.title || '创意方案'}`}</div>
                </div>
            </div>

            ${!shortStoryState.globalConfigured ? `
                <div class="short-story-alert">
                    请先在 <a href="#" id="short-story-open-api-settings" class="short-story-warning-link">设置 &gt; API配置</a> 中添加可用模型。
                </div>
            ` : ''}

            ${renderShortStoryLoadingBanner()}

            <div class="short-story-grid short-story-grid-top">
                <div class="short-story-panel">
                    <div class="short-story-panel-title">创作参数</div>
                    <div class="short-story-form-row short-story-form-row-2">
                        <div>
                            <label class="short-story-label">API配置</label>
                            <select id="short-story-api-config" class="short-story-field">
                                ${shortStoryState.apiConfigs.length === 0
                                    ? (shortStoryState.globalConfigured ? '<option value="">使用全局 API 配置</option>' : '<option value="">-- 请先配置API --</option>')
                                    : shortStoryState.apiConfigs.map((cfg) => `<option value="${escapeHtml(cfg.id)}" ${(cfg.id === (shortStoryState.selectedApiConfigId || shortStoryState.activeConfigId)) ? 'selected' : ''}>${escapeHtml(cfg.name)}</option>`).join('')}
                            </select>
                        </div>
                        <div>
                            <label class="short-story-label">模型</label>
                            <select id="short-story-model" class="short-story-field">
                                ${renderShortStoryModelOptions(shortStoryState.selectedApiConfigId || shortStoryState.activeConfigId, shortStoryState.selectedModel)}
                            </select>
                        </div>
                    </div>
                    <div class="short-story-form-row short-story-form-row-4">
                        <div>
                            <label class="short-story-label">统一创作输入</label>
                            <textarea id="short-story-keywords" rows="4" placeholder="直接粘贴灵感、例文、题材、词条或混合素材，例如：想写一个雨夜重逢却带悬疑反转的短篇；参考例文节奏偏强钩子；关键词：旧相机、失约、雨夜" class="short-story-field short-story-textarea">${escapeHtml(sourceDraft)}</textarea>
                        </div>
                        <div>
                            <label class="short-story-label">目标字数</label>
                            <input id="short-story-total-words" type="number" min="3000" max="50000" value="${totalWordDraft}" class="short-story-field">
                        </div>
                        <div>
                            <label class="short-story-label">每章字数</label>
                            <input id="short-story-chapter-words" type="number" min="500" max="3000" step="50" value="${chapterWordDraft}" class="short-story-field">
                        </div>
                        <div>
                            <label class="short-story-label">主分类</label>
                            ${renderShortStoryCategoryField(categoryDraft)}
                        </div>
                    </div>
                    <div class="short-story-action-row">
                        <button id="short-story-reset" class="short-story-btn short-story-btn-danger">清空当前流程</button>
                    </div>
                </div>
                <div class="short-story-panel">
                    <div class="short-story-panel-title">流程提醒</div>
                    <div class="short-story-tips">
                        <div>1. 直接输入任意创作素材，系统会自动识别并生成 3 个创意方案。</div>
                        <div>2. 每一步会直接调用当前所选模型。</div>
                        <div>3. 先选最满意的一版创意方案，再继续生成导语与大纲。</div>
                        <div>4. 大纲和章节都可以手改，系统会自动保存草稿。</div>
                        <div>5. 正文区支持一键生成全部章节，也支持逐章精修。</div>
                        <div>6. 顶部步骤条可直接跳转到任一流程区块。</div>
                        <div>7. 质检和复审支持先生成报告，再手动确认推进。</div>
                        <div>8. 当前每章目标字数：约 ${chapterWordDraft} 字，系统会按 ${Math.max(300, chapterWordDraft - 100)}~${Math.min(5000, chapterWordDraft + 100)} 字范围约束。</div>
                        ${(workflow?.warnings || []).map((item) => `<div class="short-story-warning-text">提示：${escapeHtml(item)}</div>`).join('')}
                    </div>
                </div>
            </div>

            <div class="short-story-stepbar">
                ${getShortStorySectionsMeta().map((item) => `
                    <button class="short-story-step-pill ${getShortStorySectionStatus(item.id, workflow, currentSectionId)}" data-step-target="${item.id}">
                        <i class="${item.icon}"></i>
                        <span>${item.step}. ${item.title}</span>
                        <strong>${getShortStorySectionBadge(item.id, workflow, currentSectionId)}</strong>
                    </button>
                `).join('')}
            </div>

            <div id="short-story-sections"></div>
        </div>
    `;

    renderShortStorySections(flags);
    bindShortStoryEvents();
    renderShortStoryNavPanel();
}

function renderShortStorySections(flags) {
    const container = document.getElementById('short-story-sections');
    const workflow = getCurrentShortStoryWorkflow();
    if (!container) return;

    const currentSectionId = getShortStoryCurrentSectionId();
    const sectionById = Object.fromEntries(getShortStorySectionsMeta().map((item) => [item.id, item]));
    const plannedChapterCount = Number(workflow?.planned_chapters || 0);
    const actualOutlineChapterCount = Array.isArray(workflow?.chapter_blueprints) ? workflow.chapter_blueprints.length : 0;
    const repairPlaceholderNumbers = getShortStoryRepairPlaceholderNumbers(workflow);
    const outlineRepairChecklistItems = getShortStoryOutlineRepairChecklist(workflow);
    const hasPendingOutlineRepair = outlineRepairChecklistItems.some((item) => !item.recovered);
    const hasOutlineCountMismatch = plannedChapterCount > 0
        && actualOutlineChapterCount > 0
        && actualOutlineChapterCount !== plannedChapterCount;
    const repairChapterLabel = repairPlaceholderNumbers.length > 0
        ? `第 ${repairPlaceholderNumbers.join('、')} 章`
        : '';
    const outlineRepairBanner = repairPlaceholderNumbers.length > 0 ? `
        <div class="short-story-warning-card">
            <div class="short-story-warning-text">已定位到异常章节：${escapeHtml(repairChapterLabel)}。</div>
            <div class="short-story-warning-text">这些章节此前缺少有效蓝图，正文已清理。请在下方大纲中补回这些章节，并核对总章节数后再点“确认大纲”。</div>
        </div>
    ` : '';
    const outlineRepairChecklist = renderShortStoryOutlineRepairChecklist(workflow);
    const outlineNote = repairPlaceholderNumbers.length > 0
        ? `当前需重点检查：${escapeHtml(repairChapterLabel)}。请确认大纲里已经补回这些章节。`
        : (actualOutlineChapterCount
            ? `计划章节：${plannedChapterCount || actualOutlineChapterCount}，当前大纲：${actualOutlineChapterCount}。确认前请先核对章节数是否匹配。`
            : `计划章节：${plannedChapterCount || 0}，生成大纲后会按计划拆分章节蓝图。`);

    const analysisSummary = workflow?.input_analysis?.summary || '';
    const analysisWarnings = Array.isArray(workflow?.input_analysis?.warnings) ? workflow.input_analysis.warnings : [];
    const analysisConfidence = Number(workflow?.input_confidence || 0);
    const suggestedInput = getShortStorySuggestedSourceInput(workflow);
    const fusionSection = renderShortStorySection(
        sectionById.fusion,
        workflow,
        currentSectionId,
        `
            <button id="short-story-generate-fusion" class="short-story-btn short-story-btn-primary" ${flags.canGenerateFusion && !isShortStoryActionLoading('generate-fusion') ? '' : 'disabled'}>
                ${getShortStoryButtonLabel('generate-fusion', (Array.isArray(workflow?.fusion_candidates) && workflow.fusion_candidates.length > 0) ? '再来 3 个方案' : '识别素材并生成 3 个方案', '生成中...')}
            </button>
        `,
        `
            ${analysisSummary ? renderShortStoryInputAnalysisSummary(workflow) : '<div class="short-story-empty">先输入创作素材，再点击“识别素材并生成 3 个方案”。</div>'}
            ${analysisConfidence > 0 && analysisConfidence < 0.75 && suggestedInput ? `
                <div class="short-story-warning-card">
                    <div class="short-story-warning-text">这段输入有点混，我先帮你整理成更清楚的写法。你可以直接替换后再生成。</div>
                    <textarea id="short-story-input-suggestion" rows="5" class="short-story-field short-story-textarea short-story-editor">${escapeHtml(suggestedInput)}</textarea>
                    <div class="short-story-action-row">
                        <button id="short-story-apply-input-suggestion" class="short-story-btn short-story-btn-warm">用这版替换输入</button>
                    </div>
                </div>
            ` : ''}
            ${analysisWarnings.map((item) => `<div class="short-story-warning-text">提示：${escapeHtml(item)}</div>`).join('')}
            <div class="short-story-card-grid">
                ${flags.hasWorkflow ? (getShortStoryFusionCards() || '<div class="short-story-empty">生成完成后，这里会展示 3 个不同风格的创意方案。</div>') : '<div class="short-story-empty">输入素材后，系统会自动识别并给出 3 个方案。</div>'}
            </div>
            ${renderShortStoryRawOutput('查看原始素材识别输出', shortStoryState.inputAnalysisRawOutput)}
            ${renderShortStoryRawOutput('查看原始创意方案输出', shortStoryState.fusionRawOutput)}
        `,
        workflow?.selected_fusion?.title ? `当前已选方案：${escapeHtml(workflow.selected_fusion.title)}` : '先选定一个创意方案，再继续生成导语。'
    );

    const synopsisSection = renderShortStorySection(
        sectionById.synopsis,
        workflow,
        currentSectionId,
        `
            <button id="short-story-generate-synopsis" class="short-story-btn short-story-btn-primary" ${flags.canGenerateSynopsis && !isShortStoryActionLoading('generate-synopsis') ? '' : 'disabled'}>
                ${getShortStoryButtonLabel('generate-synopsis', (workflow?.synopsis_candidates?.length || 0) > 0 ? '重新生成 5 条导语' : '生成 5 条导语', '生成中...')}
            </button>
        `,
        `
            <textarea id="short-story-synopsis-feedback" rows="2" placeholder="如果 5 条导语都不满意，可先填写修改方向再重新生成..." class="short-story-field short-story-textarea">${escapeHtml(shortStoryState.synopsisFeedback || '')}</textarea>
            <div class="short-story-card-grid">
                ${flags.hasWorkflow ? (getShortStorySynopsisCards() || '<div class="short-story-empty">选定创意方案后，点击"生成导语"即可在这里生成并选择导语。</div>') : '<div class="short-story-empty">请先完成创意方案选择。</div>'}
            </div>
            ${renderShortStoryRawOutput('查看原始导语输出', shortStoryState.synopsisRawOutput)}
        `,
        workflow?.selected_synopsis ? `已选导语：${escapeHtml(workflow.selected_synopsis.slice(0, 80))}${workflow.selected_synopsis.length > 80 ? '...' : ''}` : '先选创意方案，再生成候选导语。'
    );

    const outlineSection = renderShortStorySection(
        sectionById.outline,
        workflow,
        currentSectionId,
        `
            <button id="short-story-generate-outline" class="short-story-btn short-story-btn-primary" ${flags.canGenerateOutline && !isShortStoryActionLoading('generate-outline') ? '' : 'disabled'}>
                ${getShortStoryButtonLabel('generate-outline', '生成大纲', '生成中...')}
            </button>
            <button id="short-story-confirm-outline" class="short-story-btn short-story-btn-success" ${flags.canConfirmOutline && !hasPendingOutlineRepair && !hasOutlineCountMismatch && !isShortStoryActionLoading('confirm-outline') ? '' : 'disabled'}>
                ${getShortStoryButtonLabel('confirm-outline', '确认大纲', '确认中...')}
            </button>
            <button id="short-story-revise-outline" class="short-story-btn short-story-btn-warm" ${flags.canConfirmOutline && !isShortStoryActionLoading('revise-outline') ? '' : 'disabled'}>
                ${getShortStoryButtonLabel('revise-outline', '带意见重生成', '重生成中...')}
            </button>
        `,
        `
            ${outlineRepairBanner}
            <div id="short-story-outline-repair-checklist">${outlineRepairChecklist}</div>
            ${hasPendingOutlineRepair ? '<div class="short-story-review-tip short-story-warning-text">仍有缺失章节未补回，当前不可确认大纲。</div>' : ''}
            ${hasOutlineCountMismatch ? `<div class="short-story-review-tip short-story-warning-text">当前大纲为 ${actualOutlineChapterCount} 章，但按目标字数规划应为 ${plannedChapterCount} 章。请调整或重生成大纲后再确认。</div>` : ''}
            <textarea id="short-story-outline-feedback" rows="2" placeholder="如需重生成大纲，可填写调整方向..." class="short-story-field short-story-textarea">${escapeHtml(shortStoryState.outlineRevisionFeedback || workflow?.outline_feedback || '')}</textarea>
            <textarea id="short-story-outline-text" rows="12" placeholder="大纲会显示在这里，可继续手动调整。" class="short-story-field short-story-textarea short-story-editor">${escapeHtml(workflow?.outline_text || '')}</textarea>
            ${renderShortStoryRawOutput('查看原始大纲输出', shortStoryState.outlineRawOutput)}
        `,
        outlineNote
    );

    const chapterSection = renderShortStorySection(
        sectionById.chapter,
        workflow,
        currentSectionId,
        `
            <div class="short-story-inline-meta">已写 ${workflow?.chapters?.length || 0} / ${workflow?.planned_chapters || 0}</div>
            <button id="short-story-generate-all-chapters" class="short-story-btn short-story-btn-cyan" ${getCurrentShortStoryStage() === 'writing_content' && !isShortStoryActionLoading('generate-all-chapters') ? '' : 'disabled'}>
                ${getShortStoryButtonLabel('generate-all-chapters', (workflow?.chapters?.length || 0) > 0 ? '一键补全剩余正文' : '一键生成全部正文', '生成中...')}
            </button>
            ${flags.hasPlaceholderBlueprints ? `
                <button id="short-story-repair-outline-placeholders" class="short-story-btn short-story-btn-danger" ${!isShortStoryActionLoading('repair-outline-placeholders') ? '' : 'disabled'}>
                    ${getShortStoryButtonLabel('repair-outline-placeholders', '回退大纲并清理异常章节', '处理中...')}
                </button>
            ` : ''}
        `,
        flags.canWriteContent ? `${renderShortStoryPartialChapterResume()}${getShortStoryChapterEditors()}` : '<div class="short-story-empty">确认大纲后才会进入章节创作。</div>',
        workflow?.chapter_blueprints?.length ? '支持逐章生成、一键补全全部正文、手动修改和自动保存草稿。质检或复审后也可以对单章点“生成本章”重写；改动章节后，流程会回到待复检状态。' : '确认大纲后，这里会展开每一章的编辑面板。'
    );

    const qualitySection = renderShortStorySection(
        sectionById.quality,
        workflow,
        currentSectionId,
        `
            <button id="short-story-generate-quality" class="short-story-btn short-story-btn-violet" ${flags.canQualityCheck && !isShortStoryActionLoading('generate-quality') ? '' : 'disabled'}>
                ${getShortStoryButtonLabel('generate-quality', '生成质检报告', '生成中...')}
            </button>
            <button id="short-story-apply-simple-quality-fixes" class="short-story-btn short-story-btn-cyan" ${(shortStoryState.qualitySimpleFixes.length > 0) && !isShortStoryActionLoading('apply-simple-quality-fixes') ? '' : 'disabled'}>
                ${getShortStoryButtonLabel('apply-simple-quality-fixes', '一键修复简单问题', '修复中...')}
            </button>
            <button id="short-story-commit-quality" class="short-story-btn short-story-btn-success" ${flags.canQualityCheck && !isShortStoryActionLoading('commit-quality') ? '' : 'disabled'}>
                ${getShortStoryButtonLabel('commit-quality', '采纳并进入复审', '提交中...')}
            </button>
        `,
        `
            <textarea id="short-story-quality-report" rows="8" placeholder="质检报告会显示在这里。" class="short-story-field short-story-textarea short-story-editor">${escapeHtml(shortStoryState.qualityReportDraft || workflow?.quality_report || '')}</textarea>
            ${flags.hasPlaceholderBlueprints ? '<div class="short-story-review-tip short-story-warning-text">当前存在缺少有效大纲蓝图的章节，已禁止继续质检。请先回到大纲阶段补全章节规划，再重写这些章节。</div>' : ''}
            ${shortStoryState.qualitySimpleFixes.length > 0 ? `<div class="short-story-review-tip">检测到 ${shortStoryState.qualitySimpleFixes.length} 条可自动修复的简单问题，可先点“一键修复简单问题”节省 token。</div>` : ''}
            ${shortStoryState.qualitySimpleFixes.length > 0 ? `<div class="short-story-review-tip">${shortStoryState.qualitySimpleFixes.slice(0, 3).map((item) => `第${escapeHtml(String(item.chapter_number))}章：${escapeHtml(String(item.from_name || ''))} → ${escapeHtml(String(item.to_name || ''))}`).join('；')}${shortStoryState.qualitySimpleFixes.length > 3 ? '；…' : ''}</div>` : ''}
            ${shortStoryState.qualitySuggestedChapters.length > 0 ? '<div class="short-story-review-tip">检测到模型返回了修订后的完整正文，点击"采纳并进入复审"时会一并写回章节。</div>' : ''}
            <div class="short-story-review-tip">如发现问题章节，请手动修改对应章节内容，或点击对应章节的"生成本章"按钮重新生成。</div>
        `,
        shortStoryState.qualityPassedDraft ? '本轮质检已通过，可直接推进到复审。若仍想改章，可在正文区重生成/手改后，再重新点“生成质检报告”。' : '质检只输出问题报告，不会自动修改正文。请到正文区对问题章节手动修改，或点击“生成本章”重写，然后重新点“生成质检报告”。'
    );

    const coherenceSection = renderShortStorySection(
        sectionById.coherence,
        workflow,
        currentSectionId,
        `
            <button id="short-story-generate-coherence" class="short-story-btn short-story-btn-pink" ${flags.canCoherenceReview && !isShortStoryActionLoading('generate-coherence') ? '' : 'disabled'}>
                ${getShortStoryButtonLabel('generate-coherence', '生成复审报告', '生成中...')}
            </button>
            <button id="short-story-commit-coherence" class="short-story-btn short-story-btn-success" ${flags.canCoherenceReview && !isShortStoryActionLoading('commit-coherence') ? '' : 'disabled'}>
                ${getShortStoryButtonLabel('commit-coherence', '采纳并进入取名', '提交中...')}
            </button>
        `,
        `
            <textarea id="short-story-coherence-report" rows="8" placeholder="复审报告会显示在这里。" class="short-story-field short-story-textarea short-story-editor">${escapeHtml(shortStoryState.coherenceReportDraft || workflow?.coherence_report || '')}</textarea>
            ${flags.hasPlaceholderBlueprints ? '<div class="short-story-review-tip short-story-warning-text">当前存在缺少有效大纲蓝图的章节，已禁止继续复审。请先补全大纲并重写对应章节。</div>' : ''}
            ${shortStoryState.coherenceSuggestedChapters.length > 0 ? '<div class="short-story-review-tip">检测到模型返回了修订后的终版正文，点击"采纳并进入取名"时会一并写回章节。</div>' : ''}
            <div class="short-story-review-tip">如发现问题章节，请手动修改对应章节内容，或点击对应章节的"生成本章"按钮重新生成。</div>
        `,
        shortStoryState.coherencePassedDraft ? '复审已通过，下一步可以生成书名。若再改正文，流程会退回待质检，需要重新走“质检 → 复审”。' : '复审只输出问题报告，不会自动修改正文。请到正文区修改或重生成对应章节；改完后会退回待质检，再重新执行“生成质检报告”与“生成复审报告”。'
    );

    const titleSection = renderShortStorySection(
        sectionById.title,
        workflow,
        currentSectionId,
        `
            <button id="short-story-generate-titles" class="short-story-btn short-story-btn-warm" ${flags.canGenerateTitles && !isShortStoryActionLoading('generate-titles') ? '' : 'disabled'}>
                ${getShortStoryButtonLabel('generate-titles', '生成 5 个书名', '生成中...')}
            </button>
        `,
        `
            <textarea id="short-story-title-feedback" rows="2" placeholder="如果 5 个书名都不满意，可填写新的命名方向再重生..." class="short-story-field short-story-textarea">${escapeHtml(shortStoryState.titleFeedback || '')}</textarea>
            <div class="short-story-card-grid">
                ${getShortStoryTitleCards() || '<div class="short-story-empty">完成复审后可生成书名。</div>'}
            </div>
            ${renderShortStoryRawOutput('查看原始书名输出', shortStoryState.titleRawOutput)}
        `,
        workflow?.selected_title ? `当前已选书名：《${escapeHtml(workflow.selected_title)}》` : '可先给出命名方向，再批量生成书名候选。'
    );

    const assembleSection = renderShortStorySection(
        sectionById.assemble,
        workflow,
        currentSectionId,
        `
            <button id="short-story-assemble" class="short-story-btn short-story-btn-teal" ${flags.canAssemble && !isShortStoryActionLoading('assemble') ? '' : 'disabled'}>
                ${getShortStoryButtonLabel('assemble', '组装成稿并生成标签', '组装中...')}
            </button>
            ${renderShortStoryDeliverableActions(workflow)}
        `,
        `
            ${renderShortStoryTagSummary(workflow?.story_tags)}
            ${renderShortStoryManuscriptPreview(workflow, { compact: true })}
            ${renderShortStoryRawOutput('查看纯文本成稿', getCleanFinalOutput(workflow))}
        `,
        workflow?.final_output ? `当前成稿长度：${workflow.final_output.length.toLocaleString()} 字符。` : '确认书名后，系统会先判断主分类与内容标签，再组装最终成稿。'
    );

    container.innerHTML = `
        <div class="short-story-sections">
            ${fusionSection}
            ${synopsisSection}
            ${outlineSection}
            ${chapterSection}
            ${qualitySection}
            ${coherenceSection}
            ${titleSection}
            ${assembleSection}
        </div>
    `;
}

function renderShortStoryTagSummary(storyTags) {
    const mainCategory = storyTags?.main_category || '';
    const allTags = Array.isArray(storyTags?.all_tags) ? storyTags.all_tags : [];

    if (!mainCategory && allTags.length === 0) {
        return '';
    }

    return `
        <div class="short-story-tag-summary">
            ${mainCategory ? `<div class="short-story-tag-row"><strong>主分类</strong><span>${escapeHtml(mainCategory)}</span></div>` : ''}
            ${allTags.length > 0 ? `<div class="short-story-tag-row"><strong>内容标签</strong><span>${escapeHtml(allTags.join('、'))}</span></div>` : ''}
        </div>
    `;
}

function renderShortStoryDeliverableActions(workflow, options = {}) {
    const copyId = options.copyId || 'short-story-copy-final';
    const disabled = getCleanFinalOutput(workflow) ? '' : 'disabled';

    return `
        <div class="short-story-action-row">
            <button id="${copyId}" class="short-story-btn short-story-btn-success" ${disabled}><i class="ri-file-copy-line"></i>复制成稿</button>
            <button id="short-story-export-txt" class="short-story-btn" ${disabled}><i class="ri-file-text-line"></i>导出 TXT</button>
            <button id="short-story-export-md" class="short-story-btn" ${disabled}><i class="ri-markdown-line"></i>导出 MD</button>
            <button id="short-story-export-docx" class="short-story-btn" ${disabled}><i class="ri-file-word-line"></i>导出 DOCX</button>
        </div>
    `;
}

function renderShortStoryManuscriptPreview(workflow, options = {}) {
    if (!workflow?.final_output) {
        return '<div class="short-story-empty">完成组装后，这里会显示更适合阅读的成稿预览。</div>';
    }

    const title = workflow?.selected_title || '未命名成稿';
    const synopsis = String(workflow?.selected_synopsis || '').replace(/[（(][^）)]*向[）)]/g, '').trim();
    const chapters = Array.isArray(workflow?.chapters) ? workflow.chapters : [];
    const previewClass = options.compact ? ' short-story-manuscript-preview--compact' : '';
    const chapterCountLabel = chapters.length > 0 ? `展开正文（共 ${chapters.length} 章）` : '展开正文';

    return `
        <article class="short-story-manuscript-preview${previewClass}">
            <header class="short-story-manuscript-head">
                <div class="short-story-manuscript-kicker">成稿预览</div>
                <h2 class="short-story-manuscript-title">${escapeHtml(`《${title}》`)}</h2>
                ${synopsis ? `<p class="short-story-manuscript-synopsis">${escapeHtml(synopsis)}</p>` : ''}
            </header>
            ${chapters.length > 0 ? `
                <details class="short-story-manuscript-toggle" ${options.expandAll ? 'open' : ''}>
                    <summary class="short-story-manuscript-toggle-summary">${escapeHtml(chapterCountLabel)}</summary>
                    <div class="short-story-manuscript-body">
                        ${chapters.map((chapter) => `
                            <article class="short-story-manuscript-chapter">
                                <div class="short-story-manuscript-chapter-title">${escapeHtml(`${chapter.chapter_number}.`)}</div>
                                <div class="short-story-manuscript-content">${escapeHtml(cleanShortStoryDeliverableBlock(chapter.content || '', { chapterNumber: Number(chapter.chapter_number) }) || '')}</div>
                            </article>
                        `).join('')}
                    </div>
                </details>
            ` : `<div class="short-story-empty">当前还没有可展示的正文章节。</div>`}
        </article>
    `;
}

function renderShortStoryFinalChapters(workflow) {
    const chapters = Array.isArray(workflow?.chapters) ? workflow.chapters : [];
    const blueprintMap = new Map(
        (Array.isArray(workflow?.chapter_blueprints) ? workflow.chapter_blueprints : []).map((item) => [item.chapter_number, item])
    );

    if (chapters.length === 0) {
        return '<div class="short-story-empty">当前还没有可展示的正文。</div>';
    }

    return chapters.map((chapter) => `
        <article class="short-story-chapter-card">
            <div class="short-story-choice-title">${escapeHtml(`${chapter.chapter_number}. ${String(chapter.title || '').replace(/^\d+[.、]\s*/, '')}`.trim())}</div>
            ${renderShortStoryChapterMeta(blueprintMap.get(chapter.chapter_number) || {})}
            <div class="short-story-choice-content short-story-final-content">${escapeHtml(chapter.content || '')}</div>
        </article>
    `).join('');
}

function renderShortStoryFinalView(workflow) {
    return `
        <div class="short-story-page">
            ${renderShortStoryScrollTools()}
            <div class="short-story-hero">
                <div class="short-story-hero-main">
                    <div class="short-story-kicker">短篇成稿</div>
                    <h1 class="short-story-title"><i class="ri-book-2-line"></i>${escapeHtml(`《${workflow?.selected_title || '未命名成稿'}》`)}</h1>
                    <div class="short-story-subtitle">这里展示最终成稿的书名、标签、导语与正文，并支持导出为 txt / md / docx。</div>
                    <div class="short-story-hero-chips">
                        <span class="short-story-chip">主分类：${escapeHtml(workflow?.story_tags?.main_category || workflow?.category || '其他')}</span>
                        <span class="short-story-chip">正文章节：${workflow?.chapters?.length || 0}</span>
                        <span class="short-story-chip">成稿长度：${(workflow?.final_output || '').length.toLocaleString()} 字符</span>
                    </div>
                </div>
                <div class="short-story-hero-side">
                    <div class="short-story-side-label">成稿操作</div>
                    <div class="short-story-action-row short-story-final-return-row">
                        <button id="short-story-back-to-panel" class="short-story-btn short-story-btn-warm">
                            <i class="ri-arrow-left-line"></i>返回创作
                        </button>
                    </div>
                    ${renderShortStoryDeliverableActions(workflow, { copyId: 'short-story-final-copy' })}
                </div>
            </div>

            <div class="short-story-grid">
                <div class="short-story-panel">
                    <div class="short-story-panel-title">标签信息</div>
                    ${renderShortStoryTagSummary(workflow?.story_tags)}
                </div>
                <div class="short-story-panel">
                    <div class="short-story-panel-title">导语</div>
                    <div class="short-story-choice-content short-story-final-content">${escapeHtml((workflow?.selected_synopsis || '暂无导语').replace(/[（(][^）)]*向[）)]/g, ''))}</div>
                </div>
                <div class="short-story-panel">
                    <div class="short-story-panel-title">正文</div>
                    ${renderShortStoryManuscriptPreview(workflow)}
                </div>
            </div>
        </div>
    `;
}

window.renderShortStoryLoadingBanner = renderShortStoryLoadingBanner;
window.renderShortStoryRawOutput = renderShortStoryRawOutput;
window.resolveShortStoryCategory = resolveShortStoryCategory;
window.getShortStoryMainCategoryOptions = getShortStoryMainCategoryOptions;
window.renderShortStoryCategoryField = renderShortStoryCategoryField;
window.renderShortStorySection = renderShortStorySection;
window.renderShortStoryPartialChapterResume = renderShortStoryPartialChapterResume;
window.renderShortStoryScrollTools = renderShortStoryScrollTools;
window.getShortStoryFusionCards = getShortStoryFusionCards;
window.renderShortStoryInputAnalysisSummary = renderShortStoryInputAnalysisSummary;
window.getShortStorySuggestedSourceInput = getShortStorySuggestedSourceInput;
window.getShortStorySynopsisCards = getShortStorySynopsisCards;
window.getShortStoryChapterEditors = getShortStoryChapterEditors;
window.renderShortStoryChapterMeta = renderShortStoryChapterMeta;
window.getShortStoryTitleCards = getShortStoryTitleCards;
window.renderShortStoryNavPanel = renderShortStoryNavPanel;
window.renderShortStoryInterface = renderShortStoryInterface;
window.renderShortStorySections = renderShortStorySections;
window.renderShortStoryTagSummary = renderShortStoryTagSummary;
window.renderShortStoryDeliverableActions = renderShortStoryDeliverableActions;
window.renderShortStoryManuscriptPreview = renderShortStoryManuscriptPreview;
window.renderShortStoryFinalChapters = renderShortStoryFinalChapters;
window.renderShortStoryFinalView = renderShortStoryFinalView;
