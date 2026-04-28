# RALPLAN: chat-auto-save-toggle

- Generated: 2026-04-17T00:03:00Z
- Source spec: `.omx/specs/deep-interview-library-auto-save-toggle.md`
- Context snapshot: `.omx/context/library-auto-save-gating-20260416T234654Z.md`
- Planning mode: consensus-style, short

## Requirements Summary
Add a chat-UI toggle that controls **newly introduced auto-save / auto-create-file behavior** for chat-generated outputs. When enabled, built-in library categories and supported file outputs should auto-save. When disabled, existing built-in auto-persist flows remain unchanged, but newly expanded auto-save behavior must not trigger. Non-builtin/custom categories must never auto-save and must require explicit user category selection.

## Brownfield Facts
- Built-in project-data categories are fixed in backend at `novel_agent/web/routes/projects.py:31` and resolved to concrete paths in `novel_agent/project_manager.py:221`.
- Character cards currently split draft vs save using request mode from `novel_agent/web/routes/chat.py:838` and persist only in save mode at `novel_agent/agents/router_agent.py:2619` / `novel_agent/agents/router_agent.py:2679`.
- Worldbuilding auto-persists in router worldbuild flow: `novel_agent/agents/router_agent.py:2851`.
- Outline auto-persists in outline flow: `novel_agent/agents/router_agent.py:2889`.
- Eventlines / detail settings / chapter settings auto-persist in project-data generation pipeline: `novel_agent/agents/router_agent.py:3002`.
- Chapter body files are written in `_persist_chapter_result`: `novel_agent/agents/router_agent.py:2171`.
- Frontend custom knowledge categories are not unified backend project-data types; they are loaded/saved separately in `novel_agent/web/static/app-knowledge.js:47` and `:240`.
- Project-scoped UI settings can be persisted through `/api/project-state/*`: `novel_agent/web/routes/projects.py:907`, `:954`, `:968`.

## RALPLAN-DR Summary
### Principles
1. **No surprising writes**: non-builtin destinations must never be auto-written.
2. **Preserve existing behavior**: do not break current built-in auto-persist flows when the toggle is off.
3. **Single source of truth**: built-in eligibility must come from backend-known categories, not ad hoc frontend strings.
4. **UI clarity over hidden heuristics**: file creation authority should be user-visible and project-scoped.
5. **Safe expansion**: new auto-save behavior must be allowlist-based and test-covered.

### Decision Drivers
1. Avoid silent writes into user-defined/custom categories.
2. Unify currently inconsistent chat generation persistence behavior.
3. Minimize regression risk to existing worldbuilding/outline/chapter flows.

### Viable Options
#### Option A — Project-scoped boolean toggle + backend allowlist (**Chosen**)
- Pros: simple mental model; low UI cost; preserves current behavior; easy to test.
- Cons: only one coarse toggle; future per-category preferences need extension.

#### Option B — Per-category auto-save matrix
- Pros: most flexible; could separately control characters/items/worldbuilding/etc.
- Cons: larger UI/config surface; harder migration story; more regression paths.

#### Option C — LLM decides whether to save on each generation
- Pros: fewer explicit controls in UI.
- Cons: violates user decision-boundary; too risky for custom categories; nondeterministic.

### Alternative Invalidation Rationale
- Option B is viable later, but is oversized for the current requirement and increases settings complexity before the global policy is stabilized.
- Option C is rejected because the user explicitly does **not** want save authority delegated to LLM inference for non-builtin destinations.

## ADR
### Decision
Implement a **project-scoped chat auto-save toggle** stored in project state, and enforce auto-save only for a backend-defined built-in allowlist plus supported chapter output flows. Require manual selection for any non-builtin/custom category.

### Drivers
- Explicit user control over file creation.
- Need to cover built-in categories beyond the currently named subset.
- Safety boundary for custom knowledge/aux-memory categories.

### Alternatives Considered
- Per-category matrix.
- LLM-driven save decisions.
- Keep current behavior unchanged.

### Why Chosen
This approach directly satisfies the clarified spec with the smallest safe change set. It adds visible control, preserves current built-in flows when toggle is off, and prevents accidental writes to custom destinations.

### Consequences
- Need a canonical backend allowlist helper for built-in auto-save eligibility.
- Character-card path must be reworked to consult the toggle.
- UI must clearly explain that custom categories still need manual selection.

### Follow-ups
- Consider future per-category controls only after this global toggle proves stable.
- Consider migrating frontend-only custom knowledge category metadata to a backend-backed model if automatic routing is ever desired.

## Implementation Steps
1. **Introduce project-scoped auto-save preference state**
   - Add a new project-state key for chat auto-save preference, loaded/saved via existing project-state endpoints in `novel_agent/web/routes/projects.py:907` and `:968`.
   - Surface helper access in the chat runtime path inside `novel_agent/web/routes/chat.py:1100` so router/chat execution gets the resolved toggle consistently.
   - Acceptance note: default semantics must be backward-compatible with current built-in auto-persist behavior.

2. **Add chat UI toggle and persistence wiring**
   - Add the toggle control to the Copilot/chat UI in `novel_agent/web/static/app-copilot.js` near existing command/input controls (`:820` region is the current prompt-bar assembly area; final placement can be adjacent to the input toolbar).
   - Read/write the toggle using `/api/project-state/{state_key}` and restore it when project/chat context initializes, following the pattern already supported by project state endpoints in `novel_agent/web/routes/projects.py:954` and `:968`.
   - Update any shared store fields if needed in `novel_agent/web/static/app-core.js:21` so the toggle state is globally accessible for rendering and optimistic UI.

3. **Create a backend allowlist for built-in auto-save targets**
   - Add a helper in `novel_agent/web/routes/projects.py` or a shared utility layer that derives built-in eligible categories from `BUILTIN_PROJECT_DATA_TYPES` (`novel_agent/web/routes/projects.py:31`) plus supported chapter/compiled-novel file outputs from router persistence flows.
   - Explicitly treat frontend custom knowledge categories (`novel_agent/web/static/app-knowledge.js:47`, `:240`) and aux-memory categories as non-builtin.
   - Ensure the helper is used by router/chat save decisions instead of string matching scattered through the UI.

4. **Gate newly-expanded auto-save behavior in router execution**
   - Keep existing built-in auto-persist flows unchanged when toggle is off:
     - worldbuilding `novel_agent/agents/router_agent.py:2851`
     - outline `novel_agent/agents/router_agent.py:2889`
     - project data generation `novel_agent/agents/router_agent.py:3002`
     - chapter file writes `novel_agent/agents/router_agent.py:2171`
   - Extend the character-card path so auto-save can happen **only when**:
     - toggle is on, and
     - destination is builtin, and
     - request does not target a custom category.
   - The current character draft/save split is in `novel_agent/web/routes/chat.py:838` and `novel_agent/agents/router_agent.py:2417` / `:2583`; that is the primary place to thread the new policy.

5. **Handle custom-category requests with explicit manual-selection fallback**
   - If the user asks to save to a non-builtin/custom category while auto-save toggle is on, return a structured response that pauses auto-save and asks the user to manually choose the category.
   - Reuse the existing confirmation-style response approach used elsewhere in router flows (`novel_agent/agents/router_agent.py:1890`) instead of silently dropping or guessing the target.
   - If necessary, persist a pending draft reference in collected/project state so the user can choose a category without regenerating content.

6. **Tighten frontend auto-save helpers to respect the same policy**
   - Audit `novel_agent/web/static/app-workflow-auto-save.js:7` onward, which currently auto-saves several file kinds, and ensure it consults the same built-in eligibility/toggle policy instead of independently writing everything it can parse.
   - Prevent it from ever attempting to push generated content into custom knowledge categories automatically.

7. **Add regression and policy tests**
   - Extend `novel_agent/tests/test_chat_routing_execution.py` with cases for:
     - toggle on + builtin target -> auto-save occurs for newly-enabled paths
     - toggle off + existing built-in auto-persist path -> existing behavior preserved
     - toggle off + character card -> remains draft-only unless explicit save
     - toggle on + custom category request -> no auto-save, manual-selection response returned
   - Add project-state persistence tests near `novel_agent/tests/test_project_state_routes.py` for the new state key.
   - Add frontend state-persistence assertions if UI restoration logic is introduced.

## Acceptance Criteria
1. A project-scoped chat toggle exists for auto-save/auto-create-file behavior and survives reloads/project switches.
2. The system derives built-in auto-save eligibility from backend-known built-in data types and supported chapter outputs, not from arbitrary frontend category labels.
3. When the toggle is **on**, newly enabled built-in targets (for example character cards if included) auto-save to the correct backend file path.
4. When the toggle is **off**, current built-in auto-persist flows already present in router execution still behave as they do today.
5. Non-builtin/custom category requests never auto-save, regardless of toggle state, and instead require explicit manual selection.
6. No path allows LLM-only inference to choose a custom category and write files automatically.
7. Existing worldbuilding, outline, eventlines, detail settings, chapter settings, and chapter file tests remain green.

## Risks and Mitigations
- **Risk:** Toggle semantics become confusing because some existing built-in flows still auto-save when off.  
  **Mitigation:** UI copy must explicitly say the toggle controls newly-added auto-save behavior and custom-category safety remains manual.
- **Risk:** Frontend `app-workflow-auto-save.js` and backend router logic diverge.  
  **Mitigation:** centralize built-in eligibility logic and add integration tests covering both chat response file records and persisted data.
- **Risk:** Custom categories have multiple storage models.  
  **Mitigation:** treat all non-builtin destinations as manual-only for this phase.

## Verification Steps
- Run targeted chat routing tests for save/draft behavior.
- Run project-state route tests for the new toggle state key.
- Manually verify in UI:
  1. toggle on + builtin generation
  2. toggle off + builtin existing flow
  3. custom-category save request -> manual selection required
- Validate no unexpected writes appear in project directories for custom-category requests.

## Available-Agent-Types Roster
- `analyst` — requirements/edge-case pass
- `architect` — data-flow and policy boundary review
- `designer` — chat UI/toggle interaction details
- `executor` / `worker` — implementation
- `test-engineer` — regression strategy and test additions
- `verifier` — claim validation after implementation
- `critic` / `security-reviewer` — policy/safety review for write boundaries
- `writer` — user-facing setting copy / release note wording

## Follow-up Staffing Guidance
### Ralph lane (sequential, lower coordination overhead)
- Lane 1: `executor` (reasoning: high) — implement backend gating + router wiring
- Lane 2: `designer` or `executor` (reasoning: medium) — add chat toggle UI + persistence glue
- Lane 3: `test-engineer` (reasoning: medium) — add/adjust tests
- Lane 4: `verifier` (reasoning: high) — validate file-creation policy and regressions

### Team lane (parallel)
- Worker A: backend policy + project-state plumbing (`chat.py`, `router_agent.py`, `projects.py`)
- Worker B: frontend chat toggle + store restore (`app-copilot.js`, `app-core.js`)
- Worker C: tests + workflow auto-save alignment (`test_chat_routing_execution.py`, `test_project_state_routes.py`, `app-workflow-auto-save.js`)
- Suggested reasoning: backend=high, frontend=medium, tests=medium, verification=high

## Launch Hints
### Ralph
- `$ralph .omx/plans/ralplan-chat-auto-save-toggle.md`

### Team
- `$team .omx/plans/ralplan-chat-auto-save-toggle.md`
- Team kickoff should assign disjoint ownership:
  - backend policy
  - frontend toggle
  - tests/verification

## Team Verification Path
Before shutdown, the team should prove:
1. toggle state persists per project
2. builtin allowlist is enforced centrally
3. custom-category requests do not auto-write
4. existing builtin auto-persist flows were not regressed

After team execution, Ralph/verifier should perform a final pass on:
- write-boundary correctness
- UI copy accuracy
- regression suite completeness

## Changelog
- Added explicit built-in vs custom-category boundary.
- Added preservation rule for existing built-in auto-persist flows when toggle is off.
- Added team/ralph staffing and verification guidance.
