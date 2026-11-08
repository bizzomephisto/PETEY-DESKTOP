import json
import asyncio
import base64
from concurrent.futures import ThreadPoolExecutor
import threading
import tempfile
import time
import unittest
from io import BytesIO
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from petey.ai_provider import AIProvider
from petey.assistant import AssistantReply
from petey.desktop_state import DesktopState
from petey.desktop_memory import DesktopMemory
from petey.deapi_stt import DeapiSTTError
from petey.media_jobs import MediaGallery
from petey.tools.media import DEAPI_IMAGE_CONTROL
from web.desktop_app import AsyncRuntime, create_desktop_app
from petey.version import MEDIA_PROVIDER_URL, PROJECT_URL, __version__


class DesktopAppTests(unittest.TestCase):
    def test_discord_model_media_tool_respects_its_surface_permission(self):
        with tempfile.TemporaryDirectory() as directory:
            state = DesktopState(directory)
            capabilities = [{
                "id": "generate_image", "label": "Generate images",
                "metered": True, "default_daily_limit": 5,
            }]
            app = create_desktop_app(
                state=state, memory=MagicMock(), job_manager=MagicMock()
            )
            bridge = app.config["PETEY_DISCORD"]
            request = "Generate an image of Petey in a tiny spaceship"

            self.assertEqual(bridge.addon_tools_getter().schemas_for(request), [])
            state.update_petey_control(
                "deapi-media", {
                    "enabled": True,
                    "surfaces": {"discord": True},
                }, capabilities,
            )
            names = [
                item["function"]["name"]
                for item in bridge.addon_tools_getter().schemas_for(request)
            ]
            self.assertIn("generate_image", names)

    def test_discord_panel_credentials_catalog_and_controls(self):
        bridge = MagicMock()
        credential = {"has_token": True, "has_saved_token": True, "source": "saved"}
        bridge.status.return_value = {"phase": "disconnected", "credential": credential}
        bridge.credential_status.return_value = credential
        bridge.update_token.return_value = credential
        bridge.catalog.return_value = {"guilds": [], "channels": [], "identity": {"name": "PETEY"}}
        bridge.connect.return_value = {"phase": "connecting", "credential": credential}
        bridge.instruct.return_value = {"phase": "connected", "instructions": [{"status": "queued"}]}
        bridge.set_paused.return_value = {"phase": "connected", "paused": True}
        bridge.set_pace.return_value = {"phase": "connected", "pace": "fast"}
        bridge.set_watched_topics.return_value = {"phase": "connected", "watched_topics": ["linux"]}
        bridge.set_room_prompt.return_value = {"phase": "connected", "room_prompt": "Custom"}
        bridge.set_persona.return_value = {"phase": "connected", "persona_slot": 2}
        bridge.set_memory_policy.return_value = {"phase": "connected", "memory_policy": "store"}
        bridge.set_auto_connect.return_value = {"phase": "disconnected", "auto_connect": True}
        bridge.enhance_room_prompt.return_value = {"prompt": "Enhanced room behavior"}
        bridge.resolve_admin_proposal.return_value = {"phase": "connected", "admin_proposals": []}
        bridge.disconnect.return_value = {"phase": "stopping"}
        with tempfile.TemporaryDirectory() as directory:
            app = create_desktop_app(state=DesktopState(directory), memory=MagicMock(), discord_bridge=bridge)
            client = app.test_client()
            html = client.get('/').get_data(as_text=True)
            self.assertIn('id="view-discord"', html)
            self.assertIn('id="discord-topics"', html)
            self.assertIn('id="discord-room-prompt"', html)
            self.assertIn('id="discord-persona"', html)
            self.assertIn('id="discord-memory-policy"', html)
            self.assertIn('id="discord-memory-warning"', html)
            self.assertIn('id="discord-auto-connect"', html)
            self.assertIn('id="discord-enhance-room-prompt"', html)
            self.assertIn('id="discord-admin-status"', html)
            self.assertIn('/genimg, /img2img', html)
            self.assertNotIn('secret-token', html)
            self.assertEqual(client.get('/api/desktop/discord').json['phase'], 'disconnected')
            self.assertTrue(client.get('/api/desktop/discord/token').json['credential']['has_token'])
            self.assertEqual(client.put('/api/desktop/discord/token', json={"token": "secret-token"}).status_code, 200)
            self.assertEqual(client.get('/api/desktop/discord/catalog?guild_id=222222222222222222').status_code, 200)
            connected = client.post('/api/desktop/discord/connect', json={
                "guild_id": "222222222222222222", "channel_id": "333333333333333333",
                "guild": "Friends", "channel": "#general",
            })
            self.assertEqual(connected.json['phase'], 'connecting')
            self.assertEqual(client.post('/api/desktop/discord/instruct', json={"text": "Start trivia"}).status_code, 200)
            self.assertTrue(client.post('/api/desktop/discord/pause', json={"paused": True}).json['paused'])
            self.assertEqual(client.post('/api/desktop/discord/pace', json={"pace": "fast"}).json['pace'], 'fast')
            self.assertEqual(
                client.post('/api/desktop/discord/topics', json={"topics": ["linux"]}).json['watched_topics'],
                ['linux'],
            )
            self.assertEqual(
                client.post('/api/desktop/discord/room-prompt', json={"prompt": "Custom"}).json['room_prompt'],
                'Custom',
            )
            self.assertEqual(
                client.post('/api/desktop/discord/persona', json={"persona_slot": 2}).json['persona_slot'],
                2,
            )
            self.assertEqual(
                client.post('/api/desktop/discord/memory-policy', json={"policy": "store"}).json['memory_policy'],
                'store',
            )
            self.assertTrue(client.post(
                '/api/desktop/discord/auto-connect', json={"enabled": True}
            ).json['auto_connect'])
            self.assertEqual(client.post(
                '/api/desktop/discord/enhance-room-prompt', json={"prompt": "Make this better"}
            ).json['prompt'], 'Enhanced room behavior')
            self.assertEqual(client.post(
                '/api/desktop/discord/admin-approve', json={"id": "proposal-1"}
            ).status_code, 200)
            self.assertEqual(client.post(
                '/api/desktop/discord/admin-reject', json={"id": "proposal-2"}
            ).status_code, 200)
            self.assertEqual(client.post('/api/desktop/discord/disconnect', json={}).json['phase'], 'stopping')
            self.assertEqual(client.put('/api/desktop/discord/token', json={"token": "x"}, headers={"Origin": "https://evil.example"}).status_code, 403)
            self.assertEqual(client.post('/api/desktop/discord/connect', json={}, headers={"Origin": "https://evil.example"}).status_code, 403)
            self.assertEqual(client.post('/api/desktop/discord/connect', data='{}').status_code, 400)
        bridge.update_token.assert_called_once_with('secret-token', clear=False)
        bridge.catalog.assert_called_once_with('222222222222222222')
        bridge.connect.assert_called_once_with('222222222222222222', '333333333333333333', 'Friends', '#general')

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

    def test_filesystem_folders_are_managed_inside_tools(self):
        manager = MagicMock()
        with tempfile.TemporaryDirectory() as directory, tempfile.TemporaryDirectory() as folder:
            state = DesktopState(directory)
            client = create_desktop_app(
                state=state, memory=MagicMock(), job_manager=MagicMock(), mcp_manager=manager,
            ).test_client()

            added = client.post(
                "/api/desktop/tools/filesystem/folders", json={"path": folder}
            )
            folder_id = added.json["folder"]["id"]
            listed = client.get("/api/desktop/tools/filesystem/folders")
            removed = client.delete(
                f"/api/desktop/tools/filesystem/folders/{folder_id}"
            )

        self.assertEqual(added.status_code, 201)
        self.assertEqual(listed.json["folders"][0]["path"], str(Path(folder).resolve()))
        self.assertEqual(removed.json["folders"], [])
        self.assertEqual(manager.disconnect.call_count, 2)

    def test_theme_api_and_initial_html_use_saved_theme(self):
        with tempfile.TemporaryDirectory() as directory:
            state = DesktopState(directory)
            client = create_desktop_app(state=state, memory=MagicMock(), job_manager=MagicMock()).test_client()
            response = client.put("/api/desktop/preferences", json={"theme": "cognitive", "theme_accent": "#cc5500"})
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json["preferences"]["theme"], "cognitive")
            self.assertEqual(response.json["preferences"]["theme_accents"]["cognitive"], "#cc5500")
            html = client.get('/').get_data(as_text=True)
            self.assertIn('data-theme="cognitive"', html)
            self.assertIn('--theme-accent: #cc5500', html)
            self.assertEqual(client.get('/api/desktop/bootstrap').json['preferences']['theme'], 'cognitive')
            self.assertEqual(client.put('/api/desktop/preferences', json={'theme': 'bad'}).status_code, 400)
            self.assertEqual(client.put('/api/desktop/preferences', json={'theme_accent': 'orange'}).status_code, 400)

    def test_command_center_and_configurable_rail_are_server_rendered(self):
        with tempfile.TemporaryDirectory() as directory:
            state = DesktopState(directory)
            client = create_desktop_app(
                state=state, memory=MagicMock(), job_manager=MagicMock()
            ).test_client()
            response = client.put(
                "/api/desktop/preferences",
                json={
                    "command_rail_open": False,
                    "command_rail_sections": {"launch": False},
                    "command_rail_order": ["signals", "session", "launch", "addons"],
                    "command_rail_collapsed": ["signals"],
                },
            )
            self.assertEqual(response.status_code, 200)
            self.assertFalse(response.json["preferences"]["command_rail_open"])
            self.assertFalse(response.json["preferences"]["command_rail_sections"]["launch"])
            self.assertEqual(response.json["preferences"]["command_rail_order"][0], "signals")
            self.assertEqual(response.json["preferences"]["command_rail_collapsed"], ["signals"])
            html = client.get("/").get_data(as_text=True)
            self.assertIn('data-interface="command"', html)
            self.assertIn('data-command-rail="closed"', html)
            self.assertIn('id="command-rail"', html)
            self.assertFalse(client.get("/api/desktop/bootstrap").json["preferences"]["command_rail_open"])
            invalid = client.put("/api/desktop/preferences", json={
                "command_rail_sections": {"other": True}
            })
            self.assertEqual(invalid.status_code, 400)

    def test_active_chat_model_is_reported_as_the_vision_model(self):
        with tempfile.TemporaryDirectory() as directory:
            state = DesktopState(directory)
            state.update_ai_provider({"provider": "gemini", "model": "gemini-new-flash"})
            self.assertEqual(
                AIProvider(state.ai_provider).public_config()["vision_model"],
                "gemini-new-flash",
            )
            state.update_ai_provider({"provider": "local", "model": "local-chat"})
            self.assertEqual(
                AIProvider(state.ai_provider).public_config()["vision_model"],
                "local-chat",
            )

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
            sidebar = shell.get_data(as_text=True).split('<aside class="sidebar">', 1)[1]
            self.assertNotIn("deAPI Media", sidebar.split("</aside>", 1)[0])
            self.assertIn('id="view-providers"', shell.get_data(as_text=True))
            self.assertIn('id="view-help"', shell.get_data(as_text=True))
            self.assertNotIn('id="view-plan"', shell.get_data(as_text=True))
            self.assertNotIn('data-view="plan"', shell.get_data(as_text=True))
            self.assertNotIn('data-view="workspace"', shell.get_data(as_text=True))
            self.assertNotIn('id="view-workspace"', shell.get_data(as_text=True))
            dormant_plan = (
                Path(__file__).parents[1] / "web/templates/dormant/petey_plus.html"
            ).read_text(encoding="utf-8")
            self.assertEqual(dormant_plan.count('data-plan-quality='), 3)
            self.assertIn('id="plan-live-impact"', dormant_plan)
            self.assertIn("https://aistudio.google.com/apikey", shell.get_data(as_text=True))
            self.assertIn("https://platform.openai.com/api-keys", shell.get_data(as_text=True))
            self.assertIn("https://docs.deapi.ai/quickstart", shell.get_data(as_text=True))
            self.assertEqual(bootstrap.status_code, 200)
            self.assertEqual(
                bootstrap.get_json()["installation_id"], state.installation_id
            )
            self.assertEqual(bootstrap.get_json()["version"], __version__)
            self.assertIn("messages", bootstrap.get_json())
            self.assertIn("voice_cues", bootstrap.get_json())

            revision = app.config["PETEY_ASSET_REVISION"]
            cached_asset = client.head(f"/static/desktop.js?v={revision}")
            self.assertEqual(
                cached_asset.headers["Cache-Control"],
                "public, max-age=31536000, immutable",
            )
            uncached_asset = client.head("/static/desktop.js")
            self.assertNotIn("immutable", uncached_asset.headers.get("Cache-Control", ""))
            cached_asset.close()
            uncached_asset.close()

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
            {"id": 2, "user_id": "ADDON:spotify", "message": "Hidden track event",
             "timestamp": "now", "metadata": {"hidden_from_chat": True}},
            {"id": 3, "user_id": "PETEY", "message": "Hey", "timestamp": "now"},
        ]
        with tempfile.TemporaryDirectory() as directory:
            state = DesktopState(directory)
            memory_store = MagicMock()
            memory_store.get_conversation_messages.return_value = rows
            app = create_desktop_app(state=state, runtime=object(), memory=memory_store)
            response = app.test_client().get("/api/desktop/messages")

            self.assertEqual([item["role"] for item in response.get_json()], ["user", "assistant"])
            updates = app.test_client().get("/api/desktop/addon-events?after=0").get_json()
            self.assertEqual(updates, {"cursor": 0, "events": []})

    def test_addon_event_hides_prompt_and_publishes_petey_reply(self):
        with tempfile.TemporaryDirectory() as directory:
            state = DesktopState(directory)
            memory = DesktopMemory(Path(directory) / "event-memory.sqlite3", lambda _text: None)
            app = create_desktop_app(state=state, memory=memory)
            client = app.test_client()
            with patch("petey.assistant.AIProvider.complete", return_value="Now playing So What."):
                queued = app.config["PETEY_ADDON_EVENTS"].emit(
                    "spotify",
                    "Spotify changed to So What by Miles Davis.",
                    conversation_id=state.conversation_id,
                    speak=True,
                    metadata={"conference_session_id": "session-1"},
                )
                self.assertEqual(queued["status"], "queued")
                deadline = time.time() + 2
                updates = {"events": []}
                while time.time() < deadline and not updates["events"]:
                    time.sleep(0.02)
                    updates = client.get("/api/desktop/addon-events?after=0").get_json()

            self.assertEqual(updates["events"][0]["text"], "Now playing So What.")
            self.assertTrue(updates["events"][0]["speak"])
            self.assertEqual(updates["events"][0]["surface"], "petey_desktop")
            self.assertEqual(
                updates["events"][0]["metadata"]["conference_session_id"], "session-1"
            )
            messages = client.get("/api/desktop/messages").get_json()
            self.assertEqual([item["message"] for item in messages], ["Now playing So What."])
            self.assertEqual(
                messages[0]["metadata"]["conference_session_id"], "session-1"
            )
            app.config["PETEY_ADDONS"].close()

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

    def test_chat_routes_image_requests_and_preserves_ordered_edit_uploads(self):
        with tempfile.TemporaryDirectory() as directory:
            state = DesktopState(directory)
            state.update_provider_key("deapi", "test-key")
            state.update_petey_control("deapi-media", {"enabled": True}, DEAPI_IMAGE_CONTROL)
            jobs = MagicMock()
            jobs.submit.return_value = {"id": "image-job"}
            memory = MagicMock()
            app = create_desktop_app(
                state=state, runtime=AsyncRuntime(), job_manager=jobs, memory=memory,
            )
            client = app.test_client()

            def use_tool(prompt, system, history, schemas, execute, *, require_tool):
                self.assertTrue(require_tool)
                self.assertEqual(len(schemas), 1)
                name = schemas[0]["function"]["name"]
                result = execute(name, {"prompt": prompt.splitlines()[0]})
                if name == "edit_images":
                    self.assertLess(prompt.index("first.jpg"), prompt.index("second.png"))
                    retry = execute(name, {"prompt": "Try another variation"})
                    self.assertEqual(retry["job_id"], result["job_id"])
                return "Image queued.", [{"name": name, "result": result}]

            with (
                patch.object(AIProvider, "complete_with_tools", side_effect=use_tool),
                patch.object(AIProvider, "describe_image") as vision,
            ):
                generated = client.post("/api/desktop/chat", data={"message": "Generate an image of a cat"})
                self.assertEqual(generated.status_code, 200, generated.json)
                self.assertEqual(generated.json["tool_events"][0]["name"], "generate_image")
                self.assertEqual(jobs.submit.call_args.kwargs["operation"], "txt2img")
                self.assertEqual(jobs.submit.call_args.kwargs["parameters"], {})
                jobs.submit.reset_mock()

                edited = client.post("/api/desktop/chat", data={
                    "message": "Combine them and add funny hats to each of them.",
                    "surface": "mobile_petey",
                    "stream": "true",
                    "attachment": [(BytesIO(b"first"), "first.jpg"), (BytesIO(b"second"), "second.png")],
                })
                self.assertEqual(edited.status_code, 200)
                done = json.loads(edited.get_data(as_text=True).splitlines()[-1])
                self.assertEqual(done["tool_events"][0]["name"], "edit_images")
                jobs.submit.assert_called_once()
                submission = jobs.submit.call_args.kwargs
                self.assertEqual(submission["operation"], "img2img")
                self.assertTrue(submission["select_compatible_edit_model"])
                self.assertEqual(
                    [(item.filename, item.content_type, item.data) for item in submission["references"]],
                    [("first.jpg", "image/jpeg", b"first"), ("second.png", "image/png", b"second")],
                )
                vision.assert_not_called()

            jobs.submit.reset_mock()
            with (
                patch.object(AIProvider, "complete", return_value="Two cats."),
                patch.object(AIProvider, "describe_image", return_value="A cat.") as vision,
            ):
                inspected = client.post("/api/desktop/chat", data={
                    "message": "What is in these images?",
                    "attachment": [(BytesIO(b"first"), "first.jpg"), (BytesIO(b"second"), "second.png")],
                })
                self.assertEqual(inspected.json["tool_events"], [])
                self.assertEqual(vision.call_count, 2)
            jobs.submit.assert_not_called()

            state.update_petey_control("deapi-media", {"surfaces": {"mobile_petey": False}}, DEAPI_IMAGE_CONTROL)
            with patch.object(AIProvider, "complete", return_value="The edit tool is unavailable."):
                denied = client.post("/api/desktop/chat", data={
                    "message": "Edit this photo",
                    "surface": "mobile_petey",
                    "attachment": (BytesIO(b"first"), "first.jpg"),
                })
                self.assertEqual(denied.json["tool_events"], [])
            jobs.submit.assert_not_called()

    def test_chat_route_uses_the_conversations_assigned_persona(self):
        with tempfile.TemporaryDirectory() as directory:
            state = DesktopState(directory)
            state.save_persona_slot(1, {
                "name": "Story Petey",
                "system_prompt": "You narrate from the old lighthouse.",
            })
            state.create_conversation("Lighthouse", 1)
            with patch("web.desktop_app.AssistantService") as service_type:
                service_type.return_value.respond = AsyncMock(
                    return_value=AssistantReply("The lamp turns slowly.")
                )
                app = create_desktop_app(state=state, runtime=AsyncRuntime())
                response = app.test_client().post(
                    "/api/desktop/chat",
                    data={"message": "Continue", "surface": "mobile_petey"},
                )

            self.assertEqual(response.status_code, 200)
            self.assertIn("old lighthouse", service_type.call_args.args[0])
            self.assertNotEqual(service_type.call_args.args[0], state.system_prompt)
            self.assertEqual(
                service_type.return_value.respond.call_args.args[1].surface,
                "mobile_petey",
            )

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
                disposable = client.post(
                    "/api/desktop/conversations", json={"title": "Disposable"}
                ).get_json()["conversation_id"]
                saved = client.put(
                    "/api/desktop/preferences",
                    json={"always_on_top": True, "ui_scale": 1.3},
                )
                renamed = client.patch(
                    f"/api/desktop/conversations/{conversation_id}",
                    json={"title": "Named ideas"},
                )
                preserved = client.delete(
                    f"/api/desktop/conversations/{conversation_id}?preserve_memory=true"
                )
                deleted = client.delete(
                    f"/api/desktop/conversations/{disposable}?preserve_memory=false"
                )

            self.assertEqual(created.status_code, 201)
            self.assertEqual(created.get_json()["conversation"]["title"], "Ideas")
            self.assertTrue(saved.get_json()["preferences"]["always_on_top"])
            self.assertEqual(saved.get_json()["preferences"]["ui_scale"], 1.3)
            self.assertEqual(renamed.get_json()["conversation"]["title"], "Named ideas")
            self.assertTrue(preserved.get_json()["memory_preserved"])
            self.assertFalse(deleted.get_json()["memory_preserved"])
            self.assertNotEqual(deleted.get_json()["conversation_id"], conversation_id)
            memory_store.clear_conversation.assert_called_once_with(
                state.installation_id, disposable
            )

    def test_conversation_persona_can_be_chosen_when_created_and_changed_in_chat(self):
        with tempfile.TemporaryDirectory() as directory:
            state = DesktopState(directory)
            state.save_persona_slot(1, {
                "name": "Story Petey",
                "role_tag": "Narrator",
                "system_prompt": "You narrate this story.",
                "speech": {"provider": "gemini", "gemini_voice": "Sulafat"},
            })
            app = create_desktop_app(state=state, runtime=object(), memory=MagicMock())
            client = app.test_client()

            shell = client.get("/").get_data(as_text=True)
            created = client.post(
                "/api/desktop/conversations",
                json={"title": "Campaign", "persona_slot": 1},
            )
            conversation_id = created.get_json()["conversation_id"]
            unassigned = client.patch(
                f"/api/desktop/conversations/{conversation_id}",
                json={"persona_slot": None},
            )

            self.assertIn('id="chat-persona"', shell)
            self.assertIn('id="jump-to-latest"', shell)
            self.assertIn('id="new-chat-dialog"', shell)
            self.assertIn('id="delete-chat-dialog"', shell)
            self.assertIn('id="delete-chat-keep-memory"', shell)
            self.assertIn('id="delete-chat-with-memory"', shell)
            self.assertEqual(created.status_code, 201)
            self.assertEqual(created.get_json()["conversation"]["persona_slot"], 1)
            self.assertEqual(created.get_json()["conversation_persona"]["name"], "Story Petey")
            self.assertEqual(created.get_json()["speech"]["gemini_voice"], "Sulafat")
            self.assertIsNone(unassigned.get_json()["conversation"]["persona_slot"])
            self.assertEqual(
                unassigned.get_json()["conversation_persona"]["name"],
                state.persona["name"],
            )

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

    def test_legacy_gemini_vision_setting_does_not_override_local_chat(self):
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
            self.assertEqual(payload["vision_model"], "qwen")
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
            self.assertEqual(saved.get_json()["voice_cues"]["voice"], "Sulafat")
            self.assertTrue(state.speech["auto_speak"])

    def test_prompt_enhancement_uses_the_saved_active_chat_provider(self):
        with tempfile.TemporaryDirectory() as directory:
            state = DesktopState(directory)
            state.update_ai_provider({
                "provider": "local", "model": "local-model",
                "base_url": "http://localhost:1234/v1",
            })
            app = create_desktop_app(
                state=state, memory=MagicMock(), job_manager=MagicMock()
            )
            client = app.test_client()
            providers = []

            def complete(provider, prompt, system_message, history):
                providers.append(provider.provider)
                return f"Enhanced: {prompt}"

            with patch(
                "web.desktop_app.AIProvider.complete", autospec=True,
                side_effect=complete,
            ):
                persona = client.post(
                    "/api/desktop/personality/rewrite", json={"prompt": "Be helpful"}
                )
                media = client.post(
                    "/api/desktop/media/enhance",
                    json={"operation": "txt2img", "prompt": "A local robot"},
                )

            self.assertEqual(persona.status_code, 200)
            self.assertEqual(media.status_code, 200)
            self.assertEqual(providers, ["local", "local"])
            self.assertEqual(persona.json["prompt"], "Enhanced: Be helpful")
            self.assertEqual(media.json["prompt"], "Enhanced: A local robot")
            self.assertEqual(persona.json["provider"], "local")
            self.assertEqual(media.json["provider"], "local")

    def test_personality_wizard_endpoint(self):
        with tempfile.TemporaryDirectory() as directory:
            state = DesktopState(directory)
            app = create_desktop_app(state=state, runtime=object())
            client = app.test_client()

            response = client.post(
                "/api/desktop/personality/wizard",
                json={
                    "archetype": "detective",
                    "name": "Inspector Byte",
                    "role_tag": "Code Detective",
                    "concept": "Treats stack traces like crime scenes.",
                    "traits": ["Analytical", "Methodical", "Witty"],
                    "nuances": ["metaphors", "step_by_step"],
                    "sliders": {"tone": 45, "verbosity": 55, "formality": 65, "empathy": 40},
                    "vocal_vibe": "crisp",
                },
            )
            self.assertEqual(response.status_code, 200)
            data = response.get_json()
            self.assertEqual(data["name"], "Inspector Byte")
            self.assertEqual(data["role_tag"], "Code Detective")
            self.assertIn("You are Inspector Byte", data["system_prompt"])
            self.assertEqual(data["sliders"]["tone"], 45)
            self.assertIn("Analytical", data["traits"])

            invalid = client.post("/api/desktop/personality/wizard", data="invalid json", content_type="application/json")
            self.assertEqual(invalid.status_code, 400)


    def test_personality_slots_can_be_saved_and_cleared(self):
        with tempfile.TemporaryDirectory() as directory:
            state = DesktopState(directory)
            app = create_desktop_app(state=state, runtime=object())
            client = app.test_client()

            saved = client.put(
                "/api/desktop/personality/slots/2",
                json={
                    "name": "Writer Petey", "system_prompt": "You are a writing partner.",
                    "traits": ["Imaginative"],
                    "sliders": {"tone": 66, "verbosity": 81},
                    "speech": {
                        "provider": "gemini", "gemini_voice": "Kore",
                        "gemini_model": "gemini-3.1-flash-tts-preview",
                        "style": "Expressive and warm.",
                    },
                },
            )
            current = client.get("/api/desktop/personality")
            activated = client.post("/api/desktop/personality/slots/2")
            cleared = client.delete("/api/desktop/personality/slots/2")

            self.assertEqual(saved.status_code, 200)
            self.assertEqual(saved.get_json()["persona"]["name"], "Writer Petey")
            self.assertEqual(current.get_json()["saved_personas"][1]["name"], "Writer Petey")
            self.assertEqual(current.get_json()["saved_personas"][1]["speech"]["gemini_voice"], "Kore")
            self.assertEqual(activated.get_json()["persona"]["traits"], ["Imaginative"])
            self.assertEqual(activated.get_json()["persona"]["sliders"]["verbosity"], 81)
            self.assertEqual(activated.get_json()["speech"]["provider"], "gemini")
            self.assertEqual(activated.get_json()["voice_cues"]["voice"], "Kore")
            self.assertEqual(activated.get_json()["speech"]["style"], "Expressive and warm.")
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

    def test_create_queues_full_prompts_and_enhances_with_the_selected_model_limit(self):
        with tempfile.TemporaryDirectory() as directory:
            jobs = MagicMock()
            jobs.submit.return_value = {"id": "test-job", "kind": "video"}
            client = create_desktop_app(
                state=DesktopState(directory), job_manager=jobs, memory=MagicMock(),
            ).test_client()
            prompt = "x" * 14_999 + "."
            for operation in ("txt2img", "txt2video", "txt2music", "txt2audio"):
                with self.subTest(operation=operation):
                    response = client.post("/api/desktop/media/generate", data={
                        "operation": operation, "prompt": prompt,
                    })
                    self.assertEqual(response.status_code, 202)
                    self.assertEqual(jobs.submit.call_args.kwargs["prompt"], prompt)

            model = {"slug": "music-model", "info": {"limits": {"min_caption": 3, "max_caption": 300}}}
            with (
                patch("web.desktop_app.MediaService.models", new=AsyncMock(return_value=[model])),
                patch.object(AIProvider, "complete", side_effect=["x" * 300, "x" * 301]) as complete,
            ):
                models = client.get("/api/desktop/media/models/txt2music")
                self.assertEqual(models.json["models"][0]["prompt_limits"], {"min": 3, "max": 300})
                data = {"operation": "txt2music", "prompt": "A song about a cat", "model_slug": "music-model"}
                enhanced = client.post("/api/desktop/media/enhance", json=data)
                rejected = client.post("/api/desktop/media/enhance", json=data)
                self.assertEqual(enhanced.json["prompt"], "x" * 300)
                self.assertEqual(rejected.status_code, 502)
                self.assertIn("300 characters", rejected.json["error"])
                self.assertIn("300 characters", complete.call_args.args[1])

    def test_media_text_to_speech_supports_deapi_and_gemini_independently(self):
        queued = {
            "id": "speech-media", "status": "queued", "kind": "audio",
            "operation": "txt2audio", "prompt": "Hello", "model_slug": "deapi-tts",
        }
        with tempfile.TemporaryDirectory() as directory:
            state = DesktopState(directory)
            state.update_speech({"provider": "gemini"})
            jobs = MagicMock()
            jobs.submit.return_value = queued
            client = create_desktop_app(
                state=state, runtime=object(), job_manager=jobs,
            ).test_client()
            response = client.post("/api/desktop/media/generate", data={
                "operation": "txt2audio", "prompt": "Hello",
                "model_slug": "deapi-tts", "parameters": '{"voice":"Vivian"}',
            })
            self.assertEqual(response.status_code, 202)
            self.assertEqual(
                jobs.submit.call_args.kwargs["speech_settings"]["provider"], "deapi",
            )

            response = client.post("/api/desktop/media/generate", data={
                "operation": "txt2audio", "prompt": "Hello",
                "model_slug": "gemini-3.1-flash-tts-preview",
                "parameters": '{"voice":"Kore","tts_provider":"gemini"}',
            })
            self.assertEqual(response.status_code, 202)
            speech = jobs.submit.call_args.kwargs["speech_settings"]
            self.assertEqual(speech["provider"], "gemini")
            self.assertEqual(speech["gemini_model"], "gemini-3.1-flash-tts-preview")

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
            self.assertIn("Qwen3_TTS_12Hz_1_7B_CustomVoice", payload["deapi_models"])
            self.assertIn("Vivian", [voice["name"] for voice in payload["deapi_voices"]])
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
                "mode": "wake_word", "muted": True, "provider": "gemini",
                "model": "gemini-3.5-transcribe", "wake_word": "Petey",
                "device_id": "usb-mic-1", "sensitivity": "high",
            })
            self.assertEqual(saved.status_code, 200)
            self.assertEqual(saved.get_json()["configuration"]["mode"], "wake_word")
            self.assertTrue(saved.get_json()["configuration"]["muted"])
            self.assertEqual(saved.get_json()["configuration"]["device_id"], "usb-mic-1")
            self.assertTrue(client.get("/api/desktop/bootstrap").get_json()["voice_input"]["muted"])
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

    def test_wake_acknowledgement_catalog_uses_current_voice_then_default(self):
        with tempfile.TemporaryDirectory() as directory:
            state = DesktopState(directory)
            state.update_speech({"provider": "gemini", "gemini_voice": "Kore"})
            app = create_desktop_app(state=state, memory=MagicMock())
            client = app.test_client()

            empty = client.get("/api/desktop/voice-cues").get_json()
            self.assertEqual(empty["voice"], "Kore")
            self.assertEqual(empty["source_voice"], "default")
            self.assertEqual(empty["clips"], [])
            self.assertTrue(Path(empty["directory"]).is_dir())

            clip = Path(empty["directory"]) / "yeah.wav"
            clip.write_bytes(b"RIFF-canned-yeah")
            loaded = client.get("/api/desktop/voice-cues").get_json()
            self.assertEqual(loaded["source_voice"], "Kore")
            self.assertIn("?v=", loaded["clips"][0]["url"])
            self.assertEqual(loaded["clips"][0]["name"], "yeah.wav")
            response = client.get(loaded["clips"][0]["url"])
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.data, b"RIFF-canned-yeah")
            response.close()

    def test_local_wake_stream_starts_feeds_and_stops(self):
        with tempfile.TemporaryDirectory() as directory:
            state = DesktopState(directory)
            state.update_voice_input({"mode": "wake_word", "wake_word": "Petey"})
            detector = MagicMock()
            detector.start.return_value = "wake-session"
            detector.feed.return_value = True
            app = create_desktop_app(
                state=state, memory=MagicMock(), wake_detector=detector
            )
            client = app.test_client()

            started = client.post("/api/desktop/voice-input/wake")
            detected = client.post(
                "/api/desktop/voice-input/wake/wake-session",
                data=b"\x00\x00" * 2048,
                headers={"X-Petey-Sample-Rate": "16000"},
            )
            stopped = client.delete("/api/desktop/voice-input/wake/wake-session")

            self.assertEqual(started.get_json()["session_id"], "wake-session")
            detector.start.assert_called_once_with("Petey")
            detector.feed.assert_called_once_with(
                "wake-session", b"\x00\x00" * 2048, 16000
            )
            self.assertTrue(detected.get_json()["detected"])
            self.assertTrue(stopped.get_json()["stopped"])
            detector.stop.assert_called_once_with("wake-session")

    def test_automatic_microphone_uses_deapi_then_falls_back_to_gemini(self):
        with tempfile.TemporaryDirectory() as directory:
            state = DesktopState(directory)
            state.update_voice_input({
                "mode": "push_to_talk", "provider": "automatic",
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

            state.update_voice_input({"provider": "deapi", "model": "WhisperLargeV3"})
            with patch(
                "web.desktop_app.DeapiSTT.transcribe",
                side_effect=DeapiSTTError("media transcription unavailable"),
            ), patch("web.desktop_app.GeminiSTT.transcribe") as gemini:
                response = client.post(
                    "/api/desktop/voice-input/transcribe",
                    data={"audio": (BytesIO(b"RIFF-audio"), "microphone.wav")},
                    content_type="multipart/form-data",
                )
            self.assertEqual(response.status_code, 502)
            self.assertIn("deAPI", response.get_json()["error"])
            gemini.assert_not_called()

    def test_local_whisper_status_and_microphone_transcription(self):
        with tempfile.TemporaryDirectory() as directory:
            state = DesktopState(directory)
            state.update_voice_input({
                "mode": "push_to_talk", "provider": "local_whisper",
                "local_whisper_model": "small", "local_whisper_device": "cpu",
            })
            client = create_desktop_app(state=state, runtime=object()).test_client()
            with patch("web.desktop_app.LocalWhisper") as whisper:
                whisper.return_value.status.return_value = {
                    "installed": True, "downloaded": True, "model": "small",
                    "model_directory": str(Path(directory) / "local-whisper-models"),
                }
                status = client.get(
                    "/api/desktop/voice-input/local-whisper?model=small"
                )
                whisper.return_value.download.return_value = {
                    "installed": True, "downloaded": True, "model": "medium",
                    "model_directory": str(Path(directory) / "local-whisper-models"),
                }
                downloaded = client.post(
                    "/api/desktop/voice-input/local-whisper",
                    json={"model": "medium", "device": "cpu"},
                )
                whisper.return_value.transcribe.return_value = "Private transcript"
                response = client.post(
                    "/api/desktop/voice-input/transcribe",
                    data={"audio": (BytesIO(b"RIFF-audio"), "microphone.wav")},
                    content_type="multipart/form-data",
                )

            self.assertTrue(status.get_json()["downloaded"])
            self.assertIn("faster-whisper", status.get_json()["install_command"])
            self.assertTrue(downloaded.get_json()["downloaded"])
            whisper.return_value.download.assert_called_once_with("medium", "cpu")
            self.assertEqual(state.voice_input["local_whisper_model"], "medium")
            self.assertEqual(response.get_json()["provider"], "local_whisper")
            self.assertEqual(response.get_json()["transcript"], "Private transcript")
            call = whisper.return_value.transcribe.call_args
            self.assertEqual(call.args[2:4], ("medium", "cpu"))

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

    def test_chat_speech_can_queue_deapi_voice(self):
        queued = {"id": "deapi-speech-job", "status": "queued", "kind": "audio"}
        with tempfile.TemporaryDirectory() as directory:
            state = DesktopState(directory)
            state.update_speech({
                "provider": "deapi",
                "deapi_model": "Qwen3_TTS_12Hz_1_7B_CustomVoice",
                "deapi_voice": "Serena",
            })
            jobs = MagicMock()
            jobs.submit.return_value = queued
            client = create_desktop_app(
                state=state, runtime=object(), job_manager=jobs,
            ).test_client()

            response = client.post("/api/desktop/chat/speech", json={"text": "Hello"})

            self.assertEqual(response.status_code, 202)
            call = jobs.submit.call_args.kwargs
            self.assertEqual(call["model_slug"], "Qwen3_TTS_12Hz_1_7B_CustomVoice")
            self.assertEqual(call["parameters"]["voice"], "Serena")
            self.assertEqual(call["speech_settings"]["provider"], "deapi")
            self.assertFalse(call["save_to_gallery"])

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
