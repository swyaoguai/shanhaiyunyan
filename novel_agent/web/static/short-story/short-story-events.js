/**
 * 山海·云烟 - 短篇创作事件层
 */

let shortStoryLoadingHeartbeatTimer = null;

function resolveShortStoryCategoryInput(value, fallback = '其他') {
    if (typeof normalizeShortStoryCategory === 'function') {
        return normalizeShortStoryCategory(value, fallback);
    }
    const fallbackText = String(fallback || '其他').replace(/\s+/g, ' ').trim() || '其他';
    const category = String(value || '').replace(/\s+/g, ' ').trim();
    return (category || fallbackText).slice(0, 32) || '其他';
}

function syncShortStoryLoadingHeartbeat() {
    if (shortStoryLoadingHeartbeatTimer) {
        clearInterval(shortStoryLoadingHeartbeatTimer);
        shortStoryLoadingHeartbeatTimer = null;
    }

    const titleEl = document.getElementById('short-story-loading-title');
    const hintEl = document.getElementById('short-story-loading-hint');
    if (!titleEl || !hintEl || !shortStoryState.loadingAction) {
        return;
    }

    const refresh = () => {
        const meta = getShortStoryLoadingMeta();
        if (!meta) return;
        titleEl.textContent = meta.text;
        hintEl.textContent = meta.hint;
    };

    refresh();
    shortStoryLoadingHeartbeatTimer = setInterval(refresh, 1000);
}

async function ensureShortStoryWorkflowForSourceInput() {
    let workflow = getCurrentShortStoryWorkflow();
    if (workflow) {
        return workflow;
    }

    const sourceInput = document.getElementById('short-story-keywords')?.value || shortStoryState.draftSourceInput || '';
    const keywords = parseShortStoryKeywords();
    if (!String(sourceInput || '').trim()) {
        showToast('请先输入创作素材', 'error');
        return null;
    }

    const totalWords = parseInt(document.getElementById('short-story-total-words')?.value || '5000', 10);
    const recommendedChapterWords = getRecommendedShortStoryChapterWords(totalWords);
    const chapterWords = parseInt(document.getElementById('short-story-chapter-words')?.value || `${recommendedChapterWords}`, 10);
    const category = resolveShortStoryCategoryInput(document.getElementById('short-story-category')?.value);

    shortStoryState.draftSourceInput = sourceInput;
    shortStoryState.draftKeywords = sourceInput;
    shortStoryState.draftTotalWords = totalWords;
    shortStoryState.draftChapterWords = Number.isFinite(chapterWords) ? chapterWords : recommendedChapterWords;
    shortStoryState.draftCategory = category;
    resetShortStoryWorkflowArtifacts();

    const result = await callShortStoryApi('/api/short-story/workflow/start', {
        keywords,
        source_input: sourceInput,
        target_total_words: totalWords,
        chapter_word_target: shortStoryState.draftChapterWordsCustomized ? shortStoryState.draftChapterWords : null,
        category
    });

    workflow = result?.data?.workflow || getCurrentShortStoryWorkflow();
    return workflow || null;
}

async function withShortStoryLoading(actionName, task) {
    shortStoryState.loadingAction = actionName;
    shortStoryState.loadingStartedAt = Date.now();
    saveShortStoryData();
    await renderShortStoryInterface();

    try {
        return await task();
    } finally {
        shortStoryState.loadingAction = '';
        shortStoryState.loadingStartedAt = 0;
        shortStoryState.batchGenerationProgress = null;
        saveShortStoryData();
        await renderShortStoryInterface();
    }
}

async function runShortStoryBatchChapterGeneration(actionName, startingChapter = null) {
    syncShortStoryWorkflowDrafts();
    const workflow = getCurrentShortStoryWorkflow();
    if (!workflow) return;

    const planned = Number(workflow.planned_chapters || 0);
    const existingNumbers = new Set((workflow.chapters || []).map((item) => Number(item.chapter_number || 0)));
    const pendingChapters = [];
    for (let chapterNumber = 1; chapterNumber <= planned; chapterNumber += 1) {
        if (startingChapter && chapterNumber < startingChapter) {
            continue;
        }
        if (!existingNumbers.has(chapterNumber)) {
            pendingChapters.push(chapterNumber);
        }
    }

    if (pendingChapters.length === 0) {
        shortStoryState.partialChapterGeneration = null;
        saveShortStoryData();
        showToast('当前没有待生成的章节');
        return;
    }

    shortStoryState.partialChapterGeneration = null;
    shortStoryState.batchGenerationProgress = {
        total: pendingChapters.length,
        completed: 0,
        currentChapter: pendingChapters[0]
    };
    saveShortStoryData();
    await renderShortStoryInterface();

    let generatedCount = 0;
    for (const chapterNumber of pendingChapters) {
        shortStoryState.batchGenerationProgress = {
            total: pendingChapters.length,
            completed: generatedCount,
            currentChapter: chapterNumber
        };
        saveShortStoryData();
        await renderShortStoryInterface();

        const result = await callShortStoryApi('/api/short-story/chapter/generate', {
            workflow: getCurrentShortStoryWorkflow(),
            chapter_number: chapterNumber,
            api_config_id: getSelectedApiConfigIdForShortStory(),
            model: document.getElementById('short-story-model')?.value || shortStoryState.selectedModel
        });

        if (!result) {
            shortStoryState.partialChapterGeneration = {
                failedChapter: chapterNumber,
                error: '生成中断，请检查网络或接口状态后继续。',
                generatedCount
            };
            saveShortStoryData();
            await renderShortStoryInterface();
            return;
        }

        generatedCount += 1;
    }

    shortStoryState.partialChapterGeneration = null;
    saveShortStoryData();
    showToast(actionName === 'resume-all-chapters' ? '剩余章节已继续生成完成' : '剩余章节已按顺序生成');
}

function bindShortStoryDraftAutosave() {
    const bindInput = (selector, handler, eventName = 'input') => {
        document.querySelectorAll(selector).forEach((element) => {
            element.addEventListener(eventName, () => {
                handler(element);
                markShortStoryDraftSaved();
            });
        });
    };

    bindInput('#short-story-keywords', (element) => {
        shortStoryState.draftSourceInput = element.value;
        shortStoryState.draftKeywords = element.value;
        const workflow = getCurrentShortStoryWorkflow();
        if (workflow) {
            workflow.raw_input = element.value;
            workflow.legacy_keywords = parseShortStoryKeywords();
            workflow.keywords = parseShortStoryKeywords();
        }
    });

    bindInput('#short-story-total-words', (element) => {
        const value = parseInt(element.value || '5000', 10);
        shortStoryState.draftTotalWords = Number.isFinite(value) ? value : 5000;
        const recommendedChapterWords = getRecommendedShortStoryChapterWords(shortStoryState.draftTotalWords);
        if (!shortStoryState.draftChapterWordsCustomized) {
            shortStoryState.draftChapterWords = recommendedChapterWords;
            const chapterWordInput = document.getElementById('short-story-chapter-words');
            if (chapterWordInput) {
                chapterWordInput.value = `${recommendedChapterWords}`;
            }
        }
        const workflow = getCurrentShortStoryWorkflow();
        if (workflow) {
            workflow.target_total_words = shortStoryState.draftTotalWords;
            if (!shortStoryState.draftChapterWordsCustomized) {
                workflow.custom_chapter_word_target = null;
                workflow.chapter_word_target = recommendedChapterWords;
                workflow.chapter_word_min = Math.max(300, recommendedChapterWords - 100);
                workflow.chapter_word_max = Math.min(5000, recommendedChapterWords + 100);
            }
        }
    }, 'change');

    bindInput('#short-story-chapter-words', (element) => {
        const recommendedChapterWords = getRecommendedShortStoryChapterWords(shortStoryState.draftTotalWords);
        const value = parseInt(element.value || `${recommendedChapterWords}`, 10);
        shortStoryState.draftChapterWords = Number.isFinite(value) ? value : recommendedChapterWords;
        shortStoryState.draftChapterWordsCustomized = shortStoryState.draftChapterWords !== recommendedChapterWords;
        const workflow = getCurrentShortStoryWorkflow();
        if (workflow) {
            const resolvedChapterWords = shortStoryState.draftChapterWordsCustomized ? shortStoryState.draftChapterWords : recommendedChapterWords;
            workflow.custom_chapter_word_target = shortStoryState.draftChapterWordsCustomized ? resolvedChapterWords : null;
            workflow.chapter_word_target = resolvedChapterWords;
            workflow.chapter_word_min = Math.max(300, resolvedChapterWords - 100);
            workflow.chapter_word_max = Math.min(5000, resolvedChapterWords + 100);
        }
    }, 'change');

    bindInput('#short-story-category', (element) => {
        shortStoryState.draftCategory = resolveShortStoryCategoryInput(element.value);
        const workflow = getCurrentShortStoryWorkflow();
        if (workflow) {
            workflow.category = shortStoryState.draftCategory;
            workflow.tone = shortStoryState.draftCategory;
        }
    });

    bindInput('#short-story-synopsis-feedback', (element) => {
        shortStoryState.synopsisFeedback = element.value;
    });

    bindInput('#short-story-outline-feedback', (element) => {
        shortStoryState.outlineRevisionFeedback = element.value;
    });

    bindInput('#short-story-outline-text', (element) => {
        const workflow = getCurrentShortStoryWorkflow();
        if (workflow) {
            workflow.outline_text = element.value;
        }
        const checklistContainer = document.getElementById('short-story-outline-repair-checklist');
        if (checklistContainer) {
            checklistContainer.innerHTML = renderShortStoryOutlineRepairChecklist(workflow, element.value);
        }
    });

    bindInput('.short-story-chapter-content', () => {
        const workflow = getCurrentShortStoryWorkflow();
        if (workflow) {
            workflow.chapters = collectShortStoryChaptersFromEditor();
        }
    });

    bindInput('#short-story-quality-report', (element) => {
        shortStoryState.qualityReportDraft = element.value;
    });

    bindInput('#short-story-coherence-report', (element) => {
        shortStoryState.coherenceReportDraft = element.value;
    });

    bindInput('#short-story-title-feedback', (element) => {
        shortStoryState.titleFeedback = element.value;
    });
}

function scrollToShortStorySection(sectionId) {
    document.getElementById(`short-story-section-${sectionId}`)?.scrollIntoView({ behavior: 'smooth', block: 'start' });
}

function getShortStoryScrollContainer() {
    return document.getElementById('main-view') || ui?.workspace || document.scrollingElement || document.documentElement;
}

function scrollShortStoryViewport(position) {
    const container = getShortStoryScrollContainer();
    if (!container) return;

    const targetTop = position === 'bottom'
        ? Math.max(0, (container.scrollHeight || document.documentElement.scrollHeight || 0) - (container.clientHeight || window.innerHeight || 0))
        : 0;

    if (typeof container.scrollTo === 'function') {
        container.scrollTo({ top: targetTop, behavior: 'smooth' });
        return;
    }

    container.scrollTop = targetTop;
}

async function copyShortStoryFinalText() {
    const text = getCleanFinalOutput(getCurrentShortStoryWorkflow());
    if (!text.trim()) {
        showToast('当前没有可复制的成稿', 'error');
        return;
    }

    try {
        await navigator.clipboard.writeText(text);
        showToast('成稿已复制到剪贴板');
    } catch (e) {
        showToast('复制失败，请手动复制', 'error');
    }
}

function bindShortStoryEvents() {
    syncShortStoryLoadingHeartbeat();
    bindShortStoryDraftAutosave();

    document.getElementById('short-story-open-api-settings')?.addEventListener('click', (event) => {
        event.preventDefault();
        switchModule('settings');
        loadSettingsTab('api');
    });

    document.getElementById('short-story-api-config')?.addEventListener('change', (event) => {
        shortStoryState.selectedApiConfigId = event.target.value;
        const modelSelect = document.getElementById('short-story-model');
        if (modelSelect) {
            modelSelect.innerHTML = renderShortStoryModelOptions(shortStoryState.selectedApiConfigId, '');
            shortStoryState.selectedModel = modelSelect.value || '';
        }
        saveShortStoryData();
    });

    document.getElementById('short-story-model')?.addEventListener('change', (event) => {
        shortStoryState.selectedModel = event.target.value;
        saveShortStoryData();
    });

    document.querySelectorAll('[data-toggle-section]').forEach((button) => {
        button.addEventListener('click', () => {
            const sectionId = button.dataset.toggleSection;
            if (sectionId) {
                toggleShortStorySection(sectionId);
            }
        });
    });

    document.querySelectorAll('[data-step-target]').forEach((button) => {
        button.addEventListener('click', async () => {
            const sectionId = button.dataset.stepTarget;
            if (!sectionId) return;

            shortStoryState.highlightSection = sectionId;
            shortStoryState.collapsedSections[sectionId] = false;
            saveShortStoryData();
            await renderShortStoryInterface();
            scrollToShortStorySection(sectionId);

            if (shortStoryHighlightTimer) {
                clearTimeout(shortStoryHighlightTimer);
            }
            shortStoryHighlightTimer = setTimeout(() => {
                shortStoryState.highlightSection = '';
                saveShortStoryData();
                document.getElementById(`short-story-section-${sectionId}`)?.classList.remove('highlighted');
            }, 2200);
        });
    });

    document.getElementById('short-story-reset')?.addEventListener('click', async () => {
        if (!confirm('确定清空当前短篇流程吗？')) return;
        await resetShortStoryProjectState();
        await renderShortStoryInterface();
        showToast('当前流程已清空');
    });

    document.getElementById('short-story-generate-fusion')?.addEventListener('click', async (event) => {
        if (event.target.disabled || isShortStoryActionLoading('generate-fusion')) {
            return;
        }

        syncShortStoryWorkflowDrafts();
        await withShortStoryLoading('generate-fusion', async () => {
            let workflow = getCurrentShortStoryWorkflow();
            if (!workflow) {
                workflow = await ensureShortStoryWorkflowForSourceInput();
                if (!workflow) return;
            }

            if (!['analyzing_source_input', 'generating_fusion_options', 'awaiting_fusion_selection'].includes(workflow.state || '')) {
                showToast('当前流程已进入后续阶段；如需重选方案，请先清空当前流程。', 'warning');
                return;
            }

            const analyzeResult = await callShortStoryApi('/api/short-story/input/analyze', {
                workflow,
                api_config_id: getSelectedApiConfigIdForShortStory(),
                model: document.getElementById('short-story-model')?.value || shortStoryState.selectedModel
            });
            if (!analyzeResult) return;
            shortStoryState.inputAnalysisRawOutput = analyzeResult?.data?.raw_output || '';
            workflow = analyzeResult?.data?.workflow || getCurrentShortStoryWorkflow();
            if (!workflow) return;

            const fusionResult = await callShortStoryApi('/api/short-story/fusion-options/generate', {
                workflow,
                api_config_id: getSelectedApiConfigIdForShortStory(),
                model: document.getElementById('short-story-model')?.value || shortStoryState.selectedModel
            }, '创意方案已生成');
            shortStoryState.fusionRawOutput = fusionResult?.data?.raw_output || '';
            saveShortStoryData();
            await renderShortStoryInterface();
        });
    });

    document.querySelectorAll('.short-story-select-fusion').forEach((button) => {
        button.addEventListener('click', async () => {
            await withShortStoryLoading(`select-fusion-${button.dataset.selection}`, async () => {
                await callShortStoryApi('/api/short-story/fusion-options/select', {
                    workflow: getCurrentShortStoryWorkflow(),
                    selection: parseInt(button.dataset.selection || '0', 10)
                }, '已选定创意方案');
            });
        });
    });

    document.getElementById('short-story-apply-input-suggestion')?.addEventListener('click', () => {
        const suggestion = document.getElementById('short-story-input-suggestion')?.value?.trim() || '';
        const target = document.getElementById('short-story-keywords');
        if (!suggestion || !target) {
            showToast('当前没有可替换的输入建议', 'error');
            return;
        }
        target.value = suggestion;
        shortStoryState.draftSourceInput = suggestion;
        shortStoryState.draftKeywords = suggestion;
        markShortStoryDraftSaved();
        showToast('已用整理后的输入建议替换原始素材');
    });

    document.getElementById('short-story-generate-synopsis')?.addEventListener('click', async (event) => {
        if (event.target.disabled || isShortStoryActionLoading('generate-synopsis')) {
            return;
        }
        
        syncShortStoryWorkflowDrafts();
        await withShortStoryLoading('generate-synopsis', async () => {
            let workflow = getCurrentShortStoryWorkflow();
            if (!workflow?.selected_fusion) {
                showToast('请先生成并选择一个创意方案', 'error');
                return;
            }

            const result = await callShortStoryApi('/api/short-story/synopsis/generate', {
                workflow,
                api_config_id: getSelectedApiConfigIdForShortStory(),
                model: document.getElementById('short-story-model')?.value || shortStoryState.selectedModel,
                feedback: shortStoryState.synopsisFeedback || ''
            }, '导语已生成');
            shortStoryState.synopsisRawOutput = result?.data?.raw_output || '';
            saveShortStoryData();
            await renderShortStoryInterface();
        });
    });

    document.querySelectorAll('.short-story-select-synopsis').forEach((button) => {
        button.addEventListener('click', async () => {
            await withShortStoryLoading(`select-synopsis-${button.dataset.selection}`, async () => {
                await callShortStoryApi('/api/short-story/synopsis/select', {
                    workflow: getCurrentShortStoryWorkflow(),
                    selection: parseInt(button.dataset.selection || '0', 10)
                }, '已选定导语方案');
            });
        });
    });

    document.getElementById('short-story-generate-outline')?.addEventListener('click', async () => {
        await withShortStoryLoading('generate-outline', async () => {
            const result = await callShortStoryApi('/api/short-story/outline/generate', {
                workflow: getCurrentShortStoryWorkflow(),
                api_config_id: getSelectedApiConfigIdForShortStory(),
                model: document.getElementById('short-story-model')?.value || shortStoryState.selectedModel
            }, '大纲已生成');
            shortStoryState.outlineRawOutput = result?.data?.raw_output || '';
            saveShortStoryData();
            await renderShortStoryInterface();
        });
    });

    document.getElementById('short-story-confirm-outline')?.addEventListener('click', async () => {
        syncShortStoryWorkflowDrafts();
        const workflow = getCurrentShortStoryWorkflow();
        const currentOutlineText = document.getElementById('short-story-outline-text')?.value || workflow?.outline_text || '';
        const pendingRepairItems = getShortStoryOutlineRepairChecklist(workflow, currentOutlineText).filter((item) => !item.recovered);
        if (pendingRepairItems.length > 0) {
            const label = pendingRepairItems.map((item) => item.chapter_number).join('、');
            showToast(`请先补回第 ${label} 章的大纲蓝图后再确认大纲`, 'error');
            shortStoryState.highlightSection = 'outline';
            shortStoryState.collapsedSections.outline = false;
            saveShortStoryData();
            scrollToShortStorySection('outline');
            return;
        }
        await withShortStoryLoading('confirm-outline', async () => {
            await callShortStoryApi('/api/short-story/outline/confirm', {
                workflow: getCurrentShortStoryWorkflow(),
                approved: true,
                feedback: ''
            }, '大纲已确认');
        });
    });

    document.getElementById('short-story-revise-outline')?.addEventListener('click', async () => {
        syncShortStoryWorkflowDrafts();
        await withShortStoryLoading('revise-outline', async () => {
            const feedback = shortStoryState.outlineRevisionFeedback || '请根据上面的意见重写大纲。';
            await callShortStoryApi('/api/short-story/outline/confirm', {
                workflow: getCurrentShortStoryWorkflow(),
                approved: false,
                feedback
            });
            const result = await callShortStoryApi('/api/short-story/outline/generate', {
                workflow: getCurrentShortStoryWorkflow(),
                api_config_id: getSelectedApiConfigIdForShortStory(),
                model: document.getElementById('short-story-model')?.value || shortStoryState.selectedModel
            }, '已根据意见重新生成大纲');
            shortStoryState.outlineRawOutput = result?.data?.raw_output || '';
            saveShortStoryData();
            await renderShortStoryInterface();
        });
    });

    document.getElementById('short-story-repair-outline-placeholders')?.addEventListener('click', async () => {
        syncShortStoryWorkflowDrafts();
        await withShortStoryLoading('repair-outline-placeholders', async () => {
            const feedback = shortStoryState.outlineRevisionFeedback || '请补全缺失章节的有效蓝图，并确保总章节数与大纲规划一致。';
            const result = await callShortStoryApi('/api/short-story/outline/repair-placeholders', {
                workflow: getCurrentShortStoryWorkflow(),
                feedback
            }, '已回退到大纲确认阶段，并清理异常章节');
            if (!result) return;
            shortStoryState.highlightSection = 'outline';
            shortStoryState.collapsedSections.outline = false;
            saveShortStoryData();
            await renderShortStoryInterface();
            scrollToShortStorySection('outline');
        });
    });

    document.querySelectorAll('.short-story-generate-chapter').forEach((button) => {
        button.addEventListener('click', async () => {
            syncShortStoryWorkflowDrafts();
            await withShortStoryLoading(`generate-chapter-${button.dataset.chapter}`, async () => {
                await callShortStoryApi('/api/short-story/chapter/generate', {
                    workflow: getCurrentShortStoryWorkflow(),
                    chapter_number: parseInt(button.dataset.chapter || '0', 10),
                    api_config_id: getSelectedApiConfigIdForShortStory(),
                    model: document.getElementById('short-story-model')?.value || shortStoryState.selectedModel
                }, `已生成第${button.dataset.chapter}章`);
            });
        });
    });

    document.getElementById('short-story-generate-all-chapters')?.addEventListener('click', async () => {
        await withShortStoryLoading('generate-all-chapters', async () => {
            await runShortStoryBatchChapterGeneration('generate-all-chapters');
        });
    });

    document.getElementById('short-story-resume-all-chapters')?.addEventListener('click', async () => {
        const failedChapter = Number(shortStoryState.partialChapterGeneration?.failedChapter || 0);
        if (!failedChapter) {
            showToast('当前没有可继续生成的失败章节', 'error');
            return;
        }

        await withShortStoryLoading('resume-all-chapters', async () => {
            await runShortStoryBatchChapterGeneration('resume-all-chapters', failedChapter);
        });
    });

    document.querySelectorAll('.short-story-save-chapter').forEach((button) => {
        button.addEventListener('click', async () => {
            const chapterNumber = parseInt(button.dataset.chapter || '0', 10);
            const workflow = getCurrentShortStoryWorkflow();
            const blueprint = (workflow?.chapter_blueprints || []).find((item) => item.chapter_number === chapterNumber);
            const content = document.querySelector(`.short-story-chapter-content[data-chapter="${chapterNumber}"]`)?.value?.trim() || '';
            if (!content) {
                showToast('章节内容不能为空', 'error');
                return;
            }
            await withShortStoryLoading(`save-chapter-${chapterNumber}`, async () => {
                await callShortStoryApi('/api/short-story/chapter/save', {
                    workflow,
                    chapter_number: chapterNumber,
                    title: blueprint?.title || `第${chapterNumber}章`,
                    content
                }, `已保存第${chapterNumber}章`);
            });
        });
    });

    document.getElementById('short-story-generate-quality')?.addEventListener('click', async () => {
        syncShortStoryWorkflowDrafts();
        const workflow = getCurrentShortStoryWorkflow();
        if (!workflow) return;
        workflow.chapters = collectShortStoryChaptersFromEditor();

        await withShortStoryLoading('generate-quality', async () => {
            const result = await generateShortStoryReviewDraft('/api/short-story/quality-check/generate', workflow, '质检报告已生成');
            shortStoryState.qualityReportDraft = result?.data?.report || '';
            shortStoryState.qualityPassedDraft = Boolean(result?.data?.passed);
            shortStoryState.qualitySuggestedChapters = Array.isArray(result?.data?.revised_chapters) ? result.data.revised_chapters : [];
            shortStoryState.qualitySimpleFixes = Array.isArray(result?.data?.simple_fixes) ? result.data.simple_fixes : [];
            saveShortStoryData();
            await renderShortStoryInterface();
        });
    });

    document.getElementById('short-story-apply-simple-quality-fixes')?.addEventListener('click', async () => {
        await withShortStoryLoading('apply-simple-quality-fixes', async () => {
            const report = document.getElementById('short-story-quality-report')?.value || shortStoryState.qualityReportDraft;
            const result = await callShortStoryApi('/api/short-story/quality-check/apply-simple-fixes', {
                workflow: getCurrentShortStoryWorkflow(),
                report,
                chapters: collectShortStoryChaptersFromEditor()
            }, '');
            if (!result) return;
            const fixedCount = Number(result?.data?.fixed_count || 0);
            const replacementCount = Number(result?.data?.replacement_count || 0);
            shortStoryState.qualityReportDraft = '';
            shortStoryState.qualityPassedDraft = false;
            shortStoryState.qualitySuggestedChapters = [];
            shortStoryState.qualitySimpleFixes = [];
            saveShortStoryData();
            await renderShortStoryInterface();
            showToast(`已自动修复 ${fixedCount} 条简单问题，共替换 ${replacementCount} 处内容，请重新生成质检报告`);
        });
    });

    document.getElementById('short-story-commit-quality')?.addEventListener('click', async () => {
        await withShortStoryLoading('commit-quality', async () => {
            const report = document.getElementById('short-story-quality-report')?.value || shortStoryState.qualityReportDraft;
            await callShortStoryApi('/api/short-story/quality-check/commit', {
                workflow: getCurrentShortStoryWorkflow(),
                report,
                passed: shortStoryState.qualityPassedDraft
                    || shortStoryState.qualitySuggestedChapters.length > 0
                    || canShortStoryForceAdvance(report),
                chapters: shortStoryState.qualitySuggestedChapters.length > 0 ? shortStoryState.qualitySuggestedChapters : collectShortStoryChaptersFromEditor()
            }, '已进入复审阶段');
            shortStoryState.qualitySuggestedChapters = [];
            shortStoryState.qualitySimpleFixes = [];
        });
    });

    document.getElementById('short-story-generate-coherence')?.addEventListener('click', async () => {
        const workflow = getCurrentShortStoryWorkflow();
        if (!workflow) return;
        workflow.chapters = collectShortStoryChaptersFromEditor();

        await withShortStoryLoading('generate-coherence', async () => {
            const result = await generateShortStoryReviewDraft('/api/short-story/coherence-review/generate', workflow, '复审报告已生成');
            shortStoryState.coherenceReportDraft = result?.data?.report || '';
            shortStoryState.coherencePassedDraft = Boolean(result?.data?.passed);
            shortStoryState.coherenceSuggestedChapters = Array.isArray(result?.data?.final_chapters) ? result.data.final_chapters : [];
            saveShortStoryData();
            await renderShortStoryInterface();
        });
    });

    document.getElementById('short-story-commit-coherence')?.addEventListener('click', async () => {
        await withShortStoryLoading('commit-coherence', async () => {
            const report = document.getElementById('short-story-coherence-report')?.value || shortStoryState.coherenceReportDraft;
            await callShortStoryApi('/api/short-story/coherence-review/commit', {
                workflow: getCurrentShortStoryWorkflow(),
                report,
                passed: shortStoryState.coherencePassedDraft
                    || shortStoryState.coherenceSuggestedChapters.length > 0
                    || canShortStoryForceAdvance(report),
                chapters: shortStoryState.coherenceSuggestedChapters.length > 0 ? shortStoryState.coherenceSuggestedChapters : collectShortStoryChaptersFromEditor()
            }, '已进入取名阶段');
            shortStoryState.coherenceSuggestedChapters = [];
        });
    });

    document.getElementById('short-story-generate-titles')?.addEventListener('click', async () => {
        syncShortStoryWorkflowDrafts();
        await withShortStoryLoading('generate-titles', async () => {
            const result = await callShortStoryApi('/api/short-story/title/generate', {
                workflow: getCurrentShortStoryWorkflow(),
                api_config_id: getSelectedApiConfigIdForShortStory(),
                model: document.getElementById('short-story-model')?.value || shortStoryState.selectedModel,
                feedback: shortStoryState.titleFeedback
            }, '书名候选已生成');
            shortStoryState.titleRawOutput = result?.data?.raw_output || '';
            saveShortStoryData();
            await renderShortStoryInterface();
        });
    });

    document.querySelectorAll('.short-story-select-title').forEach((button) => {
        button.addEventListener('click', async () => {
            await withShortStoryLoading(`select-title-${button.dataset.selection}`, async () => {
                await callShortStoryApi('/api/short-story/title/select', {
                    workflow: getCurrentShortStoryWorkflow(),
                    selection: parseInt(button.dataset.selection || '0', 10)
                }, '已选定书名');
            });
        });
    });

    document.getElementById('short-story-assemble')?.addEventListener('click', async () => {
        const workflow = getCurrentShortStoryWorkflow();
        if (!workflow) return;
        workflow.chapters = collectShortStoryChaptersFromEditor();

        await withShortStoryLoading('assemble', async () => {
            await callShortStoryApi('/api/short-story/assemble', {
                workflow,
                api_config_id: getSelectedApiConfigIdForShortStory(),
                model: document.getElementById('short-story-model')?.value || shortStoryState.selectedModel
            }, '成稿已组装');
        });
    });

    document.getElementById('short-story-copy-final')?.addEventListener('click', copyShortStoryFinalText);
    document.getElementById('short-story-final-copy')?.addEventListener('click', copyShortStoryFinalText);
    document.getElementById('short-story-back-to-panel')?.addEventListener('click', async () => {
        shortStoryState.activeView = 'panel';
        saveShortStoryData();
        await renderShortStoryInterface();
    });
    document.getElementById('short-story-export-txt')?.addEventListener('click', () => exportShortStoryFile('txt'));
    document.getElementById('short-story-export-md')?.addEventListener('click', () => exportShortStoryFile('md'));
    document.getElementById('short-story-export-docx')?.addEventListener('click', () => exportShortStoryFile('docx'));
    document.getElementById('short-story-scroll-top')?.addEventListener('click', () => scrollShortStoryViewport('top'));
    document.getElementById('short-story-scroll-bottom')?.addEventListener('click', () => scrollShortStoryViewport('bottom'));
}

window.ensureShortStoryWorkflowForSourceInput = ensureShortStoryWorkflowForSourceInput;
window.ensureShortStoryWorkflowForSynopsis = ensureShortStoryWorkflowForSourceInput;
window.withShortStoryLoading = withShortStoryLoading;
window.bindShortStoryDraftAutosave = bindShortStoryDraftAutosave;
window.scrollToShortStorySection = scrollToShortStorySection;
window.getShortStoryScrollContainer = getShortStoryScrollContainer;
window.scrollShortStoryViewport = scrollShortStoryViewport;
window.copyShortStoryFinalText = copyShortStoryFinalText;
window.bindShortStoryEvents = bindShortStoryEvents;
