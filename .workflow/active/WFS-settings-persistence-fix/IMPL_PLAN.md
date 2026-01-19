---
identifier: WFS-settings-persistence-fix
source: "User requirements: Fix settings persistence bug where AGENT API configuration reverts to defaults after page refresh"
workflow_type: "tdd"
tdd_workflow: true
feature_count: 5
---

# Implementation Plan: Settings Persistence Fix - TDD Workflow

## 1. Summary

**Core Problem**: Settings persistence bug where AGENT API configuration reverts to defaults after page refresh. Root cause: `load_dotenv()` called once at module import, `os.getenv()` values cached at class definition.

**Core Objectives**:
- Add hot-reload capability via `Config.reload()` method
- Add error handling to all file write operations
- Fix runtime config update order
- Standardize error response format
- Add manual config reload endpoint

## 2. Task Breakdown

| Task | Title | Priority | Dependencies | Test Cases |
|------|-------|----------|--------------|------------|
| IMPL-1 | Add Config.reload() method | Critical | - | 5 tests |
| IMPL-2 | Add error handling to file writes | High | IMPL-1 | 8 tests |
| IMPL-3 | Standardize error response format | Medium | IMPL-2 | 6 tests |
| IMPL-4 | Fix runtime config update order | High | IMPL-1, IMPL-2 | 4 tests |
| IMPL-5 | Add config reload endpoint | High | IMPL-1, IMPL-4 | 5 tests |

**Total**: 28 test cases, Target Coverage: ≥85%

## 3. Execution Strategy

**Phase 1: Foundation (Day 1)**
- IMPL-1 (Config.reload() method)

**Phase 2: Core Fixes (Day 1-2, parallelizable)**
- IMPL-2 (Error handling)
- IMPL-3 (Error response format)
- IMPL-4 (Operation order)

**Phase 3: Integration (Day 2-3)**
- IMPL-5 (Reload endpoint)

## 4. Critical Files

- novel_agent/config.py (lines 85-100)
- novel_agent/web/app.py (lines 289-343, 325, ~345-380)
- novel_agent/agent_config.py (lines 279, 291)
