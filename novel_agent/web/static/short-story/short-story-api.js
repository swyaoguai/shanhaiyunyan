/**
 * 山海·云烟 - 短篇创作接口层
 */

async function loadGlobalApiConfigForShortStory() {
    try {
        const configsData = await apiCall('/api/api-configs', 'GET');
        const globalConfig = await apiCall('/api/global-config', 'GET');

        shortStoryState.apiConfigs = configsData.configs || [];
        shortStoryState.activeConfigId = configsData.active_config_id || '';
        shortStoryState.globalModel = globalConfig?.model || '';
        shortStoryState.globalConfigured = shortStoryState.apiConfigs.length > 0 || Boolean(globalConfig?.is_configured);

        if (!shortStoryState.selectedApiConfigId && shortStoryState.activeConfigId) {
            shortStoryState.selectedApiConfigId = shortStoryState.activeConfigId;
        }

        if (!shortStoryState.selectedModel) {
            const config = shortStoryState.apiConfigs.find((item) => item.id === shortStoryState.selectedApiConfigId);
            shortStoryState.selectedModel = config?.models?.[0] || shortStoryState.globalModel || '';
        }
    } catch (e) {
        console.error('[ShortStory] 加载API配置失败:', e);
        shortStoryState.apiConfigs = [];
        shortStoryState.activeConfigId = '';
        shortStoryState.globalModel = '';
        shortStoryState.globalConfigured = false;
    }
}

async function callShortStoryApi(url, data, successMessage) {
    try {
        const result = await apiCall(url, 'POST', data);
        if (result?.data?.workflow) {
            shortStoryState.workflow = repairShortStoryWorkflowBlueprints(result.data.workflow);
        }
        if (
            url.includes('/api/short-story/chapter/generate')
            || url.includes('/api/short-story/chapter/save')
            || url.includes('/api/short-story/quality-check/rewrite-issue-chapters')
        ) {
            resetShortStoryReviewArtifacts();
        }
        if (url.includes('/api/short-story/workflow/rollback')) {
            const resetRollbackArtifacts = typeof window.resetShortStoryArtifactsForRollback === 'function'
                ? window.resetShortStoryArtifactsForRollback
                : function () {};
            resetRollbackArtifacts(result?.data?.target_step || data?.target_step || 'previous');
            shortStoryState.highlightSection = result?.data?.target_step || '';
            if (shortStoryState.highlightSection) {
                shortStoryState.collapsedSections[shortStoryState.highlightSection] = false;
            }
        }
        if (url.includes('/api/short-story/chapter/generate-all')) {
            if (result?.data?.partial) {
                shortStoryState.partialChapterGeneration = {
                    failedChapter: Number(result?.data?.failed_chapter || 0),
                    error: result?.data?.error || '',
                    generatedCount: Array.isArray(result?.data?.generated_chapters) ? result.data.generated_chapters.length : 0,
                };
            } else {
                shortStoryState.partialChapterGeneration = null;
            }
        } else if (
            url.includes('/api/short-story/chapter/generate')
            || url.includes('/api/short-story/chapter/save')
            || url.includes('/api/short-story/quality-check/apply-simple-fixes')
            || url.includes('/api/short-story/quality-check/rewrite-issue-chapters')
            || url.includes('/api/short-story/quality-check/commit')
            || url.includes('/api/short-story/coherence-review/commit')
        ) {
            shortStoryState.partialChapterGeneration = null;
        }
        saveShortStoryData();
        await persistShortStoryProjectStateNow();
        if (result?.data?.partial) {
            const generatedCount = Array.isArray(result?.data?.generated_chapters) ? result.data.generated_chapters.length : 0;
            const failedChapter = result?.data?.failed_chapter;
            const error = result?.data?.error || '后续章节生成失败';
            showToast(`已生成 ${generatedCount} 章，第 ${failedChapter} 章起中断：${error}`, 'warning');
        } else if (successMessage) {
            showToast(successMessage);
        }
        await renderShortStoryInterface();
        return result;
    } catch (e) {
        showToast(e.message || '短篇接口调用失败', 'error');
        return null;
    }
}

async function generateShortStoryReviewDraft(url, workflow, successMessage) {
    try {
        const result = await apiCall(url, 'POST', {
            workflow,
            api_config_id: getSelectedApiConfigIdForShortStory(),
            model: document.getElementById('short-story-model')?.value || shortStoryState.selectedModel
        });
        if (result?.data?.workflow) {
            shortStoryState.workflow = repairShortStoryWorkflowBlueprints(result.data.workflow);
        }
        saveShortStoryData();
        await persistShortStoryProjectStateNow();
        await renderShortStoryInterface();
        if (successMessage) {
            showToast(successMessage);
        }
        return result;
    } catch (e) {
        showToast(e.message || '短篇接口调用失败', 'error');
        return null;
    }
}

function clearShortStoryRollbackArtifactsFallback(targetStep) {
    const stepOrder = ['fusion', 'synopsis', 'outline', 'chapter', 'quality', 'coherence', 'title', 'assemble'];
    const index = stepOrder.indexOf(targetStep);
    if (index < 0) return;

    if (index <= stepOrder.indexOf('fusion')) {
        shortStoryState.synopsisRawOutput = '';
        shortStoryState.synopsisFeedback = '';
    }
    if (index <= stepOrder.indexOf('synopsis')) {
        shortStoryState.outlineRawOutput = '';
        shortStoryState.outlineRevisionFeedback = '';
    }
    if (index <= stepOrder.indexOf('outline')) {
        shortStoryState.partialChapterGeneration = null;
    }
    if (index <= stepOrder.indexOf('chapter')) {
        shortStoryState.qualityReportDraft = '';
        shortStoryState.qualityPassedDraft = false;
        shortStoryState.qualitySimpleFixes = [];
        shortStoryState.qualityRewriteTargets = [];
        shortStoryState.qualitySuggestedChapters = [];
    }
    if (index <= stepOrder.indexOf('quality')) {
        shortStoryState.coherenceReportDraft = '';
        shortStoryState.coherencePassedDraft = false;
        shortStoryState.coherenceSuggestedChapters = [];
    }
    if (index <= stepOrder.indexOf('coherence')) {
        shortStoryState.titleRawOutput = '';
        shortStoryState.titleFeedback = '';
    }
    if (index <= stepOrder.indexOf('title')) {
        shortStoryState.activeView = 'panel';
    }
}

async function rollbackShortStoryWorkflow(targetStep, feedback = '') {
    try {
        const requestApi = typeof window.apiCall === 'function' ? window.apiCall : apiCall;
        const persistNow = typeof window.persistShortStoryProjectStateNow === 'function'
            ? window.persistShortStoryProjectStateNow
            : persistShortStoryProjectStateNow;
        const result = await requestApi('/api/short-story/workflow/rollback', 'POST', {
            workflow: getCurrentShortStoryWorkflow(),
            target_step: targetStep,
            feedback
        });
        if (result?.data?.workflow) {
            const repairWorkflow = typeof window.repairShortStoryWorkflowBlueprints === 'function'
                ? window.repairShortStoryWorkflowBlueprints
                : (workflow) => workflow;
            shortStoryState.workflow = repairWorkflow(result.data.workflow);
        }
        const resetRollbackArtifacts = typeof window.resetShortStoryArtifactsForRollback === 'function'
            ? window.resetShortStoryArtifactsForRollback
            : clearShortStoryRollbackArtifactsFallback;
        resetRollbackArtifacts(result?.data?.target_step || targetStep);
        saveShortStoryData();
        await persistNow();
        return result;
    } catch (e) {
        showToast(e.message || '短篇接口调用失败', 'error');
        return null;
    }
}

async function exportShortStoryFile(format) {
    const workflow = getCurrentShortStoryWorkflow();
    if (!workflow?.final_output) {
        showToast('请先完成成稿组装后再导出', 'error');
        return;
    }

    try {
        if (format === 'txt' || format === 'md') {
            const content = getCleanFinalOutput(workflow);
            if (!content.trim()) {
                throw new Error('当前没有可导出的成稿');
            }
            const blob = new Blob([content], {
                type: format === 'md' ? 'text/markdown;charset=utf-8' : 'text/plain;charset=utf-8'
            });
            const url = URL.createObjectURL(blob);
            const anchor = document.createElement('a');
            anchor.href = url;
            anchor.download = getShortStoryExportFilename(format);
            document.body.appendChild(anchor);
            anchor.click();
            document.body.removeChild(anchor);
            URL.revokeObjectURL(url);
            showToast(`已导出 ${format.toUpperCase()} 文件`);
            return;
        }

        const response = await fetch(`/api/short-story/export?format=${encodeURIComponent(format)}`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ workflow })
        });

        if (!response.ok) {
            const payload = await response.json().catch(() => ({}));
            throw new Error(payload.detail || payload.error || '导出失败');
        }

        const blob = await response.blob();
        const url = URL.createObjectURL(blob);
        const anchor = document.createElement('a');
        anchor.href = url;
        anchor.download = getShortStoryExportFilename(format);
        document.body.appendChild(anchor);
        anchor.click();
        document.body.removeChild(anchor);
        URL.revokeObjectURL(url);
        showToast(`已导出 ${format.toUpperCase()} 文件`);
    } catch (e) {
        showToast(e.message || '导出失败', 'error');
    }
}

window.loadGlobalApiConfigForShortStory = loadGlobalApiConfigForShortStory;
window.callShortStoryApi = callShortStoryApi;
window.generateShortStoryReviewDraft = generateShortStoryReviewDraft;
window.clearShortStoryRollbackArtifactsFallback = clearShortStoryRollbackArtifactsFallback;
window.rollbackShortStoryWorkflow = rollbackShortStoryWorkflow;
window.exportShortStoryFile = exportShortStoryFile;
