import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from petey.desktop_state import DesktopState


class DesktopStateTests(unittest.TestCase):
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
            saved = state.save_persona_slot(
                5,
                {
                    "name": "Coder Petey", "system_prompt": "You are a coding partner.",
                    "speech": {
                        "provider": "gemini", "gemini_voice": "Sulafat",
                        "gemini_model": "gemini-3.1-flash-tts-preview",
                    },
                },
            )

            reloaded = DesktopState(directory)
            self.assertEqual(len(reloaded.saved_personas), 5)
            self.assertEqual(saved["slot"], 5)
            self.assertEqual(reloaded.saved_personas[4]["name"], "Coder Petey")
            self.assertEqual(reloaded.saved_personas[4]["speech"]["gemini_voice"], "Sulafat")
            self.assertNotEqual(reloaded.persona["name"], "Coder Petey")
            self.assertTrue(reloaded.clear_persona_slot(5))
            self.assertIsNone(reloaded.saved_personas[4])
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
                    "visual_style": "orbital_mind",
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
            self.assertEqual(reloaded.preferences["visual_style"], "orbital_mind")
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

    def test_speech_provider_can_use_gemini_openai_or_be_disabled(self):
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

    def test_legacy_deapi_speech_provider_is_migrated_to_automatic(self):
        with tempfile.TemporaryDirectory() as directory:
            state = DesktopState(directory)
            settings = json.loads(state.settings_path.read_text(encoding="utf-8"))
            settings["speech"]["deapi_voice"] = "af_sky"
            settings["saved_personas"][0] = {
                "name": "Legacy", "system_prompt": "You are Legacy.",
                "speech": {"provider": "deapi", "deapi_voice": "af_bella"},
            }
            state.settings_path.write_text(json.dumps(settings), encoding="utf-8")

            migrated = DesktopState(directory)

            self.assertEqual(migrated.speech["provider"], "automatic")
            self.assertEqual(migrated.saved_personas[0]["speech"]["provider"], "automatic")

    def test_microphone_modes_are_persisted_and_validated(self):
        with tempfile.TemporaryDirectory() as directory:
            state = DesktopState(directory)
            self.assertEqual(state.voice_input["mode"], "disabled")
            self.assertEqual(state.voice_input["provider"], "deapi")
            self.assertEqual(state.voice_input["model"], "WhisperLargeV3")
            saved = state.update_voice_input({
                "mode": "wake_word", "provider": "gemini",
                "model": "gemini-3.5-transcribe", "gemini_model": "gemini-3.5-transcribe",
                "wake_word": "Petey", "device_id": "usb-mic-1", "sensitivity": "high",
            })
            self.assertEqual(saved["mode"], "wake_word")
            self.assertEqual(saved["device_id"], "usb-mic-1")
            self.assertEqual(saved["sensitivity"], "high")
            self.assertEqual(DesktopState(directory).voice_input["wake_word"], "Petey")
            with self.assertRaises(ValueError):
                state.update_voice_input({"mode": "secret_recording"})
            with self.assertRaises(ValueError):
                state.update_voice_input({"sensitivity": "maximum"})


if __name__ == "__main__":
    unittest.main()
