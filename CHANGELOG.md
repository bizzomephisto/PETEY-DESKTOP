# Changelog

## v0.21.0 — 2026-10-03

- Wired the desktop workspace around Chat, Create, Gallery, Tasks, and Addons.
  Addons opens the manager directly; each addon can be pinned to the sidebar.
  Chat expands the saved-chat list and closes it after selection.
- Added shared media-player space in the right rail and kept the composer
  available across desktop pages. Improved Command Console theme alignment,
  mobile settings, and the sidebar Settings icon and version placement.
- Added optional general MCP connections with local stdio and remote HTTP
  transports, selected tools, per-surface grants, and local credential storage.
- Improved conversational tool selection and literal handling of short replies.
- Added the Android companion API, local memory retrieval improvements,
  Synapse Network visuals, and an optional bundled 3D visualizer experiment.
- Expanded Create with reference-to-video generation and model dimension limits,
  and added configurable personality-wizard presets.
- Includes the Tasks scheduling and changelog features described in v0.20.0.

## v0.20.0 — 2026-09-27

- Chat messages now show their date and time on hover; Copy and clipboard image/file attachments work in the desktop window.
- Added Tasks as a built-in PETEY add-on. Task Manager combines reviewed actions
  from enabled add-ons, including Home Assistant lights, Spotify tracks, and Webcam
  snapshots. It supports one-time, daily, selected weekday, and monthly schedules.
  Tasks can be paused, edited, run immediately, or deleted; upcoming tasks can
  appear in the Command Center rail.
- Added a scheduled snapshot action to PETEY Webcam. It captures a fresh frame
  from a named, armed camera and attaches the saved image to PETEY's announcement.
  PETEY and the camera source must be running when the task is due.
- Moved the active chat's profile selector into its header and condensed core
  Controls into a fixed icon row. Theme, microphone mode, and restart choices
  expand in place; the sidebar and rail controls remain easy to find.
- Improved retrieval of older, exact-match memories and corrected the rail
  customization controls so visibility changes persist.
- Made the sidebar version open this changelog. New release notes appear once
  on the first app open after an update and remain available from the version.

## v0.19.3 — 2026-09-27

- Kept the Command Center hamburger in one fixed position. It toggles the
  right-hand rail, or opens the core Controls menu when that rail is disabled.
  The rail now resizes the workspace, and the expanded sidebar shows a larger
  PETEY logo.
- Let compatible add-ons own a remote voice session without simultaneous local
  microphone capture or automatic local speech. Typed Discord `petey play` and
  `petey queue` commands now go to the Discord Voice DJ without a duplicate
  chat-model reply.
- Routed image attachment inspection through the active chat provider and model,
  including vision-capable local models, and clarified provider boundaries in
  PETEY's local-first guidance.
- Added the PETEY and optional add-on update manager, plus independent add-on
  repository links and clearer instructions for add-ons without releases.
- Includes the v0.19.1 changes below, which were committed but did not receive
  a separate GitHub release.

## v0.19.1 — 2026-09-25

- Removed the private PETEY GitHub repository link from the desktop sidebar footer.
- Hardened browser media cleanup so camera and microphone tracks are released on
  disconnect, page exit, and native restart; QtWebEngine helpers are reaped before
  process replacement to prevent capture spin loops and helper accumulation.
- Fixed native window-size persistence when Qt reports a maximized resize before
  its maximize event; close and restart now retain the last normal dimensions.
- Replaced the collapsed Command Center rail tab with a compact upper-right menu
  button and moved the deAPI credit from the sidebar into the Media page heading.
- Cleared the desktop chat header by moving chat controls into the open Command
  Center drawer and adding a separate composer-side fallback dock for add-on status.
- Added per-add-on display switches for badges and Command Center interface controls;
  changes apply immediately without disabling or restarting the add-on.

- Made the mobile voice method a per-phone preference. Selecting Push to talk keeps
  microphone capture closed while idle, preventing fake-call behavior on some car stereos,
  without changing desktop wake-name or open-mic settings.
- Removed the Workspace IDE, editor, command runner, proposal APIs, and navigation.
- Moved read-only Filesystem folder approvals into Settings → Tools & integrations,
  including automatic migration of previously approved folders.
- Hid PETEY Plus from the rendered app and navigation while retaining its dormant
  implementation for future product work.
- Moved saved Petey profiles to the top of Personality & voice. Saving an edited
  profile now asks for a destination slot and activates the saved result.
- Persisted microphone and speaker mute states across restarts and made chat,
  Visual Mode, desktop, and mobile use the same saved state.
- Exposed the current speaker-enabled state to add-on panels so their own spoken
  cues follow PETEY's global speaker mute.
- Updated PETEY Conference Mode with fast local wake-name detection, silence-ended
  transcription segments, permission before topic-triggered contributions, common
  yes/no replies, and a three-second conversational follow-up window.
- Conference permission cue folders now accept any number of recordings, choose
  one randomly, and derive matching transcript text from each clip filename.
- Split microphone transcription into explicit Automatic, deAPI-only, Gemini-only,
  and Local Whisper choices.
- Added optional, fully private Local Whisper transcription through faster-whisper,
  with explicit model downloads, CPU/CUDA selection, setup links, and Conference support.
- Added Linux startup discovery for pip-installed NVIDIA CUDA libraries so Local
  Whisper can use the GPU without a system-wide CUDA installation.
- Made the wake name interrupt active PETEY speech immediately, play a random
  user-replaceable interruption cue, and return to listening.
- Fixed Media text-to-speech with explicit deAPI Media and Gemini choices, each
  with the correct models and voices independently from PETEY's conversational
  voice, and show complete job errors.
- Added deAPI as a conversational speech provider with profile-aware model and
  voice settings across desktop, mobile, chat, Visual Mode, and wake cues.
- Reordered Media text-to-speech controls so provider comes before its model,
  labeled Gemini and deAPI models clearly, and persisted the selected provider.

## v0.19.0 — 2026-09-23

This stable release promotes the v0.19 experimental preview and includes all of
its capabilities. The `v0.19.0-experimental.1` tag and prerelease remain available
for existing testers.

### Faster, clearer conversations

- Streamlined memory retrieval with a smaller vector cache, fewer database reads,
  and correction-aware context that works consistently across desktop and mobile.
- Added strict grounding rules so Petey states when live data, memory, or an
  integration is unavailable instead of inventing an answer.
- Reduced wake-name acknowledgement and silence-detection delays while preserving
  the no-interruption path for commands that begin with “Petey.”
- Combined initial messages, voice cues, and preferences into the startup payload
  and batched chat rendering for faster startup and saved-chat switching.

### Desktop and mobile interface

- Reworked desktop navigation, chat controls, composer actions, and the responsive
  mobile dock to keep infrequently used controls out of the conversation area.
- Added removable pending attachments and kept attachment and push-to-talk actions
  available on mobile. A quick microphone tap toggles mute; holding records.
- Rebuilt all six Visual Mode scenes as reactive animations on a black background,
  with orange listening, blue speaking, and live audio-driven movement.
- Fixed duplicate mobile responses and made automatic replies, add-on announcements,
  and wake acknowledgements consistently respect the active speaker mute state.

### Add-ons and tools

- Added an opt-in add-on event channel so integrations can send hidden updates to
  Petey, receive a normal chat response, and request speech without exposing their
  internal prompt in the feed.
- Added secure native downloads for files created inside an add-on's private data
  directory, supporting conference transcripts and recordings.
- Hardened Gemini tool declarations and tool argument validation, including empty
  parameter sets and list-valued arguments used by spreadsheet integrations.
- Added immutable revisioned asset caching for the core interface and independent
  cache revisions for installed add-ons.

### Documentation

- Added permanent Cloudflare Tunnel setup, Home Assistant alert relay, and retained
  experimental-install guides.

## v0.19.0-experimental.1 — 2026-09-22

This prerelease is published for testing. **v0.18.2 remains the stable release.**

### Mobile security

- Added a durable private pairing link for named Cloudflare access. Paired phones
  stay authorized across PETEY restarts with a one-year Secure, HttpOnly cookie;
  the bare public hostname returns `401`.
- Added `--rotate-mobile-access` to replace the pairing secret and revoke every
  previously paired browser.

### Add-on control

- Added off-by-default **Allow Petey to control** policies for compatible add-ons
  and the core deAPI image generator, with separate Desktop, Mobile, and Discord grants.
- Added per-capability controls, current-day usage, and autonomous daily limits.
  Explicit user requests bypass the daily allowance while still respecting every
  enablement, surface, and capability permission.
- Normalized add-on function schemas for Gemini so autonomous capabilities cannot
  break ordinary chat with unsupported JSON Schema keywords.
- Show Petey-requested image generations as live progress cards in the chat feed,
  replacing each card with the finished Gallery image when it completes.

### Conversations

- Added per-chat saved Petey profile assignments with a system-persona fallback.
  The effective profile supplies both instructions and speech voice without
  replacing the global persona.
- Added the persona picker to the chat header and new-chat dialog so assignments
  are visible and editable without opening Settings.
- Added a jump-to-latest button that appears when a reader scrolls away from the
  newest chat messages.

### Mobile and voice

- Refined mobile chat and Visual Mode with compact controls, a collapsible action
  row, higher captions that fade after five seconds, clearer mute states, and a
  smaller composer that preserves touch targets.
- Added wake-free follow-up turns after a standalone wake name, with configurable
  acknowledgement, silence-to-send, and follow-up timing.
- Kept automatic speech as a per-device behavior and stopped speech from reading
  OpenCode artifact filenames.

### Memory and Discord

- Added source-surface metadata to saved messages and correction-aware retrieval,
  keeping newer user corrections authoritative while retaining older context.
- Added an explicit choice to permanently delete a chat's messages or preserve
  them as searchable memory.
- Added Discord memory policies for room-only operation, storing Discord messages,
  or explicitly sharing cross-surface memory, plus per-surface Petey identity.

### Desktop and remote access

- Added secure, durable Cloudflare pairing links, restart preservation for tunnel
  settings, and launcher persistence for the configured hostname and port.
- Open external chat links in the operating system browser and generated Gallery
  images in the operating system viewer; normalize loopback artifact links for
  paired mobile browsers.
- Added per-add-on asset cache revisions so updated external panels refresh through
  browser and tunnel caches.

### Documentation

- Added a detailed PETEY architecture and product overview in `PETEY_OVERVIEW.md`.

## v0.18.2 — 2026-09-19

### Wake-name conversation

- Delayed canned wake acknowledgements briefly and cancel them when speech
  continues, so “Petey” followed by a pause gets a response while commands such
  as “Petey, turn off the lights” proceed without an interruption.

## v0.18.1 — 2026-09-19

### Voice profile fixes

- Kept automatic spoken replies as a device behavior when switching saved Petey
  profiles, so a profile saved with auto-speak off cannot unexpectedly silence
  another active voice.
- Mobile voice settings now enable spoken replies when saving an enabled voice.
- Applied each profile's wake acknowledgement catalog together with its voice,
  stopping stale clips and cache-busting replaced files so the current voice
  folder takes effect immediately.

## v0.18.0 — 2026-09-19

### Mobile and remote access

- Rebuilt the phone layout around chat and visual mode with touch-sized controls,
  safe-area spacing, a compact essentials-only settings sheet, and a direct
  fullscreen control.
- Added saved Petey profile selection to the mobile settings sheet.
- Added trusted local HTTPS with a reusable private certificate authority for phone
  microphone access on a local network.
- Added named Cloudflare Tunnel mode with a fixed loopback origin, custom hostname
  and port settings, IPv4/IPv6 localhost support, and Linux launcher integration.
- Added a complete remote-access guide for stable custom-domain tunnels, free
  temporary TryCloudflare URLs, phone home-screen shortcuts, access protection, and
  troubleshooting.

### Voice

- Unified Petey profiles so one save and one profile slot contain instructions,
  traits, communication style, voice, delivery, and speech provider. Loading a
  profile now activates the complete profile immediately.
- Added a local wake-name detector so “Petey” and “Hey Petey” can be acknowledged
  before cloud transcription finishes.
- Added replaceable wake acknowledgement clips with per-voice and default fallback
  folders, randomized playback, and built-in spoken fallbacks.
- Prevented delayed wake detections and active acknowledgement clips from talking
  over PETEY's spoken reply.
- Pre-created cue folders for every supported Gemini voice and added native folder
  access from Microphone settings.
- Improved mobile audio unlocking, Gemini speech streaming playback, voice-activity
  timing, and visual-mode push-to-talk placement.

### Add-ons and Discord

- Added a separate **Allow in Discord** permission for each external add-on's model
  commands. Permissions default off and clear when the add-on is disabled.
- Added required tool selection for narrowly matched add-on commands, including
  Gemini and OpenAI-compatible providers.
- Isolated Discord's room identity from the desktop personality so its saved room
  prompt is the complete Discord persona.

### Packaging

- Updated release metadata and source packaging for v0.18.0. Source releases still
  include only PETEY's built-in Discord integration; external add-ons and private
  configuration remain excluded.

## v0.17.0 — 2026-09-18

This release combines the feature work completed after v0.14.0. No intermediate
v0.15.0 or v0.16.0 artifacts were published.

### Discord

- Added the built-in Discord bot bridge with official REST and Gateway connections,
  online presence, native typing, bounded room context, adaptive participation,
  watched topics, owner instructions, and startup auto-connect.
- Added an editable room prompt with AI-assisted drafting and persistent pacing.
- Added reviewable channel creation, selected-channel deletion, and recent-message
  cleanup. Public channel text cannot authorize administrative actions.
- Added deAPI media slash commands backed by PETEY's existing queue and Gallery.

### Add-ons and tools

- Added a restart-gated local add-on manager with manifest-only discovery for
  disabled modules, namespaced API/assets, dedicated writable data directories,
  lifecycle cleanup, optional sidebar panels, and namespaced conversational tools.
- Extended the shared stdio MCP client with per-connection environments and working
  directories while preserving the Filesystem connector's read-only allowlist.
- GitHub releases bundle only the built-in Discord integration. External and local
  development add-ons are deliberately excluded.

### Chat and models

- Added NDJSON chat streaming with status events, incremental text, heartbeats,
  interrupted-response handling, and final-only assistant memory writes.
- Added Gemini and OpenAI-compatible tool-call loops with duplicate-call protection.
- Added live model catalogs for Gemini, OpenAI, and local servers, including stale
  request protection and automatic refresh when provider settings change.
- Synchronized Gemini vision with the selected Gemini chat model while retaining
  Gemini vision for image descriptions used by other chat providers.

### Interface and desktop

- Rebuilt Settings around a catalog-driven overview, grouped navigation, uniform
  page shells, section links, safe cross-page search, save guidance, and compact
  layouts that retain search access.
- Added Quick PETEY at the pointer with screenshot, file, chat, and push-to-talk
  controls plus the COSMIC Super+F1 installer.
- Added PETEY Plus plan previews with contribution, capability mix, rollover, and
  live usage estimates.
- Added native add-on folder and restart controls, Discord navigation, and expanded
  Help guidance.

### Validation and compatibility

- Existing settings migrate through validated defaults; keys remain redacted from
  public APIs. The loopback-only server, temporary-chat memory rules, workspace
  approval gates, and media runtime ownership remain unchanged.
- Added focused coverage for streaming, tools, add-ons, Discord transport/media,
  launcher behavior, settings structure, and persistent state.

## v0.14.0 — 2026-09-06

- Established the standalone PETEY Desktop baseline with chat, memory, knowledge,
  media, voice, visual mode, Workspace, provider settings, and desktop packaging.
