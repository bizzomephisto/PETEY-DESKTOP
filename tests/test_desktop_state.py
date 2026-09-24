import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from petey.desktop_state import DesktopState
from petey.room_chat import ROOM_PROMPT


class DesktopStateTests(unittest.TestCase):
    def test_discord_bot_token_is_private_persistent_and_supports_environment_fallback(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.dict("os.environ", {"DISCORD_BOT_TOKEN": ""}):
                state = DesktopState(directory)
                self.assertEqual(state.discord_bot_token_status["source"], "none")
                status = state.update_discord_bot_token("bot-secret")
                self.assertEqual(status["source"], "saved")
                self.assertNotIn("bot-secret", str(status))
                self.assertEqual(DesktopState(directory).discord_bot_token, "bot-secret")
                self.assertEqual(state.update_discord_pace("fast"), "fast")
                self.assertEqual(DesktopState(directory).discord_pace, "fast")
                with self.assertRaises(ValueError):
                    state.update_discord_pace("instant")
                self.assertEqual(
                    state.update_discord_watched_topics([" Linux ", "linux", "retro   games"]),
                    ["Linux", "retro games"],
                )
                self.assertEqual(
                    DesktopState(directory).discord_watched_topics,
                    ["Linux", "retro games"],
                )
                with self.assertRaises(ValueError):
                    state.update_discord_watched_topics(["x"] * 21)
                self.assertEqual(
                    state.update_discord_room_prompt("Custom room behavior"),
                    "Custom room behavior",
                )
                self.assertEqual(
                    DesktopState(directory).discord_room_prompt,
                    "Custom room behavior",
                )
                self.assertEqual(
                    state.update_discord_room_prompt(reset=True), ROOM_PROMPT
                )
                state.save_persona_slot(1, {
                    "name": "Discord Petey",
                    "role_tag": "Server regular",
                    "system_prompt": "You are Petey's Discord personality only.",
                })
                self.assertEqual(state.update_discord_persona(1), 1)
                self.assertEqual(DesktopState(directory).discord_persona_slot, 1)
                self.assertIn("Discord personality only", state.discord_system_prompt)
                self.assertIn(ROOM_PROMPT, state.discord_system_prompt)
                self.assertEqual(
                    [item["slot"] for item in state.discord_persona_options],
                    [None, 1],
                )
                with self.assertRaisesRegex(ValueError, "empty"):
                    state.update_discord_persona(2)
                state.clear_persona_slot(1)
                self.assertIsNone(state.discord_persona_slot)
                self.assertEqual(state.discord_system_prompt, ROOM_PROMPT)
                self.assertEqual(state.discord_memory_policy, "room_only")
                self.assertEqual(state.update_discord_memory_policy("store"), "store")
                self.assertEqual(DesktopState(directory).discord_memory_policy, "store")
                self.assertEqual(state.update_discord_memory_policy("shared"), "shared")
                with self.assertRaises(ValueError):
                    state.update_discord_memory_policy("everything")
                self.assertTrue(state.update_discord_auto_connect(True))
                state.update_discord_last_location(
                    "222222222222222222", "333333333333333333", "Friends", "#general"
                )
                reloaded = DesktopState(directory)
                self.assertTrue(reloaded.discord_auto_connect)
                self.assertEqual(reloaded.discord_last_location["guild"], "Friends")
                self.assertEqual(
                    reloaded.discord_last_location["channel_id"], "333333333333333333"
                )
                with self.assertRaises(ValueError):
                    state.update_discord_auto_connect("yes")
                with self.assertRaises(ValueError):
                    state.update_discord_last_location("not-an-id", "333333333333333333")
                state.update_discord_bot_token(clear=True)
                self.assertEqual(state.discord_bot_token, "")
                with self.assertRaises(ValueError):
                    state.update_discord_bot_token("")
            with patch.dict("os.environ", {"DISCORD_BOT_TOKEN": "environment-secret"}):
                state = DesktopState(directory)
                self.assertEqual(state.discord_bot_token, "environment-secret")
                self.assertEqual(state.discord_bot_token_status["source"], "environment")

    def test_filesystem_tool_defaults_off_and_persists(self):
        with tempfile.TemporaryDirectory() as directory:
            state = DesktopState(directory)
            self.assertFalse(state.tools["filesystem"]["enabled"])
            self.assertTrue(state.update_tool("filesystem", True)["enabled"])
            self.assertTrue(DesktopState(directory).tools["filesystem"]["enabled"])
            with self.assertRaises(ValueError):
                state.update_tool("unknown", True)

    def test_legacy_workspace_folders_migrate_to_approved_folders(self):
        with tempfile.TemporaryDirectory() as directory, tempfile.TemporaryDirectory() as folder:
            state = DesktopState(directory)
            settings = json.loads(state.settings_path.read_text(encoding="utf-8"))
            settings["workspaces"] = [{
                "id": "workspace-old", "name": "Old folder", "path": folder,
                "created_at": "2026-01-01T00:00:00+00:00",
            }]
            settings["active_workspace_id"] = "workspace-old"
            settings.pop("approved_folders", None)
            state.settings_path.write_text(json.dumps(settings), encoding="utf-8")

            migrated = DesktopState(directory)
            saved = json.loads(migrated.settings_path.read_text(encoding="utf-8"))

            self.assertEqual(migrated.approved_folders[0]["path"], folder)
            self.assertNotIn("workspaces", saved)
            self.assertNotIn("active_workspace_id", saved)

    def test_addon_enablement_defaults_and_persists(self):
        with tempfile.TemporaryDirectory() as directory:
            state = DesktopState(directory)
            self.assertTrue(state.addon_enabled("discord", True))
            self.assertTrue(state.update_addon_enabled("sample-addon", True))
            self.assertTrue(DesktopState(directory).addon_enabled("sample-addon"))
            with self.assertRaises(ValueError):
                state.update_addon_enabled("Bad ID", True)
            with self.assertRaises(ValueError):
                state.update_addon_enabled("sample-addon", "yes")

    def test_petey_control_defaults_to_desktop_mobile_and_enforces_daily_limit(self):
        with tempfile.TemporaryDirectory() as directory:
            state = DesktopState(directory)
            capabilities = [{
                "id": "generate_image", "label": "Generate images",
                "metered": True, "default_daily_limit": 1,
            }]
            status = state.update_petey_control(
                "deapi-media", {"enabled": True}, capabilities
            )
            self.assertTrue(status["surfaces"]["petey_desktop"])
            self.assertTrue(status["surfaces"]["mobile_petey"])
            self.assertFalse(status["surfaces"]["discord"])

            state.authorize_petey_control(
                "deapi-media", "generate_image", "petey_desktop",
                explicit=False, capabilities=capabilities, consume=True,
            )
            with self.assertRaisesRegex(ValueError, "daily limit"):
                state.authorize_petey_control(
                    "deapi-media", "generate_image", "petey_desktop",
                    explicit=False, capabilities=capabilities,
                )
            allowed = state.authorize_petey_control(
                "deapi-media", "generate_image", "petey_desktop",
                explicit=True, capabilities=capabilities, consume=True,
            )
            self.assertTrue(allowed["explicit"])

    def test_theme_persists_and_invalid_theme_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            state = DesktopState(directory)
            self.assertEqual(state.preferences["theme"], "midnight")
            for theme in ("midnight", "ocean", "forest", "paper"):
                state.update_preferences({"theme": theme})
                self.assertEqual(DesktopState(directory).preferences["theme"], theme)
            with self.assertRaises(ValueError):
                state.update_preferences({"theme": "unsupported"})
            self.assertEqual(state.preferences["theme"], "paper")

    def test_old_or_invalid_theme_settings_load_with_default(self):
        import json
        with tempfile.TemporaryDirectory() as directory:
            state = DesktopState(directory)
            for theme in (None, "unsupported", {"invalid": True}):
                settings = json.loads(state.settings_path.read_text())
                if theme is None:
                    settings["preferences"].pop("theme", None)
                else:
                    settings["preferences"]["theme"] = theme
                state.settings_path.write_text(json.dumps(settings))
                self.assertEqual(DesktopState(directory).preferences["theme"], "midnight")

    def test_installation_identity_is_stable(self):
        with tempfile.TemporaryDirectory() as directory:
            first = DesktopState(directory)
            second = DesktopState(directory)

            self.assertTrue(first.installation_id.startswith("desktop-"))
            self.assertEqual(first.installation_id, second.installation_id)
            self.assertEqual(first.conversation_id, "main")
            self.assertTrue(first.system_prompt)

    def test_existing_identity_is_preserved(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            (path / "installation.json").write_text(
                json.dumps(
                    {
                        "installation_id": "desktop-known",
                        "person_id": "person-7",
                        "display_name": "Alex",
                        "default_conversation_id": "kitchen",
                    }
                ),
                encoding="utf-8",
            )
            state = DesktopState(path)

            self.assertEqual(state.installation_id, "desktop-known")
            self.assertEqual(state.person_id, "person-7")
            self.assertEqual(state.display_name, "Alex")
            self.assertEqual(state.conversation_id, "kitchen")

    def test_new_and_legacy_automatic_names_are_neutral_until_customized(self):
        with tempfile.TemporaryDirectory() as directory:
            state = DesktopState(directory)
            self.assertEqual(state.display_name, "User")
            self.assertEqual(state.update_display_name("  Casey  "), "Casey")
            self.assertEqual(DesktopState(directory).display_name, "Casey")

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            (path / "installation.json").write_text(
                json.dumps({
                    "installation_id": "desktop-legacy",
                    "person_id": "owner",
                    "display_name": "machine-login",
                    "default_conversation_id": "main",
                }),
                encoding="utf-8",
            )
            with patch("petey.desktop_state.getpass.getuser", return_value="machine-login"):
                self.assertEqual(DesktopState(path).display_name, "User")

    def test_persona_updates_are_validated_and_persisted(self):
        with tempfile.TemporaryDirectory() as directory:
            state = DesktopState(directory)
            persona = state.update_persona(
                {
                    "name": "Petey Local",
                    "system_prompt": "You are a precise local assistant.",
                    "traits": ["Direct", " Patient ", ""],
                    "sliders": {"tone": 150, "verbosity": "22"},
                }
            )

            self.assertEqual(persona["name"], "Petey Local")
            self.assertEqual(persona["traits"], ["Direct", "Patient"])
            self.assertEqual(persona["sliders"]["tone"], 100)
            self.assertEqual(persona["sliders"]["verbosity"], 22)
            self.assertIn("precise local assistant", DesktopState(directory).system_prompt)

    def test_five_persona_slots_can_be_saved_loaded_and_cleared(self):
        with tempfile.TemporaryDirectory() as directory:
            state = DesktopState(directory)
            state.update_speech({"auto_speak": True})
            saved = state.save_persona_slot(
                5,
                {
                    "name": "Coder Petey", "system_prompt": "You are a coding partner.",
                    "traits": ["Precise", "Patient"],
                    "sliders": {"tone": 35, "verbosity": 72, "formality": 60},
                    "speech": {
                        "provider": "gemini", "gemini_voice": "Sulafat",
                        "gemini_model": "gemini-3.1-flash-tts-preview",
                        "style": "Calm and deliberate.",
                        "auto_speak": False,
                    },
                },
            )

            reloaded = DesktopState(directory)
            self.assertEqual(len(reloaded.saved_personas), 5)
            self.assertEqual(saved["slot"], 5)
            self.assertEqual(reloaded.saved_personas[4]["name"], "Coder Petey")
            self.assertEqual(reloaded.saved_personas[4]["speech"]["gemini_voice"], "Sulafat")
            self.assertNotEqual(reloaded.persona["name"], "Coder Petey")
            persona, speech = reloaded.activate_persona_slot(5)
            self.assertEqual(persona["traits"], ["Precise", "Patient"])
            self.assertEqual(persona["sliders"]["verbosity"], 72)
            self.assertEqual(speech["provider"], "gemini")
            self.assertEqual(speech["gemini_voice"], "Sulafat")
            self.assertEqual(speech["style"], "Calm and deliberate.")
            self.assertTrue(speech["auto_speak"])
            self.assertTrue(reloaded.clear_persona_slot(5))
            self.assertIsNone(reloaded.saved_personas[4])
            with self.assertRaisesRegex(ValueError, "empty"):
                reloaded.activate_persona_slot(5)
            with self.assertRaises(ValueError):
                reloaded.save_persona_slot(6, {"system_prompt": "Invalid slot"})

    def test_selected_media_models_are_persisted_per_operation(self):
        with tempfile.TemporaryDirectory() as directory:
            state = DesktopState(directory)
            state.update_selected_model("txt2img", "flux-desktop")
            state.update_selected_model("txt2video", "video-desktop")

            reloaded = DesktopState(directory)
            self.assertEqual(reloaded.selected_model("txt2img"), "flux-desktop")
            self.assertEqual(reloaded.selected_model("txt2video"), "video-desktop")

            with patch.object(reloaded, "_write_json") as write_json:
                reloaded.update_selected_model("txt2video", "video-desktop")
            write_json.assert_not_called()

            reloaded.update_selected_model("txt2img", "")
            self.assertEqual(reloaded.selected_model("txt2img"), "")

    def test_conversations_and_preferences_persist(self):
        with tempfile.TemporaryDirectory() as directory:
            state = DesktopState(directory)
            created = state.create_conversation("Project notes")
            state.update_preferences(
                {
                    "always_on_top": True, "sidebar_collapsed": True,
                    "ui_scale": 1.2, "visual_mode": True,
                    "visual_style": "aurora_flow",
                }
            )

            reloaded = DesktopState(directory)
            self.assertEqual(reloaded.conversation_id, created["id"])
            self.assertEqual(reloaded.conversations[0]["title"], "Project notes")
            renamed = reloaded.rename_conversation(created["id"], "Renamed project")
            self.assertEqual(renamed["title"], "Renamed project")
            self.assertEqual(
                DesktopState(directory).conversations[0]["title"], "Renamed project"
            )
            self.assertEqual(reloaded.preferences["ui_scale"], 1.2)
            self.assertTrue(reloaded.preferences["always_on_top"])
            self.assertTrue(reloaded.preferences["visual_mode"])
            self.assertEqual(reloaded.preferences["visual_style"], "aurora_flow")
            reloaded.update_preferences({"visual_style": "constellation_field"})
            self.assertEqual(reloaded.preferences["visual_style"], "constellation_field")
            with self.assertRaises(ValueError):
                state.update_preferences({"visual_style": "unknown"})

            deleted, active_id = reloaded.delete_conversation(created["id"])
            self.assertEqual(deleted["title"], "Renamed project")
            self.assertNotEqual(active_id, created["id"])

    def test_deleting_the_last_conversation_creates_a_replacement(self):
        with tempfile.TemporaryDirectory() as directory:
            state = DesktopState(directory)
            state.delete_conversation("main")
            self.assertEqual(len(state.conversations), 1)
            self.assertTrue(state.conversation_id.startswith("chat-"))

    def test_conversations_can_use_saved_personas_without_changing_system_persona(self):
        with tempfile.TemporaryDirectory() as directory:
            state = DesktopState(directory)
            system_name = state.persona["name"]
            state.update_speech({"auto_speak": True, "gemini_voice": "Kore"})
            state.save_persona_slot(2, {
                "name": "Workshop Petey",
                "role_tag": "Builder",
                "system_prompt": "You are Petey in the workshop.",
                "speech": {"provider": "gemini", "gemini_voice": "Sulafat"},
            })

            created = state.create_conversation("Workshop", persona_slot=2)
            plain = state.create_conversation("Plain chat")

            state.select_conversation(created["id"])
            self.assertEqual(created["persona_slot"], 2)
            self.assertEqual(state.persona["name"], system_name)
            self.assertEqual(state.conversation_persona["name"], "Workshop Petey")
            self.assertIn("Petey in the workshop", state.conversation_system_prompt)
            self.assertEqual(state.conversation_speech["gemini_voice"], "Sulafat")
            self.assertTrue(state.conversation_speech["auto_speak"])
            self.assertEqual(
                [item["slot"] for item in state.conversation_persona_options],
                [None, 2],
            )

            state.select_conversation(plain["id"])
            self.assertEqual(state.conversation_persona["name"], system_name)
            self.assertNotIn("Petey in the workshop", state.conversation_system_prompt)
            state.select_conversation(created["id"])

            state.assign_conversation_persona(created["id"], None)
            self.assertEqual(state.conversation_persona["name"], system_name)
            self.assertEqual(state.conversation_speech["gemini_voice"], "Kore")
            with self.assertRaisesRegex(ValueError, "empty"):
                state.assign_conversation_persona(created["id"], 3)

            state.assign_conversation_persona(created["id"], 2)
            state.clear_persona_slot(2)
            self.assertIsNone(state.conversation["persona_slot"])

    def test_ai_provider_settings_preserve_keys_and_validate_local_url(self):
        with tempfile.TemporaryDirectory() as directory:
            state = DesktopState(directory)
            state.update_ai_provider(
                {
                    "provider": "local",
                    "model": "qwen-local",
                    "base_url": "http://localhost:11434/v1/",
                    "api_key": "secret-token",
                    "thinking_enabled": False,
                }
            )
            state.update_ai_provider({"provider": "local", "model": "qwen-new"})

            reloaded = DesktopState(directory)
            self.assertEqual(reloaded.ai_provider["provider"], "local")
            self.assertEqual(reloaded.ai_provider["local"]["model"], "qwen-new")
            self.assertEqual(reloaded.ai_provider["local"]["api_key"], "secret-token")
            self.assertEqual(reloaded.ai_provider["local"]["base_url"], "http://localhost:11434/v1")
            self.assertFalse(reloaded.ai_provider["local"]["thinking_enabled"])
            with self.assertRaises(ValueError):
                reloaded.update_ai_provider({"provider": "local", "base_url": "localhost:9999"})

    def test_memory_provider_is_independent_from_chat_provider(self):
        with tempfile.TemporaryDirectory() as directory:
            state = DesktopState(directory)
            state.update_ai_provider({"provider": "openai", "model": "gpt-test"})
            memory = state.update_memory_provider(
                {
                    "provider": "local",
                    "model": "nomic-embed-text",
                    "local_base_url": "http://localhost:11434/v1/",
                }
            )

            self.assertEqual(state.ai_provider["provider"], "openai")
            self.assertEqual(memory["provider"], "local")
            self.assertEqual(memory["models"]["local"], "nomic-embed-text")
            self.assertEqual(memory["local_base_url"], "http://localhost:11434/v1")

    def test_speech_provider_can_use_deapi_gemini_openai_or_be_disabled(self):
        with tempfile.TemporaryDirectory() as directory:
            state = DesktopState(directory)
            speech = state.update_speech({
                "provider": "gemini",
                "gemini_model": "gemini-3.1-flash-tts-preview",
                "gemini_voice": "Sulafat",
                "style": "Warm and measured",
                "consistent_voice": False,
                "auto_speak": True,
            })
            self.assertEqual(speech["gemini_voice"], "Sulafat")
            self.assertTrue(speech["auto_speak"])
            self.assertFalse(speech["consistent_voice"])
            self.assertEqual(DesktopState(directory).speech["style"], "Warm and measured")
            disabled = state.update_speech({"provider": "disabled"})
            self.assertEqual(disabled["provider"], "disabled")
            self.assertFalse(disabled["auto_speak"])
            with self.assertRaises(ValueError):
                state.update_speech({"provider": "gemini", "gemini_voice": "Unknown"})
            openai = state.update_speech({
                "provider": "openai", "openai_model": "gpt-4o-mini-tts",
                "openai_voice": "cedar", "auto_speak": True,
            })
            self.assertEqual(openai["openai_voice"], "cedar")
            self.assertEqual(DesktopState(directory).speech["provider"], "openai")
            deapi = state.update_speech({
                "provider": "deapi",
                "deapi_model": "Qwen3_TTS_12Hz_1_7B_CustomVoice",
                "deapi_voice": "Vivian",
            })
            self.assertEqual(deapi["deapi_voice"], "Vivian")
            self.assertEqual(DesktopState(directory).speech["provider"], "deapi")

    def test_legacy_deapi_speech_provider_is_migrated_to_automatic(self):
        with tempfile.TemporaryDirectory() as directory:
            state = DesktopState(directory)
            settings = json.loads(state.settings_path.read_text(encoding="utf-8"))
            settings["speech"].pop("provider_selection_version", None)
            settings["speech"]["deapi_voice"] = "af_sky"
            settings["saved_personas"][0] = {
                "name": "Legacy", "system_prompt": "You are Legacy.",
                "speech": {"provider": "deapi", "deapi_voice": "af_bella"},
            }
            settings["saved_personas"][1] = {
                "name": "Older Legacy", "system_prompt": "You are Older Legacy.",
            }
            state.settings_path.write_text(json.dumps(settings), encoding="utf-8")

            migrated = DesktopState(directory)

            self.assertEqual(migrated.speech["provider"], "automatic")
            self.assertEqual(migrated.saved_personas[0]["speech"]["provider"], "automatic")
            self.assertEqual(migrated.saved_personas[1]["speech"], migrated.speech)

    def test_microphone_modes_are_persisted_and_validated(self):
        with tempfile.TemporaryDirectory() as directory:
            state = DesktopState(directory)
            self.assertEqual(state.voice_input["mode"], "disabled")
            self.assertFalse(state.voice_input["muted"])
            self.assertEqual(state.voice_input["provider"], "automatic")
            self.assertEqual(state.voice_input["model"], "WhisperLargeV3")
            self.assertEqual(state.voice_input["local_whisper_model"], "small")
            self.assertEqual(state.voice_input["local_whisper_device"], "auto")
            self.assertEqual(state.voice_input["wake_ack_style"], "fast")
            self.assertEqual(state.voice_input["wake_ack_delay_ms"], 300)
            self.assertEqual(state.voice_input["submit_silence_ms"], 600)
            self.assertEqual(state.voice_input["follow_up_seconds"], 8)
            saved = state.update_voice_input({
                "mode": "wake_word", "muted": True, "provider": "gemini",
                "model": "gemini-3.5-transcribe", "gemini_model": "gemini-3.5-transcribe",
                "wake_word": "Petey", "device_id": "usb-mic-1", "sensitivity": "high",
                "wake_ack_style": "spoken",
                "wake_ack_delay_ms": 650, "submit_silence_ms": 950,
                "follow_up_seconds": 12,
            })
            self.assertEqual(saved["mode"], "wake_word")
            self.assertTrue(saved["muted"])
            self.assertEqual(saved["device_id"], "usb-mic-1")
            self.assertEqual(saved["sensitivity"], "high")
            self.assertEqual(saved["wake_ack_style"], "spoken")
            self.assertEqual(saved["wake_ack_delay_ms"], 650)
            self.assertEqual(saved["submit_silence_ms"], 950)
            self.assertEqual(saved["follow_up_seconds"], 12)
            self.assertEqual(DesktopState(directory).voice_input["wake_word"], "Petey")
            self.assertTrue(DesktopState(directory).voice_input["muted"])
            with self.assertRaises(ValueError):
                state.update_voice_input({"mode": "secret_recording"})
            with self.assertRaises(ValueError):
                state.update_voice_input({"sensitivity": "maximum"})
            with self.assertRaises(ValueError):
                state.update_voice_input({"wake_ack_style": "slow"})
            with self.assertRaises(ValueError):
                state.update_voice_input({"wake_ack_delay_ms": 50})
            with self.assertRaises(ValueError):
                state.update_voice_input({"follow_up_seconds": 60})
            private = state.update_voice_input({
                "provider": "local_whisper", "local_whisper_model": "medium",
                "local_whisper_device": "cpu",
            })
            self.assertEqual(private["local_whisper_model"], "medium")
            self.assertEqual(private["local_whisper_device"], "cpu")
            with self.assertRaises(ValueError):
                state.update_voice_input({"provider": "local"})

    def test_legacy_local_transcription_server_migrates_to_local_whisper(self):
        with tempfile.TemporaryDirectory() as directory:
            state = DesktopState(directory)
            settings = json.loads(state.settings_path.read_text(encoding="utf-8"))
            settings["voice_input"].update({
                "provider": "local",
                "local_base_url": "http://localhost:1234/v1",
                "local_model": "whisper-1",
                "provider_selection_version": 2,
            })
            state.settings_path.write_text(json.dumps(settings), encoding="utf-8")

            migrated = DesktopState(directory).voice_input

            self.assertEqual(migrated["provider"], "local_whisper")
            self.assertNotIn("local_base_url", migrated)
            self.assertNotIn("local_model", migrated)

    def test_legacy_automatic_transcription_migrates_and_deapi_only_persists(self):
        with tempfile.TemporaryDirectory() as directory:
            state = DesktopState(directory)
            settings = json.loads(state.settings_path.read_text(encoding="utf-8"))
            settings["voice_input"]["provider"] = "deapi"
            settings["voice_input"].pop("provider_selection_version", None)
            state.settings_path.write_text(json.dumps(settings), encoding="utf-8")

            migrated = DesktopState(directory)
            self.assertEqual(migrated.voice_input["provider"], "automatic")
            migrated.update_voice_input({"provider": "deapi", "model": "WhisperLargeV3"})
            self.assertEqual(DesktopState(directory).voice_input["provider"], "deapi")

    def test_legacy_default_voice_timings_are_migrated_to_low_latency(self):
        with tempfile.TemporaryDirectory() as directory:
            state = DesktopState(directory)
            settings = json.loads(state.settings_path.read_text(encoding="utf-8"))
            settings["voice_input"].pop("latency_tuning_version", None)
            settings["voice_input"].pop("wake_ack_style", None)
            settings["voice_input"]["wake_ack_delay_ms"] = 500
            settings["voice_input"]["submit_silence_ms"] = 800
            state.settings_path.write_text(json.dumps(settings), encoding="utf-8")

            migrated = DesktopState(directory).voice_input

            self.assertEqual(migrated["wake_ack_style"], "fast")
            self.assertEqual(migrated["wake_ack_delay_ms"], 300)
            self.assertEqual(migrated["submit_silence_ms"], 600)
            self.assertEqual(migrated["latency_tuning_version"], 1)


if __name__ == "__main__":
    unittest.main()
