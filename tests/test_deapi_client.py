import unittest
import os
from unittest.mock import AsyncMock, patch

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
        client = DeapiClient()
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


if __name__ == "__main__":
    unittest.main()
