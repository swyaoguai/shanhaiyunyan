/**
 * 文思Agent - Copilot增强模块
 * 包含：@提及功能、智能搜索、上下文增强
 */

// ===== Copilot @提及功能 =====

function getAppCore() {
    return (window.NovelAgentApp && window.NovelAgentApp.core) || {};
}

function getCoreStore() {
    return getAppCore().store || window.store || {};
}

function getCoreUi() {
    return getAppCore().ui || window.ui || {};
}

function getCoreSwitchModule() {
    return getAppCore().switchModule || window.switchModule || function () {};
}

function getCoreRenderMarkdown() {
    return getAppCore().renderMarkdown || window.renderMarkdown || function (text) { return text || ''; };
}

function getCoreAppendMessage() {
    return getAppCore().appendMessage || window.appendMessage || function () {};
}

function getCoreCreateStreamMessage() {
    return getAppCore().createStreamMessage || window.createStreamMessage || function () { return null; };
}

function getCoreScrollCopilotToBottom() {
    return getAppCore().scrollCopilotToBottom || window.scrollCopilotToBottom || function () {};
}

function getCoreUpdateWorkflowPanel() {
    return getAppCore().updateCopilotWorkflowPanel || window.updateCopilotWorkflowPanel || function () {};
}

function getCoreRestoreWorkflowStatus() {
    return getAppCore().restoreCopilotWorkflowStatus || window.restoreCopilotWorkflowStatus || (async function () {});
}

// 提及数据缓存
let mentionData = {
    characters: [],
    settings: [],
    chapters: [],
    worlds: []
};

const COPILOT_AUTO_SAVE_STATE_KEY = 'copilot_chat_auto_save';

function getCopilotAutoSaveState() {
    const store = getCoreStore();
    if (store && store.copilotAutoSave && typeof store.copilotAutoSave === 'object') {
        return store.copilotAutoSave;
    }
    return {
        enabled: false,
        loaded: false,
        projectId: null
    };
}

function setCopilotAutoSaveState(nextState) {
    const store = getCoreStore();
    if (!store) return;
    store.copilotAutoSave = {
        ...getCopilotAutoSaveState(),
        ...(nextState || {})
    };
}

function getCopilotActiveProjectId() {
    return (typeof getActiveProjectId === 'function' ? getActiveProjectId() : null) || getCoreStore().currentProjectId || null;
}

function ensureCopilotAutoSaveToggle() {
    const inputRoot = document.querySelector('.copilot-input');
    const inputWrapper = inputRoot?.querySelector('.copilot-input-wrapper');
    if (!inputRoot || !inputWrapper) return null;

    let row = inputRoot.querySelector('.copilot-auto-save-row');
    if (!row) {
        row = document.createElement('label');
        row.className = 'copilot-auto-save-row';
        row.style.cssText = 'display:flex;align-items:center;gap:10px;padding:8px 2px 10px;color:var(--text-secondary);font-size:12px;user-select:none;';
        row.innerHTML = `
            <input type="checkbox" id="copilot-auto-save-toggle" style="accent-color: var(--accent-color); cursor: pointer;">
            <span style="display:flex;flex-direction:column;gap:2px;line-height:1.35;">
                <span style="color:var(--text-primary);font-size:12px;">自动保存文件</span>
                <span id="copilot-auto-save-hint">勾选后，新增保存的文件会自动创建，自定义分类仍需手动选择。</span>
            </span>
        `;
        inputRoot.insertBefore(row, inputWrapper);
        const checkbox = row.querySelector('#copilot-auto-save-toggle');
        checkbox?.addEventListener('change', async (event) => {
            const target = event.target;
            if (!target) return;
            await saveCopilotAutoSavePreference(Boolean(target.checked));
        });
    }
    return row;
}

function renderCopilotAutoSaveToggle() {
    const row = ensureCopilotAutoSaveToggle();
    if (!row) return;

    const checkbox = row.querySelector('#copilot-auto-save-toggle');
    const hint = row.querySelector('#copilot-auto-save-hint');
    const state = getCopilotAutoSaveState();
    const projectId = getCopilotActiveProjectId();
    const disabled = !projectId;

    if (checkbox) {
        checkbox.checked = Boolean(state.enabled);
        checkbox.disabled = disabled;
        checkbox.title = disabled ? '请先选择项目' : '控制新增接入的内置资料自动保存';
    }
    if (hint) {
        hint.textContent = disabled
            ? '请先选择项目后再配置自动保存。'
            : '勾选后，新增保存的文件会自动创建，自定义分类仍需手动选择。';
    }
    row.style.opacity = disabled ? '0.6' : '1';
}

async function loadCopilotAutoSavePreference() {
    const projectId = getCopilotActiveProjectId();
    if (!projectId || typeof apiCall !== 'function') {
        setCopilotAutoSaveState({ enabled: false, loaded: true, projectId: projectId || null });
        renderCopilotAutoSaveToggle();
        return false;
    }

    try {
        const response = await apiCall(`/api/project-state/${COPILOT_AUTO_SAVE_STATE_KEY}`, 'GET');
        const enabled = Boolean(response?.data?.enabled);
        setCopilotAutoSaveState({ enabled, loaded: true, projectId });
    } catch (error) {
        console.warn('[Copilot] 加载自动保存开关失败:', error);
        setCopilotAutoSaveState({ enabled: false, loaded: true, projectId });
    }
    renderCopilotAutoSaveToggle();
    return getCopilotAutoSaveState().enabled;
}

async function saveCopilotAutoSavePreference(enabled) {
    const projectId = getCopilotActiveProjectId();
    if (!projectId || typeof apiCall !== 'function') {
        renderCopilotAutoSaveToggle();
        return false;
    }

    try {
        await apiCall(`/api/project-state/${COPILOT_AUTO_SAVE_STATE_KEY}`, 'POST', {
            data: { enabled: Boolean(enabled) }
        });
        setCopilotAutoSaveState({ enabled: Boolean(enabled), loaded: true, projectId });
        if (typeof showToast === 'function') {
            showToast(enabled ? '已开启聊天自动保存（内置类型）' : '已关闭新增聊天自动保存');
        }
    } catch (error) {
        console.error('[Copilot] 保存自动保存开关失败:', error);
        if (typeof showToast === 'function') {
            showToast(`保存自动保存设置失败: ${error.message}`, 'error');
        }
    }
    renderCopilotAutoSaveToggle();
    return getCopilotAutoSaveState().enabled;
}

function summarizeWorldRows(rows, limit = 3) {
    if (!Array.isArray(rows)) return [];
    return rows
        .filter((row) => row && typeof row === 'object')
        .slice(0, limit)
        .map((row) => {
            const name = String(row.name || '设定').trim();
            const description = String(row.description || row.details || '').trim();
            return description ? `${name}：${description}` : name;
        });
}

function summarizeEventlineRows(rows, limit = 3) {
    if (!Array.isArray(rows)) return [];
    return rows
        .filter((row) => row && typeof row === 'object')
        .slice(0, limit)
        .map((row) => {
            const name = String(row.name || '事件线').trim();
            const conflict = String(row.conflict || row.description || '').trim();
            const status = String(row.status || '').trim();
            return `${name}${conflict || status ? `：${[conflict, status].filter(Boolean).join('｜')}` : ''}`;
        });
}

const MAX_COMMAND_SUGGESTIONS = 3;

const COPILOT_COMMANDS = [
    {
        key: 'create',
        name: '开始创作',
        label: '开始创作',
        internalName: 'create',
        description: '完整创作：世界观、大纲、章节与合集',
        icon: 'ri-magic-line',
        insertText: '/create ',
        kindLabel: '完整创作',
        keywords: ['create', 'start', 'novel'],
        aliases: ['create'],
        syntax: '/create',
        params: [],
        examples: [{ label: '/create', insertText: '/create ' }]
    },
    {
        key: 'worldbuild',
        name: '生成世界观',
        label: '生成世界观',
        internalName: 'worldbuild',
        description: '只生成或补全世界观',
        icon: 'ri-earth-line',
        insertText: '/worldbuild ',
        kindLabel: '世界观',
        keywords: ['world', 'worldbuild'],
        aliases: ['worldbuild'],
        syntax: '/worldbuild',
        params: [],
        examples: [{ label: '/worldbuild', insertText: '/worldbuild ' }]
    },
    {
        key: 'outline',
        name: '生成大纲',
        label: '生成大纲',
        internalName: 'outline',
        description: '只生成或补全大纲',
        icon: 'ri-file-list-3-line',
        insertText: '/outline ',
        kindLabel: '大纲',
        keywords: ['outline', 'plot'],
        aliases: ['outline'],
        syntax: '/outline',
        params: [],
        examples: [{ label: '/outline', insertText: '/outline ' }]
    },
    {
        key: 'chapter',
        name: '续写章节',
        label: '续写章节',
        internalName: 'chapter',
        description: '指定章节补写或续写',
        icon: 'ri-book-open-line',
        insertText: '/chapter 1 ',
        kindLabel: '章节',
        keywords: ['chapter', 'write'],
        aliases: ['chapter'],
        syntax: '/chapter <章节号>',
        params: [{ name: '章节号', required: true, description: '要生成或续写的章节编号' }],
        selectionRange: { start: '/chapter '.length, end: '/chapter 1'.length },
        examples: [{ label: '/chapter 1', insertText: '/chapter 1 ', selectionRange: { start: '/chapter '.length, end: '/chapter 1'.length } }]
    },
    {
        key: 'status',
        name: '查看进度',
        label: '查看进度',
        internalName: 'status',
        description: '查看当前工作流进度与内容同步情况',
        icon: 'ri-pulse-line',
        insertText: '/status ',
        kindLabel: '进度',
        keywords: ['status', 'progress'],
        aliases: ['status'],
        syntax: '/status',
        params: [],
        examples: [{ label: '/status', insertText: '/status ' }]
    },
    {
        key: 'pause',
        name: '暂停创作',
        label: '暂停创作',
        internalName: 'pause',
        description: '暂停当前创作流程',
        icon: 'ri-pause-circle-line',
        insertText: '/pause ',
        kindLabel: '控制',
        keywords: ['pause', 'stop'],
        aliases: ['pause'],
        syntax: '/pause',
        params: [],
        examples: [{ label: '/pause', insertText: '/pause ' }]
    },
    {
        key: 'resume',
        name: '继续创作',
        label: '继续创作',
        internalName: 'resume',
        description: '继续已暂停的创作流程',
        icon: 'ri-play-circle-line',
        insertText: '/resume ',
        kindLabel: '控制',
        keywords: ['resume', 'continue'],
        aliases: ['resume'],
        syntax: '/resume',
        params: [],
        examples: [{ label: '/resume', insertText: '/resume ' }]
    },
    {
        key: 'cancel',
        name: '取消创作',
        label: '取消创作',
        internalName: 'cancel',
        description: '取消当前创作流程',
        icon: 'ri-close-circle-line',
        insertText: '/cancel ',
        kindLabel: '控制',
        keywords: ['cancel', 'abort'],
        aliases: ['cancel'],
        syntax: '/cancel',
        params: [],
        examples: [{ label: '/cancel', insertText: '/cancel ' }]
    },
];

// 当前提及状态
let mentionState = {
    active: false,
    mode: '',
    startPos: 0,
    query: '',
    selectedIndex: 0,
    endPos: 0,
    items: []
};

// 智能搜索 - 支持拼音首字母、模糊匹配
function smartMentionMatch(query, items) {
    if (!query) return items.slice(0, 10);
    
    const lowerQuery = query.toLowerCase();
    
    return items.filter(item => {
        const name = (item.name || item.title || '').toLowerCase();
        // 完全匹配
        if (name.includes(lowerQuery)) return true;
        // 首字母匹配 (简化版)
        const initials = name.split('').filter((_, i) => i === 0 || name[i-1] === ' ').join('');
        if (initials.includes(lowerQuery)) return true;
        return false;
    }).slice(0, 10);
}

// 搜索提及项
function searchMentions(query) {
    const results = [];
    
    // 搜索角色
    const characters = smartMentionMatch(query, mentionData.characters);
    characters.forEach(c => results.push({ type: 'character', icon: 'ri-user-line', ...c }));
    
    // 搜索设定
    const settings = smartMentionMatch(query, mentionData.settings);
    settings.forEach(s => results.push({ type: 'setting', icon: 'ri-file-text-line', ...s }));
    
    // 搜索章节
    const chapters = smartMentionMatch(query, mentionData.chapters);
    chapters.forEach(ch => results.push({ type: 'chapter', icon: 'ri-book-line', ...ch }));
    
    // 搜索世界观
    const worlds = smartMentionMatch(query, mentionData.worlds);
    worlds.forEach(w => results.push({ type: 'world', icon: 'ri-earth-line', ...w }));
    
    return results.slice(0, 10);
}

function getCommandChapters() {
    const store = getCoreStore();
    if (!Array.isArray(store.projectData?.outline)) return [];
    return store.projectData.outline
        .map((chapter, index) => {
            const chapterNo = index + 1;
            const title = String(chapter?.title || '').trim();
            const insertText = `/chapter ${chapterNo} `;
            return {
                key: `chapter-${chapterNo}`,
                name: `/chapter ${chapterNo}`,
                label: title ? `续写第${chapterNo}章` : `第${chapterNo}章`,
                internalName: 'chapter',
                description: title ? `续写第${chapterNo}章 ${title}` : `续写第${chapterNo}章`,
                icon: 'ri-quill-pen-line',
                insertText,
                kindLabel: '章节',
                keywords: [`chapter ${chapterNo}`, title].filter(Boolean),
                aliases: [`chapter ${chapterNo}`],
                syntax: '/chapter <章节号>',
                params: [{ name: '章节号', required: true, description: '要生成或续写的章节编号' }],
                selectionRange: {
                    start: '/chapter '.length,
                    end: '/chapter '.length + String(chapterNo).length
                },
                examples: [{
                    label: `第${chapterNo}章`,
                    insertText,
                    selectionRange: {
                        start: '/chapter '.length,
                        end: '/chapter '.length + String(chapterNo).length
                    }
                }]
            };
        })
        .slice(0, 12);
}

function normalizeCommandSearchValue(value) {
    return String(value || '').trim().replace(/^\/+/, '').toLowerCase();
}

function isAsciiCommandAlias(value) {
    return /^[\x00-\x7F]+$/.test(String(value || ''));
}

function getCommandSearchTerms(item) {
    return [
        item.name,
        item.label,
        item.syntax,
        item.internalName,
        ...(Array.isArray(item.aliases) ? item.aliases : []),
        ...(Array.isArray(item.keywords) ? item.keywords : [])
    ]
        .map((value) => normalizeCommandSearchValue(value))
        .filter(Boolean);
}

function getCommandExactTerms(item) {
    return [
        item.name,
        item.internalName,
        ...(Array.isArray(item.aliases) ? item.aliases : [])
    ]
        .map((value) => normalizeCommandSearchValue(value))
        .filter(Boolean);
}

function searchCommands(query) {
    const normalized = normalizeCommandSearchValue(query);
    const chapterCommands = getCommandChapters();
    const allCommands = [...COPILOT_COMMANDS, ...chapterCommands];
    const scored = allCommands.map((item, index) => {
        const haystack = [
            ...getCommandSearchTerms(item),
            normalizeCommandSearchValue(item.description)
        ];
        let score = haystack.some((value) => value === normalized) ? 100 : 0;
        if (!normalized) {
            score = 10;
        } else {
            haystack.forEach((value) => {
                if (!value) return;
                if (value === normalized) score = Math.max(score, 100);
                else if (value.startsWith(normalized)) score = Math.max(score, 80);
                else if (value.includes(normalized)) score = Math.max(score, 60);
            });
        }
        if (item.key === 'chapter' && normalized && 'chapter'.startsWith(normalized)) {
            score = Math.max(score, 85);
        }
        return { item, score, index };
    });

    return scored
        .filter((entry) => entry.score > 0)
        .sort((a, b) => b.score - a.score || a.index - b.index)
        .map((entry) => ({ type: 'command', ...entry.item }))
        .slice(0, MAX_COMMAND_SUGGESTIONS);
}

function detectCommandTrigger(value, cursorPos) {
    const safeValue = String(value || '');
    const safeCursor = Number(cursorPos || 0);
    const lineStart = safeValue.lastIndexOf('\n', Math.max(0, safeCursor - 1)) + 1;
    const beforeCursor = safeValue.substring(lineStart, safeCursor);
    const leadingSpaces = beforeCursor.match(/^\s*/)?.[0]?.length || 0;
    const token = beforeCursor.substring(leadingSpaces);
    if (!token.startsWith('/')) return null;
    if (token.substring(1).includes(' ') || token.substring(1).includes('\t')) return null;
    return {
        startPos: lineStart + leadingSpaces,
        query: token.substring(1),
        endPos: safeCursor
    };
}

function setAutocompleteState(nextState) {
    mentionState.active = Boolean(nextState && nextState.active);
    mentionState.mode = String(nextState?.mode || '');
    mentionState.startPos = Number(nextState?.startPos || 0);
    mentionState.query = String(nextState?.query || '');
    mentionState.selectedIndex = Number(nextState?.selectedIndex || 0);
    mentionState.endPos = Number(nextState?.endPos || mentionState.startPos);
    mentionState.items = Array.isArray(nextState?.items) ? nextState.items : [];
}

function parseOptionalNumber(value) {
    const raw = String(value ?? '').trim();
    if (!raw) return null;
    const parsed = Number(raw);
    return Number.isFinite(parsed) ? parsed : null;
}

function matchCommandAlias(commandText, aliases, allowCompactNumber = false) {
    const rawText = String(commandText || '').trim();
    const normalized = rawText.replace(/^\/+/, '').trim();
    if (!normalized) return null;

    for (const alias of Array.isArray(aliases) ? aliases : []) {
        const rawAlias = String(alias || '').trim();
        if (!rawAlias) continue;
        const candidate = isAsciiCommandAlias(rawAlias) ? normalized.toLowerCase() : normalized;
        const aliasValue = isAsciiCommandAlias(rawAlias) ? rawAlias.toLowerCase() : rawAlias;
        if (!candidate.startsWith(aliasValue)) continue;
        const remainder = normalized.slice(rawAlias.length);
        if (!remainder) return '';
        if (/^\s/.test(remainder)) return remainder.trim();
        if (allowCompactNumber && /^\d/.test(remainder)) return remainder.trim();
    }

    return null;
}

function findCommandDefinition(commandToken) {
    const normalized = normalizeCommandSearchValue(commandToken);
    if (!normalized) return null;
    const chapterExact = getCommandChapters().find((item) => getCommandExactTerms(item).includes(normalized));
    if (chapterExact) return chapterExact;
    return COPILOT_COMMANDS.find((item) => getCommandExactTerms(item).includes(normalized)) || null;
}

function getActiveCommandContext(value, cursorPos) {
    const safeValue = String(value || '');
    const safeCursor = Number(cursorPos || 0);
    const lineStart = safeValue.lastIndexOf('\n', Math.max(0, safeCursor - 1)) + 1;
    const nextBreak = safeValue.indexOf('\n', safeCursor);
    const lineEnd = nextBreak === -1 ? safeValue.length : nextBreak;
    const lineText = safeValue.substring(lineStart, lineEnd).trim();
    if (!lineText) return null;
    if (!lineText.startsWith('/')) return null;

    const tokens = lineText.split(/\s+/).filter(Boolean);
    const commandToken = String(tokens[0] || '');
    if (!commandToken) return null;

    const exact = findCommandDefinition(commandToken) || [...COPILOT_COMMANDS, ...getCommandChapters()].find((item) => {
        const argsText = matchCommandAlias(lineText, item.aliases || [item.name], item.key === 'chapter');
        return argsText !== null;
    }) || null;
    if (exact) {
        const argsText = matchCommandAlias(lineText, exact.aliases || [exact.name], exact.key === 'chapter');
        return {
            command: exact,
            args: argsText !== null
                ? String(argsText || '').split(/\s+/).filter(Boolean)
                : tokens.slice(1),
            exact: true
        };
    }
    const fallback = searchCommands(commandToken)[0];
    if (!fallback) return null;

    return {
        command: fallback,
        args: [],
        exact: false
    };
}

function getCommandExamples(command) {
    if (!command || typeof command !== 'object') return [];
    if (command.key === 'chapter') {
        const outlineExamples = getCommandChapters().slice(0, 3).map((item) => ({
            label: item.label || item.name,
            insertText: item.insertText,
            selectionRange: item.selectionRange || null
        }));
        if (outlineExamples.length > 0) return outlineExamples;
    }
    return Array.isArray(command.examples) ? command.examples : [];
}

function shouldShowCommandPromptBar(inputValue, cursorPos) {
    return Boolean(
        detectCommandTrigger(inputValue, cursorPos) ||
        getActiveCommandContext(inputValue, cursorPos)
    );
}

function updateCommandPromptBarVisibility() {
    const promptBar = document.querySelector('.copilot-command-prompts');
    const input = document.getElementById('copilot-input-text');
    if (!promptBar || !input) return;
    const visible = shouldShowCommandPromptBar(input.value, input.selectionStart ?? input.value.length);
    promptBar.classList.toggle('hidden', !visible);
}

function renderCommandHelper() {
    const helper = document.querySelector('.copilot-command-helper');
    const input = document.getElementById('copilot-input-text');
    if (!helper || !input) return;

    updateCommandPromptBarVisibility();
    const context = getActiveCommandContext(input.value, input.selectionStart ?? input.value.length);
    if (!context) {
        helper.classList.add('hidden');
        helper.innerHTML = '';
        return;
    }

    const { command, args, exact } = context;
    const hasChapterArg = command.key === 'chapter' && args.length > 0 && /^\d+$/.test(String(args[0] || ''));
    const params = Array.isArray(command.params) ? command.params : [];
    const displayLabel = escapeHtml(command.label || command.name || '');
    const statusText = params.length > 0
        ? (hasChapterArg ? '参数已填写，回车即可执行' : `请先填写${escapeHtml(params[0]?.name || '参数')}`)
        : '回车即可执行';

    helper.innerHTML = `
        <div class="copilot-command-helper-line">
            <span class="copilot-command-helper-label">${displayLabel}</span>
            <span class="copilot-command-helper-state">${exact ? '已识别' : '候选命令'}</span>
        </div>
        <div class="copilot-command-helper-desc">${escapeHtml(command.description || '')}</div>
        <div class="copilot-command-helper-meta">
            <span class="copilot-command-helper-status ${params.length > 0 && !hasChapterArg ? 'is-missing' : ''}">${statusText}</span>
            ${params.length > 0 ? `<span class="copilot-command-helper-param-text">参数：${escapeHtml(params.map((param) => param.name).join('、'))}</span>` : ''}
        </div>
    `;
    helper.classList.remove('hidden');
}

// 初始化Copilot增强功能
function initCopilotEnhancements() {
    const input = document.getElementById('copilot-input-text');
    if (!input) return;

    if (input.dataset.copilotEnhancementsBound === '1') {
        updateMentionData();
        ensureCommandPromptBar();
        ensureCopilotAutoSaveToggle();
        renderCopilotAutoSaveToggle();
        renderCommandHelper();
        return;
    }
    input.dataset.copilotEnhancementsBound = '1';
    
    // 监听输入
    input.addEventListener('input', handleMentionInput);
    input.addEventListener('keydown', handleMentionKeydown);
    input.addEventListener('blur', () => {
        setTimeout(hideCopilotAutocomplete, 200);
    });
    
    // 更新提及数据
    updateMentionData();
    ensureCommandPromptBar();
    ensureCopilotAutoSaveToggle();
    void loadCopilotAutoSavePreference();
    renderCommandHelper();
}

// 处理输入
function handleMentionInput(e) {
    const input = e.target;
    const value = input.value;
    const cursorPos = input.selectionStart;

    const commandTrigger = detectCommandTrigger(value, cursorPos);
    if (commandTrigger) {
        const commandResults = searchCommands(commandTrigger.query);
        if (commandResults.length > 0) {
            setAutocompleteState({
                active: true,
                mode: 'command',
                startPos: commandTrigger.startPos,
                query: commandTrigger.query,
                selectedIndex: 0,
                endPos: commandTrigger.endPos,
                items: commandResults
            });
            renderCommandHelper();
            showMentionPopup(commandResults, input);
            return;
        }
    }
    
    // 查找@符号
    const textBeforeCursor = value.substring(0, cursorPos);
    const atIndex = textBeforeCursor.lastIndexOf('@');
    
    if (atIndex !== -1) {
        const textAfterAt = textBeforeCursor.substring(atIndex + 1);
        // 确保@后面没有空格（未完成的提及）
        if (!textAfterAt.includes(' ')) {
            const results = searchMentions(textAfterAt);
            if (results.length > 0) {
                setAutocompleteState({
                    active: true,
                    mode: 'mention',
                    startPos: atIndex,
                    query: textAfterAt,
                    selectedIndex: 0,
                    endPos: cursorPos,
                    items: results
                });
                renderCommandHelper();
                showMentionPopup(results, input);
                return;
            }
        }
    }
    
    hideCopilotAutocomplete();
}

// 处理键盘事件
function handleMentionKeydown(e) {
    if (!mentionState.active) return;
    
    const popup = document.getElementById('mention-popup');
    if (!popup || popup.classList.contains('hidden')) return;
    
    const items = popup.querySelectorAll('.mention-item');
    
    switch (e.key) {
        case 'ArrowDown':
            e.preventDefault();
            mentionState.selectedIndex = Math.min(mentionState.selectedIndex + 1, items.length - 1);
            updateMentionSelection(items);
            break;
        case 'ArrowUp':
            e.preventDefault();
            mentionState.selectedIndex = Math.max(mentionState.selectedIndex - 1, 0);
            updateMentionSelection(items);
            break;
        case 'Enter':
        case 'Tab':
            if (items[mentionState.selectedIndex]) {
                e.preventDefault();
                applyAutocompleteSelection(mentionState.items[mentionState.selectedIndex]);
            }
            break;
        case 'Escape':
            hideCopilotAutocomplete();
            break;
    }
}

// 显示提及弹窗
function showMentionPopup(results, input) {
    let popup = document.getElementById('mention-popup');
    
    if (!popup) {
        popup = document.createElement('div');
        popup.id = 'mention-popup';
        popup.style.cssText = `
            position: absolute;
            background: var(--bg-panel);
            border: 1px solid var(--border-color);
            border-radius: 8px;
            box-shadow: 0 8px 32px rgba(0,0,0,0.3);
            max-height: 300px;
            overflow-y: auto;
            z-index: 1000;
            min-width: 250px;
        `;
        document.body.appendChild(popup);
    }
    
    popup.innerHTML = results.map((item, index) => {
        const itemName = item.type === 'command'
            ? escapeHtml(item.label || item.name || '')
            : escapeHtml(item.name || item.title || '');
        const subtitle = item.type === 'command'
            ? escapeHtml(item.description || '')
            : (item.type === 'character'
                ? '角色'
                : item.type === 'setting'
                    ? '设定'
                    : item.type === 'chapter'
                        ? '章节'
                        : '世界观');
        const kindLabel = item.type === 'command'
            ? `<span class="mention-kind-badge">命令</span>`
            : '';
        return `
        <div class="mention-item ${index === mentionState.selectedIndex ? 'selected' : ''}" 
            data-index="${index}"
            data-type="${item.type}" 
            data-name="${itemName}"
            data-id="${item.id || ''}"
            style="padding: 10px 14px; cursor: pointer; display: flex; align-items: center; gap: 10px; 
                ${index === mentionState.selectedIndex ? 'background: var(--accent-color);' : ''}
                transition: background 0.15s;">
            <i class="${item.icon}" style="color: ${index === mentionState.selectedIndex ? 'white' : 'var(--accent-color)'}; font-size: 16px;"></i>
            <div style="flex: 1; overflow: hidden;">
                <div style="display:flex;align-items:center;gap:8px;color: ${index === mentionState.selectedIndex ? 'white' : 'var(--text-primary)'}; font-size: 14px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;">
                    <span style="overflow:hidden;text-overflow:ellipsis;">${itemName}</span>
                    ${kindLabel}
                </div>
                <div style="color: ${index === mentionState.selectedIndex ? 'rgba(255,255,255,0.7)' : 'var(--text-secondary)'}; font-size: 12px;">
                    ${subtitle}
                </div>
            </div>
        </div>
    `;
    }).join('');
    
    // 绑定点击事件
    popup.querySelectorAll('.mention-item').forEach(item => {
        item.addEventListener('click', () => {
            const index = Number(item.dataset.index || Array.from(popup.querySelectorAll('.mention-item')).indexOf(item));
            applyAutocompleteSelection(mentionState.items[index]);
        });
        item.addEventListener('mouseenter', () => {
            const allItems = popup.querySelectorAll('.mention-item');
            mentionState.selectedIndex = Array.from(allItems).indexOf(item);
            allItems.forEach(i => {
                i.classList.remove('selected');
                i.style.background = '';
            });
            item.classList.add('selected');
            item.style.background = 'var(--accent-color)';
        });
    });
    
    // 定位弹窗
    const inputRect = input.getBoundingClientRect();
    popup.style.left = inputRect.left + 'px';
    popup.style.bottom = (window.innerHeight - inputRect.top + 8) + 'px';
    popup.classList.remove('hidden');
}

// 隐藏提及弹窗
function hideMentionPopup() {
    const popup = document.getElementById('mention-popup');
    if (popup) {
        popup.classList.add('hidden');
    }
}

function hideCopilotAutocomplete() {
    hideMentionPopup();
    setAutocompleteState({
        active: false,
        mode: '',
        startPos: 0,
        query: '',
        selectedIndex: 0,
        endPos: 0,
        items: []
    });
    renderCommandHelper();
}

// 更新选中状态
function updateMentionSelection(items) {
    items.forEach((item, index) => {
        if (index === mentionState.selectedIndex) {
            item.classList.add('selected');
            item.style.background = 'var(--accent-color)';
            item.scrollIntoView({ block: 'nearest' });
        } else {
            item.classList.remove('selected');
            item.style.background = '';
        }
    });
}

// 插入提及
function insertMention(type, name, id) {
    const input = document.getElementById('copilot-input-text');
    if (!input) return;
    
    const value = input.value;
    const before = value.substring(0, mentionState.startPos);
    const after = value.substring(input.selectionStart);
    
    // 格式: @[类型:名称]
    const mention = `@[${type}:${name}] `;
    
    input.value = before + mention + after;
    input.focus();
    
    // 设置光标位置
    const newPos = before.length + mention.length;
    input.setSelectionRange(newPos, newPos);
    
    hideCopilotAutocomplete();
}

function insertCommand(commandText, selectionRange = null) {
    const input = document.getElementById('copilot-input-text');
    if (!input || !commandText) return;

    const value = input.value;
    const replaceEnd = Math.max(mentionState.endPos, mentionState.startPos);
    const before = value.substring(0, mentionState.startPos);
    const after = value.substring(replaceEnd);
    input.value = before + commandText + after;
    input.focus();
    if (selectionRange && Number.isFinite(selectionRange.start) && Number.isFinite(selectionRange.end)) {
        input.setSelectionRange(before.length + selectionRange.start, before.length + selectionRange.end);
    } else {
        const newPos = before.length + commandText.length;
        input.setSelectionRange(newPos, newPos);
    }
    hideCopilotAutocomplete();
}

function applyAutocompleteSelection(item) {
    if (!item) return;
    if (item.type === 'command') {
        insertCommand(String(item.insertText || item.name || '').trimEnd() + ' ', item.selectionRange || null);
        return;
    }
    insertMention(item.type, item.name, item.id);
}

function getPromptCommandItems() {
    return [
        COPILOT_COMMANDS.find((item) => item.key === 'create'),
        COPILOT_COMMANDS.find((item) => item.key === 'chapter'),
        COPILOT_COMMANDS.find((item) => item.key === 'worldbuild'),
        COPILOT_COMMANDS.find((item) => item.key === 'outline'),
        COPILOT_COMMANDS.find((item) => item.key === 'status')
    ].filter(Boolean);
}

function ensureCommandPromptBar() {
    const inputRoot = document.querySelector('.copilot-input');
    if (!inputRoot) return;

    let promptBar = inputRoot.querySelector('.copilot-command-prompts');
    if (!promptBar) {
        promptBar = document.createElement('div');
        promptBar.className = 'copilot-command-prompts hidden';
        inputRoot.appendChild(promptBar);
    }

    const items = getPromptCommandItems();
    promptBar.innerHTML = `
        <div class="copilot-command-prompts-label">Slash 命令</div>
        <div class="copilot-command-prompts-list">
            ${items.map((item) => `
                <button
                    type="button"
                    class="copilot-command-text"
                    data-command-insert="${escapeHtml(item.insertText)}"
                    data-selection-start="${item.selectionRange?.start ?? ''}"
                    data-selection-end="${item.selectionRange?.end ?? ''}"
                    title="${escapeHtml(item.description)}"
                >
                    ${escapeHtml(item.label || item.name)}
                </button>
            `).join('<span class="copilot-command-divider">/</span>')}
        </div>
        <div class="copilot-command-helper hidden"></div>
    `;

    promptBar.querySelectorAll('.copilot-command-text').forEach((button) => {
        button.addEventListener('click', () => {
            const input = document.getElementById('copilot-input-text');
            if (!input) return;
            promptBar.classList.remove('hidden');
            const slashTrigger = detectCommandTrigger(input.value, input.selectionStart ?? input.value.length);
            const fallbackPos = input.selectionStart ?? input.value.length;
            setAutocompleteState({
                active: true,
                mode: 'command',
                startPos: slashTrigger?.startPos ?? fallbackPos,
                query: '',
                selectedIndex: 0,
                endPos: slashTrigger?.endPos ?? fallbackPos,
                items: []
            });
            const start = parseOptionalNumber(button.dataset.selectionStart);
            const end = parseOptionalNumber(button.dataset.selectionEnd);
            insertCommand(
                String(button.dataset.commandInsert || '').trimEnd() + ' ',
                start !== null && end !== null ? { start, end } : null
            );
        });
    });
    renderCommandHelper();
}

// 更新提及数据
async function updateMentionData() {
    try {
        const store = getCoreStore();

        // 获取角色
        if (store.projectData?.characters) {
            mentionData.characters = store.projectData.characters.map((c, i) => ({
                id: i,
                name: c.name,
                description: c.description
            }));
        }
        
        // 获取章节
        if (store.projectData?.outline) {
            mentionData.chapters = store.projectData.outline.map((ch, i) => ({
                id: i,
                name: `第${i + 1}章 ${ch.title}`,
                title: ch.title
            }));
        }
        
        // 获取世界观设定
        if (Array.isArray(store.projectData?.worldbuilding)) {
            mentionData.worlds = store.projectData.worldbuilding.slice(0, 6).map((item, index) => ({
                id: item.name || `world-${index}`,
                name: item.name || `世界设定${index + 1}`,
                summary: String(item.description || item.details || '').trim(),
                type: 'world'
            }));
        }
        
        // 获取资料库设定
        mentionData.settings = [];
        if (Array.isArray(store.projectData?.eventlines)) {
            store.projectData.eventlines.slice(0, 6).forEach((item, i) => {
                mentionData.settings.push({
                    id: `eventlines-${i}`,
                    name: item.title || item.name,
                    category: 'eventlines'
                });
            });
        }
        if (Array.isArray(store.projectData?.items)) {
            store.projectData.items.slice(0, 6).forEach((item, i) => {
                mentionData.settings.push({
                    id: `items-${i}`,
                    name: item.name || item.title,
                    category: 'items'
                });
            });
        }
        if (Array.isArray(store.projectData?.detail_settings)) {
            store.projectData.detail_settings.slice(0, 4).forEach((item, i) => {
                mentionData.settings.push({
                    id: `detail_settings-${i}`,
                    name: item.name || item.title,
                    category: 'detail_settings'
                });
            });
        }
        if (Array.isArray(store.projectData?.chapter_settings)) {
            store.projectData.chapter_settings.slice(0, 4).forEach((item, i) => {
                mentionData.settings.push({
                    id: `chapter_settings-${i}`,
                    name: item.name || item.title,
                    category: 'chapter_settings'
                });
            });
        }
        if (store.extendedKnowledge) {
            Object.entries(store.extendedKnowledge).forEach(([category, items]) => {
                if (Array.isArray(items)) {
                    items.forEach((item, i) => {
                        mentionData.settings.push({
                            id: `${category}-${i}`,
                            name: item.title || item.name,
                            category: category
                        });
                    });
                }
            });
        }
        
    } catch (e) {
        console.error('Failed to update mention data:', e);
    }
}

// 发送带提及的Copilot消息
async function sendCopilotMessageWithMentions(message) {
    const store = getCoreStore();

    // 解析提及
    const mentionRegex = /@\[(\w+):([^\]]+)\]/g;
    const mentions = [];
    let match;
    
    while ((match = mentionRegex.exec(message)) !== null) {
        mentions.push({
            type: match[1],
            name: match[2]
        });
    }
    
    // 构建上下文
    let context = '';
    
    for (const mention of mentions) {
        switch (mention.type) {
            case 'character':
                const char = store.projectData?.characters?.find(c => c.name === mention.name);
                if (char) {
                    const compactPersonality = Array.isArray(char.personality) ? char.personality.slice(0, 3).join('、') : '';
                    const compactGoals = Array.isArray(char.goals) ? char.goals.slice(0, 2).join('、') : '';
                    const compactRelations = char.relationships && typeof char.relationships === 'object'
                        ? Object.entries(char.relationships).slice(0, 2).map(([name, relation]) => `${name}(${relation})`).join('、')
                        : '';
                    const profileLines = [
                        char.description ? `简介：${char.description}` : '',
                        char.role ? `定位：${char.role}` : '',
                        char.identity || char.occupation ? `身份：${char.identity || char.occupation}` : '',
                        compactPersonality ? `性格：${compactPersonality}` : '',
                        compactGoals ? `目标：${compactGoals}` : '',
                        compactRelations ? `关系：${compactRelations}` : '',
                    ].filter(Boolean);
                    context += `\n【角色：${char.name}】\n${profileLines.join('\n')}\n`;
                }
                break;
            case 'chapter':
                const chapterMatch = mention.name.match(/第(\d+)章/);
                if (chapterMatch) {
                    const chapterIndex = parseInt(chapterMatch[1]) - 1;
                    const chapter = store.projectData?.outline?.[chapterIndex];
                    if (chapter) {
                        context += `\n【${mention.name}】\n${chapter.content?.substring(0, 500) || chapter.summary || ''}\n`;
                    }
                }
                break;
            case 'world':
                if (Array.isArray(store.projectData?.worldbuilding)) {
                    const worldItem = store.projectData.worldbuilding.find(item => item?.name === mention.name);
                    const worldSummary = worldItem
                        ? [worldItem.description, worldItem.details].filter(Boolean).join('｜')
                        : summarizeWorldRows(store.projectData.worldbuilding, 3).join('\n');
                    if (worldSummary) {
                        context += `\n【世界设定】\n${worldItem ? `${mention.name}：${worldSummary}` : worldSummary}\n`;
                    }
                }
                break;
            case 'setting':
                if (mention.category === 'eventlines' && Array.isArray(store.projectData?.eventlines)) {
                    const eventItem = store.projectData.eventlines.find(item => (item?.title || item?.name) === mention.name || item?.name === mention.name);
                    const eventSummary = eventItem
                        ? [eventItem.conflict || eventItem.description, eventItem.status].filter(Boolean).join('｜')
                        : summarizeEventlineRows(store.projectData.eventlines, 3).join('\n');
                    if (eventSummary) {
                        context += `\n【事件线】\n${eventItem ? `${mention.name}：${eventSummary}` : eventSummary}\n`;
                        break;
                    }
                }
                // 从资料库获取设定
                if (store.extendedKnowledge) {
                    for (const [category, items] of Object.entries(store.extendedKnowledge)) {
                        if (Array.isArray(items)) {
                            const setting = items.find(item => (item.title || item.name) === mention.name);
                            if (setting) {
                                context += `\n【设定：${setting.title || setting.name}】\n${setting.content || ''}\n`;
                                break;
                            }
                        }
                    }
                }
                break;
        }
    }
    
    // 返回带上下文的消息
    return {
        message: message.replace(mentionRegex, '【$2】'),
        context: context,
        mentions: mentions
    };
}

// ===== Copilot面板宽度拖动调整功能 =====
function initPanelWidthResizer() {
    const dragHandle = document.getElementById('copilot-drag-handle');
    const panel = document.getElementById('copilot-panel');
    
    if (!dragHandle || !panel) {
        console.log('[Copilot] 面板宽度拖动初始化失败：元素未找到');
        return;
    }
    
    let isDragging = false;
    let startX = 0;
    let startWidth = 0;
    
    // 从localStorage恢复保存的宽度
    const savedWidth = localStorage.getItem('copilot_panel_width');
    if (savedWidth) {
        const width = parseInt(savedWidth);
        if (width >= 280 && width <= 600) {
            panel.style.width = width + 'px';
        }
    }
    
    dragHandle.addEventListener('mousedown', (e) => {
        e.preventDefault();
        isDragging = true;
        startX = e.clientX;
        startWidth = panel.offsetWidth;
        
        dragHandle.classList.add('dragging');
        document.body.classList.add('resizing-copilot');
    });
    
    document.addEventListener('mousemove', (e) => {
        if (!isDragging) return;
        
        // 向左拖动增加宽度，向右拖动减少宽度
        const deltaX = startX - e.clientX;
        let newWidth = startWidth + deltaX;
        
        // 限制宽度范围
        newWidth = Math.max(280, Math.min(600, newWidth));
        
        panel.style.width = newWidth + 'px';
    });
    
    document.addEventListener('mouseup', () => {
        if (isDragging) {
            isDragging = false;
            dragHandle.classList.remove('dragging');
            document.body.classList.remove('resizing-copilot');
            
            // 保存宽度到localStorage
            localStorage.setItem('copilot_panel_width', panel.offsetWidth);
        }
    });
    
    // 触摸设备支持
    dragHandle.addEventListener('touchstart', (e) => {
        e.preventDefault();
        const touch = e.touches[0];
        isDragging = true;
        startX = touch.clientX;
        startWidth = panel.offsetWidth;
        
        dragHandle.classList.add('dragging');
    });
    
    document.addEventListener('touchmove', (e) => {
        if (!isDragging) return;
        
        const touch = e.touches[0];
        const deltaX = startX - touch.clientX;
        let newWidth = startWidth + deltaX;
        
        newWidth = Math.max(280, Math.min(600, newWidth));
        panel.style.width = newWidth + 'px';
    });
    
    document.addEventListener('touchend', () => {
        if (isDragging) {
            isDragging = false;
            dragHandle.classList.remove('dragging');
            
            localStorage.setItem('copilot_panel_width', panel.offsetWidth);
        }
    });
    
    // 双击重置为默认宽度
    dragHandle.addEventListener('dblclick', () => {
        panel.style.width = '320px';
        localStorage.setItem('copilot_panel_width', 320);
        if (typeof showToast === 'function') {
            showToast('对话框已恢复默认宽度');
        }
    });
    
    console.log('[Copilot] 面板宽度拖动调整功能已初始化');
}

// ===== 输入框高度拖动调整功能 =====
function initInputResizer() {
    const resizeHandle = document.getElementById('copilot-resize-handle');
    const textarea = document.getElementById('copilot-input-text');
    const copilotInput = document.querySelector('.copilot-input');
    
    if (!resizeHandle || !textarea || !copilotInput) {
        console.log('[Copilot] 输入框拖动调整初始化失败：元素未找到');
        return;
    }
    
    let isDragging = false;
    let startY = 0;
    let startHeight = 0;
    
    // 从localStorage恢复保存的高度
    const savedHeight = localStorage.getItem('copilot_input_height');
    if (savedHeight) {
        const height = parseInt(savedHeight);
        if (height >= 60 && height <= 400) {
            textarea.style.height = height + 'px';
        }
    }
    
    resizeHandle.addEventListener('mousedown', (e) => {
        e.preventDefault();
        isDragging = true;
        startY = e.clientY;
        startHeight = textarea.offsetHeight;
        
        resizeHandle.classList.add('dragging');
        document.body.classList.add('resizing-input');
    });
    
    document.addEventListener('mousemove', (e) => {
        if (!isDragging) return;
        
        // 向上拖动增加高度，向下拖动减少高度
        const deltaY = startY - e.clientY;
        let newHeight = startHeight + deltaY;
        
        // 限制高度范围
        newHeight = Math.max(60, Math.min(400, newHeight));
        
        textarea.style.height = newHeight + 'px';
    });
    
    document.addEventListener('mouseup', () => {
        if (isDragging) {
            isDragging = false;
            resizeHandle.classList.remove('dragging');
            document.body.classList.remove('resizing-input');
            
            // 保存高度到localStorage
            localStorage.setItem('copilot_input_height', textarea.offsetHeight);
        }
    });
    
    // 触摸设备支持
    resizeHandle.addEventListener('touchstart', (e) => {
        e.preventDefault();
        const touch = e.touches[0];
        isDragging = true;
        startY = touch.clientY;
        startHeight = textarea.offsetHeight;
        
        resizeHandle.classList.add('dragging');
    });
    
    document.addEventListener('touchmove', (e) => {
        if (!isDragging) return;
        
        const touch = e.touches[0];
        const deltaY = startY - touch.clientY;
        let newHeight = startHeight + deltaY;
        
        newHeight = Math.max(60, Math.min(400, newHeight));
        textarea.style.height = newHeight + 'px';
    });
    
    document.addEventListener('touchend', () => {
        if (isDragging) {
            isDragging = false;
            resizeHandle.classList.remove('dragging');
            
            localStorage.setItem('copilot_input_height', textarea.offsetHeight);
        }
    });
    
    // 双击重置为默认高度
    resizeHandle.addEventListener('dblclick', () => {
        textarea.style.height = '80px';
        localStorage.setItem('copilot_input_height', 80);
        if (typeof showToast === 'function') {
            showToast('输入框已恢复默认高度');
        }
    });
    
    console.log('[Copilot] 输入框拖动调整功能已初始化');
}

// 初始化时自动调用
document.addEventListener('DOMContentLoaded', function() {
    // 延迟初始化，确保DOM完全加载
    setTimeout(() => {
        initInputResizer();
        initPanelWidthResizer();
    }, 100);
});

// 全局暴露Copilot增强函数
window.mentionData = mentionData;
window.initCopilotEnhancements = initCopilotEnhancements;
window.searchMentions = searchMentions;
window.searchCommands = searchCommands;
window.updateMentionData = updateMentionData;
window.sendCopilotMessageWithMentions = sendCopilotMessageWithMentions;
window.initInputResizer = initInputResizer;
window.initPanelWidthResizer = initPanelWidthResizer;
window.hideCopilotAutocomplete = hideCopilotAutocomplete;
window.loadCopilotAutoSavePreference = loadCopilotAutoSavePreference;
window.renderCopilotAutoSaveToggle = renderCopilotAutoSaveToggle;

console.log('[app-copilot.js] Copilot增强模块已加载');
