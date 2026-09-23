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
    emit_event: object


class AddonManager:
    """Own add-on discovery, activation, public metadata, and shutdown."""

    def __init__(self, state, user_dir: str | Path | None = None):
        self.state = state
        self.user_dir = Path(user_dir) if user_dir else state.data_dir / "addons"
        self.user_dir.mkdir(parents=True, exist_ok=True)
        self._event_broker = None
        self._records = {
            "discord": {
                "id": "discord", "name": "Discord", "version": "1.0",
                "description": "Connect PETEY to Discord chat and media slash commands.",
                "source": "built-in", "default_enabled": True, "loaded": False,
                "error": "", "path": None, "manifest": {}, "instance": None,
                "configurable_enabled": True, "control_capabilities": [],
            },
            "deapi-media": {
                "id": "deapi-media", "name": "deAPI Media", "version": "",
                "description": "Generate images through PETEY's configured deAPI media service.",
                "source": "core", "default_enabled": True, "loaded": True,
                "error": "", "path": None, "manifest": {}, "instance": None,
                "configurable_enabled": False,
                "control_capabilities": [{
                    "id": "generate_image", "label": "Generate images",
                    "metered": True, "default_daily_limit": 5,
                }],
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
            "configurable_enabled": True, "control_capabilities": [],
        }

    def enabled(self, addon_id: str) -> bool:
        record = self._records.get(addon_id)
        return bool(record) and self.state.addon_enabled(
            addon_id, bool(record.get("default_enabled"))
        )

    def activate_external(
        self, *, app, memory, gallery, runtime, get_media_jobs, event_broker=None
    ):
        self._event_broker = event_broker
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
                def emit_event(message, *, conversation_id=None, surface="petey_desktop",
                               speak=False, metadata=None, addon_id=record["id"]):
                    if self._event_broker is None:
                        raise RuntimeError("PETEY's add-on event channel is unavailable.")
                    return self._event_broker.emit(
                        addon_id,
                        message,
                        conversation_id=str(conversation_id or self.state.conversation_id),
                        surface=surface,
                        speak=speak,
                        metadata=metadata,
                    )

                record["instance"] = setup(AddonContext(
                    app=app, state=self.state, memory=memory, gallery=gallery,
                    runtime=runtime, get_media_jobs=get_media_jobs,
                    addon_id=record["id"], addon_dir=record["path"], data_dir=data_dir,
                    emit_event=emit_event,
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
        if not self._records[addon_id].get("configurable_enabled", True):
            raise ValueError("This built-in integration cannot be disabled here.")
        self.state.update_addon_enabled(addon_id, enabled)
        return self.public_record(self._records[addon_id])

    def _control_capabilities(self, record: dict) -> list[dict]:
        declared = record.get("control_capabilities")
        if declared:
            return list(declared)
        if not record.get("loaded") or record.get("error"):
            return []
        provider = getattr(record.get("instance"), "tool_specs", None)
        if not callable(provider):
            return []
        try:
            offered = provider()
        except Exception:
            return []
        capabilities = {}
        for spec in offered if isinstance(offered, list) else []:
            if not isinstance(spec, ToolSpec):
                continue
            capability = str(spec.control_capability or spec.name or "")
            if not re.fullmatch(r"[a-z][a-z0-9_-]{1,63}", capability):
                continue
            try:
                default_daily_limit = int(spec.default_daily_limit or 0)
            except (TypeError, ValueError):
                default_daily_limit = 0
            capabilities[capability] = {
                "id": capability,
                "label": str(spec.control_label or capability.replace("_", " ").title())[:80],
                "metered": bool(spec.metered),
                "default_daily_limit": max(0, min(1000, default_daily_limit)),
            }
        return list(capabilities.values())

    def set_petey_control(self, addon_id: str, changes: dict) -> dict:
        record = self._records.get(addon_id)
        if record is None:
            raise ValueError("Unknown add-on.")
        capabilities = self._control_capabilities(record)
        if not capabilities:
            raise ValueError("This add-on does not expose controllable capabilities.")
        if record["source"] == "user" and not self.enabled(addon_id):
            raise ValueError("Enable this add-on before allowing Petey to control it.")
        self.state.update_petey_control(addon_id, changes, capabilities)
        return self.public_record(record)

    def public_record(self, record: dict) -> dict:
        desired = self.enabled(record["id"])
        capabilities = self._control_capabilities(record)
        return {
            "id": record["id"], "name": record["name"], "version": record["version"],
            "description": record["description"], "source": record["source"],
            "enabled": desired, "loaded": record["loaded"], "error": record["error"],
            "configurable_enabled": record.get("configurable_enabled", True),
            "has_model_tools": bool(
                capabilities
            ),
            "petey_control": (
                self.state.petey_control_status(record["id"], capabilities)
                if capabilities else None
            ),
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
            asset_paths = [directory / panel]
            for key in ("script", "stylesheet"):
                if manifest.get(key):
                    asset_paths.append(directory / str(manifest[key]))
            asset_revision = max(
                (path.stat().st_mtime_ns for path in asset_paths if path.is_file()),
                default=0,
            )
            views.append({
                "id": f"addon-{record['id']}", "addon_id": record["id"],
                "label": str(navigation["label"])[:40],
                "icon": str(navigation.get("icon") or "◇")[:4], "html": html,
                "script": str(manifest.get("script") or ""),
                "stylesheet": str(manifest.get("stylesheet") or ""),
                "asset_revision": str(asset_revision),
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

    def tool_specs(self, *, surface: str = "petey_desktop") -> list[ToolSpec]:
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
                capability = str(spec.control_capability or spec.name or "")
                definitions = self._control_capabilities(record)

                def available(message, original=spec.available_when, addon_id=record["id"],
                              selected=capability, definitions=definitions,
                              explicit_when=spec.explicit_when, selected_surface=surface):
                    if not original(message):
                        return False
                    try:
                        self.state.authorize_petey_control(
                            addon_id, selected, selected_surface,
                            explicit=bool(explicit_when(message)),
                            capabilities=definitions,
                        )
                        return True
                    except ValueError:
                        return False

                def authorize(message, original=spec.authorize_when, addon_id=record["id"],
                              selected=capability, definitions=definitions,
                              explicit_when=spec.explicit_when, selected_surface=surface):
                    original(message)
                    try:
                        self.state.authorize_petey_control(
                            addon_id, selected, selected_surface,
                            explicit=bool(explicit_when(message)),
                            capabilities=definitions, consume=True,
                        )
                    except ValueError as exc:
                        from petey.tools.registry import ToolError
                        raise ToolError(str(exc)) from exc

                result.append(ToolSpec(
                    name=name,
                    description=f"{spec.description} Provided by the {record['name']} add-on.",
                    parameters=spec.parameters,
                    handler=spec.handler,
                    available_when=available,
                    required_when=spec.required_when,
                    authorize_when=authorize,
                    explicit_when=spec.explicit_when,
                    control_capability=capability,
                    control_label=spec.control_label,
                    metered=spec.metered,
                    default_daily_limit=spec.default_daily_limit,
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
        if self._event_broker is not None:
            self._event_broker.close()
            self._event_broker = None
