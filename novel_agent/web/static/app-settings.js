/**
 * 文思Agent - 设置模块
 * 包含：主题设置UI、API配置、Agent配置、正则规则、资料库配置
 */

// ===== 设置模块渲染 =====

function renderSettings() {
    updateBreadcrumbs(['设置']);

    // 简化的设置容器，不再有顶部标签页（使用左侧导航面板切换）
    ui.workspace.innerHTML = `
        <div class="settings-container" style="height: 100%; display: flex; flex-direction: column;">
            <div id="settings-content" style="flex: 1; padding: 24px; overflow-y: auto;"></div>
        </div>
    `;

    // 默认加载主题设置
    loadThemeSettings();
}

function loadSettingsTab(tabName) {
    switch (tabName) {
        case 'theme':
            loadThemeSettings();
            break;
        case 'api':
            loadGlobalAPISettings();
            break;
        case 'agents':
            loadAgentSettings();
            break;
        case 'knowledge':
            loadKnowledgeBaseSettings();
            break;
        case 'regex':
            loadRegexRulesSettings();
            break;
        case 'skills':
            loadSkillsSettings();
            break;
        case 'trends':
            // 热点搜索已整合到Skills，重定向到Skills设置
            loadSkillsSettings();
            break;
        case 'backup':
            loadBackupSettings();
            break;
        case 'resources':
            loadResourcesSettings();
            break;
    }
}

// ===== 主题设置 =====

function loadThemeSettings() {
    let content = document.getElementById('settings-content');

    // 如果容器不存在，先渲染设置页面
    if (!content) {
        renderSettings();
        content = document.getElementById('settings-content');
        if (!content) return; // 仍然不存在则退出
    }

    // 获取当前设置（使用与app-theme.js一致的存储键名）
    const currentTheme = localStorage.getItem('theme_mode') || 'dark';
    const currentHue = parseInt(localStorage.getItem('theme_hue') || '250');
    const currentSaturation = parseInt(localStorage.getItem('theme_saturation') || '40');
    const currentTextLightness = parseInt(localStorage.getItem('theme_text_lightness') || '90');
    const currentBgLightness = parseInt(localStorage.getItem('theme_bg_lightness') || '12');
    const currentBgOpacity = parseFloat(localStorage.getItem('theme_opacity') || '0.85');
    const hasBackground = !!store.settings.bgUrl;

    content.innerHTML = `
        <div style="max-width: 800px;">
            <h2 style="color: var(--text-primary); margin-bottom: 24px; font-size: 20px;">
                <i class="ri-palette-line" style="margin-right: 8px; color: var(--accent-color);"></i>
                主题设置
            </h2>
            
            <!-- 快捷主题 -->
            <div class="setting-section" style="background: rgba(0,0,0,0.2); border-radius: 12px; padding: 20px; margin-bottom: 20px;">
                <h3 style="color: var(--text-primary); margin-bottom: 16px; font-size: 15px;">快捷主题</h3>
                <div style="display: grid; grid-template-columns: repeat(5, 1fr); gap: 12px;">
                    <button class="theme-preset-btn ${currentTheme === 'dark' ? 'active' : ''}" data-theme="dark" style="padding: 16px; border-radius: 10px; border: 2px solid ${currentTheme === 'dark' ? 'var(--accent-color)' : 'var(--border-color)'}; background: linear-gradient(135deg, #1a1b23, #252836); cursor: pointer; transition: all 0.3s;">
                        <div style="color: #fff; font-weight: 500;">暗夜</div>
                        <div style="color: #9ca3af; font-size: 12px; margin-top: 4px;">护眼深色</div>
                    </button>
                    <button class="theme-preset-btn ${currentTheme === 'light' ? 'active' : ''}" data-theme="light" style="padding: 16px; border-radius: 10px; border: 2px solid ${currentTheme === 'light' ? 'var(--accent-color)' : 'var(--border-color)'}; background: linear-gradient(135deg, #f8fafc, #e2e8f0); cursor: pointer; transition: all 0.3s;">
                        <div style="color: #1e293b; font-weight: 500;">浅白</div>
                        <div style="color: #64748b; font-size: 12px; margin-top: 4px;">明亮清新</div>
                    </button>
                    <button class="theme-preset-btn ${currentTheme === 'green' ? 'active' : ''}" data-theme="green" style="padding: 16px; border-radius: 10px; border: 2px solid ${currentTheme === 'green' ? 'var(--accent-color)' : 'var(--border-color)'}; background: linear-gradient(135deg, #1a2318, #243022); cursor: pointer; transition: all 0.3s;">
                        <div style="color: #a7f3d0; font-weight: 500;">护眼绿</div>
                        <div style="color: #6ee7b7; font-size: 12px; margin-top: 4px;">舒适自然</div>
                    </button>
                    <button class="theme-preset-btn ${currentTheme === 'warm' ? 'active' : ''}" data-theme="warm" style="padding: 16px; border-radius: 10px; border: 2px solid ${currentTheme === 'warm' ? 'var(--accent-color)' : 'var(--border-color)'}; background: linear-gradient(135deg, #2d2418, #3d3020); cursor: pointer; transition: all 0.3s;">
                        <div style="color: #fcd34d; font-weight: 500;">暖光</div>
                        <div style="color: #fbbf24; font-size: 12px; margin-top: 4px;">温馨柔和</div>
                    </button>
                    <button class="theme-preset-btn ${currentTheme === 'blue' ? 'active' : ''}" data-theme="blue" style="padding: 16px; border-radius: 10px; border: 2px solid ${currentTheme === 'blue' ? 'var(--accent-color)' : 'var(--border-color)'}; background: linear-gradient(135deg, #0f172a, #1e3a5f); cursor: pointer; transition: all 0.3s;">
                        <div style="color: #93c5fd; font-weight: 500;">深蓝</div>
                        <div style="color: #60a5fa; font-size: 12px; margin-top: 4px;">专注沉浸</div>
                    </button>
                </div>
            </div>
            
            <!-- HSL 调节器 -->
            <div class="setting-section" style="background: rgba(0,0,0,0.2); border-radius: 12px; padding: 20px; margin-bottom: 20px;">
                <h3 style="color: var(--text-primary); margin-bottom: 16px; font-size: 15px;">
                    自定义调色
                    <span style="font-size: 12px; color: var(--text-secondary); font-weight: normal; margin-left: 8px;">精细调整颜色</span>
                </h3>
                
                <!-- 色相 -->
                <div style="margin-bottom: 20px;">
                    <div style="display: flex; justify-content: space-between; margin-bottom: 8px;">
                        <label style="color: var(--text-secondary); font-size: 13px;">色相 (Hue)</label>
                        <span id="hue-value" style="color: var(--accent-color); font-size: 13px;">${currentHue}°</span>
                    </div>
                    <input type="range" id="hue-slider" min="0" max="360" value="${currentHue}"
                        style="width: 100%; height: 8px; border-radius: 4px; -webkit-appearance: none; background: linear-gradient(to right,
                            hsl(0, 70%, 50%), hsl(60, 70%, 50%), hsl(120, 70%, 50%),
                            hsl(180, 70%, 50%), hsl(240, 70%, 50%), hsl(300, 70%, 50%), hsl(360, 70%, 50%)); cursor: pointer;">
                </div>
                
                <!-- 饱和度 -->
                <div style="margin-bottom: 20px;">
                    <div style="display: flex; justify-content: space-between; margin-bottom: 8px;">
                        <label style="color: var(--text-secondary); font-size: 13px;">饱和度 (Saturation)</label>
                        <span id="saturation-value" style="color: var(--accent-color); font-size: 13px;">${currentSaturation}%</span>
                    </div>
                    <input type="range" id="saturation-slider" min="0" max="100" value="${currentSaturation}"
                        style="width: 100%; height: 8px; border-radius: 4px; -webkit-appearance: none; background: linear-gradient(to right, #808080, var(--accent-color)); cursor: pointer;">
                </div>
                
                <!-- 背景亮度 -->
                <div style="margin-bottom: 20px;">
                    <div style="display: flex; justify-content: space-between; margin-bottom: 8px;">
                        <label style="color: var(--text-secondary); font-size: 13px;">背景亮度 (Background Lightness)</label>
                        <span id="bg-lightness-value" style="color: var(--accent-color); font-size: 13px;">${currentBgLightness}%</span>
                    </div>
                    <input type="range" id="bg-lightness-slider" min="0" max="100" value="${currentBgLightness}"
                        style="width: 100%; height: 8px; border-radius: 4px; -webkit-appearance: none; background: linear-gradient(to right, #000, #fff); cursor: pointer;">
                </div>
                
                <!-- 文字亮度 -->
                <div style="margin-bottom: 8px;">
                    <div style="display: flex; justify-content: space-between; margin-bottom: 8px;">
                        <label style="color: var(--text-secondary); font-size: 13px;">文字亮度 (Text Lightness)</label>
                        <span id="text-lightness-value" style="color: var(--accent-color); font-size: 13px;">${currentTextLightness}%</span>
                    </div>
                    <input type="range" id="text-lightness-slider" min="0" max="100" value="${currentTextLightness}"
                        style="width: 100%; height: 8px; border-radius: 4px; -webkit-appearance: none; background: linear-gradient(to right, #000, #fff); cursor: pointer;">
                </div>
            </div>
            
            <!-- 背景图片设置 -->
            <div class="setting-section" style="background: rgba(0,0,0,0.2); border-radius: 12px; padding: 20px; margin-bottom: 20px;">
                <h3 style="color: var(--text-primary); margin-bottom: 16px; font-size: 15px;">
                    背景图片
                    <span style="font-size: 12px; color: var(--text-secondary); font-weight: normal; margin-left: 8px;">个性化背景</span>
                </h3>
                
                <div style="display: flex; gap: 12px; align-items: center; margin-bottom: 16px;">
                    <input type="file" id="bg-image-input" accept="image/*" style="display: none;">
                    <button id="select-bg-btn" style="padding: 10px 20px; background: rgba(255,255,255,0.1); border: 1px solid var(--border-color); color: var(--text-primary); border-radius: 8px; cursor: pointer;">
                        <i class="ri-image-add-line"></i> 选择图片
                    </button>
                    <button id="clear-bg-btn" style="padding: 10px 20px; background: rgba(239,68,68,0.2); border: 1px solid rgba(239,68,68,0.5); color: #ef4444; border-radius: 8px; cursor: pointer; ${hasBackground ? '' : 'opacity: 0.5; pointer-events: none;'}">
                        <i class="ri-delete-bin-line"></i> 清除背景
                    </button>
                    ${hasBackground ? '<span style="color: #10b981; font-size: 13px;"><i class="ri-check-line"></i> 已设置背景图</span>' : ''}
                </div>
                
                <!-- 叠加层透明度滑块 -->
                <div style="margin-bottom: 16px; ${hasBackground ? '' : 'opacity: 0.5; pointer-events: none;'}">
                    <div style="display: flex; justify-content: space-between; margin-bottom: 8px;">
                        <label style="color: var(--text-secondary); font-size: 13px;">
                            叠加层透明度
                            <span style="font-size: 11px; color: var(--text-secondary); margin-left: 4px;">(值越低背景图越清晰)</span>
                        </label>
                        <span id="overlay-opacity-value" style="color: var(--accent-color); font-size: 13px;">${Math.round(currentBgOpacity * 100)}%</span>
                    </div>
                    <input type="range" id="overlay-opacity-slider" min="0" max="100" value="${Math.round(currentBgOpacity * 100)}"
                        style="width: 100%; height: 8px; border-radius: 4px; -webkit-appearance: none; background: linear-gradient(to right, transparent, rgba(0,0,0,0.9)); cursor: pointer;">
                </div>
                
                <div style="color: var(--text-secondary); font-size: 12px;">
                    提示：设置背景图片后，调节「叠加层透明度」控制背景图片的显示强度
                </div>
            </div>
            
            <!-- 保存按钮 -->
            <div style="margin-top: 24px;">
                <button id="save-theme-settings" style="padding: 12px 24px; background: var(--accent-color); border: none; color: white; border-radius: 8px; cursor: pointer; font-weight: 500;">
                    <i class="ri-save-line"></i> 保存主题设置
                </button>
                <span id="theme-save-status" style="margin-left: 12px; color: var(--text-secondary); font-size: 13px;"></span>
            </div>
        </div>
    `;

    // 绑定主题预设按钮
    content.querySelectorAll('.theme-preset-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            const theme = btn.dataset.theme;
            setTheme(theme);

            // 更新按钮样式
            content.querySelectorAll('.theme-preset-btn').forEach(b => {
                b.classList.remove('active');
                b.style.borderColor = 'var(--border-color)';
            });
            btn.classList.add('active');
            btn.style.borderColor = 'var(--accent-color)';

            showToast(`已切换到「${btn.querySelector('div').textContent}」主题`);
        });
    });

    // 色相滑块
    const hueSlider = document.getElementById('hue-slider');
    const hueValue = document.getElementById('hue-value');
    hueSlider.addEventListener('input', (e) => {
        const hue = parseInt(e.target.value);
        hueValue.textContent = hue + '°';
        applyFullThemeFromHue(hue);
    });

    // 饱和度滑块
    const satSlider = document.getElementById('saturation-slider');
    const satValue = document.getElementById('saturation-value');
    satSlider.addEventListener('input', (e) => {
        const sat = parseInt(e.target.value);
        satValue.textContent = sat + '%';
        setSaturation(sat);
    });

    // 背景亮度滑块
    const bgLightSlider = document.getElementById('bg-lightness-slider');
    const bgLightValue = document.getElementById('bg-lightness-value');
    bgLightSlider.addEventListener('input', (e) => {
        const light = parseInt(e.target.value);
        bgLightValue.textContent = light + '%';
        setBackgroundLightness(light);
    });

    // 文字亮度滑块
    const lightSlider = document.getElementById('text-lightness-slider');
    const lightValue = document.getElementById('text-lightness-value');
    lightSlider.addEventListener('input', (e) => {
        const light = parseInt(e.target.value);
        lightValue.textContent = light + '%';
        setTextLightness(light);
    });

    // 叠加层透明度滑块
    const overlaySlider = document.getElementById('overlay-opacity-slider');
    const overlayValue = document.getElementById('overlay-opacity-value');
    overlaySlider.addEventListener('input', (e) => {
        const opacity = parseInt(e.target.value) / 100;
        overlayValue.textContent = e.target.value + '%';
        setOverlayOpacity(opacity);
    });

    // 背景图片
    const bgInput = document.getElementById('bg-image-input');
    const selectBgBtn = document.getElementById('select-bg-btn');
    const clearBgBtn = document.getElementById('clear-bg-btn');

    selectBgBtn.addEventListener('click', () => bgInput.click());

    bgInput.addEventListener('change', (e) => {
        const file = e.target.files[0];
        if (file) {
            const reader = new FileReader();
            reader.onload = (event) => {
                setAppBackground(event.target.result);
                clearBgBtn.style.opacity = '1';
                clearBgBtn.style.pointerEvents = 'auto';
                // 启用叠加层滑块
                const overlaySection = overlaySlider.closest('div').parentElement;
                overlaySection.style.opacity = '1';
                overlaySection.style.pointerEvents = 'auto';
                // 刷新页面以更新UI
                loadThemeSettings();
            };
            reader.readAsDataURL(file);
        }
    });

    clearBgBtn.addEventListener('click', () => {
        clearAppBackground();
        clearBgBtn.style.opacity = '0.5';
        clearBgBtn.style.pointerEvents = 'none';
        // 禁用叠加层滑块
        const overlaySection = overlaySlider.closest('div').parentElement;
        overlaySection.style.opacity = '0.5';
        overlaySection.style.pointerEvents = 'none';
        // 刷新页面以更新UI
        loadThemeSettings();
    });

    // 保存主题设置按钮
    const saveThemeBtn = document.getElementById('save-theme-settings');
    const saveStatus = document.getElementById('theme-save-status');
    saveThemeBtn.addEventListener('click', () => {
        // 保存所有当前设置到localStorage（实际上滑块变化时已经保存了，这里做个确认）
        localStorage.setItem('theme_hue', store.settings.accentHue || 250);
        localStorage.setItem('theme_saturation', store.settings.accentSaturation || 40);
        localStorage.setItem('theme_bg_lightness', store.settings.bgLightness || 12);
        localStorage.setItem('theme_text_lightness', store.settings.textLightness || 90);
        localStorage.setItem('theme_opacity', store.settings.bgOpacity || 0.85);
        localStorage.setItem('theme_mode', store.settings.theme || 'dark');

        saveStatus.innerHTML = '<i class="ri-check-line" style="color: #10b981;"></i> 设置已保存';
        showToast('主题设置已保存');

        setTimeout(() => {
            saveStatus.textContent = '';
        }, 3000);
    });
}

// ===== 全局API设置（多配置管理） =====

// 存储当前配置数据
let currentApiConfigs = [];
let currentActiveConfigId = '';
let currentActiveModel = '';
let editingConfigId = null;

async function loadGlobalAPISettings() {
    let content = document.getElementById('settings-content');

    // 如果容器不存在，先渲染设置页面
    if (!content) {
        renderSettings();
        content = document.getElementById('settings-content');
        if (!content) return;
    }

    content.innerHTML = `
        <div style="display: flex; align-items: center; justify-content: center; height: 200px;">
            <i class="ri-loader-4-line" style="font-size: 32px; color: var(--accent-color); animation: spin 1s linear infinite;"></i>
        </div>
    `;

    try {
        // 获取所有API配置
        const configsData = await apiCall('/api/api-configs');
        currentApiConfigs = configsData.configs || [];
        currentActiveConfigId = configsData.active_config_id || '';
        currentActiveModel = configsData.active_model || '';

        const hasConfigs = currentApiConfigs.length > 0;
        const activeConfig = currentApiConfigs.find(c => c.id === currentActiveConfigId);

        content.innerHTML = `
            <div style="max-width: 900px;">
                <h2 style="color: var(--text-primary); margin-bottom: 24px; font-size: 20px;">
                    <i class="ri-server-line" style="margin-right: 8px; color: var(--accent-color);"></i>
                    全局API配置
                    ${hasConfigs && activeConfig ? '<span style="background: #10b981; color: white; padding: 4px 10px; border-radius: 4px; font-size: 12px; margin-left: 12px;">已配置 ✓</span>' : '<span style="background: #f59e0b; color: white; padding: 4px 10px; border-radius: 4px; font-size: 12px; margin-left: 12px;">未配置</span>'}
                </h2>
                
                <p style="color: var(--text-secondary); margin-bottom: 20px; font-size: 13px;">
                    管理多个API配置，每个配置可包含多个模型。使用时通过下拉框选择当前使用的配置和模型。
                </p>
                
                <!-- 当前激活的配置选择器 -->
                <div class="setting-section" style="background: linear-gradient(135deg, rgba(16,185,129,0.1), rgba(59,130,246,0.1)); border-radius: 12px; padding: 20px; margin-bottom: 20px; border: 1px solid rgba(16,185,129,0.3);">
                    <h3 style="color: var(--text-primary); margin-bottom: 16px; font-size: 15px;">
                        <i class="ri-play-circle-line" style="margin-right: 6px; color: #10b981;"></i>
                        当前使用配置
                    </h3>
                    
                    <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 16px;">
                        <div>
                            <label style="display: block; font-size: 13px; color: var(--text-secondary); margin-bottom: 8px;">
                                选择API配置
                            </label>
                            <select id="active-config-select" style="width: 100%; background: rgba(0,0,0,0.3); border: 1px solid var(--border-color); padding: 12px; color: var(--text-primary); border-radius: 8px; font-size: 14px; cursor: pointer;">
                                ${!hasConfigs ? '<option value="">-- 请先添加配置 --</option>' : ''}
                                ${currentApiConfigs.map(cfg => `
                                    <option value="${cfg.id}" ${cfg.id === currentActiveConfigId ? 'selected' : ''}>
                                        ${cfg.name} (${cfg.api_base ? new URL(cfg.api_base).hostname : '未设置'})
                                    </option>
                                `).join('')}
                            </select>
                        </div>
                        
                        <div>
                            <label style="display: block; font-size: 13px; color: var(--text-secondary); margin-bottom: 8px;">
                                选择模型
                            </label>
                            <select id="active-model-select" style="width: 100%; background: rgba(0,0,0,0.3); border: 1px solid var(--border-color); padding: 12px; color: var(--text-primary); border-radius: 8px; font-size: 14px; cursor: pointer;">
                                ${renderModelOptions(activeConfig)}
                            </select>
                        </div>
                    </div>
                    
                    <div style="margin-top: 16px; display: flex; gap: 12px; align-items: center;">
                        <button id="apply-active-config" style="padding: 10px 20px; background: #10b981; border: none; color: white; border-radius: 8px; cursor: pointer; font-weight: 500;">
                            <i class="ri-check-line"></i> 应用配置
                        </button>
                        <button id="test-active-config" style="padding: 10px 20px; background: rgba(255,255,255,0.1); border: 1px solid var(--border-color); color: var(--text-primary); border-radius: 8px; cursor: pointer;">
                            <i class="ri-wifi-line"></i> 测试连接
                        </button>
                        <span id="active-config-status" style="color: var(--text-secondary); font-size: 13px; margin-left: auto;">
                            ${activeConfig ? `当前: ${activeConfig.name} / ${currentActiveModel || '未选择模型'}` : '未选择配置'}
                        </span>
                    </div>
                </div>
                
                <!-- 配置列表 -->
                <div class="setting-section" style="background: rgba(0,0,0,0.2); border-radius: 12px; padding: 20px; margin-bottom: 20px;">
                    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px;">
                        <h3 style="color: var(--text-primary); font-size: 15px; margin: 0;">
                            <i class="ri-list-check" style="margin-right: 6px;"></i>
                            配置列表 (${currentApiConfigs.length})
                        </h3>
                        <button id="add-new-config" style="padding: 8px 16px; background: var(--accent-color); border: none; color: white; border-radius: 6px; cursor: pointer; font-size: 13px;">
                            <i class="ri-add-line"></i> 新建配置
                        </button>
                    </div>
                    
                    <div id="config-list-container" style="display: grid; gap: 12px;">
                        ${currentApiConfigs.length === 0 ? `
                            <div style="text-align: center; padding: 40px; color: var(--text-secondary);">
                                <i class="ri-inbox-line" style="font-size: 48px; opacity: 0.5;"></i>
                                <p style="margin-top: 12px;">还没有API配置，点击上方"新建配置"添加</p>
                            </div>
                        ` : currentApiConfigs.map(cfg => renderConfigCard(cfg)).join('')}
                    </div>
                </div>
                
                <!-- 配置编辑弹窗容器 -->
                <div id="config-edit-modal" style="display: none; position: fixed; top: 0; left: 0; right: 0; bottom: 0; background: rgba(0,0,0,0.7); z-index: 1000; align-items: center; justify-content: center;">
                    <div style="background: var(--bg-panel); border-radius: 16px; padding: 24px; width: 90%; max-width: 600px; max-height: 90vh; overflow-y: auto; border: 1px solid var(--border-color);">
                        <div id="config-edit-content"></div>
                    </div>
                </div>
            </div>
        `;

        // 绑定事件
        bindGlobalAPISettingsEvents();

    } catch (e) {
        content.innerHTML = `
            <div style="text-align: center; padding: 40px; color: var(--text-secondary);">
                <i class="ri-error-warning-line" style="font-size: 48px; color: #ef4444;"></i>
                <p style="margin-top: 16px;">加载配置失败: ${e.message}</p>
            </div>
        `;
    }
}

// 渲染模型选项
function renderModelOptions(config) {
    if (!config || !config.models || config.models.length === 0) {
        return '<option value="">-- 请先添加模型 --</option>';
    }
    return config.models.map(model => `
        <option value="${model}" ${model === currentActiveModel ? 'selected' : ''}>${model}</option>
    `).join('');
}

// 渲染配置卡片
function renderConfigCard(cfg) {
    const isActive = cfg.id === currentActiveConfigId;
    const modelCount = cfg.models ? cfg.models.length : 0;

    return `
        <div class="config-card" data-config-id="${cfg.id}" style="background: ${isActive ? 'rgba(16,185,129,0.1)' : 'rgba(0,0,0,0.2)'}; border-radius: 10px; padding: 16px; border: 1px solid ${isActive ? 'rgba(16,185,129,0.5)' : 'var(--border-color)'}; transition: all 0.2s;">
            <div style="display: flex; justify-content: space-between; align-items: flex-start;">
                <div style="flex: 1;">
                    <div style="display: flex; align-items: center; gap: 10px; margin-bottom: 8px;">
                        <span style="font-size: 16px; font-weight: 500; color: var(--text-primary);">${cfg.name}</span>
                        ${isActive ? '<span style="background: #10b981; color: white; padding: 2px 8px; border-radius: 4px; font-size: 11px;">当前使用</span>' : ''}
                        ${cfg.api_key_set ? '<span style="color: #10b981; font-size: 12px;"><i class="ri-key-line"></i> 已配置Key</span>' : '<span style="color: #f59e0b; font-size: 12px;"><i class="ri-key-line"></i> 未配置Key</span>'}
                    </div>
                    <div style="color: var(--text-secondary); font-size: 13px; margin-bottom: 6px;">
                        <i class="ri-link" style="margin-right: 4px;"></i>
                        ${cfg.api_base || '未设置URL'}
                    </div>
                    <div style="display: flex; flex-wrap: wrap; gap: 6px; margin-top: 8px;">
                        ${cfg.models && cfg.models.length > 0 ? cfg.models.map(model => `
                            <span style="background: rgba(59,130,246,0.2); color: #60a5fa; padding: 3px 10px; border-radius: 4px; font-size: 12px;">
                                ${model}
                            </span>
                        `).join('') : '<span style="color: var(--text-secondary); font-size: 12px; font-style: italic;">无模型</span>'}
                    </div>
                </div>
                <div style="display: flex; gap: 8px;">
                    <button class="edit-config-btn" data-config-id="${cfg.id}" style="padding: 8px; background: rgba(255,255,255,0.1); border: 1px solid var(--border-color); color: var(--text-primary); border-radius: 6px; cursor: pointer;" title="编辑">
                        <i class="ri-edit-line"></i>
                    </button>
                    <button class="delete-config-btn" data-config-id="${cfg.id}" style="padding: 8px; background: rgba(239,68,68,0.1); border: 1px solid rgba(239,68,68,0.3); color: #ef4444; border-radius: 6px; cursor: pointer;" title="删除">
                        <i class="ri-delete-bin-line"></i>
                    </button>
                </div>
            </div>
            <div style="display: flex; gap: 16px; margin-top: 12px; padding-top: 12px; border-top: 1px solid var(--border-color); font-size: 12px; color: var(--text-secondary);">
                <span><i class="ri-cpu-line"></i> ${modelCount} 个模型</span>
                <span><i class="ri-settings-3-line"></i> Temperature: ${cfg.temperature ?? 0.7}</span>
                <span><i class="ri-file-text-line"></i> Max Tokens: ${cfg.max_tokens || 4096}</span>
            </div>
        </div>
    `;
}

// 绑定事件
function bindGlobalAPISettingsEvents() {
    // 配置选择变化时更新模型列表
    const configSelect = document.getElementById('active-config-select');
    const modelSelect = document.getElementById('active-model-select');

    if (configSelect) {
        configSelect.addEventListener('change', () => {
            const selectedConfig = currentApiConfigs.find(c => c.id === configSelect.value);
            if (modelSelect) {
                modelSelect.innerHTML = renderModelOptions(selectedConfig);
            }
        });
    }

    // 应用配置
    const applyBtn = document.getElementById('apply-active-config');
    if (applyBtn) {
        applyBtn.addEventListener('click', async () => {
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

            applyBtn.disabled = true;
            applyBtn.innerHTML = '<i class="ri-loader-4-line"></i> 应用中...';

            try {
                await apiCall('/api/api-configs/active', 'POST', {
                    config_id: configId,
                    model: model
                });

                showToast('配置已应用 ✓', 'success');
                currentActiveConfigId = configId;
                currentActiveModel = model;

                // 更新状态显示
                const statusEl = document.getElementById('active-config-status');
                const selectedConfig = currentApiConfigs.find(c => c.id === configId);
                if (statusEl && selectedConfig) {
                    statusEl.textContent = `当前: ${selectedConfig.name} / ${model}`;
                }

                // 刷新配置列表显示激活状态
                setTimeout(() => loadGlobalAPISettings(), 300);
            } catch (e) {
                showToast('应用失败: ' + e.message, 'error');
            } finally {
                applyBtn.disabled = false;
                applyBtn.innerHTML = '<i class="ri-check-line"></i> 应用配置';
            }
        });
    }

    // 测试连接
    const testBtn = document.getElementById('test-active-config');
    if (testBtn) {
        testBtn.addEventListener('click', async () => {
            const configId = configSelect?.value;
            const model = modelSelect?.value;
            const selectedConfig = currentApiConfigs.find(c => c.id === configId);

            if (!selectedConfig) {
                showToast('请先选择一个配置', 'error');
                return;
            }

            testBtn.disabled = true;
            testBtn.innerHTML = '<i class="ri-loader-4-line ri-spin"></i> 测试中...';

            try {
                const result = await apiCall('/api/test-connection', 'POST', {
                    api_base: selectedConfig.api_base,
                    config_id: configId,  // 传递配置ID，让后端从保存的配置中获取API Key
                    model: model || (selectedConfig.models ? selectedConfig.models[0] : '')
                });

                if (result.success) {
                    showToast(`连接成功！模型: ${result.model_tested}，响应: ${result.response_time}ms`, 'success');
                } else {
                    showToast('连接失败: ' + (result.error || '未知错误'), 'error');
                }
            } catch (e) {
                showToast('测试失败: ' + e.message, 'error');
            } finally {
                testBtn.disabled = false;
                testBtn.innerHTML = '<i class="ri-wifi-line"></i> 测试连接';
            }
        });
    }

    // 新建配置
    const addBtn = document.getElementById('add-new-config');
    if (addBtn) {
        addBtn.addEventListener('click', () => {
            editingConfigId = null;
            showConfigEditModal();
        });
    }

    // 编辑配置
    document.querySelectorAll('.edit-config-btn').forEach(btn => {
        btn.addEventListener('click', (e) => {
            e.stopPropagation();
            const configId = btn.dataset.configId;
            editingConfigId = configId;
            showConfigEditModal(configId);
        });
    });

    // 删除配置
    document.querySelectorAll('.delete-config-btn').forEach(btn => {
        btn.addEventListener('click', async (e) => {
            e.stopPropagation();
            const configId = btn.dataset.configId;
            const config = currentApiConfigs.find(c => c.id === configId);

            if (!confirm(`确定要删除配置 "${config?.name || configId}" 吗？`)) {
                return;
            }

            try {
                await apiCall(`/api/api-configs/${configId}`, 'DELETE');
                showToast('配置已删除');
                loadGlobalAPISettings();
            } catch (e) {
                showToast('删除失败: ' + e.message, 'error');
            }
        });
    });

    // 关闭弹窗（点击背景）
    const modal = document.getElementById('config-edit-modal');
    if (modal) {
        modal.addEventListener('click', (e) => {
            if (e.target === modal) {
                modal.style.display = 'none';
            }
        });
    }
}

// 显示配置编辑弹窗
function showConfigEditModal(configId = null) {
    const modal = document.getElementById('config-edit-modal');
    const contentEl = document.getElementById('config-edit-content');

    if (!modal || !contentEl) return;

    const config = configId ? currentApiConfigs.find(c => c.id === configId) : null;
    const isEdit = !!config;

    contentEl.innerHTML = `
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px;">
            <h3 style="color: var(--text-primary); font-size: 18px; margin: 0;">
                <i class="${isEdit ? 'ri-edit-line' : 'ri-add-line'}" style="margin-right: 8px; color: var(--accent-color);"></i>
                ${isEdit ? '编辑配置' : '新建配置'}
            </h3>
            <button id="close-config-modal" style="background: none; border: none; color: var(--text-secondary); cursor: pointer; font-size: 20px;">
                <i class="ri-close-line"></i>
            </button>
        </div>
        
        <div style="display: grid; gap: 16px;">
            <div>
                <label style="display: block; font-size: 13px; color: var(--text-secondary); margin-bottom: 8px;">
                    配置名称 <span style="color: #ef4444;">*</span>
                </label>
                <input type="text" id="config-name" value="${config?.name || ''}"
                    placeholder="例如: OpenAI官方、DeepSeek、本地Ollama..."
                    style="width: 100%; background: rgba(0,0,0,0.3); border: 1px solid var(--border-color); padding: 12px; color: var(--text-primary); border-radius: 8px; font-size: 14px;">
            </div>
            
            <div>
                <label style="display: block; font-size: 13px; color: var(--text-secondary); margin-bottom: 8px;">
                    API Base URL <span style="color: #ef4444;">*</span>
                </label>
                <input type="text" id="config-api-base" value="${config?.api_base || ''}"
                    placeholder="https://api.openai.com/v1"
                    style="width: 100%; background: rgba(0,0,0,0.3); border: 1px solid var(--border-color); padding: 12px; color: var(--text-primary); border-radius: 8px; font-size: 14px;">
            </div>
            
            <div>
                <label style="display: block; font-size: 13px; color: var(--text-secondary); margin-bottom: 8px;">
                    API Key
                    ${config?.api_key_set ? '<span style="color: #10b981; font-size: 12px; margin-left: 8px;">✓ 已配置</span>' : ''}
                </label>
                <div style="position: relative;">
                    <input type="password" id="config-api-key" value=""
                        placeholder="${config?.api_key_set ? '已保存，如需修改请输入新Key' : '请输入API Key'}"
                        data-configured="${config?.api_key_set || false}"
                        style="width: 100%; background: rgba(0,0,0,0.3); border: 1px solid var(--border-color); padding: 12px; color: var(--text-primary); border-radius: 8px; font-size: 14px; padding-right: 50px;">
                    <button id="toggle-config-key" style="position: absolute; right: 12px; top: 50%; transform: translateY(-50%); background: none; border: none; color: var(--text-secondary); cursor: pointer;">
                        <i class="ri-eye-line"></i>
                    </button>
                </div>
            </div>
            
            <div>
                <label style="display: block; font-size: 13px; color: var(--text-secondary); margin-bottom: 8px;">
                    模型列表
                    <span style="font-size: 11px; color: var(--text-secondary);">(同一URL可配置多个模型)</span>
                </label>
                <div id="models-container" style="display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 10px;">
                    ${(config?.models || []).map(model => `
                        <span class="model-tag" data-model="${model}" style="background: rgba(59,130,246,0.2); color: #60a5fa; padding: 6px 12px; border-radius: 6px; font-size: 13px; display: flex; align-items: center; gap: 6px;">
                            ${model}
                            <button class="remove-model-btn" data-model="${model}" style="background: none; border: none; color: #60a5fa; cursor: pointer; padding: 0; line-height: 1;">
                                <i class="ri-close-line"></i>
                            </button>
                        </span>
                    `).join('')}
                </div>
                <div style="display: flex; gap: 8px;">
                    <input type="text" id="new-model-input" placeholder="输入模型名称，如 gpt-4o"
                        style="flex: 1; background: rgba(0,0,0,0.3); border: 1px solid var(--border-color); padding: 10px; color: var(--text-primary); border-radius: 6px; font-size: 13px;">
                    <button id="add-model-btn" style="padding: 10px 16px; background: rgba(59,130,246,0.2); border: 1px solid rgba(59,130,246,0.5); color: #60a5fa; border-radius: 6px; cursor: pointer;">
                        <i class="ri-add-line"></i> 添加
                    </button>
                    <button id="fetch-models-btn" style="padding: 10px 16px; background: rgba(255,255,255,0.1); border: 1px solid var(--border-color); color: var(--text-primary); border-radius: 6px; cursor: pointer;" title="从API获取模型列表">
                        <i class="ri-download-line"></i> 获取
                    </button>
                </div>
            </div>
            
            <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 16px;">
                <div>
                    <label style="display: block; font-size: 13px; color: var(--text-secondary); margin-bottom: 8px;">
                        Temperature
                    </label>
                    <input type="number" id="config-temperature" value="${config?.temperature ?? 0.7}"
                        min="0" max="2" step="0.1"
                        style="width: 100%; background: rgba(0,0,0,0.3); border: 1px solid var(--border-color); padding: 12px; color: var(--text-primary); border-radius: 8px; font-size: 14px;">
                </div>
                <div>
                    <label style="display: block; font-size: 13px; color: var(--text-secondary); margin-bottom: 8px;">
                        Max Tokens
                    </label>
                    <input type="number" id="config-max-tokens" value="${config?.max_tokens || 4096}"
                        min="100" max="128000" step="100"
                        style="width: 100%; background: rgba(0,0,0,0.3); border: 1px solid var(--border-color); padding: 12px; color: var(--text-primary); border-radius: 8px; font-size: 14px;">
                </div>
            </div>
        </div>
        
        <div style="margin-top: 24px; display: flex; gap: 12px; justify-content: flex-end;">
            <button id="cancel-config-btn" style="padding: 12px 24px; background: rgba(255,255,255,0.1); border: 1px solid var(--border-color); color: var(--text-primary); border-radius: 8px; cursor: pointer;">
                取消
            </button>
            <button id="save-config-btn" style="padding: 12px 24px; background: var(--accent-color); border: none; color: white; border-radius: 8px; cursor: pointer; font-weight: 500;">
                <i class="ri-save-line"></i> ${isEdit ? '保存修改' : '创建配置'}
            </button>
        </div>
    `;

    modal.style.display = 'flex';

    // 当前弹窗中的模型列表
    let currentModels = config?.models ? [...config.models] : [];

    // 绑定弹窗事件
    document.getElementById('close-config-modal')?.addEventListener('click', () => {
        modal.style.display = 'none';
    });

    document.getElementById('cancel-config-btn')?.addEventListener('click', () => {
        modal.style.display = 'none';
    });

    // 切换密钥可见性
    const toggleKeyBtn = document.getElementById('toggle-config-key');
    const keyInput = document.getElementById('config-api-key');
    toggleKeyBtn?.addEventListener('click', () => {
        if (keyInput.type === 'password') {
            keyInput.type = 'text';
            toggleKeyBtn.innerHTML = '<i class="ri-eye-off-line"></i>';
        } else {
            keyInput.type = 'password';
            toggleKeyBtn.innerHTML = '<i class="ri-eye-line"></i>';
        }
    });

    // 添加模型
    const addModelBtn = document.getElementById('add-model-btn');
    const newModelInput = document.getElementById('new-model-input');
    const modelsContainer = document.getElementById('models-container');

    const addModelToList = () => {
        const modelName = newModelInput?.value.trim();
        if (!modelName) return;
        if (currentModels.includes(modelName)) {
            showToast('该模型已存在', 'error');
            return;
        }

        currentModels.push(modelName);
        renderModelTags();
        newModelInput.value = '';
    };

    addModelBtn?.addEventListener('click', addModelToList);
    newModelInput?.addEventListener('keypress', (e) => {
        if (e.key === 'Enter') {
            e.preventDefault();
            addModelToList();
        }
    });

    // 渲染模型标签
    const renderModelTags = () => {
        modelsContainer.innerHTML = currentModels.map(model => `
            <span class="model-tag" data-model="${model}" style="background: rgba(59,130,246,0.2); color: #60a5fa; padding: 6px 12px; border-radius: 6px; font-size: 13px; display: flex; align-items: center; gap: 6px;">
                ${model}
                <button class="remove-model-btn" data-model="${model}" style="background: none; border: none; color: #60a5fa; cursor: pointer; padding: 0; line-height: 1;">
                    <i class="ri-close-line"></i>
                </button>
            </span>
        `).join('');

        // 重新绑定删除按钮
        document.querySelectorAll('.remove-model-btn').forEach(btn => {
            btn.addEventListener('click', () => {
                const model = btn.dataset.model;
                currentModels = currentModels.filter(m => m !== model);
                renderModelTags();
            });
        });
    };

    // 初始绑定删除按钮
    document.querySelectorAll('.remove-model-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            const model = btn.dataset.model;
            currentModels = currentModels.filter(m => m !== model);
            renderModelTags();
        });
    });

    // 从API获取模型列表
    document.getElementById('fetch-models-btn')?.addEventListener('click', async () => {
        const apiBase = document.getElementById('config-api-base')?.value;
        const apiKey = document.getElementById('config-api-key')?.value;

        if (!apiBase) {
            showToast('请先填写API Base URL', 'error');
            return;
        }

        const btn = document.getElementById('fetch-models-btn');
        btn.disabled = true;
        btn.innerHTML = '<i class="ri-loader-4-line"></i>';

        try {
            // 构建请求数据，如果是编辑模式且没有输入新Key，传递config_id让后端使用保存的Key
            const requestData = {
                api_base: apiBase,
                api_key: apiKey || ''
            };
            
            // 如果是编辑模式且没有输入新的API Key，传递config_id
            if (isEdit && !apiKey && editingConfigId) {
                requestData.config_id = editingConfigId;
            }
            
            const result = await apiCall('/api/models', 'POST', requestData);

            if (result.success && result.models && result.models.length > 0) {
                // 添加获取到的模型（去重）
                result.models.forEach(model => {
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
            showToast('获取失败: ' + e.message, 'error');
        } finally {
            btn.disabled = false;
            btn.innerHTML = '<i class="ri-download-line"></i> 获取';
        }
    });

    // 保存配置
    document.getElementById('save-config-btn')?.addEventListener('click', async () => {
        const name = document.getElementById('config-name')?.value.trim();
        const apiBase = document.getElementById('config-api-base')?.value.trim();
        const apiKey = document.getElementById('config-api-key')?.value.trim();
        const temperature = parseFloat(document.getElementById('config-temperature')?.value) || 0.7;
        const maxTokens = parseInt(document.getElementById('config-max-tokens')?.value) || 4096;

        if (!name) {
            showToast('请输入配置名称', 'error');
            return;
        }
        if (!apiBase) {
            showToast('请输入API Base URL', 'error');
            return;
        }

        const btn = document.getElementById('save-config-btn');
        btn.disabled = true;
        btn.innerHTML = '<i class="ri-loader-4-line"></i> 保存中...';

        try {
            if (isEdit) {
                // 更新配置
                const updateData = {
                    name: name,
                    api_base: apiBase,
                    models: currentModels,
                    temperature: temperature,
                    max_tokens: maxTokens
                };

                // 只有输入了新的API Key才更新
                if (apiKey) {
                    updateData.api_key = apiKey;
                }

                await apiCall(`/api/api-configs/${editingConfigId}`, 'PUT', updateData);
                showToast('配置已更新 ✓', 'success');
            } else {
                // 新建配置
                await apiCall('/api/api-configs', 'POST', {
                    name: name,
                    api_base: apiBase,
                    api_key: apiKey,
                    models: currentModels,
                    temperature: temperature,
                    max_tokens: maxTokens
                });
                showToast('配置已创建 ✓', 'success');
            }

            modal.style.display = 'none';
            loadGlobalAPISettings();
        } catch (e) {
            showToast('保存失败: ' + e.message, 'error');
        } finally {
            btn.disabled = false;
            btn.innerHTML = `<i class="ri-save-line"></i> ${isEdit ? '保存修改' : '创建配置'}`;
        }
    });
}

// ===== Agent配置 =====

// 存储Agent配置页面用的API配置列表
let agentPageApiConfigs = [];
let agentPageActiveConfigId = '';

async function loadAgentSettings() {
    let content = document.getElementById('settings-content');

    // 如果容器不存在，先渲染设置页面
    if (!content) {
        renderSettings();
        content = document.getElementById('settings-content');
        if (!content) return;
    }

    content.innerHTML = `
        <div style="display: flex; align-items: center; justify-content: center; height: 200px;">
            <i class="ri-loader-4-line" style="font-size: 32px; color: var(--accent-color); animation: spin 1s linear infinite;"></i>
        </div>
    `;

    try {
        // 同时获取Agent配置和API配置
        const [agentData, apiConfigData] = await Promise.all([
            apiCall('/api/agents'),
            apiCall('/api/api-configs')
        ]);

        // 调试：打印返回的数据结构
        console.log('[AgentSettings] agentData:', JSON.stringify(agentData, null, 2));
        console.log('[AgentSettings] apiConfigData:', JSON.stringify(apiConfigData, null, 2));

        // 将agents数组转换为以name为key的对象，方便查找
        const agentsList = agentData.agents || [];
        const agents = {};
        agentsList.forEach(agent => {
            agents[agent.name] = agent;
            // 调试：打印每个agent的关键字段
            console.log(`[AgentSettings] Agent ${agent.name}:`, {
                api_config_id: agent.api_config_id,
                api_base: agent.api_base,
                model: agent.model,
                use_global: agent.use_global,
                temperature: agent.temperature,
                max_tokens: agent.max_tokens
            });
        });
        
        agentPageApiConfigs = apiConfigData.configs || [];
        agentPageActiveConfigId = apiConfigData.active_config_id || '';

        // 从后端获取的agents数据构建agentTypes数组
        const agentTypes = agentsList.map(agent => {
            // 为每个agent分配图标
            const iconMap = {
                'Outliner': 'ri-file-list-3-line',
                'Worldbuilder': 'ri-earth-line',
                'ChapterWriter': 'ri-quill-pen-line',
                'Polisher': 'ri-magic-line',
                'Evaluator': 'ri-star-line',
                'Communicator': 'ri-chat-3-line',
                'ContinuousWriter': 'ri-infinity-line',
                'ProjectScanner': 'ri-scan-line',
                'ContextStrategy': 'ri-route-line',
                'ContentReader': 'ri-file-text-line',
                'CreativeWriter': 'ri-quill-pen-fill',
                'ContentExpansion': 'ri-text-spacing',
                'QualityValidator': 'ri-shield-check-line',
                'FileNaming': 'ri-file-edit-line',
                'SummaryOrchestrator': 'ri-list-ordered',
                'ContextCompressor': 'ri-compasses-2-line',
                'FileEditor': 'ri-edit-box-line'
            };
            
            return {
                id: agent.name,
                name: agent.display_name || agent.name,
                icon: iconMap[agent.name] || 'ri-robot-line',
                desc: agent.description || '无描述'
            };
        });

        // 辅助函数：优先按已保存的 api_config_id 回显，缺失时回退到 api_base 反查
        const findApiConfigId = (config) => {
            const explicitId = String(config.api_config_id || '').trim();
            if (explicitId && agentPageApiConfigs.some(cfg => cfg.id === explicitId)) {
                return explicitId;
            }
            const apiBase = String(config.api_base || '').trim();
            if (!apiBase) return '';
            const sameBase = agentPageApiConfigs.filter(cfg => cfg.api_base === apiBase);
            if (sameBase.length === 0) return '';

            // 当同一 API Base 有多个配置时，优先用已保存模型反推正确配置
            const savedModel = String(config.model || '').trim();
            if (savedModel) {
                const modelMatched = sameBase.find(cfg => Array.isArray(cfg.models) && cfg.models.includes(savedModel));
                if (modelMatched) {
                    return modelMatched.id;
                }
            }

            return sameBase[0].id;
        };

        content.innerHTML = `
            <div style="max-width: 900px;">
                <h2 style="color: var(--text-primary); margin-bottom: 24px; font-size: 20px;">
                    <i class="ri-robot-line" style="margin-right: 8px; color: var(--accent-color);"></i>
                    Agent配置
                </h2>
                
                <p style="color: var(--text-secondary); margin-bottom: 24px; font-size: 14px;">
                    为各个Agent单独配置API和模型。启用"单独配置"后，可以选择不同的API配置和模型。
                </p>
                
                <div style="display: grid; gap: 16px;">
                    ${agentTypes.map(agent => {
            const config = agents[agent.id] || {};
            const isOverride = config.override || !config.use_global;
            // 关键修复：根据 api_base 反向查找匹配的 API 配置 ID
            const matchedApiConfigId = findApiConfigId(config);
            const savedModel = config.model || '';
            
            console.log(`[AgentSettings] 渲染 ${agent.id}: api_base=${config.api_base}, matchedConfigId=${matchedApiConfigId}, model=${savedModel}`);
            
            return `
                            <div class="agent-config-card" data-agent="${agent.id}" style="background: rgba(0,0,0,0.2); border-radius: 12px; padding: 20px; border: 1px solid var(--border-color);">
                                <div style="display: flex; align-items: center; gap: 16px; margin-bottom: 16px;">
                                    <div style="width: 48px; height: 48px; background: var(--accent-color); border-radius: 12px; display: flex; align-items: center; justify-content: center;">
                                        <i class="${agent.icon}" style="font-size: 24px; color: white;"></i>
                                    </div>
                                    <div>
                                        <h3 style="color: var(--text-primary); font-size: 16px; margin-bottom: 4px;">${agent.name}</h3>
                                        <p style="color: var(--text-secondary); font-size: 13px;">${agent.desc}</p>
                                    </div>
                                    <label style="margin-left: auto; display: flex; align-items: center; gap: 8px; cursor: pointer;">
                                        <input type="checkbox" class="agent-override-toggle" data-agent="${agent.id}" ${isOverride ? 'checked' : ''} style="width: 18px; height: 18px; accent-color: var(--accent-color);">
                                        <span style="color: var(--text-secondary); font-size: 13px;">单独配置</span>
                                    </label>
                                </div>
                                
                                <div class="agent-config-fields" style="display: ${isOverride ? 'grid' : 'none'}; grid-template-columns: 1fr 1fr; gap: 12px;">
                                    <div>
                                        <label style="display: block; font-size: 12px; color: var(--text-secondary); margin-bottom: 6px;">选择API配置</label>
                                        <select class="agent-api-config" data-agent="${agent.id}"
                                            style="width: 100%; background: rgba(0,0,0,0.3); border: 1px solid var(--border-color); padding: 10px; color: var(--text-primary); border-radius: 6px; font-size: 13px; cursor: pointer;">
                                            <option value="">-- 使用全局配置 --</option>
                                            ${agentPageApiConfigs.map(cfg => `
                                                <option value="${cfg.id}" ${matchedApiConfigId === cfg.id ? 'selected' : ''}>
                                                    ${cfg.name} (${cfg.api_base ? new URL(cfg.api_base).hostname : '未设置'})
                                                </option>
                                            `).join('')}
                                        </select>
                                    </div>
                                    <div>
                                        <label style="display: block; font-size: 12px; color: var(--text-secondary); margin-bottom: 6px;">选择模型</label>
                                        <select class="agent-model-select" data-agent="${agent.id}"
                                            style="width: 100%; background: rgba(0,0,0,0.3); border: 1px solid var(--border-color); padding: 10px; color: var(--text-primary); border-radius: 6px; font-size: 13px; cursor: pointer;">
                                            ${renderAgentModelOptions(matchedApiConfigId, savedModel)}
                                        </select>
                                    </div>
                                    <div>
                                        <label style="display: block; font-size: 12px; color: var(--text-secondary); margin-bottom: 6px;">Temperature</label>
                                        <input type="number" class="agent-temperature" data-agent="${agent.id}" value="${config.temperature !== undefined && config.temperature !== null ? config.temperature : ''}" placeholder="0.7" min="0" max="2" step="0.1"
                                            style="width: 100%; background: rgba(0,0,0,0.3); border: 1px solid var(--border-color); padding: 10px; color: var(--text-primary); border-radius: 6px; font-size: 13px;">
                                    </div>
                                    <div>
                                        <label style="display: block; font-size: 12px; color: var(--text-secondary); margin-bottom: 6px;">Max Tokens</label>
                                        <input type="number" class="agent-max-tokens" data-agent="${agent.id}" value="${config.max_tokens !== undefined && config.max_tokens !== null ? config.max_tokens : ''}" placeholder="4096" min="100" max="128000"
                                            style="width: 100%; background: rgba(0,0,0,0.3); border: 1px solid var(--border-color); padding: 10px; color: var(--text-primary); border-radius: 6px; font-size: 13px;">
                                    </div>
                                </div>
                            </div>
                        `;
        }).join('')}
                </div>
                
                <div style="margin-top: 24px;">
                    <button id="save-agent-configs" style="padding: 12px 24px; background: var(--accent-color); border: none; color: white; border-radius: 8px; cursor: pointer; font-weight: 500;">
                        <i class="ri-save-line"></i> 保存所有Agent配置
                    </button>
                </div>
            </div>
        `;

        // 绑定开关切换
        content.querySelectorAll('.agent-override-toggle').forEach(toggle => {
            toggle.addEventListener('change', (e) => {
                const card = e.target.closest('.agent-config-card');
                const fields = card.querySelector('.agent-config-fields');
                fields.style.display = e.target.checked ? 'grid' : 'none';
            });
        });

        // 绑定API配置选择变化 - 更新模型列表
        content.querySelectorAll('.agent-api-config').forEach(select => {
            select.addEventListener('change', (e) => {
                const agentId = e.target.dataset.agent;
                const configId = e.target.value;
                const modelSelect = content.querySelector(`.agent-model-select[data-agent="${agentId}"]`);
                if (modelSelect) {
                    modelSelect.innerHTML = renderAgentModelOptions(configId, '');
                }
            });
        });

        // 保存配置
        document.getElementById('save-agent-configs').addEventListener('click', async () => {
            const btn = document.getElementById('save-agent-configs');
            btn.disabled = true;
            btn.innerHTML = '<i class="ri-loader-4-line"></i> 保存中...';

            const configs = {};
            content.querySelectorAll('.agent-config-card').forEach(card => {
                const agentId = card.dataset.agent;
                const override = card.querySelector('.agent-override-toggle').checked;

                if (override) {
                    const apiConfigId = card.querySelector('.agent-api-config').value;
                    const selectedConfig = agentPageApiConfigs.find(c => c.id === apiConfigId);
                    const modelValue = card.querySelector('.agent-model-select').value;
                    
                    // 正确解析temperature和max_tokens，避免空字符串转换问题
                    const tempInput = card.querySelector('.agent-temperature');
                    const tokensInput = card.querySelector('.agent-max-tokens');
                    const tempValue = tempInput.value.trim();
                    const tokensValue = tokensInput.value.trim();

                    configs[agentId] = {
                        override: true,
                        api_config_id: apiConfigId,
                        api_base: selectedConfig ? selectedConfig.api_base : '',
                        model: modelValue,
                        // 使用更精确的解析逻辑
                        temperature: tempValue !== '' ? parseFloat(tempValue) : null,
                        max_tokens: tokensValue !== '' ? parseInt(tokensValue) : null
                    };
                    
                    // 调试：打印要保存的配置
                    console.log(`[AgentSettings] 保存 ${agentId}:`, {
                        api_config_id: apiConfigId,
                        api_base: configs[agentId].api_base,
                        model: modelValue,
                        temperature: configs[agentId].temperature,
                        max_tokens: configs[agentId].max_tokens
                    });
                } else {
                    configs[agentId] = { override: false };
                }
            });

            try {
                // 逐个保存Agent配置
                for (const [agentId, config] of Object.entries(configs)) {
                    if (config.override) {
                        // 构建保存数据，正确处理 null 值
                        const saveData = {
                            api_config_id: config.api_config_id || '',
                            api_base: config.api_base || '',
                            model: config.model || '',
                            use_global: false
                        };
                        
                        // 只有非 null 时才添加这些字段，使用实际值而非默认值
                        if (config.temperature !== null && !isNaN(config.temperature)) {
                            saveData.temperature = config.temperature;
                        } else {
                            saveData.temperature = 0.7;  // 默认值
                        }
                        
                        if (config.max_tokens !== null && !isNaN(config.max_tokens)) {
                            saveData.max_tokens = config.max_tokens;
                        } else {
                            saveData.max_tokens = 4096;  // 默认值
                        }
                        
                        await apiCall(`/api/agents/${agentId}`, 'POST', saveData);
                    } else {
                        await apiCall(`/api/agents/${agentId}`, 'POST', {
                            use_global: true,
                            api_config_id: ''
                        });
                    }
                }
                showToast('Agent配置已保存');
            } catch (e) {
                showToast('保存失败: ' + e.message, 'error');
            } finally {
                btn.disabled = false;
                btn.innerHTML = '<i class="ri-save-line"></i> 保存所有Agent配置';
            }
        });

    } catch (e) {
        content.innerHTML = `
            <div style="text-align: center; padding: 40px; color: var(--text-secondary);">
                <i class="ri-error-warning-line" style="font-size: 48px; color: #ef4444;"></i>
                <p style="margin-top: 16px;">加载Agent配置失败: ${e.message}</p>
            </div>
        `;
    }
}

// 渲染Agent的模型选项
function renderAgentModelOptions(configId, selectedModel) {
    if (!configId) {
        // 使用全局配置时，显示全局配置的模型
        const activeConfig = agentPageApiConfigs.find(c => c.id === agentPageActiveConfigId);
        if (activeConfig && activeConfig.models && activeConfig.models.length > 0) {
            return activeConfig.models.map(model => `
                <option value="${model}" ${model === selectedModel ? 'selected' : ''}>${model} (全局)</option>
            `).join('');
        }
        return '<option value="">-- 请先配置全局API --</option>';
    }

    // 使用指定配置的模型
    const config = agentPageApiConfigs.find(c => c.id === configId);
    if (config && config.models && config.models.length > 0) {
        return config.models.map(model => `
            <option value="${model}" ${model === selectedModel ? 'selected' : ''}>${model}</option>
        `).join('');
    }
    return '<option value="">-- 该配置无可用模型 --</option>';
}

// ===== 知识库配置（向量检索） =====

async function loadKnowledgeBaseSettings() {
    let content = document.getElementById('settings-content');

    // 如果容器不存在，先渲染设置页面
    if (!content) {
        renderSettings();
        content = document.getElementById('settings-content');
        if (!content) return;
    }

    content.innerHTML = `
        <div style="display: flex; align-items: center; justify-content: center; height: 200px;">
            <i class="ri-loader-4-line" style="font-size: 32px; color: var(--accent-color); animation: spin 1s linear infinite;"></i>
        </div>
    `;

    try {
        // 同时获取配置和统计信息
        const [config, stats] = await Promise.all([
            apiCall('/api/knowledge-base/config'),
            apiCall('/api/knowledge-base/stats')
        ]);

        // 判断向量化服务是否已配置
        const hasApiKey = config.siliconflow_api_key && config.siliconflow_api_key.length > 10;

        content.innerHTML = `
            <div style="max-width: 900px;">
                <h2 style="color: var(--text-primary); margin-bottom: 8px; font-size: 20px;">
                    <i class="ri-brain-line" style="margin-right: 8px; color: var(--accent-color);"></i>
                    知识库配置
                    <span style="font-size: 12px; color: var(--text-secondary); font-weight: normal; margin-left: 8px;">（向量检索系统）</span>
                </h2>
                
                <p style="color: var(--text-secondary); margin-bottom: 24px; font-size: 13px;">
                    知识库用于章节内容的向量化存储和语义检索，需要配置向量化API服务。
                    <br><span style="color: #f59e0b;">注意：这与左侧"资料库"（角色/物品/世界观设定）是不同的功能。</span>
                </p>
                
                <!-- 向量化服务配置 -->
                <div class="setting-section" style="background: linear-gradient(135deg, rgba(16,185,129,0.1), rgba(59,130,246,0.1)); border-radius: 12px; padding: 24px; margin-bottom: 20px; border: 1px solid ${hasApiKey ? 'rgba(16,185,129,0.5)' : 'rgba(239,68,68,0.5)'};">
                    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px;">
                        <h3 style="color: var(--text-primary); font-size: 15px; margin: 0;">
                            <i class="ri-cpu-line" style="margin-right: 6px; color: ${hasApiKey ? '#10b981' : '#ef4444'};"></i>
                            向量化服务配置
                            ${hasApiKey ? '<span style="background: #10b981; color: white; padding: 2px 8px; border-radius: 4px; font-size: 11px; margin-left: 8px;">已配置 ✓</span>' : '<span style="background: #ef4444; color: white; padding: 2px 8px; border-radius: 4px; font-size: 11px; margin-left: 8px;">未配置</span>'}
                        </h3>
                        <button id="test-embedding-btn" style="padding: 8px 16px; background: rgba(255,255,255,0.1); border: 1px solid var(--border-color); color: var(--text-primary); border-radius: 6px; cursor: pointer; font-size: 13px;">
                            <i class="ri-wifi-line"></i> 测试连接
                        </button>
                    </div>
                    
                    <p style="color: var(--text-secondary); font-size: 12px; margin-bottom: 16px;">
                        使用 <a href="https://cloud.siliconflow.cn/" target="_blank" style="color: var(--accent-color);">硅基流动</a> 提供的向量化API（免费额度充足）。
                        如无账号请先注册获取API Key。
                    </p>
                    
                    <div style="display: grid; gap: 16px;">
                        <div style="display: grid; grid-template-columns: 2fr 1fr; gap: 16px;">
                            <div>
                                <label style="display: block; font-size: 13px; color: var(--text-secondary); margin-bottom: 8px;">
                                    API Base URL
                                </label>
                                <input type="text" id="kb-siliconflow-base" value="${config.siliconflow_base_url || 'https://api.siliconflow.cn/v1'}"
                                    placeholder="https://api.siliconflow.cn/v1"
                                    style="width: 100%; background: rgba(0,0,0,0.3); border: 1px solid var(--border-color); padding: 12px; color: var(--text-primary); border-radius: 8px; font-size: 14px;">
                            </div>
                            <div>
                                <label style="display: block; font-size: 13px; color: var(--text-secondary); margin-bottom: 8px;">
                                    向量维度
                                </label>
                                <select id="kb-embedding-dim" style="width: 100%; background: rgba(0,0,0,0.3); border: 1px solid var(--border-color); padding: 12px; color: var(--text-primary); border-radius: 8px; font-size: 14px;">
                                    <option value="512" ${config.siliconflow_embedding_dim == 512 ? 'selected' : ''}>512</option>
                                    <option value="1024" ${config.siliconflow_embedding_dim == 1024 || !config.siliconflow_embedding_dim ? 'selected' : ''}>1024 (推荐)</option>
                                    <option value="2048" ${config.siliconflow_embedding_dim == 2048 ? 'selected' : ''}>2048</option>
                                </select>
                            </div>
                        </div>
                        
                        <div>
                            <label style="display: block; font-size: 13px; color: var(--text-secondary); margin-bottom: 8px;">
                                API Key <span style="color: #ef4444;">*</span>
                                ${hasApiKey ? '<span style="color: #10b981; font-size: 12px; margin-left: 8px;">✓ 已保存</span>' : ''}
                            </label>
                            <div style="position: relative;">
                                <input type="password" id="kb-siliconflow-key" value=""
                                    placeholder="${hasApiKey ? '已保存，如需修改请输入新Key' : '请输入硅基流动API Key (sk-...)'}"
                                    style="width: 100%; background: rgba(0,0,0,0.3); border: 1px solid var(--border-color); padding: 12px; color: var(--text-primary); border-radius: 8px; font-size: 14px; padding-right: 50px;">
                                <button id="toggle-kb-key" style="position: absolute; right: 12px; top: 50%; transform: translateY(-50%); background: none; border: none; color: var(--text-secondary); cursor: pointer;">
                                    <i class="ri-eye-line"></i>
                                </button>
                            </div>
                        </div>
                        
                        <div>
                            <label style="display: block; font-size: 13px; color: var(--text-secondary); margin-bottom: 8px;">
                                Embedding 模型
                            </label>
                            <select id="kb-siliconflow-model" style="width: 100%; background: rgba(0,0,0,0.3); border: 1px solid var(--border-color); padding: 12px; color: var(--text-primary); border-radius: 8px; font-size: 14px;">
                                <option value="BAAI/bge-m3" ${config.siliconflow_model === 'BAAI/bge-m3' || !config.siliconflow_model ? 'selected' : ''}>BAAI/bge-m3 (推荐，多语言)</option>
                                <option value="BAAI/bge-large-zh-v1.5" ${config.siliconflow_model === 'BAAI/bge-large-zh-v1.5' ? 'selected' : ''}>BAAI/bge-large-zh-v1.5 (中文优化)</option>
                                <option value="BAAI/bge-large-en-v1.5" ${config.siliconflow_model === 'BAAI/bge-large-en-v1.5' ? 'selected' : ''}>BAAI/bge-large-en-v1.5 (英文优化)</option>
                            </select>
                        </div>
                    </div>
                    
                    <div id="embedding-test-result" style="margin-top: 16px; display: none;"></div>
                </div>
                
                <!-- 知识库统计与管理 -->
                <div class="setting-section" style="background: rgba(0,0,0,0.2); border-radius: 12px; padding: 24px; margin-bottom: 20px;">
                    <h3 style="color: var(--text-primary); margin-bottom: 16px; font-size: 15px;">
                        <i class="ri-database-2-line" style="margin-right: 6px; color: #3b82f6;"></i>
                        知识库数据统计
                    </h3>
                    
                    <div style="display: grid; grid-template-columns: repeat(4, 1fr); gap: 16px; margin-bottom: 20px;">
                        <div style="background: rgba(0,0,0,0.2); padding: 16px; border-radius: 8px; text-align: center;">
                            <div style="font-size: 28px; font-weight: 600; color: var(--accent-color);">${stats.chapter_count || 0}</div>
                            <div style="font-size: 12px; color: var(--text-secondary); margin-top: 4px;">章节数</div>
                        </div>
                        <div style="background: rgba(0,0,0,0.2); padding: 16px; border-radius: 8px; text-align: center;">
                            <div style="font-size: 28px; font-weight: 600; color: #10b981;">${stats.chunk_count || 0}</div>
                            <div style="font-size: 12px; color: var(--text-secondary); margin-top: 4px;">分块数</div>
                        </div>
                        <div style="background: rgba(0,0,0,0.2); padding: 16px; border-radius: 8px; text-align: center;">
                            <div style="font-size: 28px; font-weight: 600; color: #f59e0b;">${stats.vector_count || 0}</div>
                            <div style="font-size: 12px; color: var(--text-secondary); margin-top: 4px;">向量数</div>
                        </div>
                        <div style="background: rgba(0,0,0,0.2); padding: 16px; border-radius: 8px; text-align: center;">
                            <div style="font-size: 28px; font-weight: 600; color: #ec4899;">${stats.storage_size_mb || 0}</div>
                            <div style="font-size: 12px; color: var(--text-secondary); margin-top: 4px;">存储 (MB)</div>
                        </div>
                    </div>
                    
                    ${stats.chapters && stats.chapters.length > 0 ? `
                        <div style="margin-bottom: 16px;">
                            <label style="display: block; font-size: 13px; color: var(--text-secondary); margin-bottom: 8px;">
                                按章节删除（选择要删除的章节向量数据）
                            </label>
                            <div id="chapter-list-container" style="max-height: 200px; overflow-y: auto; background: rgba(0,0,0,0.2); border-radius: 8px; border: 1px solid var(--border-color);">
                                ${stats.chapters.map(ch => `
                                    <label style="display: flex; align-items: center; padding: 10px 12px; border-bottom: 1px solid var(--border-color); cursor: pointer; transition: background 0.2s;"
                                        onmouseover="this.style.background='rgba(255,255,255,0.05)'"
                                        onmouseout="this.style.background='transparent'">
                                        <input type="checkbox" class="chapter-checkbox" value="${ch.chapter_id}" style="width: 18px; height: 18px; margin-right: 12px; accent-color: var(--accent-color);">
                                        <span style="color: var(--text-secondary); font-size: 12px; min-width: 50px;">第${ch.chapter_number}章</span>
                                        <span style="color: var(--text-primary); font-size: 13px; flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">${escapeHtml(ch.title)}</span>
                                    </label>
                                `).join('')}
                            </div>
                            <div style="display: flex; gap: 8px; margin-top: 12px;">
                                <button id="select-all-chapters" style="padding: 8px 16px; background: rgba(255,255,255,0.1); border: 1px solid var(--border-color); color: var(--text-primary); border-radius: 6px; cursor: pointer; font-size: 12px;">
                                    <i class="ri-checkbox-multiple-line"></i> 全选
                                </button>
                                <button id="delete-selected-chapters" style="padding: 8px 16px; background: rgba(239,68,68,0.2); border: 1px solid rgba(239,68,68,0.5); color: #ef4444; border-radius: 6px; cursor: pointer; font-size: 12px;">
                                    <i class="ri-delete-bin-line"></i> 删除选中章节
                                </button>
                            </div>
                        </div>
                    ` : `
                        <div style="text-align: center; padding: 20px; color: var(--text-secondary);">
                            <i class="ri-inbox-line" style="font-size: 32px; opacity: 0.5;"></i>
                            <p style="margin-top: 8px; font-size: 13px;">当前项目暂无向量化数据</p>
                        </div>
                    `}
                    
                    <div style="border-top: 1px solid rgba(239,68,68,0.3); padding-top: 16px; margin-top: 16px;">
                        <button id="clear-all-kb" style="padding: 10px 20px; background: rgba(239,68,68,0.15); border: 1px solid rgba(239,68,68,0.5); color: #ef4444; border-radius: 8px; cursor: pointer; font-weight: 500;">
                            <i class="ri-delete-bin-7-line"></i> 清空当前项目所有知识库数据
                        </button>
                        <p style="margin-top: 8px; font-size: 12px; color: var(--text-secondary);">
                            ⚠️ 此操作不可恢复，将删除当前项目的所有向量化数据
                        </p>
                    </div>
                </div>
                
                <!-- 检索参数设置 -->
                <div class="setting-section" style="background: rgba(0,0,0,0.2); border-radius: 12px; padding: 24px; margin-bottom: 20px;">
                    <h3 style="color: var(--text-primary); margin-bottom: 16px; font-size: 15px;">
                        <i class="ri-search-line" style="margin-right: 6px;"></i>
                        检索参数
                    </h3>
                    
                    <div style="display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 16px;">
                        <div>
                            <label style="display: block; font-size: 13px; color: var(--text-secondary); margin-bottom: 8px;">
                                检索数量 (Top-K)
                            </label>
                            <input type="number" id="kb-top-k" value="${config.default_top_k || 5}" min="1" max="20"
                                style="width: 100%; background: rgba(0,0,0,0.3); border: 1px solid var(--border-color); padding: 12px; color: var(--text-primary); border-radius: 8px; font-size: 14px;">
                        </div>
                        <div>
                            <label style="display: block; font-size: 13px; color: var(--text-secondary); margin-bottom: 8px;">
                                向量权重 (0-1)
                            </label>
                            <input type="number" id="kb-vector-weight" value="${config.vector_weight || 0.7}" min="0" max="1" step="0.1"
                                style="width: 100%; background: rgba(0,0,0,0.3); border: 1px solid var(--border-color); padding: 12px; color: var(--text-primary); border-radius: 8px; font-size: 14px;">
                        </div>
                        <div>
                            <label style="display: block; font-size: 13px; color: var(--text-secondary); margin-bottom: 8px;">
                                全文权重 (0-1)
                            </label>
                            <input type="number" id="kb-fulltext-weight" value="${config.fulltext_weight || 0.3}" min="0" max="1" step="0.1"
                                style="width: 100%; background: rgba(0,0,0,0.3); border: 1px solid var(--border-color); padding: 12px; color: var(--text-primary); border-radius: 8px; font-size: 14px;">
                        </div>
                    </div>
                </div>
                
                <!-- 分块设置 -->
                <div class="setting-section" style="background: rgba(0,0,0,0.2); border-radius: 12px; padding: 24px;">
                    <h3 style="color: var(--text-primary); margin-bottom: 16px; font-size: 15px;">
                        <i class="ri-scissors-line" style="margin-right: 6px;"></i>
                        文本分块设置
                    </h3>
                    
                    <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 16px;">
                        <div>
                            <label style="display: block; font-size: 13px; color: var(--text-secondary); margin-bottom: 8px;">
                                分块大小 (字符)
                            </label>
                            <input type="number" id="kb-chunk-size" value="${config.chunk_size || 500}" min="100" max="2000"
                                style="width: 100%; background: rgba(0,0,0,0.3); border: 1px solid var(--border-color); padding: 12px; color: var(--text-primary); border-radius: 8px; font-size: 14px;">
                        </div>
                        <div>
                            <label style="display: block; font-size: 13px; color: var(--text-secondary); margin-bottom: 8px;">
                                重叠大小 (字符)
                            </label>
                            <input type="number" id="kb-chunk-overlap" value="${config.chunk_overlap || 50}" min="0" max="500"
                                style="width: 100%; background: rgba(0,0,0,0.3); border: 1px solid var(--border-color); padding: 12px; color: var(--text-primary); border-radius: 8px; font-size: 14px;">
                        </div>
                    </div>
                </div>
                
                <div style="margin-top: 24px;">
                    <button id="save-kb-config" style="padding: 12px 24px; background: var(--accent-color); border: none; color: white; border-radius: 8px; cursor: pointer; font-weight: 500;">
                        <i class="ri-save-line"></i> 保存知识库配置
                    </button>
                </div>
            </div>
        `;

        // 绑定事件
        bindKnowledgeBaseEvents(config);

    } catch (e) {
        content.innerHTML = `
            <div style="text-align: center; padding: 40px; color: var(--text-secondary);">
                <i class="ri-error-warning-line" style="font-size: 48px; color: #ef4444;"></i>
                <p style="margin-top: 16px;">加载资料库配置失败: ${e.message}</p>
            </div>
        `;
    }
}

function bindKnowledgeBaseEvents(existingConfig) {
    // 切换API Key可见性
    const toggleKeyBtn = document.getElementById('toggle-kb-key');
    const keyInput = document.getElementById('kb-siliconflow-key');
    toggleKeyBtn?.addEventListener('click', () => {
        if (keyInput.type === 'password') {
            keyInput.type = 'text';
            toggleKeyBtn.innerHTML = '<i class="ri-eye-off-line"></i>';
        } else {
            keyInput.type = 'password';
            toggleKeyBtn.innerHTML = '<i class="ri-eye-line"></i>';
        }
    });

    // 测试向量化服务连接
    document.getElementById('test-embedding-btn')?.addEventListener('click', async () => {
        const btn = document.getElementById('test-embedding-btn');
        const resultEl = document.getElementById('embedding-test-result');

        btn.disabled = true;
        btn.innerHTML = '<i class="ri-loader-4-line ri-spin"></i> 测试中...';
        resultEl.style.display = 'none';

        try {
            const apiBase = document.getElementById('kb-siliconflow-base').value;
            const apiKey = document.getElementById('kb-siliconflow-key').value;
            const model = document.getElementById('kb-siliconflow-model').value;

            const result = await apiCall('/api/knowledge-base/test-embedding', 'POST', {
                api_base: apiBase,
                api_key: apiKey || '',  // 如果为空，后端会使用已保存的Key
                model: model
            });

            if (result.success) {
                resultEl.innerHTML = `
                    <div style="background: rgba(16,185,129,0.2); border: 1px solid rgba(16,185,129,0.5); border-radius: 8px; padding: 12px; color: #10b981;">
                        <i class="ri-check-circle-line"></i> 连接成功！
                        <span style="margin-left: 8px;">模型: ${result.model}</span>
                        <span style="margin-left: 8px;">向量维度: ${result.embedding_dim}</span>
                        <span style="margin-left: 8px;">响应时间: ${result.response_time}ms</span>
                    </div>
                `;
            } else {
                resultEl.innerHTML = `
                    <div style="background: rgba(239,68,68,0.2); border: 1px solid rgba(239,68,68,0.5); border-radius: 8px; padding: 12px; color: #ef4444;">
                        <i class="ri-error-warning-line"></i> 连接失败: ${result.error || '未知错误'}
                    </div>
                `;
            }
            resultEl.style.display = 'block';
        } catch (e) {
            resultEl.innerHTML = `
                <div style="background: rgba(239,68,68,0.2); border: 1px solid rgba(239,68,68,0.5); border-radius: 8px; padding: 12px; color: #ef4444;">
                    <i class="ri-error-warning-line"></i> 测试失败: ${e.message}
                </div>
            `;
            resultEl.style.display = 'block';
        } finally {
            btn.disabled = false;
            btn.innerHTML = '<i class="ri-wifi-line"></i> 测试连接';
        }
    });

    // 保存配置
    document.getElementById('save-kb-config')?.addEventListener('click', async () => {
        const btn = document.getElementById('save-kb-config');
        btn.disabled = true;
        btn.innerHTML = '<i class="ri-loader-4-line ri-spin"></i> 保存中...';

        try {
            const apiKey = document.getElementById('kb-siliconflow-key').value;

            const configData = {
                siliconflow_base_url: document.getElementById('kb-siliconflow-base').value,
                siliconflow_model: document.getElementById('kb-siliconflow-model').value,
                siliconflow_embedding_dim: parseInt(document.getElementById('kb-embedding-dim').value),
                default_top_k: parseInt(document.getElementById('kb-top-k').value),
                vector_weight: parseFloat(document.getElementById('kb-vector-weight').value),
                fulltext_weight: parseFloat(document.getElementById('kb-fulltext-weight').value),
                chunk_size: parseInt(document.getElementById('kb-chunk-size').value),
                chunk_overlap: parseInt(document.getElementById('kb-chunk-overlap').value)
            };

            // 只有输入了新的API Key才更新
            if (apiKey) {
                configData.siliconflow_api_key = apiKey;
            }

            await apiCall('/api/knowledge-base/config', 'POST', configData);

            showToast('知识库配置已保存');

            // 刷新页面以更新状态
            setTimeout(() => loadKnowledgeBaseSettings(), 500);
        } catch (e) {
            showToast('保存失败: ' + e.message, 'error');
        } finally {
            btn.disabled = false;
            btn.innerHTML = '<i class="ri-save-line"></i> 保存知识库配置';
        }
    });

    // 全选章节
    document.getElementById('select-all-chapters')?.addEventListener('click', () => {
        const checkboxes = document.querySelectorAll('.chapter-checkbox');
        const allChecked = Array.from(checkboxes).every(cb => cb.checked);
        checkboxes.forEach(cb => cb.checked = !allChecked);
    });

    // 删除选中章节
    document.getElementById('delete-selected-chapters')?.addEventListener('click', async () => {
        const selected = Array.from(document.querySelectorAll('.chapter-checkbox:checked')).map(cb => cb.value);

        if (selected.length === 0) {
            showToast('请先选择要删除的章节', 'error');
            return;
        }

        if (!confirm(`确定要删除选中的 ${selected.length} 个章节的知识库数据吗？\n\n此操作不可恢复！`)) {
            return;
        }

        const btn = document.getElementById('delete-selected-chapters');
        btn.disabled = true;
        btn.innerHTML = '<i class="ri-loader-4-line ri-spin"></i> 删除中...';

        try {
            const result = await apiCall('/api/knowledge-base/clear', 'POST', {
                clear_all: false,
                chapter_ids: selected
            });

            if (result.success) {
                showToast(`已删除 ${selected.length} 个章节的知识库数据`);
                // 刷新页面
                loadKnowledgeBaseSettings();
            } else {
                showToast('删除失败: ' + result.error, 'error');
            }
        } catch (e) {
            showToast('删除失败: ' + e.message, 'error');
        } finally {
            btn.disabled = false;
            btn.innerHTML = '<i class="ri-delete-bin-line"></i> 删除选中章节';
        }
    });

    // 清空所有知识库
    document.getElementById('clear-all-kb')?.addEventListener('click', async () => {
        if (!confirm('⚠️ 确定要清空当前项目的所有知识库数据吗？\n\n此操作不可恢复！所有向量化数据将被永久删除。')) {
            return;
        }

        // 二次确认
        if (!confirm('再次确认：真的要删除所有知识库数据吗？')) {
            return;
        }

        const btn = document.getElementById('clear-all-kb');
        btn.disabled = true;
        btn.innerHTML = '<i class="ri-loader-4-line ri-spin"></i> 清空中...';

        try {
            const result = await apiCall('/api/knowledge-base/clear', 'POST', {
                clear_all: true
            });

            if (result.success) {
                showToast('知识库数据已清空');
                // 刷新页面
                loadKnowledgeBaseSettings();
            } else {
                showToast('清空失败: ' + result.error, 'error');
            }
        } catch (e) {
            showToast('清空失败: ' + e.message, 'error');
        } finally {
            btn.disabled = false;
            btn.innerHTML = '<i class="ri-delete-bin-7-line"></i> 清空当前项目所有知识库数据';
        }
    });
}

// ===== 正则规则设置 =====

async function loadRegexRulesSettings() {
    let content = document.getElementById('settings-content');

    // 如果容器不存在，先渲染设置页面
    if (!content) {
        renderSettings();
        content = document.getElementById('settings-content');
        if (!content) return;
    }

    // 获取规则
    const rules = getRegexRules();

    content.innerHTML = `
        <div style="max-width: 900px;">
            <h2 style="color: var(--text-primary); margin-bottom: 24px; font-size: 20px;">
                <i class="ri-code-line" style="margin-right: 8px; color: var(--accent-color);"></i>
                正则替换规则
            </h2>
            
            <p style="color: var(--text-secondary); margin-bottom: 24px; font-size: 14px;">
                配置文本替换规则，用于词汇检测和自动替换功能。规则按顺序执行。
            </p>
            
            <div id="regex-rules-container" style="display: grid; gap: 12px; margin-bottom: 20px;">
                ${rules.map((rule, index) => renderRegexRuleItem(rule, index)).join('')}
            </div>
            
            <div style="display: flex; gap: 12px;">
                <button id="add-regex-rule" style="padding: 12px 20px; background: rgba(255,255,255,0.1); border: 1px solid var(--border-color); color: var(--text-primary); border-radius: 8px; cursor: pointer;">
                    <i class="ri-add-line"></i> 添加规则
                </button>
                <button id="save-regex-rules" style="padding: 12px 24px; background: var(--accent-color); border: none; color: white; border-radius: 8px; cursor: pointer; font-weight: 500;">
                    <i class="ri-save-line"></i> 保存规则
                </button>
            </div>
        </div>
    `;

    // 绑定删除事件
    bindRegexRuleEvents();

    // 添加规则
    document.getElementById('add-regex-rule').addEventListener('click', () => {
        const container = document.getElementById('regex-rules-container');
        const index = container.children.length;
        const newRule = { pattern: '', replacement: '', enabled: true, description: '' };
        container.insertAdjacentHTML('beforeend', renderRegexRuleItem(newRule, index));
        bindRegexRuleEvents();
    });

    // 保存规则
    document.getElementById('save-regex-rules').addEventListener('click', () => {
        const container = document.getElementById('regex-rules-container');
        const rules = [];

        container.querySelectorAll('.regex-rule-item').forEach(item => {
            rules.push({
                pattern: item.querySelector('.rule-pattern').value,
                replacement: item.querySelector('.rule-replacement').value,
                enabled: item.querySelector('.rule-enabled').checked,
                description: item.querySelector('.rule-description').value
            });
        });

        localStorage.setItem('regexRules', JSON.stringify(rules));
        showToast('正则规则已保存');
    });
}

function renderRegexRuleItem(rule, index) {
    return `
        <div class="regex-rule-item" data-index="${index}" style="background: rgba(0,0,0,0.2); border-radius: 12px; padding: 16px; border: 1px solid var(--border-color);">
            <div style="display: flex; align-items: center; gap: 12px; margin-bottom: 12px;">
                <label style="display: flex; align-items: center; gap: 8px; cursor: pointer;">
                    <input type="checkbox" class="rule-enabled" ${rule.enabled ? 'checked' : ''} style="width: 18px; height: 18px; accent-color: var(--accent-color);">
                    <span style="color: var(--text-secondary); font-size: 13px;">启用</span>
                </label>
                <input type="text" class="rule-description" value="${escapeHtml(rule.description || '')}" placeholder="规则描述（可选）"
                    style="flex: 1; background: rgba(0,0,0,0.3); border: 1px solid var(--border-color); padding: 8px 12px; color: var(--text-primary); border-radius: 6px; font-size: 13px;">
                <button class="delete-rule-btn" style="padding: 8px; background: rgba(239,68,68,0.2); border: none; color: #ef4444; border-radius: 6px; cursor: pointer;">
                    <i class="ri-delete-bin-line"></i>
                </button>
            </div>
            <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 12px;">
                <div>
                    <label style="display: block; font-size: 12px; color: var(--text-secondary); margin-bottom: 6px;">匹配模式 (正则)</label>
                    <input type="text" class="rule-pattern" value="${escapeHtml(rule.pattern || '')}" placeholder="例如: \\b(违禁词)\\b"
                        style="width: 100%; background: rgba(0,0,0,0.3); border: 1px solid var(--border-color); padding: 10px; color: var(--text-primary); border-radius: 6px; font-size: 13px; font-family: monospace;">
                </div>
                <div>
                    <label style="display: block; font-size: 12px; color: var(--text-secondary); margin-bottom: 6px;">替换为</label>
                    <input type="text" class="rule-replacement" value="${escapeHtml(rule.replacement || '')}" placeholder="例如: ***"
                        style="width: 100%; background: rgba(0,0,0,0.3); border: 1px solid var(--border-color); padding: 10px; color: var(--text-primary); border-radius: 6px; font-size: 13px; font-family: monospace;">
                </div>
            </div>
        </div>
    `;
}

function bindRegexRuleEvents() {
    document.querySelectorAll('.delete-rule-btn').forEach(btn => {
        btn.onclick = () => {
            btn.closest('.regex-rule-item').remove();
        };
    });
}

// ===== Skills管理设置 =====

async function loadSkillsSettings() {
    let content = document.getElementById('settings-content');
    
    if (!content) {
        renderSettings();
        content = document.getElementById('settings-content');
        if (!content) return;
    }
    
    content.innerHTML = `
        <div style="display: flex; align-items: center; justify-content: center; height: 200px;">
            <i class="ri-loader-4-line" style="font-size: 32px; color: var(--accent-color); animation: spin 1s linear infinite;"></i>
        </div>
    `;
    
    try {
        const skillsData = await apiCall('/api/skills', 'GET');
        const skills = skillsData.skills || [];
        
        content.innerHTML = `
            <div style="max-width: 900px;">
                <h2 style="color: var(--text-primary); margin-bottom: 24px; font-size: 20px;">
                    <i class="ri-puzzle-line" style="margin-right: 8px; color: var(--accent-color);"></i>
                    Skills 管理
                </h2>
                
                <p style="color: var(--text-secondary); margin-bottom: 24px; font-size: 14px;">
                    Skills 是可扩展的功能模块，可以为Agent提供额外的能力（如热点搜索、网络搜索等）。
                    启用后，无限续写和协作创作模式都可以使用这些Skills。
                </p>
                
                <!-- Skills列表 -->
                <div class="setting-section" style="background: rgba(0,0,0,0.2); border-radius: 12px; padding: 24px; margin-bottom: 20px;">
                    <h3 style="color: var(--text-primary); margin-bottom: 16px; font-size: 15px;">
                        <i class="ri-list-check" style="margin-right: 6px;"></i>
                        可用 Skills (${skills.length})
                    </h3>
                    
                    ${skills.length === 0 ? `
                        <div style="text-align: center; padding: 40px; color: var(--text-secondary);">
                            <i class="ri-inbox-line" style="font-size: 48px; opacity: 0.5;"></i>
                            <p style="margin-top: 12px;">未发现可用的Skills</p>
                            <p style="font-size: 12px; margin-top: 8px;">请在 skills/ 目录下添加Skill模块</p>
                        </div>
                    ` : `
                        <div style="display: grid; gap: 12px;">
                            ${skills.map(skill => {
                                // 根据skill名称分配图标
                                const skillIcons = {
                                    'web_search': '🔍',
                                    'meme_search': '😄',
                                    'trends_search': '🔥',
                                    'novel_writing_assistant': '✍️'
                                };
                                const icon = skillIcons[skill.name] || '🧩';
                                
                                return `
                                <div class="skill-card" data-skill="${skill.name}" style="background: rgba(255,255,255,0.03); border: 1px solid var(--border-color); border-radius: 10px; padding: 16px;">
                                    <div style="display: flex; align-items: center; justify-content: space-between;">
                                        <div style="flex: 1;">
                                            <div style="display: flex; align-items: center; gap: 10px; margin-bottom: 8px;">
                                                <span style="font-size: 24px;">${icon}</span>
                                                <span style="font-size: 16px; font-weight: 500; color: var(--text-primary);">${skill.display_name || skill.name}</span>
                                                ${skill.enabled ? '<span style="background: #10b981; color: white; padding: 2px 8px; border-radius: 4px; font-size: 11px;">已启用</span>' : '<span style="background: #6b7280; color: white; padding: 2px 8px; border-radius: 4px; font-size: 11px;">未启用</span>'}
                                                ${!skill.available ? '<span style="background: #ef4444; color: white; padding: 2px 8px; border-radius: 4px; font-size: 11px;">不可用</span>' : ''}
                                            </div>
                                            <div style="color: var(--text-secondary); font-size: 13px; margin-bottom: 6px;">
                                                ${skill.description || '无描述'}
                                            </div>
                                            <div style="color: var(--text-secondary); font-size: 12px;">
                                                <i class="ri-folder-line"></i> ${skill.path}
                                            </div>
                                        </div>
                                        <div style="display: flex; align-items: center; gap: 12px;">
                                            <label style="display: flex; align-items: center; gap: 8px; cursor: pointer;">
                                                <input type="checkbox" class="skill-toggle" data-skill="${skill.name}" ${skill.enabled ? 'checked' : ''} ${!skill.available ? 'disabled' : ''} style="width: 20px; height: 20px; cursor: pointer; accent-color: var(--accent-color);">
                                                <span style="color: var(--text-secondary); font-size: 13px;">${skill.available ? '启用' : '不可用'}</span>
                                            </label>
                                            <button class="delete-skill-btn" data-skill="${skill.name}" style="padding: 8px; background: rgba(239,68,68,0.1); border: 1px solid rgba(239,68,68,0.3); color: #ef4444; border-radius: 6px; cursor: pointer;" title="删除Skill">
                                                <i class="ri-delete-bin-line"></i>
                                            </button>
                                        </div>
                                    </div>
                                </div>
                            `}).join('')}
                        </div>
                    `}
                </div>
                
                <!-- 提示信息 -->
                <div style="background: rgba(100, 180, 255, 0.1); border: 1px solid rgba(100, 180, 255, 0.3); border-radius: 12px; padding: 20px; margin-bottom: 24px;">
                    <h3 style="margin-bottom: 12px; font-size: 14px; color: #7dd3fc; display: flex; align-items: center; gap: 8px;">
                        <i class="ri-information-line"></i>
                        关于 Skills
                    </h3>
                    <p style="font-size: 13px; color: var(--text-secondary); line-height: 1.6;">
                        Skills 是独立的功能模块，位于 skills/ 目录下。每个Skill包含一个 SKILL.md 描述文件和 scripts/ 目录下的服务实现。
                        启用后，Agent可以通过 use_skill() 方法调用这些功能。
                    </p>
                </div>
                
                <!-- 保存按钮 -->
                <button id="save-skills-settings" style="width: 100%; padding: 14px; background: var(--accent-color); border: none; color: white; border-radius: 10px; cursor: pointer; font-weight: 600; font-size: 15px;">
                    <i class="ri-save-line"></i> 保存 Skills 配置
                </button>
            </div>
        `;
        
        // 绑定事件
        bindSkillsSettingsEvents();
        
    } catch (e) {
        content.innerHTML = `
            <div style="text-align: center; padding: 40px; color: var(--text-secondary);">
                <i class="ri-error-warning-line" style="font-size: 48px; color: #ef4444;"></i>
                <p style="margin-top: 16px;">加载Skills失败: ${e.message}</p>
            </div>
        `;
    }
}

function bindSkillsSettingsEvents() {
    // 删除Skill按钮
    document.querySelectorAll('.delete-skill-btn').forEach(btn => {
        btn.addEventListener('click', async (e) => {
            e.stopPropagation();
            const skillName = btn.dataset.skill;
            
            if (!confirm(`确定要删除 Skill "${skillName}" 吗？\n\n此操作将删除整个Skill目录及其所有文件，不可恢复！`)) {
                return;
            }
            
            btn.disabled = true;
            btn.innerHTML = '<i class="ri-loader-4-line ri-spin"></i>';
            
            try {
                await apiCall(`/api/skills/${skillName}`, 'DELETE');
                showToast(`Skill "${skillName}" 已删除`);
                
                // 刷新Skills列表
                loadSkillsSettings();
            } catch (e) {
                showToast('删除失败: ' + e.message, 'error');
                btn.disabled = false;
                btn.innerHTML = '<i class="ri-delete-bin-line"></i>';
            }
        });
    });
    
    // 保存按钮
    document.getElementById('save-skills-settings')?.addEventListener('click', async () => {
        const btn = document.getElementById('save-skills-settings');
        btn.disabled = true;
        btn.innerHTML = '<i class="ri-loader-4-line"></i> 保存中...';
        
        try {
            const toggles = document.querySelectorAll('.skill-toggle');
            const skillsConfig = {};
            
            toggles.forEach(toggle => {
                const skillName = toggle.dataset.skill;
                skillsConfig[skillName] = toggle.checked;
            });
            
            await apiCall('/api/skills/batch-toggle', 'POST', { skills: skillsConfig });
            
            showToast('Skills配置已保存 ✓');
        } catch (e) {
            showToast('保存失败: ' + e.message, 'error');
        } finally {
            btn.disabled = false;
            btn.innerHTML = '<i class="ri-save-line"></i> 保存 Skills 配置';
        }
    });
}

// 全局暴露设置模块函数
window.renderSettings = renderSettings;
window.loadSettingsTab = loadSettingsTab;
window.loadThemeSettings = loadThemeSettings;
window.loadGlobalAPISettings = loadGlobalAPISettings;
window.loadAgentSettings = loadAgentSettings;
window.loadKnowledgeBaseSettings = loadKnowledgeBaseSettings;
window.loadRegexRulesSettings = loadRegexRulesSettings;
window.loadSkillsSettings = loadSkillsSettings;
// 备份和资料库功能将由 app-backup-resources.js 提供

console.log('[app-settings.js] 设置模块已加载');
