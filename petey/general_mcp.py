"""User-configured MCP connections, independent of PETEY add-ons and memory."""
from __future__ import annotations

import copy
import json
import hashlib
import time
import os
import re
import tempfile
import threading
import uuid
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

import requests

from petey.mcp_client import MCPError, MCPStdioClient, MCP_PROTOCOL_VERSION
from petey.tools.registry import ToolError, ToolSpec
from petey.version import __version__

SUPPORTED_VERSIONS = {"2024-11-05", "2025-03-26", "2025-06-18", "2025-11-25"}
MAX_RESPONSE = 1_000_000
SURFACES = ("petey_desktop", "mobile_petey", "discord")


class MCPHTTPClient:
    """Streamable HTTP with JSON/SSE responses and explicit session cleanup."""
    def __init__(self, url, headers=None, timeout=30):
        self.url, self.headers, self.timeout = url, dict(headers or {}), timeout
        self.session = requests.Session()
        self.session_id = None
        self.version = MCP_PROTOCOL_VERSION
        self.running = False
        self._id = 0
        self._lock = threading.RLock()

    def _post(self, payload, notification=False):
        headers = {**self.headers, "Content-Type": "application/json",
                   "Accept": "application/json, text/event-stream"}
        if self.running:
            headers["MCP-Protocol-Version"] = self.version
        if self.session_id:
            headers["Mcp-Session-Id"] = self.session_id
        try:
            with self.session.post(self.url, json=payload, headers=headers,
                                   timeout=(10, self.timeout), stream=True, allow_redirects=False) as response:
                if response.status_code in (401, 403):
                    raise MCPError("Authentication failed (HTTP 401/403). Save a valid token or API key under Authentication, then test again. Browser OAuth sign-in is not supported yet.")
                if response.status_code == 404 and self.session_id:
                    self.running = False
                    self.session_id = None
                    raise MCPError("The MCP session expired. Test the connection again; the action was not retried.")
                if not 200 <= response.status_code < 300:
                    raise MCPError(f"MCP server returned HTTP {response.status_code}.")
                if payload.get("method") == "initialize":
                    self.session_id = response.headers.get("Mcp-Session-Id")
                if notification:
                    return {}
                content_type = response.headers.get("Content-Type", "")
                if "text/event-stream" in content_type:
                    parts, size = [], 0
                    deadline = time.monotonic() + self.timeout
                    for raw in response.iter_lines(chunk_size=1):
                        if time.monotonic() > deadline:
                            raise MCPError("MCP response stream timed out.")
                        size += len(raw)
                        if size > MAX_RESPONSE:
                            raise MCPError("MCP response exceeded the size limit.")
                        line = raw.decode("utf-8")
                        if line.startswith("data:"):
                            parts.append(line[5:].lstrip())
                        elif not line and parts:
                            message = json.loads("\n".join(parts)); parts = []
                            if not isinstance(message, dict):
                                raise MCPError("Invalid MCP message.")
                            if message.get("id") == payload.get("id") and "method" not in message:
                                return self._result(message)
                            if "method" in message and "id" in message:
                                reply = {"jsonrpc": "2.0", "id": message["id"]}
                                if message["method"] == "ping":
                                    reply["result"] = {}
                                else:
                                    reply["error"] = {"code": -32601, "message": "Client feature not supported."}
                                self._post(reply, notification=True)
                    raise MCPError("MCP response stream ended without a result.")
                data = bytearray()
                for chunk in response.iter_content(8192):
                    data.extend(chunk)
                    if len(data) > MAX_RESPONSE:
                        raise MCPError("MCP response exceeded the size limit.")
                message = json.loads(data)
                if not isinstance(message, dict):
                    raise MCPError("Invalid MCP message.")
                if message.get("id") != payload.get("id"):
                    raise MCPError("MCP response did not match the request.")
                return self._result(message)
        except (requests.RequestException, ValueError, UnicodeError) as exc:
            raise MCPError("The MCP server could not complete the request. Check its connection and configuration.") from exc

    @staticmethod
    def _result(message):
        if message.get("error"):
            raise MCPError("The MCP server rejected the request.")
        result = message.get("result")
        if not isinstance(result, dict):
            raise MCPError("The MCP server returned an invalid result.")
        return result

    def request(self, method, params=None):
        with self._lock:
            self._id += 1
            return self._post({"jsonrpc": "2.0", "id": self._id, "method": method, "params": params or {}})

    def start(self):
        with self._lock:
            if self.running:
                return
            result = self.request("initialize", {
                "protocolVersion": MCP_PROTOCOL_VERSION, "capabilities": {},
                "clientInfo": {"name": "petey-desktop", "version": __version__},
            })
            self.version = result.get("protocolVersion")
            if self.version not in SUPPORTED_VERSIONS:
                self.close()
                raise MCPError("The MCP server uses an unsupported protocol version.")
            self.running = True
            try:
                self._post({"jsonrpc": "2.0", "method": "notifications/initialized"}, notification=True)
            except Exception:
                self.close()
                raise

    def list_tools(self):
        self.start()
        tools, cursor = [], None
        for _ in range(10):
            result = self.request("tools/list", {"cursor": cursor} if cursor else {})
            page = result.get("tools", [])
            if not isinstance(page, list):
                raise MCPError("Invalid MCP tool listing.")
            tools.extend(item for item in page if isinstance(item, dict))
            if len(tools) > 200:
                raise MCPError("MCP tool listing exceeded the tool limit.")
            cursor = result.get("nextCursor")
            if not cursor:
                return tools[:200]
        raise MCPError("MCP tool listing exceeded the page limit.")

    def call_tool(self, name, arguments):
        self.start()
        return self.request("tools/call", {"name": name, "arguments": arguments})

    def close(self):
        if self.session_id:
            try:
                response = self.session.delete(self.url, headers={**self.headers,
                    "Mcp-Session-Id": self.session_id, "MCP-Protocol-Version": self.version},
                    timeout=5, allow_redirects=False)
                response.close()
            except requests.RequestException:
                pass
        self.session_id = None
        self.running = False
        self.session.close()


class GeneralMCPManager:
    def __init__(self, state, client_factory=None):
        self.path = Path(state.data_dir) / "mcp-servers.json"
        self.client_factory = client_factory or self._make_client
        self._lock = threading.RLock()
        self._clients, self._tools, self._errors = {}, {}, {}
        try:
            stored = json.loads(self.path.read_text())
            self._servers = stored.get("servers", {})
            self._tools = stored.get("tools", {}) if isinstance(stored.get("tools"), dict) else {}
            if not isinstance(self._servers, dict):
                self._servers = {}
            for config in self._servers.values():
                config["surfaces"] = {
                    surface: config.get("surfaces", {}).get(surface, surface in SURFACES[:2]) is True
                    for surface in SURFACES
                }
        except (OSError, ValueError, AttributeError):
            self._servers = {}

    @staticmethod
    def _make_client(config):
        if config["transport"] == "http":
            return MCPHTTPClient(config["url"], config.get("headers"))
        return MCPStdioClient([config["command"], *config.get("args", [])], [], timeout=30,
                              env=config.get("env"), cwd=config.get("cwd") or None,
                              supported_versions=SUPPORTED_VERSIONS, max_response_chars=MAX_RESPONSE)

    def _save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary = tempfile.mkstemp(prefix=".mcp-", dir=self.path.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as file:
                json.dump({"servers": self._servers, "tools": self._tools}, file, ensure_ascii=False, indent=2)
            os.replace(temporary, self.path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)

    @staticmethod
    def _validate(name, data):
        if not isinstance(name, str) or not name.strip() or len(name) > 80 or not isinstance(data, dict):
            raise ValueError("Each MCP server needs a name and a configuration object.")
        config = {"name": name.strip(), "enabled": False, "allowed_tools": [],
                  "keywords": [], "surfaces": {surface: surface in SURFACES[:2] for surface in SURFACES}}
        if data.get("url"):
            url = str(data["url"])
            try:
                parsed = urlsplit(url)
            except ValueError:
                raise ValueError("Use a valid HTTP(S) MCP endpoint.") from None
            if (parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username
                    or parsed.password or parsed.fragment or len(url) > 4096):
                raise ValueError("Use an HTTP(S) MCP endpoint without embedded credentials.")
            if data.get("type") == "sse" or data.get("transport") == "sse":
                raise ValueError("Use a Streamable HTTP endpoint; legacy SSE-only connections are not supported.")
            config.update(transport="http", url=url)
        else:
            command = data.get("command")
            args = data.get("args", [])
            if (not isinstance(command, str) or not command.strip() or "\0" in command or len(command) > 2048
                    or not isinstance(args, list) or len(args) > 100
                    or any(not isinstance(arg, str) or "\0" in arg or len(arg) > 4096 for arg in args)):
                raise ValueError("A local server needs a command and an array of argument strings.")
            cwd = data.get("cwd", "")
            if not isinstance(cwd, str) or "\0" in cwd or len(cwd) > 2048:
                raise ValueError("The working directory must be a path string.")
            config.update(transport="stdio", command=command, args=args, cwd=cwd)
        for field in ("env", "headers"):
            values = data.get(field, {})
            if (not isinstance(values, dict) or len(values) > 50
                    or any(not isinstance(k, str) or not isinstance(v, str)
                           or not k or "\0" in k or "\0" in v or len(k) > 100 or len(v) > 8192 or "\n" in k or "\r" in k
                           for k, v in values.items())):
                raise ValueError(f"{field} must contain bounded string names and values.")
            if field == "headers" and any(
                not re.fullmatch(r"[A-Za-z0-9_-]+", k) or "\n" in v or "\r" in v
                or k.lower() in {"host", "content-length", "mcp-session-id", "mcp-protocol-version"}
                for k, v in values.items()
            ):
                raise ValueError("An MCP header is invalid or reserved.")
            config[field] = values
        return config

    def import_config(self, payload):
        incoming = payload.get("mcpServers") if isinstance(payload, dict) else None
        if not isinstance(incoming, dict) or not incoming or len(incoming) > 16:
            raise ValueError("Paste an mcpServers object with 1–16 servers.")
        validated = [self._validate(name, data) for name, data in incoming.items()]
        with self._lock:
            servers = copy.deepcopy(self._servers)
            replacements = []
            for config in validated:
                key = next((k for k, v in servers.items() if v["name"] == config["name"]), uuid.uuid4().hex[:12])
                servers[key] = config
                replacements.append(key)
            if len(servers) > 16:
                raise ValueError("PETEY supports up to 16 configured MCP servers.")
            old = self._servers
            old_tools = copy.deepcopy(self._tools)
            for key in replacements:
                self._tools.pop(key, None)
            self._servers = servers
            try:
                self._save()
            except OSError:
                self._servers = old
                self._tools = old_tools
                raise
            for key in replacements:
                self.disconnect(key)
                self._tools.pop(key, None)
            return self.public_status()

    def _config(self, key):
        if key not in self._servers:
            raise ValueError("MCP server not found.")
        return self._servers[key]

    def _connect(self, key):
        config = self._config(key)
        if key not in self._clients:
            self._clients[key] = self.client_factory(config)
        return self._clients[key]

    def test(self, key):
        with self._lock:
            self._config(key)
            client = None
            try:
                client = self._connect(key)
                tools = client.list_tools()
                self._tools[key] = {tool["name"]: {field: copy.deepcopy(tool[field])
                    for field in ("name", "description", "inputSchema", "annotations") if field in tool} for tool in tools[:200]
                    if isinstance(tool, dict) and isinstance(tool.get("name"), str) and re.fullmatch(r"[A-Za-z0-9_.-]{1,100}", str(tool.get("name", "")))
                    and isinstance(tool.get("inputSchema", {}), dict)}
                self._save()
                self._errors.pop(key, None)
            except Exception as exc:
                self.disconnect(key)
                self._errors[key] = (str(exc) if isinstance(client, MCPHTTPClient) and isinstance(exc, MCPError)
                                     else "Connection failed. Check the server command, endpoint, dependencies, and credentials.")
                raise MCPError(self._errors[key]) from exc
            return self.public_status()

    def update(self, key, changes):
        if not isinstance(changes, dict):
            raise ValueError("MCP settings must be an object.")
        with self._lock:
            config = copy.deepcopy(self._config(key))
            credential_changed = "credential" in changes
            if credential_changed:
                credential = changes["credential"]
                if config["transport"] != "http" or not isinstance(credential, dict):
                    raise ValueError("Authentication settings require a remote HTTP server.")
                kind, value = credential.get("type"), credential.get("value", "")
                if kind not in {"bearer", "api_key", "clear"}:
                    raise ValueError("Choose Bearer token or API key authentication.")
                if not isinstance(value, str) or len(value) > 8192 or any(char in value for char in "\r\n\0"):
                    raise ValueError("Enter a valid token or API key.")
                if kind != "clear" and not value.strip():
                    raise ValueError("Enter a token or API key before saving authentication.")
                headers = {key: val for key, val in config.get("headers", {}).items()
                           if key.lower() not in {"authorization", "x-api-key"}}
                if kind == "bearer":
                    # Accept a pasted Authorization value as well as a raw API key.
                    headers["Authorization"] = value.strip() if value.strip().lower().startswith("bearer ") else "Bearer " + value.strip()
                elif kind == "api_key":
                    headers["X-API-Key"] = value.strip()
                config["headers"] = self._validate(config["name"], {**config, "headers": headers})["headers"]
            for flag in ("enabled",):
                if flag in changes:
                    if not isinstance(changes[flag], bool):
                        raise ValueError("Enabled must be true or false.")
                    config[flag] = changes[flag]
            if "allowed_tools" in changes:
                names = changes["allowed_tools"]
                if not isinstance(names, list) or len(names) > 100 or any(not isinstance(n, str) for n in names):
                    raise ValueError("Select up to 100 discovered tools.")
                if any(n not in self._tools.get(key, {}) for n in names):
                    raise ValueError("Test the connection before selecting its tools.")
                config["allowed_tools"] = list(dict.fromkeys(names))
            if "keywords" in changes:
                words = changes["keywords"]
                if not isinstance(words, list) or len(words) > 20 or any(not isinstance(w, str) or len(w) > 80 for w in words):
                    raise ValueError("Enter up to 20 chat keywords.")
                config["keywords"] = [w.strip().casefold() for w in words if w.strip()]
            if "surfaces" in changes:
                surfaces = changes["surfaces"]
                if not isinstance(surfaces, dict) or any(k not in SURFACES or not isinstance(v, bool) for k, v in surfaces.items()):
                    raise ValueError("Choose supported chat surfaces.")
                config["surfaces"].update(surfaces)
            if credential_changed:
                config["enabled"] = False
                config["allowed_tools"] = []
            if config["enabled"] and not config["allowed_tools"]:
                raise ValueError("Test the server and select tools before enabling it.")
            old = self._servers[key]
            old_tools = self._tools.get(key)
            if credential_changed:
                self._tools.pop(key, None)
            self._servers[key] = config
            try:
                self._save()
            except OSError:
                self._servers[key] = old
                if old_tools is not None:
                    self._tools[key] = old_tools
                raise
            if credential_changed:
                self._errors.pop(key, None)
            if not config["enabled"]:
                self.disconnect(key)
            return self.public_status()

    def disconnect(self, key):
        with self._lock:
            client = self._clients.pop(key, None)
            if client:
                try:
                    client.close()
                except Exception:
                    pass

    def remove(self, key):
        with self._lock:
            self._config(key)
            self.disconnect(key)
            old = self._servers.pop(key)
            old_tools = self._tools.pop(key, None)
            try:
                self._save()
            except OSError:
                self._servers[key] = old
                if old_tools is not None:
                    self._tools[key] = old_tools
                raise
            self._tools.pop(key, None)
            self._errors.pop(key, None)
            return self.public_status()

    def public_status(self):
        with self._lock:
            result = []
            for key, config in self._servers.items():
                parsed = urlsplit(config.get("url", ""))
                endpoint = urlunsplit((parsed.scheme, parsed.netloc, "", "", "")) if parsed.scheme else ""
                result.append({"id": key, "name": config["name"], "transport": config["transport"],
                    "has_authentication": any(k.lower() in {"authorization", "x-api-key"} for k in config.get("headers", {})),
                    "authentication_type": "api_key" if any(k.lower() == "x-api-key" for k in config.get("headers", {})) else "bearer",
                    "endpoint": endpoint, "enabled": config["enabled"],
                    "connected": bool(self._clients.get(key) and self._clients[key].running),
                    "allowed_tools": config["allowed_tools"], "keywords": config["keywords"],
                    "surfaces": config["surfaces"], "error": self._errors.get(key, ""),
                    "tools": [{"name": name, "description": str(tool.get("description", ""))[:1000],
                               "read_only_hint": bool(tool.get("annotations", {}).get("readOnlyHint")) if isinstance(tool.get("annotations"), dict) else False}
                              for name, tool in self._tools.get(key, {}).items()]})
            return {"servers": result}

    @staticmethod
    def _intent(config, message):
        words = config.get("keywords") or [config["name"]]
        return any(re.search(r"(?<!\w)" + re.escape(word) + r"(?!\w)", message, re.I) for word in words)

    def call(self, key, name, arguments, surface):
        with self._lock:
            config = self._config(key)
            if not config["enabled"] or not config["surfaces"].get(surface) or name not in config["allowed_tools"]:
                raise ToolError("This MCP tool is disabled for this chat surface.")
            try:
                result = self._connect(key).call_tool(name, arguments)
            except Exception as exc:
                self.disconnect(key)
                raise ToolError("The MCP tool failed. Check the connection; the action was not retried.") from exc
            # Never expose server failure text as a successful tool result.
            if not isinstance(result, dict):
                raise ToolError("The MCP server returned an invalid tool result.")
            if result.get("isError"):
                raise ToolError("The MCP server reported a tool failure.")
            text = json.dumps(result, ensure_ascii=False)
            if len(text) > 64000:
                return {"result": text[:64000], "truncated": True}
            return result

    def tool_specs(self, surface="petey_desktop"):
        with self._lock:
            specs = []
            for key, config in self._servers.items():
                if not config["enabled"] or not config["surfaces"].get(surface):
                    continue
                if key not in self._tools:
                    try:
                        self.test(key)
                    except MCPError:
                        continue
                for name in config["allowed_tools"]:
                    tool = self._tools.get(key, {}).get(name)
                    if not tool:
                        continue
                    schema = copy.deepcopy(tool.get("inputSchema") or {"type": "object", "properties": {}})
                    schema.pop("$schema", None)
                    specs.append(ToolSpec(name=f"mcp_{key}__{name[:32]}_{hashlib.sha256(name.encode()).hexdigest()[:8]}",
                        description=f"{str(tool.get('description') or name)[:2000]} (MCP server: {config['name']})",
                        parameters=schema,
                        handler=lambda args, k=key, n=name: self.call(k, n, args, surface),
                        available_when=lambda message, k=key: self._available(k, surface, message),
                    ))
            return specs

    def _available(self, key, surface, message):
        with self._lock:
            config = self._servers.get(key)
            return bool(config and config["enabled"] and config["surfaces"].get(surface) and self._intent(config, message))

    def close(self):
        with self._lock:
            for key in list(self._clients):
                self.disconnect(key)
