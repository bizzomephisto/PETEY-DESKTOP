import json
import tempfile
import unittest
from pathlib import Path

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
                {"name": "Coder Petey", "system_prompt": "You are a coding partner."},
            )

            reloaded = DesktopState(directory)
            self.assertEqual(len(reloaded.saved_personas), 5)
            self.assertEqual(saved["slot"], 5)
            self.assertEqual(reloaded.saved_personas[4]["name"], "Coder Petey")
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

            reloaded.update_selected_model("txt2img", "")
            self.assertEqual(reloaded.selected_model("txt2img"), "")

    def test_conversations_and_preferences_persist(self):
        with tempfile.TemporaryDirectory() as directory:
            state = DesktopState(directory)
            created = state.create_conversation("Project notes")
            state.update_preferences(
                {"always_on_top": True, "sidebar_collapsed": True, "ui_scale": 1.2}
            )

            reloaded = DesktopState(directory)
            self.assertEqual(reloaded.conversation_id, created["id"])
            self.assertEqual(reloaded.conversations[0]["title"], "Project notes")
            self.assertEqual(reloaded.preferences["ui_scale"], 1.2)
            self.assertTrue(reloaded.preferences["always_on_top"])

            deleted, active_id = reloaded.delete_conversation(created["id"])
            self.assertEqual(deleted["title"], "Project notes")
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


if __name__ == "__main__":
    unittest.main()
