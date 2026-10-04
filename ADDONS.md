# PETEY add-on map

This file is the repository-level index for PETEY's extension system. The complete
author contract is [`docs/addons.md`](docs/addons.md); the implementation in
`petey/addons.py`, `petey/tools/registry.py`, and `petey/mcp_client.py` remains the
source of truth.

## What ships

- Discord and Tasks are built-in add-ons and are enabled by default. Tasks schedules ordered, reviewed actions from enabled external add-ons, including selected weekdays.
- Home Assistant, Blender, and every other connector are external installations.
- GitHub source releases contain no third-party or example add-ons. The packaging
  script rejects `examples/`, legacy add-on roots, external `petey-addon.json`
  files, `.env`, and symlinks.
- Local development examples may exist in the ignored `examples/addons/` folder;
  they are reference workspaces rather than release contents.

## External addons on GitHub

| Addon | What it adds |
| --- | --- |
| [Home Assistant MCP](https://github.com/bizzomephisto/PETEY-HOME-ASSISTANT) | Household entities, device controls, and alerts. |
| [Spotify](https://github.com/bizzomephisto/PETEY-SPOTIFY) | Spotify Connect playback, playlists, DJ mode, and a shared media player. |
| [OpenCode](https://github.com/bizzomephisto/PETEY-OPENCODE) | Start, monitor, preview, and cancel coding-agent runs. |
| [Google Sheets Scorecards](https://github.com/bizzomephisto/PETEY-GOOGLE-SHEETS) | Read configured sheets and fill golf scores from scorecard pictures. |
| [Quick Actions](https://github.com/bizzomephisto/PETEY-QUICK-ACTIONS) | Customizable silent action buttons for desktop and mobile. |

These projects remain independently versioned and installed. Follow each
repository's setup instructions and use release archives where available.

## Additional local addons

These addons are available in the development setup; they currently have no
published repository on this GitHub account. They are installed separately.

| Addon | What it adds |
| --- | --- |
| Blender MCP | Scene inspection and reviewed Blender script execution. |
| PETEY Webcam | Named cameras, visual questions, snapshots, and frame comparison. |
| PETEY Conference | Record, transcribe, search, and selectively participate in meetings. |
| Discord Voice & YouTube DJ | Wake-name voice conversations and a YouTube playback queue. |
| Freebuff | Set up, start, and track Freebuff coding-agent runs. |
| Real-Time Clock | Current-time tools and an analog/digital clock panel. |
| System Monitor | CPU, memory, load, uptime, and process information. |

## Discord Voice and YouTube DJ

`discord-voice` is an external add-on, separate from PETEY's built-in Discord text
bridge. The built-in bridge handles room conversation, presence, slash commands,
media jobs, and administration proposals. Discord Voice adds the real-time voice
channel and DJ process and must remain independently installable and removable.

Version 0.2.2 provides these behaviors:

- Joins a selected Discord voice channel with discord.py voice receive, PyNaCl,
  and Discord's DAVE library. Incoming 48 kHz stereo PCM is separated by member
  and converted to bounded 16 kHz mono captures.
- Uses PETEY's local wake-name detector before transcription. A standalone
  “Petey” plays the configured acknowledgement and arms the next utterance; a
  continuous “Petey, ...” request and the configured same-speaker follow-up window
  go directly to transcription. With Local Whisper selected, a completed local
  utterance may also recover a missed wake-name detection without uploading
  ordinary room conversation.
- Uses PETEY's Discord room persona and assigned speech profile. Its public Discord
  activity changes from **Listening for Petey** to **Thinking...**, then
  **Speaking**, and returns to listening after playback.
- Optimizes interactive latency by capping Discord's end-of-speech wait at 650 ms,
  preloading the selected Local Whisper model after listening starts, and invoking
  Gemini or OpenAI speech directly instead of placing short replies behind the
  general media-job queue. The add-on panel exposes silence, transcription, model
  reply, speech generation, and total-to-speech timing for the most recent turn.
- Suspends core browser microphone capture and automatic desktop speech through
  `window.peteyVoiceSessions` for the duration of an active joined/listening
  session, then restores the prior runtime state when the session ends.
- Streams a bounded YouTube-only queue through yt-dlp and FFmpeg. Text, spoken,
  and panel controls cover play/queue, pause, resume, skip/next, stop/wait, and
  volume. It deliberately has no Spotify control path.

Its source manifest declares add-on API version `1`, ID `discord-voice`, and its
own requirements. Keep DAVE, Discord voice receive, yt-dlp, and similar optional
packages out of PETEY core requirements. Writable state remains under
`addon-data/discord-voice`; cached generated voice files are disposable.

## Lean private backup layout

When the user explicitly requests a minimal full-project backup, place it in a
protected directory outside the live PETEY checkout and use this layout:

```text
PETEY_DESKTOP_MINIMAL_BACKUP_<date>/
  BACKUP_README.md
  BACKUP_MANIFEST.sha256
  petey-desktop/       # current Git-tracked core files plus the requested .env
  addons/<addon-id>/   # installed add-on source, manifests, assets, and docs
```

Copy tracked core files from the working tree so intentional uncommitted edits are
preserved. Include `.env` only because the user explicitly asked for it. Prefer a
filesystem that enforces Unix ownership, set the backup folder to owner-only and
`.env` to owner read/write, verify the resulting modes, and describe the folder as private. Copy
installed add-on source so the current feature set can be restored, but omit `.git`,
virtual environments, `__pycache__`, `.pytest_cache`, downloaded dependency trees,
and transient caches. Do not copy the PETEY data root's settings, memory database,
gallery, local model downloads, `addon-data`, remote-access secret, TLS material,
or voice recordings into a minimum code backup.

To restore, copy `petey-desktop/` to a new checkout folder, create a Python 3.12+
environment, install `requirements.txt`, then copy each desired folder from
`addons/` into `<PETEY data root>/addons/`. Install each enabled add-on's own
requirements into the same PETEY environment, enable it in Manage Add-ons, and
restart PETEY. Verify `BACKUP_MANIFEST.sha256` before using the restored files.

## Runtime locations

External add-ons are installed as one folder each under:

```text
<PETEY data root>/addons/<addon-id>/
```

Their writable settings, credentials, caches, and proposals belong under:

```text
<PETEY data root>/addon-data/<addon-id>/
```

`PETEY_DATA_DIR` can override the platform data root. Never place credentials in a
manifest or source folder. Add-ons execute inside PETEY's process with the user's
filesystem and network permissions, so they are trusted local code.

## Host behavior

- Discovery reads a bounded `petey-addon.json` without importing disabled code.
- Enable/disable changes are saved immediately and applied after PETEY restarts.
- Update checks are explicit. Add-ons with a declared HTTPS GitHub `repository` can
  be updated from a validated ZIP asset on their latest release; writable
  `addon-data/<id>` is preserved and activation waits for restart.
- Core routes and databases exist before external `setup(context)` runs.
- Optional panel assets are served only from an enabled, successfully loaded
  add-on folder and cannot escape that folder. Their URLs change when the add-on's
  panel, script, or stylesheet changes so remote browser caches refresh.
- A returned object may expose `tool_specs()` and `close()`. PETEY namespaces tool
  names as `addon_<id>__<tool>` and closes add-ons before shared workers/runtimes.
- Enabled add-ons receive a bounded `emit_event()` channel for user-opted-in
  background updates. Event prompts stay hidden; PETEY's reply enters the selected
  chat, is delivered live only to the event's desktop or mobile surface, and optional
  speech respects that client's speaker mute state. Sanitized event
  metadata may attach one HTTPS image and optional external link to that reply.
  Direct user gestures may set `user_initiated=True` to retain the normal
  surface-authorized tool flow without showing the command in chat.
- Browser add-ons share camera and microphone ownership through
  `window.peteyMediaDevices`; `stop(owner)` releases owned tracks, and PETEY applies
  `stopAll()` on unload/restart as a final hardware guard. Recording add-ons use `window.peteyConferenceAudio`
  to yield and restore PETEY's ordinary continuous microphone instead of competing
  for the same input.
- Remote voice add-ons use `window.peteyVoiceSessions.suspend(addonId)` while their
  conversation is active and `release(addonId)` when it ends. PETEY pauses local
  microphone capture and automatic speech for the first owner, then restores the
  prior runtime state after the final owner releases it.
- Browser add-ons may pin bounded buttons, live panels, and transient notifications in the
  user-configurable Command Center rail through `window.peteyInterface`. Registration
  remains safe when the rail is hidden or disabled; PETEY shows the items if the user
  later enables the relevant rail section. Example:
  ```javascript
  const remove = window.peteyInterface.registerAction({
      addonId: 'weather', id: 'weather-open', label: 'Weather', icon: '☁', badge: '2',
      view: 'addon-weather',
  });
  const noticeId = window.peteyInterface.notify({
      id: 'weather-alert', title: 'Rain nearby', body: 'Expected in 20 minutes.',
      level: 'warning', view: 'addon-weather',
  });
  const removePanel = window.peteyInterface.registerPanel({
      addonId: 'weather', id: 'weather-current', title: 'Weather', icon: '☁',
      render(container) {
          container.textContent = '72° · Clear';
          return () => {}; // Optional cleanup for timers or listeners.
      },
  });
  // remove();
  // removePanel();
  // window.peteyInterface.dismissNotification(noticeId);
  ```
- Model tools stay unavailable until **Allow Petey to control** is enabled. The
  user grants Desktop, Mobile, and Discord separately, can disable
  individual capabilities, and can cap autonomous daily use of metered actions.
  Direct user requests may bypass only the daily limit.

## MCP connector rules

An MCP add-on must treat the server's advertised catalog as untrusted input. Keep
an explicit upstream-tool allowlist, sanitize schemas, bound results, use narrow
`available_when` intent gates, and expose `required_when` only for a safe,
unambiguous request that otherwise risks a false denial. Mutating, messaging,
payment, account, and administration operations need a concrete review proposal or
an explicit user-managed trust mode before dispatch.

`MCPStdioClient` is the shared client for local stdio servers. Remote Streamable
HTTP connectors own their authentication, origin validation, TLS policy, redirects,
token storage, timeouts, result bounds, and logout/revocation behavior. Pass secrets
through protected storage/environment, never command-line arguments or model-visible
descriptions.

## Change checklist

When changing the host contract:

1. Update discovery/validation in `petey/addons.py` and persistence in
   `petey/desktop_state.py`.
2. Update API/UI behavior in `web/desktop_app.py`, `web/templates/desktop_addons.html`,
   and `web/static/desktop.js`.
3. Update `docs/addons.md`, this file, `AGENTS.md`, and any affected example guide.
4. Extend `tests/test_addons.py`; add connector-local tests for tool allowlists,
   approvals, secret redaction, and cleanup.
5. Run focused tests, the full suite for runtime changes, and `git diff --check`.
6. Build a release package and confirm no external add-on manifest entered it.
