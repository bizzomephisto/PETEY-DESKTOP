import unittest
import os
from unittest.mock import AsyncMock, MagicMock, patch

from petey.deapi_client import DeapiClient, DeapiError


class _FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        return False

    def raise_for_status(self):
        return None

    async def json(self):
        return self.payload


class _FakeSession:
    def __init__(self, pages):
        self.pages = pages
        self.calls = []

    def get(self, url, headers, params):
        self.calls.append((url, params))
        return _FakeResponse(self.pages[params["page"]])


class _PostResponse:
    status = 200
    headers = {}

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        return False

    async def json(self):
        return {"data": {"request_id": "request-7"}}


class _PostSession:
    def __init__(self):
        self.payloads = []

    def post(self, url, headers, json=None, data=None):
        self.payloads.append(json if json is not None else data)
        return _PostResponse()


class _BalanceSession:
    def __init__(self, balance):
        self.balance = balance
        self.calls = []

    def get(self, url, headers):
        self.calls.append((url, headers))
        return _FakeResponse({"data": {"balance": self.balance}})


class _StatusSession:
    def __init__(self, payloads):
        self.payloads = list(payloads)

    def get(self, url, headers):
        return _FakeResponse({"data": self.payloads.pop(0)})


class DeapiClientTests(unittest.IsolatedAsyncioTestCase):
    async def test_prompt_limits_are_checked_for_the_actual_model_before_submission(self):
        client = DeapiClient(api_key="test-key")
        session = _PostSession()
        client.get_session = AsyncMock(return_value=session)
        client.wait_for_job = AsyncMock()
        client.wait_for_v2_job = AsyncMock()
        client.get_models = AsyncMock(return_value=[{
            "slug": "ace-step", "info": {"limits": {"min_caption": 3, "max_caption": 300}},
        }, {
            "slug": "minimax-music", "info": {"limits": {"min_caption": 3, "max_caption": 2_000}},
        }])
        with self.assertRaisesRegex(ValueError, "at most 300 characters"):
            await client.generate_music("x" * 301, model_slug="ace-step")
        with self.assertRaisesRegex(ValueError, "at least 3 characters"):
            await client.generate_music("hi", model_slug="ace-step")
        self.assertEqual(session.payloads, [])
        await client.generate_music("x" * 301)
        form = session.payloads.pop()
        fields = {field["name"]: value for field, _, value in form._fields}
        self.assertEqual(fields["model"], "minimax-music")
        self.assertEqual(fields["caption"], "x" * 301)

        client.get_models.return_value = [{"slug": "Kokoro", "info": {"limits": {"max_text": 10_001}}}]
        with self.assertRaisesRegex(ValueError, "at most 10,001 characters"):
            await client.generate_speech("x" * 10_002, model_slug="Kokoro")
        client.get_models.return_value = [{"slug": "MiniMaxH3_33B_Turbo_INT8"}]
        with self.assertRaisesRegex(ValueError, "at most 7,000 characters"):
            await client.generate_video("x" * 7_001)
        client.get_models.return_value = [{"slug": "image-model"}]
        with self.assertRaisesRegex(ValueError, "at most 15,000 characters"):
            await client.generate_image("x" * 15_001)
        self.assertEqual(session.payloads, [])
        client.get_models.return_value[0]["info"] = {"limits": {"max_prompt": 20_000}}
        await client.generate_image("x" * 20_000)
        self.assertEqual(len(session.payloads[0]["prompt"]), 20_000)

    async def test_image_quote_uses_live_price_and_same_model_limits_as_generation(self):
        client = DeapiClient(api_key="test-key")
        info = {"limits": {"min_steps": 4, "max_steps": 4}, "defaults": {"steps": 4}}
        client.get_models = AsyncMock(return_value=[{"slug": "image-model", "info": info}])
        session = MagicMock()
        session.post.return_value = _FakeResponse({"data": {"price": "0.003", "is_estimated": False}})
        client.get_session = AsyncMock(return_value=session)
        params = {"width": 1024, "height": 768, "steps": 20, "guidance": 3.5}
        quote = await client.estimate_price("txt2img", "image-model", params, "Robot")
        self.assertEqual(quote["price"], 0.003)
        self.assertFalse(quote["is_estimated"])
        self.assertTrue(session.post.call_args.args[0].endswith("/images/generations/price"))
        quoted = session.post.call_args.kwargs["json"]
        self.assertEqual(quoted["steps"], 4)
        self.assertEqual(quoted["prompt"], "Robot")
        generated = {}

        async def capture(endpoint, build, operation, **kwargs):
            generated.update(build("image-model", info["defaults"], info))
            return "job"

        client._execute_with_fallback = AsyncMock(side_effect=capture)
        client.wait_for_job = AsyncMock(return_value={"result_url": "test"})
        await client.generate_image("Robot", model_slug="image-model", **params)
        for key in ("model", "width", "height", "steps", "guidance", "prompt"):
            self.assertEqual(quoted[key], generated[key])

    async def test_video_quote_uses_effective_frames_fps_and_auto_model(self):
        client = DeapiClient(api_key="test-key")
        client.get_models = AsyncMock(return_value=[{
            "slug": "video-model", "info": {"limits": {"max_frames": 120, "min_fps": 30, "max_steps": 1}},
        }])
        session = MagicMock()
        session.post.return_value = _FakeResponse({"data": {"price": 0.15}})
        client.get_session = AsyncMock(return_value=session)
        quote = await client.estimate_price("img2video", "", {"width": 512, "height": 512, "steps": 20, "frames": 240, "fps": 24})
        self.assertEqual(quote["model_slug"], "video-model")
        self.assertEqual(session.post.call_args.kwargs["json"], {"model": "video-model", "width": 512, "height": 512, "steps": 1, "frames": 120, "fps": 30})
        self.assertTrue(session.post.call_args.args[0].endswith("/videos/animations/price"))

    async def test_reference_video_quote_includes_reference_surcharges(self):
        client = DeapiClient(api_key="test-key")
        client.get_models = AsyncMock(return_value=[{
            "slug": "MiniMaxH3_33B_Turbo_INT8",
            "info": {"defaults": {"width": 1344, "height": 768, "frames": 124, "fps": 24}},
        }])
        session = MagicMock()
        session.post.return_value = _FakeResponse({"data": {"price": 0.42}})
        client.get_session = AsyncMock(return_value=session)
        await client.estimate_price(
            "ref2vid", "MiniMaxH3_33B_Turbo_INT8",
            {"ref_images_count": 3, "ref_videos_count": 1},
        )
        quoted = session.post.call_args.kwargs["json"]
        self.assertEqual(quoted["ref_images_count"], 3)
        self.assertEqual(quoted["ref_videos_count"], 1)

    async def test_quotes_reject_unsupported_operations_and_invalid_prices(self):
        client = DeapiClient(api_key="test-key")
        client.get_models = AsyncMock(return_value=[{"slug": "model"}])
        for operation in ("txt2audio", "txt2music", "vid2video", "unknown"):
            with self.assertRaises(ValueError):
                await client.estimate_price(operation, "model", {})
        client.get_models.assert_not_awaited()
        session = MagicMock()
        client.get_session = AsyncMock(return_value=session)
        for price in (None, -1, True, "NaN", "Infinity", "invalid"):
            session.post.return_value = _FakeResponse({"data": {"price": price}})
            with self.assertRaises(DeapiError):
                await client.estimate_price("txt2img", "model", {})

    async def test_upscale_quote_posts_source_only_to_price_endpoint(self):
        from petey.media_service import MediaInput
        client = DeapiClient(api_key="test-key")
        client.get_models = AsyncMock(return_value=[{"slug": "upscale"}])
        session = MagicMock()
        session.post.return_value = _FakeResponse({"data": {"price": 0.01}})
        client.get_session = AsyncMock(return_value=session)
        await client.estimate_price("img-upscale", "upscale", {"scale": 2}, source=MediaInput("test.png", "image/png", b"image"))
        self.assertTrue(session.post.call_args.args[0].endswith("/images/upscales/price"))
        self.assertIn("data", session.post.call_args.kwargs)
        self.assertNotIn("Content-Type", session.post.call_args.kwargs["headers"])

    async def test_missing_key_fails_with_configuration_message(self):
        with patch.dict(os.environ, {"DEAPI_KEY": ""}):
            client = DeapiClient()
        with self.assertRaisesRegex(DeapiError, "project .env"):
            await client.get_models("txt2img")

    async def test_get_models_fetches_every_catalog_page(self):
        pages = {
            1: {
                "data": [{"slug": "Ltxv_13B_0_9_8_Distilled_FP8"}],
                "meta": {"current_page": 1, "last_page": 2},
            },
            2: {
                "data": [{"slug": "MiniMaxH3_33B_Turbo_INT8"}],
                "meta": {"current_page": 2, "last_page": 2},
            },
        }
        session = _FakeSession(pages)
        client = DeapiClient(api_key="test-key")
        client.get_session = AsyncMock(return_value=session)

        models = await client.get_models("txt2video")

        self.assertEqual(
            [model["slug"] for model in models],
            ["Ltxv_13B_0_9_8_Distilled_FP8", "MiniMaxH3_33B_Turbo_INT8"],
        )
        self.assertEqual([call[1]["page"] for call in session.calls], [1, 2])
        self.assertTrue(
            all(call[1]["filter[inference_types]"] == "txt2video" for call in session.calls)
        )

    def test_minimax_h3_parameters_use_contract_and_fixed_steps(self):
        client = DeapiClient()
        info = {
            "limits": {
                "min_width": 1344,
                "max_width": 1344,
                "min_height": 768,
                "max_height": 768,
                "min_frames": 56,
                "max_frames": 243,
                "min_fps": 24,
                "max_fps": 24,
            },
            "defaults": {"width": 1344, "height": 768, "frames": 124, "fps": 24},
            "features": {"supports_steps": False, "supports_guidance": False},
        }

        params = client._video_parameters(
            "MiniMaxH3_33B_Turbo_INT8",
            info["defaults"],
            info,
            {"width": 512, "height": 512, "frames": 241, "fps": 30, "seed": 7},
        )

        self.assertEqual(
            params,
            {
                "width": 1344,
                "height": 768,
                "steps": 8,
                "frames": 241,
                "fps": 24,
                "seed": 7,
            },
        )

    def test_existing_ltx_parameters_follow_model_defaults_and_limits(self):
        client = DeapiClient()
        info = {
            "limits": {
                "min_width": 256,
                "max_width": 768,
                "min_height": 256,
                "max_height": 768,
                "min_steps": 1,
                "max_steps": 1,
                "min_frames": 30,
                "max_frames": 120,
                "min_fps": 30,
                "max_fps": 30,
            },
            "defaults": {"width": 512, "height": 512, "steps": 1, "frames": 120, "fps": 30},
            "features": {"supports_steps": True, "supports_guidance": False},
        }

        params = client._video_parameters(
            "Ltxv_13B_0_9_8_Distilled_FP8",
            info["defaults"],
            info,
            {"frames": 241, "fps": 24, "seed": 9},
        )

        self.assertEqual(params["steps"], 1)
        self.assertEqual(params["frames"], 120)
        self.assertEqual(params["fps"], 30)
        self.assertNotIn("guidance", params)

    def test_video_dimensions_observe_model_grid_and_pixel_cap(self):
        client = DeapiClient()
        info = {
            "limits": {
                "min_width": 512, "max_width": 1344,
                "min_height": 512, "max_height": 1344,
                "dimension_multiple": 32, "max_pixels": 1032192,
            },
            "defaults": {"width": 1344, "height": 768, "frames": 124, "fps": 24},
        }
        params = client._video_parameters(
            "MiniMaxH3_33B_Turbo_INT8", info["defaults"], info,
            {"width": 1024, "height": 1024},
        )
        self.assertEqual((params["width"], params["height"]), (992, 992))
        self.assertLessEqual(params["width"] * params["height"], 1032192)

    async def test_explicit_desktop_model_is_selected_without_guild_config(self):
        client = DeapiClient()
        session = _PostSession()
        client.get_models = AsyncMock(
            return_value=[
                {"slug": "first", "info": {"defaults": {}}},
                {"slug": "chosen", "info": {"defaults": {}}},
            ]
        )
        client.get_session = AsyncMock(return_value=session)

        request_id = await client._execute_with_fallback(
            "/generate",
            lambda model, defaults, info: {"model": model},
            "txt2img",
            selected_model_slug="chosen",
        )

        self.assertEqual(request_id, "request-7")
        self.assertEqual(session.payloads, [{"model": "chosen"}])

    async def test_get_balance_uses_authenticated_v2_account_endpoint(self):
        client = DeapiClient()
        client.api_key = "test-key"
        session = _BalanceSession("12.345")
        client.get_session = AsyncMock(return_value=session)

        balance = await client.get_balance()

        self.assertEqual(balance, 12.345)
        self.assertTrue(session.calls[0][0].endswith("/api/v2/account/balance"))
        self.assertEqual(session.calls[0][1]["Authorization"], "Bearer test-key")

    async def test_job_status_reports_real_progress_and_preview(self):
        updates = []
        client = DeapiClient(progress_callback=updates.append)
        client.get_session = AsyncMock(return_value=_StatusSession([
            {"status": "pending", "progress": "12.5"},
            {"status": "processing", "progress": 68, "preview": "https://media.example/preview.jpg"},
            {"status": "done", "progress": 100, "result_url": "https://media.example/final.png"},
        ]))
        with patch("petey.deapi_client.asyncio.sleep", new=AsyncMock()):
            result = await client.wait_for_job("request-42")

        self.assertEqual(result["status"], "done")
        self.assertEqual([item["progress"] for item in updates], ["12.5", 68, 100])
        self.assertEqual(updates[1]["preview_url"], "https://media.example/preview.jpg")
        self.assertTrue(all(item["request_id"] == "request-42" for item in updates))

    async def test_qwen_speech_uses_v2_endpoint_voice_and_emotion_instructions(self):
        client = DeapiClient()
        client._execute_with_fallback = AsyncMock(return_value="speech-42")
        client.wait_for_v2_job = AsyncMock(
            return_value={"status": "done", "result_url": "https://media.example/speech.mp3"}
        )

        result = await client.generate_speech(
            "That is fantastic!", voice="Dylan", style="Excited and celebratory"
        )

        request = client._execute_with_fallback.await_args
        self.assertEqual(request.args[0], "/api/v2/audio/speech")
        self.assertEqual(request.kwargs["selected_model_slug"], "Qwen3_TTS_12Hz_1_7B_CustomVoice")
        self.assertTrue(request.kwargs["strict_model"])
        form = request.args[1]("Qwen3_TTS_12Hz_1_7B_CustomVoice", {}, {})
        fields = {headers["name"]: value for headers, _headers, value in form._fields}
        self.assertEqual(fields["voice"], "Dylan")
        self.assertEqual(fields["lang"], "English")
        self.assertEqual(fields["instruct"], "Excited and celebratory")
        self.assertEqual(result["status"], "done")
        client.wait_for_v2_job.assert_awaited_once_with("speech-42")

    async def test_h3_reference_video_posts_indexed_v2_reference_fields(self):
        from petey.media_service import MediaInput
        client = DeapiClient(api_key="test-key")
        info = {
            "limits": {"max_ref_images": 9, "max_ref_videos": 1, "max_ref_audios": 3, "max_ref_files": 12},
            "defaults": {"width": 1344, "height": 768, "frames": 124, "fps": 24},
        }
        captured = {}

        async def execute(endpoint, builder, inference_type, **kwargs):
            captured.update(endpoint=endpoint, inference_type=inference_type, kwargs=kwargs)
            captured["form"] = builder("MiniMaxH3_33B_Turbo_INT8", info["defaults"], info)
            return "h3-job"

        client._execute_with_fallback = AsyncMock(side_effect=execute)
        client.wait_for_v2_job = AsyncMock(return_value={"result_url": "https://media.example/h3.mp4"})
        references = [
            MediaInput("face.png", "image/png", b"i" * 1024),
            MediaInput("pose.jpg", "image/jpeg", b"j" * 1024),
            MediaInput("move.mp4", "video/mp4", b"v" * 1024),
            MediaInput("voice.wav", "audio/wav", b"a" * 1024),
        ]

        await client.generate_reference_to_video("Combine them", references)

        self.assertEqual(captured["endpoint"], "/api/v2/videos/animations")
        self.assertEqual(captured["inference_type"], "img2video")
        self.assertTrue(captured["kwargs"]["strict_model"])
        names = [headers["name"] for headers, _headers, _value in captured["form"]._fields]
        self.assertIn("ref_images[0]", names)
        self.assertIn("ref_images[1]", names)
        self.assertIn("ref_videos[0]", names)
        self.assertIn("ref_audios[0]", names)
        client.wait_for_v2_job.assert_awaited_once_with("h3-job", timeout=900)

    async def test_image_to_image_payload_does_not_depend_on_reference_inputs(self):
        client = DeapiClient(api_key="test-key")
        captured = {}

        async def execute(_endpoint, builder, _inference_type, **_kwargs):
            captured["form"] = builder("image-model", {}, {})
            return "image-job"

        client._execute_with_fallback = AsyncMock(side_effect=execute)
        client.wait_for_v2_job = AsyncMock(return_value={"result_url": "https://media.example/image.png"})
        await client.generate_image_to_image("Restyle", b"image")
        names = [headers["name"] for headers, _headers, _value in captured["form"]._fields]
        self.assertIn("image", names)


if __name__ == "__main__":
    unittest.main()
