"""Path-safe desktop workspaces, reviewable changes, and approved command runs."""

from __future__ import annotations

import difflib
import hashlib
import json
import os
import re
import signal
import subprocess
import threading
import time
import uuid
from pathlib import Path

from petey.ai_provider import AIProvider


MAX_FILE_BYTES = 2 * 1024 * 1024
MAX_OUTPUT_BYTES = 200 * 1024
MAX_PROPOSAL_AGE = 60 * 60


class WorkspaceError(ValueError):
    """A workspace operation failed validation."""


class WorkspaceService:
    def __init__(self, state):
        self.state = state
        self._proposals: dict[str, dict] = {}
        self._lock = threading.RLock()

    def workspace(self, workspace_id: str) -> dict:
        match = next((item for item in self.state.workspaces if item["id"] == workspace_id), None)
        if match is None:
            raise WorkspaceError("Approved folder not found.")
        root = Path(match["path"]).resolve(strict=True)
        if not root.is_dir():
            raise WorkspaceError("The approved folder is no longer available.")
        return {**match, "root": root}

    def resolve(self, workspace_id: str, relative: str = "", *, must_exist: bool = True) -> tuple[dict, Path]:
        workspace = self.workspace(workspace_id)
        root: Path = workspace["root"]
        relative = str(relative or "").replace("\\", "/").lstrip("/")
        candidate = root / relative
        try:
            if must_exist:
                resolved = candidate.resolve(strict=True)
            else:
                parent = candidate.parent.resolve(strict=True)
                resolved = parent / candidate.name
        except (OSError, RuntimeError) as exc:
            raise WorkspaceError("That path does not exist inside the approved folder.") from exc
        if resolved != root and root not in resolved.parents:
            raise WorkspaceError("That path escapes the approved folder.")
        return workspace, resolved

    def list_directory(self, workspace_id: str, relative: str = "") -> dict:
        workspace, directory = self.resolve(workspace_id, relative)
        if not directory.is_dir():
            raise WorkspaceError("That path is not a folder.")
        entries = []
        try:
            children = sorted(directory.iterdir(), key=lambda path: (not path.is_dir(), path.name.lower()))
        except OSError as exc:
            raise WorkspaceError(f"Could not read this folder: {exc}") from exc
        for child in children[:500]:
            try:
                resolved = child.resolve(strict=True)
                if resolved != workspace["root"] and workspace["root"] not in resolved.parents:
                    continue
                is_dir = resolved.is_dir()
            except OSError:
                continue
            entries.append(
                {
                    "name": child.name,
                    "path": child.relative_to(workspace["root"]).as_posix(),
                    "type": "directory" if is_dir else "file",
                }
            )
        return {"path": directory.relative_to(workspace["root"]).as_posix(), "entries": entries}

    def read_file(self, workspace_id: str, relative: str) -> dict:
        workspace, path = self.resolve(workspace_id, relative)
        if not path.is_file():
            raise WorkspaceError("That path is not a file.")
        try:
            size = path.stat().st_size
            if size > MAX_FILE_BYTES:
                raise WorkspaceError("Files larger than 2 MB cannot be opened in the editor.")
            raw = path.read_bytes()
        except OSError as exc:
            raise WorkspaceError(f"Could not read the file: {exc}") from exc
        if b"\0" in raw:
            raise WorkspaceError("Binary files cannot be opened in the text editor.")
        try:
            content = raw.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise WorkspaceError("This file is not UTF-8 text.") from exc
        return {
            "path": path.relative_to(workspace["root"]).as_posix(),
            "content": content,
            "sha256": hashlib.sha256(raw).hexdigest(),
        }

    def preview_write(self, workspace_id: str, relative: str, content: str) -> dict:
        if len(content.encode("utf-8")) > MAX_FILE_BYTES:
            raise WorkspaceError("Editor files are limited to 2 MB.")
        workspace, path = self.resolve(workspace_id, relative, must_exist=False)
        original = ""
        original_hash = None
        if path.exists():
            current = self.read_file(workspace_id, relative)
            original = current["content"]
            original_hash = current["sha256"]
        diff = "".join(
            difflib.unified_diff(
                original.splitlines(keepends=True),
                content.splitlines(keepends=True),
                fromfile=f"a/{relative}",
                tofile=f"b/{relative}",
            )
        )
        return {
            "path": path.relative_to(workspace["root"]).as_posix(),
            "content": content,
            "original_sha256": original_hash,
            "diff": diff or "(No changes)",
        }

    def write_file(self, workspace_id: str, relative: str, content: str, expected_sha256=None) -> dict:
        preview = self.preview_write(workspace_id, relative, content)
        if expected_sha256 is not None and preview["original_sha256"] != expected_sha256:
            raise WorkspaceError("The file changed since it was opened. Reload it before saving.")
        _, path = self.resolve(workspace_id, relative, must_exist=False)
        temporary = path.with_name(f".{path.name}.petey-{uuid.uuid4().hex}.tmp")
        try:
            temporary.write_text(content, encoding="utf-8")
            os.replace(temporary, path)
        except OSError as exc:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass
            raise WorkspaceError(f"Could not save the file: {exc}") from exc
        return self.read_file(workspace_id, relative)

    def _remember(self, proposal: dict) -> dict:
        with self._lock:
            now = time.time()
            self._proposals = {
                key: value for key, value in self._proposals.items()
                if now - value["created_timestamp"] < MAX_PROPOSAL_AGE
            }
            proposal_id = uuid.uuid4().hex
            proposal = {**proposal, "id": proposal_id, "created_timestamp": now}
            self._proposals[proposal_id] = proposal
        return self.public_proposal(proposal)

    @staticmethod
    def public_proposal(proposal: dict) -> dict:
        return {key: value for key, value in proposal.items() if key not in {"content", "created_timestamp"}}

    def propose_write(self, workspace_id: str, relative: str, content: str) -> dict:
        preview = self.preview_write(workspace_id, relative, content)
        return self._remember({"type": "write_file", "workspace_id": workspace_id, **preview})

    def propose_command(self, workspace_id: str, command: str, cwd: str = "") -> dict:
        command = str(command or "").strip()
        if not command:
            raise WorkspaceError("Enter a command to run.")
        if len(command) > 2000 or "\0" in command:
            raise WorkspaceError("The command is too long or invalid.")
        self.resolve(workspace_id, cwd)
        return self._remember(
            {"type": "run_command", "workspace_id": workspace_id, "command": command, "cwd": cwd}
        )

    def reject(self, proposal_id: str) -> None:
        with self._lock:
            if self._proposals.pop(proposal_id, None) is None:
                raise WorkspaceError("Proposal not found or already handled.")

    def approve(self, proposal_id: str) -> dict:
        with self._lock:
            proposal = self._proposals.pop(proposal_id, None)
        if proposal is None or time.time() - proposal["created_timestamp"] >= MAX_PROPOSAL_AGE:
            raise WorkspaceError("Proposal not found or expired.")
        if proposal["type"] == "write_file":
            result = self.write_file(
                proposal["workspace_id"], proposal["path"], proposal["content"],
                proposal.get("original_sha256"),
            )
            return {"type": "write_file", "file": result}
        return {"type": "run_command", "run": self.run_command(proposal)}

    def run_command(self, proposal: dict) -> dict:
        _, cwd = self.resolve(proposal["workspace_id"], proposal.get("cwd", ""))
        if not cwd.is_dir():
            raise WorkspaceError("The command working directory is not a folder.")
        started = time.monotonic()
        process = subprocess.Popen(
            proposal["command"], cwd=cwd, shell=True, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, stdin=subprocess.DEVNULL,
            start_new_session=(os.name != "nt"),
        )
        try:
            stdout, stderr = process.communicate(timeout=60)
            output = (stdout + stderr)[:MAX_OUTPUT_BYTES].decode("utf-8", errors="replace")
            return {
                "command": proposal["command"], "cwd": proposal.get("cwd", ""),
                "exit_code": process.returncode, "output": output,
                "duration_seconds": round(time.monotonic() - started, 2),
                "truncated": len(stdout) + len(stderr) > MAX_OUTPUT_BYTES,
            }
        except subprocess.TimeoutExpired:
            if os.name != "nt":
                os.killpg(process.pid, signal.SIGKILL)
            else:
                process.kill()
            stdout, stderr = process.communicate()
            output = (stdout + stderr)[:MAX_OUTPUT_BYTES].decode("utf-8", errors="replace")
            return {"command": proposal["command"], "cwd": proposal.get("cwd", ""), "exit_code": None,
                    "output": output + "\nCommand stopped after the 60 second limit.", "duration_seconds": 60,
                    "timed_out": True, "truncated": False}

    def agent_proposals(self, workspace_id: str, instruction: str, selected_path: str = "") -> dict:
        instruction = str(instruction or "").strip()
        if not instruction:
            raise WorkspaceError("Tell Petey what you want changed or run.")
        root_listing = self.list_directory(workspace_id)["entries"][:200]
        selected = None
        if selected_path:
            selected = self.read_file(workspace_id, selected_path)
        context = {
            "files_at_workspace_root": root_listing,
            "selected_file": selected,
        }
        system = (
            "You are Petey's workspace planning engine. Return only valid JSON, no markdown. "
            "Use this shape: {\"reply\":\"short explanation\",\"actions\":["
            "{\"type\":\"write_file\",\"path\":\"relative/path\",\"content\":\"complete file text\"},"
            "{\"type\":\"run_command\",\"command\":\"exact command\",\"cwd\":\"relative/folder\"}]}. "
            "Actions are proposals reviewed by the user. Never use absolute paths or paths outside the workspace. "
            "Return at most five actions. Omit actions you cannot safely or correctly specify."
        )
        raw = AIProvider(self.state.ai_provider).complete(
            f"Request: {instruction}\nWorkspace context: {json.dumps(context)}", system, []
        )
        data = self._parse_agent_json(raw)
        proposals = []
        errors = []
        for action in data.get("actions", [])[:5]:
            try:
                if action.get("type") == "write_file":
                    proposals.append(self.propose_write(workspace_id, action.get("path", ""), str(action.get("content", ""))))
                elif action.get("type") == "run_command":
                    proposals.append(self.propose_command(workspace_id, action.get("command", ""), action.get("cwd", "")))
            except WorkspaceError as exc:
                errors.append(str(exc))
        return {"reply": str(data.get("reply") or "I prepared these proposals."), "proposals": proposals, "errors": errors}

    @staticmethod
    def _parse_agent_json(raw: str) -> dict:
        cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", str(raw).strip(), flags=re.IGNORECASE)
        if not cleaned.startswith("{") and "{" in cleaned and "}" in cleaned:
            cleaned = cleaned[cleaned.find("{"):cleaned.rfind("}") + 1]
        try:
            data = json.loads(cleaned)
        except json.JSONDecodeError as exc:
            raise WorkspaceError("The model did not return a usable workspace proposal. Try a more specific request.") from exc
        if not isinstance(data, dict) or not isinstance(data.get("actions", []), list):
            raise WorkspaceError("The model returned an invalid workspace proposal.")
        return data
