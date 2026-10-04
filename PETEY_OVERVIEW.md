# PETEY — Detailed Product and Technical Overview

Prepared September 22, 2026 for the v0.19 series and updated for **v0.21.0**. The earlier **v0.19.0-experimental.1** preview remains available. External add-ons have their own installation requirements and release histories.

## 1. What PETEY is

PETEY is a standalone desktop AI companion and assistant that brings conversation, customizable characters, persistent memory, voice interaction, creative media, and project tools into one application. It can serve as a general assistant, a roleplay character, a narrator, a game master, or a collaborator for writing and development.

The application runs on the user's computer and stores its settings, conversations, reference material, and generated gallery files locally. Users choose the services behind its AI capabilities: hosted providers such as Gemini and OpenAI, an OpenAI-compatible local model server, and deAPI for supported media operations.

PETEY's local storage and desktop interface do not imply that every operation runs offline. Hosted chat, embeddings, image inspection, transcription, speech, and media generation send the context needed for those operations to their configured providers. Chat, prompt enhancement, and image inspection follow the active chat provider; local image inspection requires a vision-capable local model. Other capabilities retain their own configuration.

Desktop and mobile access are two interfaces to the same running installation. Discord can participate through its own personality, room context, and explicitly selected memory policy. Optional add-ons extend PETEY into other applications and services.

## 2. Conversations and everyday interaction

### Saved chats and streaming replies

PETEY supports multiple named conversations, a visible conversation header, and a jump-to-latest control for long histories. Ordinary chat replies stream into the interface with progress and interruption handling. Tool-assisted response loops can remain buffered while tools complete.

The conversation pipeline combines the user's message with recent history, the effective character profile, relevant retrieved context, and available tools. Image attachments can be described through Gemini before their information is included in a reply. The final cleaned assistant response is stored in memory; incomplete streaming fragments do not become separate assistant memories.

Users can copy messages, request spoken playback of a reply, and enable automatic speech. Automatic playback can begin after the first complete streamed sentence, with subsequent speech queued behind it.

Links in assistant messages, including OpenCode artifact links, use the native bridge to request a new window in the operating system's default browser. Browser and mobile sessions use a new-tab link. The browser ultimately decides how to honor a new-window request.

### Temporary conversations

Temporary mode bypasses memory retrieval and memory writes, including image-generation memory records. The open interface supplies the current temporary conversation history. Providers and tools can still be used, so temporary mode is a storage choice rather than an offline mode.

### Quick PETEY

Quick PETEY is a compact popup positioned near the cursor. It supports chat, file and screenshot attachments, and push-to-talk. The launcher provides a direct `--quick` mode, and a COSMIC shortcut installer can bind it to Super+F1. Quick PETEY offers a lightweight entry point without requiring the full desktop app to remain in view.

## 3. Personality, character creation, and roleplay

PETEY's character system combines editable instructions, traits, communication controls, voice selection, delivery guidance, and speech-provider choice. Five saved Petey profile slots allow users to maintain distinct assistants or characters.

A saved conversation can be assigned to one profile. That chat then uses the profile's prompt and speech settings without replacing the installation's system-default personality. Unassigned chats inherit the system default. Removing an assigned profile returns affected chats to the fallback behavior.

Prior conversation text and retrieved memories provide factual context, while the selected profile remains authoritative for personality and speaking style. This helps prevent an old character's replies from defining a newly selected character.

Typical uses include:

- Separate characters or narrators for different stories and campaigns.
- A writing partner with a preferred level of detail and tone.
- A practical assistant with a concise conversational style.
- A game master supported by uploaded lore and character sheets.
- A voiced companion with persistent conversational continuity.

Discord chooses its saved profile independently of desktop chats. Its default room identity does not automatically inherit the system profile. Petey Life uses the system-default personality rather than a desktop conversation's profile assignment.

## 4. Memory and reference knowledge

### Persistent conversational memory

PETEY uses a local SQLite database for messages, document content, embeddings, and related metadata. Memory retrieval can bring relevant material from earlier conversations into a new exchange.

Messages retain their source surface, such as Desktop, Mobile, or Discord. Retrieved context includes source and time information. Selected results are ordered so recent explicit corrections can take precedence while older statements remain available as historical records.

Desktop and Mobile share the same installation's memory. Discord's participation is separately configurable.

### Knowledge files and retrieval

Users can upload reference documents, manage the knowledge collection, test retrieval, and rebuild embeddings. This retrieval-augmented generation workflow is useful for project notes, manuals, worldbuilding, character sheets, and other source material that should inform responses.

Embedding models are configured separately from chat models. Supported configuration paths include local and hosted embeddings. Changing the embedding provider, model, or vector dimensions may require rebuilding the stored index.

### Deletion choices

Deleting a conversation presents two distinct outcomes:

| Choice | Result |
| --- | --- |
| Delete chat, preserve memory | Removes the conversation from the chat list but keeps its messages available for retrieval. |
| Delete chat and memory | Removes the conversation and permanently deletes its associated message rows. |

Memory and privacy settings also expose storage inspection and removal controls. Temporary mode avoids adding new conversational memory but does not erase existing saved data.

## 5. Voice and visual interaction

### Listening modes

PETEY supports push-to-talk, always-on microphone input, and wake-name interaction. Completed recordings are sent to the selected transcription provider. deAPI is the default transcription path, with Gemini fallback support.

Wake-name mode combines a fast local detector with transcription fallback. A standalone wake name followed by a short pause can trigger a canned acknowledgement. Continued speech cancels the pending cue, helping avoid an interruption when a command begins with “Petey.”

Acknowledgement clips can be supplied per voice, with a default fallback. Users can adjust wake acknowledgement timing, silence-to-send behavior, and the follow-up listening period.

After a standalone wake starts a conversation, PETEY suppresses recording during its response and reopens a wake-free follow-up window after speech finishes. The configurable follow-up interval is 3–30 seconds, with an eight-second default.

### Spoken replies

Speech configuration is separate from the chat provider. PETEY includes Gemini streaming speech and OpenAI fallback paths, plus other configured speech paths supported by the application. A saved profile owns its voice, delivery instructions, and speech-provider selection; microphone behavior remains installation-wide.

Desktop automatic-speech changes persist. Mobile text chat begins muted on each page load; entering visual mode enables automatic speech for that session.

### Visual Mode

Visual Mode offers four audio-reactive neural-network views, spoken-reply captions, and fullscreen presentation. It is designed for voice-led interaction, character performance, and a less text-heavy companion experience. The phone interface provides direct visual fullscreen controls.

## 6. Media studio and gallery

PETEY includes a media studio backed by deAPI and a local gallery for completed outputs.

| Operation | Purpose |
| --- | --- |
| Generate image | Create an image from a text prompt. |
| Restyle image | Transform a supplied image with a prompt. |
| Generate video | Create video from a text prompt. |
| Animate image | Use an image as the starting point for video. |
| Restyle video | Apply a supported transformation to an input video. |
| Generate music | Create music using the supported model inputs. |
| Text to speech | Generate a speech asset. |
| Remove background | Extract an image subject from its background. |
| Upscale image | Increase image resolution through a supported model. |

Available models and valid parameters depend on the provider catalog and the operation. PETEY validates supported inputs and exposes relevant model limits.

Jobs run through a queue with three workers by default. The interface displays job progress and provider status; submission means a job is queued or running, not that generation has finished. Outputs are captured in the gallery, with preview, open, and save actions. FFmpeg supports browser-compatible video previews.

Media prompt drafts are retained per operation across restarts. A thumbnail browser helps select input images. Supported image and video operations can request price estimates without submitting a generation job; speech, music, and legacy video restyling do not have the same estimate path.

Conversational image generation is available through a model tool, subject to the relevant intent and capability controls. Transient chat speech can be kept outside the gallery.

## 7. Models and provider configuration

PETEY separates the configuration of chat, vision, embeddings, speech, and transcription.

| Capability | Configuration behavior |
| --- | --- |
| Chat | Gemini, OpenAI, or an OpenAI-compatible endpoint, including compatible LM Studio and Ollama setups. |
| Vision | Follows the active local, Gemini, or OpenAI chat model; the selected model must support image input. |
| Memory search | Independently selected embedding provider and model. |
| Speech | Profile-associated speech provider and voice, with speech model settings under Models & API keys. |
| Transcription | Separate microphone transcription settings, with deAPI and Gemini paths. |
| Creative media | deAPI model catalog, account balance, supported estimates, and generation jobs. |

Model dropdowns can refresh from Gemini, OpenAI, and local-server catalogs. A model appearing in a catalog does not guarantee that the configured account can generate with it; connection testing checks generation access.

Keys can be managed through the settings interface, with supported environment-variable fallbacks. Public settings responses redact secret values and expose key status instead.

## 8. Tools and coding assistance

### Read-only Filesystem MCP

An optional Filesystem MCP connector launches a pinned official server through `npx`. Its roots are folders chosen under Settings → Tools. PETEY offers only a bounded allowlist of reading, listing, metadata, and search capabilities to the model. Server write, move, delete, and arbitrary-command capabilities are not exposed.

Enabling the connector is explicit. Merely opening Settings does not start its process. The first enable may download the pinned server package.

### OpenCode integration in this local installation

The external OpenCode add-on starts `opencode run --format json` for a configured project, presents bounded live output, supports cancellation, and remembers recent project folders. Separate model capabilities start runs and check their status.

Users can direct PETEY to use OpenCode for a coding task and ask for progress. The integration provides authoritative run status and links to detected output artifacts. OpenCode's own permission rules remain active; the add-on does not pass `--auto`.

This is an independently installed extension with its own workflow and permission system.

## 9. Discord participation

Discord is the only built-in add-on and is enabled by default. Connecting a bot requires configuration and credentials; enablement alone does not connect an account.

The bridge uses Discord's REST API and Gateway for channel interaction, online presence, typing indicators, and reconnection. It supports a selected server and channel, optional startup auto-connect, editable room instructions, and a separately chosen Petey profile.

Conversation behavior includes direct mentions and replies, recognition of PETEY's name, watched topics, follow-up handling, and configurable pacing for spontaneous participation. Bot and webhook messages are ignored, and outgoing mentions are disabled.

Memory policy is explicit:

| Mode | Store new Discord messages | Let public Discord replies retrieve shared memory |
| --- | --- | --- |
| Room only, the default | No | No |
| Store Discord | Yes | No |
| Full shared memory | Yes | Yes |

Media slash commands submit work through the desktop media job manager and gallery. Supported owner administration requests—create a text channel, delete the selected channel, or clear a bounded number of recent messages—become review proposals. Public channel text cannot directly approve those operations.

## 10. Add-on architecture and integrations

External add-ons live under the application's data directory and are installed separately from PETEY source releases. Their manifests describe the extension without requiring disabled code to be imported. Enablement changes take effect after a restart.

An enabled extension can supply namespaced API routes, a sidebar panel and assets, services, model tools, and cleanup behavior. Add-ons run as trusted local code inside PETEY's process with the user's privileges.

Model control is a separate opt-in from installing or enabling an add-on. Compatible extensions expose individual capability grants and surface controls for Desktop, Mobile, Discord, and Petey Life. Metered capabilities can have daily autonomous-use limits. A direct user request can bypass an applicable daily limit, but it does not bypass the underlying grant.

Examples documented by the project or present in this local setup include:

| Extension | Role |
| --- | --- |
| Home Assistant MCP | Access exposed household entities and device controls through its configured review or trust workflow. |
| Petey Life | Give the system-default persona an editable pixel home with autonomous, directed, and build modes. |
| Blender MCP | Inspect scenes and objects and propose Python scripts for explicit review before execution in Blender. |
| OpenCode | Run coding tasks in a chosen project, inspect progress, cancel work, and open output artifacts. |

The local Blender integration limits model access to scene/object inspection and script proposals. Its README describes local socket communication and exact-code approval; broad upstream tools, asset downloads, and paid generation are not exposed through that integration.

Availability, dependencies, grants, and connection state vary by installation. Listing an integration here does not imply that it ships in every release or is currently enabled.

## 11. Desktop, browser, and phone access

PETEY normally runs a loopback-only local server inside a native pywebview window. Browser mode exposes the same application through a browser. Phone and remote access require explicit launch modes.

| Mode | Example command | Behavior |
| --- | --- | --- |
| Desktop | `python run_desktop.py` | Native window using a local loopback origin. |
| Browser | `python run_desktop.py --browser` | Open the local interface in a browser. |
| LAN | `python run_desktop.py --lan` | Explicit network binding protected by a private-link token. |
| LAN HTTPS | `python run_desktop.py --lan-https` | Local certificate setup and HTTPS for trusted phone microphone access. |
| Named Cloudflare tunnel | `python run_desktop.py --cloudflare --cloudflare-hostname meetpetey.com` | Open the desktop app while serving an existing tunnel's fixed local origin. |
| Quick popup | `python run_desktop.py --quick` | Compact desktop interaction near the cursor. |

The hostname above is the example used in this installation; other installations supply their own configured hostname. PETEY does not create or manage `cloudflared`. The named tunnel must already route to the appropriate origin port.

Cloudflare mode uses a durable private pairing token and exchanges it for an HttpOnly, SameSite, Secure cookie. The bare hostname remains blocked without PETEY authorization, even if an outer Cloudflare Access layer is absent. `--rotate-mobile-access` replaces the pairing secret and invalidates previously paired browsers.

The mobile layout focuses on chat, visual mode, and compact profile, voice, and microphone settings. Desktop-only views stay hidden at phone widths. Mobile connects to the desktop installation and its data rather than creating a separate memory store.

### Linux shortcuts

Run from the project directory using the intended Python environment:

```bash
# Install or update the normal PETEY launcher.
.venv/bin/python run_desktop.py --install-shortcut

# Install or update that launcher to start with the named tunnel configuration.
.venv/bin/python run_desktop.py --install-shortcut \
  --cloudflare --cloudflare-hostname meetpetey.com

# Install the COSMIC Quick PETEY keyboard shortcut.
.venv/bin/python run_desktop.py --install-quick-hotkey
```

The Cloudflare shortcut installer preserves the resolved hostname and port in the launcher command. Both regular and Cloudflare installation update the same PETEY application-menu entry.

## 12. Interface and settings

The interface uses a sidebar, feature views, and searchable settings organized into:

- Appearance & profile.
- Personality & voice.
- Microphone.
- Models & API keys.
- Tools & integrations.
- Knowledge files.
- Memory & privacy.

Appearance options include Midnight, Ocean, Forest, and Paper themes, interface scaling, collapsible navigation, and always-on-top behavior. A Help view contains feature guidance and direct links to relevant settings.

Profile settings keep personality and voice together. Provider credentials and model choices remain centralized, while installation-wide microphone behavior has its own page. Settings search indexes headings and labels rather than secret or user-entered field values.

## 13. Dormant PETEY Plus plan code

The repository retains a local plan builder with a monthly budget from $5 to $150 in $5 increments, Economy/Balanced/Premium quality choices, and an allocation mix across chat, images, video, and voice. It is hidden from navigation and excluded from the rendered app experience while the product direction is revisited.

This is a **planning preview**. Its implementation returns `checkout_available: False` and uses a local planning rate card. Displayed rollover and overage policies describe the proposed plan design; they do not establish an active subscription, funded balance, or live billing service. Provider-backed media price lookups are a separate feature.

## 14. Technical architecture

PETEY uses Python 3.12+, Flask/Werkzeug, pywebview, and vanilla HTML, CSS, and JavaScript. The frontend has no JavaScript build pipeline or `package.json` requirement.

The main request flow is:

```text
Native window or browser
        |
        v
Flask desktop API
        |
        +-- Assistant service --> selected model provider
        |         |
        |         +-- profile + recent history + memory retrieval
        |         +-- authorized model tools
        |
        +-- Media job manager --> media service --> deAPI
        |         +-- local gallery
        |
        +-- Desktop state + SQLite memory
        +-- approved folders + Filesystem MCP
        +-- Discord bridge + enabled external add-ons
```

Key implementation areas:

| Area | Main files |
| --- | --- |
| Launch, native bridge, shortcuts, and network modes | `run_desktop.py` |
| API composition and request validation | `web/desktop_app.py` |
| Conversation orchestration and provider clients | `petey/assistant.py`, `petey/ai_provider.py` |
| Settings, profiles, and conversation metadata | `petey/desktop_state.py` |
| SQLite storage and retrieval | `petey/desktop_memory.py` |
| Tool registration and capability dispatch | `petey/tools/registry.py`, `petey/tools/__init__.py` |
| Media validation, queue, provider calls, and gallery | `petey/media_service.py`, `petey/media_jobs.py`, `petey/deapi_client.py` |
| Read-only filesystem connection | `petey/mcp_client.py` |
| Add-on discovery and lifecycle | `petey/addons.py` |
| Discord | `petey/discord_bridge.py`, `petey/discord_transport.py`, `petey/discord_media.py` |
| Interface and settings catalog | `web/templates/desktop.html`, `web/static/desktop.js`, `web/static/desktop.css`, `web/settings_pages.py` |

JSON state uses locked temporary-file replacement. SQLite uses WAL and per-operation connections, with bounded background embedding work. Streaming responses use NDJSON events and heartbeats. Media requests and workers preserve explicit client and event-loop ownership. Native bridge methods supply OS-facing actions such as folder dialogs, external browser opening, and gallery file handling.

## 15. Local data and operational boundaries

Default data locations are:

| Platform | Default location |
| --- | --- |
| Linux | `$XDG_DATA_HOME/petey` or `~/.local/share/petey` |
| macOS | `~/Library/Application Support/Petey` |
| Windows | `%LOCALAPPDATA%/Petey` |

`PETEY_DATA_DIR` overrides the location. The directory can contain installation identity, settings, the SQLite memory database, gallery files, add-ons and their private state, wake acknowledgements, LAN certificates, and remote pairing information.

Important behavioral boundaries include:

- Default network access is loopback-only; broader access is explicit and token-protected.
- Public provider settings omit credential values.
- Temporary chat skips memory reads and writes but can still contact services.
- Tool grants are enforced both when exposing tools and when dispatching calls.
- Disabled external add-ons are not imported.
- Filesystem MCP remains read-only and rooted in approved folders.
- Shared Discord recall is an explicit choice because its output is public to the room.

## 16. Setup and development

The base setup uses a Python virtual environment and `requirements.txt`. Feature-specific requirements include FFmpeg for video previews, Node.js and `npx` for Filesystem MCP, OpenSSL for LAN HTTPS, and provider credentials or a compatible local server for the desired AI capabilities. External extensions have their own dependencies.

Tests use Python's `unittest`, mocked providers, temporary data roots, and Flask's test client. The full suite runs with:

```bash
python -m unittest discover -s tests -v
```

JavaScript syntax can be checked with Node when available. Voice, fullscreen, native-window, and mobile behaviors also need browser or native smoke checks; backend tests alone cannot establish those interactions.

Release packaging deliberately excludes private data, credentials, and external add-ons. Durable product constraints live in the manifest, and the repository's agent guide maps features to implementation and tests.

## 17. Further reading and source basis

This overview was assembled from local source and documentation rather than live provider catalogs or external product announcements.

- [README](README.md): installation, features, and launch guidance.
- [Product manifest](PETEY_MANIFEST.md): durable product and runtime constraints.
- [Add-on map](ADDONS.md): bundled versus external integrations.
- [Add-on author contract](docs/addons.md): extension APIs and lifecycle.
- [Discord guide](docs/discord.md): configuration, participation, memory, and administration.
- [Memory, knowledge, and privacy](docs/wiki/Memory-Knowledge-and-Privacy.md).
- [Tools and integrations](docs/wiki/Tools-and-Integrations.md).
- [Mobile and remote access](docs/wiki/Mobile-and-Remote-Access.md).
- [Interface design](docs/interface-design.md).

The OpenCode and Blender descriptions also draw on their installed add-on READMEs and, for OpenCode's run tools and artifacts, its local implementation. Those add-on files are outside the core repository and are not bundled with this overview.
