/**
 * 文思Agent - 主题和背景设置模块
 * 包含：主题配置、HSL颜色控制、背景图片管理
 */

// 5个主题配置
const THEMES = {
    dark: {
        name: '深色',
        icon: '🌙',
        bgMain: '#0a0a0f',
        bgPanel: 'rgba(255,255,255,0.03)',
        textPrimary: '#ffffff',
        textSecondary: 'rgba(255,255,255,0.6)',
        borderColor: 'rgba(255,255,255,0.08)',
        overlayColor: '10,10,15',
        overlayOpacity: 0.85
    },
    light: {
        name: '浅色',
        icon: '☀️',
        bgMain: '#f8f9fa',
        bgPanel: 'rgba(255,255,255,0.9)',
        textPrimary: '#1a1a2e',
        textSecondary: '#666',
        borderColor: 'rgba(0,0,0,0.1)',
        overlayColor: '248,249,250',
        overlayOpacity: 0.9
    },
    green: {
        name: '绿色护眼',
        icon: '🌿',
        bgMain: '#2d5a2d',
        bgPanel: 'rgba(200,230,200,0.12)',
        textPrimary: '#e8f5e8',
        textSecondary: 'rgba(200,230,200,0.8)',
        borderColor: 'rgba(200,230,200,0.2)',
        overlayColor: '60,110,60',
        overlayOpacity: 0.65
    },
    warm: {
        name: '暖黄护眼',
        icon: '🌅',
        bgMain: '#3d3520',
        bgPanel: 'rgba(255,240,200,0.08)',
        textPrimary: '#f5e8c8',
        textSecondary: 'rgba(255,240,200,0.7)',
        overlayColor: '70,60,35',
        borderColor: 'rgba(255,240,200,0.15)',
        overlayOpacity: 0.75
    },
    blue: {
        name: '浅蓝清新',
        icon: '💎',
        bgMain: '#2d4a6a',
        bgPanel: 'rgba(200,220,255,0.12)',
        textPrimary: '#e8f0ff',
        textSecondary: 'rgba(200,220,255,0.8)',
        borderColor: 'rgba(200,220,255,0.2)',
        overlayColor: '55,85,120',
        overlayOpacity: 0.65
    }
};

const THEME_ORDER = ['dark', 'light', 'green', 'warm', 'blue'];

function setTheme(themeKey, showMessage = true) {
    const theme = THEMES[themeKey];
    if (!theme) return;

    store.settings.theme = themeKey;
    localStorage.setItem('theme_mode', themeKey);

    // 只应用文本和面板颜色，背景由hue控制
    applyThemeColors(themeKey);

    if (showMessage) {
        showToast(`已切换到${theme.name}文本模式 ${theme.icon}`);
    }
}

function cycleTheme() {
    // 简化为深色/浅色切换
    const currentTheme = store.settings.theme || 'dark';
    const nextTheme = currentTheme === 'dark' ? 'light' : 'dark';
    setTheme(nextTheme);
}

// 获取安全的主题设置值（避免0值问题）
function getSafeSettingValue(value, defaultValue) {
    return (value !== undefined && value !== null && !isNaN(value)) ? value : defaultValue;
}

function updateThemeButton() {
    const themeKey = store.settings.theme || 'dark';
    const theme = THEMES[themeKey];
    const btn = document.getElementById('theme-cycle-btn');
    if (btn && theme) {
        btn.innerHTML = `${theme.icon} ${theme.name}`;
    }
}

function setBackgroundOpacity(opacity) {
    store.settings.bgOpacity = opacity;
    localStorage.setItem('theme_opacity', opacity);
    // 重新应用完整的主题颜色
    applyFullThemeFromHue(store.settings.accentHue || 250);
}

// 设置背景亮度（0=纯黑，100=纯白）
function setBackgroundLightness(lightness) {
    store.settings.bgLightness = lightness;
    localStorage.setItem('theme_bg_lightness', lightness);
    applyFullThemeFromHue(store.settings.accentHue || 250);
}

// 设置背景图片透明度（用于叠加层）
function setOverlayOpacity(opacity) {
    store.settings.bgOpacity = opacity;
    localStorage.setItem('theme_opacity', opacity);
    applyFullThemeFromHue(store.settings.accentHue || 250);
}

// 根据hue值设置完整的主题颜色（背景 + 面板 + 强调色）
function setBackgroundFromHue(hue) {
    store.settings.accentHue = hue;
    localStorage.setItem('theme_hue', hue);
    document.documentElement.style.setProperty('--primary-hue', hue);
    applyFullThemeFromHue(hue);
}

// 应用完整的主题颜色到所有元素
function applyFullThemeFromHue(hue) {
    // 使用明确的默认值检查，避免0值被当作falsy
    const saturation = (store.settings.accentSaturation !== undefined && store.settings.accentSaturation !== null)
        ? store.settings.accentSaturation : 40;
    const bgLightness = (store.settings.bgLightness !== undefined && store.settings.bgLightness !== null)
        ? store.settings.bgLightness : 12;
    const overlayOpacity = (store.settings.bgOpacity !== undefined && store.settings.bgOpacity !== null)
        ? store.settings.bgOpacity : 0.85;
    const hasBgImage = !!store.settings.bgUrl;
    
    // 判断是浅色还是深色模式
    const isLightMode = bgLightness > 50;
    
    // 1. 设置主背景覆盖层
    const overlayEl = document.getElementById('app-overlay');
    if (overlayEl) {
        if (hasBgImage) {
            // 有背景图片时，使用透明度控制叠加层
            overlayEl.style.background = `hsla(${hue}, ${saturation}%, ${bgLightness}%, ${overlayOpacity})`;
        } else {
            // 无背景图片时，使用纯色
            overlayEl.style.background = `hsl(${hue}, ${saturation}%, ${bgLightness}%)`;
        }
    }
    
    // 2. 更新CSS变量
    const panelSat = Math.min(saturation, 25);
    
    if (isLightMode) {
        // 浅色模式
        const panelLight = Math.min(bgLightness + 5, 98);
        const panelBg = `hsl(${hue}, ${panelSat}%, ${panelLight}%)`;
        const borderColor = `hsla(${hue}, ${Math.min(saturation, 15)}%, ${bgLightness - 20}%, 0.2)`;
        const workspaceBg = `hsla(${hue}, ${Math.min(saturation, 15)}%, ${bgLightness - 5}%, 0.3)`;
        
        document.documentElement.style.setProperty('--bg-panel', panelBg);
        document.documentElement.style.setProperty('--bg-workspace', workspaceBg);
        document.documentElement.style.setProperty('--border-color', borderColor);
        document.documentElement.style.setProperty('--bg-main', `hsl(${hue}, ${panelSat}%, ${bgLightness}%)`);
    } else {
        // 深色模式
        const panelLight = Math.max(bgLightness - 2, 5);
        const panelBg = `hsla(${hue}, ${panelSat}%, ${panelLight}%, 0.95)`;
        const borderColor = `hsla(${hue}, ${Math.min(saturation, 20)}%, ${bgLightness + 15}%, 0.3)`;
        const workspaceBg = `hsla(${hue}, ${Math.min(saturation, 15)}%, ${Math.max(bgLightness - 4, 3)}%, 0.3)`;
        
        document.documentElement.style.setProperty('--bg-panel', panelBg);
        document.documentElement.style.setProperty('--bg-workspace', workspaceBg);
        document.documentElement.style.setProperty('--border-color', borderColor);
        document.documentElement.style.setProperty('--bg-main', `hsl(${hue}, ${panelSat}%, ${bgLightness}%)`);
    }
    
    // 强调色
    const accentSat = Math.max(saturation, 50);
    const accentLight = isLightMode ? 45 : 60;
    const accentColor = `hsl(${hue}, ${accentSat}%, ${accentLight}%)`;
    const accentHover = `hsl(${hue}, ${accentSat}%, ${accentLight - 10}%)`;
    
    document.documentElement.style.setProperty('--accent-color', accentColor);
    document.documentElement.style.setProperty('--accent-hover', accentHover);
    document.documentElement.style.setProperty('--primary-hue', hue);
    
    // 3. 应用字体颜色
    applyTextColor();
}

// 设置饱和度
function setSaturation(saturation) {
    store.settings.accentSaturation = saturation;
    localStorage.setItem('theme_saturation', saturation);
    applyFullThemeFromHue(store.settings.accentHue || 250);
}

// 设置字体亮度
function setTextLightness(lightness) {
    store.settings.textLightness = lightness;
    localStorage.setItem('theme_text_lightness', lightness);
    applyTextColor();
}

// 应用字体颜色
function applyTextColor() {
    const hue = (store.settings.accentHue !== undefined && store.settings.accentHue !== null)
        ? store.settings.accentHue : 250;
    const lightness = (store.settings.textLightness !== undefined && store.settings.textLightness !== null)
        ? store.settings.textLightness : 90;
    
    // 主文字颜色：基于hue的浅色
    const textPrimary = `hsl(${hue}, 15%, ${lightness}%)`;
    // 次要文字颜色：稍暗一些
    const textSecondary = `hsl(${hue}, 10%, ${Math.max(40, lightness - 30)}%)`;
    
    document.documentElement.style.setProperty('--text-primary', textPrimary);
    document.documentElement.style.setProperty('--text-secondary', textSecondary);
}

async function setAppBackground(url) {
    if (!url) return;

    const bgEl = document.getElementById('app-bg');
    if (bgEl) {
        bgEl.style.backgroundImage = `url('${url}')`;
        bgEl.style.backgroundSize = 'cover';
        bgEl.style.backgroundPosition = 'center';
        bgEl.style.backgroundRepeat = 'no-repeat';
        bgEl.style.opacity = '1';  // 确保背景图片可见
    }

    store.settings.bgUrl = url;
    
    // 添加body类，启用侧边栏透明效果
    document.body.classList.add('has-bg-image');

    // 使用IndexedDB存储大图片，localStorage作为备用
    try {
        await saveToIndexedDB('theme_bg', url);
        console.log('[Background] 已保存到IndexedDB');
    } catch (e) {
        console.warn('IndexedDB save failed, trying localStorage:', e);
        // 降级到localStorage（小于1MB才保存）
        if (url.length < 1000000) {
            try {
                localStorage.setItem('theme_bg', url);
            } catch (e2) {
                console.warn('Background image too large for localStorage');
            }
        }
    }

    // 有背景图片时，重新应用主题以调整叠加层透明度
    applyFullThemeFromHue(store.settings.accentHue || 250);
    
    showToast('背景图片已应用，调节「叠加层透明度」控制图片显示强度');
}

async function clearAppBackground() {
    const bgEl = document.getElementById('app-bg');
    if (bgEl) {
        bgEl.style.backgroundImage = '';
        bgEl.style.opacity = '0';
    }

    store.settings.bgUrl = '';
    
    // 清除IndexedDB和localStorage中的背景图片
    try {
        await deleteFromIndexedDB('theme_bg');
    } catch (e) {
        console.warn('Failed to delete from IndexedDB:', e);
    }
    localStorage.removeItem('theme_bg');
    
    // 移除body类，恢复侧边栏原有样式
    document.body.classList.remove('has-bg-image');

    // 清空输入框
    const urlInput = document.getElementById('bg-url-input');
    if (urlInput) {
        urlInput.value = '';
    }

    // 重新应用主题（恢复纯色背景）
    applyFullThemeFromHue(store.settings.accentHue || 250);
    
    showToast('背景图片已清除');
}

async function loadSavedSettings() {
    // 加载强调色（优先加载，因为背景颜色依赖于此）
    const savedHue = localStorage.getItem('theme_hue');
    if (savedHue !== null && savedHue !== '') {
        const parsedHue = parseInt(savedHue);
        store.settings.accentHue = isNaN(parsedHue) ? 250 : parsedHue;
    } else {
        store.settings.accentHue = 250; // 默认值
    }

    // 加载饱和度
    const savedSaturation = localStorage.getItem('theme_saturation');
    if (savedSaturation !== null && savedSaturation !== '') {
        const parsedSat = parseInt(savedSaturation);
        store.settings.accentSaturation = isNaN(parsedSat) ? 40 : parsedSat;
    } else {
        store.settings.accentSaturation = 40; // 默认值
    }

    // 加载背景亮度
    const savedBgLightness = localStorage.getItem('theme_bg_lightness');
    if (savedBgLightness !== null && savedBgLightness !== '') {
        const parsedBgLight = parseInt(savedBgLightness);
        store.settings.bgLightness = isNaN(parsedBgLight) ? 12 : parsedBgLight;
    } else {
        store.settings.bgLightness = 12; // 默认深色
    }

    // 加载背景透明度
    const savedOpacity = localStorage.getItem('theme_opacity');
    if (savedOpacity !== null && savedOpacity !== '') {
        const parsedOpacity = parseFloat(savedOpacity);
        store.settings.bgOpacity = isNaN(parsedOpacity) ? 0.85 : parsedOpacity;
    } else {
        store.settings.bgOpacity = 0.85;
    }

    // 加载字体亮度
    const savedTextLightness = localStorage.getItem('theme_text_lightness');
    if (savedTextLightness !== null && savedTextLightness !== '') {
        const parsedTextLight = parseInt(savedTextLightness);
        store.settings.textLightness = isNaN(parsedTextLight) ? 90 : parsedTextLight;
    } else {
        store.settings.textLightness = 90; // 默认值
    }

    console.log('[Theme] 加载主题设置:', {
        hue: store.settings.accentHue,
        saturation: store.settings.accentSaturation,
        bgLightness: store.settings.bgLightness,
        bgOpacity: store.settings.bgOpacity,
        textLightness: store.settings.textLightness
    });

    // 应用完整的主题颜色（基于hue和saturation）
    applyFullThemeFromHue(store.settings.accentHue);

    // 优先从IndexedDB加载背景图片，然后尝试localStorage
    let savedBg = null;
    try {
        savedBg = await loadFromIndexedDB('theme_bg');
        if (savedBg) {
            console.log('[Background] 从IndexedDB加载成功');
        }
    } catch (e) {
        console.warn('Failed to load from IndexedDB:', e);
    }
    
    // 如果IndexedDB没有，尝试localStorage
    if (!savedBg) {
        savedBg = localStorage.getItem('theme_bg');
        if (savedBg) {
            console.log('[Background] 从localStorage加载');
            // 迁移到IndexedDB
            try {
                await saveToIndexedDB('theme_bg', savedBg);
                localStorage.removeItem('theme_bg');
                console.log('[Background] 已迁移到IndexedDB');
            } catch (e) {
                console.warn('Failed to migrate to IndexedDB:', e);
            }
        }
    }
    
    if (savedBg) {
        store.settings.bgUrl = savedBg;
        // 添加body类，启用侧边栏透明效果
        document.body.classList.add('has-bg-image');
        // 延迟设置背景图片，确保DOM加载完成
        setTimeout(() => {
            const bgEl = document.getElementById('app-bg');
            if (bgEl) {
                bgEl.style.backgroundImage = `url('${savedBg}')`;
                bgEl.style.backgroundSize = 'cover';
                bgEl.style.backgroundPosition = 'center';
                bgEl.style.opacity = '1';
                console.log('[Background] 背景图片已应用');
            }
            // 重新应用主题以确保叠加层正确显示
            applyFullThemeFromHue(store.settings.accentHue);
        }, 100);
    }

    // 加载主题模式（仅用于快速切换深色/浅色）
    const savedTheme = localStorage.getItem('theme_mode');
    store.settings.theme = (savedTheme === 'light') ? 'light' : 'dark';
}

// 快速切换深色/浅色模式
function applyThemeColors(themeKey) {
    if (themeKey === 'light') {
        // 浅色模式：低亮度字体（深色文字），高背景亮度
        store.settings.textLightness = 15;
        store.settings.bgLightness = 95;
        store.settings.bgOpacity = 0.1;
    } else {
        // 深色模式：高亮度字体（浅色文字），低背景亮度
        store.settings.textLightness = 90;
        store.settings.bgLightness = 12;
        store.settings.bgOpacity = 0.85;
    }
    localStorage.setItem('theme_text_lightness', store.settings.textLightness);
    localStorage.setItem('theme_bg_lightness', store.settings.bgLightness);
    localStorage.setItem('theme_opacity', store.settings.bgOpacity);
    
    const hue = getSafeSettingValue(store.settings.accentHue, 250);
    applyFullThemeFromHue(hue);
}

// 全局暴露主题函数
window.THEMES = THEMES;
window.THEME_ORDER = THEME_ORDER;
window.setTheme = setTheme;
window.cycleTheme = cycleTheme;
window.getSafeSettingValue = getSafeSettingValue;
window.updateThemeButton = updateThemeButton;
window.setBackgroundOpacity = setBackgroundOpacity;
window.setBackgroundLightness = setBackgroundLightness;
window.setOverlayOpacity = setOverlayOpacity;
window.setBackgroundFromHue = setBackgroundFromHue;
window.applyFullThemeFromHue = applyFullThemeFromHue;
window.setSaturation = setSaturation;
window.setTextLightness = setTextLightness;
window.applyTextColor = applyTextColor;
window.setAppBackground = setAppBackground;
window.clearAppBackground = clearAppBackground;
window.loadSavedSettings = loadSavedSettings;
window.applyThemeColors = applyThemeColors;

console.log('[app-theme.js] 主题模块已加载');