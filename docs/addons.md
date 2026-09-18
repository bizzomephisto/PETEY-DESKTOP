# PETEY Desktop add-ons

PETEY Desktop add-ons are local Python modules that can add API routes, background
services, and optional sidebar screens. The built-in Discord integration appears in
the same **Add-ons** manager, so people can choose whether PETEY loads it.

PETEY's GitHub releases bundle no external add-ons. Discord is the only built-in
integration. Third-party add-ons remain separate folders installed by the user.

Add-ons run inside PETEY's process with the same filesystem, network, settings, and
user permissions as PETEY. Install only code you trust. PETEY discovers manifests
without importing disabled add-ons. Enabling or disabling an add-on takes effect on
the next restart.

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

Do not hold provider keys longer than necessary or return them through an API. Use
`context.state.ai_provider` only when the add-on explicitly needs configured provider
access. Paid media work should go through `context.get_media_jobs()` so PETEY retains
queue limits, isolated provider clients, progress, shutdown, and Gallery capture.

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
the current shared client does not yet implement remote transports or OAuth.
