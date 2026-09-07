import json
import asyncio
import base64
from concurrent.futures import ThreadPoolExecutor
import threading
import tempfile
import unittest
from io import BytesIO
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from petey.assistant import AssistantReply
from petey.desktop_state import DesktopState
from petey.deapi_stt import DeapiSTTError
from petey.media_jobs import MediaGallery
from web.desktop_app import AsyncRuntime, create_desktop_app
from petey.version import MEDIA_PROVIDER_URL, PROJECT_URL, __version__


class DesktopAppTests(unittest.TestCase):
    def test_tools_api_controls_and_tests_filesystem_mcp(self):
        manager = MagicMock()
        off = {"id": "filesystem", "enabled": False, "connected": False, "tools": []}
        on = {"id": "filesystem", "enabled": True, "connected": True,
              "tools": [{"name": "read_text_file", "description": "Read text"}]}
        manager.public_status.return_value = off
        manager.set_enabled.return_value = on
        manager.test_connection.return_value = on
        with tempfile.TemporaryDirectory() as directory:
            app = create_desktop_app(
                state=DesktopState(directory), memory=MagicMock(),
                job_manager=MagicMock(), mcp_manager=manager,
            )
            client = app.test_client()
            self.assertEqual(client.get("/api/desktop/tools").json["filesystem"], off)
            enabled = client.put("/api/desktop/tools/filesystem", json={"enabled": True})
            tested = client.post("/api/desktop/tools/filesystem/test")
            invalid = client.put("/api/desktop/tools/filesystem", json={"enabled": "yes"})

        self.assertEqual(enabled.json["filesystem"], on)
        self.assertEqual(tested.json["filesystem"], on)
        self.assertEqual(invalid.status_code, 400)
        manager.set_enabled.assert_called_once_with(True)
        manager.test_connection.assert_called_once_with()

    def test_theme_api_and_initial_html_use_saved_theme(self):
        with tempfile.TemporaryDirectory() as directory:
            state = DesktopState(directory)
            client = create_desktop_app(state=state, memory=MagicMock(), job_manager=MagicMock()).test_client()
            response = client.put("/api/desktop/preferences", json={"theme": "paper"})
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json["preferences"]["theme"], "paper")
            self.assertIn('data-theme="paper"', client.get('/').get_data(as_text=True))
            self.assertEqual(client.get('/api/desktop/bootstrap').json['preferences']['theme'], 'paper')
            self.assertEqual(client.put('/api/desktop/preferences', json={'theme': 'bad'}).status_code, 400)

    def test_gemini_model_selection_also_updates_vision(self):
        with tempfile.TemporaryDirectory() as directory:
            state = DesktopState(directory)
            state.update_ai_provider({"provider": "gemini", "model": "gemini-new-flash"})
            self.assertEqual(state.ai_provider["gemini"]["vision_model"], "gemini-new-flash")
            state.update_ai_provider({"provider": "local", "model": "local-chat"})
            self.assertEqual(state.ai_provider["gemini"]["vision_model"], "gemini-new-flash")

    def test_vision_catalog_uses_gemini_without_changing_chat_provider(self):
        with tempfile.TemporaryDirectory() as directory:
            state = DesktopState(directory)
            state.update_ai_provider({"provider": "local", "model": "local-chat"})
            before = state.ai_provider
            app = create_desktop_app(state=state, memory=MagicMock(), job_manager=MagicMock())
            def catalog(provider):
                self.assertEqual(provider.provider, "gemini")
                return ["gemini-new-flash", "gemini-new-pro"]
            with patch("web.desktop_app.AIProvider.list_models", autospec=True, side_effect=catalog):
                response = app.test_client().get("/api/desktop/ai-provider/models?provider=gemini")
            self.assertEqual(response.json["models"], ["gemini-new-flash", "gemini-new-pro"])
            self.assertEqual(state.ai_provider, before)
            self.assertEqual(state.ai_provider["provider"], "local")
            self.assertEqual(app.test_client().get("/api/desktop/ai-provider/models?provider=bad").status_code, 400)

    def test_chat_stream_delivers_text_before_reply_finishes(self):
        release = threading.Event()
        async def respond(*args, on_text, **kwargs):
            on_text("Hello ")
            if not release.wait(3):
                raise RuntimeError("Client did not receive first delta")
            on_text("world")
            return AssistantReply(text="Hello world")
        with tempfile.TemporaryDirectory() as directory:
            app = create_desktop_app(state=DesktopState(directory), memory=MagicMock(), job_manager=MagicMock())
            with patch("web.desktop_app.AssistantService.respond", side_effect=respond):
                response = app.test_client().post("/api/desktop/chat", data={"message": "Hi", "stream": "true"}, buffered=False)
                chunks = iter(response.response)
                self.assertEqual(json.loads(next(chunks))["type"], "status")
                self.assertEqual(json.loads(next(chunks)), {"type": "delta", "text": "Hello "})
                release.set()
                events = [json.loads(chunk) for chunk in chunks]
                self.assertEqual(events[-1]["type"], "done")
                self.assertEqual(events[-1]["text"], "Hello world")
                self.assertNotIn("gif_url", events[-1])
                response.close()

    def test_chat_stream_reports_errors_without_done(self):
        async def respond(*args, on_text, **kwargs):
            on_text("Partial")
            raise ValueError("Interrupted")
        with tempfile.TemporaryDirectory() as directory:
            app = create_desktop_app(state=DesktopState(directory), memory=MagicMock(), job_manager=MagicMock())
            with patch("web.desktop_app.AssistantService.respond", side_effect=respond):
                response = app.test_client().post("/api/desktop/chat", data={"message": "Hi", "stream": "true"})
                events = [json.loads(line) for line in response.data.splitlines()]
            self.assertEqual([event["type"] for event in events], ["status", "delta", "error"])

    def test_media_price_lookup_never_queues_a_generation(self):
        with tempfile.TemporaryDirectory() as directory:
            jobs = MagicMock()
            app = create_desktop_app(state=DesktopState(directory), runtime=AsyncRuntime(), job_manager=jobs)
            client = app.test_client()
            quote = {"price": 0.003, "currency": "USD", "model_slug": "model"}
            with patch("web.desktop_app.MediaService.estimate", new=AsyncMock(return_value=quote)) as estimate:
                response = client.post("/api/desktop/media/estimate", data={
                    "operation": "txt2img", "model_slug": "model", "parameters": '{"width":512}', "prompt": "Robot",
                })
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json, quote)
                estimate.assert_awaited_once_with("txt2img", "model", {"width": 512}, "Robot", None)
            for operation in ("txt2audio", "txt2music"):
                self.assertEqual(client.post("/api/desktop/media/estimate", data={"operation": operation}).status_code, 400)
            self.assertEqual(client.post("/api/desktop/media/estimate", data={"parameters": "[]"}).status_code, 400)
            self.assertEqual(client.post("/api/desktop/media/estimate", data={"operation": "img-upscale"}).status_code, 400)
            jobs.submit.assert_not_called()

    def test_initial_media_models_and_balance_have_independent_sessions(self):
        # The first Media visit requests both endpoints concurrently. A shared
        # aiohttp client cannot be used across their separate Flask event loops.
        barrier = threading.Barrier(2)
        clients = []

        class Client:
            def __init__(self, api_key=None):
                self.api_key = api_key
                self.loop = None
                self.closed = False

            async def read(self, result):
                loop = asyncio.get_running_loop()
                if self.loop is None:
                    self.loop = loop
                barrier.wait(timeout=3)
                await asyncio.sleep(0)
                if self.loop is not loop or self.closed:
                    raise RuntimeError("Media session belongs to another request")
                return result

            async def get_models(self, operation):
                return await self.read([{"slug": "image-model", "name": "Image model"}])

            async def get_balance(self):
                return await self.read(12.34)

            async def close(self):
                self.closed = True

        def make_client(**kwargs):
            client = Client(**kwargs)
            clients.append(client)
            return client

        shared = Client()
        with tempfile.TemporaryDirectory() as directory, patch.dict(
            "os.environ", {"DEAPI_KEY": "test-environment-key"}
        ), patch("petey.deapi_client.DeapiClient", side_effect=make_client), patch(
            "petey.deapi_client.deapi", shared
        ), patch("petey.media_service.deapi", shared):
            app = create_desktop_app(state=DesktopState(directory), runtime=AsyncRuntime())

            def get(path):
                with app.test_client() as client:
                    response = client.get(path)
                    return response.status_code, response.get_json()

            with ThreadPoolExecutor(max_workers=2) as executor:
                models = executor.submit(get, "/api/desktop/media/models/txt2img")
                balance = executor.submit(get, "/api/desktop/media/balance")
                self.assertEqual(models.result(), (200, {"operation": "txt2img", "models": [{"slug": "image-model", "name": "Image model"}]}))
                self.assertEqual(balance.result(), (200, {"balance": 12.34, "currency": "USD"}))
            self.assertEqual(len(clients), 2)
            self.assertIsNot(clients[0].loop, clients[1].loop)
            self.assertTrue(all(client.closed for client in clients))

    def test_provider_keys_are_redacted_and_do_not_switch_chat(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(
            "os.environ", {"DEAPI_KEY": "environment-secret"}, clear=True
        ):
            state = DesktopState(directory)
            state.update_ai_provider({"provider": "local", "model": "my-model"})
            client = create_desktop_app(state=state, runtime=object()).test_client()
            for provider in ("gemini", "openai", "local", "deapi"):
                response = client.put("/api/desktop/provider-keys", json={
                    "provider": provider, "api_key": "saved-secret",
                })
                self.assertEqual(response.status_code, 200)
                self.assertNotIn("saved-secret", response.get_data(as_text=True))
                self.assertNotIn("environment-secret", response.get_data(as_text=True))
                self.assertEqual(response.json["providers"][provider]["source"], "saved")
            self.assertEqual(state.ai_provider["provider"], "local")
            self.assertEqual(state.ai_provider["local"]["model"], "my-model")
            client.put("/api/desktop/provider-keys", json={"provider": "deapi", "api_key": ""})
            self.assertEqual(DesktopState(directory).ai_provider["deapi"]["api_key"], "saved-secret")
            response = client.put("/api/desktop/provider-keys", json={"provider": "deapi", "clear_api_key": True})
            self.assertEqual(response.json["providers"]["deapi"]["source"], "environment")
            self.assertEqual(DesktopState(directory).ai_provider["deapi"]["api_key"], "")
            for payload in ([1], {"provider": "unknown"}, {"provider": "gemini", "api_key": [1]}, {"provider": "gemini", "api_key": "x" * 4097}):
                self.assertEqual(client.put("/api/desktop/provider-keys", json=payload).status_code, 400)

    def test_saved_media_key_reaches_transcription_and_catalog(self):
        with tempfile.TemporaryDirectory() as directory:
            state = DesktopState(directory)
            state.update_provider_key("deapi", "saved-media-key")
            state.update_voice_input({"mode": "push_to_talk", "provider": "deapi"})
            client = create_desktop_app(state=state, runtime=object()).test_client()
            self.assertTrue(client.get("/api/desktop/voice-input").json["deapi_has_api_key"])
            self.assertTrue(client.get("/api/desktop/media").json["configured"])
            with patch("web.desktop_app.DeapiSTT") as stt:
                stt.return_value.transcribe.return_value = "Hello"
                response = client.post("/api/desktop/voice-input/transcribe", data={"audio": (BytesIO(b"RIFF-audio"), "test.wav")})
                self.assertEqual(response.status_code, 200)
                stt.assert_called_once_with(api_key="saved-media-key")

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
            self.assertIn('id="view-providers"', shell.get_data(as_text=True))
            self.assertIn('id="view-help"', shell.get_data(as_text=True))
            self.assertIn("https://aistudio.google.com/apikey", shell.get_data(as_text=True))
            self.assertIn("https://platform.openai.com/api-keys", shell.get_data(as_text=True))
            self.assertIn("https://docs.deapi.ai/quickstart", shell.get_data(as_text=True))
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
            self.assertNotIn("gif_url", response.get_json())

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
                json={
                    "name": "Desktop Petey", "system_prompt": "You are Desktop Petey.",
                    "speech": {
                        "provider": "gemini", "gemini_voice": "Sulafat",
                        "gemini_model": "gemini-3.1-flash-tts-preview",
                        "auto_speak": True,
                    },
                },
            )

            self.assertIn("friendly_helper", current.get_json()["presets"])
            self.assertEqual(saved.status_code, 200)
            self.assertEqual(saved.get_json()["persona"]["name"], "Desktop Petey")
            self.assertEqual(saved.get_json()["speech"]["gemini_voice"], "Sulafat")
            self.assertTrue(state.speech["auto_speak"])

    def test_personality_slots_can_be_saved_and_cleared(self):
        with tempfile.TemporaryDirectory() as directory:
            state = DesktopState(directory)
            app = create_desktop_app(state=state, runtime=object())
            client = app.test_client()

            saved = client.put(
                "/api/desktop/personality/slots/2",
                json={
                    "name": "Writer Petey", "system_prompt": "You are a writing partner.",
                    "speech": {
                        "provider": "gemini", "gemini_voice": "Kore",
                        "gemini_model": "gemini-3.1-flash-tts-preview",
                    },
                },
            )
            current = client.get("/api/desktop/personality")
            cleared = client.delete("/api/desktop/personality/slots/2")

            self.assertEqual(saved.status_code, 200)
            self.assertEqual(saved.get_json()["persona"]["name"], "Writer Petey")
            self.assertEqual(current.get_json()["saved_personas"][1]["name"], "Writer Petey")
            self.assertEqual(current.get_json()["saved_personas"][1]["speech"]["gemini_voice"], "Kore")
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

    def test_speech_settings_expose_gemini_choices_without_exposing_key(self):
        with tempfile.TemporaryDirectory() as directory:
            state = DesktopState(directory)
            state.update_ai_provider({"provider": "gemini", "api_key": "private-gemini-key"})
            app = create_desktop_app(state=state, runtime=object())
            client = app.test_client()

            response = client.put("/api/desktop/speech", json={
                "provider": "gemini",
                "gemini_model": "gemini-3.1-flash-tts-preview",
                "gemini_voice": "Kore",
                "consistent_voice": True,
            })

            payload = response.get_json()
            self.assertEqual(response.status_code, 200)
            self.assertTrue(payload["gemini_has_api_key"])
            self.assertFalse(payload["openai_has_api_key"])
            self.assertIn("gpt-4o-mini-tts", payload["openai_models"])
            self.assertIn("marin", payload["openai_voices"])
            self.assertTrue(payload["configuration"]["consistent_voice"])
            self.assertFalse(payload["balance_available_via_api"])
            self.assertIn("Kore", [voice["name"] for voice in payload["gemini_voices"]])
            self.assertNotIn("private-gemini-key", response.get_data(as_text=True))

    def test_microphone_settings_and_transcription_endpoint(self):
        with tempfile.TemporaryDirectory() as directory:
            state = DesktopState(directory)
            state.update_ai_provider({"provider": "gemini", "api_key": "private-key"})
            app = create_desktop_app(state=state, runtime=object())
            client = app.test_client()

            saved = client.put("/api/desktop/voice-input", json={
                "mode": "wake_word", "provider": "gemini",
                "model": "gemini-3.5-transcribe", "wake_word": "Petey",
                "device_id": "usb-mic-1", "sensitivity": "high",
            })
            self.assertEqual(saved.status_code, 200)
            self.assertEqual(saved.get_json()["configuration"]["mode"], "wake_word")
            self.assertEqual(saved.get_json()["configuration"]["device_id"], "usb-mic-1")
            self.assertNotIn("private-key", saved.get_data(as_text=True))

            with patch("web.desktop_app.GeminiSTT.transcribe", return_value="Petey hello") as transcribe:
                response = client.post(
                    "/api/desktop/voice-input/transcribe",
                    data={"audio": (BytesIO(b"RIFF-audio"), "microphone.wav")},
                    content_type="multipart/form-data",
                )
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.get_json()["transcript"], "Petey hello")
            self.assertEqual(transcribe.call_args.args[1], "audio/x-wav")
            self.assertEqual(transcribe.call_args.kwargs["vocabulary"], ["Petey"])

    def test_microphone_uses_deapi_then_falls_back_to_gemini(self):
        with tempfile.TemporaryDirectory() as directory:
            state = DesktopState(directory)
            state.update_voice_input({
                "mode": "push_to_talk", "provider": "deapi",
                "model": "WhisperLargeV3",
            })
            app = create_desktop_app(state=state, runtime=object())
            client = app.test_client()

            with patch("web.desktop_app.DeapiSTT.transcribe", return_value="cheap transcript") as deapi:
                response = client.post(
                    "/api/desktop/voice-input/transcribe",
                    data={"audio": (BytesIO(b"RIFF-audio"), "microphone.wav")},
                    content_type="multipart/form-data",
                )
            self.assertEqual(response.get_json()["provider"], "deapi")
            self.assertEqual(response.get_json()["transcript"], "cheap transcript")
            deapi.assert_called_once()

            with patch(
                "web.desktop_app.DeapiSTT.transcribe",
                side_effect=DeapiSTTError("media transcription unavailable"),
            ), patch("web.desktop_app.GeminiSTT.transcribe", return_value="fallback transcript"):
                response = client.post(
                    "/api/desktop/voice-input/transcribe",
                    data={"audio": (BytesIO(b"RIFF-audio"), "microphone.wav")},
                    content_type="multipart/form-data",
                )
            self.assertEqual(response.get_json()["provider"], "gemini")
            self.assertEqual(response.get_json()["transcript"], "fallback transcript")

    def test_chat_speech_queues_temporary_audio_outside_gallery(self):
        queued = {"id": "speech-job", "status": "queued", "kind": "audio"}
        with tempfile.TemporaryDirectory() as directory:
            state = DesktopState(directory)
            state.update_speech({
                "provider": "gemini", "gemini_model": "gemini-3.1-flash-tts-preview",
                "gemini_voice": "Kore", "auto_speak": True,
            })
            jobs = MagicMock()
            jobs.submit.return_value = queued
            app = create_desktop_app(state=state, runtime=object(), job_manager=jobs)
            client = app.test_client()

            response = client.post("/api/desktop/chat/speech", json={"text": "Hello there"})

            self.assertEqual(response.status_code, 202)
            self.assertEqual(response.get_json()["job"]["id"], "speech-job")
            self.assertFalse(jobs.submit.call_args.kwargs["save_to_gallery"])
            self.assertEqual(jobs.submit.call_args.kwargs["parameters"]["voice"], "Kore")
            self.assertTrue(client.get("/api/desktop/bootstrap").get_json()["speech"]["auto_speak"])

    def test_chat_speech_serves_inline_generated_audio(self):
        jobs = MagicMock()
        jobs.result_data.return_value = (b"RIFF-speech", "audio/wav")
        with tempfile.TemporaryDirectory() as directory:
            app = create_desktop_app(
                state=DesktopState(directory), runtime=object(), job_manager=jobs
            )
            response = app.test_client().get("/api/desktop/media/jobs/speech-job/file")

            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.content_type, "audio/wav")
            self.assertEqual(response.data, b"RIFF-speech")
            response.close()

    def test_gemini_chat_speech_streams_audio_chunks(self):
        with tempfile.TemporaryDirectory() as directory:
            state = DesktopState(directory)
            state.update_ai_provider({"provider": "gemini", "api_key": "private-key"})
            state.update_speech({
                "provider": "gemini", "gemini_model": "gemini-3.1-flash-tts-preview",
                "gemini_voice": "Kore",
            })
            app = create_desktop_app(state=state, runtime=object())
            with patch("web.desktop_app.GeminiTTS.stream_pcm", return_value=iter([b"pcm-one", b"pcm-two"])) as stream:
                response = app.test_client().post(
                    "/api/desktop/chat/speech/stream", json={"text": "Hello"}
                )
                body = response.get_data(as_text=True)

            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.content_type, "application/x-ndjson")
            self.assertIn(base64.b64encode(b"pcm-one").decode("ascii"), body)
            self.assertIn('"status": "done"', body)
            self.assertTrue(stream.call_args.args[4])


if __name__ == "__main__":
    unittest.main()
