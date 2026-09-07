# Installation

## Requirements

- Python 3.12 or newer
- Git
- FFmpeg for browser-compatible generated-video previews
- A Gemini, OpenAI, or local OpenAI-compatible chat provider
- Node.js with `npx` only if you want the optional Filesystem MCP tool

## Install

```bash
git clone https://github.com/bizzomephisto/PETEY-DESKTOP.git
cd PETEY-DESKTOP
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
cp .env.example .env
python run_desktop.py
```

On Windows, activate the environment with:

```powershell
.venv\Scripts\activate
```

The `.env` file is optional because keys can be saved inside PETEY. Never commit
that file or share its contents.

## Linux application menu

With the environment active, run:

```bash
python run_desktop.py --install-shortcut
```

Run this command again after moving the project or replacing its Python environment.
The shortcut stores absolute paths to the project and interpreter.

## Browser mode

For development or when a native window backend is unavailable:

```bash
python run_desktop.py --browser
```

PETEY binds its local web server to `127.0.0.1` on an available port.

Next: [Getting Started](Getting-Started).
