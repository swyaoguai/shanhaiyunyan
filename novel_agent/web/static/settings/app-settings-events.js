/**
 * 山海·云烟 - 设置页事件层
 */

function bindThemeSettingsEvents() {
    const content = document.getElementById('settings-content');
    if (!content) return;

    content.querySelectorAll('.theme-preset-btn').forEach((btn) => {
        btn.addEventListener('click', () => {
            const theme = btn.dataset.theme;
            setTheme(theme);

            content.querySelectorAll('.theme-preset-btn').forEach((button) => {
                button.classList.remove('active');
                button.style.borderColor = 'var(--border-color)';
            });

            btn.classList.add('active');
            btn.style.borderColor = 'var(--accent-color)';
            showToast(`已切换到「${btn.querySelector('div').textContent}」主题`);
        });
    });

    document.getElementById('hue-slider')?.addEventListener('input', (event) => {
        const hue = parseInt(event.target.value, 10);
        document.getElementById('hue-value').textContent = `${hue}°`;
        applyFullThemeFromHue(hue);
    });

    document.getElementById('saturation-slider')?.addEventListener('input', (event) => {
        const value = parseInt(event.target.value, 10);
        document.getElementById('saturation-value').textContent = `${value}%`;
        setSaturation(value);
    });

    document.getElementById('bg-lightness-slider')?.addEventListener('input', (event) => {
        const value = parseInt(event.target.value, 10);
        document.getElementById('bg-lightness-value').textContent = `${value}%`;
        setBackgroundLightness(value);
    });

    document.getElementById('text-lightness-slider')?.addEventListener('input', (event) => {
        const value = parseInt(event.target.value, 10);
        document.getElementById('text-lightness-value').textContent = `${value}%`;
        setTextLightness(value);
    });

    const overlaySlider = document.getElementById('overlay-opacity-slider');
    overlaySlider?.addEventListener('input', (event) => {
        const opacity = parseInt(event.target.value, 10) / 100;
        document.getElementById('overlay-opacity-value').textContent = `${event.target.value}%`;
        setOverlayOpacity(opacity);
    });

    const bgInput = document.getElementById('bg-image-input');
    const clearBgBtn = document.getElementById('clear-bg-btn');

    document.getElementById('select-bg-btn')?.addEventListener('click', () => bgInput?.click());

    bgInput?.addEventListener('change', (event) => {
        const file = event.target.files?.[0];
        if (!file) return;

        const reader = new FileReader();
        reader.onload = (readerEvent) => {
            setAppBackground(readerEvent.target.result);
            clearBgBtn.style.opacity = '1';
            clearBgBtn.style.pointerEvents = 'auto';
            const overlaySection = overlaySlider?.closest('div')?.parentElement;
            if (overlaySection) {
                overlaySection.style.opacity = '1';
                overlaySection.style.pointerEvents = 'auto';
            }
            loadThemeSettings();
        };
        reader.readAsDataURL(file);
    });

    clearBgBtn?.addEventListener('click', () => {
        clearAppBackground();
        clearBgBtn.style.opacity = '0.5';
        clearBgBtn.style.pointerEvents = 'none';
        const overlaySection = overlaySlider?.closest('div')?.parentElement;
        if (overlaySection) {
            overlaySection.style.opacity = '0.5';
            overlaySection.style.pointerEvents = 'none';
        }
        loadThemeSettings();
    });

    document.getElementById('save-theme-settings')?.addEventListener('click', () => {
        localStorage.setItem('theme_hue', store.settings.accentHue || 250);
        localStorage.setItem('theme_saturation', store.settings.accentSaturation || 40);
        localStorage.setItem('theme_bg_lightness', store.settings.bgLightness || 12);
        localStorage.setItem('theme_text_lightness', store.settings.textLightness || 90);
        localStorage.setItem('theme_opacity', store.settings.bgOpacity || 0.85);
        localStorage.setItem('theme_mode', store.settings.theme || 'dark');

        const saveStatus = document.getElementById('theme-save-status');
        saveStatus.innerHTML = '<i class="ri-check-line" style="color: #10b981;"></i> 设置已保存';
        showToast('主题设置已保存');

        setTimeout(() => {
            saveStatus.textContent = '';
        }, 3000);
    });
}

function bindGlobalAPISettingsEvents(timeoutSettings = {}) {
    const configSelect = document.getElementById('active-config-select');
    const modelSelect = document.getElementById('active-model-select');

    configSelect?.addEventListener('change', () => {
        const selectedConfig = currentApiConfigs.find((item) => item.id === configSelect.value);
        if (modelSelect) {
            modelSelect.innerHTML = renderModelOptions(selectedConfig);
        }
        const resultEl = document.getElementById('active-config-test-result');
        if (resultEl) {
            resultEl.innerHTML = renderApiTestResultPanel();
        }
    });

    document.getElementById('apply-active-config')?.addEventListener('click', async (event) => {
        const button = event.currentTarget;
        const configId = configSelect?.value;
        const model = modelSelect?.value;

        if (!configId) {
            showToast('请先选择一个配置', 'error');
            return;
        }
        if (!model) {
            showToast('请选择一个模型', 'error');
            return;
        }

        button.disabled = true;
        button.innerHTML = '<i class="ri-loader-4-line"></i> 应用中...';

        try {
            await saveActiveApiConfig(configId, model);
            showToast('配置已应用 ✓', 'success');
            const selectedConfig = currentApiConfigs.find((item) => item.id === configId);
            const statusEl = document.getElementById('active-config-status');
            if (statusEl && selectedConfig) {
                statusEl.textContent = `当前: ${selectedConfig.name} / ${model}`;
            }
            setTimeout(() => loadGlobalAPISettings(), 300);
        } catch (e) {
            showToast(`应用失败: ${e.message}`, 'error');
        } finally {
            button.disabled = false;
            button.innerHTML = '<i class="ri-check-line"></i> 应用配置';
        }
    });

    document.getElementById('save-timeout-settings')?.addEventListener('click', async (event) => {
        const button = event.currentTarget;
        const llmRanges = timeoutSettings.ranges?.llm || {};
        const shortStoryRange = timeoutSettings.ranges?.short_story || { min: 30, max: 600 };
        const llmFields = ['connect', 'read', 'write', 'pool'];
        const shortStoryFields = ['synopsis', 'outline', 'chapter', 'quality', 'coherence', 'title', 'tags'];
        const payload = { llm: {}, short_story: {} };

        for (const key of llmFields) {
            const input = document.getElementById(`llm-timeout-${key}`);
            const rawValue = input?.value?.trim() || '';
            const parsed = parseInt(rawValue, 10);
            const range = llmRanges[key] || { min: 1, max: 3600 };
            if (!rawValue || Number.isNaN(parsed)) {
                showToast('请填写完整的通用超时设置', 'error');
                input?.focus();
                return;
            }
            if (parsed < range.min || parsed > range.max) {
                showToast(`通用超时 ${key} 必须在 ${range.min}~${range.max} 秒之间`, 'error');
                input?.focus();
                return;
            }
            payload.llm[key] = parsed;
        }

        for (const key of shortStoryFields) {
            const input = document.getElementById(`short-story-timeout-${key}`);
            const rawValue = input?.value?.trim() || '';
            const parsed = parseInt(rawValue, 10);
            if (!rawValue || Number.isNaN(parsed)) {
                showToast('请填写完整的短篇超时设置', 'error');
                input?.focus();
                return;
            }
            if (parsed < shortStoryRange.min || parsed > shortStoryRange.max) {
                showToast(`短篇超时必须在 ${shortStoryRange.min}~${shortStoryRange.max} 秒之间`, 'error');
                input?.focus();
                return;
            }
            payload.short_story[key] = parsed;
        }

        button.disabled = true;
        button.innerHTML = '<i class="ri-loader-4-line"></i> 保存中...';

        try {
            await saveTimeoutSettings(payload);
            showToast('全局超时设置已保存', 'success');
        } catch (e) {
            showToast(`保存失败: ${e.message}`, 'error');
        } finally {
            button.disabled = false;
            button.innerHTML = '<i class="ri-save-line"></i> 保存全局超时设置';
        }
    });

    document.getElementById('test-active-config')?.addEventListener('click', async (event) => {
        const button = event.currentTarget;
        const configId = configSelect?.value;
        const model = modelSelect?.value;
        const resultEl = document.getElementById('active-config-test-result');

        if (!configId) {
            showToast('请先选择一个配置', 'error');
            return;
        }

        button.disabled = true;
        button.innerHTML = '<i class="ri-loader-4-line ri-spin"></i> 测试中...';
        if (resultEl) {
            resultEl.innerHTML = `
                <div class="settings-inline-panel-title">测试结果</div>
                <div class="settings-inline-panel-copy">我正在替你试连这套配置，稍等一下。</div>
            `;
        }

        try {
            const result = await testApiConnection(configId, model);
            if (resultEl) {
                resultEl.innerHTML = renderApiTestResultPanel(result);
            }
            if (result.success) {
                showToast(`连通了，${result.model_tested} 可以用，响应 ${result.response_time}ms。`, 'success');
            } else {
                showToast(result.error || '这次测试没过。', 'error');
            }
        } catch (e) {
            if (resultEl) {
                resultEl.innerHTML = renderApiTestResultPanel({
                    success: false,
                    error_code: 'request_failed',
                    title: '测试没跑通',
                    solution: '先看错误详情，再检查地址、模型和权限。',
                    detail: e.message || '请求失败，请稍后再试。',
                });
            }
            showToast(`测试失败: ${e.message}`, 'error');
        } finally {
            button.disabled = false;
            button.innerHTML = '<i class="ri-wifi-line"></i> 测试连接';
        }
    });

    document.getElementById('add-new-config')?.addEventListener('click', () => {
        editingConfigId = null;
        showConfigEditModal();
    });

    document.querySelectorAll('.edit-config-btn').forEach((btn) => {
        btn.addEventListener('click', (event) => {
            event.stopPropagation();
            editingConfigId = btn.dataset.configId;
            showConfigEditModal(btn.dataset.configId);
        });
    });

    document.querySelectorAll('.delete-config-btn').forEach((btn) => {
        btn.addEventListener('click', async (event) => {
            event.stopPropagation();
            const configId = btn.dataset.configId;
            const config = currentApiConfigs.find((item) => item.id === configId);
            if (!confirm(`确定要删除配置 "${config?.name || configId}" 吗？`)) {
                return;
            }
            try {
                await deleteApiConfig(configId);
                showToast('配置已删除');
                loadGlobalAPISettings();
            } catch (e) {
                showToast(`删除失败: ${e.message}`, 'error');
            }
        });
    });

    const modal = document.getElementById('config-edit-modal');
    modal?.addEventListener('click', (event) => {
        if (event.target === modal) {
            modal.style.display = 'none';
        }
    });
}

function showConfigEditModal(configId = null) {
    const modal = document.getElementById('config-edit-modal');
    const contentEl = document.getElementById('config-edit-content');
    if (!modal || !contentEl) return;

    const config = configId ? currentApiConfigs.find((item) => item.id === configId) : null;
    const isEdit = !!config;

    const currentApiType = config?.api_type || 'openai_chat';

    contentEl.innerHTML = `
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px;">
            <h3 style="color: var(--text-primary); font-size: 18px; margin: 0;">
                <i class="${isEdit ? 'ri-edit-line' : 'ri-add-line'}" style="margin-right: 8px; color: var(--accent-color);"></i>
                ${isEdit ? '编辑配置' : '新建配置'}
            </h3>
            <button id="close-config-modal" style="background: none; border: none; color: var(--text-secondary); cursor: pointer; font-size: 20px;"><i class="ri-close-line"></i></button>
        </div>
        <div style="display: grid; gap: 16px;">
            <div><label style="display: block; font-size: 13px; color: var(--text-secondary); margin-bottom: 8px;">配置名称 <span style="color: #ef4444;">*</span></label><input type="text" id="config-name" value="${safeAttr(config?.name || '')}" placeholder="例如: OpenAI官方、DeepSeek、本地Ollama..." style="width: 100%; background: rgba(0,0,0,0.3); border: 1px solid var(--border-color); padding: 12px; color: var(--text-primary); border-radius: 8px; font-size: 14px;"></div>
            <div>
                <label style="display: block; font-size: 13px; color: var(--text-secondary); margin-bottom: 8px;">API 类型 <span style="color: #ef4444;">*</span></label>
                <select id="config-api-type" style="width: 100%; background: rgba(0,0,0,0.3); border: 1px solid var(--border-color); padding: 12px; color: var(--text-primary); border-radius: 8px; font-size: 14px;">
                    <option value="openai_chat" ${currentApiType === 'openai_chat' ? 'selected' : ''}>OpenAI Chat（默认）</option>
                    <option value="openai_responses" ${currentApiType === 'openai_responses' ? 'selected' : ''}>OpenAI Responses（新版）</option>
                    <option value="anthropic" ${currentApiType === 'anthropic' ? 'selected' : ''}>Anthropic（原生）</option>
                </select>
                <div id="api-type-hint" style="font-size: 12px; color: var(--text-secondary); margin-top: 6px;">
                    ${currentApiType === 'anthropic' ? 'Anthropic 使用原生消息接口，需要填写 Base URL（如 https://api.anthropic.com 或中转地址）' : '使用 OpenAI 兼容的聊天补全端点'}
                </div>
            </div>
            <div><label style="display: block; font-size: 13px; color: var(--text-secondary); margin-bottom: 8px;">API Base URL <span style="color: #ef4444;">*</span></label><input type="text" id="config-api-base" value="${safeAttr(config?.api_base || '')}" placeholder="${currentApiType === 'anthropic' ? 'https://api.anthropic.com 或中转地址' : 'https://api.openai.com/v1'}" style="width: 100%; background: rgba(0,0,0,0.3); border: 1px solid var(--border-color); padding: 12px; color: var(--text-primary); border-radius: 8px; font-size: 14px;"></div>
            <div>
                <label style="display: block; font-size: 13px; color: var(--text-secondary); margin-bottom: 8px;">API Key ${config?.api_key_set ? '<span style="color: #10b981; font-size: 12px; margin-left: 8px;">✓ 已配置</span>' : ''}</label>
                <div style="position: relative;">
                    <input type="password" id="config-api-key" value="" placeholder="${config?.api_key_set ? '已保存，如需修改请输入新Key' : '请输入API Key'}" data-configured="${config?.api_key_set || false}" style="width: 100%; background: rgba(0,0,0,0.3); border: 1px solid var(--border-color); padding: 12px; color: var(--text-primary); border-radius: 8px; font-size: 14px; padding-right: 50px;">
                    <button id="toggle-config-key" style="position: absolute; right: 12px; top: 50%; transform: translateY(-50%); background: none; border: none; color: var(--text-secondary); cursor: pointer;"><i class="ri-eye-line"></i></button>
                </div>
            </div>
            <div>
                <label style="display: block; font-size: 13px; color: var(--text-secondary); margin-bottom: 8px;">模型列表 <span style="font-size: 11px; color: var(--text-secondary);">（同一URL可配置多个模型）</span></label>
                <div id="models-container" style="display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 10px;">
                    ${(config?.models || []).map((model) => `
                        <span class="model-tag" data-model="${safeAttr(model)}" style="background: rgba(59,130,246,0.2); color: #60a5fa; padding: 6px 12px; border-radius: 6px; font-size: 13px; display: flex; align-items: center; gap: 6px;">
                            ${safeText(model)}
                            <button class="remove-model-btn" data-model="${safeAttr(model)}" style="background: none; border: none; color: #60a5fa; cursor: pointer; padding: 0; line-height: 1;"><i class="ri-close-line"></i></button>
                        </span>
                    `).join('')}
                </div>
                <div style="display: flex; gap: 8px;">
                    <input type="text" id="new-model-input" placeholder="输入模型名称，如 gpt-4o" style="flex: 1; background: rgba(0,0,0,0.3); border: 1px solid var(--border-color); padding: 10px; color: var(--text-primary); border-radius: 6px; font-size: 13px;">
                    <button id="add-model-btn" style="padding: 10px 16px; background: rgba(59,130,246,0.2); border: 1px solid rgba(59,130,246,0.5); color: #60a5fa; border-radius: 6px; cursor: pointer;"><i class="ri-add-line"></i> 添加</button>
                    <button id="fetch-models-btn" style="padding: 10px 16px; background: rgba(255,255,255,0.1); border: 1px solid var(--border-color); color: var(--text-primary); border-radius: 6px; cursor: pointer;" title="从API获取模型列表"><i class="ri-download-line"></i> 获取</button>
                </div>
            </div>
            <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 16px;">
                <div><label style="display: block; font-size: 13px; color: var(--text-secondary); margin-bottom: 8px;">温度参数</label><input type="number" id="config-temperature" value="${config?.temperature ?? 0.7}" min="0" max="2" step="0.1" style="width: 100%; background: rgba(0,0,0,0.3); border: 1px solid var(--border-color); padding: 12px; color: var(--text-primary); border-radius: 8px; font-size: 14px;"></div>
                <div><label style="display: block; font-size: 13px; color: var(--text-secondary); margin-bottom: 8px;">最大输出长度</label><input type="number" id="config-max-tokens" value="${config?.max_tokens || 4096}" min="100" max="128000" step="100" style="width: 100%; background: rgba(0,0,0,0.3); border: 1px solid var(--border-color); padding: 12px; color: var(--text-primary); border-radius: 8px; font-size: 14px;"></div>
            </div>
        </div>
        <div style="margin-top: 24px; display: flex; gap: 12px; justify-content: flex-end;">
            <button id="cancel-config-btn" style="padding: 12px 24px; background: rgba(255,255,255,0.1); border: 1px solid var(--border-color); color: var(--text-primary); border-radius: 8px; cursor: pointer;">取消</button>
            <button id="save-config-btn" style="padding: 12px 24px; background: var(--accent-color); border: none; color: white; border-radius: 8px; cursor: pointer; font-weight: 500;"><i class="ri-save-line"></i> ${isEdit ? '保存修改' : '创建配置'}</button>
        </div>
    `;

    modal.style.display = 'flex';

    let currentModels = config?.models ? [...config.models] : [];
    const renderModelTags = () => {
        document.getElementById('models-container').innerHTML = currentModels.map((model) => `
            <span class="model-tag" data-model="${safeAttr(model)}" style="background: rgba(59,130,246,0.2); color: #60a5fa; padding: 6px 12px; border-radius: 6px; font-size: 13px; display: flex; align-items: center; gap: 6px;">
                ${safeText(model)}
                <button class="remove-model-btn" data-model="${safeAttr(model)}" style="background: none; border: none; color: #60a5fa; cursor: pointer; padding: 0; line-height: 1;"><i class="ri-close-line"></i></button>
            </span>
        `).join('');
        document.querySelectorAll('.remove-model-btn').forEach((btn) => {
            btn.addEventListener('click', () => {
                currentModels = currentModels.filter((model) => model !== btn.dataset.model);
                renderModelTags();
            });
        });
    };

    document.getElementById('close-config-modal')?.addEventListener('click', () => { modal.style.display = 'none'; });
    document.getElementById('cancel-config-btn')?.addEventListener('click', () => { modal.style.display = 'none'; });

    // API类型切换事件
    document.getElementById('config-api-type')?.addEventListener('change', (event) => {
        const selectedType = event.target.value;
        const hintEl = document.getElementById('api-type-hint');
        const apiBaseInput = document.getElementById('config-api-base');

        if (selectedType === 'anthropic') {
            if (hintEl) hintEl.textContent = 'Anthropic 使用原生消息接口，需要填写 Base URL（如 https://api.anthropic.com 或中转地址）';
            if (apiBaseInput) apiBaseInput.placeholder = 'https://api.anthropic.com 或中转地址';
        } else if (selectedType === 'openai_responses') {
            if (hintEl) hintEl.textContent = '使用 OpenAI Responses 端点（/v1/responses），需要兼容的 API Key';
            if (apiBaseInput) apiBaseInput.placeholder = 'https://api.openai.com/v1';
        } else {
            if (hintEl) hintEl.textContent = '使用 OpenAI 兼容的聊天补全端点';
            if (apiBaseInput) apiBaseInput.placeholder = 'https://api.openai.com/v1';
        }
    });

    document.getElementById('toggle-config-key')?.addEventListener('click', () => {
        const keyInput = document.getElementById('config-api-key');
        if (keyInput.type === 'password') {
            keyInput.type = 'text';
            document.getElementById('toggle-config-key').innerHTML = '<i class="ri-eye-off-line"></i>';
        } else {
            keyInput.type = 'password';
            document.getElementById('toggle-config-key').innerHTML = '<i class="ri-eye-line"></i>';
        }
    });

    const addModel = () => {
        const input = document.getElementById('new-model-input');
        const modelName = input?.value.trim();
        if (!modelName) return;
        if (currentModels.includes(modelName)) {
            showToast('该模型已存在', 'error');
            return;
        }
        currentModels.push(modelName);
        renderModelTags();
        input.value = '';
    };

    document.getElementById('add-model-btn')?.addEventListener('click', addModel);
    document.getElementById('new-model-input')?.addEventListener('keypress', (event) => {
        if (event.key === 'Enter') {
            event.preventDefault();
            addModel();
        }
    });

    renderModelTags();

    document.getElementById('fetch-models-btn')?.addEventListener('click', async (event) => {
        const button = event.currentTarget;
        const apiBase = document.getElementById('config-api-base')?.value;
        const apiKey = document.getElementById('config-api-key')?.value;
        const apiType = document.getElementById('config-api-type')?.value || 'openai_chat';
        if (!apiBase) {
            showToast('请先填写API Base URL', 'error');
            return;
        }
        button.disabled = true;
        button.innerHTML = '<i class="ri-loader-4-line"></i>';
        try {
            const requestData = { api_base: apiBase || '', api_key: apiKey || '', api_type: apiType };
            if (isEdit && !apiKey && editingConfigId) {
                requestData.config_id = editingConfigId;
            }
            const result = await fetchModelsForApiConfig(requestData);
            if (result.success && result.models && result.models.length > 0) {
                result.models.forEach((model) => {
                    if (!currentModels.includes(model)) {
                        currentModels.push(model);
                    }
                });
                renderModelTags();
                showToast(`获取到 ${result.models.length} 个模型`, 'success');
            } else {
                showToast(result.error || '未能获取模型列表，请手动输入', 'error');
            }
        } catch (e) {
            showToast(`获取失败: ${e.message}`, 'error');
        } finally {
            button.disabled = false;
            button.innerHTML = '<i class="ri-download-line"></i> 获取';
        }
    });

    document.getElementById('save-config-btn')?.addEventListener('click', async (event) => {
        const button = event.currentTarget;
        const name = document.getElementById('config-name')?.value.trim();
        const apiBase = document.getElementById('config-api-base')?.value.trim();
        const apiKey = document.getElementById('config-api-key')?.value.trim();
        const apiType = document.getElementById('config-api-type')?.value || 'openai_chat';
        const temperature = parseFloat(document.getElementById('config-temperature')?.value) || 0.7;
        const maxTokens = parseInt(document.getElementById('config-max-tokens')?.value, 10) || 4096;
        if (!name) {
            showToast('请输入配置名称', 'error');
            return;
        }
        if (!apiBase) {
            showToast('请输入API Base URL', 'error');
            return;
        }

        button.disabled = true;
        button.innerHTML = '<i class="ri-loader-4-line"></i> 保存中...';

        try {
            if (isEdit) {
                const updateData = { name, api_base: apiBase, models: currentModels, temperature, max_tokens: maxTokens, api_type: apiType };
                if (apiKey) {
                    updateData.api_key = apiKey;
                }
                await updateApiConfig(editingConfigId, updateData);
                showToast('配置已更新 ✓', 'success');
            } else {
                await createApiConfig({ name, api_base: apiBase, api_key: apiKey, models: currentModels, temperature, max_tokens: maxTokens, api_type: apiType });
                showToast('配置已创建 ✓', 'success');
            }
            modal.style.display = 'none';
            loadGlobalAPISettings();
        } catch (e) {
            showToast(`保存失败: ${e.message}`, 'error');
        } finally {
            button.disabled = false;
            button.innerHTML = `<i class="ri-save-line"></i> ${isEdit ? '保存修改' : '创建配置'}`;
        }
    });
}

function bindAgentSettingsEvents() {
    const content = document.getElementById('settings-content');
    if (!content) return;

    content.querySelectorAll('.agent-override-toggle').forEach((toggle) => {
        toggle.addEventListener('change', (event) => {
            const card = event.target.closest('.agent-config-card');
            card.querySelector('.agent-config-fields').style.display = event.target.checked ? 'grid' : 'none';
        });
    });

    content.querySelectorAll('.agent-api-config').forEach((select) => {
        select.addEventListener('change', (event) => {
            const agentId = event.target.dataset.agent;
            const modelSelect = content.querySelector(`.agent-model-select[data-agent="${agentId}"]`);
            if (modelSelect) {
                modelSelect.innerHTML = renderAgentModelOptions(event.target.value, '');
            }
            const card = event.target.closest('.agent-config-card');
            const resultEl = card?.querySelector('.agent-test-result');
            const statusEl = card?.querySelector('.agent-test-status');
            if (resultEl) {
                resultEl.style.display = 'none';
                resultEl.innerHTML = '';
            }
            if (statusEl) {
                statusEl.textContent = '测试当前Agent选中的API配置和模型';
            }
        });
    });

    content.querySelectorAll('.agent-test-config').forEach((button) => {
        button.addEventListener('click', async (event) => {
            const testButton = event.currentTarget;
            const card = testButton.closest('.agent-config-card');
            const agentId = card?.dataset.agent || testButton.dataset.agent || '';
            const configId = card?.querySelector('.agent-api-config')?.value || '';
            const model = card?.querySelector('.agent-model-select')?.value || '';
            const resultEl = card?.querySelector('.agent-test-result');
            const statusEl = card?.querySelector('.agent-test-status');

            if (!configId) {
                showToast('请先为这个Agent选择一个API配置', 'error');
                card?.querySelector('.agent-api-config')?.focus();
                return;
            }

            testButton.disabled = true;
            testButton.innerHTML = '<i class="ri-loader-4-line ri-spin"></i> 测试中...';
            if (statusEl) {
                statusEl.textContent = '正在测试当前Agent的独立配置...';
            }
            if (resultEl) {
                resultEl.style.display = 'block';
                resultEl.innerHTML = `
                    <div class="settings-inline-panel-title">测试结果</div>
                    <div class="settings-inline-panel-copy">正在用这个Agent当前选中的API配置和模型发起试连。</div>
                `;
            }

            try {
                const result = await testAgentApiConnection(agentId, configId, model);
                if (resultEl) {
                    resultEl.innerHTML = renderApiTestResultPanel(result);
                }
                if (result.success) {
                    if (statusEl) {
                        statusEl.textContent = `已通过：${result.model_tested || model || '当前模型'} 可用`;
                    }
                    showToast(`${agentId} 连通了，${result.model_tested || model || '当前模型'} 可以用。`, 'success');
                } else {
                    if (statusEl) {
                        statusEl.textContent = '测试未通过，请查看下方详情';
                    }
                    showToast(result.error || `${agentId} 的连接测试没过。`, 'error');
                }
            } catch (e) {
                if (resultEl) {
                    resultEl.innerHTML = renderApiTestResultPanel({
                        success: false,
                        error_code: 'request_failed',
                        title: '测试没跑通',
                        solution: '先检查这个Agent选中的API配置、模型名称和权限。',
                        detail: e.message || '请求失败，请稍后再试。',
                    });
                }
                if (statusEl) {
                    statusEl.textContent = '测试请求失败';
                }
                showToast(`测试失败: ${e.message}`, 'error');
            } finally {
                testButton.disabled = false;
                testButton.innerHTML = '<i class="ri-wifi-line"></i> 测试连接';
            }
        });
    });

    document.getElementById('save-agent-configs')?.addEventListener('click', async (event) => {
        const button = event.currentTarget;
        button.disabled = true;
        button.innerHTML = '<i class="ri-loader-4-line"></i> 保存中...';

        try {
            for (const card of content.querySelectorAll('.agent-config-card')) {
                const agentId = card.dataset.agent;
                const override = card.querySelector('.agent-override-toggle').checked;
                if (override) {
                    const apiConfigId = card.querySelector('.agent-api-config').value;
                    const selectedConfig = agentPageApiConfigs.find((item) => item.id === apiConfigId);
                    const tempValue = card.querySelector('.agent-temperature').value.trim();
                    const tokensValue = card.querySelector('.agent-max-tokens').value.trim();
                    const payload = {
                        api_config_id: apiConfigId || '',
                        api_base: selectedConfig ? selectedConfig.api_base : '',
                        model: card.querySelector('.agent-model-select').value || '',
                        use_global: false,
                        temperature: tempValue !== '' ? parseFloat(tempValue) : 0.7,
                        max_tokens: tokensValue !== '' ? parseInt(tokensValue, 10) : 4096
                    };
                    await saveAgentConfig(agentId, payload);
                } else {
                    await saveAgentConfig(agentId, { use_global: true, api_config_id: '' });
                }
            }
            if (typeof checkGlobalAPIConfig === 'function') {
                await checkGlobalAPIConfig();
            }
            showToast('Agent配置已保存');
        } catch (e) {
            showToast(`保存失败: ${e.message}`, 'error');
        } finally {
            button.disabled = false;
            button.innerHTML = '<i class="ri-save-line"></i> 保存所有Agent配置';
        }
    });
}

function bindKnowledgeBaseEvents() {
    const toggleKeyBtn = document.getElementById('toggle-kb-key');
    const keyInput = document.getElementById('kb-siliconflow-key');
    const providerSelect = document.getElementById('kb-embedding-provider');
    const apiPanel = document.getElementById('kb-provider-api-panel');
    const localPanel = document.getElementById('kb-provider-local-panel');
    const testButton = document.getElementById('test-embedding-btn');

    const syncEmbeddingProviderPanels = () => {
        const provider = providerSelect?.value || 'api';
        const isLocal = provider === 'local_onnx';
        if (apiPanel) apiPanel.style.display = isLocal ? 'none' : '';
        if (localPanel) localPanel.style.display = isLocal ? '' : 'none';
        if (testButton) testButton.style.display = isLocal ? 'none' : '';
    };

    syncEmbeddingProviderPanels();
    providerSelect?.addEventListener('change', syncEmbeddingProviderPanels);

    toggleKeyBtn?.addEventListener('click', () => {
        if (keyInput.type === 'password') {
            keyInput.type = 'text';
            toggleKeyBtn.innerHTML = '<i class="ri-eye-off-line"></i>';
        } else {
            keyInput.type = 'password';
            toggleKeyBtn.innerHTML = '<i class="ri-eye-line"></i>';
        }
    });

    const collectKnowledgeBasePayload = () => {
        const apiKey = document.getElementById('kb-siliconflow-key')?.value || '';
        const payload = {
            embedding_provider: document.getElementById('kb-embedding-provider')?.value || 'api',
            siliconflow_base_url: document.getElementById('kb-siliconflow-base')?.value || 'https://api.siliconflow.cn/v1',
            siliconflow_model: document.getElementById('kb-siliconflow-model')?.value || 'BAAI/bge-m3',
            siliconflow_embedding_dim: parseInt(document.getElementById('kb-embedding-dim')?.value || '1024', 10),
            onnx_model_dir: document.getElementById('kb-onnx-model-dir')?.value || 'novel_agent/models/embedding/default',
            onnx_model_file: document.getElementById('kb-onnx-model-file')?.value || 'model.onnx',
            onnx_tokenizer_dir: '',
            onnx_max_length: parseInt(document.getElementById('kb-onnx-max-length')?.value || '512', 10),
            onnx_threads: null,
            onnx_pooling: document.getElementById('kb-onnx-pooling')?.value || 'cls',
            default_top_k: parseInt(document.getElementById('kb-top-k')?.value || '5', 10),
            vector_weight: parseFloat(document.getElementById('kb-vector-weight')?.value || '0.7'),
            fulltext_weight: parseFloat(document.getElementById('kb-fulltext-weight')?.value || '0.3'),
            chunk_size: parseInt(document.getElementById('kb-chunk-size')?.value || '500', 10),
            chunk_overlap: parseInt(document.getElementById('kb-chunk-overlap')?.value || '50', 10)
        };

        if (apiKey) {
            payload.siliconflow_api_key = apiKey;
        }
        return payload;
    };

    document.getElementById('install-onnx-package-btn')?.addEventListener('click', async (event) => {
        const button = event.currentTarget;
        const fileInput = document.getElementById('kb-onnx-package-file');
        const resultEl = document.getElementById('onnx-install-result');
        const file = fileInput?.files?.[0];
        if (!file) {
            showToast('请选择本地模型包 zip 文件', 'error');
            return;
        }

        button.disabled = true;
        button.innerHTML = '<i class="ri-loader-4-line ri-spin"></i> 安装中...';
        if (resultEl) resultEl.style.display = 'none';

        try {
            const result = await installLocalOnnxPackage(file);
            document.getElementById('kb-embedding-provider').value = 'local_onnx';
            document.getElementById('kb-onnx-model-dir').value = result.onnx_model_dir || 'novel_agent/models/embedding/default';
            document.getElementById('kb-onnx-model-file').value = result.onnx_model_file || 'model.onnx';
            document.getElementById('kb-onnx-max-length').value = result.onnx_max_length || 512;
            document.getElementById('kb-onnx-pooling').value = result.onnx_pooling || 'cls';
            syncEmbeddingProviderPanels();
            await saveKnowledgeBaseConfig(collectKnowledgeBasePayload());

            if (resultEl) {
                const modelName = result.metadata?.model_id || result.metadata?.base_model || '本地模型包';
                resultEl.innerHTML = `
                    <div style="background: rgba(16,185,129,0.2); border: 1px solid rgba(16,185,129,0.5); border-radius: 8px; padding: 12px; color: #10b981;">
                        <i class="ri-check-circle-line"></i> 已安装并启用：${safeText(modelName)}
                    </div>
                `;
                resultEl.style.display = 'block';
            }
            showToast('本地模型包已安装并启用');
            setTimeout(() => loadKnowledgeBaseSettings(), 800);
        } catch (e) {
            if (resultEl) {
                resultEl.innerHTML = `
                    <div style="background: rgba(239,68,68,0.2); border: 1px solid rgba(239,68,68,0.5); border-radius: 8px; padding: 12px; color: #ef4444;">
                        <i class="ri-error-warning-line"></i> 安装失败: ${safeErrorText(e)}
                    </div>
                `;
                resultEl.style.display = 'block';
            }
            showToast(`安装失败: ${e.message}`, 'error');
        } finally {
            button.disabled = false;
            button.innerHTML = '<i class="ri-upload-cloud-line"></i> 安装模型包';
        }
    });

    const summaryToggle = document.getElementById('cs-auto-summary-toggle');
    const summaryBadge = document.getElementById('cs-status-badge');
    summaryToggle?.addEventListener('change', async () => {
        const enabled = summaryToggle.checked;
        try {
            await apiCall('/api/chapter-summary-config', 'POST', {
                auto_summary_enabled: enabled
            });
            if (summaryBadge) {
                summaryBadge.textContent = enabled ? '已启用' : '未启用';
                summaryBadge.className = 'settings-badge ' + (enabled ? 'settings-badge--success' : 'settings-badge--muted');
            }
            const label = summaryToggle.closest('.settings-checkbox-label');
            const statusText = label?.querySelector('.settings-status-text');
            if (statusText) statusText.textContent = enabled ? '已启用' : '未启用';
            showToast(enabled ? '已开启章节自动摘要' : '已关闭章节自动摘要');
        } catch (e) {
            console.error('保存自动摘要设置失败:', e);
            summaryToggle.checked = !enabled;
            showToast(`保存自动摘要设置失败: ${e.message}`, 'error');
        }
    });

    document.getElementById('test-embedding-btn')?.addEventListener('click', async (event) => {
        const button = event.currentTarget;
        const resultEl = document.getElementById('embedding-test-result');

        button.disabled = true;
        button.innerHTML = '<i class="ri-loader-4-line ri-spin"></i> 测试中...';
        resultEl.style.display = 'none';

        try {
            const result = await testKnowledgeBaseConnection({
                api_base: document.getElementById('kb-siliconflow-base').value,
                api_key: document.getElementById('kb-siliconflow-key').value || '',
                model: document.getElementById('kb-siliconflow-model').value
            });

            if (result.success) {
                resultEl.innerHTML = `
                    <div style="background: rgba(16,185,129,0.2); border: 1px solid rgba(16,185,129,0.5); border-radius: 8px; padding: 12px; color: #10b981;">
                        <i class="ri-check-circle-line"></i> 连接成功！
                        <span style="margin-left: 8px;">模型: ${safeText(result.model)}</span>
                        <span style="margin-left: 8px;">向量维度: ${result.embedding_dim}</span>
                        <span style="margin-left: 8px;">响应时间: ${result.response_time}ms</span>
                    </div>
                `;
            } else {
                resultEl.innerHTML = `
                    <div style="background: rgba(239,68,68,0.2); border: 1px solid rgba(239,68,68,0.5); border-radius: 8px; padding: 12px; color: #ef4444;">
                        <i class="ri-error-warning-line"></i> 连接失败: ${safeText(result.error || '未知错误')}
                    </div>
                `;
            }

            resultEl.style.display = 'block';
        } catch (e) {
            resultEl.innerHTML = `
                <div style="background: rgba(239,68,68,0.2); border: 1px solid rgba(239,68,68,0.5); border-radius: 8px; padding: 12px; color: #ef4444;">
                    <i class="ri-error-warning-line"></i> 测试失败: ${safeErrorText(e)}
                </div>
            `;
            resultEl.style.display = 'block';
        } finally {
            button.disabled = false;
            button.innerHTML = '<i class="ri-wifi-line"></i> 测试连接';
        }
    });

    document.getElementById('save-kb-config')?.addEventListener('click', async (event) => {
        const button = event.currentTarget;
        button.disabled = true;
        button.innerHTML = '<i class="ri-loader-4-line ri-spin"></i> 保存中...';

        try {
            await saveKnowledgeBaseConfig(collectKnowledgeBasePayload());
            showToast('知识库配置已保存');
            setTimeout(() => loadKnowledgeBaseSettings(), 500);
        } catch (e) {
            showToast(`保存失败: ${e.message}`, 'error');
        } finally {
            button.disabled = false;
            button.innerHTML = '<i class="ri-save-line"></i> 保存知识库配置';
        }
    });

    document.getElementById('select-all-chapters')?.addEventListener('click', () => {
        const checkboxes = document.querySelectorAll('.chapter-checkbox');
        const allChecked = Array.from(checkboxes).every((checkbox) => checkbox.checked);
        checkboxes.forEach((checkbox) => {
            checkbox.checked = !allChecked;
        });
    });

    document.getElementById('delete-selected-chapters')?.addEventListener('click', async () => {
        const selected = Array.from(document.querySelectorAll('.chapter-checkbox:checked')).map((checkbox) => checkbox.value);
        if (selected.length === 0) {
            showToast('请先选择要删除的章节', 'error');
            return;
        }
        if (!confirm(`确定要删除选中的 ${selected.length} 个章节的知识库数据吗？\n\n此操作不可恢复！`)) {
            return;
        }
        const button = document.getElementById('delete-selected-chapters');
        button.disabled = true;
        button.innerHTML = '<i class="ri-loader-4-line ri-spin"></i> 删除中...';
        try {
            const result = await clearKnowledgeBaseData({ clear_all: false, chapter_ids: selected });
            if (result.success) {
                showToast(`已删除 ${selected.length} 个章节的知识库数据`);
                loadKnowledgeBaseSettings();
            } else {
                showToast(`删除失败: ${result.error}`, 'error');
            }
        } catch (e) {
            showToast(`删除失败: ${e.message}`, 'error');
        } finally {
            button.disabled = false;
            button.innerHTML = '<i class="ri-delete-bin-line"></i> 删除选中章节';
        }
    });

    document.getElementById('clear-all-kb')?.addEventListener('click', async () => {
        if (!confirm('⚠️ 确定要清空当前项目的所有知识库数据吗？\n\n此操作不可恢复！所有向量化数据将被永久删除。')) {
            return;
        }
        if (!confirm('再次确认：真的要删除所有知识库数据吗？')) {
            return;
        }
        const button = document.getElementById('clear-all-kb');
        button.disabled = true;
        button.innerHTML = '<i class="ri-loader-4-line ri-spin"></i> 清空中...';
        try {
            const result = await clearKnowledgeBaseData({ clear_all: true });
            if (result.success) {
                showToast('知识库数据已清空');
                loadKnowledgeBaseSettings();
            } else {
                showToast(`清空失败: ${result.error}`, 'error');
            }
        } catch (e) {
            showToast(`清空失败: ${e.message}`, 'error');
        } finally {
            button.disabled = false;
            button.innerHTML = '<i class="ri-delete-bin-7-line"></i> 清空当前项目所有知识库数据';
        }
    });
}

function bindRegexRuleEvents() {
    document.querySelectorAll('.delete-rule-btn').forEach((btn) => {
        btn.addEventListener('click', () => {
            btn.closest('.regex-rule-item')?.remove();
        });
    });

    document.getElementById('add-regex-rule')?.addEventListener('click', () => {
        const container = document.getElementById('regex-rules-container');
        const index = container.children.length;
        container.insertAdjacentHTML('beforeend', renderRegexRuleItem({ pattern: '', replacement: '', enabled: true, description: '' }, index));
        bindRegexRuleEvents();
    });

    document.getElementById('save-regex-rules')?.addEventListener('click', () => {
        const rules = [];
        document.querySelectorAll('.regex-rule-item').forEach((item) => {
            rules.push({
                pattern: item.querySelector('.rule-pattern').value,
                replacement: item.querySelector('.rule-replacement').value,
                enabled: item.querySelector('.rule-enabled').checked,
                description: item.querySelector('.rule-description').value
            });
        });
        saveRegexRules(rules);
        showToast('正则规则已保存');
    });
}

function bindSkillsSettingsEvents() {
    document.querySelectorAll('.delete-skill-btn').forEach((btn) => {
        btn.addEventListener('click', async (event) => {
            event.stopPropagation();
            const skillName = btn.dataset.skill;
            if (!confirm(`确定要删除技能“${skillName}”吗？\n\n此操作会删除整个技能目录和里面的所有文件，删掉后不能恢复。`)) {
                return;
            }
            btn.disabled = true;
            btn.innerHTML = '<i class="ri-loader-4-line ri-spin"></i>';
            try {
                await deleteSkill(skillName);
                showToast(`技能“${skillName}”已删除`);
                loadSkillsSettings();
            } catch (e) {
                showToast(`删除失败: ${e.message}`, 'error');
                btn.disabled = false;
                btn.innerHTML = '<i class="ri-delete-bin-line"></i>';
            }
        });
    });

    document.getElementById('save-skills-settings')?.addEventListener('click', async (event) => {
        const button = event.currentTarget;
        button.disabled = true;
        button.innerHTML = '<i class="ri-loader-4-line"></i> 保存中...';
        try {
            const skillsConfig = {};
            document.querySelectorAll('.skill-toggle').forEach((toggle) => {
                skillsConfig[toggle.dataset.skill] = toggle.checked;
            });
            await saveSkillsConfig(skillsConfig);
            showToast('技能设置已保存 ✓');
        } catch (e) {
            showToast(`保存失败: ${e.message}`, 'error');
        } finally {
            button.disabled = false;
            button.innerHTML = '<i class="ri-save-line"></i> 保存技能设置';
        }
    });
}

window.bindThemeSettingsEvents = bindThemeSettingsEvents;
window.bindGlobalAPISettingsEvents = bindGlobalAPISettingsEvents;
window.showConfigEditModal = showConfigEditModal;
window.bindAgentSettingsEvents = bindAgentSettingsEvents;
window.bindKnowledgeBaseEvents = bindKnowledgeBaseEvents;
window.bindRegexRuleEvents = bindRegexRuleEvents;
window.bindSkillsSettingsEvents = bindSkillsSettingsEvents;
