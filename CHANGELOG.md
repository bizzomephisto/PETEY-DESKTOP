# Changelog

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
