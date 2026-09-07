# Workspace and Tools

Workspace lets PETEY work with project folders that you explicitly approve.

## Approve a folder

Open **Workspace**, add a folder, and select it as the active workspace. PETEY's
built-in browser and editor resolve files within approved roots, including symlink
checks that prevent paths from escaping those roots.

Manual editor saves are separate from AI proposals.

## Proposed changes and commands

PETEY can propose file edits or shell commands. Review each proposal before approval:

- File changes show a diff and use a content hash to detect stale files.
- Commands remain inert until approved and stop after 60 seconds.
- Proposals expire rather than remaining indefinitely actionable.

Approved commands run with your operating-system user permissions. Workspace folder
approval constrains PETEY's built-in file operations; it is not an operating-system
sandbox for arbitrary shell commands.

## Filesystem MCP tool

The optional Filesystem connection is under **Settings → Tools** and requires Node.js
with `npx`. Enabling it is an explicit action and its first start may download the
pinned official filesystem server package.

The model receives only read, list, metadata, and search tools rooted in approved
Workspace folders. Write, move, delete, and arbitrary-command capabilities are not
offered through this connection. Opening Settings alone does not start the server.
