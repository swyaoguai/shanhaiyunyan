# Deep Interview Spec: multi-agent-library-unification

## Metadata
- Profile: standard
- Final ambiguity: 0.12
- Threshold: 0.20
- Context type: brownfield
- Context snapshot: `.omx/context/library-auto-save-gating-20260416T234654Z.md`
- Transcript: `.omx/interviews/multi-agent-library-unification-20260417T013000Z.md`

## Clarity Breakdown
| Dimension | Score |
|---|---:|
| Intent Clarity | 0.97 |
| Outcome Clarity | 0.93 |
| Scope Clarity | 0.92 |
| Constraint Clarity | 0.82 |
| Success Criteria Clarity | 0.86 |
| Context Clarity | 0.96 |

## Intent
Unify all referenceable multi-agent creation assets into a single library-backed knowledge model so downstream agents always read from one coherent source of truth, while preserving the current frontend module layout.

## Desired Outcome
- One unified library-backed model for all multi-agent referenceable assets.
- A single true outline model inside that library system.
- Detail outline, chapter settings, character cards, and user-defined categories also participate in the same library-backed model.
- Chapter正文 remains file-first, but its summary/index/metadata becomes referenceable from the library.
- Existing frontend modules (write/world/library etc.) can stay, but should use the unified underlying data model.

## In-Scope
- Outline / detail outline / chapter settings / character cards / user-defined categories unification
- Library-backed single source of truth for multi-agent referenceable content
- Chapter body summary/index representation in the library
- UI read/write alignment while preserving current module entry points
- Auto-save / save-policy compatibility with the unified library model

## Out-of-Scope / Non-goals
- Do not force chapter full text into the library as the primary storage model
- Do not collapse the UI into a single “library-only” page
- Do not keep two conceptual outline sources long-term

## Decision Boundaries
### OMX may decide without further confirmation
- Technical migration strategy from current `outline` / `detail_settings` / `chapter_settings` / `characters` split into a unified library-backed domain model
- Exact adapter/helper names and backend service boundaries
- Whether the unified model is implemented as canonical storage + compatibility views, as long as the user-facing source of truth becomes singular

### OMX must NOT decide without confirmation
- Must not store chapter full text primarily inside the library instead of files
- Must not preserve the current conceptual split where `outline_settings` and real outline coexist as two different “outline” concepts
- Must not remove the current module-based UX entry points

## Constraints
- Current backend built-in project data types are split across `outline`, `worldbuilding`, `characters`, `items`, `eventlines`, `outline_settings`, `detail_settings`, `chapter_settings`
- Current frontend library category UX treats these as separate category tabs
- Custom knowledge categories and aux-memory categories are not currently unified with the same backend project-data model

## Testable Acceptance Criteria
1. There is only one true outline concept in the system, and it is part of the unified library-backed model.
2. Multi-agent referenced assets (at minimum outline, detail outline, chapter settings, character cards, user custom categories) are read through the same unified knowledge model.
3. Chapter full text remains file-first.
4. Chapter summaries/indexes/metadata become referenceable from the unified library model.
5. Existing frontend modules remain available, but their data comes from the unified model rather than split conceptual sources.
6. Auto-save and downstream agent lookup behave consistently across these asset types.

## Assumptions Exposed + Resolutions
- Assumption: only the outline naming is wrong.  
  Resolution: no, the user wants broader unification across all referenceable multi-agent assets.
- Assumption: the user wants the library page to replace all other modules.  
  Resolution: no, the user chose to preserve current modules while unifying underlying data.
- Assumption: chapter full text should also move into the library.  
  Resolution: no, chapter正文 stays file-first; only its referenceable summary/index enters the library.

## Pressure-pass Findings
- The broader system intent is not merely “rename outline settings”; it is to remove conceptual duplication across all multi-agent referenceable assets.
- The user explicitly rejected a UI collapse and explicitly preserved a file-first model for full chapter content.

## Brownfield Evidence vs Inference
### Evidence
- `outline.json` is currently the real outline source.
- `outline_settings` currently exists as a separate library-style category with nonstandard outline fields.
- `detail_settings` and `chapter_settings` are already modeled as library-like structured lists.
- Project data and library categories are currently split in both backend and frontend.

### Inference
- A canonical library-backed domain layer with compatibility views/adapters is likely the cleanest migration path.

## Technical Context Findings
- Real outline path: `outline.json`
- UI loads project data separately from library category configuration
- Current category labels likely blur “real outline” vs “outline settings” in user mental model

## Execution Bridge
### Recommended: `$ralplan`
Input: `.omx/specs/deep-interview-multi-agent-library-unification.md`

### Alternatives
- `$autopilot .omx/specs/deep-interview-multi-agent-library-unification.md`
- `$ralph .omx/specs/deep-interview-multi-agent-library-unification.md`
- `$team .omx/specs/deep-interview-multi-agent-library-unification.md`
- Refine further if you want schema-level examples before planning
