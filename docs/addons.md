# PETEY Desktop add-ons

For the repository-level map and release boundary, see [`../ADDONS.md`](../ADDONS.md).
For cross-system product and runtime invariants, see
[`../PETEY_MANIFEST.md`](../PETEY_MANIFEST.md).

PETEY Desktop add-ons are local Python modules that can add API routes, background
services, and optional sidebar screens. The built-in Discord integration appears in
the same **Add-ons** manager, so people can choose whether PETEY loads it.

PETEY's GitHub releases bundle no external add-ons. Discord is the only built-in
integration. Third-party add-ons remain separate folders installed by the user.
`scripts/package_release.py` enforces this boundary by rejecting `examples/`, known
legacy add-on roots, external `petey-addon.json` files, `.env`, and symlinks.

Official external add-ons are released independently:

- [Home Assistant MCP](https://github.com/bizzomephisto/PETEY-HOME-ASSISTANT)
- [Petey Life](https://github.com/bizzomephisto/PETEY-LIFE)

Petey Life reads `DesktopState.system_prompt`, so its simulation always uses the
system-default Petey profile and never the persona assigned to the active chat or
Discord. Its decision prompt explicitly identifies the current surface as Petey Life.

Add-ons run inside PETEY's process with the same filesystem, network, settings, and
user permissions as PETEY. Install only code you trust. PETEY discovers manifests
without importing disabled add-ons. Enabling or disabling an add-on takes effect on
the next restart.

Model commands contributed by an external add-on remain unavailable until the user
turns on **Allow Petey to control**. The user can independently allow Desktop,
Mobile, Discord, and Petey Life, disable individual capabilities, and set autonomous
daily limits for metered capabilities. These policy changes take effect immediately.
The add-on remains responsible for its own approval or trust policy for consequential
commands.

The public add-on status includes desired `enabled` state, actual `loaded` state,
`restart_required`, a bounded load error, whether model tools are present, and the
sanitized model-control policy and current-day usage. Never add secrets or private
configuration values to that projection.

## Install an add-on

1. Open **Add-ons** in PETEY and choose **Open add-ons folder**.
2. Copy the add-on's whole folder into that directory. Each add-on gets one folder.
3. Return to **Add-ons**, enable it, and restart PETEY.

Use **Restart PETEY** on the Add-ons screen to apply changes immediately in the
native desktop app. In browser development mode, stop and rerun the launch command.

PETEY stores each add-on's writable data separately under `addon-data/<addon-id>`
in the PETEY data directory. Keep add-on source and dependencies outside the PETEY
repository so source releases remain independent of third-party code.

## Folder contract

```text
my-addon/
├── petey-addon.json
├── addon.py
├── panel.html       # optional
├── panel.js         # optional
└── panel.css        # optional
```

`petey-addon.json`:

```json
{
  "api_version": 1,
  "id": "my-addon",
  "name": "My add-on",
  "version": "0.1.0",
  "description": "A local PETEY Desktop add-on.",
  "entrypoint": "addon.py",
  "panel": "panel.html",
  "script": "panel.js",
  "stylesheet": "panel.css",
  "navigation": {"label": "My add-on", "icon": "◇"}
}
```

The manifest is limited to 64 KB. `api_version` must be `1`. IDs use lowercase
letters, numbers, hyphens, and underscores and must remain stable across releases.
All file paths are relative to the add-on folder and cannot contain `..`. Omit
`panel`, `script`, `stylesheet`, and `navigation` for a background/API-only add-on.
Set `default_enabled` to `true` only for an add-on distributed as part of a controlled
installation; user add-ons should normally require an explicit toggle.

## Python entrypoint

The entrypoint must define `setup(context)`. It may register uniquely named Flask
routes and start services. Return an object with `close()` when cleanup is needed.
The entrypoint is loaded as a private Python package, so larger add-ons can use
relative imports such as `from .client import Client` for sibling modules.

```python
from flask import jsonify


class Addon:
    def close(self):
        pass


def setup(context):
    def status():
        return jsonify({"ok": True})

    context.app.add_url_rule(
        "/api/addons/my-addon/status",
        endpoint="addon_my_addon_status",
        view_func=status,
    )
    return Addon()
```

Use `/api/addons/<your-id>/...` for routes and prefix Flask endpoint names with the
add-on ID. Core PETEY routes are registered first and must not be replaced.

`context` exposes:

| Attribute | Purpose |
| --- | --- |
| `app` | Flask application for route registration |
| `state` | `DesktopState`; persistent PETEY settings and installation identity |
| `memory` | Desktop memory/search service |
| `gallery` | Local generated-media gallery |
| `runtime` | Helper for bounded asynchronous calls |
| `get_media_jobs` | Lazily returns the shared `MediaJobManager` |
| `addon_id` | Stable ID from the manifest |
| `addon_dir` | Read-only-by-convention installed module folder |
| `data_dir` | Dedicated writable data folder for the add-on |
| `emit_event` | Queue an opt-in hidden event for PETEY to answer in chat |

Do not hold provider keys longer than necessary or return them through an API. Use
`context.state.ai_provider` only when the add-on explicitly needs configured provider
access. Paid media work should go through `context.get_media_jobs()` so PETEY retains
queue limits, isolated provider clients, progress, shutdown, and Gallery capture.

### Hidden add-on events

An add-on may react to an external state change without fabricating a visible user
message. Call `context.emit_event()` only after the user enables that behavior in
the add-on. PETEY processes events serially on a bounded queue, hides the event
prompt, saves the assistant response to the selected conversation, and delivers it
to connected desktop and mobile clients.

```python
context.emit_event(
    "Playback changed to So What by Miles Davis. Announce it briefly.",
    speak=True,
    metadata={"track_uri": "spotify:track:example"},
)
```

For a command triggered by a direct button press or equivalent current user gesture,
pass `user_initiated=True`. PETEY then treats the hidden text as the user's current
instruction and makes the normally authorized tools for that surface available. Do
not set this flag for timers, webhooks, device changes, or other autonomous events.

`conversation_id` defaults to the active conversation at emission time. `surface`
may be `petey_desktop` or `mobile_petey`. `speak=True` requests automatic speech,
but the browser still respects its speaker mute control. Scalar `metadata` is saved
on both the hidden event and visible reply so the originating add-on can correlate
the completed response, and the published browser event carries the same sanitized
fields. An add-on may render one HTTPS image beneath the visible reply with
`chat_image_url`, plus optional `chat_image_link`, `chat_image_alt`, and
`chat_image_caption` strings. Keep events under 5,000
characters, avoid secrets, suppress repeats at the source, and provide a disabled-
by-default user toggle because each event can invoke the configured chat provider.

## Sidebar panels and browser assets

Panel HTML is inserted inside `<section id="view-addon-<id>">`. Add-on JavaScript
can listen for navigation without changing PETEY's main script:

```javascript
window.addEventListener('petey:view', event => {
    if (event.detail.view === 'addon-my-addon') {
        // Refresh the panel.
    }
});
```

Scripts and styles are served only for enabled, successfully loaded add-ons from
`/api/desktop/addons/<id>/assets/...`. Keep DOM IDs globally unique by prefixing them
with the add-on ID. Use `textContent` for external values and validate every API
argument server-side.
Asset URLs include a revision derived from the add-on's panel, script, and stylesheet
modification times so browser and tunnel caches refresh after those files change.

### Camera and microphone ownership

Use `window.peteyMediaDevices` when a panel opens browser media hardware. Register a
stream with an add-on-specific owner ID and release that lease before stopping or
discarding the stream. A consumer may clone a camera from `findShareable('video')`;
it must stop only its clone. The original owner remains responsible for its stream.

Long-running recording modes should call `await window.peteyConferenceAudio.prepare()`
before opening their microphone and `release()` when finished. This pauses and later
restores PETEY's continuous wake/open-mic capture. Listen for `petey:voice-playback`
to exclude PETEY's own speech from live transcription while leaving the archive
recording intact.

An add-on that plays its own optional spoken cue can check
`window.peteyAudioControls.speakerEnabled()` first. This reflects PETEY's persisted
speaker mute and disabled speech-provider state. Add-on cues must obey it.

### Downloading add-on files

Normal browsers can download a same-origin add-on API response with an `<a>` link.
PETEY's native window exposes
`window.pywebview.api.download_addon_file(addonId, relativePath)` for a native Save
As dialog. The path is restricted to `addon-data/<addonId>/`; use the browser link
as the fallback when that API is absent.

## Lifecycle and compatibility

- Discovery reads manifests at startup. Disabled add-on Python is not imported.
- `setup(context)` runs once after core routes and databases are ready.
- PETEY calls `close()` during desktop shutdown.
- Route and panel changes require a restart; runtime hot loading is intentionally
  unsupported.
- Add-ons must bound uploads, queues, network timeouts, stored data, and background
  threads. A shutdown hook should signal and join owned workers.
- Pin any extra Python dependencies in the add-on's installation instructions. Do
  not install packages automatically from `setup()`.

Test with a temporary `PETEY_DATA_DIR` so development never touches real user
settings or memory. `tests/test_addons.py` covers the host-side lifecycle contract.

## Connecting an MCP server

An add-on can expose model tools by returning an object whose `tool_specs()` method
returns `petey.tools.registry.ToolSpec` objects. PETEY namespaces every contributed
name as `addon_<id>__<tool>` to prevent collisions. `available_when` should narrowly
match user intent so a paid, private, or mutating tool is not offered unnecessarily.
Every contributed tool is wrapped by PETEY's host policy. It is offered only when
the add-on's master control, capability, and current surface are enabled. Other
desktop tools and the filesystem MCP are not included by an add-on permission.

Describe a controllable capability directly on `ToolSpec`:

```python
ToolSpec(
    name="create_report",
    description="Create a report from the current data.",
    parameters={"type": "object", "properties": {}},
    handler=create_report,
    available_when=lambda message: "report" in message.casefold(),
    explicit_when=lambda message: "create" in message.casefold(),
    control_capability="create_report",
    control_label="Create reports",
    metered=True,
    default_daily_limit=3,
)
```

Tools with the same `control_capability` share one permission and usage counter.
`explicit_when` identifies a direct user request. A direct request may exceed the
autonomous daily limit, but it never bypasses a disabled add-on, master control,
surface, or capability. The host increments metered usage immediately before an
autonomous dispatch. Keep `explicit_when` narrow enough that casual mentions do not
become paid or consequential actions.

For a narrowly matched request where an optional model decision would create a false
denial, a `ToolSpec` may set `required_when`. PETEY then requires one tool call on the
first provider round and returns to automatic tool selection for the final response:

```python
ToolSpec(
    name="get_live_status",
    description="Read current status.",
    parameters={"type": "object", "properties": {}},
    handler=read_status,
    available_when=lambda message: "status" in message.casefold(),
    required_when=lambda message: "status" in message.casefold(),
)
```

Keep `required_when` at its default `False` for tools that are broadly available or
consequential. Its predicate should be at least as narrow as `available_when`.

A successful tool result can render one image beneath PETEY's visible reply by
returning `chat_image_url`, with optional `chat_image_alt`, `chat_image_caption`,
and `chat_image_link` strings. Use a same-origin add-on route or HTTPS URL. Tool
events are saved with the reply, so the URL must remain valid when the conversation
is reopened. Keep local image storage bounded and serve private data only through
PETEY's token-gated origin.

Local stdio MCP add-ons can reuse `petey.mcp_client.MCPStdioClient`:

```python
import re
from petey.mcp_client import MCPStdioClient
from petey.tools.registry import ToolSpec

ALLOWED_TOOLS = {"search_issues", "get_issue"}
ISSUE_INTENT = re.compile(r"\b(issue|bug|ticket|repository)\b", re.I)


class IssueMCP:
    def __init__(self, context):
        # Read a token from the add-on's own protected configuration. Pass secrets
        # through env, never command-line arguments or tool descriptions.
        token = (context.data_dir / "token").read_text().strip()
        self.client = MCPStdioClient(
            ["npx", "-y", "@vendor/issue-mcp@1.2.3"],
            roots=[],
            env={"ISSUE_SERVICE_TOKEN": token},
        )
        self._specs = None

    def tool_specs(self):
        if self._specs is not None:
            return self._specs
        specs = []
        for tool in self.client.list_tools():
            name = str(tool.get("name") or "")
            if name not in ALLOWED_TOOLS:
                continue
            schema = tool.get("inputSchema") or {"type": "object", "properties": {}}
            specs.append(ToolSpec(
                name=name,
                description=str(tool.get("description") or name),
                parameters=schema,
                handler=lambda arguments, selected=name: {
                    "result": self.client.call_tool(selected, arguments)
                },
                available_when=lambda message: bool(ISSUE_INTENT.search(message)),
            ))
        self._specs = specs
        return list(self._specs)

    def close(self):
        self.client.close()


def setup(context):
    return IssueMCP(context)
```

Use a pinned package version, an explicit tool allowlist, bounded result sizes, and
the narrowest credentials the service supports. Do not automatically expose every
tool returned by `tools/list`: MCP servers may include write, delete, payment, or
administration operations. Add-ons that intentionally expose consequential actions
should implement a review/approval UI before dispatch.

`MCPStdioClient` supports stdio servers, connection-specific environment variables,
working directories, roots, timeouts, and lifecycle cleanup. A remote Streamable HTTP
MCP can implement the same `tool_specs()` contract with its own authenticated client;
the current shared client does not yet implement remote transports or OAuth. Such an
add-on owns strict origin validation, TLS policy, redirect refusal or validation,
protected token storage, refresh/logout behavior, bounded timeouts and responses,
and clear disclosure of data sent to the remote service.

## Release boundary

External add-ons must be distributed and versioned separately from PETEY core. Do
not place an enabled user's add-on folder, token, generated configuration, or
`addon-data/` contents in this repository. Local ignored examples are useful during
development, but a release ZIP must contain Discord only. Run the packaging script
as part of release validation; do not bypass its external-manifest check.

Add-ons do not choose PETEY's bind address or authentication. Normal startup and
Cloudflare origins are loopback; explicit LAN modes remain owned by the launcher.
