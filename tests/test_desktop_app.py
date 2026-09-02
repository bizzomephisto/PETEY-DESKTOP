import tempfile
import unittest
from io import BytesIO
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from petey.assistant import AssistantReply
from petey.desktop_state import DesktopState
from petey.media_jobs import MediaGallery
from web.desktop_app import AsyncRuntime, create_desktop_app
from petey.version import MEDIA_PROVIDER_URL, PROJECT_URL, __version__


class DesktopAppTests(unittest.TestCase):
    def test_shell_and_bootstrap_are_local_app_routes(self):
        with tempfile.TemporaryDirectory() as directory:
            state = DesktopState(directory)
            app = create_desktop_app(state=state, runtime=object())
            client = app.test_client()

            shell = client.get("/")
            bootstrap = client.get("/api/desktop/bootstrap")

            self.assertEqual(shell.status_code, 200)
            self.assertIn("Message Petey", shell.get_data(as_text=True))
            self.assertIn(f"v{__version__}", shell.get_data(as_text=True))
            self.assertIn(PROJECT_URL, shell.get_data(as_text=True))
            self.assertIn(MEDIA_PROVIDER_URL, shell.get_data(as_text=True))
            self.assertNotIn("deAPI Media", shell.get_data(as_text=True))
            self.assertEqual(shell.get_data(as_text=True).count("deAPI"), 1)
            self.assertEqual(bootstrap.status_code, 200)
            self.assertEqual(
                bootstrap.get_json()["installation_id"], state.installation_id
            )
            self.assertEqual(bootstrap.get_json()["version"], __version__)

    def test_user_can_save_their_display_name(self):
        with tempfile.TemporaryDirectory() as directory:
            state = DesktopState(directory)
            app = create_desktop_app(state=state, runtime=object())
            client = app.test_client()

            response = client.put(
                "/api/desktop/identity", json={"display_name": "  Casey  "}
            )

            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.get_json()["person_name"], "Casey")
            self.assertEqual(client.get("/api/desktop/bootstrap").get_json()["person_name"], "Casey")
            self.assertEqual(DesktopState(directory).display_name, "Casey")

    def test_messages_are_labeled_by_speaker(self):
        rows = [
            {"id": 1, "user_id": "owner", "message": "Hi", "timestamp": "now"},
            {"id": 2, "user_id": "PETEY", "message": "Hey", "timestamp": "now"},
        ]
        with tempfile.TemporaryDirectory() as directory:
            state = DesktopState(directory)
            memory_store = MagicMock()
            memory_store.get_conversation_messages.return_value = rows
            app = create_desktop_app(state=state, runtime=object(), memory=memory_store)
            response = app.test_client().get("/api/desktop/messages")

            self.assertEqual([item["role"] for item in response.get_json()], ["user", "assistant"])

    def test_gallery_exposes_qt_compatible_video_preview(self):
        with tempfile.TemporaryDirectory() as directory:
            preview = Path(directory) / "video-1.preview.webm"
            preview.write_bytes(b"webm-data")
            gallery = MagicMock()
            gallery.list_items.return_value = [{
                "id": "video-1",
                "created_at": "2026-01-01T00:00:00+00:00",
                "operation": "txt2video",
                "kind": "video",
                "prompt": "A robot",
                "model_slug": "video-model",
                "remote_url": "https://media.example/video.mp4",
                "local_filename": "video-1.mp4",
                "content_type": "video/mp4",
                "download_error": "",
            }]
            gallery.video_preview_path.return_value = preview
            app = create_desktop_app(
                state=DesktopState(directory), runtime=object(), gallery=gallery
            )
            client = app.test_client()

            item = client.get("/api/desktop/gallery").get_json()["items"][0]
            response = client.get(item["preview_url"])

            self.assertEqual(item["media_url"], "/api/desktop/gallery/file/video-1")
            self.assertEqual(item["preview_url"], "/api/desktop/gallery/preview/video-1")
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.content_type, "video/webm")
            self.assertEqual(response.data, b"webm-data")
            response.close()

    def test_chat_route_returns_assistant_reply(self):
        with tempfile.TemporaryDirectory() as directory:
            state = DesktopState(directory)
            with patch(
                    "web.desktop_app.AssistantService.respond",
                    new=AsyncMock(return_value=AssistantReply("Desktop reply")),
                ):
                app = create_desktop_app(state=state, runtime=AsyncRuntime())
                response = app.test_client().post(
                    "/api/desktop/chat", data={"message": "Hello Petey"}
                )

            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.get_json()["text"], "Desktop reply")

    def test_conversation_management_and_preferences(self):
        with tempfile.TemporaryDirectory() as directory:
            state = DesktopState(directory)
            memory_store = MagicMock()
            memory_store.clear_conversation.return_value = 0
            with tempfile.TemporaryDirectory():
                app = create_desktop_app(state=state, runtime=object(), memory=memory_store)
                client = app.test_client()
                created = client.post("/api/desktop/conversations", json={"title": "Ideas"})
                conversation_id = created.get_json()["conversation_id"]
                saved = client.put(
                    "/api/desktop/preferences",
                    json={"always_on_top": True, "ui_scale": 1.3},
                )
                renamed = client.patch(
                    f"/api/desktop/conversations/{conversation_id}",
                    json={"title": "Named ideas"},
                )
                deleted = client.delete(f"/api/desktop/conversations/{conversation_id}")

            self.assertEqual(created.status_code, 201)
            self.assertEqual(created.get_json()["conversation"]["title"], "Ideas")
            self.assertTrue(saved.get_json()["preferences"]["always_on_top"])
            self.assertEqual(saved.get_json()["preferences"]["ui_scale"], 1.3)
            self.assertEqual(renamed.get_json()["conversation"]["title"], "Named ideas")
            self.assertNotEqual(deleted.get_json()["conversation_id"], conversation_id)

    def test_ai_provider_configuration_never_returns_saved_key(self):
        with tempfile.TemporaryDirectory() as directory:
            state = DesktopState(directory)
            app = create_desktop_app(state=state, runtime=object())
            response = app.test_client().put(
                    "/api/desktop/ai-provider",
                    json={"provider": "openai", "model": "gpt-test", "api_key": "sk-private"},
                )

            payload = response.get_json()["configuration"]
            self.assertEqual(payload["provider"], "openai")
            self.assertTrue(payload["has_api_key"])
            self.assertNotIn("sk-private", response.get_data(as_text=True))

    def test_vision_model_is_saved_independently_of_chat_provider(self):
        with tempfile.TemporaryDirectory() as directory:
            state = DesktopState(directory)
            app = create_desktop_app(state=state, runtime=object())
            response = app.test_client().put(
                "/api/desktop/ai-provider",
                json={
                    "provider": "local",
                    "model": "qwen",
                    "base_url": "http://localhost:1234/v1",
                    "vision_model": "gemini-vision-test",
                },
            )

            payload = response.get_json()["configuration"]
            self.assertEqual(payload["provider"], "local")
            self.assertEqual(payload["vision_model"], "gemini-vision-test")
            self.assertEqual(
                state.ai_provider["gemini"]["vision_model"], "gemini-vision-test"
            )

    def test_chat_route_passes_temporary_history(self):
        with tempfile.TemporaryDirectory() as directory:
            state = DesktopState(directory)
            with patch(
                    "web.desktop_app.AssistantService.respond",
                    new=AsyncMock(return_value=AssistantReply("Temporary reply")),
                ) as respond:
                app = create_desktop_app(state=state, runtime=AsyncRuntime())
                response = app.test_client().post(
                    "/api/desktop/chat",
                    data={
                        "message": "Hello",
                        "temporary": "true",
                        "temporary_history": '[{"role":"user","content":"Earlier"}]',
                    },
                )

            self.assertEqual(response.status_code, 200)
            self.assertTrue(respond.call_args.kwargs["temporary"])
            self.assertEqual(respond.call_args.kwargs["temporary_history"][0]["content"], "Earlier")

    def test_personality_can_be_read_and_saved(self):
        with tempfile.TemporaryDirectory() as directory:
            state = DesktopState(directory)
            app = create_desktop_app(state=state, runtime=object())
            client = app.test_client()

            current = client.get("/api/desktop/personality")
            saved = client.put(
                "/api/desktop/personality",
                json={"name": "Desktop Petey", "system_prompt": "You are Desktop Petey."},
            )

            self.assertIn("friendly_helper", current.get_json()["presets"])
            self.assertEqual(saved.status_code, 200)
            self.assertEqual(saved.get_json()["persona"]["name"], "Desktop Petey")

    def test_personality_slots_can_be_saved_and_cleared(self):
        with tempfile.TemporaryDirectory() as directory:
            state = DesktopState(directory)
            app = create_desktop_app(state=state, runtime=object())
            client = app.test_client()

            saved = client.put(
                "/api/desktop/personality/slots/2",
                json={"name": "Writer Petey", "system_prompt": "You are a writing partner."},
            )
            current = client.get("/api/desktop/personality")
            cleared = client.delete("/api/desktop/personality/slots/2")

            self.assertEqual(saved.status_code, 200)
            self.assertEqual(saved.get_json()["persona"]["name"], "Writer Petey")
            self.assertEqual(current.get_json()["saved_personas"][1]["name"], "Writer Petey")
            self.assertTrue(cleared.get_json()["removed"])
            self.assertIsNone(cleared.get_json()["saved_personas"][1])

    def test_knowledge_upload_queues_document_and_replaces_same_name(self):
        with tempfile.TemporaryDirectory() as directory:
            state = DesktopState(directory)
            memory_store = MagicMock()
            memory_store.delete_document.return_value = True
            app = create_desktop_app(state=state, runtime=object(), memory=memory_store)
            response = app.test_client().post(
                    "/api/desktop/knowledge",
                    data={"file": (BytesIO(b"Petey knowledge"), "notes.md")},
                    content_type="multipart/form-data",
                )

            self.assertEqual(response.status_code, 202)
            memory_store.delete_document.assert_called_once_with(state.installation_id, "notes.md")
            memory_store.store_document.assert_called_once_with(state.installation_id, "notes.md", "Petey knowledge")

    def test_rag_search_and_memory_management_use_local_identity(self):
        with tempfile.TemporaryDirectory() as directory:
            state = DesktopState(directory)
            stats = {"conversation_messages": 4, "document_chunks": 8, "embedded_memories": 10}
            memory_store = MagicMock()
            memory_store.search_memories.return_value = "Relevant memory"
            memory_store.get_memory_stats.return_value = stats
            memory_store.clear_conversation.return_value = 4
            with tempfile.TemporaryDirectory():
                app = create_desktop_app(state=state, runtime=object(), memory=memory_store)
                client = app.test_client()
                rag = client.post("/api/desktop/knowledge/search", json={"query": "Petey"})
                memory = client.get("/api/desktop/memory/stats")
                cleared = client.delete("/api/desktop/memory/conversation")

            self.assertEqual(rag.get_json()["result"], "Relevant memory")
            self.assertEqual(memory.get_json(), stats)
            self.assertEqual(cleared.get_json()["deleted"], 4)
            memory_store.search_memories.assert_called_once_with("Petey", state.installation_id, 8)
            memory_store.clear_conversation.assert_called_once_with(state.installation_id, state.conversation_id)

    def test_media_catalog_and_generation_are_desktop_scoped(self):
        queued = {
            "id": "job-1", "status": "queued", "kind": "image", "operation": "txt2img",
            "prompt": "A desktop robot", "model_slug": "flux-desktop",
        }
        with tempfile.TemporaryDirectory() as directory:
            state = DesktopState(directory)
            jobs = MagicMock()
            jobs.submit.return_value = queued
            memory_store = MagicMock()
            with tempfile.TemporaryDirectory():
                app = create_desktop_app(
                    state=state,
                    runtime=AsyncRuntime(),
                    gallery=MediaGallery(state.data_dir / "gallery"),
                    job_manager=jobs,
                    memory=memory_store,
                )
                client = app.test_client()
                catalog = client.get("/api/desktop/media")
                response = client.post(
                    "/api/desktop/media/generate",
                    data={
                        "operation": "txt2img",
                        "prompt": "A desktop robot",
                        "model_slug": "flux-desktop",
                        "parameters": '{"width": 1024}',
                    },
                )

            self.assertIn("txt2img", catalog.get_json()["operations"])
            self.assertEqual(response.status_code, 202)
            self.assertEqual(response.get_json()["job"]["id"], "job-1")
            self.assertEqual(jobs.submit.call_args.kwargs["installation_id"], state.installation_id)
            self.assertEqual(state.selected_model("txt2img"), "flux-desktop")
            memory_store.record_image_generation.assert_called_once_with(state.installation_id, state.person_id, "A desktop robot")

    def test_media_generation_reads_visual_browser_selection_server_side(self):
        queued = {
            "id": "job-visual", "status": "queued", "kind": "image",
            "operation": "img2img", "prompt": "Restyle it", "model_slug": "",
        }
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "images"
            root.mkdir()
            image_path = root / "selected.png"
            image_path.write_bytes(b"local-image-bytes")
            state = DesktopState(Path(directory) / "state")
            jobs = MagicMock()
            jobs.submit.return_value = queued
            app = create_desktop_app(state=state, runtime=AsyncRuntime(), job_manager=jobs)
            client = app.test_client()
            opened = client.post("/api/desktop/image-browser/open", json={"path": str(root)})
            token = opened.get_json()["token"]

            response = client.post(
                "/api/desktop/media/generate",
                data={
                    "operation": "img2img",
                    "prompt": "Restyle it",
                    "parameters": "{}",
                    "source_browser_token": token,
                    "source_browser_path": "selected.png",
                },
            )

            self.assertEqual(response.status_code, 202)
            source = jobs.submit.call_args.kwargs["source"]
            self.assertEqual(source.filename, "selected.png")
            self.assertEqual(source.content_type, "image/png")
            self.assertEqual(source.data, b"local-image-bytes")

    def test_media_balance_is_returned_without_exposing_key(self):
        with tempfile.TemporaryDirectory() as directory:
            state = DesktopState(directory)
            with patch(
                    "web.desktop_app.MediaService.balance",
                    new=AsyncMock(return_value=19.72),
                ):
                app = create_desktop_app(state=state, runtime=AsyncRuntime())
                response = app.test_client().get("/api/desktop/media/balance")

            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.get_json(), {"balance": 19.72, "currency": "USD"})
            self.assertNotIn("key", response.get_data(as_text=True).lower())


if __name__ == "__main__":
    unittest.main()
