"""Persistent installation identity and settings for the desktop application."""

from __future__ import annotations

import getpass
import copy
import json
import os
import sys
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path

from petey.config import _build_enriched_prompt, make_default_persona

PERSONA_SLOT_COUNT = 5


def default_data_dir() -> Path:
    override = os.getenv("PETEY_DATA_DIR")
    if override:
        return Path(override).expanduser()
    if sys.platform == "win32":
        root = Path(os.getenv("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
        return root / "Petey"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "Petey"
    return Path(os.getenv("XDG_DATA_HOME", Path.home() / ".local" / "share")) / "petey"


class DesktopState:
    """Owns the local machine identity without exposing Discord-shaped concepts."""

    def __init__(self, data_dir: str | Path | None = None):
        self.data_dir = Path(data_dir) if data_dir else default_data_dir()
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.identity_path = self.data_dir / "installation.json"
        self.settings_path = self.data_dir / "settings.json"
        self._lock = threading.RLock()
        self.identity = self._load_or_create_identity()
        self.settings = self._load_or_create_settings()

    def _read_json(self, path: Path) -> dict:
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            return {}

    def _write_json(self, path: Path, value: dict) -> None:
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text(json.dumps(value, indent=2), encoding="utf-8")
        temporary.replace(path)
        try:
            path.chmod(0o600)
        except OSError:
            pass

    def _load_or_create_identity(self) -> dict:
        identity = self._read_json(self.identity_path)
        if not identity.get("installation_id"):
            identity = {
                "installation_id": f"desktop-{uuid.uuid4()}",
                "person_id": "owner",
                "display_name": getpass.getuser() or "You",
                "default_conversation_id": "main",
            }
            self._write_json(self.identity_path, identity)
        return identity

    def _load_or_create_settings(self) -> dict:
        settings = self._read_json(self.settings_path)
        changed = False
        if "persona" not in settings:
            settings["persona"] = make_default_persona(1)
            changed = True
        saved_personas = settings.get("saved_personas")
        if not isinstance(saved_personas, list):
            settings["saved_personas"] = [None] * PERSONA_SLOT_COUNT
            changed = True
        else:
            normalized_slots = [
                copy.deepcopy(item) if isinstance(item, dict) else None
                for item in saved_personas[:PERSONA_SLOT_COUNT]
            ]
            normalized_slots.extend([None] * (PERSONA_SLOT_COUNT - len(normalized_slots)))
            if normalized_slots != saved_personas:
                settings["saved_personas"] = normalized_slots
                changed = True
        if "selected_models" not in settings:
            settings["selected_models"] = {}
            changed = True
        legacy_id = str(self.identity.get("default_conversation_id", "main"))
        if not isinstance(settings.get("conversations"), list) or not settings["conversations"]:
            settings["conversations"] = [self._new_conversation(legacy_id, "Main chat")]
            changed = True
        if not settings.get("active_conversation_id"):
            settings["active_conversation_id"] = legacy_id
            changed = True
        valid_ids = {item.get("id") for item in settings["conversations"] if isinstance(item, dict)}
        if settings["active_conversation_id"] not in valid_ids:
            settings["active_conversation_id"] = settings["conversations"][0]["id"]
            changed = True
        if not isinstance(settings.get("preferences"), dict):
            settings["preferences"] = {}
            changed = True
        defaults = {"always_on_top": False, "sidebar_collapsed": False, "ui_scale": 1.0}
        for key, value in defaults.items():
            if key not in settings["preferences"]:
                settings["preferences"][key] = value
                changed = True
        if not isinstance(settings.get("workspaces"), list):
            settings["workspaces"] = []
            changed = True
        if "active_workspace_id" not in settings:
            settings["active_workspace_id"] = ""
            changed = True
        if not isinstance(settings.get("ai_provider"), dict):
            settings["ai_provider"] = {
                "provider": "gemini",
                "gemini": {"model": "gemini-2.5-flash", "api_key": ""},
                "openai": {"model": "gpt-4.1-mini", "api_key": ""},
                "local": {
                    "model": "",
                    "base_url": "http://localhost:1234/v1",
                    "api_key": "",
                },
            }
            changed = True
        ai_defaults = {
            "gemini": {"model": "gemini-2.5-flash", "api_key": "", "thinking_enabled": True},
            "openai": {"model": "gpt-4.1-mini", "api_key": "", "thinking_enabled": True},
            "local": {
                "model": "",
                "base_url": "http://localhost:1234/v1",
                "api_key": "",
                "thinking_enabled": True,
            },
        }
        for provider, provider_defaults in ai_defaults.items():
            if not isinstance(settings["ai_provider"].get(provider), dict):
                settings["ai_provider"][provider] = {}
                changed = True
            for key, value in provider_defaults.items():
                if key not in settings["ai_provider"][provider]:
                    settings["ai_provider"][provider][key] = value
                    changed = True
        if not isinstance(settings.get("memory_provider"), dict):
            settings["memory_provider"] = {
                "semantic_enabled": True,
                "provider": "gemini",
                "models": {
                    "gemini": "gemini-embedding-001",
                    "openai": "text-embedding-3-small",
                    "local": "nomic-embed-text",
                },
                "local_base_url": "http://localhost:11434/v1",
            }
            changed = True
        memory_defaults = {
            "semantic_enabled": True,
            "provider": "gemini",
            "models": {
                "gemini": "gemini-embedding-001",
                "openai": "text-embedding-3-small",
                "local": "nomic-embed-text",
            },
            "local_base_url": "http://localhost:11434/v1",
        }
        for key, value in memory_defaults.items():
            if key not in settings["memory_provider"]:
                settings["memory_provider"][key] = copy.deepcopy(value)
                changed = True
        if changed:
            self._write_json(self.settings_path, settings)
        return settings

    @staticmethod
    def _new_conversation(conversation_id: str, title: str) -> dict:
        return {
            "id": conversation_id,
            "title": title,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }

    @property
    def installation_id(self) -> str:
        return str(self.identity["installation_id"])

    @property
    def person_id(self) -> str:
        return str(self.identity.get("person_id", "owner"))

    @property
    def display_name(self) -> str:
        return str(self.identity.get("display_name", "You"))

    @property
    def conversation_id(self) -> str:
        return str(self.settings.get("active_conversation_id", "main"))

    @property
    def conversations(self) -> list[dict]:
        return copy.deepcopy(self.settings.get("conversations", []))

    @property
    def preferences(self) -> dict:
        return copy.deepcopy(self.settings.get("preferences", {}))

    def create_conversation(self, title: str = "New chat") -> dict:
        title = str(title or "New chat").strip()[:80] or "New chat"
        conversation = self._new_conversation(f"chat-{uuid.uuid4().hex}", title)
        with self._lock:
            self.settings["conversations"] = [conversation, *self.settings["conversations"]]
            self.settings["active_conversation_id"] = conversation["id"]
            self._write_json(self.settings_path, self.settings)
        return copy.deepcopy(conversation)

    def select_conversation(self, conversation_id: str) -> dict:
        with self._lock:
            match = next(
                (item for item in self.settings["conversations"] if item["id"] == conversation_id),
                None,
            )
            if match is None:
                raise KeyError("Conversation not found.")
            self.settings["active_conversation_id"] = conversation_id
            self._write_json(self.settings_path, self.settings)
        return copy.deepcopy(match)

    def delete_conversation(self, conversation_id: str) -> tuple[dict, str]:
        with self._lock:
            conversations = self.settings["conversations"]
            match = next((item for item in conversations if item["id"] == conversation_id), None)
            if match is None:
                raise KeyError("Conversation not found.")
            remaining = [item for item in conversations if item["id"] != conversation_id]
            if not remaining:
                remaining = [self._new_conversation(f"chat-{uuid.uuid4().hex}", "New chat")]
            self.settings["conversations"] = remaining
            if self.conversation_id == conversation_id:
                self.settings["active_conversation_id"] = remaining[0]["id"]
            self._write_json(self.settings_path, self.settings)
        return copy.deepcopy(match), self.conversation_id

    def update_preferences(self, changes: dict) -> dict:
        preferences = self.preferences
        if "always_on_top" in changes:
            preferences["always_on_top"] = bool(changes["always_on_top"])
        if "sidebar_collapsed" in changes:
            preferences["sidebar_collapsed"] = bool(changes["sidebar_collapsed"])
        if "ui_scale" in changes:
            try:
                preferences["ui_scale"] = round(max(0.75, min(1.5, float(changes["ui_scale"]))), 2)
            except (TypeError, ValueError):
                raise ValueError("UI scale must be a number.") from None
        with self._lock:
            self.settings["preferences"] = preferences
            self._write_json(self.settings_path, self.settings)
        return self.preferences

    @property
    def workspaces(self) -> list[dict]:
        return copy.deepcopy(self.settings.get("workspaces", []))

    @property
    def active_workspace_id(self) -> str:
        return str(self.settings.get("active_workspace_id") or "")

    def add_workspace(self, path: str) -> dict:
        try:
            root = Path(str(path or "")).expanduser().resolve(strict=True)
        except (OSError, RuntimeError) as exc:
            raise ValueError("Choose an existing folder.") from exc
        if not root.is_dir():
            raise ValueError("Choose an existing folder.")
        if root == Path(root.anchor):
            raise ValueError("The filesystem root cannot be approved as a workspace.")
        normalized = str(root)
        with self._lock:
            existing = next(
                (item for item in self.settings["workspaces"] if item.get("path") == normalized),
                None,
            )
            if existing:
                self.settings["active_workspace_id"] = existing["id"]
                self._write_json(self.settings_path, self.settings)
                return copy.deepcopy(existing)
            workspace = {
                "id": f"workspace-{uuid.uuid4().hex}",
                "name": root.name or normalized,
                "path": normalized,
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
            self.settings["workspaces"].append(workspace)
            self.settings["active_workspace_id"] = workspace["id"]
            self._write_json(self.settings_path, self.settings)
        return copy.deepcopy(workspace)

    def select_workspace(self, workspace_id: str) -> dict:
        with self._lock:
            match = next((item for item in self.settings["workspaces"] if item["id"] == workspace_id), None)
            if match is None:
                raise KeyError("Approved folder not found.")
            self.settings["active_workspace_id"] = workspace_id
            self._write_json(self.settings_path, self.settings)
        return copy.deepcopy(match)

    def remove_workspace(self, workspace_id: str) -> dict:
        with self._lock:
            match = next((item for item in self.settings["workspaces"] if item["id"] == workspace_id), None)
            if match is None:
                raise KeyError("Approved folder not found.")
            self.settings["workspaces"] = [
                item for item in self.settings["workspaces"] if item["id"] != workspace_id
            ]
            if self.active_workspace_id == workspace_id:
                self.settings["active_workspace_id"] = (
                    self.settings["workspaces"][0]["id"] if self.settings["workspaces"] else ""
                )
            self._write_json(self.settings_path, self.settings)
        return copy.deepcopy(match)

    @property
    def ai_provider(self) -> dict:
        return copy.deepcopy(self.settings.get("ai_provider", {}))

    def update_ai_provider(self, changes: dict) -> dict:
        provider = str(changes.get("provider") or self.ai_provider.get("provider", "gemini"))
        if provider not in {"gemini", "openai", "local"}:
            raise ValueError("Unsupported AI provider.")
        current = self.ai_provider
        current["provider"] = provider
        provider_settings = dict(current.get(provider, {}))
        if "model" in changes:
            provider_settings["model"] = str(changes.get("model") or "").strip()[:200]
        if provider == "local" and "base_url" in changes:
            base_url = str(changes.get("base_url") or "").strip().rstrip("/")
            if not base_url.startswith(("http://", "https://")):
                raise ValueError("The local server URL must begin with http:// or https://.")
            provider_settings["base_url"] = base_url
        if changes.get("clear_api_key"):
            provider_settings["api_key"] = ""
        elif str(changes.get("api_key") or "").strip():
            provider_settings["api_key"] = str(changes["api_key"]).strip()
        if "thinking_enabled" in changes:
            provider_settings["thinking_enabled"] = bool(changes["thinking_enabled"])
        current[provider] = provider_settings
        with self._lock:
            self.settings["ai_provider"] = current
            self._write_json(self.settings_path, self.settings)
        return self.ai_provider

    @property
    def memory_provider(self) -> dict:
        return copy.deepcopy(self.settings.get("memory_provider", {}))

    def update_memory_provider(self, changes: dict) -> dict:
        current = self.memory_provider
        provider = str(changes.get("provider") or current.get("provider", "gemini"))
        if provider not in {"gemini", "openai", "local"}:
            raise ValueError("Unsupported embedding provider.")
        current["provider"] = provider
        if "semantic_enabled" in changes:
            current["semantic_enabled"] = bool(changes["semantic_enabled"])
        if "local_base_url" in changes:
            base_url = str(changes.get("local_base_url") or "").strip().rstrip("/")
            if not base_url.startswith(("http://", "https://")):
                raise ValueError("The local embedding URL must begin with http:// or https://.")
            current["local_base_url"] = base_url
        models = dict(current.get("models", {}))
        if "model" in changes:
            models[provider] = str(changes.get("model") or "").strip()[:200]
        current["models"] = models
        with self._lock:
            self.settings["memory_provider"] = current
            self._write_json(self.settings_path, self.settings)
        return self.memory_provider

    @property
    def system_prompt(self) -> str:
        persona = self.settings.get("persona", {})
        return _build_enriched_prompt(persona)

    @property
    def persona(self) -> dict:
        return copy.deepcopy(self.settings.get("persona") or make_default_persona(1))

    def update_persona(self, changes: dict) -> dict:
        """Validate and persist the editable parts of the desktop persona."""
        persona = self._validated_persona(self.persona, changes)
        with self._lock:
            self.settings["persona"] = persona
            self._write_json(self.settings_path, self.settings)
        return self.persona

    @staticmethod
    def _validated_persona(base: dict, changes: dict) -> dict:
        persona = copy.deepcopy(base)
        for key in ("name", "role_tag", "tagline", "system_prompt", "preset_key"):
            if key in changes:
                persona[key] = str(changes[key]).strip()

        if "traits" in changes:
            traits = changes.get("traits") or []
            if isinstance(traits, str):
                traits = traits.split(",")
            persona["traits"] = [str(item).strip() for item in traits if str(item).strip()][:12]

        if "sliders" in changes:
            sliders = dict(persona.get("sliders", {}))
            slider_changes = changes.get("sliders") or {}
            if not isinstance(slider_changes, dict):
                slider_changes = {}
            for key in ("tone", "verbosity", "formality", "empathy"):
                if key in slider_changes:
                    try:
                        sliders[key] = max(0, min(100, int(slider_changes[key])))
                    except (TypeError, ValueError):
                        pass
            persona["sliders"] = sliders

        if not persona.get("name"):
            persona["name"] = "Petey"
        if not persona.get("system_prompt"):
            raise ValueError("The personality prompt cannot be empty.")
        return persona

    @property
    def saved_personas(self) -> list[dict | None]:
        slots = self.settings.get("saved_personas", [])
        return [copy.deepcopy(item) if isinstance(item, dict) else None for item in slots]

    @staticmethod
    def _persona_slot_index(slot: int) -> int:
        try:
            index = int(slot) - 1
        except (TypeError, ValueError) as exc:
            raise ValueError("Persona slot must be between 1 and 5.") from exc
        if not 0 <= index < PERSONA_SLOT_COUNT:
            raise ValueError("Persona slot must be between 1 and 5.")
        return index

    def save_persona_slot(self, slot: int, changes: dict) -> dict:
        index = self._persona_slot_index(slot)
        persona = self._validated_persona(self.persona, changes)
        persona["slot"] = index + 1
        persona["is_default"] = False
        with self._lock:
            slots = self.saved_personas
            slots[index] = persona
            self.settings["saved_personas"] = slots
            self._write_json(self.settings_path, self.settings)
        return copy.deepcopy(persona)

    def clear_persona_slot(self, slot: int) -> bool:
        index = self._persona_slot_index(slot)
        with self._lock:
            slots = self.saved_personas
            existed = slots[index] is not None
            slots[index] = None
            self.settings["saved_personas"] = slots
            self._write_json(self.settings_path, self.settings)
        return existed

    def selected_model(self, inference_type: str) -> str:
        return str(self.settings.get("selected_models", {}).get(inference_type, ""))

    def update_selected_model(self, inference_type: str, model_slug: str) -> None:
        models = dict(self.settings.get("selected_models", {}))
        if model_slug:
            models[str(inference_type)] = str(model_slug)
        else:
            models.pop(str(inference_type), None)
        self.settings["selected_models"] = models
        self._write_json(self.settings_path, self.settings)
