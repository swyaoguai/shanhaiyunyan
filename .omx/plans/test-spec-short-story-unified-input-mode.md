# Test Spec: 短篇创作统一输入 + 融合方案模式

## Scope
- short story service workflow
- short story routes
- router guidance
- short story frontend state/render/events
- regression on existing review/export behavior

## Unit / Service Tests

Target file: `novel_agent/tests/test_short_story_service.py`

### Add
1. `test_short_story_start_workflow_accepts_unified_source_input`
   - given `source_input="灵感：..."`  
   - assert workflow enters `analyzing_source_input`
2. `test_short_story_records_input_analysis_and_detected_material_types`
   - assert `input_analysis`, `detected_material_types`, `input_confidence` written
3. `test_short_story_registers_three_fusion_candidates`
   - assert exactly 3 candidates
4. `test_short_story_select_fusion_option_advances_to_generating_synopsis`
5. `test_short_story_synopsis_prompt_uses_selected_fusion_not_raw_keywords`
6. `test_short_story_fusion_prompt_enforces_refresh_of_characters_setting_events`
7. `test_short_story_start_workflow_migrates_legacy_keywords_to_unified_input`

### Keep green
- Existing capabilities + workflow tests around chapter planning and prompt generation must still pass after adaptation. Baseline examples: `novel_agent/tests/test_short_story_service.py:21`, `novel_agent/tests/test_short_story_service.py:35`

## Route Tests

Target file: `novel_agent/tests/test_short_story_routes.py`

### Add
1. `test_short_story_start_route_accepts_source_input`
2. `test_short_story_input_analyze_route_returns_detected_materials`
3. `test_short_story_fusion_generate_route_returns_three_options`
4. `test_short_story_fusion_select_route_advances_workflow`
5. `test_short_story_routes_complete_workflow_from_selected_fusion`
6. `test_router_guides_unified_short_story_material_input_to_panel`

### Update
- Existing complete workflow baseline at `novel_agent/tests/test_short_story_routes.py:120` should start from unified input rather than raw keywords-only JSON.
- Existing router test at `novel_agent/tests/test_short_story_routes.py:889` should no longer assert “固定入口 + 填词条 + 5 条导语” wording.

## Frontend State / Bundle Regression

Target file: `novel_agent/tests/test_frontend_state_persistence.py`

### Add
1. Assert bundle contains `draftSourceInput` and legacy migration from `draftKeywords`
2. Assert bundle no longer hardcodes old “创作词条” / “先填词条，再直接点生成导语” copy
3. Assert bundle includes fusion-option rendering and selection hooks
4. Assert persisted payload saves unified input state

### Keep green
- Project-state persistence checks remain valid. Baseline: `novel_agent/tests/test_frontend_state_persistence.py:71`
- Blueprint repair/placeholder protection checks remain valid. Baseline: `novel_agent/tests/test_frontend_state_persistence.py:109`

## Frontend DOM Tests

Target file: `frontend-tests/settings-short-story.dom.test.js`

### Add
1. single unified input textarea renders with new guidance copy
2. analyze/fusion sections render before synopsis section
3. three fusion cards render and one can be selected
4. selecting a fusion option enables synopsis generation
5. legacy localStorage payload with `draftKeywords` hydrates into unified input box

## Manual / Exploratory Matrix

| Input type | Example | Expected |
|---|---|---|
| 纯词条 | `旧相机、失约、雨夜` | 自动识别为词条素材，生成 3 个不同故事路数 |
| 纯灵感 | `想写一个雨夜重逢却带悬疑反转的短篇` | 自动识别为灵感/题材，生成 3 个方案 |
| 纯例文 | 粘贴一段参考例文 | 直接拆解节奏/结构并生成 3 个方案 |
| 混合输入 | 例文 + 灵感 + 题材 + 词条 | 识别为混合素材并输出 3 案 |

## Verification Commands
- `pytest novel_agent/tests/test_short_story_service.py`
- `pytest novel_agent/tests/test_short_story_routes.py`
- `pytest novel_agent/tests/test_frontend_state_persistence.py`
- `npm.cmd run test:frontend -- settings-short-story.dom.test.js`

## Exit Criteria
1. 新旧相关测试通过
2. 单输入框可覆盖纯词条、灵感、例文、混合输入四类场景
3. 每类场景都能产出 3 个不同故事路数
4. 人工验证“强借鉴但内容换新”边界未被破坏
