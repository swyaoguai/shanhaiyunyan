
/**
 * 无限续写章节编辑器模块
 * 提供章节编辑、正则查找替换、标题修改等功能
 */

// ===== 当前编辑的章节状态 =====
let currentEditingIWChapter = {
    index: -1,
    chapter: null,
    modified: false
};

// 查找匹配状态
let iwFindMatches = [];
let iwCurrentMatchIndex = -1;

// ===== 显示章节编辑器（替换原有的预览功能） =====
function showInfiniteWriteChapterEditor(chapter) {
    const chapterIndex = infiniteWriteState.chapters.findIndex(ch => ch.chapter_number === chapter.chapter_number);
    currentEditingIWChapter = {
        index: chapterIndex,
        chapter: chapter,
        modified: false
    };
    
    const modal = document.getElementById('modal-container');
    if (!modal) return;
    
    modal.classList.remove('hidden');
    
    modal.innerHTML = `
        <div style="position: fixed; top: 0; left: 0; right: 0; bottom: 0; background: rgba(0,0,0,0.8); display: flex; align-items: stretch; justify-content: center; z-index: 1000; padding: 20px;">
            <div style="background: var(--bg-panel); border: 1px solid var(--border-color); border-radius: 16px; width: 95%; max-width: 1200px; display: flex; flex-direction: column;">
                <!-- 标题栏 -->
                <div style="padding: 16px 20px; border-bottom: 1px solid var(--border-color); display: flex; align-items: center; gap: 12px;">
                    <span style="color: var(--text-secondary); font-size: 14px;">第${chapter.chapter_number}章</span>
                    <input type="text" id="iw-edit-chapter-title" value="${escapeHtml(chapter.title || '')}" 
                        placeholder="章节标题"
                        style="flex: 1; background: rgba(0,0,0,0.3); border: 1px solid var(--border-color); padding: 8px 12px; color: var(--text-primary); border-radius: 6px; font-size: 16px; font-weight: 500;">
                    <span id="iw-edit-word-count" style="font-size: 13px; color: var(--text-secondary);">${(chapter.word_count || 0).toLocaleString()} 字</span>
                    <span id="iw-edit-save-status" style="font-size: 12px; color: #10b981; display: none;">已保存</span>
                    <button id="close-iw-editor" style="background: none; border: none; color: var(--text-secondary); font-size: 24px; cursor: pointer; padding: 4px;" title="关闭">
                        <i class="ri-close-line"></i>
                    </button>
                </div>
                
                <!-- 工具栏 -->
                <div style="padding: 12px 20px; border-bottom: 1px solid var(--border-color); display: flex; align-items: center; gap: 8px; flex-wrap: wrap;">
                    <button id="iw-edit-find-replace-btn" style="padding: 6px 12px; background: rgba(255,255,255,0.1); border: 1px solid var(--border-color); color: var(--text-primary); border-radius: 6px; cursor: pointer; font-size: 13px;" title="查找替换 (Ctrl+H)">
                        <i class="ri-search-line"></i> 查找替换
                    </button>
                    <button id="iw-edit-word-check-btn" style="padding: 6px 12px; background: rgba(139, 92, 246, 0.15); border: 1px solid rgba(139, 92, 246, 0.4); color: #a78bfa; border-radius: 6px; cursor: pointer; font-size: 13px;" title="高频词检测与正则替换">
                        <i class="ri-search-eye-line"></i> 词汇检测
                    </button>
                    <button id="iw-edit-polish-btn" style="padding: 6px 12px; background: rgba(34, 197, 94, 0.15); border: 1px solid rgba(34, 197, 94, 0.4); color: #22c55e; border-radius: 6px; cursor: pointer; font-size: 13px;" title="AI润色">
                        <i class="ri-magic-line"></i> AI润色
                    </button>
                    <div style="flex: 1;"></div>
                    <button id="iw-edit-undo-btn" style="padding: 6px 12px; background: rgba(255,255,255,0.1); border: 1px solid var(--border-color); color: var(--text-primary); border-radius: 6px; cursor: pointer; font-size: 13px;" title="撤销 (Ctrl+Z)">
                        <i class="ri-arrow-go-back-line"></i>
                    </button>
                    <button id="iw-edit-redo-btn" style="padding: 6px 12px; background: rgba(255,255,255,0.1); border: 1px solid var(--border-color); color: var(--text-primary); border-radius: 6px; cursor: pointer; font-size: 13px;" title="重做 (Ctrl+Y)">
                        <i class="ri-arrow-go-forward-line"></i>
                    </button>
                </div>
                
                <!-- 查找替换面板（默认隐藏） -->
                <div id="iw-find-replace-panel" style="display: none; padding: 12px 20px; border-bottom: 1px solid var(--border-color); background: rgba(0,0,0,0.2);">
                    <div style="display: flex; gap: 12px; align-items: flex-start;">
                        <div style="flex: 1;">
                            <div style="display: flex; gap: 8px; margin-bottom: 8px;">
                                <input type="text" id="iw-find-input" placeholder="查找内容..." 
                                    style="flex: 1; background: rgba(0,0,0,0.3); border: 1px solid var(--border-color); padding: 8px 12px; color: var(--text-primary); border-radius: 6px; font-size: 13px;">
                                <button id="iw-find-prev-btn" style="padding: 8px 12px; background: rgba(255,255,255,0.1); border: 1px solid var(--border-color); color: var(--text-primary); border-radius: 6px; cursor: pointer;" title="上一个">
                                    <i class="ri-arrow-up-line"></i>
                                </button>
                                <button id="iw-find-next-btn" style="padding: 8px 12px; background: rgba(255,255,255,0.1); border: 1px solid var(--border-color); color: var(--text-primary); border-radius: 6px; cursor: pointer;" title="下一个">
                                    <i class="ri-arrow-down-line"></i>
                                </button>
                            </div>
                            <div style="display: flex; gap: 8px;">
                                <input type="text" id="iw-replace-input" placeholder="替换为..." 
                                    style="flex: 1; background: rgba(0,0,0,0.3); border: 1px solid var(--border-color); padding: 8px 12px; color: var(--text-primary); border-radius: 6px; font-size: 13px;">
                                <button id="iw-replace-btn" style="padding: 8px 12px; background: rgba(255,255,255,0.1); border: 1px solid var(--border-color); color: var(--text-primary); border-radius: 6px; cursor: pointer;" title="替换">
                                    替换
                                </button>
                                <button id="iw-replace-all-btn" style="padding: 8px 12px; background: linear-gradient(135deg, #8b5cf6, #6366f1); border: none; color: white; border-radius: 6px; cursor: pointer;" title="全部替换">
                                    全部替换
                                </button>
                            </div>
                        </div>
                        <div style="display: flex; flex-direction: column; gap: 6px; min-width: 150px;">
                            <label style="display: flex; align-items: center; gap: 6px; font-size: 12px; color: var(--text-secondary); cursor: pointer;">
                                <input type="checkbox" id="iw-find-regex" style="width: 14px; height: 14px;">
                                使用正则表达式
                            </label>
                            <label style="display: flex; align-items: center; gap: 6px; font-size: 12px; color: var(--text-secondary); cursor: pointer;">
                                <input type="checkbox" id="iw-find-case" style="width: 14px; height: 14px;">
                                区分大小写
                            </label>
                            <span id="iw-find-count" style="font-size: 12px; color: var(--text-secondary); margin-top: 4px;"></span>
                        </div>
                        <button id="iw-close-find-panel" style="background: none; border: none; color: var(--text-secondary); font-size: 18px; cursor: pointer; padding: 4px;">
                            <i class="ri-close-line"></i>
                        </button>
                    </div>
                </div>
                
                <!-- 编辑区域 -->
                <div style="flex: 1; overflow: hidden; display: flex; flex-direction: column;">
                    <textarea id="iw-edit-content" 
                        style="flex: 1; width: 100%; background: rgba(0,0,0,0.2); border: none; padding: 24px; color: var(--text-primary); font-size: 15px; line-height: 2; resize: none; outline: none;"
                        placeholder="开始编辑章节内容...">${chapter.content || ''}</textarea>
                </div>
                
                <!-- 章节信息 -->
                ${chapter.important_events || chapter.new_characters ? `
                <div style="padding: 12px 20px; border-top: 1px solid var(--border-color); background: rgba(0,0,0,0.2);">
                    <div style="font-size: 12px; color: var(--text-secondary);">
                        ${chapter.important_events ? `<span style="margin-right: 16px;"><strong>重要事件：</strong>${chapter.important_events}</span>` : ''}
                        ${chapter.new_characters && chapter.new_characters !== '无' ? `<span><strong>新增角色：</strong>${chapter.new_characters}</span>` : ''}
                    </div>
                </div>
                ` : ''}
                
                <!-- 底部操作栏 -->
                <div style="padding: 16px 20px; border-top: 1px solid var(--border-color); display: flex; gap: 12px; justify-content: space-between;">
                    <div style="display: flex; gap: 12px;">
                        <button id="iw-delete-chapter-btn" style="padding: 10px 20px; background: rgba(239, 68, 68, 0.2); border: 1px solid rgba(239, 68, 68, 0.4); color: #ef4444; border-radius: 8px; cursor: pointer;">
                            <i class="ri-delete-bin-line"></i> 删除章节
                        </button>
                    </div>
                    <div style="display: flex; gap: 12px;">
                        <button id="iw-save-changes-btn" style="padding: 10px 20px; background: linear-gradient(135deg, #8b5cf6, #6366f1); border: none; color: white; border-radius: 8px; cursor: pointer; font-weight: 500;">
                            <i class="ri-save-line"></i> 保存修改
                        </button>
                        <button id="iw-save-to-project-btn" style="padding: 10px 20px; background: linear-gradient(135deg, #22c55e, #10b981); border: none; color: white; border-radius: 8px; cursor: pointer; font-weight: 500;">
                            <i class="ri-folder-add-line"></i> 保存到项目
                        </button>
                    </div>
                </div>
            </div>
        </div>
    `;
    
    // 绑定编辑器事件
    bindIWEditorEvents(chapter);
}

// ===== 绑定编辑器事件 =====
function bindIWEditorEvents(chapter) {
    const modal = document.getElementById('modal-container');
    const titleInput = document.getElementById('iw-edit-chapter-title');
    const contentTextarea = document.getElementById('iw-edit-content');
    const wordCountEl = document.getElementById('iw-edit-word-count');
    const saveStatusEl = document.getElementById('iw-edit-save-status');
    
    // 关闭编辑器
    document.getElementById('close-iw-editor')?.addEventListener('click', () => {
        closeIWEditor();
    });
    
    // 标题修改
    titleInput?.addEventListener('input', () => {
        currentEditingIWChapter.modified = true;
        saveStatusEl.style.display = 'none';
    });
    
    // 内容修改
    let autoSaveTimer = null;
    contentTextarea?.addEventListener('input', () => {
        currentEditingIWChapter.modified = true;
        saveStatusEl.style.display = 'none';
        
        // 更新字数
        const content = contentTextarea.value;
        const wordCount = content.replace(/\s/g, '').length;
        wordCountEl.textContent = wordCount.toLocaleString() + ' 字';
        
        // 自动保存（3秒后）
        clearTimeout(autoSaveTimer);
        autoSaveTimer = setTimeout(() => {
            saveIWChapterChanges(false);
        }, 3000);
    });
    
    // 查找替换面板开关
    document.getElementById('iw-edit-find-replace-btn')?.addEventListener('click', () => {
        toggleIWFindReplacePanel();
    });
    
    // 词汇检测（复用智能体模式的功能）
    document.getElementById('iw-edit-word-check-btn')?.addEventListener('click', () => {
        const content = contentTextarea.value.trim();
        if (!content) {
            showToast('请先输入需要检测的内容', 'warning');
            return;
        }
        
        // 调用智能体模式的词汇检测对话框
        showWordCheckDialog(content, (newContent) => {
            contentTextarea.value = newContent;
            const newCount = newContent.replace(/\s/g, '').length;
            wordCountEl.textContent = newCount.toLocaleString() + ' 字';
            currentEditingIWChapter.modified = true;
            saveStatusEl.style.display = 'none';
            showToast('替换已应用 ✓');
        });
    });
    
    // AI润色功能（复用智能体模式的润色API）
    document.getElementById('iw-edit-polish-btn')?.addEventListener('click', async () => {
        const content = contentTextarea.value.trim();
        if (!content) {
            showToast('请先输入需要润色的内容', 'warning');
            return;
        }
        
        const btn = document.getElementById('iw-edit-polish-btn');
        btn.disabled = true;
        btn.innerHTML = '<i class="ri-loader-4-line"></i> 润色中...';
        
        try {
            // 调用章节API，action设为polish
            const response = await apiCall('/api/chapter', 'POST', {
                chapter_index: currentEditingIWChapter.index,
                chapter_title: titleInput?.value || '',
                existing_content: content,
                action: 'polish'
            });
            
            if (response.content) {
                contentTextarea.value = response.content;
                const newCount = response.content.replace(/\s/g, '').length;
                wordCountEl.textContent = newCount.toLocaleString() + ' 字';
                currentEditingIWChapter.modified = true;
                saveStatusEl.style.display = 'none';
                showToast('润色完成 ✓');
            } else if (response.error) {
                showToast('润色失败: ' + response.error, 'error');
            }
        } catch (e) {
            showToast('润色失败: ' + e.message, 'error');
        } finally {
            btn.disabled = false;
            btn.innerHTML = '<i class="ri-magic-line"></i> AI润色';
        }
    });
    
    document.getElementById('iw-close-find-panel')?.addEventListener('click', () => {
        document.getElementById('iw-find-replace-panel').style.display = 'none';
    });
    
    // 查找功能
    document.getElementById('iw-find-input')?.addEventListener('input', () => {
        highlightIWMatches();
    });
    
    document.getElementById('iw-find-regex')?.addEventListener('change', () => {
        highlightIWMatches();
    });
    
    document.getElementById('iw-find-case')?.addEventListener('change', () => {
        highlightIWMatches();
    });
    
    document.getElementById('iw-find-next-btn')?.addEventListener('click', () => {
        findIWNext();
    });
    
    document.getElementById('iw-find-prev-btn')?.addEventListener('click', () => {
        findIWPrev();
    });
    
    // 替换功能
    document.getElementById('iw-replace-btn')?.addEventListener('click', () => {
        replaceIWCurrent();
    });
    
    document.getElementById('iw-replace-all-btn')?.addEventListener('click', () => {
        replaceIWAll();
    });
    
    // 撤销/重做
    document.getElementById('iw-edit-undo-btn')?.addEventListener('click', () => {
        contentTextarea?.focus();
        document.execCommand('undo');
    });
    
    document.getElementById('iw-edit-redo-btn')?.addEventListener('click', () => {
        contentTextarea?.focus();
        document.execCommand('redo');
    });
    
    // 保存修改
    document.getElementById('iw-save-changes-btn')?.addEventListener('click', () => {
        saveIWChapterChanges(true);
    });
    
    // 保存到项目
    document.getElementById('iw-save-to-project-btn')?.addEventListener('click', async () => {
        await saveIWChapterChanges(false);
        const updatedChapter = {
            ...currentEditingIWChapter.chapter,
            title: titleInput.value,
            content: contentTextarea.value,
            word_count: contentTextarea.value.replace(/\s/g, '').length
        };
        await saveChapterToProject(updatedChapter);
    });
    
    // 删除章节
    document.getElementById('iw-delete-chapter-btn')?.addEventListener('click', () => {
        deleteIWChapter();
    });
    
    // 键盘快捷键
    contentTextarea?.addEventListener('keydown', (e) => {
        // Ctrl+H 查找替换
        if (e.ctrlKey && e.key === 'h') {
            e.preventDefault();
            toggleIWFindReplacePanel();
        }
        // Ctrl+S 保存
        if (e.ctrlKey && e.key === 's') {
            e.preventDefault();
            saveIWChapterChanges(true);
        }
        // Escape 关闭查找面板
        if (e.key === 'Escape') {
            const panel = document.getElementById('iw-find-replace-panel');
            if (panel && panel.style.display !== 'none') {
                panel.style.display = 'none';
            }
        }
    });
    
    // 点击背景关闭
    modal?.addEventListener('click', (e) => {
        if (e.target === modal.firstElementChild) {
            closeIWEditor();
        }
    });
}

// ===== 关闭编辑器 =====
function closeIWEditor() {
    const modal = document.getElementById('modal-container');
    
    if (currentEditingIWChapter.modified) {
        if (!confirm('有未保存的修改，确定要关闭吗？')) {
            return;
        }
    }
    
    modal.classList.add('hidden');
    modal.innerHTML = '';
    currentEditingIWChapter = { index: -1, chapter: null, modified: false };
}

// ===== 保存章节修改 =====
async function saveIWChapterChanges(showNotification) {
    const titleInput = document.getElementById('iw-edit-chapter-title');
    const contentTextarea = document.getElementById('iw-edit-content');
    const saveStatusEl = document.getElementById('iw-edit-save-status');
    const wordCountEl = document.getElementById('iw-edit-word-count');
    
    if (currentEditingIWChapter.index < 0) return;
    
    const newTitle = titleInput?.value || '';
    const newContent = contentTextarea?.value || '';
    const newWordCount = newContent.replace(/\s/g, '').length;
    
    // 更新本地状态
    const chapter = infiniteWriteState.chapters[currentEditingIWChapter.index];
    if (chapter) {
        chapter.title = newTitle;
        chapter.content = newContent;
        chapter.word_count = newWordCount;
        chapter.summary = newContent.substring(0, 200) + (newContent.length > 200 ? '...' : '');
        
        // 更新总字数
        infiniteWriteState.totalWords = infiniteWriteState.chapters.reduce(
            (sum, ch) => sum + (ch.word_count || 0), 0
        );
        
        // 保存到本地存储
        saveInfiniteWriteData();
        
        // 更新当前编辑状态
        currentEditingIWChapter.chapter = chapter;
        currentEditingIWChapter.modified = false;
        
        // 显示保存状态
        if (saveStatusEl) {
            saveStatusEl.style.display = 'inline';
            saveStatusEl.textContent = '已保存';
        }
        
        // 更新字数显示
        if (wordCountEl) {
            wordCountEl.textContent = newWordCount.toLocaleString() + ' 字';
        }
        
        // 刷新列表
        renderInfiniteWriteChaptersList();
        loadInfiniteWriteNavChapterList();
        
        if (showNotification) {
            showToast('章节已保存 ✓');
        }
        
        // 同步到后端（可选）
        try {
            await apiCall('/api/continuous-write/chapter', 'PUT', {
                chapter_index: currentEditingIWChapter.index,
                title: newTitle,
                content: newContent
            });
        } catch (e) {
            // 后端同步失败不影响本地保存
            console.log('[IWEditor] 后端同步失败，数据已保存在本地:', e);
        }
    }
}

// ===== 删除章节 =====
function deleteIWChapter() {
    if (currentEditingIWChapter.index < 0) return;
    
    const chapter = currentEditingIWChapter.chapter;
    if (!confirm(`确定要删除「第${chapter.chapter_number}章 ${chapter.title || ''}」吗？\n\n此操作不可恢复！`)) {
        return;
    }
    
    // 从列表中移除
    infiniteWriteState.chapters.splice(currentEditingIWChapter.index, 1);
    
    // 更新总字数
    infiniteWriteState.totalWords = infiniteWriteState.chapters.reduce(
        (sum, ch) => sum + (ch.word_count || 0), 0
    );
    
    // 保存到本地存储
    saveInfiniteWriteData();
    
    // 关闭编辑器
    currentEditingIWChapter.modified = false;
    closeIWEditor();
    
    // 刷新界面
    updateInfiniteWriteUI();
    renderInfiniteWriteChaptersList();
    loadInfiniteWriteNavChapterList();
    
    showToast('章节已删除');
}

// ===== 切换查找替换面板 =====
function toggleIWFindReplacePanel() {
    const panel = document.getElementById('iw-find-replace-panel');
    if (!panel) return;
    
    const isVisible = panel.style.display !== 'none';
    panel.style.display = isVisible ? 'none' : 'block';
    
    if (!isVisible) {
        document.getElementById('iw-find-input')?.focus();
    }
}

// ===== 高亮匹配 =====
function highlightIWMatches() {
    const findInput = document.getElementById('iw-find-input');
    const contentTextarea = document.getElementById('iw-edit-content');
    const countEl = document.getElementById('iw-find-count');
    const useRegex = document.getElementById('iw-find-regex')?.checked;
    const caseSensitive = document.getElementById('iw-find-case')?.checked;
    
    if (!findInput || !contentTextarea) return;
    
    const searchText = findInput.value;
    const content = contentTextarea.value;
    
    iwFindMatches = [];
    iwCurrentMatchIndex = -1;
    
    if (!searchText) {
        countEl.textContent = '';
        return;
    }
    
    try {
        let pattern;
        if (useRegex) {
            const flags = caseSensitive ? 'g' : 'gi';
            pattern = new RegExp(searchText, flags);
        } else {
            const escapedSearch = searchText.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
            const flags = caseSensitive ? 'g' : 'gi';
            pattern = new RegExp(escapedSearch, flags);
        }
        
        let match;
        while ((match = pattern.exec(content)) !== null) {
            iwFindMatches.push({
                start: match.index,
                end: match.index + match[0].length,
                text: match[0]
            });
            // 防止无限循环（空匹配）
            if (match[0].length === 0) break;
        }
        
        countEl.textContent = iwFindMatches.length > 0 
            ? `找到 ${iwFindMatches.length} 处`
            : '无匹配';
        countEl.style.color = iwFindMatches.length > 0 ? '#10b981' : '#ef4444';
        
        // 自动跳转到第一个匹配
        if (iwFindMatches.length > 0) {
            iwCurrentMatchIndex = 0;
            scrollToIWMatch(iwCurrentMatchIndex);
        }
        
    } catch (e) {
        countEl.textContent = '正则表达式错误';
        countEl.style.color = '#ef4444';
    }
}

// ===== 滚动到匹配位置 =====
function scrollToIWMatch(index) {
    const contentTextarea = document.getElementById('iw-edit-content');
    if (!contentTextarea || index < 0 || index >= iwFindMatches.length) return;
    
    const match = iwFindMatches[index];
    
    // 选中匹配文本
    contentTextarea.focus();
    contentTextarea.setSelectionRange(match.start, match.end);
    
    // 滚动到可见位置
    const textBefore = contentTextarea.value.substring(0, match.start);
    const lineNumber = (textBefore.match(/\n/g) || []).length;
    const lineHeight = 30;
    contentTextarea.scrollTop = lineNumber * lineHeight - 100;
    
    // 更新计数显示
    const countEl = document.getElementById('iw-find-count');
    if (countEl) {
        countEl.textContent = `${index + 1} / ${iwFindMatches.length}`;
    }
}

// ===== 查找下一个 =====
function findIWNext() {
    if (iwFindMatches.length === 0) return;
    
    iwCurrentMatchIndex = (iwCurrentMatchIndex + 1) % iwFindMatches.length;
    scrollToIWMatch(iwCurrentMatchIndex);
}

// ===== 查找上一个 =====
function findIWPrev() {
    if (iwFindMatches.length === 0) return;
    
    iwCurrentMatchIndex = (iwCurrentMatchIndex - 1 + iwFindMatches.length) % iwFindMatches.length;
    scrollToIWMatch(iwCurrentMatchIndex);
}

// ===== 替换当前 =====
function replaceIWCurrent() {
    const contentTextarea = document.getElementById('iw-edit-content');
    const replaceInput = document.getElementById('iw-replace-input');
    
    if (!contentTextarea || iwCurrentMatchIndex < 0 || iwCurrentMatchIndex >= iwFindMatches.length) return;
    
    const match = iwFindMatches[iwCurrentMatchIndex];
    const content = contentTextarea.value;
    const replacement = replaceInput?.value || '';
    
    // 执行替换
    const newContent = content.substring(0, match.start) + replacement + content.substring(match.end);
    contentTextarea.value = newContent;
    
    // 标记已修改
    currentEditingIWChapter.modified = true;
    document.getElementById('iw-edit-save-status').style.display = 'none';
    
    // 更新字数
    const wordCount = newContent.replace(/\s/g, '').length;
    document.getElementById('iw-edit-word-count').textContent = wordCount.toLocaleString() + ' 字';
    
    // 重新搜索
    highlightIWMatches();
    
    showToast('已替换');
}

// ===== 全部替换 =====
async function replaceIWAll() {
    const contentTextarea = document.getElementById('iw-edit-content');
    const findInput = document.getElementById('iw-find-input');
    const replaceInput = document.getElementById('iw-replace-input');
    const useRegex = document.getElementById('iw-find-regex')?.checked;
    const caseSensitive = document.getElementById('iw-find-case')?.checked;
    
    if (!contentTextarea || !findInput?.value) return;
    
    const searchText = findInput.value;
    const replacement = replaceInput?.value || '';
    
    try {
        if (useRegex) {
            // 使用后端API进行正则替换
            const flags = (caseSensitive ? '' : 'i') + 'g';
            const result = await apiCall('/api/text/regex-replace', 'POST', {
                content: contentTextarea.value,
                pattern: searchText,
                replacement: replacement,
                flags: flags
            });
            
            if (result.success) {
                contentTextarea.value = result.new_content;
                showToast(`已替换 ${result.match_count} 处`);
            } else {
                showToast(result.error, 'error');
                return;
            }
        } else {
            // 简单文本替换
            const escapedSearch = searchText.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
            const flags = caseSensitive ? 'g' : 'gi';
            const pattern = new RegExp(escapedSearch, flags);
            
            const matchCount = (contentTextarea.value.match(pattern) || []).length;
            contentTextarea.value = contentTextarea.value.replace(pattern, replacement);
            
            showToast(`已替换 ${matchCount} 处`);
        }
        
        // 标记已修改
        currentEditingIWChapter.modified = true;
        document.getElementById('iw-edit-save-status').style.display = 'none';
        
        // 更新字数
        const wordCount = contentTextarea.value.replace(/\s/g, '').length;
        document.getElementById('iw-edit-word-count').textContent = wordCount.toLocaleString() + ' 字';
        // 清空匹配
        iwFindMatches = [];
        iwCurrentMatchIndex = -1;
        document.getElementById('iw-find-count').textContent = '';
        
    } catch (e) {
        showToast('替换失败: ' + e.message, 'error');
    }
}

// ===== 覆盖原有的预览函数 =====
// 将 showInfiniteWriteChapterPreview 指向编辑器
window.showInfiniteWriteChapterPreview = showInfiniteWriteChapterEditor;

// 导出函数
window.showInfiniteWriteChapterEditor = showInfiniteWriteChapterEditor;
window.closeIWEditor = closeIWEditor;
window.saveIWChapterChanges = saveIWChapterChanges;
window.deleteIWChapter = deleteIWChapter;
window.toggleIWFindReplacePanel = toggleIWFindReplacePanel;
window.replaceIWAll = replaceIWAll;
window.replaceIWCurrent = replaceIWCurrent;
window.findIWNext = findIWNext;
window.findIWPrev = findIWPrev;

console.log('[iw-editor.js] 无限续写章节编辑器模块已加载');
        