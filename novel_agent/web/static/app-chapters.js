/**
 * 山海·云烟 - 章节管理模块
 * 包含：章节CRUD、章节编辑器、自动保存
 */

// ===== 章节管理功能 =====

let currentEditingChapterIndex = null;
let autoSaveTimer = null;

function getStoredChapters() {
    if (!Array.isArray(store.projectData.chapters)) {
        store.projectData.chapters = [];
    }
    return store.projectData.chapters;
}

function isChapterSettingsPlaceholder(chapter) {
    if (!chapter || typeof chapter !== 'object') return false;
    if (chapter.created_from === 'chapter_settings_placeholder') return true;
    return chapter.source === 'chapter_settings' && !String(chapter.content || '').trim();
}

function getVisibleStoredChapters() {
    return getStoredChapters().filter((chapter) => !isChapterSettingsPlaceholder(chapter));
}

function getStoredChapterIndexFromVisibleIndex(visibleIndex) {
    const chapters = getStoredChapters();
    let visibleCount = -1;
    for (let index = 0; index < chapters.length; index += 1) {
        if (isChapterSettingsPlaceholder(chapters[index])) {
            continue;
        }
        visibleCount += 1;
        if (visibleCount === visibleIndex) {
            return index;
        }
    }
    return -1;
}

function getChapterDisplayNumber(chapter, fallback) {
    const parsed = Number(chapter?.chapter_number || chapter?.chapter || fallback || 1);
    return Number.isFinite(parsed) && parsed > 0 ? parsed : (fallback || 1);
}

function getNextStoredChapterNumber() {
    const numbers = getVisibleStoredChapters()
        .map((chapter, index) => getChapterDisplayNumber(chapter, index + 1))
        .filter((number) => number > 0);
    return (numbers.length > 0 ? Math.max(...numbers) : 0) + 1;
}

function getChapterSettingPlaceholders() {
    const settings = Array.isArray(store.projectData.chapter_settings) ? store.projectData.chapter_settings : [];
    return settings.map((item, index) => {
        const chapterNumber = Number(item.chapter_number || item.chapter || index + 1) || (index + 1);
        return {
            chapter_number: chapterNumber,
            title: item.name || item.title || `第${chapterNumber}章`,
            summary: item.description || item.chapter_goal || item.key_event || '',
            content: '',
            chapter_goal: item.chapter_goal || '',
            key_event: item.key_event || '',
            ending_hook: item.ending_hook || '',
            source: 'chapter_settings'
        };
    });
}

function getMultiAgentChapters() {
    return getVisibleStoredChapters();
}

function ensureChapterRecord(index) {
    const chapters = getStoredChapters();
    const storedIndex = getStoredChapterIndexFromVisibleIndex(index);
    if (storedIndex >= 0 && chapters[storedIndex]) {
        return chapters[storedIndex];
    }

    return null;
}

function addNewChapter() {
    showAddChapterDialog();
}

function showCollaborativeImportDialog() {
    const modal = document.getElementById('modal-container');
    if (!modal) return;

    modal.classList.remove('hidden');
    modal.innerHTML = `
        <div style="position: fixed; top: 0; left: 0; right: 0; bottom: 0; background: rgba(0,0,0,0.65); display: flex; align-items: center; justify-content: center; z-index: 1000; padding: 20px;">
            <div style="background: var(--bg-panel); border: 1px solid var(--border-color); border-radius: 14px; width: 560px; max-width: 100%; padding: 24px;">
                <h3 style="margin: 0 0 16px 0; color: var(--text-primary); font-size: 18px; display: flex; align-items: center; gap: 8px;">
                    <i class="ri-upload-cloud-2-line"></i>
                    导入小说到多Agent模式
                </h3>
                <p style="margin: 0 0 14px 0; color: var(--text-secondary); font-size: 13px; line-height: 1.7;">
                    支持 <code>.txt</code> / <code>.md</code> / <code>.docx</code>。导入后会立即自动整理协作记忆，并反向补全角色卡、世界观和大纲。
                </p>

                <div style="margin-bottom: 14px;">
                    <label style="display: block; margin-bottom: 6px; font-size: 12px; color: var(--text-secondary);">选择文件</label>
                    <input id="collab-import-file" type="file" accept=".txt,.md,.docx"
                        style="width: 100%; background: rgba(0,0,0,0.2); border: 1px solid var(--border-color); border-radius: 8px; padding: 10px; color: var(--text-primary);">
                </div>

                <div style="margin-bottom: 20px;">
                    <label style="display: block; margin-bottom: 6px; font-size: 12px; color: var(--text-secondary);">导入方式</label>
                    <select id="collab-import-merge-mode"
                        style="width: 100%; background: rgba(0,0,0,0.2); border: 1px solid var(--border-color); border-radius: 8px; padding: 10px; color: var(--text-primary);">
                        <option value="replace">替换现有章节（推荐）</option>
                        <option value="append">追加到现有章节</option>
                    </select>
                </div>

                <div style="display: flex; gap: 10px;">
                    <button id="collab-import-cancel" style="flex: 1; padding: 11px; border-radius: 8px; border: 1px solid var(--border-color); background: rgba(255,255,255,0.1); color: var(--text-primary); cursor: pointer;">
                        取消
                    </button>
                    <button id="collab-import-confirm" style="flex: 1; padding: 11px; border-radius: 8px; border: none; background: linear-gradient(135deg, #22c55e, #16a34a); color: #fff; font-weight: 600; cursor: pointer;">
                        开始导入
                    </button>
                </div>
            </div>
        </div>
    `;

    const closeModal = () => {
        modal.classList.add('hidden');
        modal.innerHTML = '';
    };

    document.getElementById('collab-import-cancel')?.addEventListener('click', closeModal);
    document.getElementById('collab-import-confirm')?.addEventListener('click', async () => {
        const fileInput = document.getElementById('collab-import-file');
        const mergeModeEl = document.getElementById('collab-import-merge-mode');
        const btn = document.getElementById('collab-import-confirm');
        const file = fileInput?.files?.[0];
        const mergeMode = mergeModeEl?.value || 'append';

        if (!file) {
            showToast('请先选择文件', 'warning');
            return;
        }

        btn.disabled = true;
        btn.innerHTML = '<i class="ri-loader-4-line" style="animation: spin 1s linear infinite;"></i> 导入中...';

        try {
            const formData = new FormData();
            formData.append('novel_file', file);
            formData.append('merge_mode', mergeMode);

            const response = await apiFormCall('/api/projects/import-novel', formData, 'POST');
            if (!response.success) {
                throw new Error(response.error || '导入失败');
            }

            await loadCurrentProjectData();
            renderNavPanel('write');
            closeModal();

            const importedCount = response.imported_chapters || 0;
            const supplement = response.material_supplement || {};
            const added = Number(supplement.total_added || 0);
            const suffix = added > 0 ? `，补全 ${added} 条资料` : '，资料已检查';
            showToast(`已导入 ${importedCount} 章，协作记忆已自动整理${suffix}`, 'success');

            if (Array.isArray(store.projectData.chapters) && store.projectData.chapters.length > 0) {
                const openIndex = Math.max(0, store.projectData.chapters.length - importedCount);
                openChapterEditor(openIndex);
            }
        } catch (e) {
            showToast(`导入失败: ${e.message}`, 'error');
        } finally {
            btn.disabled = false;
            btn.innerHTML = '开始导入';
        }
    });
}

function showAddChapterDialog() {
    const modal = document.getElementById('modal-container');
    modal.classList.remove('hidden');

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
                        value=""
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
        
        getStoredChapters().push({
            title: title,
            chapter_number: getNextStoredChapterNumber(),
            summary: summary,
            content: '',
            created_at: new Date().toISOString()
        });
        saveChaptersData();
        renderNavPanel('write');
        
        modal.classList.add('hidden');
        modal.innerHTML = '';
        showToast(`章节「${title}」已创建`);
        
        // 自动打开新创建的章节
        openChapterEditor(getStoredChapters().length - 1);
    });
    
    // 回车确认
    document.getElementById('new-chapter-title').addEventListener('keydown', (e) => {
        if (e.key === 'Enter') {
            document.getElementById('confirm-add-chapter').click();
        }
    });
}

function editChapterTitle(index) {
    const chapter = ensureChapterRecord(index);
    if (!chapter) return;

    const newTitle = prompt('修改章节标题：', chapter.title);
    if (newTitle && newTitle.trim() && newTitle !== chapter.title) {
        chapter.title = newTitle.trim();
        saveChaptersData();
        renderNavPanel('write'); // 刷新列表，传入正确的模块ID
        showToast('标题已更新');
    }
}

async function deleteChapter(index) {
    const chapter = getMultiAgentChapters()[index];
    if (!chapter) return;

    const chapterNumber = getChapterDisplayNumber(chapter, index + 1);
    if (await window.showConfirmDialog(`确定要删除「${formatChapterDisplay(chapterNumber, chapter.title)}」吗？\n\n此操作不可恢复！`)) {
        const storedIndex = getStoredChapterIndexFromVisibleIndex(index);
        if (storedIndex < 0) return;
        getStoredChapters().splice(storedIndex, 1);
        saveChaptersData();
        renderNavPanel('write'); // 刷新列表，传入正确的模块ID

        // 如果正在编辑这个章节，清空编辑器
        if (currentEditingChapterIndex === index) {
            showEmptyEditor();
            currentEditingChapterIndex = null;
        }

        showToast('章节已删除');
    }
}


function openChapterEditor(index) {
    const chapter = ensureChapterRecord(index);
    if (!chapter) return;

    currentEditingChapterIndex = index;
    const chapterNumber = getChapterDisplayNumber(chapter, index + 1);
    updateBreadcrumbs(['写作', formatChapterDisplay(chapterNumber, chapter.title)]);

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
            const chapter = ensureChapterRecord(currentEditingChapterIndex);
            const trendsEnabled = typeof trendsState !== 'undefined'
                ? trendsState.enabled !== false
                : false;
            const trendsPlatforms = Array.isArray(trendsState?.config?.defaultPlatforms)
                && trendsState.config.defaultPlatforms.length > 0
                ? trendsState.config.defaultPlatforms
                : ['toutiao', 'douyin'];
            const response = await apiCall('/api/chapter', 'POST', {
                chapter_index: currentEditingChapterIndex,
                chapter_title: chapter.title,
                existing_content: content,
                action: 'continue',
                word_count: 500,  // 续写约500字
                enable_trends: trendsEnabled,
                trends_platforms: trendsPlatforms,
                trends_query: `${chapter.title || ''} ${content.slice(-120)}`
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
        const content = contentInput.value;
        if (!content.trim()) {
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
    
}

function saveCurrentChapter() {
    if (currentEditingChapterIndex === null) return;

    const titleInput = document.getElementById('chapter-title-input');
    const contentInput = document.getElementById('chapter-content-input');

    if (titleInput && contentInput) {
        const chapter = ensureChapterRecord(currentEditingChapterIndex);
        if (!chapter) return;
        chapter.title = titleInput.value;
        chapter.content = contentInput.value;
        chapter.updated_at = new Date().toISOString();
        saveChaptersData();

        // 更新左侧列表中的标题
        renderNavPanel('write'); // 刷新列表，传入正确的模块ID
    }
}

async function saveOutlineData() {
    return saveChaptersData();
}

async function saveChaptersData() {
    try {
        await apiCall('/api/project-data/chapters', 'POST', {
            data: getVisibleStoredChapters()
        });
    } catch (e) {
        console.error('Failed to save chapters:', e);
    }
}

// 全局暴露章节管理函数
window.currentEditingChapterIndex = currentEditingChapterIndex;
window.addNewChapter = addNewChapter;
window.showCollaborativeImportDialog = showCollaborativeImportDialog;
window.showAddChapterDialog = showAddChapterDialog;
window.editChapterTitle = editChapterTitle;
window.deleteChapter = deleteChapter;
window.openChapterEditor = openChapterEditor;
window.saveCurrentChapter = saveCurrentChapter;
window.saveOutlineData = saveOutlineData;
window.saveChaptersData = saveChaptersData;
window.getMultiAgentChapters = getMultiAgentChapters;
window.getChapterDisplayNumber = getChapterDisplayNumber;

console.log('[app-chapters.js] 章节管理模块已加载');
