# PETEY coding-agent context

Scope: repository. Snapshot: 2026-09-06, v0.14.0, source baseline `2d1db8d`.
Start here; read only task-relevant implementation/tests. This is a navigation cache, not a substitute for checking code before edits. Source wins on factual drift; update this file when architecture, commands, contracts, or extension points change. Keep it compact; no session logs or copied source.

## Fast start

- Product: standalone desktop AI companion/roleplay assistant; chats, personas, SQLite memory/RAG, media studio/gallery, voice, visual mode, approved-folder IDE.
- Stack: Python 3.12+, Flask/Werkzeug, pywebview, vanilla JS/CSS/HTML; direct HTTP provider clients. No JS build pipeline/package.json.
- Launch: `python run_desktop.py`; browser development: `python run_desktop.py --browser`; Linux menu shortcut: `python run_desktop.py --install-shortcut`; cursor popup: `python run_desktop.py --quick`; COSMIC Super+F1 binding: `python run_desktop.py --install-quick-hotkey`.
- The visible app/window/launcher name is `PETEY`. Linux Qt windows retain `petey-desktop` as their application name and desktop-file ID; keep the installed launcher's `StartupWMClass` aligned so docks resolve the icon on Wayland/X11.
- Setup: venv + `python -m pip install -r requirements.txt`; copy `.env.example` only if `.env` absent. Linux requirements select pywebview/PySide6; FFmpeg supplies video previews. See README for platform setup.
- First checks: `git status --short`; `git ls-files`. Use `rg -n 'symbol' specific/files` then bounded reads. Avoid dumping entire large files, repository-wide recursive reads, assets, environments, databases.
- This folder (`PETEY_DESKTOP`) contains the standalone desktop project. Legacy Discord/web-admin source, data, and the old copied `venv` have been removed; `.gitignore` still excludes them to prevent accidental reintroduction. Use `.venv` for the desktop environment and tracked files to identify current source.

## Runtime/data flow

`run_desktop.LocalServer` -> `create_desktop_app()` -> threaded Werkzeug on `127.0.0.1`, ephemeral port -> pywebview (or browser). `DesktopBridge` handles native folder dialogs, window flags/fullscreen, gallery open/save, project/provider links.

UI `web/templates/desktop.html` + `web/static/desktop.js` + `desktop.css` -> `/api/desktop/*` in `web/desktop_app.py` (composition root, validation, errors, service injection).

Chat model picker: `AIProvider.list_models` supports Gemini's paginated model catalog (filtered for chat), OpenAI, and local servers. Providers settings exposes one dropdown per model; `loadModelCatalogs` automatically refreshes on settings entry, provider/key changes, and local server URL changes, preserving selections and rejecting stale replies. Catalog presence does not guarantee account access; Test connection checks generation.

Vision has no separate UI selector. With Gemini chat, `AIProvider._vision_model` follows the chat model (including older settings); saving Gemini chat also synchronizes the retained vision setting. OpenAI/local chat still uses the configured Gemini vision model. Read-only catalog provider and local `base_url` overrides never change saved settings.

Chat: multipart `/chat` -> `AssistantIdentity` + optional `AssistantAttachment` -> `AssistantService.respond` -> recent history + cross-conversation retrieval + optional Gemini image description -> `AIProvider.complete[_with_tools]` -> `AssistantReply(text,tool_events)` -> persistence/UI. User messages can use deferred embeddings; queue them after provider completion. Assistant author ID = `PETEY`.

Chat streaming: multipart `/chat` with `stream=true` returns NDJSON status/delta/done/error events and heartbeats via a bounded worker queue. `AssistantService.respond(on_text=...)` uses `AIProvider.complete_stream` for ordinary replies; tool loops remain buffered. `AIProvider.complete_with_tools` supports Gemini and OpenAI-compatible function calling with duplicate-call protection. Provider SSE responses close on completion/error; only final cleaned replies enter assistant memory. JS `readChatStream` handles split UTF-8/events and marks interrupted partial replies; speech runs after completion. The original JSON route behavior remains available without the stream flag.

MCP tools: `FilesystemMCPManager` in `mcp_client.py` owns a persistent stdio JSON-RPC connection to a pinned official filesystem server launched through `npx`. Approved Workspace paths are its only roots. `tool_specs()` filters the discovered catalog through an explicit read-only allowlist and prefixes model-facing names with `mcp_filesystem__`; write/move/delete capabilities never enter `ToolRegistry`. Settings/API: `DesktopState.tools`, `/api/desktop/tools*`, `view-tools`, `loadTools`. First enable may download the pinned npm package; opening Settings alone never starts it. `LocalServer.close()` stops the child process.

Media: route or model tool -> `MediaJobManager.submit` -> worker -> `MediaService` -> async `DeapiClient` -> progress/job polling -> `MediaGallery` capture. Default 3 workers; queued does not mean completed. Chat speech may use transient job audio outside gallery.

Media estimates: `/media/estimate` -> `MediaService.estimate` -> `DeapiClient.estimate_price` uses deAPI v2 price lookups without queuing jobs. Images/video share model parameter limits with generation; speech, music, and legacy video restyling have no estimate. JS `scheduleMediaEstimate` debounces lookups and rejects stale replies. Catalog, balance, and estimate requests use request-local clients via `media_provider_request` to isolate event loops.

State: `DesktopState` owns installation/person IDs, conversation metadata, settings, personas/voice slots, approved workspaces. JSON writes use temp-file replacement + lock. `DesktopMemory` owns message/document content and embeddings; SQLite WAL, per-operation connections, bounded background embedding workers. Tables: `memory_items`, `image_generations`, `metadata`; embedding provider/model/dimension signatures matter.

Data root: `PETEY_DATA_DIR` override; else Linux `$XDG_DATA_HOME/petey` or `~/.local/share/petey`; macOS `~/Library/Application Support/Petey`; Windows `%LOCALAPPDATA%/Petey`. Files: `installation.json`, `settings.json`, `petey-memory-v2.sqlite3`, `gallery/`. Never use real user data for tests or commit it. `.env`, `envbak/`, `config_*.json`, `chroma_db/`, `gens/`, `user_images/` are private/ignored; don't read secrets for onboarding.

## Task -> files/symbols

Paths below are repo-relative; backend modules live under `petey/` unless otherwise shown. Tests normally `tests/test_<module>.py`.

| Task | Read/edit anchors |
|---|---|
| Chat/prompts/history/attachments | `assistant.py`: `AssistantService.respond`, `_describe_image`; `config.py`: presets, `_build_enriched_prompt`; `tests/test_assistant.py` |
| Chat providers/models/vision/embeddings | `ai_provider.py`: `AIProvider`, `public_config`, `complete_with_tools`, `describe_image`, `embed`; `http_client.py`: shared bounded requests session |
| Defaults/settings/personas/saved chats | `desktop_state.py`: `_load_or_create_settings`, `update_*`, `_validated_*`, persona-slot methods; `config.py` |
| PETEY Plus plan preview | `subscription_plans.py`: `normalize_plan`, `estimate_plan`, rate card; API `/plan`; template `view-plan`; JS `loadPlanBuilder`, `renderPlanEstimate`; `tests/test_subscription_plans.py` |
| Memory/RAG/search | `desktop_memory.py`: `store_memory_deferred`, `store_document`, `search_memories`, `rebuild_embeddings`; API `/knowledge*`, `/memory/*` |
| New conversational tool | `tools/registry.py`: `ToolSpec`, `ToolRegistry`; implement module in `tools/`, compose in `tools/__init__.py:build_desktop_tool_registry`; `tools/media.py` is example; `tests/test_tools.py` |
| MCP client/filesystem tools | `mcp_client.py`: `MCPStdioClient`, `FilesystemMCPManager`, read-only allowlist; API `/tools*`; `tests/test_mcp_client.py` |
| Media operation/parameters/provider API | `media_service.py`: `OPERATIONS`, `MediaInput`, validation/dispatch; `deapi_client.py`: model discovery, limits/fallback, polling; `tests/test_media_service.py`, `test_deapi_client.py` |
| Queue/progress/gallery/video preview | `media_jobs.py`: `MediaJobManager`, `MediaGallery`; API `/media/jobs*`, `/gallery*`; `tests/test_media_jobs.py` |
| Voice output | `gemini_tts.py`: `generate`, `stream_pcm`; `openai_tts.py`, `deapi_tts.py`; `media_jobs.py:_execute_speech`; API `/speech`, `/chat/speech[/stream]` |
| Microphone/transcription | `deapi_stt.py`, `gemini_stt.py`; API `/voice-input[/transcribe]`; JS `handleMicrophoneAudio`, `finishVoiceCapture`, `handleVoiceTranscript`, `beginPushToTalk` |
| Folder IDE/edit/command approval | `workspace.py`: `resolve`, `preview_write`, `propose_write`, `propose_command`, `approve`, `agent_proposals`; API `/workspaces*`, `/workspace/*` |
| Image picker/thumbnails | `image_browser.py`: token-scoped `open`, `resolve`, `thumbnail`; API `/image-browser/*` |
| Window/launcher/packaging artwork | `run_desktop.py`: `DesktopBridge`, `quick_window_position`, `LocalServer`, `main`; `petey/quick_window.py`; `assets/icons/`; `tests/test_desktop_launcher.py` |
| API wiring/contracts | `web/desktop_app.py:create_desktop_app`; injectable state/runtime/gallery/jobs/memory/workspace service; `tests/test_desktop_app.py` |
| Version/project URLs | `version.py`; README release text; template receives version/URLs from Flask |

JS navigation (search symbols, not fixed line numbers): `loadDesktop`, `addMessage`, `showView`, `applyPreferences`; `loadAIProvider`; `loadVoiceInputSettings`; `speakChatText`, `playGeminiSpeechStream`; `loadPersonality`, `renderSavedPersonaSlots`; `loadKnowledge`, `loadMemoryProvider`; `loadTools`, `renderFilesystemTool`; `loadMediaCatalog`; `loadWorkspaces`, `openWorkspaceFile`, `renderWorkspaceProposals`; `startNeuralVisualization`. Composer submission and many controls use inline event listeners. Match HTML element IDs, JS selectors, CSS classes, and API fields when changing UI.

Settings UI: `settings_navigation` template macro provides category navigation: Appearance (`view-settings`), Personality & voice, Microphone (`view-microphone`), Models & API keys (`view-providers`), Tools (`view-tools`), Knowledge, Memory & privacy. Provider choices/keys stay centralized; `openSetting` and `data-settings-target` jump to specific sections. Search indexes headings/labels, not field values. Persona snapshots include speech configuration; microphone behavior stays installation-wide. Theme preference (`midnight`, `ocean`, `forest`, `paper`) is validated/persisted by DesktopState, server-rendered on `<html data-theme>`, and applied by semantic CSS variables. See `docs/interface-design.md`. `/api/desktop/provider-keys` returns status only; saved deAPI keys feed media and STT with environment fallback.

## Preserve these contracts

Help: sidebar `view-help` includes `web/templates/desktop_help.html`; setup links and feature guidance stay here, with settings jumps through `data-settings-view` / `data-settings-target`. Keep `knownViews` aware of `help` for direct `#help` navigation. Provider documentation links open externally.

- Temporary chat bypasses memory reads/writes and image-generation memory recording; temporary history is supplied by frontend. It can still invoke providers/tools; it is not offline mode.
- Chat, vision, embeddings, TTS, STT have separate configuration. Vision is Gemini even when chat is OpenAI/local. STT defaults to deAPI with Gemini fallback; Gemini speech supports streaming and OpenAI fallback. Inspect each path before changing fallback behavior.
- Public provider settings must redact keys. Environment names: `GEMINI_API_KEY`, `OPENAI_API_KEY`, `LOCAL_AI_API_KEY`, `DEAPI_KEY`. Use `.env.example` for names, not `.env` contents.
- Tool availability is checked both when offering schemas and dispatching. Current conversational tool is `generate_image`, gated by explicit image intent; keep paid actions tied to user intent. Validate arguments in handlers.
- Workspace paths resolve within approved roots (including symlink checks); AI writes/commands are proposals until approved. Preserve stale-content hashes, proposal expiry, 60s command timeout. Manual editor save is a separate path. Shell commands run with OS-user privileges, not an OS sandbox. These are product behavior requirements, not extra approval rules for coding agents editing this repo.
- Filesystem MCP receives only approved Workspace roots. Keep the model-facing allowlist read-only and bounded; never pass through server write, move, delete, or arbitrary command tools. Enabling the connector must be an explicit user action.
- `AsyncRuntime.call` uses a fresh event loop per request and closes the shared deAPI session. Media model/balance reads must create and close a request-local client for both saved and environment keys: the first Media visit requests them concurrently. Preserve session/loop ownership and job-worker shutdown; don't casually move blocking/provider calls between threads/loops.
- Keep Flask loopback-only. Upload cap currently 25 MiB; workspace text-file cap 2 MiB. Preserve API error handling and bounded inputs.

## Extend + validate

- New setting: state default/load/validation/update -> API public projection -> HTML/JS -> state/API tests; existing settings must still load.
- New feature: relevant service -> route -> UI as needed; reuse injectable services and existing boundaries. New media operation must cover catalog, input validation, dispatch, job handling/UI, tests.
- Full suite: `python -m unittest discover -s tests -v`.
- Focused suite example: `python -m unittest discover -s tests -p 'test_workspace.py' -v` (substitute mapped test filename). Tests use `unittest`, mocks/AsyncMock, temporary directories, Flask test client; do not require paid live calls for routine verification.
- JS syntax if Node available: `node --check web/static/desktop.js`; no configured frontend test runner. UI changes also need a browser/native smoke check of the affected flow; Python tests don't prove microphone/audio/fullscreen/native behavior.
- Docs-only: verify referenced paths/symbols and `git diff --check`; runtime suite unnecessary. Report checks actually run, not assumed results.
