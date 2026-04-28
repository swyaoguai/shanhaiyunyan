# Deep Interview Transcript Summary

- Timestamp: 2026-04-17T00:03:00Z
- Profile: standard
- Context type: brownfield
- Final ambiguity: 0.18
- Threshold: 0.20
- Context snapshot: `.omx/context/library-auto-save-gating-20260416T234654Z.md`

## Summary
The user wants a chat-UI switch that controls whether newly generated content should automatically create/save files. When enabled, built-in library categories and chapter/body outputs should auto-save. For non-builtin/custom categories, the system must not auto-save and must require manual category selection first. When disabled, existing built-in auto-persist behaviors may remain, but no newly introduced auto-save behavior should occur unless explicitly saved/confirmed.

## Round Log
1. Decision boundary: user proposed a chat UI switch instead of pure LLM-based save authority.
2. Scope: chose a global switch, but required checking library categories beyond the listed examples.
3. Decision boundary: custom/non-builtin categories must never auto-save; manual selection required.
4. Non-goal probe: user rejected “switch off means no automatic writes at all”.
5. Non-goal refinement: user chose to preserve current built-in auto-persist behavior while preventing new auto-save behavior when switch is off.

## Brownfield Evidence
- Explicit character save trigger lives in `novel_agent/web/routes/chat.py:701`.
- Character `save` vs `draft` mode is set in `novel_agent/web/routes/chat.py:838`.
- Character drafts do not persist when `request_mode != save`: `novel_agent/agents/router_agent.py:2647`.
- Character persistence occurs when `request_mode == save`: `novel_agent/agents/router_agent.py:2619`, `novel_agent/agents/router_agent.py:2679`.
- Worldbuilding, outline, eventlines, detail settings, chapter settings, and chapter files already auto-persist in router pipelines: `novel_agent/agents/router_agent.py:2851`, `:2889`, `:3002`, `:2171`.
- Built-in project-data types are fixed in backend: `novel_agent/web/routes/projects.py:31`, `novel_agent/project_manager.py:221`.
- Frontend custom knowledge categories are stored separately from built-in backend project-data, while aux-memory categories use another backend API: `novel_agent/web/static/app-knowledge.js:47`, `:240`; `novel_agent/web/routes/aux_memory.py:42`.
