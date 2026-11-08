# Tools and Integrations

## Visible web browser

Open **Settings → Tools & integrations → Web browser** and turn on **Let Petey
browse the web**. PETEY opens a separate browser window on its host computer,
including when you request a search from mobile chat. The feature starts off.
Update the Python dependencies and use **Install Chromium** if needed. See the
[web browser guide](https://github.com/bizzomephisto/PETEY-DESKTOP/blob/main/docs/web-browser.md)
for setup and the supported actions.

## Read-only Filesystem connector

The optional Filesystem connection is under **Settings → Tools & integrations**.
Choose **Add folder** there to grant access to specific folders. Removing a folder
revokes that access without deleting anything from disk.

Filesystem requires Node.js with `npx`. Enabling it is an explicit action, and its
first start may download the pinned official filesystem server package. Merely
opening Settings does not start the server.

PETEY receives only read, list, metadata, and search tools rooted in the folders
you approved. Write, move, delete, and arbitrary command capabilities are not
offered through this connection.

## Add-ons

Add-ons provide optional integrations and may expose their own settings, panels,
or model tools. Install only add-ons you trust because enabled add-ons run as local
code with PETEY's permissions. Add-on enablement takes effect after PETEY restarts.
