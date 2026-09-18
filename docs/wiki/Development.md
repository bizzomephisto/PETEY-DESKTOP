# Development

PETEY uses Python 3.12+, Flask, Werkzeug, pywebview, vanilla JavaScript, CSS, and
HTML. There is no JavaScript build pipeline.

## Start a development session

```bash
source .venv/bin/activate
python run_desktop.py --browser
```

Read [`AGENTS.md`](https://github.com/bizzomephisto/PETEY-DESKTOP/blob/main/AGENTS.md)
before changing the code. It documents the runtime flow, task-to-file map, preserved
contracts, and focused test commands.

## Main components

- `run_desktop.py` — launcher and native-window bridge
- `petey/assistant.py` — conversation service
- `petey/ai_provider.py` — chat, vision, tools, and embeddings providers
- `petey/desktop_memory.py` — SQLite memory and RAG
- `petey/desktop_state.py` — settings, identity, and conversations
- `petey/media_service.py` and `petey/media_jobs.py` — media operations and queue
- `petey/workspace.py` — approved-folder operations and proposals
- `petey/mcp_client.py` — read-only Filesystem MCP integration
- `petey/addons.py` — external add-on discovery and lifecycle
- `petey/discord_*.py` and `petey/room_chat.py` — built-in Discord integration
- `web/desktop_app.py` — loopback Flask API
- `web/settings_pages.py` — Settings page and section catalog
- `web/templates/` and `web/static/` — desktop interface

PETEY releases include Discord as the only built-in integration. External add-ons
belong in the user's PETEY data directory and are not stored in this repository.
See [`docs/addons.md`](../addons.md) for the extension contract.

## Build a source release

The release builder uses Git's tracked and non-ignored source file set, rejects
external add-on manifests and local development folders, and writes a versioned
ZIP under `dist/`:

```bash
python scripts/package_release.py
```

Inspect the printed file count and SHA-256 digest before attaching the archive to
a GitHub release. GitHub's automatic source archives should be created from the
same reviewed commit and version tag.

## Validation

```bash
python -m unittest discover -s tests -v
node --check web/static/desktop.js
node --check web/static/settings.js
node --check web/static/discord.js
git diff --check
```

UI changes also need a browser or native-window smoke check of the affected flow.
Routine tests do not make paid provider calls.

Contributions and bug reports are welcome in the
[PETEY repository](https://github.com/bizzomephisto/PETEY-DESKTOP).
