# PETEY project manifest

This is the durable handoff for future PETEY development sessions. It records the
product's intent and boundaries rather than implementation detail. `AGENTS.md` is
the compact code-navigation guide; source and tests win whenever either document
drifts.

## Current baseline

- Release: **v0.21.0**
- Current version: **v0.21.0**
- Experimental preview retained at tag: `v0.19.0-experimental.1`
- Runtime: Python 3.12+, Flask/Werkzeug, pywebview, vanilla HTML/CSS/JavaScript
- Test framework: `unittest`; current full suite contains 353 tests
- Packaging: reviewed source ZIP built by `scripts/package_release.py`
- Built-in integrations: Discord and Tasks

PETEY is a local-first personal AI companion. It combines chat, complete persona and
voice profiles, SQLite memory/RAG, media generation, voice conversation, visual
mode, Discord, read-only approved-folder tools, and explicitly installed add-ons.
The desktop app should remain usable without a JavaScript build pipeline or a
separate web service.

Local-first messaging must lead with what stays on the computer and clearly name
the boundary of every model route: chat, prompt enhancement, and image inspection
follow the active local, Gemini, or OpenAI model; the selected model must support
images for vision. Transcription can use Local Whisper, and conversational speech
currently uses optional hosted providers or can remain disabled. Prompt-enhancement
actions always use the saved active chat provider rather than naming or forcing Gemini.

## Product principles

- Keep ordinary interaction simple. Advanced providers, tools, and integrations
  belong in settings or dedicated views.
- The desktop chat header keeps only the conversation title, status, and a chevron
  visible. Profile, animation, fullscreen, Chat/Visual, and Temporary controls live
  in its dismissible dropdown so chat and Visual Mode retain focus. The private
  repository is not linked from the app; the version sits beneath the deAPI link
  in the desktop sidebar footer.
- Mobile is a focused remote control: chat, visual mode, saved Petey profile, voice,
  microphone method, animation, and fullscreen. Its compact settings sheet keeps
  those essentials first and exposes the complete settings views behind an explicit
  Show all settings switch.
- Mobile chat keeps attachment and push-to-talk controls visible. In push-to-talk
  mode, holding the mic records and releasing submits; a quick tap toggles the
  persisted microphone mute state and shows the standard red X when muted.
- Microphone and automatic reply speech mute states persist across app restarts and
  are shared by desktop chat, mobile chat, and Visual Mode. Speaker buttons beside
  the microphone expose the same control on desktop and mobile. Mobile automatic
  replies use one speech request per answer; queued replies, add-on announcements,
  and wake acknowledgements re-check and obey the current mute state.
- Visual mode renders six distinct, full-canvas reactive scenes on pure black:
  Neural Core, Synapse Drift, Orbital Mind, Signal Bloom, Aurora Flow, and
  Constellation Field. Microphone and speech energy drive their motion, scale,
  light, signals, and particle density. Orange indicates listening, violet/blue
  indicates thinking, and electric blue follows PETEY's speech. Muted and error
  states remain distinct, reduced-motion preferences lower the animation, and the
  current PETEY avatar anchors the frameless bottom controls. Desktop fullscreen
  captions sit immediately below the speaking/listening state heading.
- Wake-name mode uses a small local keyword detector and a preloaded voice clip or
  immediate local chime for its fast acknowledgement.
  Completed utterances in every microphone mode are uploaded to the selected
  transcription provider. Configurable wake-pause and silence-to-send timers
  control acknowledgement and submission.
- Chat requests identify Petey Desktop or Mobile Petey; Discord and Petey Life add their own explicit surface context. SQLite message rows retain the source surface, and correction-aware retrieval presents older facts before newer user corrections.
- Deleting a saved chat asks whether to preserve its rows for memory retrieval or permanently delete them; memory deletion is irreversible.
- A Petey profile owns instructions, traits, communication style, speech provider,
  voice, and delivery. Microphone mode and the device's auto-speak behavior remain
  device/session concerns when a saved profile is activated.
- Personality & voice shows the five saved profiles first. The main Save Petey
  profile action asks which slot to use, then saves and activates that complete
  profile; occupied choices clearly indicate that they will be replaced.
- A saved chat may reference one saved Petey profile. Its prompt and speech voice
  follow that profile without changing the system persona. Chats with no assignment
  always inherit the current system persona, and clearing a saved profile returns
  its assigned chats to that fallback.
- Discord has its own room identity prompt and an independent saved persona. Its
  memory policy defaults to room-only, can store Discord for Desktop/Mobile recall,
  or can explicitly allow public Discord replies to search shared memory. Tools
  remain separately granted per add-on.
- Consequential add-on actions use proposals unless the user deliberately enables
  a scoped trust mode.

## Launch and network modes

| Mode | Command | Exposure and trust |
| --- | --- | --- |
| Native desktop | `python run_desktop.py` | Ephemeral loopback origin in pywebview |
| Browser development | `python run_desktop.py --browser` | Ephemeral loopback origin in browser |
| Local private link | `python run_desktop.py --lan` | Explicit LAN bind, random token exchanged for HttpOnly cookie |
| Trusted LAN HTTPS | `python run_desktop.py --lan-https` | Private CA/server certificate, Secure cookie, phone microphone support |
| Named Cloudflare tunnel | `python run_desktop.py --cloudflare` | Fixed loopback origin; PETEY private token plus Cloudflare HTTPS/access policy |
| Quick window | `python run_desktop.py --quick` | Compact local desktop window at cursor |

The native desktop remembers its last normal width and height in
`desktop-window.json` and restores them at the next launch. Fullscreen and
maximized transitions roll pending geometry back to the last committed normal
size before close or restart writes the file.

Cloudflare mode expects an already configured `cloudflared` tunnel and does not
start or manage it. It requires a durable PETEY pairing token stored in the private
data root's `remote-access.json` and exchanges it for a one-year HttpOnly, SameSite,
Secure cookie; the bare public hostname returns `401`. `--rotate-mobile-access`
replaces the token and revokes existing browser cookies on the next request. A
successful named-tunnel launch also stores the hostname and origin port there so a
later plain desktop launch can restart into Cloudflare mode. If none has been saved,
the native restart flow asks for the hostname.
Cloudflare Access should remain an outer identity check. Default startup must remain
loopback-only, and network binding must remain explicit.

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
- `mcp-servers.json`: private direct-MCP launch/auth configuration, tool allowlists, surfaces, keywords, and cached discovery
- `remote-access.json`: durable private Cloudflare pairing secret, hostname, and origin port
- `desktop-window.json`: last normal native desktop width and height
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
- Wake-name mode uses a local keyword detector for low-latency acknowledgement;
  the selected deAPI or Gemini provider transcribes the complete recording.
- A canned cue plays only when “Petey” or “Hey Petey” is followed by a short pause.
  Continued speech cancels the pending cue, so “Petey, turn off the lights” reaches
  the command path without an acknowledgement interrupting it.
- A standalone wake name starts a continuous voice turn: the cue plays, the request
  is recorded, transcribed by the selected provider, and sent after silence. The
  microphone re-arms after PETEY finishes speaking. Follow-ups do not require the wake name until the saved
  3–30 second dialogue window expires. The default window is eight seconds and is
  shared by desktop and mobile access.
- Cue selection follows the active speech voice, then `default/`, then an immediate
  local chime. The user may opt into browser-spoken fallback, which can start more
  slowly. Profile/speech API responses carry the resolved catalog, and audio URLs
  include file modification revisions to prevent stale browser playback.
- PETEY speech and wake acknowledgements must never overlap.
- When a remote voice add-on owns an active conversation, the browser suspends
  local microphone capture and automatic speech without changing saved mute
  preferences, then restores the prior runtime state after the session ends.

## Tools and add-ons

The built-in Filesystem MCP is read-only and receives only folders approved under
Settings → Tools. Never expose upstream write, move, delete, or arbitrary command
tools through that connector.

Direct MCP servers are configured independently under Settings → Tools & integrations.
Imports are disabled with no selected tools. Testing starts the local command or
contacts the remote endpoint; saved tool selection and explicit enablement grant
model access. Keywords and per-surface permissions apply at schema and dispatch.
Local stdio processes have the OS access of PETEY, unlike the approved-folder
Filesystem connector. PETEY retains local memory management. See `docs/mcp.md`.

External add-ons are trusted process-level Python but remain explicit and
restart-gated. Disabled code is never imported. Their routes live under
`/api/addons/<id>/`, assets stay within the installed folder, writable state goes to
`addon-data/<id>`, and cleanup runs at shutdown. Read `ADDONS.md` and
`docs/addons.md` before extension work.

Tasks is a built-in, restart-gated add-on. Its persisted schedules live in the
private data root, and external add-ons may register named task actions through
`context.tasks`. A schedule can contain ordered, reviewed actions from multiple enabled add-ons
and recur on selected weekdays. It invokes only those saved handlers; it does
not grant model tools or run arbitrary prompt text. PETEY must be running for due
actions, and schedules more than five minutes late are marked missed.

Update checks run only on explicit user action. PETEY core accepts only a clean
fast-forward from its official Git origin. Add-on updates require a manifest-declared
HTTPS GitHub repository and a bounded release ZIP whose ID, version, paths, and
manifest validate before atomic replacement. Add-on data remains separate and is
never replaced by an update.

Background add-on events are opt-in at the add-on level. The host serializes them
through a bounded queue, hides their source prompts from chat, persists PETEY's
visible reply in the transcript, and lets requested speech obey the client mute
state. Sanitized event metadata may attach one HTTPS image and external link to the
visible reply. Add-ons suppress routine repeats and never include credentials.

Browser-local camera and microphone consumers register bounded ownership through
`window.peteyMediaDevices`. Add-ons may clone an explicitly shareable camera track;
recording modes yield PETEY's ordinary continuous microphone and restore it when
finished rather than opening competing inputs. PETEY Webcam v0.3 and Conference
v0.3 also broker stable named cameras between paired browsers: one device may host
the Conference microphone and controls while another records video and answers
fresh-frame requests. Remote audio/video originals remain separate, with a
best-effort FFmpeg combined recording and explicit disconnects instead of camera
fallback.

Conference v0.4.3 runs the local wake detector while it owns the microphone and ends
live transcription segments after speech followed by silence. Direct wake-name
requests respond immediately. Topic-triggered contributions first play a short
permission cue and wait for a common affirmative or negative reply. After speaking,
PETEY returns to wake-name listening. Conference dialogue stays in the session
database until deletion, while PETEY can recall regular memories during a meeting.
Permission clips resolve from
`voice-cues/<voice>/conference/permission/` with the `default` voice fallback,
randomize across every supported clip, derive transcript text from filenames, and
obey PETEY's persisted speaker mute.

Microphone transcription offers Automatic (deAPI then Gemini), deAPI only, Gemini
only, and Local Whisper. Local Whisper optionally
uses faster-whisper in process, requires an explicit model download into PETEY's
data root, and supports automatic, CPU, or CUDA execution. On Linux, startup can
discover pip-installed NVIDIA runtime libraries before faster-whisper loads.
Conference follows the same selection. Media text-to-speech offers explicit deAPI Media and Gemini
choices with their own model and voice lists, independently from PETEY's
conversational speech provider.
Conversational speech supports Automatic (Gemini then OpenAI), deAPI, Gemini,
OpenAI, and Disabled. The selected provider, model, and voice belong to the
active PETEY profile and apply consistently to desktop, mobile, and Visual Mode.

Model tool schemas and dispatch both enforce availability. Compatible add-ons have
an off-by-default model-control policy with capability and surface grants. Metered
capabilities enforce autonomous daily limits; direct requests identified by the
tool's `explicit_when` predicate bypass only that limit. Add-on MCP catalogs need
exact allowlists and bounded results.

## UI and compatibility

- Settings navigation is catalog-driven by `web/settings_pages.py`; preserve stable
  view and section IDs so help links and saved hashes continue to work.
- The startup bootstrap includes current messages and voice-cue metadata so desktop
  and mobile need one initial API round trip. Core static assets use a startup mtime
  query revision and immutable caching. Restart the server and reload remote browsers
  after JavaScript/CSS changes.
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

## Native Android companion

The optional sibling `petey-android-companion/` owns Android microphone, wake-name
inference, audio routing, foreground-service lifecycle, and Keystore storage.
Desktop owns transcription, conversations, memory, model/tool policy, and speech.
Its narrow `/api/companion/v1` bearer API exchanges the existing remote private-link
secret for a one-year device credential, stores only credential hashes, and permits
self-revocation. Rotating mobile access revokes all companion credentials as well.
The Android client requires HTTPS, validates certificates, refuses redirects, and
never uploads idle wake-detection audio. Android microphone recovery after process
kill/reboot requires a visible user start; Bluetooth/Android Auto compatibility
must be validated on hardware and does not imply a projected car dashboard app.
