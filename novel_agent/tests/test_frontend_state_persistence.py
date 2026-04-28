"""前端本地状态持久化回归测试。"""

from pathlib import Path
import re


def _read(path: str) -> str:
    return Path(path).read_text(encoding="utf-8")


def _read_many(*paths: str) -> str:
    return "\n".join(_read(path) for path in paths)


def _read_short_story_bundle() -> str:
    return _read_many(
        "novel_agent/web/static/app-short-story.js",
        "novel_agent/web/static/short-story/short-story-state.js",
        "novel_agent/web/static/short-story/short-story-formatters.js",
        "novel_agent/web/static/short-story/short-story-api.js",
        "novel_agent/web/static/short-story/short-story-render.js",
        "novel_agent/web/static/short-story/short-story-events.js",
    )


def _read_novel_to_script_bundle() -> str:
    return _read_many(
        "novel_agent/web/static/app-novel-to-script.js",
        "novel_agent/web/static/novel-to-script/novel-to-script-state.js",
        "novel_agent/web/static/novel-to-script/novel-to-script-api.js",
        "novel_agent/web/static/novel-to-script/novel-to-script-render.js",
        "novel_agent/web/static/novel-to-script/novel-to-script-events.js",
    )


def _extract_function(source: str, name: str) -> str:
    pattern = re.compile(rf"function {re.escape(name)}\([^\)]*\) \{{.*?\n\}}", re.S)
    match = pattern.search(source)
    assert match, f"未找到函数: {name}"
    return match.group(0)


def test_short_story_does_not_restore_transient_loading_state():
    content = _read_short_story_bundle()

    apply_block = _extract_function(content, "applyShortStoryProjectState")
    save_block = _extract_function(content, "saveShortStoryData")

    assert "shortStoryState.loadingAction = defaults.loadingAction;" in apply_block
    assert "shortStoryState.highlightSection = defaults.highlightSection;" in apply_block
    assert "loadingAction:" not in save_block
    assert "highlightSection:" not in save_block
    assert "const preserveTransientState = shortStoryState.loadedProjectId === projectId;" in content
    assert "shortStoryState.loadingAction = transientLoadingAction;" in content
    assert "shortStoryState.highlightSection = transientHighlightSection;" in content


def test_short_story_exposes_inline_loading_feedback():
    content = _read_short_story_bundle()

    assert "function getShortStoryLoadingMeta" in content
    assert "function renderShortStoryLoadingBanner" in content
    assert "short-story-loading-banner" in content
    assert "short-story-loading-spinner" in content
    assert "正在识别素材并生成方案..." in content
    assert "正在生成导语..." in content
    assert "正在生成大纲..." in content
    assert "正在生成正文..." in content
    assert "当前操作：" in content


def test_short_story_uses_project_state_and_final_export_view():
    content = _read_short_story_bundle()

    assert "const SHORT_STORY_PROJECT_STATE_KEY = 'short_story_panel';" in content
    assert "apiCall(`/api/project-state/${SHORT_STORY_PROJECT_STATE_KEY}`, 'POST'" in content
    assert "apiCall(`/api/project-state/${SHORT_STORY_PROJECT_STATE_KEY}`, 'GET')" in content
    assert "function renderShortStoryFinalView" in content
    assert "short-story-export-txt" in content
    assert "short-story-export-md" in content
    assert "short-story-export-docx" in content
    assert "renderShortStoryFinalChapters" in content
    assert "draftSourceInput" in content
    assert "inputAnalysisRawOutput" in content
    assert "fusionRawOutput" in content


def test_short_story_reset_persists_empty_state_before_rerender():
    content = _read_short_story_bundle()

    reset_block = _extract_function(content, "resetShortStoryProjectState")

    assert "clearQueuedShortStoryProjectStateSave();" in reset_block
    assert "applyShortStoryProjectState(createShortStoryProjectState());" in reset_block
    assert "localStorage.setItem(storageKey, JSON.stringify(buildShortStoryPersistedPayload()));" in reset_block
    assert "await persistShortStoryProjectState();" in reset_block
    assert "await resetShortStoryProjectState();" in content


def test_short_story_quality_button_can_recover_after_chapter_regeneration():
    content = _read_many(
        "novel_agent/web/static/short-story/short-story-render.js",
        "novel_agent/web/static/short-story/short-story-api.js",
        "novel_agent/web/static/short-story/short-story-state.js",
    )

    assert "const hasCompleteDraft = plannedChapterCount > 0 && existingChapterCount >= plannedChapterCount;" in content
    assert "canQualityCheck: hasCompleteDraft && !hasPlaceholderBlueprints" in content
    assert "function resetShortStoryReviewArtifacts()" in content
    assert "await persistShortStoryProjectStateNow();" in content


def test_short_story_repairs_missing_blueprints_from_planned_chapter_count():
    content = _read("novel_agent/web/static/short-story/short-story-state.js")

    assert "const planned = Number(workflow.planned_chapters || 0);" in content
    assert "const highestChapter = Math.max(" in content
    assert "title: chapter.title || fallback.title || `第${chapterNumber}章`" in content
    assert "workflow.chapter_blueprints = repaired;" in content
    assert "缺少有效大纲蓝图" in content


def test_short_story_placeholder_blueprints_disable_downstream_actions():
    content = _read_many(
        "novel_agent/web/static/short-story/short-story-formatters.js",
        "novel_agent/web/static/short-story/short-story-render.js",
    )

    assert "function isShortStoryPlaceholderBlueprint" in content
    assert "canQualityCheck: hasCompleteDraft && !hasPlaceholderBlueprints" in content
    assert "canCoherenceReview: !hasPlaceholderBlueprints" in content
    assert "readonly" in content


def test_settings_exposes_global_timeout_controls():
    content = _read_many(
        "novel_agent/web/static/app-settings.js",
        "novel_agent/web/static/settings/app-settings-helpers.js",
        "novel_agent/web/static/settings/app-settings-api.js",
        "novel_agent/web/static/settings/app-settings-renderers.js",
        "novel_agent/web/static/settings/app-settings-events.js",
    )

    assert "apiCall('/api/timeout-settings')" in content
    assert "全局超时设置" in content
    assert "save-timeout-settings" in content
    assert "llm-timeout-${key}" in content
    assert "通用模型请求超时" in content
    assert "short-story-timeout-${key}" in content
    assert "['quality', '质量检查']" in content
    assert "['coherence', '复审定稿']" in content
    assert "safeHostText(cfg.api_base)" in content
    assert "safeErrorText(e)" in content
    assert "window.loadGlobalAPISettingsModern = loadGlobalAPISettings;" in content


def test_settings_split_modules_are_loaded_from_template():
    content = _read("novel_agent/web/templates/index.html")

    assert "/static/settings/app-settings-helpers.js" in content
    assert "/static/settings/app-settings-api.js" in content
    assert "/static/settings/app-settings-renderers.js" in content
    assert "/static/settings/app-settings-events.js" in content
    assert "/static/app-settings.js?v=2.0" in content


def test_copilot_workflow_sync_module_is_loaded_and_used_in_both_chat_paths():
    template = _read("novel_agent/web/templates/index.html")
    core = _read("novel_agent/web/static/app-core.js")
    auto_save = _read("novel_agent/web/static/app-workflow-auto-save.js")

    assert "/static/app-workflow-auto-save.js?v=1.1" in template
    assert "await handleWorkflowAutoSave(res.workflow);" in core
    assert "await handleWorkflowAutoSave(evt.workflow);" in core
    assert "function handleWorkflowAutoSave" in auto_save
    assert "function refreshWorkflowTargetedData" in auto_save
    assert "function mapWorkflowFileKindToProjectDataKey" in auto_save
    assert "function reloadProjectDataAndRefreshView" in auto_save
    assert "function dedupeWorkflowFiles" in auto_save
    assert "await apiCall(`/api/project-data/${dataKey}`, 'GET')" in auto_save
    assert "chapter: 'outline'" in auto_save


def test_settings_styles_are_consolidated_into_style_sheet():
    renderer = _read("novel_agent/web/static/settings/app-settings-renderers.js")
    style = _read("novel_agent/web/static/style.css")

    assert "/* ===== Settings ===== */" in style
    assert ".settings-section-panel" in style
    assert ".settings-button" in style
    assert ".settings-page-title" in style
    assert ".settings-input-action .settings-button" in style
    assert "width: auto;" in style
    assert 'class="setting-section settings-section-panel' in renderer
    assert 'class="settings-button settings-button--primary"' in renderer
    assert "${renderModelOptions(activeConfig, activeModel)}" in renderer
    assert "onmouseover=" not in renderer
    assert "onmouseout=" not in renderer


def test_frontend_security_helpers_escape_quotes_and_handle_invalid_urls():
    content = _read("novel_agent/web/static/app-utils.js")

    assert "replace(/[&<>\"']/g" in content
    assert "\"'\": '&#39;'" in content
    assert "function safeHostname(url, fallback = '未设置')" in content
    assert "return new URL(raw).hostname || fallback;" in content
    assert "return raw;" in content


def test_short_story_uses_bound_settings_link_instead_of_inline_onclick():
    content = _read_short_story_bundle()

    assert 'id="short-story-open-api-settings"' in content
    assert "document.getElementById('short-story-open-api-settings')?.addEventListener('click'" in content
    assert 'onclick="switchModule(\'settings\'); loadSettingsTab(\'api\'); return false;"' not in content
    assert 'escapeHtml(cfg.name)' in content
    assert 'escapeHtml(shortStoryState.globalModel)' in content


def test_short_story_split_modules_are_loaded_from_template():
    content = _read("novel_agent/web/templates/index.html")

    assert "/static/short-story/short-story-state.js" in content
    assert "/static/short-story/short-story-formatters.js" in content
    assert "/static/short-story/short-story-api.js" in content
    assert "/static/short-story/short-story-render.js" in content
    assert "/static/short-story/short-story-events.js" in content
    assert "/static/app-short-story.js?v=2.0" in content


def test_short_story_unified_input_and_fusion_flow_strings_exist():
    content = _read_short_story_bundle()

    assert "统一创作输入" in content
    assert "系统会自动识别并生成 3 个融合方案" in content
    assert "识别把握：" in content
    assert "用这版替换输入" in content
    assert "draftSourceInput" in content
    assert "getShortStoryFusionCards" in content
    assert "renderShortStoryInputAnalysisSummary" in content
    assert "getShortStorySuggestedSourceInput" in content
    assert "/api/short-story/input/analyze" in content
    assert "/api/short-story/fusion-options/generate" in content
    assert "/api/short-story/fusion-options/select" in content


def test_novel_to_script_uses_project_state_and_export_actions():
    content = _read_novel_to_script_bundle()

    assert "const NOVEL_TO_SCRIPT_PROJECT_STATE_KEY = 'novel_to_script_draft';" in content
    assert "apiCall('/api/novel-to-script/state', 'POST'" in content
    assert "apiCall('/api/novel-to-script/state', 'GET')" in content
    assert "apiCall('/api/novel-to-script/convert', 'POST'" in content
    assert "apiFormCall('/api/novel-to-script/import', formData)" in content
    assert "novel-to-script-export-txt" in content
    assert "novel-to-script-export-md" in content
    assert "novel-to-script-export-docx" in content
    assert "data-result-tab=\"text\"" in content
    assert "data-result-tab=\"scenes\"" in content
    assert "data-result-tab=\"characters\"" in content
    assert "自动识别（推荐）" in content
    assert "getNovelToScriptStrategySummary" in content
    assert "recommendedMode" in content
    assert "function getNovelToScriptLoadingMeta" in content
    assert "novel-to-script-loading-banner" in content
    assert "function renderNovelToScriptBatchSummary" in content
    assert "batch_summaries" in content
    assert "reconvertNovelToScriptBatch" in content
    assert "data-retry-batch" in content
    assert "syncNovelToScriptResultFromText" in content
    assert "window.renderNovelToScriptInterface = renderNovelToScriptInterface;" in content


def test_novel_to_script_module_is_wired_into_template_and_core_navigation():
    template = _read("novel_agent/web/templates/index.html")
    core = _read("novel_agent/web/static/app-core.js")
    nav = _read("novel_agent/web/static/app-nav.js")
    style = _read("novel_agent/web/static/style.css")

    assert 'data-module="novel-to-script"' in template
    assert "/static/novel-to-script/novel-to-script-state.js" in template
    assert "/static/novel-to-script/novel-to-script-api.js" in template
    assert "/static/novel-to-script/novel-to-script-render.js" in template
    assert "/static/novel-to-script/novel-to-script-events.js" in template
    assert "/static/app-novel-to-script.js?v=1.0" in template
    assert "normalizedModuleId === 'novel-to-script'" in core
    assert "renderNovelToScriptInterface" in core
    assert "case 'novel-to-script':" in nav
    assert "renderNovelToScriptNavPanel" in nav
    assert "/* ===== 小说转剧本模块 ===== */" in style


def test_legacy_app_global_api_page_shows_deprecation_notice():
    content = _read("novel_agent/web/static/app.js")
    block = _extract_function(content, "loadGlobalAPISettings")

    assert "window.loadGlobalAPISettingsModern" in block
    assert "旧版设置页已废弃" in block
    assert "<code>app-settings.js</code>" in block


def test_infinite_write_persists_pending_summary_removal_and_avoids_duplicates():
    content = _read("novel_agent/web/static/continuous_write.js")

    show_block = _extract_function(content, "showPendingSummary")
    confirm_block = _extract_function(content, "confirmSummary")

    assert "const exists = infiniteWriteState.pendingSummaries.some(" in show_block
    assert "if (!exists) {" in show_block
    assert "saveInfiniteWriteData();" in confirm_block


def test_infinite_write_exposes_direct_export_actions():
    content = _read("novel_agent/web/static/continuous_write.js")

    assert "iw-export-txt" in content
    assert "iw-export-md" in content
    assert "iw-export-docx" in content
    assert "function buildInfiniteWriteExportPayload()" in content
    assert "function exportInfiniteWriteFile(format)" in content
    assert "window.exportInfiniteWriteFile = exportInfiniteWriteFile;" in content


def test_infinite_write_exposes_character_anchor_panel():
    content = _read("novel_agent/web/static/continuous_write.js")

    assert "function loadInfiniteWriteContinuationContext()" in content
    assert "function renderInfiniteWriteCharacterAnchors()" in content
    assert "function toggleInfiniteWriteMemoryPreview" in content
    assert "人物和设定锚点" in content
    assert "这里展示系统当前记住的人物状态和最近剧情" in content
    assert "先看系统记忆" in content
