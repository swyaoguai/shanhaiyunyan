/**
 * 山海·云烟 - 小说封面生成工作台
 */

(function () {
    'use strict';

    const COVER_API = '/api/cover-images';
    const COVER_JOB_POLL_INTERVAL_MS = 2000;

    const COVER_PLATFORM_PRESETS = [
        { id: 'fanqie', label: '番茄小说', size: '800x600', note: '番茄平台封面预设，最终保存为横版 800x600；请求服务商时会自动适配模型支持的尺寸。' },
        { id: 'custom', label: '自定义分辨率', size: 'custom', note: '自定义分辨率需要当前图像模型和服务商接口支持。' },
    ];

    const coverState = {
        templates: [],
        selectedTemplateId: 'wuxia_gold_blade',
        history: [],
        apiConfigs: [],
        activeConfigId: '',
        draft: null,
        result: null,
        previewCover: null,
        selectedHistoryIds: [],
        loadingAction: '',
        loadingKind: '',
        form: {
            title: '',
            author: '',
            sourceMode: 'project_plus_custom',
            apiConfigId: '',
            model: '',
            platformPreset: 'fanqie',
            customWidth: '800',
            customHeight: '600',
            customElements: {
                creative_idea: '',
                characters: '',
                scene_background: '',
                symbols_props: '',
                atmosphere_color: '',
            },
        },
    };

    window.renderCoverImagesInterface = renderCoverImagesInterface;
    window.renderCoverImagesNavPanel = renderCoverImagesNavPanel;

    function isCoverImagesRenderCurrent(renderToken) {
        if (!renderToken) return true;
        const guard = window.NovelAgentApp?.core?.isCurrentModuleRender;
        if (typeof guard === 'function') {
            return guard('cover-images', renderToken);
        }
        return window.store?.currentModule === 'cover-images';
    }

    async function renderCoverImagesInterface(renderToken = null) {
        ensureCoverStyles();
        if (typeof updateBreadcrumbs === 'function') {
            updateBreadcrumbs(['项目资源', '封面生成']);
        }

        const container = document.getElementById('main-view');
        if (!container) return;

        container.innerHTML = `
            <div class="cover-workbench">
                <div class="cover-loading">
                    <i class="ri-loader-4-line"></i>
                    <span>正在加载封面工作台...</span>
                </div>
            </div>
        `;

        await loadCoverWorkbenchData();
        if (!isCoverImagesRenderCurrent(renderToken)) return;

        renderCoverWorkbench();
    }

    function renderCoverImagesNavPanel() {
        const nav = document.getElementById('nav-list-container');
        if (!nav) return;
        nav.innerHTML = '';
    }

    async function loadCoverWorkbenchData() {
        const [templatesResp, historyResp, configsResp] = await Promise.all([
            apiCall(`${COVER_API}/templates`),
            apiCall(`${COVER_API}/history`).catch(() => ({ covers: [] })),
            apiCall('/api/api-configs').catch(() => ({ configs: [], active_config_id: '' })),
        ]);

        coverState.templates = templatesResp.templates || [];
        coverState.history = historyResp.covers || [];
        coverState.apiConfigs = configsResp.configs || [];
        coverState.activeConfigId = configsResp.active_config_id || coverState.apiConfigs[0]?.id || '';
        const imageConfig = getImageCapableConfig(coverState.form.apiConfigId || coverState.activeConfigId);
        coverState.form.apiConfigId = imageConfig?.id || coverState.form.apiConfigId || coverState.activeConfigId;

        if (!coverState.templates.some((item) => item.id === coverState.selectedTemplateId)) {
            coverState.selectedTemplateId = coverState.templates[0]?.id || '';
        }
        if (!coverState.form.model || !isImageModelName(coverState.form.model)) {
            coverState.form.model = getSelectedModel(getActiveConfig());
        }
    }

    function renderCoverWorkbench() {
        const container = document.getElementById('main-view');
        if (!container) return;

        const selectedTemplate = getSelectedTemplate();
        const activeConfig = getActiveConfig();
        const selectedModel = getSelectedModel(activeConfig);
        coverState.form.model = selectedModel;
        const imageModels = getImageModels(activeConfig);
        const selectedPreset = getSelectedPreset();
        const busy = isCoverActionBusy();
        const draftingPrompt = isCoverActionBusy('prompt-draft');
        const generatingCover = isCoverActionBusy('cover-generation');
        const canGenerateCover = Boolean(coverState.draft?.final_prompt && selectedModel);

        container.innerHTML = `
            <div class="cover-workbench">
                <header class="cover-header">
                    <div>
                        <h2><i class="ri-image-add-line"></i> 小说封面生成</h2>
                        <p>选择字体风格与平台分辨率，确认书名后用本地变量生成封面提示词和图片。</p>
                    </div>
                </header>

                <div class="cover-layout">
                    <section class="cover-section">
                        <div class="cover-section-title">字体示例</div>
                        <div class="cover-template-grid">
                            ${coverState.templates.map((template) => renderTemplateButton(template)).join('')}
                        </div>
                    </section>

                    <section class="cover-section cover-section-main">
                        <div class="cover-section-title">元素与提示词</div>
                        <div class="cover-form-grid">
                            <label>
                                <span>书名</span>
                                <input id="cover-title" type="text" class="cover-input" value="${escapeHtml(coverState.form.title)}" placeholder="留空则使用当前项目名">
                                <small class="cover-field-hint cover-field-hint-warning">${escapeHtml(getTitleReminder())}</small>
                            </label>
                            <label>
                                <span>作者</span>
                                <input id="cover-author" type="text" class="cover-input" value="${escapeHtml(coverState.form.author)}" placeholder="XXXX">
                            </label>
                            <label>
                                <span>元素来源</span>
                                <select id="cover-source-mode" class="cover-input">
                                    <option value="project_plus_custom" ${coverState.form.sourceMode === 'project_plus_custom' ? 'selected' : ''}>项目自动提取 + 自定义补充</option>
                                    <option value="project" ${coverState.form.sourceMode === 'project' ? 'selected' : ''}>自动提取项目元素</option>
                                    <option value="custom" ${coverState.form.sourceMode === 'custom' ? 'selected' : ''}>只使用自定义元素</option>
                                </select>
                            </label>
                            <label>
                                <span>平台 / 分辨率</span>
                                <select id="cover-platform" class="cover-input">
                                    ${COVER_PLATFORM_PRESETS.map((preset) => `
                                        <option value="${escapeHtml(preset.id)}" ${preset.id === coverState.form.platformPreset ? 'selected' : ''}>
                                            ${escapeHtml(preset.label)} · ${escapeHtml(preset.size === 'custom' ? '自定义' : preset.size)}
                                        </option>
                                    `).join('')}
                                </select>
                                <small class="cover-field-hint">${escapeHtml(selectedPreset.note)}</small>
                            </label>
                            <label>
                                <span>图片 API 配置</span>
                                <select id="cover-api-config" class="cover-input">
                                    ${renderConfigOptions()}
                                </select>
                            </label>
                            <label>
                                <span>图像模型</span>
                                <select id="cover-model" class="cover-input" ${imageModels.length ? '' : 'disabled'}>
                                    ${renderImageModelOptions(activeConfig, selectedModel)}
                                </select>
                                <small class="cover-field-hint">${escapeHtml(getImageModelHint(activeConfig))}</small>
                            </label>
                            ${coverState.form.platformPreset === 'custom' ? `
                                <label>
                                    <span>自定义宽度</span>
                                    <input id="cover-custom-width" type="number" min="64" step="1" class="cover-input" value="${escapeHtml(coverState.form.customWidth)}" placeholder="800">
                                </label>
                                <label>
                                    <span>自定义高度</span>
                                    <input id="cover-custom-height" type="number" min="64" step="1" class="cover-input" value="${escapeHtml(coverState.form.customHeight)}" placeholder="600">
                                    <small class="cover-field-hint">自定义分辨率需要模型支持才可以正常生成。</small>
                                </label>
                            ` : ''}
                        </div>

                        <div class="cover-custom-grid">
                            ${renderCustomTextarea('creative_idea', '创作想法', '项目资料为空时建议填写：主角是谁、题材方向、想看到的画面、禁忌或参考气质。系统会据此补全角色和背景。', 'cover-custom-wide')}
                            ${renderCustomTextarea('characters', '角色/人物', '项目不为空时可留空自动提取；项目为空时尽量填写角色名、身份、外观、姿态、关系。')}
                            ${renderCustomTextarea('scene_background', '背景场景', '项目不为空时可留空自动提取；项目为空时尽量填写地点、时代、环境、远景和空间层次。')}
                            ${renderCustomTextarea('symbols_props', '关键道具/符号', '项目不为空时可留空自动提取；项目为空时尽量填写武器、信物、符号、核心意象。')}
                            ${renderCustomTextarea('atmosphere_color', '画面情绪/色彩', '项目不为空时可留空推断；项目为空时尽量填写情绪关键词、主色、光影和氛围。')}
                        </div>

                        <div class="cover-prompt-actions">
                            <div class="cover-action-row">
                                <button type="button" class="cover-btn cover-btn-primary" id="cover-draft-prompt" ${draftingPrompt ? 'disabled aria-busy="true"' : (busy ? 'disabled' : '')}>
                                    <i class="${draftingPrompt ? 'ri-loader-4-line cover-spin' : 'ri-magic-line'}"></i> ${draftingPrompt ? '正在生成提示词' : '生成封面提示词'}
                                </button>
                            </div>
                            <div class="cover-action-row cover-action-row-secondary">
                                <button type="button" class="cover-btn cover-btn-ghost" id="cover-copy-prompt" ${coverState.draft?.final_prompt && !busy ? '' : 'disabled'}>
                                    <i class="ri-file-copy-line"></i> 复制提示词
                                </button>
                                <button type="button" class="cover-btn cover-btn-primary" id="cover-generate" ${canGenerateCover && !busy ? '' : 'disabled'} ${generatingCover ? 'aria-busy="true"' : ''}>
                                    <i class="${generatingCover ? 'ri-loader-4-line cover-spin' : 'ri-sparkling-line'}"></i> ${generatingCover ? '正在生成封面' : '生成封面'}
                                </button>
                            </div>
                            <span class="cover-status" id="cover-status">${escapeHtml(getStatusText())}</span>
                            <small class="cover-model-note">${escapeHtml(getModelUsageHint(selectedModel))}</small>
                        </div>

                        ${renderExtractedElements()}

                        <label class="cover-prompt-block">
                            <span>最终封面提示词</span>
                            <textarea id="cover-final-prompt" class="cover-textarea cover-final-prompt" rows="10" placeholder="生成后的最终提示词会显示在这里，可手动微调。">${escapeHtml(coverState.draft?.final_prompt || '')}</textarea>
                        </label>
                    </section>

                    <section class="cover-section" id="cover-history-panel">
                        <div class="cover-section-title">预览与历史</div>
                        ${renderCoverResult()}
                        ${renderCoverHistory()}
                    </section>
                </div>
                ${renderCoverLightbox()}
            </div>
        `;

        bindCoverEvents();
    }

    function renderTemplateButton(template) {
        const active = template.id === coverState.selectedTemplateId;
        return `
            <button type="button" id="cover-template-${escapeHtml(template.id)}" class="cover-template ${active ? 'active' : ''}" data-template-id="${escapeHtml(template.id)}">
                ${template.preview_image ? `<img class="cover-template-thumb" src="${escapeHtml(template.preview_image)}" alt="${escapeHtml(template.name)} 示例">` : ''}
                ${active ? '<span class="cover-template-check" aria-label="已选择"><i class="ri-check-line"></i></span>' : ''}
                <span class="cover-template-meta">
                    <strong>${escapeHtml(template.name)}</strong>
                    <small>${escapeHtml(template.genre || '')}</small>
                    <em>${escapeHtml(template.preview || template.description || '')}</em>
                </span>
            </button>
        `;
    }

    function renderCustomTextarea(id, label, placeholder, className = '') {
        return `
            <label class="${escapeHtml(className)}">
                <span>${escapeHtml(label)}</span>
                <textarea id="cover-custom-${escapeHtml(id)}" class="cover-textarea" rows="3" placeholder="${escapeHtml(placeholder)}">${escapeHtml(coverState.form.customElements[id] || '')}</textarea>
            </label>
        `;
    }

    function renderExtractedElements() {
        const elements = coverState.draft?.elements || null;
        if (!elements) return '';
        const rows = [
            ['角色/人物', elements.characters],
            ['背景场景', elements.scene_background],
            ['关键道具/符号', elements.symbols_props],
            ['画面情绪/色彩', elements.atmosphere_color],
        ];
        return `
            <div class="cover-extracted">
                <div class="cover-section-title">自动提取与补充结果</div>
                ${coverState.draft?.completion_notice ? `<div class="cover-extracted-note">${escapeHtml(coverState.draft.completion_notice)}</div>` : ''}
                ${rows.map(([label, value]) => `
                    <div class="cover-extracted-row">
                        <strong>${escapeHtml(label)}</strong>
                        <span>${escapeHtml(value || '未提取到内容，已使用当前字体模板的默认描写。')}</span>
                    </div>
                `).join('')}
            </div>
        `;
    }

    function renderConfigOptions() {
        const imageConfigs = getImageCapableConfigs();
        if (!imageConfigs.length) {
            return '<option value="">暂无配置了图片模型的 API 配置</option>';
        }
        return imageConfigs.map((config) => `
            <option value="${escapeHtml(config.id)}" ${config.id === coverState.form.apiConfigId ? 'selected' : ''}>
                ${escapeHtml(config.name || config.id)}
            </option>
        `).join('');
    }

    function renderImageModelOptions(config, selectedModel) {
        const models = getImageModels(config);
        if (!models.length) {
            return '<option value="">请先在 API 配置中添加图片模型</option>';
        }
        return models.map((model) => `
            <option value="${escapeHtml(model)}" ${model === selectedModel ? 'selected' : ''}>${escapeHtml(model)}</option>
        `).join('');
    }

    function renderCoverResult() {
        if (!coverState.result?.image_url) {
            return `
                <div class="cover-empty">
                    <i class="ri-image-line"></i>
                    <span>封面生成后会显示在这里。</span>
                </div>
            `;
        }
        const aspect = sizeToAspect(coverState.result.size || getGenerationSize({ silent: true }) || '800x600');
        const name = coverState.result.cover_id || '最新封面';
        return `
            <div class="cover-result">
                <button type="button" class="cover-image-open" data-view-cover="${escapeHtml(coverState.result.cover_id || '')}" data-cover-scope="result" title="查看大图">
                    <img class="cover-result-image" style="aspect-ratio: ${escapeHtml(aspect)};" src="${escapeHtml(coverState.result.image_url)}" alt="生成的小说封面">
                </button>
                <div class="cover-result-meta">${escapeHtml(name)}</div>
                <div class="cover-save-note">
                    <i class="ri-information-line"></i>
                    <span>封面已保存到项目历史；请及时保存到本地，项目文件被移动或清理后链接可能失效。</span>
                </div>
                <div class="cover-result-actions">
                    <button type="button" class="cover-btn cover-btn-ghost" data-view-cover="${escapeHtml(coverState.result.cover_id || '')}" data-cover-scope="result">
                        <i class="ri-zoom-in-line"></i> 查看大图
                    </button>
                    <a class="cover-btn cover-btn-primary" href="${escapeHtml(coverState.result.image_url)}" download="${escapeHtml(safeCoverFilename(name))}">
                        <i class="ri-download-2-line"></i> 保存到本地
                    </a>
                </div>
            </div>
        `;
    }

    function renderCoverHistory() {
        if (!coverState.history.length) {
            return '<div class="cover-history-empty">暂无历史封面。</div>';
        }
        const selectedCount = coverState.selectedHistoryIds.length;
        return `
            <div class="cover-history-toolbar">
                <label class="cover-history-select-all">
                    <input type="checkbox" id="cover-history-select-all" ${selectedCount === coverState.history.length ? 'checked' : ''}>
                    <span>全选</span>
                </label>
                <button type="button" class="cover-btn cover-btn-danger" id="cover-delete-selected" ${selectedCount ? '' : 'disabled'}>
                    <i class="ri-delete-bin-6-line"></i> 删除选中${selectedCount ? `（${selectedCount}）` : ''}
                </button>
            </div>
            <div class="cover-history-list">
                ${coverState.history.map((item) => `
                    <div class="cover-history-item ${coverState.selectedHistoryIds.includes(item.cover_id) ? 'selected' : ''}">
                        <input type="checkbox" class="cover-history-check" data-select-cover="${escapeHtml(item.cover_id)}" ${coverState.selectedHistoryIds.includes(item.cover_id) ? 'checked' : ''} aria-label="选择历史封面">
                        <button type="button" class="cover-history-thumb-btn" data-view-cover="${escapeHtml(item.cover_id)}" data-cover-scope="history" title="查看大图">
                            <img loading="lazy" src="${escapeHtml(item.thumbnail_url || item.image_url || '')}" alt="历史封面缩略图">
                        </button>
                        <div>
                            <strong>${escapeHtml(item.template_id || '封面')}</strong>
                            <small>${escapeHtml(item.size || '')}${item.size ? ' · ' : ''}${escapeHtml(formatCoverTime(item.created_at))}</small>
                            <div class="cover-history-actions">
                                <a href="${escapeHtml(item.image_url || '')}" download="${escapeHtml(safeCoverFilename(item.cover_id || 'cover'))}">保存</a>
                                <button type="button" data-view-cover="${escapeHtml(item.cover_id)}" data-cover-scope="history">大图</button>
                            </div>
                        </div>
                        <button type="button" class="cover-icon-btn" data-delete-cover="${escapeHtml(item.cover_id)}" title="删除封面">
                            <i class="ri-delete-bin-line"></i>
                        </button>
                    </div>
                `).join('')}
            </div>
        `;
    }

    function renderCoverLightbox() {
        const cover = coverState.previewCover;
        if (!cover?.image_url) return '';
        const name = cover.cover_id || cover.template_id || '封面';
        return `
            <div class="cover-lightbox" role="dialog" aria-modal="true" aria-label="封面大图预览">
                <div class="cover-lightbox-panel">
                    <div class="cover-lightbox-header">
                        <strong>${escapeHtml(name)}</strong>
                        <div class="cover-lightbox-actions">
                            <a class="cover-btn cover-btn-primary" href="${escapeHtml(cover.image_url)}" download="${escapeHtml(safeCoverFilename(name))}">
                                <i class="ri-download-2-line"></i> 保存到本地
                            </a>
                            <button type="button" class="cover-icon-btn" id="cover-close-preview" title="关闭预览">
                                <i class="ri-close-line"></i>
                            </button>
                        </div>
                    </div>
                    <img class="cover-lightbox-image" src="${escapeHtml(cover.image_url)}" alt="封面大图">
                    <div class="cover-save-note">
                        <i class="ri-information-line"></i>
                        <span>建议及时保存到本地，历史文件被删除、项目迁移或链接失效后将无法再次显示。</span>
                    </div>
                </div>
            </div>
        `;
    }

    function bindCoverEvents() {
        document.querySelectorAll('[data-template-id]').forEach((button) => {
            button.addEventListener('click', () => {
                captureFormState();
                coverState.selectedTemplateId = button.dataset.templateId || coverState.selectedTemplateId;
                coverState.draft = null;
                coverState.result = null;
                renderCoverWorkbench();
            });
        });

        document.getElementById('cover-api-config')?.addEventListener('change', (event) => {
            captureFormState();
            coverState.activeConfigId = event.target.value;
            coverState.form.apiConfigId = event.target.value;
            const config = getActiveConfig();
            coverState.form.model = getSelectedModel(config);
            coverState.draft = null;
            coverState.result = null;
            renderCoverWorkbench();
        });

        document.getElementById('cover-platform')?.addEventListener('change', () => {
            captureFormState();
            renderCoverWorkbench();
        });

        ['cover-title', 'cover-author', 'cover-source-mode', 'cover-model', 'cover-custom-width', 'cover-custom-height'].forEach((id) => {
            document.getElementById(id)?.addEventListener('input', () => captureFormState());
            document.getElementById(id)?.addEventListener('change', () => captureFormState());
        });
        document.querySelectorAll('[id^="cover-custom-"]').forEach((node) => {
            node.addEventListener('input', () => captureFormState());
        });

        document.getElementById('cover-draft-prompt')?.addEventListener('click', () => runPromptDraft());
        document.getElementById('cover-generate')?.addEventListener('click', () => runCoverGeneration());
        document.getElementById('cover-copy-prompt')?.addEventListener('click', () => copyFinalPrompt());
        document.querySelectorAll('[data-view-cover]').forEach((button) => {
            button.addEventListener('click', () => openCoverPreview(button.dataset.viewCover, button.dataset.coverScope));
        });
        document.getElementById('cover-close-preview')?.addEventListener('click', () => closeCoverPreview());
        document.querySelector('.cover-lightbox')?.addEventListener('click', (event) => {
            if (event.target?.classList?.contains('cover-lightbox')) closeCoverPreview();
        });
        document.querySelectorAll('[data-select-cover]').forEach((checkbox) => {
            checkbox.addEventListener('change', () => toggleHistorySelection(checkbox.dataset.selectCover, checkbox.checked));
        });
        document.getElementById('cover-history-select-all')?.addEventListener('change', (event) => toggleAllHistorySelection(event.target.checked));
        document.getElementById('cover-delete-selected')?.addEventListener('click', () => deleteSelectedCovers());
        document.querySelectorAll('[data-delete-cover]').forEach((button) => {
            button.addEventListener('click', () => deleteCover(button.dataset.deleteCover));
        });
    }

    async function runPromptDraft() {
        if (isCoverActionBusy()) return;
        captureFormState();
        setLoading('正在生成提示词...', 'prompt-draft');
        try {
            const response = await apiCall(`${COVER_API}/prompt-draft`, 'POST', {
                template_id: coverState.selectedTemplateId,
                source_mode: coverState.form.sourceMode || 'project_plus_custom',
                title: coverState.form.title,
                author: coverState.form.author,
                custom_elements: collectCustomElements(),
            });
            coverState.draft = response.data;
            clearLoading();
            renderCoverWorkbench();
            showToast?.('封面提示词已生成', 'success');
        } catch (error) {
            clearLoading();
            renderCoverWorkbench();
            showToast?.(error.message || '提示词生成失败', 'error');
        }
    }

    async function runCoverGeneration() {
        if (isCoverActionBusy()) return;
        captureFormState();
        const prompt = getFieldValue('cover-final-prompt');
        if (!prompt) {
            showToast?.('请先生成或填写封面提示词', 'warning');
            return;
        }
        const size = getGenerationSize();
        if (!size) return;
        if (!coverState.form.model || !isImageModelName(coverState.form.model)) {
            showToast?.('请选择支持图像生成的图片模型', 'warning');
            return;
        }
        setLoading('正在提交封面生成任务...', 'cover-generation');
        try {
            const response = await apiCall(`${COVER_API}/generate-jobs`, 'POST', {
                template_id: coverState.selectedTemplateId,
                prompt,
                typography_prompt: coverState.draft?.typography_prompt || '',
                element_prompt: coverState.draft?.element_prompt || '',
                source_mode: coverState.form.sourceMode || 'project_plus_custom',
                custom_elements: collectCustomElements(),
                api_config_id: coverState.form.apiConfigId,
                model: coverState.form.model,
                size,
            });
            const taskId = response.task_id || response.data?.task_id || '';
            if (!taskId) {
                throw new Error('封面生成任务创建失败：未返回任务 ID。');
            }
            setLoading('封面生成任务已提交，正在等待图片接口返回...', 'cover-generation');
            const result = await pollCoverGenerationJob(taskId, response.poll_interval_ms);
            coverState.result = result;
            clearLoading();
            coverState.history = [result, ...coverState.history.filter((item) => item.cover_id !== result.cover_id)];
            coverState.selectedHistoryIds = [];
            renderCoverWorkbench();
            showToast?.('封面已生成，请及时保存到本地', 'success');
        } catch (error) {
            clearLoading();
            renderCoverWorkbench();
            showToast?.(error.message || '封面生成失败', 'error');
        }
    }

    async function pollCoverGenerationJob(taskId, pollIntervalMs = COVER_JOB_POLL_INTERVAL_MS) {
        const intervalMs = normalizePollInterval(pollIntervalMs);
        while (true) {
            const response = await apiCall(`${COVER_API}/generate-jobs/${encodeURIComponent(taskId)}`, 'GET');
            const job = response.data || response.job || response;
            const status = String(job.status || '').toLowerCase();
            if (status === 'completed') {
                if (!job.result) {
                    throw new Error('封面生成任务已完成，但没有返回图片结果。');
                }
                return job.result;
            }
            if (status === 'failed') {
                throw new Error(job.error || job.message || '封面生成失败，请检查图像模型配置。');
            }
            const message = job.message || (status === 'queued'
                ? '封面生成任务已提交，正在等待执行...'
                : '封面正在生成中，图片接口可能需要较长时间...');
            setLoading(message, 'cover-generation');
            await waitForCoverJob(intervalMs);
        }
    }

    function normalizePollInterval(value) {
        const parsed = Number(value);
        if (!Number.isFinite(parsed) || parsed <= 0) return COVER_JOB_POLL_INTERVAL_MS;
        return Math.min(Math.max(parsed, 500), 10000);
    }

    function waitForCoverJob(ms) {
        return new Promise((resolve) => setTimeout(resolve, ms));
    }

    async function copyFinalPrompt() {
        const prompt = getFieldValue('cover-final-prompt');
        if (!prompt) return;
        await navigator.clipboard?.writeText(prompt);
        showToast?.('提示词已复制', 'success');
    }

    async function deleteCover(coverId) {
        if (!coverId) return;
        if (!(await askConfirm('确定删除这张历史封面吗？删除后本地历史文件也会移除。'))) return;
        try {
            await apiCall(`${COVER_API}/history/${encodeURIComponent(coverId)}`, 'DELETE');
            coverState.history = coverState.history.filter((item) => item.cover_id !== coverId);
            coverState.selectedHistoryIds = coverState.selectedHistoryIds.filter((id) => id !== coverId);
            if (coverState.result?.cover_id === coverId) coverState.result = null;
            if (coverState.previewCover?.cover_id === coverId) coverState.previewCover = null;
            renderCoverWorkbench();
            showToast?.('封面已删除', 'success');
        } catch (error) {
            showToast?.(error.message || '删除失败', 'error');
        }
    }

    async function deleteSelectedCovers() {
        const ids = [...coverState.selectedHistoryIds];
        if (!ids.length) return;
        if (!(await askConfirm(`确定删除选中的 ${ids.length} 张历史封面吗？删除后本地历史文件也会移除。`))) return;
        try {
            const response = await apiCall(`${COVER_API}/history/delete-batch`, 'POST', { cover_ids: ids });
            const deleted = response.deleted || [];
            coverState.history = coverState.history.filter((item) => !deleted.includes(item.cover_id));
            coverState.selectedHistoryIds = coverState.selectedHistoryIds.filter((id) => !deleted.includes(id));
            if (coverState.result?.cover_id && deleted.includes(coverState.result.cover_id)) coverState.result = null;
            if (coverState.previewCover?.cover_id && deleted.includes(coverState.previewCover.cover_id)) coverState.previewCover = null;
            renderCoverWorkbench();
            showToast?.(`已删除 ${deleted.length} 张历史封面`, 'success');
        } catch (error) {
            showToast?.(error.message || '批量删除失败', 'error');
        }
    }

    function toggleHistorySelection(coverId, checked) {
        if (!coverId) return;
        const set = new Set(coverState.selectedHistoryIds);
        if (checked) set.add(coverId);
        else set.delete(coverId);
        coverState.selectedHistoryIds = [...set];
        renderCoverWorkbench();
    }

    function toggleAllHistorySelection(checked) {
        coverState.selectedHistoryIds = checked
            ? coverState.history.map((item) => item.cover_id).filter(Boolean)
            : [];
        renderCoverWorkbench();
    }

    function openCoverPreview(coverId, scope) {
        let cover = null;
        if (scope === 'result' && coverState.result?.cover_id === coverId) cover = coverState.result;
        if (!cover) cover = coverState.history.find((item) => item.cover_id === coverId) || null;
        if (!cover?.image_url && coverState.result?.image_url && scope === 'result') cover = coverState.result;
        if (!cover?.image_url) return;
        coverState.previewCover = cover;
        renderCoverWorkbench();
    }

    function closeCoverPreview() {
        coverState.previewCover = null;
        renderCoverWorkbench();
    }

    async function askConfirm(message) {
        if (typeof window.showConfirmDialog !== 'function') return true;
        return await window.showConfirmDialog(message);
    }

    function captureFormState() {
        coverState.form.title = getFieldValue('cover-title');
        coverState.form.author = getFieldValue('cover-author');
        coverState.form.sourceMode = getFieldValue('cover-source-mode') || coverState.form.sourceMode;
        coverState.form.apiConfigId = getFieldValue('cover-api-config') || coverState.form.apiConfigId || coverState.activeConfigId;
        coverState.form.model = getFieldValue('cover-model') || coverState.form.model;
        coverState.form.platformPreset = getFieldValue('cover-platform') || coverState.form.platformPreset;
        coverState.form.customWidth = getFieldValue('cover-custom-width') || coverState.form.customWidth;
        coverState.form.customHeight = getFieldValue('cover-custom-height') || coverState.form.customHeight;
        coverState.form.customElements = collectCustomElements();
    }

    function collectCustomElements() {
        return {
            creative_idea: getFieldValue('cover-custom-creative_idea'),
            characters: getFieldValue('cover-custom-characters'),
            scene_background: getFieldValue('cover-custom-scene_background'),
            symbols_props: getFieldValue('cover-custom-symbols_props'),
            atmosphere_color: getFieldValue('cover-custom-atmosphere_color'),
        };
    }

    function getGenerationSize(options = {}) {
        const preset = getSelectedPreset();
        if (preset.size !== 'custom') return preset.size;
        const width = parseInt(coverState.form.customWidth || getFieldValue('cover-custom-width') || '0', 10);
        const height = parseInt(coverState.form.customHeight || getFieldValue('cover-custom-height') || '0', 10);
        if (!Number.isFinite(width) || !Number.isFinite(height) || width < 64 || height < 64) {
            if (!options.silent) showToast?.('请输入有效的自定义分辨率，宽高至少 64。', 'warning');
            return '';
        }
        return `${width}x${height}`;
    }

    function getSelectedTemplate() {
        return coverState.templates.find((item) => item.id === coverState.selectedTemplateId) || coverState.templates[0] || null;
    }

    function getActiveConfig() {
        const activeId = coverState.form.apiConfigId || coverState.activeConfigId;
        return coverState.apiConfigs.find((config) => config.id === activeId) || coverState.apiConfigs[0] || null;
    }

    function getSelectedModel(config) {
        const models = getImageModels(config);
        if (coverState.form.model && models.includes(coverState.form.model)) return coverState.form.model;
        return models[0] || '';
    }

    function getImageCapableConfigs() {
        return coverState.apiConfigs.filter((config) => getImageModels(config).length > 0);
    }

    function getImageCapableConfig(preferredId) {
        const imageConfigs = getImageCapableConfigs();
        return imageConfigs.find((config) => config.id === preferredId) || imageConfigs[0] || null;
    }

    function getImageModels(config) {
        return typeof window.getImageModelsFromConfig === 'function'
            ? window.getImageModelsFromConfig(config)
            : [];
    }

    function isImageModelName(model) {
        return typeof window.isImageModelName === 'function'
            ? window.isImageModelName(model)
            : false;
    }

    function getSelectedPreset() {
        return COVER_PLATFORM_PRESETS.find((preset) => preset.id === coverState.form.platformPreset) || COVER_PLATFORM_PRESETS[0];
    }

    function getFieldValue(id) {
        const node = document.getElementById(id);
        return node ? String(node.value || '').trim() : '';
    }

    function getProjectName() {
        if (window.store?.currentProjectName) return String(window.store.currentProjectName);
        const activeId = window.store?.currentProjectId || window.store?.currentProject;
        const project = Array.isArray(window.store?.projects)
            ? window.store.projects.find((item) => item?.id === activeId)
            : null;
        return project?.name ? String(project.name) : '';
    }

    function getTitleReminder() {
        if (coverState.form.title) return '';
        if (coverState.draft?.title_warning) return coverState.draft.title_warning;
        const projectName = getProjectName();
        if (!projectName) return '留空时会使用当前项目名；若项目名不是小说书名，请手动填写。';
        return `留空时会使用当前项目名“${projectName}”；若项目名不是小说书名，请改为正确书名。`;
    }

    function getStatusText() {
        if (coverState.loadingAction) return coverState.loadingAction;
        if (coverState.draft?.completion_notice) return coverState.draft.completion_notice;
        if (coverState.draft?.final_prompt) return '提示词已就绪，可继续微调后生成封面。';
        return '四个元素可自动从世界观、主角档案、物品设定和大纲中提取；留空即可使用项目内容。';
    }

    function getModelUsageHint(imageModel) {
        const imageModelText = String(imageModel || '').trim();
        const promptPart = '封面提示词由本地模板和变量生成，不调用文本模型。';
        if (imageModelText) {
            const imageFormat = getImageApiFormatLabel(getActiveConfig()?.image_api_format || 'auto');
            return `${promptPart} 生成封面会使用图像模型“${imageModelText}”，图片格式：${imageFormat}。`;
        }
        return `${promptPart} 请先在 API 配置中添加并选择图片模型后再生成封面。`;
    }

    function getImageModelHint(config) {
        if (!config) return '当前没有可用 API 配置；请先在设置中添加图片模型配置。';
        if (!getImageModels(config).length) return '当前 API 配置没有识别到图片模型；请在设置中添加 image / imagen / dall-e 等图片模型。';
        return `这里只能从当前 API 配置中的图片模型下拉选择；图片格式：${getImageApiFormatLabel(config.image_api_format || 'auto')}。`;
    }

    function getImageApiFormatLabel(format) {
        const labels = {
            auto: 'Auto 自动尝试',
            openai_images: 'OpenAI Images',
            qwen_images: 'Qwen Images',
            gemini_native: 'Gemini 原生图片',
            responses: 'OpenAI Responses 图片',
            chat_completions: 'Chat 图片输出',
        };
        return labels[format] || labels.auto;
    }

    function setLoading(text, kind) {
        coverState.loadingAction = text;
        coverState.loadingKind = text ? (kind || coverState.loadingKind || 'general') : '';
        const status = document.getElementById('cover-status');
        if (status) status.textContent = text;
        syncCoverActionDisabledState();
    }

    function clearLoading() {
        setLoading('', '');
    }

    function isCoverActionBusy(kind = '') {
        if (!coverState.loadingAction) return false;
        return kind ? coverState.loadingKind === kind : true;
    }

    function syncCoverActionDisabledState() {
        const busy = isCoverActionBusy();
        const generateButton = document.getElementById('cover-generate');
        const draftButton = document.getElementById('cover-draft-prompt');
        const copyButton = document.getElementById('cover-copy-prompt');
        const draftingPrompt = isCoverActionBusy('prompt-draft');
        const generatingCover = isCoverActionBusy('cover-generation');
        if (draftButton) {
            draftButton.disabled = busy;
            draftButton.setAttribute('aria-busy', String(draftingPrompt));
            draftButton.innerHTML = draftingPrompt
                ? '<i class="ri-loader-4-line cover-spin"></i> 正在生成提示词'
                : '<i class="ri-magic-line"></i> 生成封面提示词';
        }
        if (generateButton) {
            generateButton.disabled = busy || !coverState.draft?.final_prompt || !coverState.form.model;
            generateButton.setAttribute('aria-busy', String(generatingCover));
            generateButton.innerHTML = generatingCover
                ? '<i class="ri-loader-4-line cover-spin"></i> 正在生成封面'
                : '<i class="ri-sparkling-line"></i> 生成封面';
        }
        if (copyButton) {
            copyButton.disabled = busy || !coverState.draft?.final_prompt;
        }
    }

    function formatCoverTime(value) {
        if (!value) return '';
        try {
            return new Date(value).toLocaleString();
        } catch (_) {
            return String(value);
        }
    }

    function safeCoverFilename(value) {
        const base = String(value || 'novel-cover')
            .replace(/[\\/:*?"<>|]+/g, '-')
            .replace(/\s+/g, '-')
            .replace(/-+/g, '-')
            .replace(/^-|-$/g, '') || 'novel-cover';
        return `${base}.png`;
    }

    function sizeToAspect(size) {
        const match = String(size || '').match(/^(\d+)x(\d+)$/);
        if (!match) return '4 / 3';
        return `${Number(match[1]) || 4} / ${Number(match[2]) || 3}`;
    }

    function ensureCoverStyles() {
        if (document.getElementById('cover-images-style')) return;
        const style = document.createElement('style');
        style.id = 'cover-images-style';
        style.textContent = `
            .cover-workbench { max-width: 1480px; margin: 0 auto; padding: 24px; color: var(--text-primary); }
            .cover-header { display: flex; align-items: flex-start; justify-content: space-between; gap: 16px; margin-bottom: 20px; }
            .cover-header h2 { margin: 0; font-size: 24px; display: flex; align-items: center; gap: 10px; letter-spacing: 0; }
            .cover-header p { margin: 8px 0 0; color: var(--text-secondary); line-height: 1.6; }
            .cover-action-row { display: flex; gap: 10px; align-items: center; flex-wrap: wrap; }
            .cover-layout { display: grid; grid-template-columns: minmax(260px, 0.95fr) minmax(460px, 1.55fr) minmax(280px, 0.9fr); gap: 16px; align-items: start; }
            .cover-section { border: 1px solid var(--border-color); background: rgba(15, 23, 42, 0.35); border-radius: 8px; padding: 16px; }
            .cover-section-title { font-size: 13px; font-weight: 700; color: var(--text-primary); margin-bottom: 12px; }
            .cover-template-grid { display: grid; gap: 10px; max-height: calc(100vh - 180px); overflow: auto; padding-right: 4px; }
            .cover-template { position: relative; width: 100%; text-align: left; border: 1px solid rgba(148, 163, 184, 0.28); background: rgba(255,255,255,0.04); color: var(--text-primary); border-radius: 8px; padding: 10px; cursor: pointer; display: grid; gap: 8px; }
            .cover-template:hover, .cover-template.active { border-color: rgba(99, 102, 241, 0.75); background: rgba(99, 102, 241, 0.15); }
            .cover-template-thumb { width: 100%; aspect-ratio: 4 / 3; object-fit: cover; border-radius: 6px; background: rgba(0,0,0,0.25); }
            .cover-template-check { position: absolute; right: 14px; bottom: 14px; width: 28px; height: 28px; border-radius: 50%; display: inline-flex; align-items: center; justify-content: center; color: #ffffff; background: rgba(34, 197, 94, 0.92); border: 2px solid rgba(255,255,255,0.92); box-shadow: 0 8px 18px rgba(0,0,0,0.28); font-size: 17px; }
            .cover-template-meta { display: grid; gap: 4px; }
            .cover-template small, .cover-template em { color: var(--text-secondary); font-style: normal; line-height: 1.45; font-size: 12px; }
            .cover-form-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px; }
            .cover-custom-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px; margin-top: 14px; }
            .cover-custom-wide { grid-column: 1 / -1; }
            .cover-input, .cover-textarea { width: 100%; box-sizing: border-box; border: 1px solid var(--border-color); border-radius: 8px; background: rgba(0,0,0,0.22); color: var(--text-primary); padding: 10px 12px; font: inherit; }
            .cover-textarea { resize: vertical; line-height: 1.55; }
            .cover-final-prompt { min-height: 190px; }
            .cover-workbench label span, .cover-prompt-block span { display: block; font-size: 12px; color: var(--text-secondary); margin-bottom: 6px; }
            .cover-field-hint { display: block; margin-top: 6px; font-size: 11px; line-height: 1.45; color: var(--text-secondary); }
            .cover-field-hint-warning { color: #fbbf24; }
            .cover-prompt-actions { display: grid; gap: 8px; margin: 14px 0; }
            .cover-action-row { margin: 0; }
            .cover-action-row-secondary { padding-top: 2px; }
            .cover-status { color: var(--text-secondary); font-size: 12px; line-height: 1.5; }
            .cover-model-note { color: var(--text-secondary); font-size: 11px; line-height: 1.45; }
            .cover-btn { border: 1px solid var(--border-color); border-radius: 8px; padding: 9px 14px; color: var(--text-primary); background: rgba(255,255,255,0.06); cursor: pointer; display: inline-flex; gap: 8px; align-items: center; justify-content: center; }
            .cover-btn:disabled { opacity: 0.5; cursor: not-allowed; }
            .cover-spin { animation: cover-spin 0.9s linear infinite; }
            @keyframes cover-spin { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }
            .cover-btn-primary { border-color: rgba(99, 102, 241, 0.75); background: rgba(99, 102, 241, 0.88); color: white; }
            .cover-btn-ghost { background: transparent; }
            .cover-btn-danger { border-color: rgba(239, 68, 68, 0.5); background: rgba(239, 68, 68, 0.14); color: #fecaca; }
            .cover-extracted { margin: 12px 0 14px; border: 1px solid rgba(148, 163, 184, 0.2); border-radius: 8px; padding: 12px; background: rgba(255,255,255,0.035); }
            .cover-extracted-note { margin-bottom: 10px; color: #bfdbfe; background: rgba(59, 130, 246, 0.12); border: 1px solid rgba(96, 165, 250, 0.26); border-radius: 8px; padding: 8px 10px; font-size: 12px; line-height: 1.5; }
            .cover-extracted-warning { color: #fde68a; background: rgba(245, 158, 11, 0.12); border-color: rgba(245, 158, 11, 0.28); }
            .cover-extracted-row { display: grid; grid-template-columns: 104px minmax(0, 1fr); gap: 10px; padding: 7px 0; border-top: 1px solid rgba(148, 163, 184, 0.15); color: var(--text-secondary); font-size: 12px; line-height: 1.55; }
            .cover-extracted-row:first-of-type { border-top: 0; }
            .cover-extracted-row strong { color: var(--text-primary); font-weight: 600; }
            .cover-empty, .cover-loading, .cover-history-empty { min-height: 180px; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 10px; color: var(--text-secondary); text-align: center; }
            .cover-empty i, .cover-loading i { font-size: 32px; color: #a5b4fc; }
            .cover-result { display: grid; gap: 10px; }
            .cover-image-open { display: block; width: 100%; padding: 0; border: 0; background: transparent; cursor: zoom-in; }
            .cover-result-image { width: 100%; object-fit: cover; border-radius: 8px; border: 1px solid var(--border-color); background: rgba(0,0,0,0.25); }
            .cover-result-meta { font-size: 12px; color: var(--text-secondary); word-break: break-all; }
            .cover-result-actions { display: flex; flex-wrap: wrap; gap: 8px; }
            .cover-result-actions .cover-btn, .cover-lightbox-actions .cover-btn { text-decoration: none; }
            .cover-save-note { display: flex; align-items: flex-start; gap: 8px; color: #fde68a; background: rgba(245, 158, 11, 0.12); border: 1px solid rgba(245, 158, 11, 0.28); border-radius: 8px; padding: 8px 10px; font-size: 12px; line-height: 1.5; }
            .cover-history-list { display: grid; gap: 10px; margin-top: 14px; }
            .cover-history-toolbar { display: flex; align-items: center; justify-content: space-between; gap: 10px; margin-top: 12px; padding-top: 12px; border-top: 1px solid var(--border-color); }
            .cover-history-select-all { display: inline-flex; align-items: center; gap: 7px; color: var(--text-secondary); font-size: 12px; }
            .cover-history-item { display: grid; grid-template-columns: 18px 56px minmax(0, 1fr) 32px; gap: 10px; align-items: center; border-top: 1px solid var(--border-color); padding-top: 10px; }
            .cover-history-item.selected { background: rgba(99, 102, 241, 0.1); border-radius: 8px; padding: 10px 8px 0; }
            .cover-history-check { width: 16px; height: 16px; accent-color: #818cf8; }
            .cover-history-thumb-btn { width: 56px; height: 42px; border: 0; padding: 0; border-radius: 6px; overflow: hidden; background: rgba(0,0,0,0.25); cursor: zoom-in; }
            .cover-history-item img { width: 56px; height: 42px; object-fit: cover; border-radius: 6px; background: rgba(0,0,0,0.25); }
            .cover-history-item small { display: block; color: var(--text-secondary); margin-top: 4px; line-height: 1.35; }
            .cover-history-actions { display: flex; gap: 8px; margin-top: 5px; }
            .cover-history-actions a, .cover-history-actions button { border: 0; background: transparent; padding: 0; color: #a5b4fc; font-size: 12px; text-decoration: none; cursor: pointer; }
            .cover-icon-btn { width: 32px; height: 32px; border-radius: 8px; border: 1px solid transparent; background: transparent; color: var(--text-secondary); cursor: pointer; }
            .cover-icon-btn:hover { color: #ef4444; border-color: rgba(239, 68, 68, 0.4); background: rgba(239, 68, 68, 0.12); }
            .cover-lightbox { position: fixed; inset: 0; z-index: 1200; background: rgba(2, 6, 23, 0.78); backdrop-filter: blur(8px); display: flex; align-items: center; justify-content: center; padding: 24px; }
            .cover-lightbox-panel { width: min(960px, 96vw); max-height: 94vh; display: grid; gap: 12px; border: 1px solid rgba(148, 163, 184, 0.35); border-radius: 8px; background: rgba(15, 23, 42, 0.96); padding: 14px; box-shadow: 0 24px 80px rgba(0,0,0,0.42); }
            .cover-lightbox-header { display: flex; align-items: center; justify-content: space-between; gap: 12px; }
            .cover-lightbox-actions { display: flex; align-items: center; gap: 8px; }
            .cover-lightbox-image { width: 100%; max-height: calc(94vh - 140px); object-fit: contain; border-radius: 8px; background: rgba(0,0,0,0.3); }
            @media (max-width: 1180px) { .cover-layout { grid-template-columns: 1fr; } .cover-template-grid { max-height: none; } .cover-form-grid, .cover-custom-grid { grid-template-columns: 1fr; } }
        `;
        document.head.appendChild(style);
    }

    console.log('[app-cover-images.js] 小说封面生成模块已加载');
})();
