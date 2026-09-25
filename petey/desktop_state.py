"""Persistent installation identity and settings for the desktop application."""

from __future__ import annotations

import getpass
import copy
import json
import os
import re
import sys
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path

from petey.config import _build_enriched_prompt, make_default_persona
from petey.room_chat import ROOM_PROMPT
from petey.subscription_plans import DEFAULT_PLAN, normalize_plan

PERSONA_SLOT_COUNT = 5
DISCORD_MEMORY_POLICIES = {"room_only", "store", "shared"}
PETEY_CONTROL_SURFACES = {"petey_desktop", "mobile_petey", "discord", "petey_life"}
DESKTOP_THEMES = {"nebula", "studio", "signal", "terminal", "ember"}
COMMAND_RAIL_SECTIONS = {"session", "launch", "addons", "signals"}
DEFAULT_COMMAND_RAIL_SECTIONS = {section: True for section in COMMAND_RAIL_SECTIONS}
DEFAULT_THEME_ACCENTS = {
    "nebula": "#8b5cf6",
    "studio": "#d65f36",
    "signal": "#31d7a5",
    "terminal": "#63ff8f",
    "ember": "#ff8a4c",
}
LEGACY_THEME_MIGRATION = {
    "midnight": "nebula", "ocean": "nebula", "forest": "signal", "paper": "studio",
}
HEX_COLOR = re.compile(r"#[0-9a-fA-F]{6}")
PETEY_CONTROL_ID = re.compile(r"[a-z][a-z0-9_-]{1,63}")


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
        changed = False
        if not identity.get("installation_id"):
            identity = {
                "installation_id": f"desktop-{uuid.uuid4()}",
                "person_id": "owner",
                "display_name": "User",
                "display_name_customized": False,
                "default_conversation_id": "main",
            }
            changed = True
        elif "display_name_customized" not in identity:
            legacy_name = str(identity.get("display_name") or "").strip()
            system_name = str(getpass.getuser() or "").strip()
            was_automatic = not legacy_name or legacy_name.casefold() == system_name.casefold()
            identity["display_name"] = "User" if was_automatic else legacy_name
            identity["display_name_customized"] = not was_automatic
            changed = True
        if not str(identity.get("display_name") or "").strip():
            identity["display_name"] = "User"
            identity["display_name_customized"] = False
            changed = True
        if changed:
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
        for conversation in settings["conversations"]:
            if not isinstance(conversation, dict):
                continue
            persona_slot = self._normalized_conversation_persona_slot(
                conversation.get("persona_slot")
            )
            if conversation.get("persona_slot") != persona_slot or "persona_slot" not in conversation:
                conversation["persona_slot"] = persona_slot
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
        defaults = {
            "always_on_top": False,
            "sidebar_collapsed": False,
            "ui_scale": 1.0,
            "visual_mode": False,
            "visual_style": "neural_core",
            "command_rail_enabled": True,
            "command_rail_open": True,
            "command_rail_sections": copy.deepcopy(DEFAULT_COMMAND_RAIL_SECTIONS),
            "theme": "nebula",
            "theme_accents": copy.deepcopy(DEFAULT_THEME_ACCENTS),
        }
        for key, value in defaults.items():
            if key not in settings["preferences"]:
                settings["preferences"][key] = value
                changed = True
        try:
            plan_preview = normalize_plan(settings.get("plan_preview"))
        except ValueError:
            plan_preview = copy.deepcopy(DEFAULT_PLAN)
        if settings.get("plan_preview") != plan_preview:
            settings["plan_preview"] = plan_preview
            changed = True
        saved_theme = str(settings["preferences"].get("theme") or "")
        migrated_theme = LEGACY_THEME_MIGRATION.get(saved_theme, saved_theme)
        if migrated_theme not in DESKTOP_THEMES:
            migrated_theme = "nebula"
        if settings["preferences"].get("theme") != migrated_theme:
            settings["preferences"]["theme"] = migrated_theme
            changed = True
        if "interface_layout" in settings["preferences"]:
            settings["preferences"].pop("interface_layout", None)
            changed = True
        saved_rail_sections = settings["preferences"].get("command_rail_sections")
        normalized_rail_sections = copy.deepcopy(DEFAULT_COMMAND_RAIL_SECTIONS)
        if isinstance(saved_rail_sections, dict):
            for section in COMMAND_RAIL_SECTIONS:
                if isinstance(saved_rail_sections.get(section), bool):
                    normalized_rail_sections[section] = saved_rail_sections[section]
        if saved_rail_sections != normalized_rail_sections:
            settings["preferences"]["command_rail_sections"] = normalized_rail_sections
            changed = True
        saved_accents = settings["preferences"].get("theme_accents")
        normalized_accents = copy.deepcopy(DEFAULT_THEME_ACCENTS)
        if isinstance(saved_accents, dict):
            for theme in DESKTOP_THEMES:
                color = str(saved_accents.get(theme) or "")
                if HEX_COLOR.fullmatch(color):
                    normalized_accents[theme] = color.lower()
        if saved_accents != normalized_accents:
            settings["preferences"]["theme_accents"] = normalized_accents
            changed = True
        if not isinstance(settings.get("approved_folders"), list):
            legacy_folders = settings.get("workspaces")
            settings["approved_folders"] = legacy_folders if isinstance(legacy_folders, list) else []
            changed = True
        if "workspaces" in settings or "active_workspace_id" in settings:
            settings.pop("workspaces", None)
            settings.pop("active_workspace_id", None)
            changed = True
        if not isinstance(settings.get("tools"), dict):
            settings["tools"] = {}
            changed = True
        if not isinstance(settings.get("addons"), dict):
            settings["addons"] = {"discord": True}
            changed = True
        elif not isinstance(settings["addons"].get("discord", True), bool):
            settings["addons"]["discord"] = True
            changed = True
        if "addon_discord_tools" in settings:
            settings.pop("addon_discord_tools", None)
            changed = True
        normalized_control = self._normalized_petey_control(settings.get("petey_control"))
        if settings.get("petey_control") != normalized_control:
            settings["petey_control"] = normalized_control
            changed = True
        if not isinstance(settings.get("discord"), dict):
            settings["discord"] = {
                "bot_token": "", "pace": "auto", "watched_topics": [],
                "room_prompt": ROOM_PROMPT, "auto_connect": False,
                "last_location": {}, "persona_slot": None,
                "memory_policy": "room_only",
            }
            changed = True
        elif not isinstance(settings["discord"].get("bot_token"), str):
            settings["discord"]["bot_token"] = ""
            changed = True
        if settings["discord"].get("pace") not in {"auto", "relaxed", "balanced", "lively", "fast"}:
            settings["discord"]["pace"] = "auto"
            changed = True
        try:
            watched_topics = self._normalize_discord_topics(
                settings["discord"].get("watched_topics", [])
            )
        except ValueError:
            watched_topics = []
        if settings["discord"].get("watched_topics") != watched_topics:
            settings["discord"]["watched_topics"] = watched_topics
            changed = True
        room_prompt = settings["discord"].get("room_prompt")
        if not isinstance(room_prompt, str) or not room_prompt.strip() or len(room_prompt) > 12000:
            settings["discord"]["room_prompt"] = ROOM_PROMPT
            changed = True
        discord_persona_slot = self._normalized_conversation_persona_slot(
            settings["discord"].get("persona_slot")
        )
        if (discord_persona_slot is not None
                and not isinstance(settings["saved_personas"][discord_persona_slot - 1], dict)):
            discord_persona_slot = None
        if (settings["discord"].get("persona_slot") != discord_persona_slot
                or "persona_slot" not in settings["discord"]):
            settings["discord"]["persona_slot"] = discord_persona_slot
            changed = True
        if not isinstance(settings["discord"].get("auto_connect"), bool):
            settings["discord"]["auto_connect"] = False
            changed = True
        if settings["discord"].get("memory_policy") not in DISCORD_MEMORY_POLICIES:
            settings["discord"]["memory_policy"] = "room_only"
            changed = True
        location = settings["discord"].get("last_location")
        required_location = {"guild_id", "channel_id", "guild", "channel"}
        if not isinstance(location, dict) or not required_location.issubset(location):
            settings["discord"]["last_location"] = {}
            changed = True
        elif (any(not isinstance(location.get(key), str) for key in required_location)
              or not location.get("guild_id", "").isdigit()
              or not location.get("channel_id", "").isdigit()):
            settings["discord"]["last_location"] = {}
            changed = True
        filesystem_tool = settings["tools"].get("filesystem")
        if not isinstance(filesystem_tool, dict):
            settings["tools"]["filesystem"] = {"enabled": False}
            changed = True
        elif not isinstance(filesystem_tool.get("enabled"), bool):
            filesystem_tool["enabled"] = False
            changed = True
        if not isinstance(settings.get("ai_provider"), dict):
            settings["ai_provider"] = {
                "provider": "gemini",
                "gemini": {
                    "model": "gemini-2.5-flash",
                    "vision_model": "gemini-2.5-flash",
                    "api_key": "",
                },
                "openai": {"model": "gpt-4.1-mini", "api_key": ""},
                "local": {
                    "model": "",
                    "base_url": "http://localhost:1234/v1",
                    "api_key": "",
                },
            }
            changed = True
        ai_defaults = {
            "deapi": {"api_key": ""},
            "gemini": {
                "model": "gemini-2.5-flash",
                "vision_model": "gemini-2.5-flash",
                "api_key": "",
                "thinking_enabled": True,
            },
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
        speech_defaults = {
            "provider": "automatic",
            "provider_selection_version": 2,
            "deapi_model": "Qwen3_TTS_12Hz_1_7B_CustomVoice",
            "deapi_voice": "Vivian",
            "gemini_model": "gemini-3.1-flash-tts-preview",
            "gemini_voice": "Kore",
            "openai_model": "gpt-4o-mini-tts",
            "openai_voice": "marin",
            "style": "",
            "consistent_voice": True,
            "auto_speak": False,
        }
        if not isinstance(settings.get("speech"), dict):
            settings["speech"] = copy.deepcopy(speech_defaults)
            changed = True
        legacy_speech_provider = "provider_selection_version" not in settings["speech"]
        for key, value in speech_defaults.items():
            if key not in settings["speech"]:
                settings["speech"][key] = value
                changed = True
        if legacy_speech_provider and settings["speech"].get("provider") == "deapi":
            settings["speech"]["provider"] = "automatic"
            changed = True
        if legacy_speech_provider:
            settings["speech"]["provider_selection_version"] = 2
            changed = True
        for saved_persona in settings["saved_personas"]:
            if not isinstance(saved_persona, dict):
                continue
            saved_speech = saved_persona.get("speech")
            if not isinstance(saved_speech, dict):
                saved_persona["speech"] = copy.deepcopy(settings["speech"])
                changed = True
            elif (
                legacy_speech_provider
                and saved_speech.get("provider") == "deapi"
                and "provider_selection_version" not in saved_speech
            ):
                saved_speech["provider"] = "automatic"
                changed = True
        legacy_gemini_voice_input = (
            isinstance(settings.get("voice_input"), dict)
            and settings["voice_input"].get("provider") == "gemini"
            and "gemini_model" not in settings["voice_input"]
        )
        legacy_voice_latency = (
            isinstance(settings.get("voice_input"), dict)
            and "latency_tuning_version" not in settings["voice_input"]
        )
        legacy_transcription_provider = (
            isinstance(settings.get("voice_input"), dict)
            and "provider_selection_version" not in settings["voice_input"]
        )
        voice_input_defaults = {
            "mode": "disabled",
            "muted": False,
            "provider": "automatic",
            "model": "WhisperLargeV3",
            "gemini_model": "gemini-3.5-transcribe",
            "local_whisper_model": "small",
            "local_whisper_device": "auto",
            "wake_word": "Petey",
            "device_id": "",
            "sensitivity": "normal",
            "wake_ack_style": "fast",
            "wake_ack_delay_ms": 300,
            "submit_silence_ms": 600,
            "follow_up_seconds": 8,
            "latency_tuning_version": 1,
            "provider_selection_version": 3,
        }
        if not isinstance(settings.get("voice_input"), dict):
            settings["voice_input"] = copy.deepcopy(voice_input_defaults)
            changed = True
        for key, value in voice_input_defaults.items():
            if key not in settings["voice_input"]:
                settings["voice_input"][key] = value
                changed = True
        if settings["voice_input"].get("provider") == "local":
            settings["voice_input"]["provider"] = "local_whisper"
            changed = True
        for obsolete_key in ("local_base_url", "local_model"):
            if obsolete_key in settings["voice_input"]:
                settings["voice_input"].pop(obsolete_key, None)
                changed = True
        if legacy_voice_latency:
            if settings["voice_input"].get("wake_ack_delay_ms") == 500:
                settings["voice_input"]["wake_ack_delay_ms"] = 300
            if settings["voice_input"].get("submit_silence_ms") == 800:
                settings["voice_input"]["submit_silence_ms"] = 600
            settings["voice_input"]["latency_tuning_version"] = 1
            changed = True
        if legacy_gemini_voice_input:
            settings["voice_input"]["gemini_model"] = settings["voice_input"].get(
                "model", "gemini-3.5-transcribe"
            )
            settings["voice_input"]["provider"] = "automatic"
            settings["voice_input"]["model"] = "WhisperLargeV3"
            changed = True
        elif legacy_transcription_provider:
            if settings["voice_input"].get("provider") == "deapi":
                settings["voice_input"]["provider"] = "automatic"
            settings["voice_input"]["provider_selection_version"] = 3
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
    def _new_conversation(
        conversation_id: str, title: str, persona_slot: int | None = None
    ) -> dict:
        return {
            "id": conversation_id,
            "title": title,
            "persona_slot": persona_slot,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }

    @staticmethod
    def _normalized_conversation_persona_slot(value: object) -> int | None:
        if value is None or value == "" or value == "system" or type(value) is bool:
            return None
        try:
            slot = int(value)
        except (TypeError, ValueError):
            return None
        return slot if 1 <= slot <= PERSONA_SLOT_COUNT else None

    @property
    def installation_id(self) -> str:
        return str(self.identity["installation_id"])

    @property
    def person_id(self) -> str:
        return str(self.identity.get("person_id", "owner"))

    @property
    def display_name(self) -> str:
        return str(self.identity.get("display_name") or "User")

    def update_display_name(self, display_name: str) -> str:
        display_name = str(display_name or "").strip()
        if not display_name:
            raise ValueError("Enter a user name.")
        if len(display_name) > 50:
            raise ValueError("The user name must be 50 characters or fewer.")
        with self._lock:
            self.identity["display_name"] = display_name
            self.identity["display_name_customized"] = True
            self._write_json(self.identity_path, self.identity)
        return self.display_name

    @property
    def conversation_id(self) -> str:
        return str(self.settings.get("active_conversation_id", "main"))

    @property
    def conversations(self) -> list[dict]:
        return copy.deepcopy(self.settings.get("conversations", []))

    @property
    def conversation(self) -> dict:
        match = next(
            (item for item in self.settings.get("conversations", [])
             if item.get("id") == self.conversation_id),
            None,
        )
        return copy.deepcopy(match or self._new_conversation(self.conversation_id, "New chat"))

    @property
    def conversation_persona(self) -> dict:
        slot = self._normalized_conversation_persona_slot(
            self.conversation.get("persona_slot")
        )
        if slot is not None:
            saved = self.saved_personas[slot - 1]
            if isinstance(saved, dict):
                return copy.deepcopy(saved)
        return self.persona

    @property
    def conversation_persona_options(self) -> list[dict]:
        options = [{
            "slot": None,
            "name": str(self.persona.get("name") or "Petey")[:80],
            "role_tag": str(self.persona.get("role_tag") or "System persona")[:80],
            "system": True,
        }]
        for index, saved in enumerate(self.saved_personas, 1):
            if not isinstance(saved, dict):
                continue
            options.append({
                "slot": index,
                "name": str(saved.get("name") or f"Profile {index}")[:80],
                "role_tag": str(saved.get("role_tag") or "Saved profile")[:80],
                "system": False,
            })
        return options

    @property
    def conversation_speech(self) -> dict:
        slot = self._normalized_conversation_persona_slot(
            self.conversation.get("persona_slot")
        )
        if slot is None:
            return self.speech
        saved = self.saved_personas[slot - 1]
        if not isinstance(saved, dict) or not isinstance(saved.get("speech"), dict):
            return self.speech
        speech = self._validated_speech(self.speech, saved["speech"])
        if speech.get("provider") != "disabled":
            speech["auto_speak"] = bool(self.speech.get("auto_speak", False))
        return speech

    @property
    def preferences(self) -> dict:
        return copy.deepcopy(self.settings.get("preferences", {}))

    @property
    def plan_preview(self) -> dict:
        return copy.deepcopy(self.settings.get("plan_preview", DEFAULT_PLAN))

    def update_plan_preview(self, changes: dict) -> dict:
        plan = normalize_plan(changes)
        with self._lock:
            self.settings["plan_preview"] = plan
            self._write_json(self.settings_path, self.settings)
        return self.plan_preview

    def create_conversation(
        self, title: str = "New chat", persona_slot: object = None
    ) -> dict:
        title = str(title or "New chat").strip()[:80] or "New chat"
        slot = self._validated_conversation_persona_slot(persona_slot)
        conversation = self._new_conversation(
            f"chat-{uuid.uuid4().hex}", title, slot
        )
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

    def _validated_conversation_persona_slot(self, value: object) -> int | None:
        slot = self._normalized_conversation_persona_slot(value)
        if value is not None and value != "" and value != "system" and slot is None:
            raise ValueError("Choose a saved Petey profile or the system persona.")
        if slot is not None and not isinstance(self.saved_personas[slot - 1], dict):
            raise ValueError("That saved Petey profile is empty.")
        return slot

    def assign_conversation_persona(
        self, conversation_id: str, persona_slot: object
    ) -> dict:
        slot = self._validated_conversation_persona_slot(persona_slot)
        with self._lock:
            match = next(
                (item for item in self.settings["conversations"]
                 if item["id"] == conversation_id),
                None,
            )
            if match is None:
                raise KeyError("Conversation not found.")
            match["persona_slot"] = slot
            self._write_json(self.settings_path, self.settings)
        return copy.deepcopy(match)

    def rename_conversation(self, conversation_id: str, title: str) -> dict:
        title = str(title or "").strip()
        if not title:
            raise ValueError("Enter a chat name.")
        if len(title) > 80:
            raise ValueError("Chat names must be 80 characters or fewer.")
        with self._lock:
            match = next(
                (item for item in self.settings["conversations"] if item["id"] == conversation_id),
                None,
            )
            if match is None:
                raise KeyError("Conversation not found.")
            match["title"] = title
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
        theme = str(changes.get("theme") or preferences.get("theme") or "nebula")
        if "theme" in changes:
            if theme not in DESKTOP_THEMES:
                raise ValueError("Choose a supported theme.")
        if "theme_accent" in changes:
            color = str(changes["theme_accent"] or "").lower()
            if theme not in DESKTOP_THEMES or not HEX_COLOR.fullmatch(color):
                raise ValueError("Choose a valid theme accent color.")
        if "theme" in changes:
            preferences["theme"] = theme
        if "command_rail_enabled" in changes:
            preferences["command_rail_enabled"] = bool(changes["command_rail_enabled"])
        if "command_rail_open" in changes:
            preferences["command_rail_open"] = bool(changes["command_rail_open"])
        if "command_rail_sections" in changes:
            sections = changes["command_rail_sections"]
            if not isinstance(sections, dict) or any(
                key not in COMMAND_RAIL_SECTIONS or not isinstance(value, bool)
                for key, value in sections.items()
            ):
                raise ValueError("Choose valid Command Center rail sections.")
            normalized = copy.deepcopy(
                preferences.get("command_rail_sections") or DEFAULT_COMMAND_RAIL_SECTIONS
            )
            normalized.update(sections)
            preferences["command_rail_sections"] = normalized
        if "theme_accent" in changes:
            accents = copy.deepcopy(preferences.get("theme_accents") or DEFAULT_THEME_ACCENTS)
            accents[theme] = color
            preferences["theme_accents"] = accents
        if "always_on_top" in changes:
            preferences["always_on_top"] = bool(changes["always_on_top"])
        if "sidebar_collapsed" in changes:
            preferences["sidebar_collapsed"] = bool(changes["sidebar_collapsed"])
        if "visual_mode" in changes:
            preferences["visual_mode"] = bool(changes["visual_mode"])
        if "visual_style" in changes:
            style = str(changes.get("visual_style") or "neural_core")
            if style not in {
                "neural_core", "synapse_drift", "orbital_mind", "signal_bloom",
                "aurora_flow", "constellation_field",
            }:
                raise ValueError("Choose a supported visual style.")
            preferences["visual_style"] = style
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
    def tools(self) -> dict:
        return copy.deepcopy(self.settings.get("tools", {"filesystem": {"enabled": False}}))

    def update_tool(self, tool_id: str, enabled: bool) -> dict:
        if tool_id != "filesystem":
            raise ValueError("Unknown tool connection.")
        tools = self.tools
        tools[tool_id] = {"enabled": bool(enabled)}
        with self._lock:
            self.settings["tools"] = tools
            self._write_json(self.settings_path, self.settings)
        return copy.deepcopy(tools[tool_id])

    @property
    def approved_folders(self) -> list[dict]:
        return copy.deepcopy(self.settings.get("approved_folders", []))

    def add_approved_folder(self, path: str) -> dict:
        try:
            root = Path(str(path or "")).expanduser().resolve(strict=True)
        except (OSError, RuntimeError) as exc:
            raise ValueError("Choose an existing folder.") from exc
        if not root.is_dir():
            raise ValueError("Choose an existing folder.")
        if root == Path(root.anchor):
            raise ValueError("The filesystem root cannot be approved.")
        normalized = str(root)
        with self._lock:
            existing = next(
                (item for item in self.settings["approved_folders"] if item.get("path") == normalized),
                None,
            )
            if existing:
                return copy.deepcopy(existing)
            folder = {
                "id": f"folder-{uuid.uuid4().hex}",
                "name": root.name or normalized,
                "path": normalized,
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
            self.settings["approved_folders"].append(folder)
            self._write_json(self.settings_path, self.settings)
        return copy.deepcopy(folder)

    def remove_approved_folder(self, folder_id: str) -> dict:
        with self._lock:
            match = next((item for item in self.settings["approved_folders"] if item["id"] == folder_id), None)
            if match is None:
                raise KeyError("Approved folder not found.")
            self.settings["approved_folders"] = [
                item for item in self.settings["approved_folders"] if item["id"] != folder_id
            ]
            self._write_json(self.settings_path, self.settings)
        return copy.deepcopy(match)

    @property
    def ai_provider(self) -> dict:
        return copy.deepcopy(self.settings.get("ai_provider", {}))

    @property
    def discord_bot_token(self) -> str:
        saved = str(self.settings.get("discord", {}).get("bot_token") or "").strip()
        return saved or str(os.getenv("DISCORD_BOT_TOKEN", "")).strip()

    @property
    def discord_bot_token_status(self) -> dict:
        saved = bool(str(self.settings.get("discord", {}).get("bot_token") or "").strip())
        environment = bool(str(os.getenv("DISCORD_BOT_TOKEN", "")).strip())
        return {
            "has_token": saved or environment,
            "has_saved_token": saved,
            "source": "saved" if saved else "environment" if environment else "none",
        }

    def update_discord_bot_token(self, token: str = "", clear: bool = False) -> dict:
        if not isinstance(token, str) or len(token) > 4096:
            raise ValueError("Discord bot token must be text of at most 4096 characters.")
        if not clear and not token.strip():
            raise ValueError("Enter a Discord bot token.")
        with self._lock:
            current = dict(self.settings.get("discord") or {})
            current["bot_token"] = "" if clear else token.strip()
            self.settings["discord"] = current
            self._write_json(self.settings_path, self.settings)
        return self.discord_bot_token_status

    @property
    def discord_pace(self) -> str:
        pace = str(self.settings.get("discord", {}).get("pace") or "auto")
        return pace if pace in {"auto", "relaxed", "balanced", "lively", "fast"} else "auto"

    def update_discord_pace(self, pace: str) -> str:
        if pace not in {"auto", "relaxed", "balanced", "lively", "fast"}:
            raise ValueError("Choose a valid Discord pacing mode.")
        with self._lock:
            current = dict(self.settings.get("discord") or {})
            current["pace"] = pace
            self.settings["discord"] = current
            self._write_json(self.settings_path, self.settings)
        return self.discord_pace

    @staticmethod
    def _normalize_discord_topics(topics) -> list[str]:
        if not isinstance(topics, list) or len(topics) > 20:
            raise ValueError("Enter up to 20 Discord watched topics.")
        normalized = []
        seen = set()
        for topic in topics:
            if not isinstance(topic, str):
                raise ValueError("Each Discord watched topic must be text.")
            topic = " ".join(topic.split())
            if not 1 <= len(topic) <= 50:
                raise ValueError("Each Discord watched topic must be 1–50 characters.")
            key = topic.casefold()
            if key not in seen:
                normalized.append(topic)
                seen.add(key)
        return normalized

    @property
    def discord_watched_topics(self) -> list[str]:
        try:
            return self._normalize_discord_topics(
                self.settings.get("discord", {}).get("watched_topics", [])
            )
        except ValueError:
            return []

    def update_discord_watched_topics(self, topics) -> list[str]:
        topics = self._normalize_discord_topics(topics)
        with self._lock:
            current = dict(self.settings.get("discord") or {})
            current["watched_topics"] = topics
            self.settings["discord"] = current
            self._write_json(self.settings_path, self.settings)
        return self.discord_watched_topics

    @property
    def discord_room_prompt(self) -> str:
        prompt = self.settings.get("discord", {}).get("room_prompt")
        return prompt if isinstance(prompt, str) and prompt.strip() else ROOM_PROMPT

    def update_discord_room_prompt(self, prompt="", reset=False) -> str:
        if reset:
            prompt = ROOM_PROMPT
        if not isinstance(prompt, str) or not 1 <= len(prompt.strip()) <= 12000:
            raise ValueError("Discord room prompt must contain 1–12,000 characters.")
        saved_prompt = ROOM_PROMPT if reset else prompt.strip()
        with self._lock:
            current = dict(self.settings.get("discord") or {})
            current["room_prompt"] = saved_prompt
            self.settings["discord"] = current
            self._write_json(self.settings_path, self.settings)
        return self.discord_room_prompt

    @property
    def discord_persona_slot(self) -> int | None:
        slot = self._normalized_conversation_persona_slot(
            self.settings.get("discord", {}).get("persona_slot")
        )
        if slot is None or not isinstance(self.saved_personas[slot - 1], dict):
            return None
        return slot

    @property
    def discord_persona_options(self) -> list[dict]:
        options = [{
            "slot": None,
            "name": "Discord default",
            "role_tag": "Room personality",
        }]
        for index, saved in enumerate(self.saved_personas, 1):
            if not isinstance(saved, dict):
                continue
            options.append({
                "slot": index,
                "name": str(saved.get("name") or f"Profile {index}")[:80],
                "role_tag": str(saved.get("role_tag") or "Saved profile")[:80],
            })
        return options

    @property
    def discord_system_prompt(self) -> str:
        slot = self.discord_persona_slot
        if slot is None:
            return self.discord_room_prompt
        persona = self.saved_personas[slot - 1]
        return (
            _build_enriched_prompt(persona)
            + "\n\nPROFILE BOUNDARY: This selected profile exclusively controls your identity, "
              "traits, tone, and communication style. Room history supplies conversational "
              "context only; never inherit another personality from earlier replies."
            + "\n\nDiscord room instructions:\n"
            + self.discord_room_prompt
        )

    def update_discord_persona(self, persona_slot: object) -> int | None:
        slot = self._validated_conversation_persona_slot(persona_slot)
        with self._lock:
            current = dict(self.settings.get("discord") or {})
            current["persona_slot"] = slot
            self.settings["discord"] = current
            self._write_json(self.settings_path, self.settings)
        return self.discord_persona_slot

    @property
    def discord_memory_policy(self) -> str:
        policy = self.settings.get("discord", {}).get("memory_policy")
        return policy if policy in DISCORD_MEMORY_POLICIES else "room_only"

    def update_discord_memory_policy(self, policy: object) -> str:
        if policy not in DISCORD_MEMORY_POLICIES:
            raise ValueError("Choose a valid Discord memory access level.")
        with self._lock:
            current = dict(self.settings.get("discord") or {})
            current["memory_policy"] = policy
            self.settings["discord"] = current
            self._write_json(self.settings_path, self.settings)
        return self.discord_memory_policy

    @property
    def discord_auto_connect(self) -> bool:
        return self.settings.get("discord", {}).get("auto_connect") is True

    def update_discord_auto_connect(self, enabled) -> bool:
        if not isinstance(enabled, bool):
            raise ValueError("Choose whether Discord auto-connect is enabled.")
        with self._lock:
            current = dict(self.settings.get("discord") or {})
            current["auto_connect"] = enabled
            self.settings["discord"] = current
            self._write_json(self.settings_path, self.settings)
        return self.discord_auto_connect

    @property
    def discord_last_location(self) -> dict:
        location = self.settings.get("discord", {}).get("last_location")
        return copy.deepcopy(location) if isinstance(location, dict) else {}

    def update_discord_last_location(self, guild_id, channel_id, guild="", channel="") -> dict:
        location = {
            "guild_id": str(guild_id or "")[:24],
            "channel_id": str(channel_id or "")[:24],
            "guild": str(guild or "")[:100],
            "channel": str(channel or "")[:100],
        }
        if not location["guild_id"].isdigit() or not location["channel_id"].isdigit():
            raise ValueError("Choose a Discord server and channel first.")
        with self._lock:
            current = dict(self.settings.get("discord") or {})
            current["last_location"] = location
            self.settings["discord"] = current
            self._write_json(self.settings_path, self.settings)
        return self.discord_last_location

    def addon_enabled(self, addon_id: str, default=False) -> bool:
        value = self.settings.get("addons", {}).get(str(addon_id))
        return value if isinstance(value, bool) else bool(default)

    def update_addon_enabled(self, addon_id: str, enabled) -> bool:
        addon_id = str(addon_id or "")
        if not re.fullmatch(r"[a-z][a-z0-9_-]{1,48}", addon_id):
            raise ValueError("Choose a valid add-on.")
        if not isinstance(enabled, bool):
            raise ValueError("Add-on enabled must be true or false.")
        with self._lock:
            addons = dict(self.settings.get("addons") or {})
            addons[addon_id] = enabled
            self.settings["addons"] = addons
            self._write_json(self.settings_path, self.settings)
        return self.addon_enabled(addon_id)

    @staticmethod
    def _normalized_petey_control(value) -> dict:
        if not isinstance(value, dict):
            return {}
        normalized = {}
        for addon_id, raw in value.items():
            addon_id = str(addon_id or "")
            if not PETEY_CONTROL_ID.fullmatch(addon_id) or not isinstance(raw, dict):
                continue
            surfaces = raw.get("surfaces") if isinstance(raw.get("surfaces"), dict) else {}
            capabilities = raw.get("capabilities") if isinstance(raw.get("capabilities"), dict) else {}
            usage = raw.get("usage") if isinstance(raw.get("usage"), dict) else {}
            normalized_capabilities = {}
            for capability, policy in capabilities.items():
                capability = str(capability or "")
                if not PETEY_CONTROL_ID.fullmatch(capability) or not isinstance(policy, dict):
                    continue
                try:
                    daily_limit = max(0, min(1000, int(policy.get("daily_limit", 0))))
                except (TypeError, ValueError):
                    daily_limit = 0
                normalized_capabilities[capability] = {
                    "enabled": policy.get("enabled") is True,
                    "daily_limit": daily_limit,
                }
            normalized_usage = {}
            for day, counts in usage.items():
                if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(day)) or not isinstance(counts, dict):
                    continue
                day_counts = {}
                for capability, count in counts.items():
                    if PETEY_CONTROL_ID.fullmatch(str(capability or "")):
                        try:
                            day_counts[str(capability)] = max(0, int(count))
                        except (TypeError, ValueError):
                            pass
                if day_counts:
                    normalized_usage[str(day)] = day_counts
            normalized[addon_id] = {
                "enabled": raw.get("enabled") is True,
                "surfaces": {
                    surface: surfaces.get(surface) is True
                    for surface in PETEY_CONTROL_SURFACES
                },
                "capabilities": normalized_capabilities,
                "usage": normalized_usage,
            }
        return normalized

    @staticmethod
    def _control_capability_definitions(capabilities) -> dict:
        result = {}
        for item in capabilities if isinstance(capabilities, list) else []:
            if not isinstance(item, dict):
                continue
            capability = str(item.get("id") or "")
            if not PETEY_CONTROL_ID.fullmatch(capability):
                continue
            try:
                default_daily_limit = int(item.get("default_daily_limit") or 0)
            except (TypeError, ValueError):
                default_daily_limit = 0
            result[capability] = {
                "id": capability,
                "label": str(item.get("label") or capability.replace("_", " ").title())[:80],
                "metered": item.get("metered") is True,
                "default_daily_limit": max(0, min(1000, default_daily_limit)),
            }
        return result

    def petey_control_status(self, addon_id: str, capabilities: list[dict]) -> dict:
        definitions = self._control_capability_definitions(capabilities)
        saved = self.settings.get("petey_control", {}).get(str(addon_id), {})
        surfaces = saved.get("surfaces") if isinstance(saved.get("surfaces"), dict) else {}
        policies = saved.get("capabilities") if isinstance(saved.get("capabilities"), dict) else {}
        today = datetime.now().astimezone().date().isoformat()
        usage = saved.get("usage", {}).get(today, {}) if isinstance(saved.get("usage"), dict) else {}
        return {
            "enabled": saved.get("enabled") is True,
            "surfaces": {
                "petey_desktop": surfaces.get("petey_desktop", True) is True,
                "mobile_petey": surfaces.get("mobile_petey", True) is True,
                "discord": surfaces.get("discord") is True,
                "petey_life": surfaces.get("petey_life") is True,
            },
            "capabilities": [{
                **definition,
                "enabled": policies.get(capability, {}).get("enabled", True) is True,
                "daily_limit": int(policies.get(capability, {}).get(
                    "daily_limit", definition["default_daily_limit"]
                )),
                "used_today": int(usage.get(capability, 0)),
            } for capability, definition in definitions.items()],
        }

    def update_petey_control(self, addon_id: str, changes: dict, capabilities: list[dict]) -> dict:
        addon_id = str(addon_id or "")
        definitions = self._control_capability_definitions(capabilities)
        if not PETEY_CONTROL_ID.fullmatch(addon_id) or not definitions:
            raise ValueError("This add-on does not expose controllable capabilities.")
        if not isinstance(changes, dict):
            raise ValueError("Petey control settings require an object.")
        with self._lock:
            controls = copy.deepcopy(self.settings.get("petey_control") or {})
            saved_current = controls.get(addon_id)
            if isinstance(saved_current, dict):
                current = self._normalized_petey_control(
                    {addon_id: saved_current}
                ).get(addon_id, {})
            else:
                current = {
                    "enabled": False,
                    "surfaces": {
                        "petey_desktop": True, "mobile_petey": True,
                        "discord": False, "petey_life": False,
                    },
                    "capabilities": {}, "usage": {},
                }
            if "enabled" in changes:
                if not isinstance(changes["enabled"], bool):
                    raise ValueError("Allow Petey to control must be true or false.")
                current["enabled"] = changes["enabled"]
            if "surfaces" in changes:
                if not isinstance(changes["surfaces"], dict):
                    raise ValueError("Surface permissions require an object.")
                for surface, enabled in changes["surfaces"].items():
                    if surface not in PETEY_CONTROL_SURFACES or not isinstance(enabled, bool):
                        raise ValueError("Choose valid surface permissions.")
                    current["surfaces"][surface] = enabled
            if "capabilities" in changes:
                if not isinstance(changes["capabilities"], dict):
                    raise ValueError("Capability permissions require an object.")
                for capability, policy in changes["capabilities"].items():
                    if capability not in definitions or not isinstance(policy, dict):
                        raise ValueError("Choose a valid add-on capability.")
                    saved_policy = dict(current["capabilities"].get(capability) or {})
                    if "enabled" in policy:
                        if not isinstance(policy["enabled"], bool):
                            raise ValueError("Capability enabled must be true or false.")
                        saved_policy["enabled"] = policy["enabled"]
                    if "daily_limit" in policy:
                        try:
                            limit = int(policy["daily_limit"])
                        except (TypeError, ValueError) as exc:
                            raise ValueError("Daily limits must be whole numbers.") from exc
                        if limit < 0 or limit > 1000:
                            raise ValueError("Daily limits must be between 0 and 1000.")
                        saved_policy["daily_limit"] = limit
                    current["capabilities"][capability] = saved_policy
            controls[addon_id] = current
            self.settings["petey_control"] = controls
            self._write_json(self.settings_path, self.settings)
        return self.petey_control_status(addon_id, capabilities)

    def authorize_petey_control(
        self, addon_id: str, capability: str, surface: str, *, explicit: bool,
        capabilities: list[dict], consume: bool = False,
    ) -> dict:
        with self._lock:
            status = self.petey_control_status(addon_id, capabilities)
            selected = next(
                (item for item in status["capabilities"] if item["id"] == capability), None
            )
            if not status["enabled"] or not status["surfaces"].get(surface, False):
                raise ValueError("Petey is not allowed to control this add-on on this surface.")
            if selected is None or not selected["enabled"]:
                raise ValueError("Petey is not allowed to use this capability.")
            if not explicit and selected["metered"]:
                if selected["daily_limit"] <= selected["used_today"]:
                    raise ValueError("Petey reached the autonomous daily limit for this capability.")
                if consume:
                    controls = copy.deepcopy(self.settings.get("petey_control") or {})
                    current = controls.setdefault(addon_id, {})
                    usage = current.setdefault("usage", {})
                    today = datetime.now().astimezone().date().isoformat()
                    counts = usage.setdefault(today, {})
                    counts[capability] = int(counts.get(capability, 0)) + 1
                    self.settings["petey_control"] = controls
                    self._write_json(self.settings_path, self.settings)
                    selected["used_today"] += 1
            return {"explicit": bool(explicit), "policy": selected}

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
        if "vision_model" in changes:
            gemini_settings = dict(current.get("gemini", {}))
            vision_model = str(changes.get("vision_model") or "").strip()[:200]
            if not vision_model:
                raise ValueError("Choose a Gemini vision model.")
            gemini_settings["vision_model"] = vision_model
            current["gemini"] = gemini_settings
        if provider == "gemini":
            current["gemini"]["vision_model"] = provider_settings.get("model") or "gemini-2.5-flash"
        with self._lock:
            self.settings["ai_provider"] = current
            self._write_json(self.settings_path, self.settings)
        return self.ai_provider

    @property
    def speech(self) -> dict:
        return copy.deepcopy(self.settings.get("speech", {}))

    def update_provider_key(self, provider: str, api_key: str = "", clear: bool = False) -> None:
        if provider not in {"gemini", "openai", "local", "deapi"}:
            raise ValueError("Unsupported credential provider.")
        if not isinstance(api_key, str) or len(api_key) > 4096:
            raise ValueError("API key must be text of at most 4096 characters.")
        with self._lock:
            current = self.ai_provider
            selected = dict(current.get(provider, {}))
            if clear:
                selected["api_key"] = ""
            elif api_key.strip():
                selected["api_key"] = api_key.strip()
            current[provider] = selected
            self.settings["ai_provider"] = current
            self._write_json(self.settings_path, self.settings)

    def update_speech(self, changes: dict) -> dict:
        current = self._validated_speech(self.speech, changes)
        with self._lock:
            self.settings["speech"] = current
            self._write_json(self.settings_path, self.settings)
        return self.speech

    @staticmethod
    def _validated_speech(base: dict, changes: dict) -> dict:
        from petey.deapi_tts import DEAPI_TTS_MODEL, DEAPI_TTS_VOICES
        from petey.gemini_tts import GEMINI_TTS_MODELS, GEMINI_TTS_VOICES
        from petey.openai_tts import OPENAI_TTS_MODELS, OPENAI_TTS_VOICES

        current = copy.deepcopy(base)
        provider = str(changes.get("provider") or current.get("provider") or "automatic")
        if provider not in {"disabled", "automatic", "deapi", "gemini", "openai"}:
            raise ValueError("Unsupported speech provider.")
        current["provider"] = provider
        current["provider_selection_version"] = 2
        if "deapi_model" in changes:
            model = str(changes.get("deapi_model") or "").strip()
            if model != DEAPI_TTS_MODEL:
                raise ValueError("Choose a supported deAPI TTS model.")
            current["deapi_model"] = model
        if "deapi_voice" in changes:
            voice = str(changes.get("deapi_voice") or "").strip()
            if voice not in DEAPI_TTS_VOICES:
                raise ValueError("Choose a supported deAPI voice.")
            current["deapi_voice"] = voice
        if "gemini_model" in changes:
            model = str(changes.get("gemini_model") or "").strip()
            if model not in GEMINI_TTS_MODELS:
                raise ValueError("Choose a supported Gemini TTS model.")
            current["gemini_model"] = model
        if "gemini_voice" in changes:
            voice = str(changes.get("gemini_voice") or "").strip()
            if voice not in GEMINI_TTS_VOICES:
                raise ValueError("Choose a supported Gemini voice.")
            current["gemini_voice"] = voice
        if "openai_model" in changes:
            model = str(changes.get("openai_model") or "").strip()
            if model not in OPENAI_TTS_MODELS:
                raise ValueError("Choose a supported OpenAI TTS model.")
            current["openai_model"] = model
        if "openai_voice" in changes:
            voice = str(changes.get("openai_voice") or "").strip().lower()
            if voice not in OPENAI_TTS_VOICES:
                raise ValueError("Choose a supported OpenAI voice.")
            current["openai_voice"] = voice
        if "style" in changes:
            current["style"] = str(changes.get("style") or "").strip()[:2000]
        if "consistent_voice" in changes:
            current["consistent_voice"] = bool(changes["consistent_voice"])
        if "auto_speak" in changes:
            current["auto_speak"] = bool(changes["auto_speak"])
        if provider == "disabled":
            current["auto_speak"] = False
        return current

    @property
    def voice_input(self) -> dict:
        return copy.deepcopy(self.settings.get("voice_input", {}))

    def update_voice_input(self, changes: dict) -> dict:
        from petey.gemini_stt import GEMINI_STT_MODELS

        current = self.voice_input
        mode = str(changes.get("mode") or current.get("mode") or "disabled")
        if mode not in {"disabled", "push_to_talk", "always_on", "wake_word"}:
            raise ValueError("Unsupported microphone mode.")
        current["mode"] = mode
        if "muted" in changes:
            current["muted"] = bool(changes["muted"])
        provider = str(changes.get("provider") or current.get("provider") or "automatic")
        if provider not in {"automatic", "deapi", "gemini", "local_whisper"}:
            raise ValueError("Unsupported transcription provider.")
        current["provider"] = provider
        current["provider_selection_version"] = 3
        if "model" in changes and provider != "local_whisper":
            model = str(changes.get("model") or "").strip()
            supported = ({"WhisperLargeV3"} if provider in {"automatic", "deapi"}
                         else set(GEMINI_STT_MODELS))
            if model not in supported:
                raise ValueError("Choose a supported transcription model.")
            current["model"] = model
        if "gemini_model" in changes:
            model = str(changes.get("gemini_model") or "").strip()
            if model not in GEMINI_STT_MODELS:
                raise ValueError("Choose a supported Gemini transcription model.")
            current["gemini_model"] = model
        if "local_whisper_model" in changes:
            from petey.local_whisper import LOCAL_WHISPER_MODELS

            model = str(changes.get("local_whisper_model") or "").strip()
            if model not in LOCAL_WHISPER_MODELS:
                raise ValueError("Choose a supported Local Whisper model.")
            current["local_whisper_model"] = model
        if "local_whisper_device" in changes:
            from petey.local_whisper import LOCAL_WHISPER_DEVICES

            device = str(changes.get("local_whisper_device") or "").strip().lower()
            if device not in LOCAL_WHISPER_DEVICES:
                raise ValueError("Choose Automatic, CPU, or NVIDIA CUDA.")
            current["local_whisper_device"] = device
        if "wake_word" in changes:
            wake_word = str(changes.get("wake_word") or "Petey").strip()[:40]
            if not wake_word:
                raise ValueError("Enter a wake name.")
            current["wake_word"] = wake_word
        if "device_id" in changes:
            current["device_id"] = str(changes.get("device_id") or "").strip()[:500]
        if "sensitivity" in changes:
            sensitivity = str(changes.get("sensitivity") or "normal")
            if sensitivity not in {"high", "normal", "low"}:
                raise ValueError("Choose a supported microphone sensitivity.")
            current["sensitivity"] = sensitivity
        if "wake_ack_style" in changes:
            style = str(changes.get("wake_ack_style") or "fast")
            if style not in {"fast", "spoken"}:
                raise ValueError("Choose a supported wake acknowledgement.")
            current["wake_ack_style"] = style
        for key, minimum, maximum in (
            ("wake_ack_delay_ms", 150, 2000),
            ("submit_silence_ms", 350, 3000),
            ("follow_up_seconds", 3, 30),
        ):
            if key in changes:
                try:
                    value = int(changes[key])
                except (TypeError, ValueError) as exc:
                    raise ValueError("Voice timing must be a whole number.") from exc
                if value < minimum or value > maximum:
                    raise ValueError("Choose a supported voice timing.")
                current[key] = value
        with self._lock:
            self.settings["voice_input"] = current
            self._write_json(self.settings_path, self.settings)
        return self.voice_input

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
    def conversation_system_prompt(self) -> str:
        return _build_enriched_prompt(self.conversation_persona)

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

    def update_persona_with_speech(self, changes: dict) -> tuple[dict, dict]:
        persona = self._validated_persona(self.persona, changes)
        speech_changes = changes.get("speech")
        speech = self.speech
        if isinstance(speech_changes, dict):
            speech = self._validated_speech(speech, speech_changes)
        with self._lock:
            self.settings["persona"] = persona
            self.settings["speech"] = speech
            self._write_json(self.settings_path, self.settings)
        return self.persona, self.speech

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
        speech_changes = changes.get("speech")
        persona["speech"] = self._validated_speech(
            self.speech,
            speech_changes if isinstance(speech_changes, dict) else self.speech,
        )
        persona["slot"] = index + 1
        persona["is_default"] = False
        with self._lock:
            slots = self.saved_personas
            slots[index] = persona
            self.settings["saved_personas"] = slots
            self._write_json(self.settings_path, self.settings)
        return copy.deepcopy(persona)

    def activate_persona_slot(self, slot: int) -> tuple[dict, dict]:
        index = self._persona_slot_index(slot)
        saved = self.saved_personas[index]
        if not isinstance(saved, dict):
            raise ValueError("That Petey profile slot is empty.")
        persona = self._validated_persona(self.persona, saved)
        # Whether replies play automatically belongs to the current chat/device
        # session. Loading a character profile must not unexpectedly make a
        # working voice fall silent because the slot was saved while auto-speak
        # happened to be off.
        auto_speak = bool(self.speech.get("auto_speak", False))
        speech = self._validated_speech(self.speech, saved.get("speech") or {})
        if speech.get("provider") != "disabled":
            speech["auto_speak"] = auto_speak
        with self._lock:
            self.settings["persona"] = persona
            self.settings["speech"] = speech
            self._write_json(self.settings_path, self.settings)
        return self.persona, self.speech

    def clear_persona_slot(self, slot: int) -> bool:
        index = self._persona_slot_index(slot)
        with self._lock:
            slots = self.saved_personas
            existed = slots[index] is not None
            slots[index] = None
            self.settings["saved_personas"] = slots
            if existed:
                for conversation in self.settings.get("conversations", []):
                    if conversation.get("persona_slot") == index + 1:
                        conversation["persona_slot"] = None
                if self.settings.get("discord", {}).get("persona_slot") == index + 1:
                    self.settings["discord"]["persona_slot"] = None
            self._write_json(self.settings_path, self.settings)
        return existed

    def selected_model(self, inference_type: str) -> str:
        return str(self.settings.get("selected_models", {}).get(inference_type, ""))

    def update_selected_model(self, inference_type: str, model_slug: str) -> None:
        inference_type = str(inference_type)
        model_slug = str(model_slug or "")
        with self._lock:
            models = dict(self.settings.get("selected_models", {}))
            if models.get(inference_type, "") == model_slug:
                return
            if model_slug:
                models[inference_type] = model_slug
            else:
                models.pop(inference_type, None)
            self.settings["selected_models"] = models
            self._write_json(self.settings_path, self.settings)
