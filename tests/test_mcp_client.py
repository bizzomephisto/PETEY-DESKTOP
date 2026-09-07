import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from petey.desktop_state import DesktopState
from petey.mcp_client import (
    FILESYSTEM_PACKAGE,
    FilesystemMCPManager,
    MCPError,
    MCPStdioClient,
)


FAKE_SERVER = r'''
import json
import sys

for line in sys.stdin:
    message = json.loads(line)
    if "id" not in message:
        continue
    method = message.get("method")
    if method == "initialize":
        result = {
            "protocolVersion": "2025-06-18",
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "fake-filesystem", "version": "1"},
        }
    elif method == "tools/list":
        result = {"tools": [
            {"name": "read_text_file", "description": "Read text", "inputSchema": {
                "type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]
            }},
            {"name": "write_file", "description": "Write text", "inputSchema": {"type": "object"}},
        ]}
    elif method == "tools/call":
        result = {"content": [{"type": "text", "text": "hello from " + message["params"]["arguments"]["path"]}]}
    else:
        print(json.dumps({"jsonrpc": "2.0", "id": message["id"], "error": {"code": -32601, "message": "unknown"}}), flush=True)
        continue
    print(json.dumps({"jsonrpc": "2.0", "id": message["id"], "result": result}), flush=True)
'''


class MCPStdioClientTests(unittest.TestCase):
    def test_stdio_initializes_lists_and_calls_tools(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            server = root / "fake_server.py"
            server.write_text(FAKE_SERVER, encoding="utf-8")
            client = MCPStdioClient([sys.executable, str(server)], [root], timeout=3)
            try:
                tools = client.list_tools()
                result = client.call_tool("read_text_file", {"path": "notes.txt"})
            finally:
                client.close()

        self.assertEqual([tool["name"] for tool in tools], ["read_text_file", "write_file"])
        self.assertEqual(result["content"][0]["text"], "hello from notes.txt")


class FilesystemMCPManagerTests(unittest.TestCase):
    class FakeClient:
        def __init__(self, argv, roots):
            self.argv = argv
            self.roots = roots
            self.running = False
            self.calls = []

        def start(self):
            self.running = True
            return {}

        def list_tools(self):
            return [
                {"name": "read_text_file", "description": "Read text", "inputSchema": {"type": "object", "properties": {}}},
                {"name": "write_file", "description": "Write text", "inputSchema": {"type": "object", "properties": {}}},
            ]

        def call_tool(self, name, arguments):
            self.calls.append((name, arguments))
            return {"content": [{"type": "text", "text": "safe"}]}

        def close(self):
            self.running = False

    def test_manager_uses_approved_roots_and_only_exposes_read_tools(self):
        with tempfile.TemporaryDirectory() as data_directory, tempfile.TemporaryDirectory() as workspace:
            state = DesktopState(data_directory)
            state.add_workspace(workspace)
            clients = []

            def factory(argv, roots):
                client = self.FakeClient(argv, roots)
                clients.append(client)
                return client

            manager = FilesystemMCPManager(state, client_factory=factory)
            with patch("petey.mcp_client.shutil.which", return_value="/usr/bin/npx"):
                status = manager.set_enabled(True)
                specs = manager.tool_specs()
                result = specs[0].handler({"path": "notes.txt"})

            self.assertTrue(status["enabled"])
            self.assertEqual([tool["name"] for tool in status["tools"]], ["read_text_file"])
            self.assertEqual([spec.name for spec in specs], ["mcp_filesystem__read_text_file"])
            self.assertTrue(specs[0].available_when("Read the project file"))
            self.assertFalse(specs[0].available_when("How are you today?"))
            self.assertIn(FILESYSTEM_PACKAGE, clients[0].argv)
            self.assertEqual(clients[0].roots, [Path(workspace).resolve()])
            self.assertIn("safe", result["result"])
            with self.assertRaises(MCPError):
                manager.call_tool("write_file", {"path": "notes.txt"})
            manager.close()

    def test_manager_requires_an_approved_workspace(self):
        with tempfile.TemporaryDirectory() as data_directory:
            manager = FilesystemMCPManager(DesktopState(data_directory))
            with patch("petey.mcp_client.shutil.which", return_value="/usr/bin/npx"):
                with self.assertRaisesRegex(MCPError, "Approve at least one"):
                    manager.set_enabled(True)


if __name__ == "__main__":
    unittest.main()
