/**
 * 文思Agent - 章节管理模块
 * 包含：章节CRUD、章节编辑器、自动保存
 */

// ===== 章节管理功能 =====

let currentEditingChapterIndex = null;
let autoSaveTimer = null;

function addNewChapter() {
    showAddChapterDialog();
}

function showAddChapterDialog() {
    const modal = document.getElementById('modal-container');
    modal.classList.remove('hidden');
    
    const chapters = store.projectData.outline || [];
    const nextChapterNum = chapters.length + 1;
    
    modal.innerHTML = `
        <div style="position: fixed; top: 0; left: 0; right: 0; bottom: 0; background: rgba(0,0,0,0.6); display: flex; align-items: center; justify-content: center; z-index: 1000;">
            <div style="background: var(--bg-panel); border: 1px solid var(--border-color); border-radius: 16px; padding: 30px; width: 500px; max-width: 90%;">
                <h3 style="color: var(--text-primary); margin-bottom: 24px; font-size: 18px;">
                    <i class="ri-file-add-line" style="margin-right: 8px;"></i>
                    添加新章节
                </h3>
                
                <div style="margin-bottom: 20px;">
                    <label style="display: block; font-size: 13px; color: var(--text-secondary); margin-bottom: 8px;">章节标题</label>
                    <input type="text" id="new-chapter-title" placeholder="例如：初入江湖、命运之夜..."
                        value="第${nextChapterNum}章"
                        style="width: 100%; background: rgba(0,0,0,0.3); border: 1px solid var(--border-color); padding: 12px; color: var(--text-primary); border-radius: 8px; font-size: 14px;">
                </div>
                
                <div style="margin-bottom: 24px;">
                    <label style="display: block; font-size: 13px; color: var(--text-secondary); margin-bottom: 8px;">章节摘要 (可选)</label>
                    <textarea id="new-chapter-summary" rows="3" placeholder="简要描述本章主要内容..."
                        style="width: 100%; background: rgba(0,0,0,0.3); border: 1px solid var(--border-color); padding: 12px; color: var(--text-primary); border-radius: 8px; font-size: 14px; resize: vertical;"></textarea>
                </div>
                
                <div style="display: flex; gap: 12px;">
                    <button id="cancel-add-chapter" style="flex: 1; padding: 12px; background: rgba(255,255,255,0.1); border: 1px solid var(--border-color); color: var(--text-primary); border-radius: 8px; cursor: pointer;">取消</button>
                    <button id="confirm-add-chapter" style="flex: 1; padding: 12px; background: var(--accent-color); border: none; color: white; border-radius: 8px; cursor: pointer; font-weight: 600;">创建章节</button>
                </div>
            </div>
        </div>
    `;
    
    // 自动聚焦输入框并选中文本
    setTimeout(() => {
        const input = document.getElementById('new-chapter-title');
        input.focus();
        input.select();
    }, 100);
    
    // 取消
    document.getElementById('cancel-add-chapter').addEventListener('click', () => {
        modal.classList.add('hidden');
        modal.innerHTML = '';
    });
    
    // 确认
    document.getElementById('confirm-add-chapter').addEventListener('click', () => {
        const title = document.getElementById('new-chapter-title').value.trim();
        const summary = document.getElementById('new-chapter-summary').value.trim();
        
        if (!title) {
            showToast('请输入章节标题', 'error');
            return;
        }
        
        store.projectData.outline.push({
            title: title,
            summary: summary,
            content: '',
            created_at: new Date().toISOString()
        });
        saveOutlineData();
        renderNavPanel('write');
        
        modal.classList.add('hidden');
        modal.innerHTML = '';
        showToast(`章节「${title}」已创建`);
        
        // 自动打开新创建的章节
        openChapterEditor(store.projectData.outline.length - 1);
    });
    
    // 回车确认
    document.getElementById('new-chapter-title').addEventListener('keydown', (e) => {
        if (e.key === 'Enter') {
            document.getElementById('confirm-add-chapter').click();
        }
    });
}

function editChapterTitle(index) {
    const chapter = store.projectData.outline[index];
    if (!chapter) return;

    const newTitle = prompt('修改章节标题：', chapter.title);
    if (newTitle && newTitle.trim() && newTitle !== chapter.title) {
        store.projectData.outline[index].title = newTitle.trim();
        saveOutlineData();
        renderNavPanel('write'); // 刷新列表，传入正确的模块ID
        showToast('标题已更新');
    }
}

function deleteChapter(index) {
    const chapter = store.projectData.outline[index];
    if (!chapter) return;

    if (confirm(`确定要删除「第${index + 1}章 ${chapter.title}」吗？\n\n此操作不可恢复！`)) {
        store.projectData.outline.splice(index, 1);
        saveOutlineData();
        renderNavPanel('write'); // 刷新列表，传入正确的模块ID

        // 如果正在编辑这个章节，清空编辑器
        if (currentEditingChapterIndex === index) {
            showEmptyEditor();
            currentEditingChapterIndex = null;
        }

        showToast('章节已删除');
    }
}

// 多Agent写作模式热点状态
let multiAgentShowTrends = true;

function openChapterEditor(index) {
    const chapter = store.projectData.outline[index];
    if (!chapter) return;

    currentEditingChapterIndex = index;
    updateBreadcrumbs(['写作', `第${index + 1}章 ${chapter.title}`]);

    const wordCount = (chapter.content || '').replace(/\s/g, '').length;

    ui.workspace.innerHTML = `
        <div class="editor-container" style="display: flex; gap: 20px; height: 100%; padding: 24px;">
            <!-- 主编辑区 -->
            <div style="flex: 1; display: flex; flex-direction: column; min-width: 0;">
                <div class="editor-header" style="display: flex; align-items: center; gap: 16px; margin-bottom: 16px; padding-bottom: 16px; border-bottom: 1px solid var(--border-color);">
                    <input type="text" id="chapter-title-input" class="title-input" value="${chapter.title || ''}"
                        placeholder="章节标题" style="flex: 1; background: transparent; border: none; font-size: 24px; font-weight: 600; color: var(--text-primary); outline: none;">
                    <div style="display: flex; align-items: center; gap: 12px; color: var(--text-secondary); font-size: 13px;">
                        <span id="word-count">${wordCount} 字</span>
                        <span id="save-status" style="color: #10b981;">已保存</span>
                    </div>
                    <button id="toggle-trends-btn" style="padding: 8px 12px; background: rgba(239, 68, 68, 0.15); border: 1px solid rgba(239, 68, 68, 0.4); color: #ef4444; border-radius: 6px; cursor: pointer; font-weight: 500;" title="热点灵感">
                        <i class="ri-fire-fill"></i>
                    </button>
                    <button id="ai-continue-btn" style="padding: 8px 16px; background: linear-gradient(135deg, #8b5cf6, #6366f1); border: none; color: white; border-radius: 6px; cursor: pointer; font-weight: 500;">
                        <i class="ri-magic-line"></i> AI续写
                    </button>
                    <button id="word-check-btn" style="padding: 8px 16px; background: rgba(255,255,255,0.1); border: 1px solid var(--border-color); color: var(--text-primary); border-radius: 6px; cursor: pointer;">
                        <i class="ri-search-eye-line"></i> 词汇检测
                    </button>
                    <button id="save-chapter-btn" style="padding: 8px 20px; background: var(--accent-color); border: none; color: white; border-radius: 6px; cursor: pointer; font-weight: 500;">
                        <i class="ri-save-line"></i> 保存
                    </button>
                </div>
                <textarea id="chapter-content-input" class="body-input" placeholder="开始创作..."
                    style="flex: 1; background: rgba(0,0,0,0.2); border: 1px solid var(--border-color); border-radius: 8px; padding: 20px; color: var(--text-primary); font-size: 16px; line-height: 1.8; resize: none; outline: none;">${chapter.content || ''}</textarea>
            </div>
            
            <!-- 热点灵感侧边栏 -->
            <div id="multi-agent-trends-sidebar" style="${multiAgentShowTrends ? '' : 'display: none;'} width: 320px; flex-shrink: 0; overflow: hidden;">
                <div id="multi-agent-trends-panel" style="height: 100%;">
                    <!-- 热点面板将在这里渲染 -->
                </div>
            </div>
        </div>
    `;

    // 绑定事件
    const titleInput = document.getElementById('chapter-title-input');
    const contentInput = document.getElementById('chapter-content-input');
    const saveBtn = document.getElementById('save-chapter-btn');
    const wordCountEl = document.getElementById('word-count');
    const saveStatusEl = document.getElementById('save-status');

    // 自动保存
    const triggerAutoSave = () => {
        saveStatusEl.textContent = '保存中...';
        saveStatusEl.style.color = 'var(--accent-color)';

        clearTimeout(autoSaveTimer);
        autoSaveTimer = setTimeout(() => {
            saveCurrentChapter();
            saveStatusEl.textContent = '已保存';
            saveStatusEl.style.color = '#10b981';
        }, 1000);
    };

    titleInput.addEventListener('input', triggerAutoSave);
    contentInput.addEventListener('input', () => {
        // 更新字数
        const count = contentInput.value.replace(/\s/g, '').length;
        wordCountEl.textContent = `${count} 字`;
        triggerAutoSave();
    });

    // AI续写按钮
    const aiContinueBtn = document.getElementById('ai-continue-btn');
    const wordCheckBtn = document.getElementById('word-check-btn');
    
    aiContinueBtn.addEventListener('click', async () => {
        const content = contentInput.value.trim();
        if (!content) {
            showToast('请先输入一些内容作为上下文', 'warning');
            return;
        }
        
        aiContinueBtn.disabled = true;
        aiContinueBtn.innerHTML = '<i class="ri-loader-4-line"></i> AI续写中...';
        
        try {
            const chapter = store.projectData.outline[currentEditingChapterIndex];
            const response = await apiCall('/api/chapter', 'POST', {
                chapter_index: currentEditingChapterIndex,
                chapter_title: chapter.title,
                existing_content: content,
                action: 'continue',
                word_count: 500  // 续写约500字
            });
            
            if (response.content) {
                // 追加AI生成的内容
                contentInput.value = content + '\n\n' + response.content;
                const newCount = contentInput.value.replace(/\s/g, '').length;
                wordCountEl.textContent = `${newCount} 字`;
                saveCurrentChapter();
                showToast('AI续写完成 ✓');
            } else if (response.error) {
                showToast('AI续写失败: ' + response.error, 'error');
            }
        } catch (e) {
            showToast('AI续写失败: ' + e.message, 'error');
        } finally {
            aiContinueBtn.disabled = false;
            aiContinueBtn.innerHTML = '<i class="ri-magic-line"></i> AI续写';
        }
    });
    
    wordCheckBtn.addEventListener('click', () => {
        const content = contentInput.value.trim();
        if (!content) {
            showToast('请先输入需要检测的内容', 'warning');
            return;
        }
        
        showWordCheckDialog(content, (newContent) => {
            contentInput.value = newContent;
            const newCount = newContent.replace(/\s/g, '').length;
            wordCountEl.textContent = `${newCount} 字`;
            saveCurrentChapter();
        });
    });
    
    saveBtn.addEventListener('click', () => {
        clearTimeout(autoSaveTimer);
        saveCurrentChapter();
        saveStatusEl.textContent = '已保存';
        saveStatusEl.style.color = '#10b981';
        showToast('章节已保存');
    });
    
    // 热点面板开关按钮
    const toggleTrendsBtn = document.getElementById('toggle-trends-btn');
    if (toggleTrendsBtn) {
        toggleTrendsBtn.addEventListener('click', () => {
            multiAgentShowTrends = !multiAgentShowTrends;
            const sidebar = document.getElementById('multi-agent-trends-sidebar');
            if (sidebar) {
                sidebar.style.display = multiAgentShowTrends ? '' : 'none';
            }
            toggleTrendsBtn.style.background = multiAgentShowTrends
                ? 'rgba(239, 68, 68, 0.15)'
                : 'rgba(255,255,255,0.1)';
            toggleTrendsBtn.style.borderColor = multiAgentShowTrends
                ? 'rgba(239, 68, 68, 0.4)'
                : 'var(--border-color)';
            toggleTrendsBtn.style.color = multiAgentShowTrends
                ? '#ef4444'
                : 'var(--text-secondary)';
            
            // 保存设置
            if (typeof saveTrendsVisibility === 'function') {
                const infiniteWriteShow = typeof trendsState !== 'undefined'
                    ? trendsState.config?.showInInfiniteWrite ?? true
                    : true;
                saveTrendsVisibility(infiniteWriteShow, multiAgentShowTrends);
            }
        });
    }
    
    // 初始化热点面板
    initMultiAgentTrends();
}

// ===== 初始化多Agent写作热点面板 =====
async function initMultiAgentTrends() {
    // 加载热点配置
    if (typeof loadTrendsConfig === 'function') {
        await loadTrendsConfig();
    }
    
    // 检查是否在多Agent模式显示热点
    if (typeof trendsState !== 'undefined' && trendsState.config) {
        multiAgentShowTrends = trendsState.config.showInMultiAgent !== false;
    }
    
    // 更新侧边栏显示状态
    const sidebar = document.getElementById('multi-agent-trends-sidebar');
    if (sidebar) {
        sidebar.style.display = multiAgentShowTrends ? '' : 'none';
    }
    
    // 更新按钮状态
    const toggleBtn = document.getElementById('toggle-trends-btn');
    if (toggleBtn) {
        toggleBtn.style.background = multiAgentShowTrends
            ? 'rgba(239, 68, 68, 0.15)'
            : 'rgba(255,255,255,0.1)';
        toggleBtn.style.borderColor = multiAgentShowTrends
            ? 'rgba(239, 68, 68, 0.4)'
            : 'var(--border-color)';
        toggleBtn.style.color = multiAgentShowTrends
            ? '#ef4444'
            : 'var(--text-secondary)';
    }
    
    // 渲染热点面板
    if (multiAgentShowTrends && typeof renderTrendsPanel === 'function') {
        renderTrendsPanel('multi-agent-trends-panel', {
            compact: false,
            showToggle: false,
            maxItems: 15,
            onSelect: (title, item) => {
                useHotTrendForChapter(title, item);
            }
        });
    }
}

// ===== 使用热点作为章节灵感 =====
function useHotTrendForChapter(title, item) {
    const contentInput = document.getElementById('chapter-content-input');
    if (contentInput) {
        const currentContent = contentInput.value;
        const cursorPos = contentInput.selectionStart;
        
        // 在光标位置插入热点内容
        const insertText = `【热点灵感：${title}】`;
        const newContent = currentContent.substring(0, cursorPos) + insertText + currentContent.substring(cursorPos);
        
        contentInput.value = newContent;
        contentInput.focus();
        
        // 设置光标位置到插入文本之后
        const newPos = cursorPos + insertText.length;
        contentInput.setSelectionRange(newPos, newPos);
        
        // 更新字数
        const wordCountEl = document.getElementById('word-count');
        if (wordCountEl) {
            const count = newContent.replace(/\s/g, '').length;
            wordCountEl.textContent = `${count} 字`;
        }
        
        // 触发自动保存
        const saveStatusEl = document.getElementById('save-status');
        if (saveStatusEl) {
            saveStatusEl.textContent = '保存中...';
            saveStatusEl.style.color = 'var(--accent-color)';
        }
        
        clearTimeout(autoSaveTimer);
        autoSaveTimer = setTimeout(() => {
            saveCurrentChapter();
            if (saveStatusEl) {
                saveStatusEl.textContent = '已保存';
                saveStatusEl.style.color = '#10b981';
            }
        }, 1000);
        
        showToast('热点灵感已插入 ✨');
    }
}

function saveCurrentChapter() {
    if (currentEditingChapterIndex === null) return;

    const titleInput = document.getElementById('chapter-title-input');
    const contentInput = document.getElementById('chapter-content-input');

    if (titleInput && contentInput) {
        store.projectData.outline[currentEditingChapterIndex].title = titleInput.value;
        store.projectData.outline[currentEditingChapterIndex].content = contentInput.value;
        store.projectData.outline[currentEditingChapterIndex].updated_at = new Date().toISOString();
        saveOutlineData();

        // 更新左侧列表中的标题
        renderNavPanel('write'); // 刷新列表，传入正确的模块ID
    }
}

async function saveOutlineData() {
    try {
        await apiCall('/api/project-data/outline', 'POST', {
            data: store.projectData.outline
        });
    } catch (e) {
        console.error('Failed to save outline:', e);
    }
}

// 全局暴露章节管理函数
window.currentEditingChapterIndex = currentEditingChapterIndex;
window.addNewChapter = addNewChapter;
window.showAddChapterDialog = showAddChapterDialog;
window.editChapterTitle = editChapterTitle;
window.deleteChapter = deleteChapter;
window.openChapterEditor = openChapterEditor;
window.saveCurrentChapter = saveCurrentChapter;
window.saveOutlineData = saveOutlineData;
window.initMultiAgentTrends = initMultiAgentTrends;
window.useHotTrendForChapter = useHotTrendForChapter;

console.log('[app-chapters.js] 章节管理模块已加载');