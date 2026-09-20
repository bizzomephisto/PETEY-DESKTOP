# PETEY project manifest

This is the durable handoff for future PETEY development sessions. It records the
product's intent and boundaries rather than implementation detail. `AGENTS.md` is
the compact code-navigation guide; source and tests win whenever either document
drifts.

## Current baseline

- Release: **v0.18.2**
- Baseline commit: `6694347`
- Runtime: Python 3.12+, Flask/Werkzeug, pywebview, vanilla HTML/CSS/JavaScript
- Test framework: `unittest`; current full suite contains 260 tests
- Packaging: reviewed source ZIP built by `scripts/package_release.py`
- Built-in integration: Discord only

PETEY is a local-first personal AI companion. It combines chat, complete persona and
voice profiles, SQLite memory/RAG, media generation, voice conversation, visual
mode, Discord, approved-folder workspace tools, and explicitly installed add-ons.
The desktop app should remain usable without a JavaScript build pipeline or a
separate web service.

## Product principles

- Keep ordinary interaction simple. Advanced providers, tools, and integrations
  belong in settings or dedicated views.
- Mobile is a focused remote control: chat, visual mode, saved Petey profile, voice,
  microphone method, animation, and fullscreen.
- A Petey profile owns instructions, traits, communication style, speech provider,
  voice, and delivery. Microphone mode and the device's auto-speak behavior remain
  device/session concerns when a saved profile is activated.
- A saved chat may reference one saved Petey profile. Its prompt and speech voice
  follow that profile without changing the system persona. Chats with no assignment
  always inherit the current system persona, and clearing a saved profile returns
  its assigned chats to that fallback.
- Discord has its own room identity prompt. Desktop persona, memory, and tools do
  not bleed into Discord unless a specific external add-on is allowed there.
- Consequential work is reviewable. Workspace model writes/commands and untrusted
  add-on actions use proposals unless the user deliberately enables a scoped trust
  mode.

## Launch and network modes

| Mode | Command | Exposure and trust |
| --- | --- | --- |
| Native desktop | `python run_desktop.py` | Ephemeral loopback origin in pywebview |
| Browser development | `python run_desktop.py --browser` | Ephemeral loopback origin in browser |
| Local private link | `python run_desktop.py --lan` | Explicit LAN bind, random token exchanged for HttpOnly cookie |
| Trusted LAN HTTPS | `python run_desktop.py --lan-https` | Private CA/server certificate, Secure cookie, phone microphone support |
| Named Cloudflare tunnel | `python run_desktop.py --cloudflare` | Fixed loopback origin; Cloudflare provides public HTTPS/access policy |
| Quick window | `python run_desktop.py --quick` | Compact local desktop window at cursor |

Cloudflare mode expects an already configured `cloudflared` tunnel and does not
start or manage it. It intentionally does not use the LAN private-link token;
Cloudflare Access should protect an everyday public hostname. Default startup must
remain loopback-only, and network binding must remain explicit.

## State and secrets

The data root is `PETEY_DATA_DIR` when set, otherwise the platform application-data
directory. Important contents include:

- `settings.json`: preferences, providers, profiles, integrations, approved paths
- `installation.json`: stable local identity
- `petey-memory-v2.sqlite3`: messages, documents, embeddings, generation records
- `gallery/`: captured media results
- `addons/`: installed external source
- `addon-data/<id>/`: external add-on state and credentials
- `voice-cues/<voice>/`: user-replaceable wake acknowledgements
- `lan-tls/`: reusable local CA and LAN certificates
- `wake-word/`: downloaded local keyword model

Never commit or inspect secret values casually. Public APIs return key/token status,
never saved credentials. Supported environment names are `GEMINI_API_KEY`,
`OPENAI_API_KEY`, `LOCAL_AI_API_KEY`, `DEAPI_KEY`, `DISCORD_BOT_TOKEN`,
`PETEY_CLOUDFLARE_HOSTNAME`, `PETEY_CLOUDFLARE_PORT`, and `PETEY_DATA_DIR`.

Tests use temporary data roots and mocks. They must not touch live user databases,
credentials, paid provider calls, Home Assistant, Discord, or other external
services.

## Voice behavior

- Chat TTS, vision, embeddings, and STT are independently configured.
- Gemini 3.1 speech can stream PCM; automatic speech can fall back to OpenAI.
- Wake-name mode uses a local keyword detector for low latency and cloud STT for the
  complete request.
- A canned cue plays only when “Petey” or “Hey Petey” is followed by a short pause.
  Continued speech cancels the pending cue, so “Petey, turn off the lights” reaches
  the command path without an acknowledgement interrupting it.
- Cue selection follows the active speech voice, then `default/`, then browser
  speech. Profile/speech API responses carry the resolved catalog, and audio URLs
  include file modification revisions to prevent stale browser playback.
- PETEY speech and wake acknowledgements must never overlap.

## Tools and add-ons

The built-in Filesystem MCP is read-only and receives only approved Workspace
roots. Never expose upstream write, move, delete, or arbitrary command tools through
that connector.

External add-ons are trusted process-level Python but remain explicit and
restart-gated. Disabled code is never imported. Their routes live under
`/api/addons/<id>/`, assets stay within the installed folder, writable state goes to
`addon-data/<id>`, and cleanup runs at shutdown. Read `ADDONS.md` and
`docs/addons.md` before extension work.

Model tool schemas and dispatch both enforce availability. Keep paid or mutating
tools tied to clear user intent. Add-on MCP catalogs need exact allowlists and
bounded results; Discord receives only the tools from external add-ons individually
authorized with **Allow in Discord**.

## UI and compatibility

- Settings navigation is catalog-driven by `web/settings_pages.py`; preserve stable
  view and section IDs so help links and saved hashes continue to work.
- Core static assets use a startup mtime query revision. Restart the server and
  reload remote browsers after JavaScript/CSS changes.
- The chat header keeps the conversation name and effective persona visible. New
  chats choose a saved profile in the creation dialog, and long chats expose a
  jump-to-latest control only while the reader is away from the bottom.
- Phone layout applies at 760 px and below. Keep controls within safe areas and test
  at a real phone-sized viewport.
- pywebview, ordinary browsers, mobile Chrome, and Cloudflare proxying have distinct
  microphone/fullscreen/audio constraints. Python tests do not prove those flows;
  perform a browser or native smoke check when they change.
- Existing settings must migrate in place. New settings need defaults, validation,
  persistence, public projection, UI wiring, and state/API tests.

## Release discipline

1. Update `petey/version.py`, README/wiki version text, and `CHANGELOG.md`.
2. Run focused tests, then `python -m unittest discover -s tests -v` for runtime
   changes. Run `node --check` when Node is available and JavaScript changed.
3. Run `git diff --check` and inspect `git status` and the final diff.
4. Commit and create a new annotated tag. Never move or amend a published tag.
5. Run `python scripts/package_release.py`. The script rejects external/example
   add-ons, `.env`, symlinks, and known legacy add-on roots.
6. Generate release notes from the matching changelog section and a SHA-256 file.
7. Push the commit and tag, publish both assets, and verify the release is public.

Keep release artifacts under ignored `dist/`. A clean final status should show local
`main` synchronized with `origin/main` after publication.

## Start-of-session checklist

1. Read this file and `AGENTS.md`; read `ADDONS.md` for extension work.
2. Run `git status --short`, `git log -1 --oneline`, and inspect the current version.
3. Search task-relevant symbols with `rg`; use source and tests to resolve drift.
4. Preserve user data and secrets. Use temporary roots for tests and smoke servers.
5. Finish the requested behavior, validate it, update durable documentation, and
   report only checks actually run.
