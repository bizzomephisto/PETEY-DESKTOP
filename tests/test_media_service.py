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
        self.assertEqual(kwargs["width"], 2048)
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


if __name__ == "__main__":
    unittest.main()
