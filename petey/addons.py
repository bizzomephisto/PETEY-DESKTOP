"""Discover and load explicitly enabled PETEY Desktop add-ons."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import sys

from petey.tools.registry import ToolSpec


ADDON_ID = re.compile(r"[a-z][a-z0-9_-]{1,48}")
MANIFEST_NAME = "petey-addon.json"


@dataclass(frozen=True)
class AddonContext:
    app: object
    state: object
    memory: object
    gallery: object
    runtime: object
    get_media_jobs: object
    addon_id: str
    addon_dir: Path
    data_dir: Path


class AddonManager:
    """Own add-on discovery, activation, public metadata, and shutdown."""

    def __init__(self, state, user_dir: str | Path | None = None):
        self.state = state
        self.user_dir = Path(user_dir) if user_dir else state.data_dir / "addons"
        self.user_dir.mkdir(parents=True, exist_ok=True)
        self._records = {
            "discord": {
                "id": "discord", "name": "Discord", "version": "1.0",
                "description": "Connect PETEY to Discord chat and media slash commands.",
                "source": "built-in", "default_enabled": True, "loaded": False,
                "error": "", "path": None, "manifest": {}, "instance": None,
            }
        }
        self._discover_user_addons()

    def _discover_user_addons(self):
        for directory in sorted(self.user_dir.iterdir()):
            if not directory.is_dir() or directory.is_symlink():
                continue
            manifest_path = directory / MANIFEST_NAME
            try:
                if manifest_path.stat().st_size > 64 * 1024:
                    raise ValueError("Manifest exceeds 64 KB.")
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                record = self._validate_manifest(manifest, directory)
            except FileNotFoundError:
                continue
            except (OSError, json.JSONDecodeError, ValueError) as exc:
                addon_id = directory.name if ADDON_ID.fullmatch(directory.name) else f"invalid-{len(self._records)}"
                if addon_id not in self._records:
                    self._records[addon_id] = {
                        "id": addon_id, "name": directory.name, "version": "",
                        "description": "Could not read this add-on manifest.", "source": "user",
                        "default_enabled": False, "loaded": False, "error": str(exc)[:500],
                        "path": directory, "manifest": {}, "instance": None,
                    }
                continue
            if record["id"] in self._records:
                record["error"] = "An add-on with this ID is already installed."
                record["id"] = f"duplicate-{record['id']}"
            self._records[record["id"]] = record

    @staticmethod
    def _validate_manifest(manifest, directory: Path) -> dict:
        if not isinstance(manifest, dict):
            raise ValueError("Manifest must be a JSON object.")
        addon_id = str(manifest.get("id") or "")
        if not ADDON_ID.fullmatch(addon_id):
            raise ValueError("Add-on ID must use lowercase letters, numbers, hyphens, or underscores.")
        if manifest.get("api_version") != 1:
            raise ValueError("Add-on api_version must be 1.")
        name = str(manifest.get("name") or "").strip()
        description = str(manifest.get("description") or "").strip()
        entrypoint = str(manifest.get("entrypoint") or "addon.py")
        if not name or len(name) > 80 or len(description) > 300:
            raise ValueError("Add-on name or description is invalid.")
        for key in ("entrypoint", "panel", "script", "stylesheet"):
            value = str(manifest.get(key) or ("addon.py" if key == "entrypoint" else ""))
            if value and (Path(value).is_absolute() or ".." in Path(value).parts):
                raise ValueError(f"Manifest field {key} must be a relative path inside the add-on.")
            if value:
                candidate = (directory / value).resolve()
                if directory.resolve() not in candidate.parents:
                    raise ValueError(f"Manifest field {key} must stay inside the add-on folder.")
                if key != "entrypoint" and not candidate.is_file():
                    raise ValueError(f"Manifest file for {key} was not found.")
        entry_path = (directory / entrypoint).resolve()
        if (entry_path.suffix != ".py" or directory.resolve() not in entry_path.parents
                or not entry_path.is_file()):
            raise ValueError("Add-on entrypoint was not found inside its folder.")
        navigation = manifest.get("navigation") or {}
        if not isinstance(navigation, dict):
            raise ValueError("Add-on navigation must be an object.")
        return {
            "id": addon_id, "name": name, "version": str(manifest.get("version") or "0.1")[:40],
            "description": description, "source": "user",
            "default_enabled": manifest.get("default_enabled") is True,
            "loaded": False, "error": "", "path": directory, "manifest": manifest,
            "instance": None,
        }

    def enabled(self, addon_id: str) -> bool:
        record = self._records.get(addon_id)
        return bool(record) and self.state.addon_enabled(
            addon_id, bool(record.get("default_enabled"))
        )

    def activate_external(self, *, app, memory, gallery, runtime, get_media_jobs):
        for record in self._records.values():
            if record["source"] != "user" or not self.enabled(record["id"]) or record["error"]:
                continue
            try:
                entrypoint = record["path"] / str(record["manifest"].get("entrypoint") or "addon.py")
                module_name = f"petey_user_addon_{record['id'].replace('-', '_')}"
                spec = importlib.util.spec_from_file_location(
                    module_name, entrypoint,
                    submodule_search_locations=[str(record["path"])],
                )
                if spec is None or spec.loader is None:
                    raise RuntimeError("Python could not load the add-on entrypoint.")
                module = importlib.util.module_from_spec(spec)
                sys.modules[module_name] = module
                spec.loader.exec_module(module)
                setup = getattr(module, "setup", None)
                if not callable(setup):
                    raise RuntimeError("Add-on entrypoint must define setup(context).")
                data_dir = self.state.data_dir / "addon-data" / record["id"]
                data_dir.mkdir(parents=True, exist_ok=True)
                record["instance"] = setup(AddonContext(
                    app=app, state=self.state, memory=memory, gallery=gallery,
                    runtime=runtime, get_media_jobs=get_media_jobs,
                    addon_id=record["id"], addon_dir=record["path"], data_dir=data_dir,
                ))
                record["loaded"] = True
            except Exception as exc:
                record["error"] = f"{type(exc).__name__}: {exc}"[:500]
                sys.modules.pop(f"petey_user_addon_{record['id'].replace('-', '_')}", None)

    def mark_builtin_loaded(self, addon_id: str, loaded: bool):
        if addon_id in self._records:
            self._records[addon_id]["loaded"] = bool(loaded)

    def set_enabled(self, addon_id: str, enabled) -> dict:
        if addon_id not in self._records:
            raise ValueError("Unknown add-on.")
        self.state.update_addon_enabled(addon_id, enabled)
        return self.public_record(self._records[addon_id])

    def public_record(self, record: dict) -> dict:
        desired = self.enabled(record["id"])
        return {
            "id": record["id"], "name": record["name"], "version": record["version"],
            "description": record["description"], "source": record["source"],
            "enabled": desired, "loaded": record["loaded"], "error": record["error"],
            "restart_required": desired != record["loaded"] and not bool(record["error"]),
        }

    def public_status(self) -> dict:
        return {
            "directory": str(self.user_dir),
            "addons": [self.public_record(record) for record in self._records.values()],
        }

    def template_views(self) -> list[dict]:
        views = []
        for record in self._records.values():
            if record["source"] != "user" or not record["loaded"] or record["error"]:
                continue
            manifest, directory = record["manifest"], record["path"]
            panel = str(manifest.get("panel") or "")
            navigation = manifest.get("navigation") or {}
            if not panel or not navigation.get("label"):
                continue
            try:
                html = (directory / panel).read_text(encoding="utf-8")
            except OSError:
                continue
            views.append({
                "id": f"addon-{record['id']}", "addon_id": record["id"],
                "label": str(navigation["label"])[:40],
                "icon": str(navigation.get("icon") or "◇")[:4], "html": html,
                "script": str(manifest.get("script") or ""),
                "stylesheet": str(manifest.get("stylesheet") or ""),
            })
        return views

    def asset(self, addon_id: str, relative_path: str) -> Path | None:
        record = self._records.get(addon_id)
        if not record or not record["loaded"] or record["source"] != "user":
            return None
        try:
            candidate = (record["path"] / relative_path).resolve()
            if record["path"].resolve() not in candidate.parents or not candidate.is_file():
                return None
            return candidate
        except OSError:
            return None

    @staticmethod
    def _tool_name(addon_id: str, local_name: str) -> str:
        prefix = f"addon_{addon_id.replace('-', '_')}__"
        local = re.sub(r"[^a-zA-Z0-9_-]", "_", str(local_name or "")).strip("_")
        if not local:
            return ""
        full = prefix + local
        if len(full) <= 64:
            return full
        digest = hashlib.sha256(full.encode("utf-8")).hexdigest()[:8]
        return full[:55] + "_" + digest

    def tool_specs(self) -> list[ToolSpec]:
        """Collect model tools from loaded add-ons under collision-safe names."""
        result = []
        for record in self._records.values():
            if not record["loaded"] or record["error"]:
                continue
            provider = getattr(record.get("instance"), "tool_specs", None)
            if not callable(provider):
                continue
            try:
                offered = provider()
            except Exception as exc:
                record["error"] = f"Tool discovery failed: {exc}"[:500]
                continue
            for spec in offered if isinstance(offered, list) else []:
                if not isinstance(spec, ToolSpec):
                    continue
                name = self._tool_name(record["id"], spec.name)
                if not name:
                    continue
                result.append(ToolSpec(
                    name=name,
                    description=f"{spec.description} Provided by the {record['name']} add-on.",
                    parameters=spec.parameters,
                    handler=spec.handler,
                    available_when=spec.available_when,
                ))
        return result

    def close(self):
        for record in reversed(list(self._records.values())):
            instance = record.get("instance")
            close = getattr(instance, "close", None)
            if callable(close):
                try:
                    close()
                except Exception:
                    pass
