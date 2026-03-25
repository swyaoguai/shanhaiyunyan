/**
 * 文思Agent - 小说转剧本事件层
 */

async function withNovelToScriptLoading(actionName, task) {
    novelToScriptState.loadingAction = actionName;
    saveNovelToScriptData();
    await renderNovelToScriptInterface();

    try {
        return await task();
    } finally {
        novelToScriptState.loadingAction = '';
        saveNovelToScriptData();
        await renderNovelToScriptInterface();
    }
}

async function copyNovelToScriptResult() {
    const text = novelToScriptState.result?.formatted_text || novelToScriptState.result?.full_text || '';
    if (!text.trim()) {
        showToast('当前没有可复制的结果', 'error');
        return;
    }

    try {
        await navigator.clipboard.writeText(text);
        showToast('剧本结果已复制到剪贴板');
    } catch (e) {
        showToast('复制失败，请手动复制', 'error');
    }
}

function syncNovelToScriptConfigDraft() {
    novelToScriptState.config = {
        ...novelToScriptState.config,
        script_style: document.getElementById('novel-to-script-style')?.value || novelToScriptState.config.script_style,
        convert_mode: document.getElementById('novel-to-script-convert-mode')?.value || novelToScriptState.config.convert_mode,
        scene_density: document.getElementById('novel-to-script-scene-density')?.value || novelToScriptState.config.scene_density,
        dialogue_ratio: document.getElementById('novel-to-script-dialogue-ratio')?.value || novelToScriptState.config.dialogue_ratio,
        human_name_strategy: document.getElementById('novel-to-script-human-name-strategy')?.value || novelToScriptState.config.human_name_strategy,
        keep_voice_style: Boolean(document.getElementById('novel-to-script-keep-voice-style')?.checked)
    };
}

function bindNovelToScriptAutosave() {
    document.getElementById('novel-to-script-source-text')?.addEventListener('input', (event) => {
        novelToScriptState.sourceType = 'paste';
        novelToScriptState.sourceText = event.target.value;
        novelToScriptState.analysis = null;
        novelToScriptState.conversionPlan = null;
        markNovelToScriptDraftSaved();
    });

    document.getElementById('novel-to-script-result-editor')?.addEventListener('input', (event) => {
        syncNovelToScriptResultFromText(event.target.value);
        markNovelToScriptDraftSaved();
    });

    [
        'novel-to-script-style',
        'novel-to-script-convert-mode',
        'novel-to-script-scene-density',
        'novel-to-script-dialogue-ratio',
        'novel-to-script-human-name-strategy',
        'novel-to-script-keep-voice-style'
    ].forEach((id) => {
        document.getElementById(id)?.addEventListener(id === 'novel-to-script-keep-voice-style' ? 'change' : 'change', () => {
            syncNovelToScriptConfigDraft();
            markNovelToScriptDraftSaved();
        });
    });
}

function bindNovelToScriptEvents() {
    bindNovelToScriptAutosave();

    document.getElementById('novel-to-script-open-api-settings')?.addEventListener('click', (event) => {
        event.preventDefault();
        switchModule('settings');
        loadSettingsTab('api');
    });

    document.getElementById('novel-to-script-api-config')?.addEventListener('change', (event) => {
        novelToScriptState.selectedApiConfigId = event.target.value;
        const modelSelect = document.getElementById('novel-to-script-model');
        if (modelSelect) {
            modelSelect.innerHTML = renderNovelToScriptModelOptions(novelToScriptState.selectedApiConfigId, '');
            novelToScriptState.selectedModel = modelSelect.value || '';
        }
        saveNovelToScriptData();
    });

    document.getElementById('novel-to-script-model')?.addEventListener('change', (event) => {
        novelToScriptState.selectedModel = event.target.value;
        saveNovelToScriptData();
    });

    document.getElementById('novel-to-script-import-trigger')?.addEventListener('click', () => {
        document.getElementById('novel-to-script-import-input')?.click();
    });

    document.getElementById('novel-to-script-import-input')?.addEventListener('change', async (event) => {
        const file = event.target.files?.[0];
        if (!file) return;

        try {
            await withNovelToScriptLoading('importing', async () => {
                await importNovelToScriptFile(file);
                showToast(`已导入 ${file.name}`);
            });
        } catch (e) {
            showToast(e.message || '导入失败', 'error');
        } finally {
            event.target.value = '';
        }
    });

    document.getElementById('novel-to-script-convert')?.addEventListener('click', async () => {
        syncNovelToScriptConfigDraft();
        try {
            await withNovelToScriptLoading('converting', async () => {
                await convertNovelToScript();
                showToast('小说内容已转换为场景台本');
            });
        } catch (e) {
            showToast(e.message || '转换失败', 'error');
        }
    });

    document.querySelectorAll('[data-retry-batch]').forEach((button) => {
        button.addEventListener('click', async () => {
            const batchNumber = Number(button.dataset.retryBatch || 0);
            if (!batchNumber) return;
            syncNovelToScriptConfigDraft();
            try {
                await withNovelToScriptLoading(`reconverting-batch-${batchNumber}`, async () => {
                    await reconvertNovelToScriptBatch(batchNumber);
                    showToast(`第 ${batchNumber} 批已重新转换`);
                });
            } catch (e) {
                showToast(e.message || '批次重转失败', 'error');
            }
        });
    });

    document.getElementById('novel-to-script-copy-result')?.addEventListener('click', async () => {
        await copyNovelToScriptResult();
    });

    document.getElementById('novel-to-script-open-result')?.addEventListener('click', async () => {
        if (!novelToScriptState.result?.formatted_text) return;
        novelToScriptState.activeView = 'result';
        saveNovelToScriptData();
        await renderNovelToScriptInterface();
    });

    document.getElementById('novel-to-script-back-workbench')?.addEventListener('click', async () => {
        novelToScriptState.activeView = 'workbench';
        saveNovelToScriptData();
        await renderNovelToScriptInterface();
    });

    document.querySelectorAll('[data-scene-index]').forEach((button) => {
        button.addEventListener('click', async () => {
            novelToScriptState.selectedSceneIndex = Number(button.dataset.sceneIndex || 0);
            saveNovelToScriptData();
            await renderNovelToScriptInterface();
        });
    });

    document.querySelectorAll('[data-result-tab]').forEach((button) => {
        button.addEventListener('click', async () => {
            novelToScriptState.resultTab = button.dataset.resultTab || 'text';
            saveNovelToScriptData();
            await renderNovelToScriptInterface();
        });
    });

    document.getElementById('novel-to-script-export-txt')?.addEventListener('click', async () => {
        try {
            await exportNovelToScriptFile('txt');
            showToast('已导出 TXT 文件');
        } catch (e) {
            showToast(e.message || '导出失败', 'error');
        }
    });

    document.getElementById('novel-to-script-export-md')?.addEventListener('click', async () => {
        try {
            await exportNovelToScriptFile('md');
            showToast('已导出 MD 文件');
        } catch (e) {
            showToast(e.message || '导出失败', 'error');
        }
    });

    document.getElementById('novel-to-script-export-docx')?.addEventListener('click', async () => {
        try {
            await exportNovelToScriptFile('docx');
            showToast('已导出 DOCX 文件');
        } catch (e) {
            showToast(e.message || '导出失败', 'error');
        }
    });

    document.getElementById('novel-to-script-reset')?.addEventListener('click', async () => {
        await resetNovelToScriptProjectState();
        showToast('当前转换草稿已清空');
        await renderNovelToScriptInterface();
    });
}
