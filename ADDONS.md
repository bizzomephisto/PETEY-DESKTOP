# PETEY add-on map

This file is the repository-level index for PETEY's extension system. The complete
author contract is [`docs/addons.md`](docs/addons.md); the implementation in
`petey/addons.py`, `petey/tools/registry.py`, and `petey/mcp_client.py` remains the
source of truth.

## What ships

- Discord is PETEY's only built-in add-on and is enabled by default.
- Home Assistant, Blender, and every other connector are external installations.
- GitHub source releases contain no third-party or example add-ons. The packaging
  script rejects `examples/`, legacy add-on roots, external `petey-addon.json`
  files, `.env`, and symlinks.
- Local development examples may exist in the ignored `examples/addons/` folder;
  they are reference workspaces rather than release contents.

## Official external add-ons

- [Home Assistant MCP](https://github.com/bizzomephisto/PETEY-HOME-ASSISTANT) connects PETEY to Home Assistant's official Assist MCP endpoint.
- [Petey Life](https://github.com/bizzomephisto/PETEY-LIFE) provides an original editable pixel home driven by PETEY's active persona.

These projects use PETEY add-on API version `1` and publish their own installable
archives. Their source, releases, issues, and version histories stay in their own
repositories.

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
- Core routes and databases exist before external `setup(context)` runs.
- Optional panel assets are served only from an enabled, successfully loaded
  add-on folder and cannot escape that folder.
- A returned object may expose `tool_specs()` and `close()`. PETEY namespaces tool
  names as `addon_<id>__<tool>` and closes add-ons before shared workers/runtimes.
- Desktop chat can receive a loaded add-on's narrowly gated tools. Discord access
  is a separate per-add-on **Allow in Discord** permission, defaults off, takes
  effect immediately, and clears when the add-on is disabled.

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
