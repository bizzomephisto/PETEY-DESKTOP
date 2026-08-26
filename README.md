# PETEY Desktop

Current release: **v0.10.0**

PETEY is a standalone desktop AI assistant with local conversations, configurable
personality, universal SQLite memory, RAG document management, deAPI media tools,
and an approval-gated project workspace.

## Highlights

- Gemini, OpenAI, LM Studio, Ollama, and other OpenAI-compatible chat providers
- Local SQLite conversation memory with configurable local or hosted embeddings
- Temporary chats that do not read or write memory
- Built-in personality templates, editable system prompts, and five saved persona slots
- RAG uploads, retrieval testing, vector rebuilding, and local database controls
- Parallel deAPI image, video, music, speech, background-removal, and upscale jobs
- Real deAPI progress, provider status, live previews, balance, and a local gallery
- Conversational image generation through modular model tools
- Visual thumbnail browser for selecting source images
- Multiple saved chats, UI scaling, collapsible navigation, and always-on-top mode
- Approved-folder IDE with a file tree, editor, command console, and reviewable AI edits

PETEY runs a loopback-only Flask server inside a pywebview desktop window. If a
native backend is unavailable, the launcher can open the same interface in your
browser.

## Requirements

- Python 3.12 or newer
- A language-model provider: Gemini, OpenAI, or a local OpenAI-compatible server
- A deAPI key only if you want media generation

## Install and run

```bash
git clone https://github.com/bizzomephisto/PETEY-DESKTOP.git
cd PETEY-DESKTOP
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python run_desktop.py
```

On Windows, activate the environment with `.venv\Scripts\activate`. For
browser-based development, run:

```bash
python run_desktop.py --browser
```

On Linux, the requirements install the PySide6 backend for pywebview. Do not run
`pip install gi`; PyGObject is supplied through Linux distribution packages.

Install PETEY Desktop in your Linux application menu with:

```bash
python run_desktop.py --install-shortcut
```

Application artwork is available under `assets/icons/` as a transparent PNG
master, Linux PNG, Windows ICO, and macOS ICNS file.

Provider keys and models can be configured from **Settings**. Values saved there
are stored in PETEY's platform application-data directory. Environment variables
from `.env` are also supported.

## Local data and privacy

PETEY stores its installation identity, settings, memory database, and generated
gallery in the platform application-data directory—not in this repository. Use
temporary chat when a conversation should not be retained.

When a hosted chat or embedding provider is selected, relevant prompts, selected
workspace-file context, or memory text are sent to that provider. Local-provider
mode keeps those model requests on the configured local endpoint. deAPI media
requests are sent to deAPI.

## Workspace safety

PETEY's file tools are restricted to folders you explicitly approve. Proposed AI
edits display a diff and remain inert until approved. Commands also require an
explicit approval and stop after 60 seconds.

Approved commands still run with your operating-system user permissions. Folder
approval constrains PETEY's built-in file operations; it is not an operating-system
sandbox for arbitrary code.

## Development

Run the test suite with:

```bash
python -m unittest discover -s tests -v
```

Core layout:

- `run_desktop.py` — desktop launcher and native-window bridge
- `petey/assistant.py` — provider-neutral conversation service
- `petey/desktop_memory.py` — local SQLite memory and RAG store
- `petey/desktop_state.py` — installation settings and saved chats
- `petey/deapi_client.py` — deAPI transport and progress polling
- `petey/media_jobs.py` — concurrent generation queue and gallery capture
- `petey/workspace.py` — approved-folder file and command operations
- `petey/tools/` — permission-aware model tool registry and capability modules
- `web/desktop_app.py` — loopback Flask API
- `web/templates/desktop.html` and `web/static/desktop.*` — desktop interface
