import unittest
from unittest.mock import AsyncMock, patch

from petey.media_service import MediaInput, MediaService


class MediaServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_text_to_image_dispatches_selected_model_and_clamped_values(self):
        service = MediaService()
        with patch(
            "petey.media_service.deapi.generate_image",
            new=AsyncMock(return_value={"result_url": "https://media.example/image.png"}),
        ) as generate:
            result = await service.generate(
                "txt2img",
                "A small robot",
                "desktop-test",
                model_slug="flux-test",
                parameters={"width": 9999, "height": 64, "steps": "8"},
            )

        self.assertEqual(result["kind"], "image")
        self.assertEqual(result["result_url"], "https://media.example/image.png")
        kwargs = generate.await_args.kwargs
        self.assertEqual(kwargs["model_slug"], "flux-test")
        self.assertEqual(kwargs["width"], 4096)
        self.assertEqual(kwargs["height"], 128)
        self.assertEqual(kwargs["steps"], 8)

    async def test_image_operation_requires_image_input(self):
        service = MediaService()
        with self.assertRaisesRegex(ValueError, "source image"):
            await service.generate("img2img", "Restyle", "desktop-test")

        video = MediaInput("clip.mp4", "video/mp4", b"video")
        with self.assertRaisesRegex(ValueError, "must be an image"):
            await service.generate("img2img", "Restyle", "desktop-test", source=video)

    async def test_music_accepts_optional_reference_audio(self):
        service = MediaService()
        audio = MediaInput("reference.wav", "audio/wav", b"audio")
        with patch(
            "petey.media_service.deapi.generate_music",
            new=AsyncMock(return_value={"result_url": "https://media.example/song.mp3"}),
        ) as generate:
            result = await service.generate(
                "txt2music",
                "Synthwave",
                "desktop-test",
                source=audio,
                parameters={"lyrics": "Neon nights", "duration": 45},
            )

        self.assertEqual(result["kind"], "audio")
        self.assertEqual(generate.await_args.kwargs["reference_audio"], b"audio")
        self.assertEqual(generate.await_args.kwargs["duration"], 45)

    async def test_deapi_speech_sends_the_full_15000_character_script(self):
        client = AsyncMock()
        client.generate_speech.return_value = {"result_url": "https://media.example/speech.mp3"}
        script = "a" * 14_999 + "."

        await MediaService(client).generate("txt2audio", script, "desktop-test")

        self.assertEqual(client.generate_speech.await_args.args, (script,))

    async def test_minimax_h3_reference_video_dispatches_ordered_mixed_files(self):
        service = MediaService()
        references = [
            MediaInput("person.png", "image/png", b"i" * 1024),
            MediaInput("motion.mp4", "video/mp4", b"v" * 1024),
            MediaInput("voice.wav", "audio/wav", b"a" * 1024),
        ]
        with patch(
            "petey.media_service.deapi.generate_reference_to_video",
            new=AsyncMock(return_value={"result_url": "https://media.example/h3.mp4"}),
        ) as generate:
            result = await service.generate(
                "ref2vid", "<Picture 1> follows <Video 1>", "desktop-test",
                model_slug="MiniMaxH3_33B_Turbo_INT8", references=references,
            )

        self.assertEqual(result["kind"], "video")
        self.assertEqual(generate.await_args.args[1], references)
        self.assertEqual(generate.await_args.kwargs["model_slug"], "MiniMaxH3_33B_Turbo_INT8")

    async def test_reference_video_rejects_audio_only_and_excess_video(self):
        service = MediaService()
        with self.assertRaisesRegex(ValueError, "Audio cannot be the only"):
            await service.generate(
                "ref2vid", "Use the sound", "desktop-test",
                references=[MediaInput("voice.wav", "audio/wav", b"a" * 1024)],
            )
        with self.assertRaisesRegex(ValueError, "at most 1 video"):
            await service.generate(
                "ref2vid", "Use both", "desktop-test", references=[
                    MediaInput("one.mp4", "video/mp4", b"1" * 1024),
                    MediaInput("two.mp4", "video/mp4", b"2" * 1024),
                ],
            )

    async def test_reference_video_catalog_contains_only_minimax_h3(self):
        client = AsyncMock()
        client.get_models.return_value = [
            {"slug": "other-img2video"},
            {"slug": "MiniMaxH3_33B_Turbo_INT8"},
        ]
        models = await MediaService(client).models("ref2vid")
        client.get_models.assert_awaited_once_with("img2video")
        self.assertEqual([item["slug"] for item in models], ["MiniMaxH3_33B_Turbo_INT8"])


if __name__ == "__main__":
    unittest.main()
