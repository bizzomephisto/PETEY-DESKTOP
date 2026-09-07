"""Small MCP stdio client and the approved-folder filesystem integration."""

from __future__ import annotations

import json
import os
import queue
import re
import shutil
import subprocess
import threading
from collections import deque
from pathlib import Path

from petey.tools.registry import ToolSpec
from petey.version import __version__


MCP_PROTOCOL_VERSION = "2025-06-18"
FILESYSTEM_PACKAGE = "@modelcontextprotocol/server-filesystem@2026.8.31"
MAX_TOOL_RESULT_CHARS = 64_000
READ_ONLY_FILESYSTEM_TOOLS = {
    "read_file",
    "read_text_file",
    "read_multiple_files",
    "list_directory",
    "list_directory_with_sizes",
    "directory_tree",
    "search_files",
    "get_file_info",
    "list_allowed_directories",
}
_FILE_INTENT = re.compile(
    r"\b(file|files|folder|folders|directory|directories|workspace|project|codebase|"
    r"source|repository|repo|readme|document|documents|search|find|inspect|open|list)\b",
    re.IGNORECASE,
)


class MCPError(RuntimeError):
    """An MCP server could not start or complete a request."""


class MCPStdioClient:
    """Synchronous, single-flight MCP client for a local stdio server."""

    def __init__(self, argv: list[str], roots: list[Path], timeout: float = 60):
        self.argv = [str(part) for part in argv]
        self.roots = [Path(root).resolve() for root in roots]
        self.timeout = timeout
        self._process: subprocess.Popen | None = None
        self._messages: queue.Queue = queue.Queue()
        self._stderr = deque(maxlen=30)
        self._request_id = 0
        self._lock = threading.RLock()

    @property
    def running(self) -> bool:
        return self._process is not None and self._process.poll() is None

    def start(self) -> dict:
        with self._lock:
            if self.running:
                return {}
            try:
                self._process = subprocess.Popen(
                    self.argv,
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    bufsize=1,
                    shell=False,
                )
            except OSError as exc:
                raise MCPError(f"Could not start the MCP server: {exc}") from exc
            threading.Thread(target=self._read_stdout, daemon=True, name="petey-mcp-stdout").start()
            threading.Thread(target=self._read_stderr, daemon=True, name="petey-mcp-stderr").start()
            try:
                result = self.request(
                    "initialize",
                    {
                        "protocolVersion": MCP_PROTOCOL_VERSION,
                        "capabilities": {"roots": {"listChanged": True}},
                        "clientInfo": {"name": "petey-desktop", "version": __version__},
                    },
                )
                if result.get("protocolVersion") != MCP_PROTOCOL_VERSION:
                    raise MCPError("The MCP server does not support Petey's protocol version.")
                self.notify("notifications/initialized")
                return result
            except Exception:
                self.close()
                raise

    def _read_stdout(self) -> None:
        process = self._process
        if process is None or process.stdout is None:
            return
        for line in process.stdout:
            line = line.strip()
            if not line:
                continue
            try:
                self._messages.put(json.loads(line))
            except json.JSONDecodeError:
                self._stderr.append(f"Invalid server output: {line[:300]}")
        self._messages.put(None)

    def _read_stderr(self) -> None:
        process = self._process
        if process is None or process.stderr is None:
            return
        for line in process.stderr:
            self._stderr.append(line.strip())

    def _write(self, payload: dict) -> None:
        process = self._process
        if process is None or process.stdin is None or process.poll() is not None:
            raise MCPError(self._stopped_message())
        try:
            process.stdin.write(json.dumps(payload, separators=(",", ":")) + "\n")
            process.stdin.flush()
        except (BrokenPipeError, OSError) as exc:
            raise MCPError(self._stopped_message()) from exc

    def _stopped_message(self) -> str:
        detail = " ".join(item for item in self._stderr if item).strip()
        return f"The MCP server stopped unexpectedly.{(' ' + detail[-600:]) if detail else ''}"

    def _answer_server_request(self, message: dict) -> None:
        request_id = message.get("id")
        method = message.get("method")
        if method == "roots/list":
            result = {
                "roots": [
                    {"uri": root.as_uri(), "name": root.name or str(root)}
                    for root in self.roots
                ]
            }
            self._write({"jsonrpc": "2.0", "id": request_id, "result": result})
        elif method == "ping":
            self._write({"jsonrpc": "2.0", "id": request_id, "result": {}})
        else:
            self._write({
                "jsonrpc": "2.0", "id": request_id,
                "error": {"code": -32601, "message": "Method not supported by Petey."},
            })

    def request(self, method: str, params: dict | None = None) -> dict:
        with self._lock:
            if not self.running and method != "initialize":
                self.start()
            self._request_id += 1
            request_id = self._request_id
            payload = {"jsonrpc": "2.0", "id": request_id, "method": method}
            if params is not None:
                payload["params"] = params
            self._write(payload)
            while True:
                try:
                    message = self._messages.get(timeout=self.timeout)
                except queue.Empty as exc:
                    raise MCPError(f"The MCP server did not answer {method} within {self.timeout:g} seconds.") from exc
                if message is None:
                    raise MCPError(self._stopped_message())
                if isinstance(message, dict) and "method" in message and "id" in message:
                    self._answer_server_request(message)
                    continue
                if not isinstance(message, dict) or message.get("id") != request_id:
                    continue
                if "error" in message:
                    error = message.get("error") or {}
                    raise MCPError(str(error.get("message") or "The MCP server returned an error."))
                result = message.get("result", {})
                return result if isinstance(result, dict) else {"value": result}

    def notify(self, method: str, params: dict | None = None) -> None:
        payload = {"jsonrpc": "2.0", "method": method}
        if params is not None:
            payload["params"] = params
        self._write(payload)

    def list_tools(self) -> list[dict]:
        self.start()
        tools = self.request("tools/list").get("tools", [])
        return [tool for tool in tools if isinstance(tool, dict)]

    def call_tool(self, name: str, arguments: dict) -> dict:
        self.start()
        return self.request("tools/call", {"name": name, "arguments": arguments})

    def close(self) -> None:
        with self._lock:
            process, self._process = self._process, None
            if process is None:
                return
            try:
                if process.stdin:
                    process.stdin.close()
            except OSError:
                pass
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=2)
            for stream in (process.stdout, process.stderr):
                try:
                    if stream:
                        stream.close()
                except OSError:
                    pass


class FilesystemMCPManager:
    """Own the official filesystem MCP connection for approved workspaces."""

    def __init__(self, state, client_factory=None):
        self.state = state
        self._client_factory = client_factory or (
            lambda argv, roots: MCPStdioClient(argv, roots)
        )
        self._client = None
        self._signature: tuple[str, ...] = ()
        self._tools: list[dict] = []
        self._last_error = ""
        self._lock = threading.RLock()

    @property
    def enabled(self) -> bool:
        return bool(self.state.tools.get("filesystem", {}).get("enabled", False))

    def _roots(self) -> list[Path]:
        roots = []
        for workspace in self.state.workspaces:
            try:
                root = Path(workspace.get("path", "")).resolve(strict=True)
            except (OSError, RuntimeError):
                continue
            if root.is_dir():
                roots.append(root)
        return roots

    @staticmethod
    def _argv(roots: list[Path]) -> list[str]:
        prefix = ["cmd", "/c", "npx"] if os.name == "nt" else ["npx"]
        return [*prefix, "-y", FILESYSTEM_PACKAGE, *(str(root) for root in roots)]

    def _ensure_client(self):
        roots = self._roots()
        if not roots:
            raise MCPError("Approve at least one Workspace folder before enabling Filesystem.")
        if shutil.which("npx") is None:
            raise MCPError("Filesystem MCP needs Node.js and npx installed on this computer.")
        signature = tuple(str(root) for root in roots)
        if self._client is not None and self._signature == signature and self._client.running:
            return self._client
        self.disconnect()
        client = self._client_factory(self._argv(roots), roots)
        client.start()
        self._client = client
        self._signature = signature
        return client

    def connect(self) -> list[dict]:
        with self._lock:
            try:
                client = self._ensure_client()
                if self._tools:
                    return list(self._tools)
                offered = client.list_tools()
                self._tools = [
                    tool for tool in offered
                    if str(tool.get("name") or "") in READ_ONLY_FILESYSTEM_TOOLS
                ]
                if not self._tools:
                    raise MCPError("The filesystem server did not offer any supported read-only tools.")
                self._last_error = ""
                return list(self._tools)
            except Exception as exc:
                self._last_error = str(exc)
                self.disconnect(keep_error=True)
                raise

    def disconnect(self, keep_error: bool = False) -> None:
        with self._lock:
            if self._client is not None:
                self._client.close()
            self._client = None
            self._signature = ()
            self._tools = []
            if not keep_error:
                self._last_error = ""

    def public_status(self) -> dict:
        roots = self._roots()
        return {
            "id": "filesystem",
            "name": "Filesystem",
            "kind": "MCP",
            "enabled": self.enabled,
            "connected": bool(self._client is not None and self._client.running),
            "available": shutil.which("npx") is not None,
            "approved_folders": [
                {"name": root.name or str(root), "path": str(root)} for root in roots
            ],
            "tools": [
                {"name": tool.get("name", ""), "description": tool.get("description", "")}
                for tool in self._tools
            ],
            "error": self._last_error,
        }

    def test_connection(self) -> dict:
        tools = self.connect()
        status = self.public_status()
        status["tools"] = [
            {"name": tool.get("name", ""), "description": tool.get("description", "")}
            for tool in tools
        ]
        if not self.enabled:
            self.disconnect()
            status["connected"] = False
        return status

    def set_enabled(self, enabled: bool) -> dict:
        if enabled:
            self.connect()
            self.state.update_tool("filesystem", True)
        else:
            self.state.update_tool("filesystem", False)
            self.disconnect()
        return self.public_status()

    def call_tool(self, name: str, arguments: dict) -> dict:
        if name not in READ_ONLY_FILESYSTEM_TOOLS:
            raise MCPError("That filesystem capability is not available in read-only mode.")
        result = self._ensure_client().call_tool(name, arguments)
        encoded = json.dumps(result, ensure_ascii=False)
        truncated = len(encoded) > MAX_TOOL_RESULT_CHARS
        if truncated:
            encoded = encoded[:MAX_TOOL_RESULT_CHARS]
        return {
            "server": "Filesystem",
            "tool": name,
            "result": encoded,
            "truncated": truncated,
        }

    def tool_specs(self) -> list[ToolSpec]:
        if not self.enabled:
            return []
        try:
            tools = self.connect()
        except Exception:
            return []
        specs = []
        for tool in tools:
            original_name = str(tool.get("name") or "")
            schema = tool.get("inputSchema")
            if not isinstance(schema, dict):
                schema = {"type": "object", "properties": {}}
            else:
                schema = dict(schema)
                schema.pop("$schema", None)
            description = str(tool.get("description") or original_name)
            specs.append(ToolSpec(
                name=f"mcp_filesystem__{original_name}",
                description=f"{description} Read only; limited to folders approved in Petey Workspace.",
                parameters=schema,
                handler=lambda arguments, name=original_name: self.call_tool(name, arguments),
                available_when=lambda message: bool(_FILE_INTENT.search(str(message or ""))),
            ))
        return specs

    def close(self) -> None:
        self.disconnect()
