
/**
 * 山海·云烟 - 工具函数模块
 * 包含：API调用、Toast提示、HTML转义等通用工具
 */

// ===== API 调用 =====

const DEFAULT_API_BASE = '/api/v1';

function normalizeApiUrl(url) {
    const raw = String(url || '').trim();
    if (!raw) return raw;
    if (/^https?:\/\//i.test(raw)) return raw;
    if (!raw.startsWith('/')) return raw;
    if (raw.startsWith('/api/v1/')) return raw;
    if (raw === '/api/v1') return raw;
    if (raw.startsWith('/api/')) {
        return `${DEFAULT_API_BASE}${raw.slice('/api'.length)}`;
    }
    if (raw === '/api') {
        return DEFAULT_API_BASE;
    }
    return raw;
}

async function apiCall(url, method = 'GET', data) {
    const options = {
        method: method,
        headers: { 'Content-Type': 'application/json' }
    };
    if (data !== undefined && data !== null) {
        options.body = JSON.stringify(data);
    }

    const res = await fetch(normalizeApiUrl(url), options);
    const contentType = res.headers.get('content-type') || '';

    if (!res.ok) {
        let errorDetail = '';
        try {
            if (contentType.includes('application/json')) {
                const errorPayload = await res.json();
                if (typeof errorPayload === 'string') {
                    errorDetail = errorPayload;
                } else if (typeof errorPayload?.detail === 'string') {
                    errorDetail = errorPayload.detail;
                } else if (typeof errorPayload?.detail?.message === 'string') {
                    errorDetail = errorPayload.detail.message;
                } else if (Array.isArray(errorPayload?.detail)) {
                    errorDetail = errorPayload.detail
                        .map(item => item?.msg || JSON.stringify(item))
                        .join('; ');
                } else if (typeof errorPayload?.error?.message === 'string') {
                    errorDetail = errorPayload.error.message;
                } else {
                    const candidate = errorPayload?.message || errorPayload?.error || '';
                    if (typeof candidate === 'string') {
                        errorDetail = candidate;
                    } else if (candidate && typeof candidate === 'object') {
                        errorDetail = candidate.message || JSON.stringify(candidate);
                    } else if (errorPayload && typeof errorPayload === 'object') {
                        errorDetail = JSON.stringify(errorPayload);
                    } else {
                        errorDetail = '';
                    }
                }

                if (res.status === 429) {
                    const retryAfter = Number(errorPayload?.retry_after);
                    if (Number.isFinite(retryAfter) && retryAfter > 0) {
                        errorDetail = `${errorDetail || '请求过于频繁'}（请在 ${retryAfter} 秒后重试）`;
                    }
                }
            } else {
                errorDetail = (await res.text()).trim();
            }
        } catch (_) {
            errorDetail = '';
        }

        const error = new Error(errorDetail ? `HTTP ${res.status}: ${errorDetail}` : `HTTP ${res.status}`);
        error.status = res.status;
        const retryAfterHeader = Number(res.headers.get('Retry-After'));
        const retryAfterPayload = Number(
            typeof errorDetail === 'string'
                ? (errorDetail.match(/(\d+)\s*秒后重试/) || [])[1]
                : 0
        );
        const retryAfter = retryAfterHeader > 0 ? retryAfterHeader : (retryAfterPayload > 0 ? retryAfterPayload : 0);
        if (retryAfter > 0) {
            error.retryAfter = retryAfter;
        }
        throw error;
    }

    if (res.status === 204) {
        return {};
    }

    if (contentType.includes('application/json')) {
        return await res.json();
    }

    const text = await res.text();
    return text ? { message: text } : {};
}

async function apiFormCall(url, formData, method = 'POST') {
    if (!(formData instanceof FormData)) {
        throw new Error('formData must be a FormData instance');
    }

    const res = await fetch(normalizeApiUrl(url), {
        method: method,
        body: formData
    });
    const contentType = res.headers.get('content-type') || '';

    if (!res.ok) {
        let errorDetail = '';
        try {
            if (contentType.includes('application/json')) {
                const errorPayload = await res.json();
                errorDetail = errorPayload?.detail || errorPayload?.error || errorPayload?.message || '';
                if (typeof errorDetail !== 'string') {
                    errorDetail = JSON.stringify(errorDetail);
                }
            } else {
                errorDetail = (await res.text()).trim();
            }
        } catch (_) {
            errorDetail = '';
        }
        throw new Error(errorDetail ? `HTTP ${res.status}: ${errorDetail}` : `HTTP ${res.status}`);
    }

    if (res.status === 204) {
        return {};
    }
    if (contentType.includes('application/json')) {
        return await res.json();
    }

    const text = await res.text();
    return text ? { message: text } : {};
}

// ===== Toast 提示 =====

function showToast(msg, type) {
    const t = document.getElementById('toast');
    if (!t) return;
    t.textContent = msg;
    t.classList.remove('hidden');
    t.style.opacity = 1;
    
    // 根据类型设置样式
    if (type === 'error') {
        t.style.background = 'rgba(239, 68, 68, 0.9)';
    } else if (type === 'warning') {
        t.style.background = 'rgba(245, 158, 11, 0.9)';
    } else {
        t.style.background = 'rgba(34, 197, 94, 0.9)';
    }
    
    setTimeout(() => {
        t.style.opacity = 0;
        setTimeout(() => {
            t.classList.add('hidden');
            t.style.background = '';  // 重置背景色
        }, 300);
    }, 2500);
}

// ===== HTML 转义 =====

function escapeHtml(text) {
    if (text === null || text === undefined) return '';
    return String(text).replace(/[&<>"']/g, (char) => {
        const entities = {
            '&': '&amp;',
            '<': '&lt;',
            '>': '&gt;',
            '"': '&quot;',
            "'": '&#39;'
        };
        return entities[char] || char;
    });
}

function safeHostname(url, fallback = '未设置') {
    const raw = String(url || '').trim();
    if (!raw) {
        return fallback;
    }
    try {
        return new URL(raw).hostname || fallback;
    } catch (_) {
        return raw;
    }
}

const IMAGE_MODEL_PATTERN = /(image|imagen|dall[-_ ]?e|gpt-image|codex-gpt-image|flux|stable[-_ ]?diffusion|seedream|jimeng|midjourney|ideogram|recraft|hidream|playground|pixverse)/i;
const NON_TEXT_MODEL_PATTERN = /(embedding|embed|rerank|tts|whisper|audio|speech|moderation)/i;

function getConfiguredModels(config) {
    if (!Array.isArray(config?.models)) return [];
    return config.models
        .map((model) => String(model || '').trim())
        .filter(Boolean);
}

function isImageModelName(model) {
    return IMAGE_MODEL_PATTERN.test(String(model || ''));
}

function isNonTextModelName(model) {
    return NON_TEXT_MODEL_PATTERN.test(String(model || ''));
}

function isTextModelName(model) {
    const value = String(model || '').trim();
    return Boolean(value) && !isImageModelName(value) && !isNonTextModelName(value);
}

function getImageModelsFromConfig(config) {
    return getConfiguredModels(config).filter((model) => isImageModelName(model));
}

function getTextModelsFromConfig(config) {
    return getConfiguredModels(config).filter((model) => isTextModelName(model));
}

function makeElementActivatable(element, onActivate, options = {}) {
    if (!element || typeof onActivate !== 'function') {
        return element;
    }

    const {
        role = 'button',
        tabIndex = 0,
        allowWhen = () => true,
        bindClick = true
    } = options;

    if (!element.hasAttribute('role')) {
        element.setAttribute('role', role);
    }
    if (!element.hasAttribute('tabindex')) {
        element.tabIndex = tabIndex;
    }

    const activate = (event) => {
        if (!allowWhen(event)) {
            return;
        }
        onActivate(event);
    };

    if (bindClick) {
        element.addEventListener('click', activate);
    }
    element.addEventListener('keydown', (event) => {
        if (event.key !== 'Enter' && event.key !== ' ') {
            return;
        }
        event.preventDefault();
        activate(event);
    });

    return element;
}

// ===== 面包屑更新 =====

function updateBreadcrumbs(path) {
    const breadcrumbs = document.getElementById('breadcrumbs');
    if (!breadcrumbs) return;
    breadcrumbs.innerHTML = path.map((p, i) =>
        i === path.length - 1
            ? `<span class="current">${p}</span>`
            : `<span>${p}</span> <span style="opacity:0.55; margin:0 6px;">&gt;</span>`
    ).join('');
}

// ===== IndexedDB 背景图片存储 =====

const DB_NAME = 'wensi_agent_db';
const DB_VERSION = 1;
const STORE_NAME = 'settings';

let dbInstance = null;

async function openDatabase() {
    if (dbInstance) return dbInstance;
    
    return new Promise((resolve, reject) => {
        const request = indexedDB.open(DB_NAME, DB_VERSION);
        
        request.onerror = () => reject(request.error);
        
        request.onsuccess = () => {
            dbInstance = request.result;
            resolve(dbInstance);
        };
        
        request.onupgradeneeded = (event) => {
            const db = event.target.result;
            if (!db.objectStoreNames.contains(STORE_NAME)) {
                db.createObjectStore(STORE_NAME, { keyPath: 'key' });
            }
        };
    });
}

async function saveToIndexedDB(key, value) {
    try {
        const db = await openDatabase();
        return new Promise((resolve, reject) => {
            const transaction = db.transaction([STORE_NAME], 'readwrite');
            const store = transaction.objectStore(STORE_NAME);
            const request = store.put({ key, value });
            request.onsuccess = () => resolve(true);
            request.onerror = () => reject(request.error);
        });
    } catch (e) {
        console.error('IndexedDB save error:', e);
        return false;
    }
}

async function loadFromIndexedDB(key) {
    try {
        const db = await openDatabase();
        return new Promise((resolve, reject) => {
            const transaction = db.transaction([STORE_NAME], 'readonly');
            const store = transaction.objectStore(STORE_NAME);
            const request = store.get(key);
            request.onsuccess = () => resolve(request.result?.value || null);
            request.onerror = () => reject(request.error);
        });
    } catch (e) {
        console.error('IndexedDB load error:', e);
        return null;
    }
}

async function deleteFromIndexedDB(key) {
    try {
        const db = await openDatabase();
        return new Promise((resolve, reject) => {
            const transaction = db.transaction([STORE_NAME], 'readwrite');
            const store = transaction.objectStore(STORE_NAME);
            const request = store.delete(key);
            request.onsuccess = () => resolve(true);
            request.onerror = () => reject(request.error);
        });
    } catch (e) {
        console.error('IndexedDB delete error:', e);
        return false;
    }
}

// ===== AI套路词汇检测与正则替换功能 =====

// AI常用套路词汇列表（预定义）
const AI_CLICHE_WORDS = {
    // 模糊词汇 - AI常用来模糊表达的词
    fuzzy: [
        '仿佛', '似乎', '好像', '宛如', '犹如', '恍若', '恰似', '宛若', '如同', '好似',
        '隐约', '依稀', '朦胧', '模糊', '若隐若现', '若有若无'
    ],
    // 情绪套路 - 机械化的情绪描写
    emotion: [
        '心中一紧', '心头一震', '眉头一皱', '心中一凛', '心下一沉', '心头一跳',
        '心中大骇', '心神一颤', '心中暗道', '眼中闪过', '脸色一变', '面色一沉',
        '眼神一凝', '目光一凝', '瞳孔一缩', '眼底闪过', '嘴角一勾', '嘴角微扬',
        '心中暗喜', '心中暗叹', '心中暗惊', '心中暗骂', '不由自主', '情不自禁'
    ],
    // 冷系词汇 - AI偏爱的"冷"相关词
    cold: [
        '冰冷', '冰寒', '冰凉', '寒意', '寒芒', '冷冽', '凛冽', '刺骨', '冰锥', '寒气',
        '冷意', '冰冷刺骨', '寒风刺骨', '冷若冰霜', '寒光', '冷光'
    ],
    // 力量套路 - 过度使用的力量描写
    power: [
        '磅礴', '澎湃', '汹涌', '浩瀚', '滔天', '惊天', '撼动', '震颤', '颤抖', '战栗',
        '恐怖', '骇人', '惊骇', '惊悚', '不寒而栗', '毛骨悚然', '令人胆寒'
    ],
    // 修饰套路 - 过度修饰词
    modifier: [
        '淬毒', '森然', '阴森', '幽暗', '漆黑', '深邃', '璀璨', '绚烂', '夺目', '耀眼',
        '炽热', '滚烫', '灼热', '狂暴', '狰狞', '扭曲', '诡异', '诡谲', '莫名', '难以言喻'
    ],
    // 转折套路 - AI喜欢用来开头的转折词
    transition: [
        '然而', '但是', '不过', '可是', '只是', '却是', '岂料', '殊不知', '哪知', '谁知',
        '不曾想', '没想到', '出乎意料', '始料未及'
    ],
    // 总结套路 - 概括性表达
    summary: [
        '这一切', '所有的', '一切的', '全部的', '种种', '一时间', '霎时间', '刹那间',
        '瞬息之间', '转眼之间', '眨眼之间', '倏忽之间', '不知不觉'
    ],
    // 四字成语堆砌
    idiom: [
        '气势磅礴', '波澜壮阔', '惊天动地', '翻天覆地', '排山倒海', '摧枯拉朽',
        '势如破竹', '锐不可当', '所向披靡', '战无不胜', '无坚不摧', '横扫千军'
    ],
    // 其他高频套路词
    other: [
        '竟然', '居然', '果然', '显然', '固然', '当然', '自然', '虽然',
        '缓缓', '徐徐', '渐渐', '慢慢', '轻轻', '默默', '静静', '悄悄',
        '微微', '淡淡', '幽幽', '森森', '凛凛', '飒飒'
    ]
};

// 获取所有AI套路词汇（扁平化）
function getAllAIClicheWords() {
    const allWords = [];
    Object.values(AI_CLICHE_WORDS).forEach(category => {
        allWords.push(...category);
    });
    return allWords;
}

// 获取用户自定义的AI套路词汇
function getCustomAIClicheWords() {
    try {
        const saved = localStorage.getItem('custom_ai_cliche_words');
        if (saved) {
            return JSON.parse(saved);
        }
    } catch (e) {
        console.error('Failed to load custom AI cliche words:', e);
    }
    return [];
}

// 保存用户自定义的AI套路词汇
function saveCustomAIClicheWords(words) {
    localStorage.setItem('custom_ai_cliche_words', JSON.stringify(words));
}

// 默认正则替换规则
const DEFAULT_REGEX_RULES = [
    { id: '1', name: '多余空格', pattern: '[ \\t]{2,}', replacement: ' ', enabled: true, description: '将多个连续空格或Tab替换为单个空格' },
    { id: '2', name: '中英文空格', pattern: '([\\u4e00-\\u9fa5])[ \\t]+([\\u4e00-\\u9fa5])', replacement: '$1$2', enabled: true, description: '去除中文之间的空格或Tab' },
    { id: '3', name: '重复标点', pattern: '([。！？，、；：])\\1+', replacement: '$1', enabled: true, description: '去除重复的标点符号' },
    { id: '4', name: '"的"字过多', pattern: '的{2,}', replacement: '的', enabled: false, description: '将多个连续的"的"替换为单个' },
    { id: '5', name: '省略号规范', pattern: '\\.{3,}|。{3,}', replacement: '……', enabled: true, description: '将三个及以上句点替换为省略号' }
];

const REGEX_RULE_PATTERN_MIGRATIONS = {
    '\\s{2,}': '[ \\t]{2,}',
    '([\\u4e00-\\u9fa5])\\s+([\\u4e00-\\u9fa5])': '([\\u4e00-\\u9fa5])[ \\t]+([\\u4e00-\\u9fa5])'
};

function normalizeRegexRule(rule) {
    const normalized = { ...(rule || {}) };
    const pattern = String(normalized.pattern || '');
    if (Object.prototype.hasOwnProperty.call(REGEX_RULE_PATTERN_MIGRATIONS, pattern)) {
        normalized.pattern = REGEX_RULE_PATTERN_MIGRATIONS[pattern];
        if (normalized.description === '将多个连续空格替换为单个空格') {
            normalized.description = '将多个连续空格或Tab替换为单个空格';
        }
        if (normalized.description === '去除中文之间的空格') {
            normalized.description = '去除中文之间的空格或Tab';
        }
    }
    return normalized;
}

function normalizeRegexRules(rules) {
    const source = Array.isArray(rules) ? rules : DEFAULT_REGEX_RULES;
    return source.map(normalizeRegexRule);
}

// 获取用户保存的规则
function getRegexRules() {
    try {
        const saved = localStorage.getItem('regex_replacement_rules');
        if (saved) {
            const parsed = JSON.parse(saved);
            const normalized = normalizeRegexRules(parsed);
            if (JSON.stringify(parsed) !== JSON.stringify(normalized)) {
                saveRegexRules(normalized);
            }
            return normalized;
        }
    } catch (e) {
        console.error('Failed to load regex rules:', e);
    }
    return normalizeRegexRules(DEFAULT_REGEX_RULES);
}

// 保存规则
function saveRegexRules(rules) {
    localStorage.setItem('regex_replacement_rules', JSON.stringify(normalizeRegexRules(rules)));
}

// 检测文本中的AI套路词汇
function detectAIClicheWords(text) {
    // 合并预定义词汇和用户自定义词汇
    const allClicheWords = [...getAllAIClicheWords(), ...getCustomAIClicheWords()];
    
    // 统计每个套路词在文本中出现的次数
    const detectedWords = {};
    
    allClicheWords.forEach(word => {
        // 使用正则表达式进行全局匹配
        const regex = new RegExp(word, 'g');
        const matches = text.match(regex);
        if (matches && matches.length > 0) {
            detectedWords[word] = matches.length;
        }
    });
    
    // 按出现次数降序排列
    const sortedWords = Object.entries(detectedWords)
        .sort((a, b) => b[1] - a[1]);
    
    return sortedWords;
}

// 按类别分析AI套路词汇
function analyzeAIClicheByCategory(text) {
    const customWords = getCustomAIClicheWords();
    const results = {};
    
    // 分析每个类别
    Object.entries(AI_CLICHE_WORDS).forEach(([category, words]) => {
        const detected = [];
        words.forEach(word => {
            const regex = new RegExp(word, 'g');
            const matches = text.match(regex);
            if (matches && matches.length > 0) {
                detected.push([word, matches.length]);
            }
        });
        if (detected.length > 0) {
            results[category] = detected.sort((a, b) => b[1] - a[1]);
        }
    });
    
    // 分析自定义词汇
    if (customWords.length > 0) {
        const detected = [];
        customWords.forEach(word => {
            const regex = new RegExp(word, 'g');
            const matches = text.match(regex);
            if (matches && matches.length > 0) {
                detected.push([word, matches.length]);
            }
        });
        if (detected.length > 0) {
            results['custom'] = detected.sort((a, b) => b[1] - a[1]);
        }
    }
    
    return results;
}

// 获取类别的中文名称
function getCategoryName(category) {
    const names = {
        'fuzzy': '模糊词汇',
        'emotion': '情绪套路',
        'cold': '冷系词汇',
        'power': '力量套路',
        'modifier': '修饰套路',
        'transition': '转折套路',
        'summary': '总结套路',
        'idiom': '四字成语',
        'other': '其他套路',
        'custom': '自定义词汇'
    };
    return names[category] || category;
}

// 获取类别颜色
function getCategoryColor(category) {
    const colors = {
        'fuzzy': '#8b5cf6',      // 紫色
        'emotion': '#ec4899',    // 粉色
        'cold': '#06b6d4',       // 青色
        'power': '#ef4444',      // 红色
        'modifier': '#f59e0b',   // 橙色
        'transition': '#10b981', // 绿色
        'summary': '#6366f1',    // 靛蓝
        'idiom': '#14b8a6',      // 青绿
        'other': '#64748b',      // 灰色
        'custom': '#3b82f6'      // 蓝色
    };
    return colors[category] || '#64748b';
}

// 保持向后兼容的旧函数名
function analyzeHighFrequencyWords(text, minFreq = 1) {
    return detectAIClicheWords(text);
}

// 应用正则替换规则
function applyRegexRules(text, rules) {
    let result = text;
    let appliedCount = 0;
    const appliedDetails = [];

    normalizeRegexRules(rules).filter(r => r.enabled).forEach(rule => {
        try {
            const regex = new RegExp(rule.pattern, 'g');
            const matches = result.match(regex);
            if (matches && matches.length > 0) {
                appliedCount += matches.length;
                appliedDetails.push({ name: rule.name, count: matches.length });
                result = result.replace(regex, rule.replacement);
            }
        } catch (e) {
            console.error(`Regex error for rule ${rule.name}:`, e);
        }
    });
    
    return { result, appliedCount, appliedDetails };
}

// 显示AI套路词汇检测对话框
function showWordCheckDialog(content, onApply) {
    const modal = document.getElementById('modal-container');
    modal.classList.remove('hidden');
    
    // 检测AI套路词汇
    const detectedWords = detectAIClicheWords(content);
    const categoryResults = analyzeAIClicheByCategory(content);
    const rules = getRegexRules();
    const customWords = getCustomAIClicheWords();
    
    // 计算总数
    const totalCount = detectedWords.reduce((sum, [word, count]) => sum + count, 0);
    const uniqueCount = detectedWords.length;
    
    modal.innerHTML = `
        <div style="position: fixed; top: 0; left: 0; right: 0; bottom: 0; background: rgba(0,0,0,0.7); display: flex; align-items: center; justify-content: center; z-index: 1000;">
            <div style="background: var(--bg-panel); border: 1px solid var(--border-color); border-radius: 16px; padding: 30px; width: 900px; max-width: 95%; max-height: 85vh; overflow-y: auto;">
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 24px;">
                    <h3 style="color: var(--text-primary); font-size: 20px; margin: 0;">
                        <i class="ri-robot-line" style="margin-right: 8px; color: #f59e0b;"></i>
                        AI套路词汇检测
                    </h3>
                    <button id="close-word-check" style="background: none; border: none; color: var(--text-secondary); cursor: pointer; font-size: 24px;">
                        <i class="ri-close-line"></i>
                    </button>
                </div>
                
                <!-- 检测统计 -->
                <div style="display: grid; grid-template-columns: repeat(3, 1fr); gap: 16px; margin-bottom: 24px;">
                    <div style="background: rgba(239,68,68,0.1); border: 1px solid rgba(239,68,68,0.3); border-radius: 10px; padding: 16px; text-align: center;">
                        <div style="font-size: 28px; font-weight: 600; color: #ef4444;">${uniqueCount}</div>
                        <div style="font-size: 12px; color: var(--text-secondary);">检测到的套路词种类</div>
                    </div>
                    <div style="background: rgba(245,158,11,0.1); border: 1px solid rgba(245,158,11,0.3); border-radius: 10px; padding: 16px; text-align: center;">
                        <div style="font-size: 28px; font-weight: 600; color: #f59e0b;">${totalCount}</div>
                        <div style="font-size: 12px; color: var(--text-secondary);">套路词总出现次数</div>
                    </div>
                    <div style="background: ${uniqueCount > 20 ? 'rgba(239,68,68,0.1)' : uniqueCount > 10 ? 'rgba(245,158,11,0.1)' : 'rgba(34,197,94,0.1)'}; border: 1px solid ${uniqueCount > 20 ? 'rgba(239,68,68,0.3)' : uniqueCount > 10 ? 'rgba(245,158,11,0.3)' : 'rgba(34,197,94,0.3)'}; border-radius: 10px; padding: 16px; text-align: center;">
                        <div style="font-size: 28px; font-weight: 600; color: ${uniqueCount > 20 ? '#ef4444' : uniqueCount > 10 ? '#f59e0b' : '#22c55e'};">
                            ${uniqueCount > 20 ? '⚠️ 高' : uniqueCount > 10 ? '⚡ 中' : '✓ 低'}
                        </div>
                        <div style="font-size: 12px; color: var(--text-secondary);">AI痕迹程度</div>
                    </div>
                </div>
                
                <!-- 按类别展示检测结果 -->
                <div style="margin-bottom: 24px;">
                    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px;">
                        <h4 style="color: var(--text-primary); font-size: 14px; margin: 0;">
                            🔍 检测到的AI套路词汇
                        </h4>
                        <button id="manage-cliche-words" style="padding: 6px 12px; background: rgba(255,255,255,0.1); border: 1px solid var(--border-color); color: var(--text-primary); border-radius: 6px; cursor: pointer; font-size: 12px;">
                            <i class="ri-settings-3-line"></i> 管理词汇库
                        </button>
                    </div>
                    <div style="background: rgba(0,0,0,0.2); border-radius: 10px; padding: 16px; max-height: 250px; overflow-y: auto;">
                        ${Object.keys(categoryResults).length > 0 ? Object.entries(categoryResults).map(([category, words]) => `
                            <div style="margin-bottom: 16px;">
                                <div style="font-size: 12px; color: var(--text-secondary); margin-bottom: 8px; display: flex; align-items: center; gap: 6px;">
                                    <span style="width: 8px; height: 8px; border-radius: 50%; background: ${getCategoryColor(category)};"></span>
                                    ${getCategoryName(category)} (${words.length}种/${words.reduce((s, w) => s + w[1], 0)}次)
                                </div>
                                <div style="display: flex; flex-wrap: wrap; gap: 6px;">
                                    ${words.map(([word, count]) => `
                                        <span style="padding: 4px 10px; background: ${getCategoryColor(category)}20; border: 1px solid ${getCategoryColor(category)}50; border-radius: 15px; font-size: 12px; color: var(--text-primary);">
                                            ${word} <span style="color: ${getCategoryColor(category)}; font-weight: 600;">×${count}</span>
                                        </span>
                                    `).join('')}
                                </div>
                            </div>
                        `).join('') : `
                            <div style="text-align: center; padding: 30px; color: #22c55e;">
                                <i class="ri-checkbox-circle-line" style="font-size: 32px;"></i>
                                <p style="margin-top: 8px;">太棒了！未检测到AI套路词汇</p>
                            </div>
                        `}
                    </div>
                </div>
                
                <!-- 正则替换规则 -->
                <div style="margin-bottom: 24px;">
                    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px;">
                        <h4 style="color: var(--text-primary); font-size: 14px; margin: 0;">
                            🔧 正则替换规则
                        </h4>
                        <button id="add-regex-rule" style="padding: 6px 12px; background: rgba(255,255,255,0.1); border: 1px solid var(--border-color); color: var(--text-primary); border-radius: 6px; cursor: pointer; font-size: 12px;">
                            <i class="ri-add-line"></i> 添加规则
                        </button>
                    </div>
                    <div id="regex-rules-list" style="background: rgba(0,0,0,0.2); border-radius: 10px; overflow: hidden; max-height: 200px; overflow-y: auto;">
                        ${rules.map((rule, index) => `
                            <div class="regex-rule-item" data-id="${rule.id}" style="display: flex; align-items: center; gap: 12px; padding: 12px 16px; border-bottom: 1px solid var(--border-color);">
                                <input type="checkbox" class="rule-enabled" ${rule.enabled ? 'checked' : ''} style="width: 18px; height: 18px; accent-color: var(--accent-color);">
                                <div style="flex: 1;">
                                    <div style="font-size: 14px; color: var(--text-primary);">${rule.name}</div>
                                    <div style="font-size: 11px; color: var(--text-secondary); margin-top: 2px;">
                                        <code style="background: rgba(255,255,255,0.1); padding: 2px 6px; border-radius: 4px;">${escapeHtml(rule.pattern)}</code>
                                        → <code style="background: rgba(255,255,255,0.1); padding: 2px 6px; border-radius: 4px;">${escapeHtml(rule.replacement) || '(删除)'}</code>
                                    </div>
                                </div>
                                <button class="edit-rule-btn" title="编辑" style="background: none; border: none; color: var(--text-secondary); cursor: pointer; padding: 4px;">
                                    <i class="ri-edit-line"></i>
                                </button>
                                <button class="delete-rule-btn" title="删除" style="background: none; border: none; color: #ef4444; cursor: pointer; padding: 4px;">
                                    <i class="ri-delete-bin-line"></i>
                                </button>
                            </div>
                        `).join('')}
                    </div>
                </div>
                
                <!-- 预览区域 -->
                <div style="margin-bottom: 24px;">
                    <h4 style="color: var(--text-primary); font-size: 14px; margin-bottom: 12px;">
                        👁️ 替换预览
                    </h4>
                    <div id="replacement-preview" style="padding: 16px; background: rgba(0,0,0,0.2); border-radius: 10px; font-size: 13px; color: var(--text-secondary); max-height: 120px; overflow-y: auto;">
                        点击「预览替换」查看效果
                    </div>
                </div>
                
                <!-- 操作按钮 -->
                <div style="display: flex; gap: 12px;">
                    <button id="preview-replacement" style="flex: 1; padding: 14px; background: rgba(255,255,255,0.1); border: 1px solid var(--border-color); color: var(--text-primary); border-radius: 8px; cursor: pointer; font-size: 14px;">
                        <i class="ri-eye-line"></i> 预览替换
                    </button>
                    <button id="apply-replacement" style="flex: 1; padding: 14px; background: var(--accent-color); border: none; color: white; border-radius: 8px; cursor: pointer; font-weight: 600; font-size: 14px;">
                        <i class="ri-check-line"></i> 应用替换
                    </button>
                </div>
                
                <!-- AI套路词汇说明 -->
                <div style="margin-top: 20px; padding: 16px; background: rgba(245,158,11,0.1); border: 1px solid rgba(245,158,11,0.3); border-radius: 10px;">
                    <h5 style="color: #fbbf24; font-size: 13px; margin-bottom: 8px;">💡 关于AI套路词汇</h5>
                    <ul style="font-size: 12px; color: var(--text-secondary); line-height: 1.8; padding-left: 18px; margin: 0;">
                        <li><strong>模糊词汇</strong>：仿佛、似乎、好像等 - AI常用来规避精确描写</li>
                        <li><strong>情绪套路</strong>：心中一紧、眉头一皱等 - 机械化的情绪表达</li>
                        <li><strong>冷系词汇</strong>：冰冷、刺骨、寒芒等 - AI偏爱的冷色调词汇</li>
                        <li><strong>转折套路</strong>：然而、但是、殊不知等 - 段落开头高频词</li>
                        <li>可通过「管理词汇库」添加自定义检测词汇</li>
                    </ul>
                </div>
            </div>
        </div>
    `;
    
    let currentContent = content;
    let currentRules = rules;
    
    // 关闭按钮
    document.getElementById('close-word-check').addEventListener('click', () => {
        modal.classList.add('hidden');
        modal.innerHTML = '';
    });
    
    // 管理词汇库按钮
    document.getElementById('manage-cliche-words')?.addEventListener('click', () => {
        showManageClicheWordsDialog(() => {
            // 刷新对话框
            showWordCheckDialog(content, onApply);
        });
    });
    
    // 规则启用/禁用
    modal.querySelectorAll('.rule-enabled').forEach(checkbox => {
        checkbox.addEventListener('change', (e) => {
            const ruleId = e.target.closest('.regex-rule-item').dataset.id;
            const rule = currentRules.find(r => r.id === ruleId);
            if (rule) {
                rule.enabled = e.target.checked;
                saveRegexRules(currentRules);
            }
        });
    });
    
    // 编辑规则
    modal.querySelectorAll('.edit-rule-btn').forEach(btn => {
        btn.addEventListener('click', (e) => {
            const ruleId = e.target.closest('.regex-rule-item').dataset.id;
            const rule = currentRules.find(r => r.id === ruleId);
            if (rule) {
                showEditRuleDialog(rule, (updatedRule) => {
                    const index = currentRules.findIndex(r => r.id === ruleId);
                    currentRules[index] = updatedRule;
                    saveRegexRules(currentRules);
                    showWordCheckDialog(currentContent, onApply);
                });
            }
        });
    });
    
    // 删除规则
    modal.querySelectorAll('.delete-rule-btn').forEach(btn => {
        btn.addEventListener('click', async (e) => {
            const ruleId = e.target.closest('.regex-rule-item').dataset.id;
            if (await window.showConfirmDialog('确定要删除这条规则吗？')) {
                currentRules = currentRules.filter(r => r.id !== ruleId);
                saveRegexRules(currentRules);
                showWordCheckDialog(currentContent, onApply);
            }
        });
    });
    
    // 添加规则
    document.getElementById('add-regex-rule').addEventListener('click', () => {
        showEditRuleDialog(null, (newRule) => {
            newRule.id = Date.now().toString();
            currentRules.push(newRule);
            saveRegexRules(currentRules);
            showWordCheckDialog(currentContent, onApply);
        });
    });
    
    // 预览替换
    document.getElementById('preview-replacement').addEventListener('click', () => {
        const { result, appliedCount, appliedDetails } = applyRegexRules(content, currentRules);
        const previewEl = document.getElementById('replacement-preview');
        
        if (appliedCount > 0) {
            previewEl.innerHTML = `
                <div style="margin-bottom: 12px; color: #22c55e;">
                    ✓ 共匹配 ${appliedCount} 处，将进行替换：
                    <span style="color: var(--text-secondary); font-size: 12px;">
                        ${appliedDetails.map(d => `${d.name}(${d.count})`).join('、')}
                    </span>
                </div>
                <div style="border-top: 1px solid var(--border-color); padding-top: 12px; white-space: pre-wrap; line-height: 1.6;">
                    ${escapeHtml(result.substring(0, 500))}${result.length > 500 ? '...' : ''}
                </div>
            `;
            currentContent = result;
        } else {
            previewEl.innerHTML = '<span style="color: var(--text-secondary);">没有匹配到需要替换的内容</span>';
        }
    });
    
    // 应用替换
    document.getElementById('apply-replacement').addEventListener('click', () => {
        const { result, appliedCount, appliedDetails } = applyRegexRules(content, currentRules);
        
        if (appliedCount > 0) {
            onApply(result);
            modal.classList.add('hidden');
            modal.innerHTML = '';
            showToast(`已替换 ${appliedCount} 处内容 ✓`);
        } else {
            showToast('没有匹配到需要替换的内容', 'warning');
        }
    });
}

// 管理AI套路词汇库对话框
function showManageClicheWordsDialog(onClose) {
    const customWords = getCustomAIClicheWords();
    
    const dialogEl = document.createElement('div');
    dialogEl.id = 'manage-cliche-dialog';
    dialogEl.style.cssText = 'position: fixed; top: 0; left: 0; right: 0; bottom: 0; background: rgba(0,0,0,0.6); display: flex; align-items: center; justify-content: center; z-index: 1002;';
    dialogEl.innerHTML = `
        <div style="background: var(--bg-panel); border: 1px solid var(--border-color); border-radius: 16px; padding: 24px; width: 600px; max-width: 95%; max-height: 80vh; overflow-y: auto;">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px;">
                <h4 style="color: var(--text-primary); font-size: 18px; margin: 0;">
                    <i class="ri-settings-3-line" style="margin-right: 8px; color: var(--accent-color);"></i>
                    管理AI套路词汇库
                </h4>
                <button id="close-manage-dialog" style="background: none; border: none; color: var(--text-secondary); cursor: pointer; font-size: 20px;">
                    <i class="ri-close-line"></i>
                </button>
            </div>
            
            <!-- 预定义词汇统计 -->
            <div style="margin-bottom: 20px; padding: 16px; background: rgba(0,0,0,0.2); border-radius: 10px;">
                <h5 style="color: var(--text-primary); font-size: 13px; margin-bottom: 12px;">📚 预定义词汇库</h5>
                <div style="display: grid; grid-template-columns: repeat(3, 1fr); gap: 8px;">
                    ${Object.entries(AI_CLICHE_WORDS).map(([category, words]) => `
                        <div style="padding: 8px 12px; background: ${getCategoryColor(category)}15; border-radius: 6px; font-size: 12px;">
                            <span style="color: ${getCategoryColor(category)};">${getCategoryName(category)}</span>
                            <span style="color: var(--text-secondary); margin-left: 4px;">(${words.length}个)</span>
                        </div>
                    `).join('')}
                </div>
                <p style="font-size: 11px; color: var(--text-secondary); margin-top: 12px;">
                    预定义词汇库共 ${getAllAIClicheWords().length} 个词汇，不可编辑
                </p>
            </div>
            
            <!-- 自定义词汇 -->
            <div style="margin-bottom: 20px;">
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px;">
                    <h5 style="color: var(--text-primary); font-size: 13px; margin: 0;">
                        ✏️ 自定义词汇 (${customWords.length}个)
                    </h5>
                </div>
                <div style="display: flex; gap: 8px; margin-bottom: 12px;">
                    <input type="text" id="new-cliche-word" placeholder="输入要添加的套路词汇..."
                        style="flex: 1; background: rgba(0,0,0,0.3); border: 1px solid var(--border-color); padding: 10px; color: var(--text-primary); border-radius: 6px; font-size: 13px;">
                    <button id="add-cliche-word" style="padding: 10px 16px; background: var(--accent-color); border: none; color: white; border-radius: 6px; cursor: pointer;">
                        <i class="ri-add-line"></i> 添加
                    </button>
                </div>
                <div id="custom-words-list" style="display: flex; flex-wrap: wrap; gap: 8px; padding: 12px; background: rgba(0,0,0,0.2); border-radius: 8px; min-height: 60px;">
                    ${customWords.length > 0 ? customWords.map(word => `
                        <span class="custom-word-tag" data-word="${escapeHtml(word)}" style="padding: 6px 12px; background: rgba(59,130,246,0.2); border: 1px solid rgba(59,130,246,0.5); border-radius: 15px; font-size: 12px; color: var(--text-primary); display: flex; align-items: center; gap: 6px;">
                            ${escapeHtml(word)}
                            <button class="remove-word-btn" style="background: none; border: none; color: #ef4444; cursor: pointer; padding: 0; line-height: 1;">
                                <i class="ri-close-line"></i>
                            </button>
                        </span>
                    `).join('') : '<span style="color: var(--text-secondary); font-size: 12px;">暂无自定义词汇，在上方输入框添加</span>'}
                </div>
            </div>
            
            <div style="display: flex; gap: 12px;">
                <button id="close-manage-btn" style="flex: 1; padding: 12px; background: rgba(255,255,255,0.1); border: 1px solid var(--border-color); color: var(--text-primary); border-radius: 8px; cursor: pointer;">
                    关闭
                </button>
            </div>
        </div>
    `;
    
    document.body.appendChild(dialogEl);
    
    let currentCustomWords = [...customWords];
    
    // 关闭按钮
    const closeDialog = () => {
        dialogEl.remove();
        if (onClose) onClose();
    };
    
    dialogEl.querySelector('#close-manage-dialog').addEventListener('click', closeDialog);
    dialogEl.querySelector('#close-manage-btn').addEventListener('click', closeDialog);
    
    // 点击背景关闭
    dialogEl.addEventListener('click', (e) => {
        if (e.target === dialogEl) closeDialog();
    });
    
    // 添加词汇
    const addWord = () => {
        const input = dialogEl.querySelector('#new-cliche-word');
        const word = input.value.trim();
        if (!word) {
            showToast('请输入词汇', 'error');
            return;
        }
        if (currentCustomWords.includes(word)) {
            showToast('该词汇已存在', 'error');
            return;
        }
        if (getAllAIClicheWords().includes(word)) {
            showToast('该词汇已在预定义列表中', 'warning');
            return;
        }
        
        currentCustomWords.push(word);
        saveCustomAIClicheWords(currentCustomWords);
        input.value = '';
        
        // 刷新列表
        const listEl = dialogEl.querySelector('#custom-words-list');
        listEl.innerHTML = currentCustomWords.map(w => `
            <span class="custom-word-tag" data-word="${escapeHtml(w)}" style="padding: 6px 12px; background: rgba(59,130,246,0.2); border: 1px solid rgba(59,130,246,0.5); border-radius: 15px; font-size: 12px; color: var(--text-primary); display: flex; align-items: center; gap: 6px;">
                ${escapeHtml(w)}
                <button class="remove-word-btn" style="background: none; border: none; color: #ef4444; cursor: pointer; padding: 0; line-height: 1;">
                    <i class="ri-close-line"></i>
                </button>
            </span>
        `).join('');
        
        bindRemoveButtons();
        showToast(`已添加「${word}」`);
    };
    
    dialogEl.querySelector('#add-cliche-word').addEventListener('click', addWord);
    dialogEl.querySelector('#new-cliche-word').addEventListener('keypress', (e) => {
        if (e.key === 'Enter') addWord();
    });
    
    // 删除词汇
    const bindRemoveButtons = () => {
        dialogEl.querySelectorAll('.remove-word-btn').forEach(btn => {
            btn.addEventListener('click', (e) => {
                const tag = e.target.closest('.custom-word-tag');
                const word = tag.dataset.word;
                currentCustomWords = currentCustomWords.filter(w => w !== word);
                saveCustomAIClicheWords(currentCustomWords);
                tag.remove();
                
                // 如果列表为空，显示提示
                const listEl = dialogEl.querySelector('#custom-words-list');
                if (currentCustomWords.length === 0) {
                    listEl.innerHTML = '<span style="color: var(--text-secondary); font-size: 12px;">暂无自定义词汇，在上方输入框添加</span>';
                }
            });
        });
    };
    
    bindRemoveButtons();
}

// 编辑/添加规则对话框
function showEditRuleDialog(rule, onSave) {
    const isNew = !rule;
    const modal = document.getElementById('modal-container');
    
    // 创建嵌套对话框
    const dialogEl = document.createElement('div');
    dialogEl.id = 'edit-rule-dialog';
    dialogEl.style.cssText = 'position: fixed; top: 0; left: 0; right: 0; bottom: 0; background: rgba(0,0,0,0.5); display: flex; align-items: center; justify-content: center; z-index: 1001;';
    dialogEl.innerHTML = `
        <div style="background: var(--bg-panel); border: 1px solid var(--border-color); border-radius: 12px; padding: 24px; width: 450px; max-width: 90%;">
            <h4 style="color: var(--text-primary); margin-bottom: 20px; font-size: 16px;">
                ${isNew ? '添加' : '编辑'}正则替换规则
            </h4>
            
            <div style="margin-bottom: 16px;">
                <label style="display: block; font-size: 12px; color: var(--text-secondary); margin-bottom: 6px;">规则名称</label>
                <input type="text" id="rule-name" value="${rule ? escapeHtml(rule.name) : ''}" placeholder="例如：去除多余空格"
                    style="width: 100%; background: rgba(0,0,0,0.3); border: 1px solid var(--border-color); padding: 10px; color: var(--text-primary); border-radius: 6px;">
            </div>
            
            <div style="margin-bottom: 16px;">
                <label style="display: block; font-size: 12px; color: var(--text-secondary); margin-bottom: 6px;">正则表达式</label>
                <input type="text" id="rule-pattern" value="${rule ? escapeHtml(rule.pattern) : ''}" placeholder="例如：\\s{2,}"
                    style="width: 100%; background: rgba(0,0,0,0.3); border: 1px solid var(--border-color); padding: 10px; color: var(--text-primary); border-radius: 6px; font-family: monospace;">
            </div>
            
            <div style="margin-bottom: 16px;">
                <label style="display: block; font-size: 12px; color: var(--text-secondary); margin-bottom: 6px;">替换为（留空表示删除）</label>
                <input type="text" id="rule-replacement" value="${rule ? escapeHtml(rule.replacement) : ''}" placeholder="例如：单个空格"
                    style="width: 100%; background: rgba(0,0,0,0.3); border: 1px solid var(--border-color); padding: 10px; color: var(--text-primary); border-radius: 6px; font-family: monospace;">
            </div>
            
            <div style="margin-bottom: 20px;">
                <label style="display: block; font-size: 12px; color: var(--text-secondary); margin-bottom: 6px;">描述（可选）</label>
                <input type="text" id="rule-description" value="${rule ? escapeHtml(rule.description || '') : ''}" placeholder="规则说明"
                    style="width: 100%; background: rgba(0,0,0,0.3); border: 1px solid var(--border-color); padding: 10px; color: var(--text-primary); border-radius: 6px;">
            </div>
            
            <div style="display: flex; gap: 12px;">
                <button id="cancel-rule" style="flex: 1; padding: 12px; background: rgba(255,255,255,0.1); border: 1px solid var(--border-color); color: var(--text-primary); border-radius: 6px; cursor: pointer;">取消</button>
                <button id="save-rule" style="flex: 1; padding: 12px; background: var(--accent-color); border: none; color: white; border-radius: 6px; cursor: pointer; font-weight: 600;">保存</button>
            </div>
        </div>
    `;
    
    document.body.appendChild(dialogEl);
    
    // 取消
    dialogEl.querySelector('#cancel-rule').addEventListener('click', () => {
        dialogEl.remove();
    });
    
    // 保存
    dialogEl.querySelector('#save-rule').addEventListener('click', () => {
        const name = dialogEl.querySelector('#rule-name').value.trim();
        const pattern = dialogEl.querySelector('#rule-pattern').value.trim();
        const replacement = dialogEl.querySelector('#rule-replacement').value;
        const description = dialogEl.querySelector('#rule-description').value.trim();
        
        if (!name || !pattern) {
            showToast('请填写规则名称和正则表达式', 'error');
            return;
        }
        
        // 验证正则表达式
        try {
            new RegExp(pattern);
        } catch (e) {
            showToast('正则表达式语法错误: ' + e.message, 'error');
            return;
        }
        
        const updatedRule = {
            id: rule ? rule.id : '',
            name,
            pattern,
            replacement,
            description,
            enabled: rule ? rule.enabled : true
        };
        
        dialogEl.remove();
        onSave(updatedRule);
    });
    
    // 点击背景关闭
    dialogEl.addEventListener('click', (e) => {
        if (e.target === dialogEl) {
            dialogEl.remove();
        }
    });
}

// 全局暴露工具函数
window.DEFAULT_API_BASE = DEFAULT_API_BASE;
window.normalizeApiUrl = normalizeApiUrl;
window.apiCall = apiCall;
window.apiFormCall = apiFormCall;
window.showToast = showToast;
window.escapeHtml = escapeHtml;
window.safeHostname = safeHostname;
window.getConfiguredModels = getConfiguredModels;
window.isImageModelName = isImageModelName;
window.isNonTextModelName = isNonTextModelName;
window.isTextModelName = isTextModelName;
window.getImageModelsFromConfig = getImageModelsFromConfig;
window.getTextModelsFromConfig = getTextModelsFromConfig;
window.makeElementActivatable = makeElementActivatable;
window.updateBreadcrumbs = updateBreadcrumbs;
window.openDatabase = openDatabase;
window.saveToIndexedDB = saveToIndexedDB;
window.loadFromIndexedDB = loadFromIndexedDB;
window.deleteFromIndexedDB = deleteFromIndexedDB;
window.getRegexRules = getRegexRules;
window.saveRegexRules = saveRegexRules;
window.analyzeHighFrequencyWords = analyzeHighFrequencyWords;
window.detectAIClicheWords = detectAIClicheWords;
window.analyzeAIClicheByCategory = analyzeAIClicheByCategory;
window.getAllAIClicheWords = getAllAIClicheWords;
window.getCustomAIClicheWords = getCustomAIClicheWords;
window.saveCustomAIClicheWords = saveCustomAIClicheWords;
window.openDatabase = openDatabase;
window.saveToIndexedDB = saveToIndexedDB;
window.loadFromIndexedDB = loadFromIndexedDB;
window.deleteFromIndexedDB = deleteFromIndexedDB;
window.getRegexRules = getRegexRules;
window.saveRegexRules = saveRegexRules;
window.analyzeHighFrequencyWords = analyzeHighFrequencyWords;
window.detectAIClicheWords = detectAIClicheWords;
window.analyzeAIClicheByCategory = analyzeAIClicheByCategory;
window.getAllAIClicheWords = getAllAIClicheWords;
window.getCustomAIClicheWords = getCustomAIClicheWords;
window.saveCustomAIClicheWords = saveCustomAIClicheWords;
window.getCategoryName = getCategoryName;
window.getCategoryColor = getCategoryColor;
window.applyRegexRules = applyRegexRules;
window.showWordCheckDialog = showWordCheckDialog;
window.showManageClicheWordsDialog = showManageClicheWordsDialog;
window.showEditRuleDialog = showEditRuleDialog;
window.AI_CLICHE_WORDS = AI_CLICHE_WORDS;

// ===== 自定义统一弹窗 =====
function showConfirmDialog(message, title = '确认操作') {
    return new Promise((resolve) => {
        const dialogEl = document.createElement('div');
        dialogEl.className = 'custom-dialog-overlay';
        dialogEl.innerHTML = `
            <div class="custom-dialog-box">
                <div class="custom-dialog-header">
                    <i class="ri-question-line"></i>
                    <span>${escapeHtml(title)}</span>
                </div>
                <div class="custom-dialog-body">
                    ${escapeHtml(message).replace(/\n/g, '<br>')}
                </div>
                <div class="custom-dialog-footer">
                    <button class="custom-dialog-btn btn-cancel">取消</button>
                    <button class="custom-dialog-btn btn-confirm">确认</button>
                </div>
            </div>
        `;
        document.body.appendChild(dialogEl);

        // 动画触发
        requestAnimationFrame(() => dialogEl.classList.add('show'));

        const closeDialog = (result) => {
            dialogEl.classList.remove('show');
            setTimeout(() => {
                dialogEl.remove();
                resolve(result);
            }, 300); // 对应CSS过渡时间
        };

        dialogEl.querySelector('.btn-cancel').addEventListener('click', () => closeDialog(false));
        dialogEl.querySelector('.btn-confirm').addEventListener('click', () => closeDialog(true));
    });
}

function showAlertDialog(message, title = '提示') {
    return new Promise((resolve) => {
        const dialogEl = document.createElement('div');
        dialogEl.className = 'custom-dialog-overlay';
        dialogEl.innerHTML = `
            <div class="custom-dialog-box">
                <div class="custom-dialog-header">
                    <i class="ri-information-line"></i>
                    <span>${escapeHtml(title)}</span>
                </div>
                <div class="custom-dialog-body">
                    ${escapeHtml(message).replace(/\n/g, '<br>')}
                </div>
                <div class="custom-dialog-footer" style="justify-content: center;">
                    <button class="custom-dialog-btn btn-confirm">确定</button>
                </div>
            </div>
        `;
        document.body.appendChild(dialogEl);

        // 动画触发
        requestAnimationFrame(() => dialogEl.classList.add('show'));

        const closeDialog = () => {
            dialogEl.classList.remove('show');
            setTimeout(() => {
                dialogEl.remove();
                resolve(true);
            }, 300);
        };

        dialogEl.querySelector('.btn-confirm').addEventListener('click', () => closeDialog());
    });
}

window.showConfirmDialog = showConfirmDialog;
window.showAlertDialog = showAlertDialog;


console.log('[app-utils.js] 工具函数模块已加载');
