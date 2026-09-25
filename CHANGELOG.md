# Changelog

## v0.19.1 — 2026-09-25

- Removed the private PETEY GitHub repository link from the desktop sidebar footer.
- Hardened browser media cleanup so camera and microphone tracks are released on
  disconnect, page exit, and native restart; QtWebEngine helpers are reaped before
  process replacement to prevent capture spin loops and helper accumulation.

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
  and the core deAPI image generator, with separate Desktop, Mobile, Discord, and
  Petey Life grants.
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
