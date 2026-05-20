# AGENTS.md

This file provides guidance to Codex (Codex.ai/code) when working with code in this repository.

## Common commands

### Setup and run
```bash
pip install -r requirements.txt
cp .env.example .env
python run.py
```

Notes:
- `run.py` is the real dev entrypoint. It loads `.env`, checks data-dir write permission, finds an available port starting from configured `PORT`/default `5656`, creates the FastAPI app, and starts Uvicorn.
- On startup the app may auto-switch to the next free port if `5656` is occupied.

### Backend tests
```bash
pytest
pytest novel_agent/tests
pytest novel_agent/knowledge_base/tests
```

Single test / filtered test:
```bash
pytest novel_agent/tests/test_short_story_service.py
pytest novel_agent/tests/test_short_story_service.py -k some_case_name
```

### Frontend tests
```bash
npm install
npm run test:frontend
npm run test:frontend:watch
```

Single frontend test file:
```bash
npx vitest run --pool threads --maxWorkers 1 frontend-tests/continuous-write.dom.test.js
```

### Release build
```bash
python build_release.py
```

Notes:
- The build scripts expect PyInstaller, and final installer EXE output requires Inno Setup (`ISCC.exe`).
- The release script builds exactly one Windows installer EXE file in `dist/`: the local-model version with `novel_agent/models/embedding/default` bundled. Do not publish the no-ONNX/lite installer.
- Release builds do not generate zip archives. `build_portable.py` is kept only for local portable-directory checks and also no longer creates zip files.
- The build scripts package `run.py`, bundle `novel_agent/web/static`, `novel_agent/web/templates`, `novel_agent/prompts`, Skills, and a clean release data copy.

### No lint command
- There is no dedicated root lint script in `package.json` or repo-level documented lint command. Do not invent one in changes or docs.

### Update log
- Record future version updates, bug fixes, UX changes, and test/build changes in `CHANGELOG.md`.
- Keep entries concise. The current product version line starts at `v1.0.0`; during future development, add pending items under `[未发布]` only when a release section has not been chosen yet.

## High-level architecture

### Runtime startup flow
- `run.py` is the outer runtime wrapper.
- `run.py` calls `novel_agent.web.create_app()` and runs Uvicorn.
- `novel_agent/web/app.py` is the FastAPI application factory and lifecycle glue.
- In app lifespan startup, the app:
  - validates startup config
  - initializes global config
  - starts cache cleanup
  - creates `NovelCoordinator`
  - creates `RouterAgent`
  - optionally wires router knowledge-base access
  - starts the message bus
  - installs a default message handler so unhandled requests fall back to `RouterAgent`

Important files:
- `run.py`
- `novel_agent/web/app.py`
- `novel_agent/web/dependencies.py`
- `novel_agent/web/routes/__init__.py`

### Backend composition
- The backend is a FastAPI app with modular routers under `novel_agent/web/routes/`.
- Route registration happens in `novel_agent/web/routes/__init__.py`.
- APIs are mounted twice:
  - `/api/v1/*` for versioned endpoints
  - `/api/*` for backward compatibility
- `novel_agent/web/app.py` also configures CORS, rate limiting, static files, templates, and log sanitization.

### Coordinator-worker writing architecture
- The core writing engine is `NovelCoordinator` in `novel_agent/workflow/coordinator.py`.
- It owns workflow state, checkpoints, project switching, and orchestration across specialist agents.
- It instantiates and coordinates:
  - `WorldbuilderAgent`
  - `OutlinerAgent`
  - `ChapterWriterAgent`
  - `PolisherAgent`
  - `EvaluatorAgent`
- It also wires in:
  - `ContextManager`
  - `CharacterManager`
  - `WorldManager`
  - memory/aux-memory services
  - message bus and metrics

This is the main “backend brain” for novel generation and project-scoped writing state.

### Router-first request handling
- `novel_agent/agents/router_agent.py` is the first-level intent router for user requests.
- It uses keyword/entity analysis to classify requests into creation, continuation, polishing, web search, trends, knowledge queries, project/config operations, or general chat.
- Depending on intent it routes to:
  - `NovelCoordinator`
  - continuous writing
  - polishing flow
  - communicator/chat flow
  - Skill calls for web/trend operations
- The router can consult the knowledge base before responding.

### Base agent / LLM configuration model
- `novel_agent/agents/base_agent.py` centralizes shared agent behavior.
- Agents use `openai.AsyncOpenAI` against OpenAI-compatible endpoints.
- Timeouts come from timeout settings, and retries are handled by project logic rather than SDK retries.
- `novel_agent/agent_config.py` defines the effective model config system:
  - multiple saved API configs
  - active config/model selection
  - per-agent overrides
  - fallback to global config

### Settings reload behavior
- `novel_agent/web/routes/settings.py` persists API settings back into `.env`.
- After reload/save, it recreates `NovelCoordinator` and re-syncs the `RouterAgent` coordinator reference.
- `/models` fetches model lists from OpenAI-compatible `/models` endpoints.

When modifying settings behavior, account for both config persistence and in-memory coordinator/router replacement.

### Project persistence model
- `novel_agent/project_manager.py` manages multi-project state.
- Project metadata lives in `projects.json`.
- Per-project content is stored under `data/projects/<project_id>/`.
- Project directories contain chapter and knowledge files such as `outline.json`, `characters.json`, `worldbuilding.json`, and `items.json`.
- Coordinator project switching reinitializes context/character/world managers against the selected project directory.

### Knowledge base architecture
- The knowledge base is a layered subsystem under `novel_agent/knowledge_base/`:
  - data layer: vector/full-text/metadata storage
  - logic layer: embeddings, chunking, chapter marking
  - application layer: hybrid search and navigation
- README documents hybrid retrieval (semantic + keyword search).
- Router knowledge-base wiring is conditional on embedding configuration being available.
- ChromaDB is used for vector storage; full-text search uses SQLite/FTS-style storage.

### Skill system
- v1.1 replaced older MCP-style integration with the `skills/` directory model.
- `novel_agent/web/routes/skills.py` discovers skills by scanning `skills/<skill>/SKILL.md` and loading service implementations from `scripts/*_service.py`.
- Skill enablement is persisted in `novel_agent/data/skills_config.json`.
- The router maps some intents directly to skills such as web search and trends.

### Frontend structure
- The frontend is server-rendered shell + modular vanilla JS, not React/Vue.
- Main HTML shell: `novel_agent/web/templates/index.html`
- Core bootstrap/state module: `novel_agent/web/static/app-core.js`
- `index.html` loads frontend scripts in strict dependency order; preserve that order when adding or moving modules.
- `app-core.js` owns:
  - global `store`
  - UI references
  - app initialization
  - module switching
  - project loading
  - Copilot session restoration
- `init()` in `app-core.js` is the real frontend bootstrap entry.

Important frontend modules visible from load order:
- `app-utils.js`
- `app-theme.js`
- `app-core.js`
- `app-nav.js`
- `app-knowledge.js`
- `app-aux-memory.js`
- `app-chapters.js`
- `app-settings.js` plus `web/static/settings/*`
- `app-copilot.js`
- `app-project.js`
- `continuous_write.js`
- `short-story/*` + `app-short-story.js`
- `novel-to-script/*` + `app-novel-to-script.js`
- `iw-editor.js`
- `app-trends.js`

### Feature areas currently present
From routers, frontend modules, and tests, the app includes multiple product surfaces beyond the original novel workflow:
- collaborative writing / Copilot chat
- infinite/continuous writing
- short-story creation
- novel-to-script workbench
- knowledge/resource management
- auxiliary memory center
- settings/model management
- trends search
- backup/resources APIs

When implementing UI changes, check both the route module and the corresponding `web/static/*.js` module pairings.

## Migration context that matters
From `MIGRATION_GUIDE.md`:
- default port changed from `8000` to `5656`
- MCP was replaced by Skills under `skills/`
- the old monolithic web app was split into modular route files under `novel_agent/web/routes/`
- rate limiting, CORS, and dependency injection were added as first-class web concerns

## Testing/package context
From `START_TESTING.md` and build scripts:
- packaged app testing expects `.env.example` to be copied to `.env`
- packaged runtime should be tested outside protected directories such as `C:\Program Files`
- packaged app persists data across restarts under its data directory
- startup failures may emit `startup_error.txt`
