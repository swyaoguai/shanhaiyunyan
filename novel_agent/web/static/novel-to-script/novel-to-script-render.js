/**
 * 山海·云烟 - 小说转剧本渲染层
 */

function formatNovelToScriptSavedTime() {
    if (!novelToScriptState.draftSavedAt) {
        return '草稿未保存';
    }
    const diff = Math.max(0, Math.round((Date.now() - novelToScriptState.draftSavedAt) / 1000));
    if (diff < 10) return '刚刚已保存';
    if (diff < 60) return `${diff} 秒前已保存`;
    const minutes = Math.round(diff / 60);
    if (minutes < 60) return `${minutes} 分钟前已保存`;
    return '草稿已保存';
}

function renderNovelToScriptSelectOptions(items, selectedValue) {
    return (items || []).map((item) => `
        <option value="${escapeHtml(item.value)}" ${selectedValue === item.value ? 'selected' : ''}>${escapeHtml(item.label)}</option>
    `).join('');
}

function getNovelToScriptLoadingMeta() {
    if (!novelToScriptState.loadingAction) {
        return null;
    }

    if (novelToScriptState.loadingAction === 'importing') {
        return {
            text: '正在导入小说',
            hint: '系统会先解析正文、统计字数并识别章节结构。'
        };
    }

    if (novelToScriptState.loadingAction.startsWith('reconverting-batch-')) {
        const batchNumber = Number(novelToScriptState.loadingAction.replace('reconverting-batch-', '') || 0);
        return {
            text: `正在重转第 ${batchNumber} 批`,
            hint: '系统只会重新请求当前这一批，并在完成后自动回写整份剧本。'
        };
    }

    const strategySummary = novelToScriptState.analysis || getNovelToScriptStrategySummary();
    const plan = novelToScriptState.conversionPlan;
    const batchCount = Number(plan?.batch_count || strategySummary.estimatedBatches || 1);
    const modeLabel = plan?.resolved_mode_label || strategySummary.recommendedModeLabel || '单次转换';
    return {
        text: batchCount > 1 ? `正在执行${modeLabel}` : '正在转换剧本',
        hint: batchCount > 1
            ? `预计共 ${batchCount} 批，当前请求会按批顺序处理并在完成后自动合并。`
            : '当前文本会在一次请求内完成转换并生成分场景剧本。'
    };
}

function renderNovelToScriptLoadingBanner() {
    const meta = getNovelToScriptLoadingMeta();
    if (!meta) {
        return '';
    }

    return `
        <div class="novel-to-script-loading-banner" role="status" aria-live="polite">
            <i class="ri-loader-4-line novel-to-script-loading-spinner" aria-hidden="true"></i>
            <div>
                <div class="novel-to-script-loading-title">${escapeHtml(meta.text)}</div>
                <div class="novel-to-script-loading-hint">${escapeHtml(meta.hint)}</div>
            </div>
        </div>
    `;
}

function renderNovelToScriptSourceSummary() {
    const wordCount = getNovelToScriptWordCount();
    const chapterCount = getNovelToScriptChapterCount();
    return `
        <div class="novel-to-script-summary-grid">
            <div class="novel-to-script-summary-item">
                <span class="novel-to-script-summary-label">输入来源</span>
                <strong>${novelToScriptState.sourceFilename ? escapeHtml(novelToScriptState.sourceFilename) : '手动粘贴'}</strong>
            </div>
            <div class="novel-to-script-summary-item">
                <span class="novel-to-script-summary-label">字数</span>
                <strong>${wordCount.toLocaleString()}</strong>
            </div>
            <div class="novel-to-script-summary-item">
                <span class="novel-to-script-summary-label">章节</span>
                <strong>${chapterCount}</strong>
            </div>
        </div>
    `;
}

function renderNovelToScriptBatchSummary() {
    const batches = Array.isArray(novelToScriptState.result?.batch_summaries) ? novelToScriptState.result.batch_summaries : [];
    if (batches.length <= 1) {
        return '';
    }

    return `
        <section class="novel-to-script-batch-panel">
            <div class="novel-to-script-panel-title">批次摘要</div>
            <div class="novel-to-script-panel-copy">长篇内容会先分批改写，再自动合并为一份完整剧本。这里保留每批执行摘要，方便你判断哪里需要回头精修。</div>
            <div class="novel-to-script-card-grid">
                ${batches.map((batch) => `
                    <article class="novel-to-script-info-card">
                        <div class="novel-to-script-info-title">第 ${Number(batch.batch_number || 0)} 批</div>
                        <div class="novel-to-script-info-copy">${escapeHtml(batch.title || '未命名批次')}</div>
                        <div class="novel-to-script-info-meta">字数：${Number(batch.word_count || 0).toLocaleString()} · 场景：${Number(batch.scene_count || 0)}</div>
                        <div class="novel-to-script-info-meta">章节范围：${Array.isArray(batch.chapter_range) && batch.chapter_range.length ? batch.chapter_range.join('、') : '未拆章'}</div>
                        <div class="novel-to-script-action-row">
                            <button type="button" class="novel-to-script-btn novel-to-script-batch-retry" data-retry-batch="${Number(batch.batch_number || 0)}">
                                重转此批
                            </button>
                        </div>
                    </article>
                `).join('')}
            </div>
        </section>
    `;
}

function renderNovelToScriptSceneLines(scene) {
    if (!scene) {
        return '<div class="novel-to-script-empty-inline">还没有可展示的场景结构。</div>';
    }

    const beats = Array.isArray(scene.beats) ? scene.beats : [];
    return `
        <div class="novel-to-script-scene-card">
            <div class="novel-to-script-scene-title">【${escapeHtml(scene.scene_label || '场景')}：${escapeHtml(scene.heading || '未命名场景')}】</div>
            <div class="novel-to-script-scene-line"><strong>人物：</strong>${escapeHtml(scene.characters_text || '待补充')}</div>
            <div class="novel-to-script-scene-line"><strong>环境：</strong>${escapeHtml(scene.environment_text || '待补充')}</div>
            ${(beats || []).map((beat) => {
                const prefix = beat.type === 'character_line'
                    ? `${beat.speaker || beat.label || '角色'}${beat.qualifier ? `（${beat.qualifier}）` : ''}`
                    : `${beat.label || '动作/旁白'}${beat.qualifier ? `（${beat.qualifier}）` : ''}`;
                return `<div class="novel-to-script-scene-line"><strong>${escapeHtml(prefix)}：</strong>${escapeHtml(beat.text || '')}</div>`;
            }).join('')}
        </div>
    `;
}

function renderNovelToScriptWorkbenchPreview() {
    if (!novelToScriptState.result?.formatted_text) {
        return `
            <div class="novel-to-script-empty-state">
                <i class="ri-film-line"></i>
                <div>转换结果会显示在这里，默认以纯文本剧本形式预览。</div>
            </div>
        `;
    }

    return `
        <div class="novel-to-script-preview-shell">
            <div class="novel-to-script-preview-meta">
                <span>${(getNovelToScriptScenes().length || 0).toLocaleString()} 个场景</span>
                <span>${formatNovelToScriptSavedTime()}</span>
            </div>
            <textarea id="novel-to-script-result-editor" class="novel-to-script-result-editor" rows="20" placeholder="转换结果会显示在这里，可直接手动编辑。">${escapeHtml(novelToScriptState.result.formatted_text || '')}</textarea>
        </div>
    `;
}

function renderNovelToScriptCharactersView() {
    const characters = Array.isArray(novelToScriptState.result?.character_index) ? novelToScriptState.result.character_index : [];
    if (characters.length === 0) {
        return '<div class="novel-to-script-empty-inline">当前结果里还没有可识别的人物索引。</div>';
    }

    return `
        <div class="novel-to-script-card-grid">
            ${characters.map((item) => `
                <article class="novel-to-script-info-card">
                    <div class="novel-to-script-info-title">${escapeHtml(item.name || '未命名人物')}</div>
                    <div class="novel-to-script-info-copy">${escapeHtml(item.description || '未补充人物简介')}</div>
                    <div class="novel-to-script-info-meta">出现场景：${Array.isArray(item.scene_numbers) ? item.scene_numbers.join('、') : ''}</div>
                </article>
            `).join('')}
        </div>
    `;
}

function renderNovelToScriptScenesView() {
    const outline = Array.isArray(novelToScriptState.result?.scene_outline) ? novelToScriptState.result.scene_outline : [];
    if (outline.length === 0) {
        return '<div class="novel-to-script-empty-inline">当前结果里还没有可识别的场景目录。</div>';
    }

    return `
        <div class="novel-to-script-card-grid">
            ${outline.map((scene, index) => `
                <article class="novel-to-script-info-card ${index === novelToScriptState.selectedSceneIndex ? 'active' : ''}">
                    <div class="novel-to-script-info-title">${escapeHtml(scene.scene_label || `场景${index + 1}`)}</div>
                    <div class="novel-to-script-info-copy">${escapeHtml(scene.heading || '未命名场景')}</div>
                    <div class="novel-to-script-info-meta">人物：${escapeHtml(scene.characters_text || '待补充')} · 段落：${Number(scene.beat_count || 0)}</div>
                </article>
            `).join('')}
        </div>
    `;
}

function renderNovelToScriptResultBody() {
    if (novelToScriptState.resultTab === 'characters') {
        return renderNovelToScriptCharactersView();
    }
    if (novelToScriptState.resultTab === 'scenes') {
        return renderNovelToScriptScenesView();
    }
    return `<textarea id="novel-to-script-result-editor" class="novel-to-script-result-editor" rows="24" placeholder="转换结果会显示在这里，可直接手动编辑。">${escapeHtml(novelToScriptState.result?.formatted_text || '')}</textarea>`;
}

function renderNovelToScriptResultView() {
    const scenes = getNovelToScriptScenes();
    const selectedScene = getSelectedNovelToScriptScene();

    return `
        <div class="novel-to-script-page novel-to-script-page-result">
            <div class="novel-to-script-hero">
                <div>
                    <div class="novel-to-script-kicker">Novel to Script</div>
                    <h1 class="novel-to-script-title"><i class="ri-movie-2-line"></i> 小说转剧本</h1>
                    <div class="novel-to-script-subtitle">结果页默认展示纯文本剧本，同时保留分场景结构预览，方便继续改写与导出。</div>
                </div>
                <div class="novel-to-script-hero-tags">
                    <span class="novel-to-script-chip">${novelToScriptState.sourceFilename ? escapeHtml(novelToScriptState.sourceFilename) : '未命名输入'}</span>
                    <span class="novel-to-script-chip">${(scenes.length || 0).toLocaleString()} 个场景</span>
                    <span class="novel-to-script-chip">${formatNovelToScriptSavedTime()}</span>
                </div>
            </div>
            <div class="novel-to-script-result-layout">
                <aside class="novel-to-script-scene-list">
                    <button type="button" class="novel-to-script-back-btn app-back-button" id="novel-to-script-back-workbench">
                        <i class="ri-arrow-left-line"></i>
                        <span>返回工作台</span>
                    </button>
                    ${scenes.length === 0 ? '<div class="novel-to-script-empty-inline">暂无场景目录。</div>' : scenes.map((scene, index) => `
                        <button type="button" class="novel-to-script-scene-item ${index === novelToScriptState.selectedSceneIndex ? 'active' : ''}" data-scene-index="${index}">
                            <span class="novel-to-script-scene-item-label">${escapeHtml(scene.scene_label || `场景${index + 1}`)}</span>
                            <strong>${escapeHtml(scene.heading || '未命名场景')}</strong>
                        </button>
                    `).join('')}
                </aside>
                <section class="novel-to-script-result-panel">
                    <div class="novel-to-script-action-row">
                        <button id="novel-to-script-copy-result" class="novel-to-script-btn novel-to-script-btn-primary">复制结果</button>
                        <button id="novel-to-script-export-txt" class="novel-to-script-btn">导出 TXT</button>
                        <button id="novel-to-script-export-md" class="novel-to-script-btn">导出 MD</button>
                        <button id="novel-to-script-export-docx" class="novel-to-script-btn">导出 DOCX</button>
                    </div>
                    <div class="novel-to-script-scene-detail">
                        ${renderNovelToScriptSceneLines(selectedScene)}
                    </div>
                    <div class="novel-to-script-tabbar">
                        <button type="button" class="novel-to-script-tab ${novelToScriptState.resultTab === 'text' ? 'active' : ''}" data-result-tab="text">剧本正文</button>
                        <button type="button" class="novel-to-script-tab ${novelToScriptState.resultTab === 'scenes' ? 'active' : ''}" data-result-tab="scenes">场景目录</button>
                        <button type="button" class="novel-to-script-tab ${novelToScriptState.resultTab === 'characters' ? 'active' : ''}" data-result-tab="characters">人物表</button>
                    </div>
                    ${renderNovelToScriptResultBody()}
                </section>
            </div>
            ${renderNovelToScriptBatchSummary()}
        </div>
    `;
}

function renderNovelToScriptWorkbench() {
    const capabilities = novelToScriptState.capabilities || getNovelToScriptFallbackCapabilities();
    const options = capabilities.options || {};
    const isBusy = Boolean(novelToScriptState.loadingAction);
    const hasResult = Boolean(novelToScriptState.result?.formatted_text || novelToScriptState.result?.full_text);
    const strategySummary = novelToScriptState.analysis || getNovelToScriptStrategySummary();
    const plan = novelToScriptState.conversionPlan;
    const strategyBatchCount = Number(plan?.batch_count || strategySummary.estimatedBatches || 1);

    return `
        <div class="novel-to-script-page">
            <div class="novel-to-script-hero">
                <div>
                    <div class="novel-to-script-kicker">Standalone Workbench</div>
                    <h1 class="novel-to-script-title"><i class="ri-movie-2-line"></i> 小说转剧本</h1>
                    <div class="novel-to-script-subtitle">把已有小说内容改写为分场景剧本。支持粘贴正文、导入文件、生成结果、编辑复制与导出。</div>
                </div>
                <div class="novel-to-script-hero-tags">
                    <span class="novel-to-script-chip">推荐：${escapeHtml(strategySummary.recommendedModeLabel || '单次转换')}</span>
                    <span class="novel-to-script-chip">预计：${strategyBatchCount} ${strategyBatchCount > 1 ? '批' : '次'}</span>
                    <span class="novel-to-script-chip">${novelToScriptState.config.scene_density === 'high' ? '场景详细' : novelToScriptState.config.scene_density === 'low' ? '场景简洁' : '场景适中'}</span>
                    <span class="novel-to-script-chip">${formatNovelToScriptSavedTime()}</span>
                </div>
            </div>

            ${!novelToScriptState.globalConfigured ? `
                <div class="novel-to-script-alert">
                    请先在 <a href="#" id="novel-to-script-open-api-settings">设置 &gt; API配置</a> 中添加可用模型。
                </div>
            ` : ''}

            ${renderNovelToScriptLoadingBanner()}

            <div class="novel-to-script-grid">
                <section class="novel-to-script-panel">
                    <div class="novel-to-script-panel-head">
                        <div>
                            <div class="novel-to-script-panel-title">输入区</div>
                            <div class="novel-to-script-panel-copy">支持粘贴小说正文，或导入 <code>.txt</code> / <code>.md</code> / <code>.docx</code>。</div>
                        </div>
                        <div class="novel-to-script-action-row">
                            <input id="novel-to-script-import-input" type="file" accept=".txt,.md,.docx" hidden>
                            <button id="novel-to-script-import-trigger" class="novel-to-script-btn">导入文件</button>
                            <button id="novel-to-script-reset" class="novel-to-script-btn novel-to-script-btn-danger">清空草稿</button>
                        </div>
                    </div>
                    ${renderNovelToScriptSourceSummary()}
                    <div class="novel-to-script-strategy-card">
                        <div class="novel-to-script-strategy-title">智能识别</div>
                        <div class="novel-to-script-strategy-copy">${escapeHtml(strategySummary.reason || '系统会根据字数和章节结构自动选择更稳的转换方式。')}</div>
                        <div class="novel-to-script-strategy-meta">
                            <span>推荐模式：${escapeHtml(strategySummary.recommendedModeLabel || '单次转换')}</span>
                            <span>预计执行：${strategyBatchCount} ${strategyBatchCount > 1 ? '批' : '次'}</span>
                        </div>
                    </div>
                    <textarea id="novel-to-script-source-text" class="novel-to-script-source-text" rows="18" placeholder="把小说正文粘贴到这里，或点击上方“导入文件”。">${escapeHtml(novelToScriptState.sourceText || '')}</textarea>
                </section>

                <section class="novel-to-script-panel">
                    <div class="novel-to-script-panel-head">
                        <div>
                            <div class="novel-to-script-panel-title">转换配置</div>
                            <div class="novel-to-script-panel-copy">先保证输出稳定，再逐步调整对话比例、场景详细程度和风格差异。</div>
                        </div>
                    </div>
                    <div class="novel-to-script-form-grid">
                        <label class="novel-to-script-field-block">
                            <span>API配置</span>
                            <select id="novel-to-script-api-config" class="novel-to-script-field">
                                ${novelToScriptState.apiConfigs.length === 0
                                    ? (novelToScriptState.globalConfigured ? '<option value="">使用全局 API 配置</option>' : '<option value="">-- 请先配置API --</option>')
                                    : novelToScriptState.apiConfigs.map((cfg) => `<option value="${escapeHtml(cfg.id)}" ${(cfg.id === (novelToScriptState.selectedApiConfigId || novelToScriptState.activeConfigId)) ? 'selected' : ''}>${escapeHtml(cfg.name)}</option>`).join('')}
                            </select>
                        </label>
                        <label class="novel-to-script-field-block">
                            <span>模型</span>
                            <select id="novel-to-script-model" class="novel-to-script-field">
                                ${renderNovelToScriptModelOptions(novelToScriptState.selectedApiConfigId || novelToScriptState.activeConfigId, novelToScriptState.selectedModel)}
                            </select>
                        </label>
                        <label class="novel-to-script-field-block">
                            <span>转换方式</span>
                            <select id="novel-to-script-convert-mode" class="novel-to-script-field">
                                ${renderNovelToScriptSelectOptions(options.convert_modes, novelToScriptState.config.convert_mode)}
                            </select>
                        </label>
                        <label class="novel-to-script-field-block">
                            <span>场景详细程度</span>
                            <select id="novel-to-script-scene-density" class="novel-to-script-field">
                                ${renderNovelToScriptSelectOptions(options.scene_densities, novelToScriptState.config.scene_density)}
                            </select>
                        </label>
                        <label class="novel-to-script-field-block">
                            <span>对话比例</span>
                            <select id="novel-to-script-dialogue-ratio" class="novel-to-script-field">
                                ${renderNovelToScriptSelectOptions(options.dialogue_ratios, novelToScriptState.config.dialogue_ratio)}
                            </select>
                        </label>
                        <label class="novel-to-script-field-block">
                            <span>角色名处理</span>
                            <select id="novel-to-script-human-name-strategy" class="novel-to-script-field">
                                ${renderNovelToScriptSelectOptions(options.human_name_strategies, novelToScriptState.config.human_name_strategy)}
                            </select>
                        </label>
                        <label class="novel-to-script-toggle">
                            <input id="novel-to-script-keep-voice-style" type="checkbox" ${novelToScriptState.config.keep_voice_style ? 'checked' : ''}>
                            <span>保留原文语气和网络小说风格</span>
                        </label>
                    </div>
                    <div class="novel-to-script-panel-copy" style="margin-top:8px;font-size:12px;opacity:0.7;">以上配置会在点击"开始转换"时生效，修改后需重新转换才能看到变化。</div>
                    <div class="novel-to-script-action-row">
                        <button id="novel-to-script-convert" class="novel-to-script-btn novel-to-script-btn-primary" ${isBusy ? 'disabled' : ''}>
                            ${isBusy ? `转换中...` : (hasResult ? '重新转换' : `开始转换`)}
                        </button>
                        <button id="novel-to-script-copy-result" class="novel-to-script-btn" ${hasResult ? '' : 'disabled'}>复制结果</button>
                        <button id="novel-to-script-open-result" class="novel-to-script-btn" ${hasResult ? '' : 'disabled'}>打开结果页</button>
                    </div>
                    ${plan?.warnings?.length ? `
                        <div class="novel-to-script-warning-list">
                            ${plan.warnings.map((item) => `<div class="novel-to-script-warning-item">${escapeHtml(item)}</div>`).join('')}
                        </div>
                    ` : ''}
                </section>
            </div>

            <section class="novel-to-script-panel novel-to-script-panel-preview">
                <div class="novel-to-script-panel-head">
                    <div>
                        <div class="novel-to-script-panel-title">转换结果</div>
                        <div class="novel-to-script-panel-copy">默认按纯文本剧本连续展示，便于直接复制、修改、导出。</div>
                    </div>
                    <div class="novel-to-script-action-row">
                        <button id="novel-to-script-export-txt" class="novel-to-script-btn" ${hasResult ? '' : 'disabled'}>导出 TXT</button>
                        <button id="novel-to-script-export-md" class="novel-to-script-btn" ${hasResult ? '' : 'disabled'}>导出 MD</button>
                        <button id="novel-to-script-export-docx" class="novel-to-script-btn" ${hasResult ? '' : 'disabled'}>导出 DOCX</button>
                    </div>
                </div>
                ${renderNovelToScriptWorkbenchPreview()}
            </section>
        </div>
    `;
}

function renderNovelToScriptNavPanel() {
    const navList = document.getElementById('nav-list-container');
    if (!navList) return;

    const scenes = getNovelToScriptScenes();
    navList.innerHTML = '';

    const workbenchEntry = document.createElement('button');
    workbenchEntry.type = 'button';
    workbenchEntry.className = `list-item short-story-nav-entry ${novelToScriptState.activeView !== 'result' ? 'active' : ''}`;
    workbenchEntry.innerHTML = `
        <i class="ri-layout-grid-line short-story-nav-entry-icon"></i>
        <span class="list-item-strong">工作台</span>
    `;
    workbenchEntry.addEventListener('click', async () => {
        novelToScriptState.activeView = 'workbench';
        saveNovelToScriptData();
        await renderNovelToScriptInterface();
    });
    navList.appendChild(workbenchEntry);

    const resultEntry = document.createElement('button');
    resultEntry.type = 'button';
    resultEntry.className = `list-item short-story-nav-entry ${novelToScriptState.activeView === 'result' ? 'active' : ''}`;
    resultEntry.innerHTML = `
        <i class="ri-file-copy-2-line short-story-nav-entry-icon"></i>
        <span class="list-item-strong">转换结果</span>
    `;
    resultEntry.disabled = !novelToScriptState.result?.formatted_text;
    resultEntry.addEventListener('click', async () => {
        if (!novelToScriptState.result?.formatted_text) return;
        novelToScriptState.activeView = 'result';
        saveNovelToScriptData();
        await renderNovelToScriptInterface();
    });
    navList.appendChild(resultEntry);

    const status = document.createElement('div');
    status.className = 'short-story-nav-status';
    status.innerHTML = `
        <div class="short-story-nav-status-title">当前草稿</div>
        <div>来源：${novelToScriptState.sourceFilename ? escapeHtml(novelToScriptState.sourceFilename) : '手动粘贴'}</div>
        <div>字数：${getNovelToScriptWordCount().toLocaleString()}</div>
        <div>章节：${getNovelToScriptChapterCount()}</div>
        <div>场景：${scenes.length}</div>
    `;
    navList.appendChild(status);

    if (scenes.length > 0) {
        scenes.forEach((scene, index) => {
            const item = document.createElement('button');
            item.type = 'button';
            item.className = `list-item ${index === novelToScriptState.selectedSceneIndex ? 'active' : ''}`;
            item.innerHTML = `
                <i class="ri-clapperboard-line"></i>
                <span>${escapeHtml(scene.scene_label || `场景${index + 1}`)}</span>
            `;
            item.addEventListener('click', async () => {
                novelToScriptState.selectedSceneIndex = index;
                novelToScriptState.activeView = 'result';
                saveNovelToScriptData();
                await renderNovelToScriptInterface();
            });
            navList.appendChild(item);
        });
    }
}

async function renderNovelToScriptInterface() {
    await hydrateNovelToScriptProjectState();
    await loadNovelToScriptCapabilities();
    await loadGlobalApiConfigForNovelToScript();
    saveNovelToScriptData();

    const hasResult = Boolean(novelToScriptState.result?.formatted_text || novelToScriptState.result?.full_text);
    if (novelToScriptState.activeView === 'result' && hasResult) {
        updateBreadcrumbs(['小说转剧本', '转换结果']);
        ui.workspace.innerHTML = renderNovelToScriptResultView();
    } else {
        if (novelToScriptState.activeView === 'result' && !hasResult) {
            novelToScriptState.activeView = 'workbench';
            saveNovelToScriptData();
        }
        updateBreadcrumbs(['小说转剧本', '工作台']);
        ui.workspace.innerHTML = renderNovelToScriptWorkbench();
    }

    bindNovelToScriptEvents();
    renderNovelToScriptNavPanel();
}
