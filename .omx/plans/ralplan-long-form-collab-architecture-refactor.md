# RALPLAN-DR: Long-Form Multi-Agent Collaboration Architecture Refactor

## Metadata
- Created: 2026-04-25
- Mode: short
- Scope: `novel_agent/workflow/` long-form multi-agent collaboration only
- Out of scope: Router / Communicator / ContinuousWriter / short-story / script modes
- Grounding sources:
  - `多Agent架构改造方案.md:5-29`
  - `.omx/context/multi-agent-architecture-refactor-implementation-20260425T153529Z.md:7-40`
  - `novel_agent/workflow/coordinator.py:168-226`
  - `novel_agent/workflow/coordinator.py:1541-1553`
  - `novel_agent/workflow/coordinator.py:1576-1589`
  - `novel_agent/workflow/coordinator.py:1679-1707`
  - `novel_agent/workflow/coordinator.py:2119-2263`
  - `novel_agent/workflow/coordinator.py:2199-2208`
  - `novel_agent/workflow/coordinator.py:2396-2477`
  - `novel_agent/workflow/coordinator.py:2705-2985`
  - `novel_agent/workflow/contracts.py:238-390`
  - `novel_agent/workflow/task_pool.py:108-317`
  - `novel_agent/workflow/__init__.py:16-46`
  - `novel_agent/agents/capability_registry.py:11-149`
  - `novel_agent/agents/collab_sub_agents.py:21-27`
  - `novel_agent/agents/collab_sub_agents.py:289-598`
  - `novel_agent/agents/base_agent.py:100-151`
  - `novel_agent/tests/test_supervised_collab_foundation.py:274`
  - `novel_agent/tests/test_supervised_collab_foundation.py:342-394`
  - `novel_agent/tests/test_supervised_collab_foundation.py:397-430`
  - `novel_agent/tests/test_supervised_collab_foundation.py:489-760`
  - `novel_agent/tests/test_supervised_collab_foundation.py:798-850`
  - `novel_agent/tests/test_supervised_collab_foundation.py:853-904`
  - `novel_agent/tests/test_supervised_collab_foundation.py:1223-1310`
  - `novel_agent/tests/test_workflow.py:376-494`

---

## Brownfield Summary

1. `NovelCoordinator` currently instantiates and registers six task agents plus five helper-style nodes directly in one place, coupling orchestration, lifecycle, and capability registration (`novel_agent/workflow/coordinator.py:168-226`).
2. The exact current `_run_autonomous_task()` call sites are `_execute_project_ready_build_world()` (`novel_agent/workflow/coordinator.py:1541-1553`), `_execute_project_ready_build_outline()` (`novel_agent/workflow/coordinator.py:1576-1589`), `_execute_project_ready_summary_orchestrate()` (`novel_agent/workflow/coordinator.py:1679-1707`), and the `_execute_chapter_task_market()` dispatch path (`novel_agent/workflow/coordinator.py:2199-2208`).
3. `create_novel()` still calls `worldbuilder.execute()`, `character_builder.execute()`, and `outliner.execute()` directly, so Phase 1 must explicitly exclude that direct path (`novel_agent/workflow/coordinator.py:2396-2477`).
4. `_run_autonomous_task()` already concentrates candidate lookup, selection, fallback, task-pool updates, persistence, and progress events, making it the lowest-risk extraction seam for a first Dispatcher slice (`novel_agent/workflow/coordinator.py:2705-2985`).
5. `_execute_chapter_task_market()` mutates a free-form `working_context` and writes `loaded_context` back via `working_context.update(...)`, which is exactly the unstable source-of-truth/merge pattern the proposal wants to remove (`novel_agent/workflow/coordinator.py:2119-2263`).
6. `AgentCapabilityRegistry` is a global capability-and-instance container with priority sorting, but no stage, required-context, fixed-agent provenance, or routing-reason semantics (`novel_agent/agents/capability_registry.py:11-149`).
7. Helper nodes in `collab_sub_agents.py` inherit `_SimpleAgent -> BaseAgent`, so they currently pay full `BaseAgent` client initialization cost despite behaving like local services (`novel_agent/agents/collab_sub_agents.py:21-27`, `novel_agent/agents/base_agent.py:100-151`).
8. Existing tests already guard task-pool transitions, autonomous fallback, chapter task-market loops, summary orchestration, project-ready execution, and permanent-memory persistence; these should be used as migration rails rather than replaced (`novel_agent/tests/test_supervised_collab_foundation.py:342-394`, `:397-430`, `:489-760`, `:798-850`, `:853-904`, `:1223-1310`, `novel_agent/tests/test_workflow.py:376-494`).

---

## RALPLAN-DR Summary

### Principles
1. **Route explicitly, not implicitly**: capability discovery may inform routing, but final assignment must come from explicit task/stage/context rules.
2. **Context is a contract, not a mutable bag**: dispatchable work must validate required context before execution and merge results through named rules.
3. **Separate dispatchable agents from local services**: helper services should not occupy the same routing space as true task agents.
4. **Migrate from the existing stable seam outward**: Phase 1 touches only the current `_run_autonomous_task()` call sites and excludes `create_novel()` direct world/character/outline execution.
5. **Metadata-first compatibility before schema change**: Phase 1 may add metadata fields, but must not require task-pool top-level schema changes.

### Top 3 Decision Drivers
1. **Correctness of agent assignment**: the proposal prioritizes avoiding wrong-agent dispatch over cosmetic file splitting (`多Agent架构改造方案.md:32-36`, `:625-635`).
2. **Context continuity and debuggability**: current `working_context.update(...)` flow is the main source of dropped or opaque state (`多Agent架构改造方案.md:297-390`, `novel_agent/workflow/coordinator.py:2230-2233`).
3. **Low-risk incremental migration**: public coordinator entrypoints must stay compatible, and current tests already cover the most important collaboration paths (`多Agent架构改造方案.md:717-724`, `.omx/context/multi-agent-architecture-refactor-implementation-20260425T153529Z.md:21-24`).

### Viable Options

#### Option A — Incremental dispatcher-first migration from the chapter collaboration seam **(Recommended)**
- Shape:
  - Add `routing_policy.py`, `execution_context.py`, and `agent_dispatcher.py`.
  - Integrate them first only under the exact current `_run_autonomous_task()` call sites.
  - Keep `create_novel()` world/character/outline direct calls unchanged and explicitly out of Phase 1.
- Pros:
  - Uses the most test-covered seam first.
  - Fixes the two highest-priority problems early: wrong routing and lost context.
  - Preserves public flow compatibility while introducing new abstractions behind existing coordinator APIs.
- Cons:
  - Coordinator remains partially hybrid for one migration phase.
  - Temporary adapters will exist between dict-based context and structured context.

#### Option B — Full big-bang dispatcher rewrite across all long-form flows
- Shape:
  - Introduce the full target module set and switch `create_novel()`, chapter task market, project-ready tasks, checkpoint/memory logic, and helper boundaries in one pass.
- Pros:
  - Reaches target architecture fastest on paper.
  - Minimizes temporary dual-path code.
- Cons:
  - Highest regression risk because it touches both direct main-flow execution and autonomous collaboration simultaneously.
  - Harder to localize failures when routing, context, persistence, and helper boundaries all move together.

#### Option C — Registry/service split first, routing/context second
- Shape:
  - First demote helper agents into services and create collab-specific registries; delay dispatcher/context-contract introduction.
- Pros:
  - Simplifies runtime topology early.
  - Removes helper pollution from the candidate pool.
- Cons:
  - Does not directly solve the current wrong-routing or context-loss problems first.
  - Risks spending an iteration on structural cleanup while the most user-visible failure modes remain.

### Recommendation
Choose **Option A**. It aligns with the proposal’s stated priorities, leverages current test coverage, and creates a reversible migration ladder. The safest first slice is:

> **Phase 1: add `RoutingPolicy` + `CollabExecutionContext` + a minimal `AgentDispatcher`, then route only these current `_run_autonomous_task()` call sites through them: `_execute_project_ready_build_world()` (`1541-1553`), `_execute_project_ready_build_outline()` (`1576-1589`), `_execute_project_ready_summary_orchestrate()` (`1679-1707`), and `_execute_chapter_task_market()` dispatch (`2199-2208`). `create_novel()` direct world/character/outline calls (`2396-2477`) are explicitly excluded from Phase 1.**

That slice is safest because the existing autonomous task path is already centralized (`novel_agent/workflow/coordinator.py:2705-2985`) and heavily covered by tests across those exact seams (`novel_agent/tests/test_supervised_collab_foundation.py:342-394`, `:397-430`, `:489-760`, `:798-850`, `:853-904`, `:1223-1310`, `novel_agent/tests/test_workflow.py:376-494`).

---

## Recommended Implementation Phases

### Phase 1 — Executor-safe safety slice: exact current `_run_autonomous_task()` call sites only
**Goal:** Fix assignment and context correctness only on the already-centralized autonomous seam, without broadening into `create_novel()` direct execution.

**Primary touchpoints**
- New: `novel_agent/workflow/routing_policy.py`
- New: `novel_agent/workflow/execution_context.py`
- New: `novel_agent/workflow/agent_dispatcher.py`
- Modify: `novel_agent/workflow/coordinator.py`
- Modify: `novel_agent/workflow/contracts.py`
- Modify: `novel_agent/workflow/task_pool.py`
- Modify: `novel_agent/workflow/__init__.py`
- Modify/add tests:
  - `novel_agent/tests/test_supervised_collab_foundation.py`
  - `novel_agent/tests/test_workflow.py`

**Implementation intent**
- Scope only these call sites:
  - `_execute_project_ready_build_world()` (`coordinator.py:1541-1553`)
  - `_execute_project_ready_build_outline()` (`coordinator.py:1576-1589`)
  - `_execute_project_ready_summary_orchestrate()` (`coordinator.py:1679-1707`)
  - `_execute_chapter_task_market()` dispatch invocation (`coordinator.py:2199-2208`)
- Explicitly exclude `create_novel()` direct `worldbuilder.execute()`, `character_builder.execute()`, and `outliner.execute()` calls (`coordinator.py:2396-2477`).
- Define explicit route rules only for Phase 1 in-scope tasks: `build_world`, `build_outline`, `summary_orchestrate`, `context_plan`, `content_read`, `write_chapter`, `evaluate_chapter`, `polish_chapter`, `expand_content`.
- Add `CollabExecutionContext` + `TaskExecutionEnvelope` with validation and controlled merge helpers.
- Add a fixed-agent routing rule: when a route rule resolves to a fixed in-scope agent and capability discovery returns no candidates, dispatcher may still dispatch to that fixed agent, but must record provenance.
- Require metadata keys in Phase 1 outputs/persistence: `route_reason`, `candidate_source`, `fallback_provenance`.
- Metadata semantics:
  - `route_reason`: human-readable reason for route choice or fail-fast outcome
  - `candidate_source`: `capability_registry` or `fixed_route_rule`
  - `fallback_provenance`: empty for non-fallback success, otherwise identify source agent and fallback trigger
- Wrap the existing `_run_autonomous_task()` path so coordinator delegates route resolution, dispatch, event payload creation, and fallback handling to `AgentDispatcher`.
- Maintain metadata-first compatibility: Phase 1 may append metadata inside existing task/task-pool records, but must not require any top-level task-pool snapshot schema changes.

**Single-writer ownership rules**
- **Context delta merge:** single writer = `ExecutionContext` merge helpers invoked by dispatcher; coordinator may consume merged results but must not perform parallel ad hoc writes for the same delta path.
- **Permanent-memory persistence:** single writer = dispatcher-owned persistence handoff for `content_read` results; coordinator must not duplicate persistence after dispatcher takes ownership of that write path.
- **Execution trace / context snapshot recording:** single writer = dispatcher/runtime-state path; coordinator may read identifiers but must not emit competing trace/snapshot records for the same dispatch.

**Exit criteria**
- `_run_autonomous_task()` no longer directly chooses agents from capability candidates.
- In-scope Phase 1 call sites dispatch via the new dispatcher path; `create_novel()` direct calls remain unchanged.
- Fixed-agent dispatch works when capability candidates are empty and provenance metadata is recorded.
- `_execute_chapter_task_market()` no longer performs unconstrained `working_context.update(...)` on dispatch-return payloads for Phase 1-dispatched work.
- Task-pool snapshots remain top-level schema-compatible.
- Tests cover missing required context fail-fast, fixed-agent route with empty capability candidates, metadata-first persistence, and routing-reason propagation.

### Phase 2 — Registry boundary cleanup: collab agents vs local services
**Goal:** Remove helper/service nodes from the same dispatch space as true task agents.

**Primary touchpoints**
- New: `novel_agent/workflow/collab_registry.py`
- New: `novel_agent/workflow/collab_services.py`
- Modify: `novel_agent/workflow/coordinator.py`
- Modify: `novel_agent/workflow/__init__.py`
- Modify: `novel_agent/agents/capability_registry.py`
- Modify: `novel_agent/agents/collab_sub_agents.py`
- Modify tests:
  - `novel_agent/tests/test_supervised_collab_foundation.py`
  - `novel_agent/tests/test_workflow.py`

**Implementation intent**
- Create a scoped collab registry for actual dispatchable agents only.
- Move `ContextStrategy`, `ContentReader`, `ContentExpansion`, `FileNaming`, and `SummaryOrchestrator` into service-style wrappers for the long-form collaboration mode, while preserving transitional compatibility for any existing imports.
- Reduce `AgentCapabilityRegistry` to candidate discovery / declaration support rather than final routing ownership.
- Update coordinator assembly and knowledge-base propagation to operate via collab registry/service registry rather than a hard-coded list.

**Exit criteria**
- Helper-style nodes no longer require `BaseAgent` lifecycle when used only as local services in the long-form collaboration runtime.
- Coordinator no longer registers all helper nodes into the global candidate pool by default.

### Phase 3 — Runtime state extraction and persistence seams
**Goal:** Pull dispatch trace, snapshots, checkpoint/memory sync seams out of coordinator without broad behavioral change.

**Primary touchpoints**
- New: `novel_agent/workflow/runtime_state.py`
- New: `novel_agent/workflow/checkpoint_manager.py`
- New: `novel_agent/workflow/memory_sync.py`
- Modify: `novel_agent/workflow/coordinator.py`
- Modify: `novel_agent/workflow/task_pool.py`
- Modify: `novel_agent/workflow/__init__.py`
- Modify tests:
  - `novel_agent/tests/test_supervised_collab_foundation.py`
  - `novel_agent/tests/test_workflow.py`

**Implementation intent**
- Start with thin facades over current coordinator behavior for checkpoint/memory logic; deeper internal simplification can happen later.
- Move execution-trace recording and context snapshot indexing into `RuntimeStateStore`.
- Keep project-state persistence keys stable unless there is a compelling migration reason.

**Exit criteria**
- Coordinator no longer owns direct snapshot bookkeeping or trace-shape decisions for dispatched tasks.
- Existing persisted runtime/task-pool consumers continue to read expected keys.

### Phase 4 — Coordinator convergence for long-form collaboration entrypoints
**Goal:** Convert the remaining long-form collaboration entrypoints to use the new runtime while preserving public signatures.

**Primary touchpoints**
- Modify: `novel_agent/workflow/coordinator.py`
- Modify: `novel_agent/workflow/contracts.py`
- Modify: `novel_agent/workflow/__init__.py`
- Modify tests:
  - `novel_agent/tests/test_supervised_collab_foundation.py`
  - `novel_agent/tests/test_workflow.py`

**Implementation intent**
- Migrate the long-form `create_novel()` project-building path into dispatcher/context-factory usage only after Phases 1-3 are stable.
- Preserve signatures for `create_novel`, `execute_project_ready_tasks`, `set_knowledge_base`, pause/resume/cancel, and project switching.
- Remove or deprecate coordinator-owned route/selection logic that is now duplicated by dispatcher or routing policy.

**Exit criteria**
- All in-scope long-form collaboration flows use the same dispatch/context contract.
- Coordinator is primarily orchestration and lifecycle wiring, not route selection or ad hoc context assembly.

---

## Acceptance Criteria

1. **Routing is explicit and inspectable**
   - Every in-scope long-form collaborative task resolves through a route rule with agent choice reason and fallback data.
   - Capability registry is no longer the final decision-maker for in-scope long-form task assignment.
   - If capability discovery returns empty for a fixed-agent Phase 1 rule, dispatcher may still dispatch to that fixed agent and persists `candidate_source=fixed_route_rule`.

2. **Context validation happens before execution**
   - Dispatchable tasks fail fast when required context keys are missing.
   - Context merge behavior is explicit by field class: structured overwrite, single-value overwrite, or namespaced merge.
   - Context delta merge has one owner in the dispatcher/context layer.

3. **Agent/service boundaries are clear**
   - Helper services are no longer mixed into the dispatch candidate space for long-form collaboration.
   - Knowledge-base and lifecycle propagation still reach all required runtime participants.

4. **Coordinator scope shrinks without API breakage**
   - Public coordinator entrypoints remain signature-compatible.
   - Coordinator no longer contains independent agent-selection logic for long-form collaborative execution.

5. **Observability improves**
   - Runtime/task metadata can show `selected_agent`, `route_reason`, `candidate_source`, `fallback_provenance`, `fallback_used`, and `context_snapshot_id` for in-scope dispatched tasks.

6. **Metadata-first compatibility gate**
   - Phase 1 forbids required top-level schema changes for task-pool snapshots.
   - Any new Phase 1 compatibility data is additive metadata only.

---

## Verification Strategy

### Targeted test layers
1. **Routing unit tests**
   - Route matching by `task_type + stage`
   - Missing-context fail-fast
   - Fixed-agent route with empty capability candidates
   - Fallback ordering / invalid rule handling

2. **Execution-context unit tests**
   - Validation of required keys
   - Merge semantics for structured fields vs namespaced memory fields
   - Snapshot/export conversion to agent-facing dict context
   - Single-writer merge ownership behavior for context deltas

3. **Dispatcher integration tests**
   - Success path records route metadata and runtime trace
   - Failure path records error and fallback
   - No-candidate / invalid-context path stops before agent execution unless a fixed-agent route rule explicitly allows dispatch
   - Metadata-first persistence path records `route_reason`, `candidate_source`, and `fallback_provenance` without changing task-pool top-level schema

4. **Regression tests on existing seams**
   - Preserve and extend:
     - `novel_agent/tests/test_supervised_collab_foundation.py:342-394`
     - `novel_agent/tests/test_supervised_collab_foundation.py:397-430`
     - `novel_agent/tests/test_supervised_collab_foundation.py:489-760`
     - `novel_agent/tests/test_supervised_collab_foundation.py:798-850`
     - `novel_agent/tests/test_supervised_collab_foundation.py:853-904`
     - `novel_agent/tests/test_supervised_collab_foundation.py:1223-1310`
     - `novel_agent/tests/test_workflow.py:376-494`

### New Phase 1 tests required
- Missing required context fail-fast before agent execution
- Fixed-agent route succeeds with empty capability candidates and records `candidate_source=fixed_route_rule`
- Metadata-first persistence asserts `route_reason`, `candidate_source`, and `fallback_provenance` are stored compatibly in existing task metadata / runtime records
- Task-pool top-level snapshot shape remains unchanged

### Verification checkpoints by phase
- **After Phase 1:** only the four in-scope `_run_autonomous_task()` call sites are migrated; autonomous-task/project-ready/chapter-task-market regressions green; new fail-fast, fixed-route, and metadata-first tests green; task-pool top-level snapshot shape unchanged; `create_novel()` direct world/character/outline path untouched.
- **After Phase 2:** no helper/service is selected via collab routing unless explicitly intended; compatibility imports still work.
- **After Phase 3:** persisted trace/task-pool/state readers still function against project-state snapshots.
- **After Phase 4:** full long-form creation flow uses unified dispatch/context path without changing external API shape.

---

## Risks and Mitigations

1. **Risk: hybrid migration creates duplicate routing logic**
   - Mitigation: Phase 1 must declare dispatcher/routing policy as the single source of assignment truth for the autonomous chapter-collab path, even if `create_novel()` remains temporarily direct.

2. **Risk: serialization breakage in task-pool or project-state snapshots**
   - Mitigation: add metadata fields compatibly; Phase 1 explicitly forbids required top-level task-pool snapshot schema changes.

3. **Risk: helper demotion breaks code paths that import helper agents directly**
   - Mitigation: keep compatibility shims or deprecation wrappers in `collab_sub_agents.py` until the new service layer is proven.

4. **Risk: context contract is too broad on first pass**
   - Mitigation: start with the fields already used by `_execute_chapter_task_market()` and `ContentReaderAgent`, then expand only when another in-scope path requires it.

5. **Risk: touching `create_novel()` too early broadens blast radius**
   - Mitigation: defer main-flow convergence until after Phase 1-3 evidence is green; this is why Option A is recommended over a big-bang rewrite.

6. **Risk: ambiguous ownership causes duplicate writes**
   - Mitigation: enforce single-writer ownership in Phase 1 for context delta merge, permanent-memory persistence, and execution trace/context snapshot recording.

---

## ADR

### Decision
Adopt an **incremental dispatcher-first refactor** for the long-form collaboration runtime: introduce explicit routing policy, execution-context contract, and a dispatcher only beneath the exact current `_run_autonomous_task()` call sites first; preserve metadata-first compatibility; then split registries/services, extract runtime state, and only later converge remaining coordinator entrypoints.

### Drivers
1. Correct agent assignment must become deterministic and inspectable.
2. Context propagation must stop depending on unconstrained dict mutation.
3. Migration must preserve current public APIs, existing task-pool schema shape, and exploit existing regression coverage.

### Alternatives Considered
1. **Big-bang full rewrite**
   - Rejected because it combines routing, context, persistence, and lifecycle changes in one high-blast-radius step.
2. **Registry/service cleanup first**
   - Rejected as the lead move because it improves structure before addressing the two primary failure modes: wrong routing and dropped context.

### Why Chosen
- It lands the proposal’s highest-value guarantees earliest.
- It uses the clearest current extraction seam in brownfield code without widening into `create_novel()` direct execution.
- It keeps changes reversible and testable by phase.

### Consequences
- Coordinator will remain temporarily hybrid during the migration.
- Transitional adapters and deprecation wrappers will exist for one or more phases.
- Test scope will expand before line count shrinks materially.
- Phase 1 implementation is constrained by ownership and metadata-compatibility gates, reducing executor freedom but lowering regression risk.

### Follow-ups
1. After Phase 1, reassess whether any remaining `_run_autonomous_task()`-adjacent long-form tasks need route rules before widening scope.
2. Before Phase 2, confirm the Phase 1 ownership split is stable enough to move helper/service responsibilities.
3. After Phase 2, decide whether helper compatibility shims can be retired or need one more release window.
4. After Phase 3, decide whether checkpoint/memory facades can be deepened into cleaner internal APIs without changing persisted state shape.

---

## Later Execution Handoff Guidance

### Phase 1 executor checklist
- Touch only the exact Phase 1 call sites plus supporting dispatcher/context/routing files.
- Do not migrate `create_novel()` direct world/character/outline execution.
- Preserve task-pool top-level snapshot schema.
- Ensure `route_reason`, `candidate_source`, and `fallback_provenance` persist compatibly.
- Enforce single-writer ownership for context delta merge, permanent-memory persistence, and execution trace/context snapshot recording.

### Available-agent-types roster
- `architect` — architecture review / boundary integrity
- `critic` — plan challenge / tradeoff scrutiny
- `executor` — implementation lane
- `verifier` — completion evidence / acceptance validation
- `test-engineer` — regression and test design
- `code-reviewer` — post-implementation review
- `debugger` / `build-fixer` — failure isolation if tests or type checks regress
- `researcher` — only if unexpected external doc lookup is needed
- `writer` — migration notes / deprecation notes if needed
- `team-executor` — conservative orchestration lane for multi-worker delivery

### Recommended reasoning levels by lane
- Architecture / decision integrity: **high to xhigh**
- Core implementation / refactor lane: **high**
- Test design / verification: **medium to high**
- Code review / verification summary: **high**
- Build/debug rescue lane: **high**

### Staffing guidance for `ralph`
Use `ralph` when the team wants one controlled sequential lane with explicit verification gates.

**Suggested lane order**
1. `architect` — validate Phase 1 slice boundaries and invariants.
2. `executor` — implement Phase 1 only.
3. `test-engineer` — extend/adjust tests for routing/context/dispatcher.
4. `verifier` — check acceptance criteria and confirm no out-of-scope files were changed.
5. `code-reviewer` — final review before moving to Phase 2.

**Ralph emphasis**
- Start with **Phase 1 only**.
- Do not authorize Phase 2 until Phase 1 verification is green, route/context metadata is visible in runtime outputs, and metadata-first compatibility is confirmed.

**Launch hint**
- `$ralph "Implement Phase 1 from .omx/plans/ralplan-long-form-collab-architecture-refactor.md only. Respect proposal scope boundaries. Stop after verification."`

### Staffing guidance for `team`
Use `team` when Phase 1 work is approved and splitable into disjoint write scopes.

**Recommended initial staffing**
1. **Lane A — Routing + context contract**
   - Roles: `architect` (brief design check), `executor`
   - Files: `workflow/routing_policy.py`, `workflow/execution_context.py`, `workflow/contracts.py`
2. **Lane B — Dispatcher integration**
   - Roles: `executor`, `debugger` on standby
   - Files: `workflow/agent_dispatcher.py`, `workflow/coordinator.py`, `workflow/task_pool.py`
3. **Lane C — Regression coverage**
   - Roles: `test-engineer`, `verifier`
   - Files: `tests/test_supervised_collab_foundation.py`, `tests/test_workflow.py`

**Single-writer lane ownership**
- Lane A owns context delta merge semantics.
- Lane B owns permanent-memory persistence handoff and execution trace/context snapshot recording.
- Lane C verifies no competing write paths remain for those three ownership domains.

**Team verification path**
1. Lane C validates routing/context/dispatcher behavior against Phase 1 acceptance criteria.
2. `verifier` confirms no out-of-scope modules (`router_agent.py`, `communicator.py`, `continuous_writer.py`, short-story/script paths) were touched.
3. `code-reviewer` checks coordinator still preserves public signatures and that fallback/trace metadata remain compatible.

**Launch hint**
- `$team "Execute Phase 1 from .omx/plans/ralplan-long-form-collab-architecture-refactor.md with lanes: A routing/context, B dispatcher/coordinator integration, C regression tests + verification. Keep scope to long-form collaboration only."`
- `omx team "Execute Phase 1 from .omx/plans/ralplan-long-form-collab-architecture-refactor.md with the approved lane split and verification path."`
