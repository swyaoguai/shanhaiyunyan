/**
 * 文思Agent - Copilot增强模块
 * 包含：@提及功能、智能搜索、上下文增强
 */

// ===== Copilot @提及功能 =====

// 提及数据缓存
let mentionData = {
    characters: [],
    settings: [],
    chapters: [],
    worlds: []
};

// 当前提及状态
let mentionState = {
    active: false,
    startPos: 0,
    query: '',
    selectedIndex: 0
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

// 初始化Copilot增强功能
function initCopilotEnhancements() {
    const input = document.getElementById('copilot-input-text');
    if (!input) return;
    
    // 监听输入
    input.addEventListener('input', handleMentionInput);
    input.addEventListener('keydown', handleMentionKeydown);
    input.addEventListener('blur', () => {
        setTimeout(hideMentionPopup, 200);
    });
    
    // 更新提及数据
    updateMentionData();
}

// 处理输入
function handleMentionInput(e) {
    const input = e.target;
    const value = input.value;
    const cursorPos = input.selectionStart;
    
    // 查找@符号
    const textBeforeCursor = value.substring(0, cursorPos);
    const atIndex = textBeforeCursor.lastIndexOf('@');
    
    if (atIndex !== -1) {
        const textAfterAt = textBeforeCursor.substring(atIndex + 1);
        // 确保@后面没有空格（未完成的提及）
        if (!textAfterAt.includes(' ')) {
            mentionState.active = true;
            mentionState.startPos = atIndex;
            mentionState.query = textAfterAt;
            mentionState.selectedIndex = 0;
            
            const results = searchMentions(textAfterAt);
            if (results.length > 0) {
                showMentionPopup(results, input);
                return;
            }
        }
    }
    
    hideMentionPopup();
    mentionState.active = false;
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
                const item = items[mentionState.selectedIndex];
                insertMention(item.dataset.type, item.dataset.name, item.dataset.id);
            }
            break;
        case 'Escape':
            hideMentionPopup();
            mentionState.active = false;
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
    
    popup.innerHTML = results.map((item, index) => `
        <div class="mention-item ${index === mentionState.selectedIndex ? 'selected' : ''}" 
            data-type="${item.type}" 
            data-name="${escapeHtml(item.name || item.title)}"
            data-id="${item.id || ''}"
            style="padding: 10px 14px; cursor: pointer; display: flex; align-items: center; gap: 10px; 
                ${index === mentionState.selectedIndex ? 'background: var(--accent-color);' : ''}
                transition: background 0.15s;">
            <i class="${item.icon}" style="color: ${index === mentionState.selectedIndex ? 'white' : 'var(--accent-color)'}; font-size: 16px;"></i>
            <div style="flex: 1; overflow: hidden;">
                <div style="color: ${index === mentionState.selectedIndex ? 'white' : 'var(--text-primary)'}; font-size: 14px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;">
                    ${escapeHtml(item.name || item.title)}
                </div>
                <div style="color: ${index === mentionState.selectedIndex ? 'rgba(255,255,255,0.7)' : 'var(--text-secondary)'}; font-size: 12px;">
                    ${item.type === 'character' ? '角色' : item.type === 'setting' ? '设定' : item.type === 'chapter' ? '章节' : '世界观'}
                </div>
            </div>
        </div>
    `).join('');
    
    // 绑定点击事件
    popup.querySelectorAll('.mention-item').forEach(item => {
        item.addEventListener('click', () => {
            insertMention(item.dataset.type, item.dataset.name, item.dataset.id);
        });
        item.addEventListener('mouseenter', () => {
            popup.querySelectorAll('.mention-item').forEach(i => {
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
    
    hideMentionPopup();
    mentionState.active = false;
}

// 更新提及数据
async function updateMentionData() {
    try {
        // 获取角色
        if (store.projectData.characters) {
            mentionData.characters = store.projectData.characters.map((c, i) => ({
                id: i,
                name: c.name,
                description: c.description
            }));
        }
        
        // 获取章节
        if (store.projectData.outline) {
            mentionData.chapters = store.projectData.outline.map((ch, i) => ({
                id: i,
                name: `第${i + 1}章 ${ch.title}`,
                title: ch.title
            }));
        }
        
        // 获取世界观设定
        if (store.projectData.worldbuilding) {
            const wb = store.projectData.worldbuilding;
            mentionData.worlds = [];
            if (wb.geography) mentionData.worlds.push({ id: 'geography', name: '地理环境', type: 'world' });
            if (wb.history) mentionData.worlds.push({ id: 'history', name: '历史背景', type: 'world' });
            if (wb.culture) mentionData.worlds.push({ id: 'culture', name: '文化习俗', type: 'world' });
            if (wb.magic_system) mentionData.worlds.push({ id: 'magic', name: '力量体系', type: 'world' });
        }
        
        // 获取资料库设定
        if (store.extendedKnowledge) {
            mentionData.settings = [];
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
                const char = store.projectData.characters?.find(c => c.name === mention.name);
                if (char) {
                    context += `\n【角色：${char.name}】\n${char.description || ''}\n`;
                }
                break;
            case 'chapter':
                const chapterMatch = mention.name.match(/第(\d+)章/);
                if (chapterMatch) {
                    const chapterIndex = parseInt(chapterMatch[1]) - 1;
                    const chapter = store.projectData.outline?.[chapterIndex];
                    if (chapter) {
                        context += `\n【${mention.name}】\n${chapter.content?.substring(0, 500) || chapter.summary || ''}\n`;
                    }
                }
                break;
            case 'world':
                const wb = store.projectData.worldbuilding;
                if (wb) {
                    const worldMap = {
                        'geography': wb.geography,
                        'history': wb.history,
                        'culture': wb.culture,
                        'magic': wb.magic_system
                    };
                    const worldContent = worldMap[mention.name] || wb[mention.name];
                    if (worldContent) {
                        context += `\n【世界观：${mention.name}】\n${worldContent}\n`;
                    }
                }
                break;
            case 'setting':
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
window.updateMentionData = updateMentionData;
window.sendCopilotMessageWithMentions = sendCopilotMessageWithMentions;
window.initInputResizer = initInputResizer;
window.initPanelWidthResizer = initPanelWidthResizer;

console.log('[app-copilot.js] Copilot增强模块已加载');
