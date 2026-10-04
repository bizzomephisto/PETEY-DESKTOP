# Direct MCP connections

PETEY can use MCP tool servers directly. You do not need a separate PETEY add-on
for each server. Sites such as [mcp.so](https://mcp.so/) list independent servers;
use the selected server's installation instructions and configuration.

After restarting PETEY, open **Settings → Tools & integrations → MCP servers**.

1. Expand **Import server configuration** and paste the server's `mcpServers` JSON.
2. Click **Import configuration**. Imported servers are off, with no tool grants.
3. Click **Test connection**. This launches a local command or contacts the endpoint
   and discovers its tools. Local commands may download packages if their arguments
   request it; review the command and follow the server's installation instructions.
4. Select the tools PETEY may use. Selected tools may make changes if the server
   supports them; tool annotations are server hints, not a permission boundary.
5. Enter **Chat keywords**, separated by commas, such as `calendar, appointment`.
   Without keywords, PETEY offers the tools when you mention the server's name.
   This applies to each request, including follow-up requests.
6. Choose chat surfaces, check **Let Petey use selected tools**, and click
   **Save settings**. Desktop and mobile are the initial surface choices;
   Discord is off initially.
7. Ask PETEY for an action using a keyword. The chat model must support tool calls.
   A successful connection test proves discovery, not that every server tool works.

Save with the enable switch off to stop a connection. Remove server deletes its
configuration and stops its connection. Reimporting a server with the same name
replaces launch/auth details, turns it off, and clears tool grants. No restart is
needed for importing, enabling, disabling, or removing servers.

## Configuration examples

A local stdio server:

```json
{
  "mcpServers": {
    "my-server": {
      "command": "/absolute/path/to/python",
      "args": ["/absolute/path/to/server.py"],
      "cwd": "/absolute/path/to/server-directory",
      "env": {"SERVICE_API_KEY": "your-key"}
    }
  }
}
```

Commands execute directly, without a shell. Use actual executable/argument names
from the server's instructions; shell strings, redirects, and variable expansion
are not interpreted. Node/npm, Python, uv, Docker, or other required runtimes must
already be available to the PETEY process. GUI launchers can have a different PATH
from your terminal, so absolute executable paths help. Windows paths need JSON
escaping, for example `C:\\Tools\\Python\\python.exe`.

A remote Streamable HTTP endpoint:

```json
{
  "mcpServers": {
    "my-remote-server": {
      "url": "https://your-server.example/mcp",
      "headers": {"Authorization": "Bearer your-token"}
    }
  }
}
```

Header authentication is supported. Each remote server has an **Authentication**
section with **Bearer token / API key (Authorization)** and **API key (X-API-Key)**
choices. Enter a credential and click **Save authentication**, then test and grant
tools again. Saving or removing authentication turns the server off, closes its
connection, and clears its tool grants and cached discovery; saved values are never
returned to the page. Other custom headers can still be supplied through import.

For Tinyfish, use `https://agent.tinyfish.ai/mcp`, select **Bearer token / API key
(Authorization)**, and paste your API key from its dashboard. A URL-only import
cannot authenticate because PETEY does not currently complete browser OAuth.
See [Tinyfish's MCP authentication instructions](https://docs.tinyfish.ai/mcp-integration). Browser OAuth sign-in, legacy SSE-only
endpoints, resources, prompts, sampling, elicitation, and proactive server events
are not supported. HTTP POST responses may use JSON or SSE; that is different from
the legacy SSE transport. PETEY handles initialization, sessions, paginated tool
discovery, tool calls, and session cleanup. Redirects are not followed. Expired or
failed actions are not automatically retried.

The bridge follows the MCP [lifecycle](https://modelcontextprotocol.io/specification/2025-06-18/basic/lifecycle)
and [Streamable HTTP transport](https://modelcontextprotocol.io/specification/2025-06-18/basic/transports).
It negotiates supported versions including 2024-11-05, 2025-03-26, 2025-06-18,
and 2025-11-25. Limits: 16 servers, 200 discovered tools per server across at most
10 pages, 100 selected tools, 1 MB HTTP responses and 1 million-character stdio responses, and 64,000-character tool
results. Discovery is cached across restarts; use Test connection to refresh it
when a server's tools change.

## Local ownership

PETEY stores launch/auth configuration and tool discovery in `mcp-servers.json`
inside its data directory, using atomic private-file writes. Secrets are hidden
from public status responses and settings after import; use Save authentication for supported headers or reimport to update other settings.
The file contains credentials in plaintext, so treat data-directory backups as
private. Tools receive their requested arguments; selected tool schemas and
results are supplied to the chat model.

Memory storage, retrieval, embeddings, correction, and deletion remain managed
by PETEY locally. This bridge does not register PETEY's memory database as an MCP
resource. An imported server still runs with PETEY's OS permissions, and can access
files/services according to its own configuration. The built-in **Filesystem**
connector keeps its separate approved-folder and read-only restrictions.

## Implementation and checks

`petey/general_mcp.py` owns configuration, policy, connection lifecycle, and the
remote client. `petey/mcp_client.py` supplies stdio. Desktop/mobile and Discord chat
registries include granted tools. Schema availability and dispatch both check grants. Remote
errors and subprocess diagnostics are sanitized before reaching public APIs.

Run focused checks from the core directory:

```bash
python -m unittest tests.test_general_mcp tests.test_mcp_client tests.test_tools tests.test_assistant tests.test_companion_api
node --check web/static/mcp.js
```

Tests use temporary data, a real fake-server stdio process, a loopback HTTP server
with JSON/SSE responses, and Flask routes. They do not install packages, contact
third-party servers, read live credentials, or modify PETEY memory.
