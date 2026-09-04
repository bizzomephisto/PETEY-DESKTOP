import asyncio
import tempfile
import threading
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from petey.media_jobs import MediaGallery, MediaJobManager


class _FakeContent:
    async def iter_chunked(self, _size):
        yield b"generated-"
        yield b"media"


class _FakeResponse:
    headers = {"Content-Type": "image/png"}
    content = _FakeContent()

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        return False

    def raise_for_status(self):
        return None


class _FakeSession:
    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        return False

    def get(self, _url):
        return _FakeResponse()


class MediaGalleryTests(unittest.TestCase):
    def test_capture_writes_inline_gemini_audio(self):
        with tempfile.TemporaryDirectory() as directory:
            gallery = MediaGallery(directory)
            result = {
                "result_url": "", "data": b"RIFF-audio", "content_type": "audio/wav",
                "kind": "audio", "operation": "txt2audio",
            }
            item = asyncio.run(gallery.capture("speech-1", result, "Hello", "gemini-tts"))

            self.assertEqual(item["local_filename"], "speech-1.wav")
            self.assertEqual((Path(directory) / "speech-1.wav").read_bytes(), b"RIFF-audio")

    def test_capture_persists_file_index_and_delete(self):
        with tempfile.TemporaryDirectory() as directory:
            gallery = MediaGallery(directory)
            result = {
                "result_url": "https://media.example/image.png",
                "kind": "image",
                "operation": "txt2img",
            }
            with patch("petey.media_jobs.aiohttp.ClientSession", _FakeSession):
                item = asyncio.run(gallery.capture("item-1", result, "A robot", "flux"))

            self.assertEqual(item["local_filename"], "item-1.png")
            self.assertEqual((Path(directory) / "item-1.png").read_bytes(), b"generated-media")
            self.assertEqual(MediaGallery(directory).get("item-1")["prompt"], "A robot")
            self.assertTrue(gallery.delete("item-1"))
            self.assertFalse((Path(directory) / "item-1.png").exists())
            self.assertEqual(gallery.list_items(), [])

    def test_video_preview_is_cached_as_webm_and_removed_with_original(self):
        with tempfile.TemporaryDirectory() as directory:
            gallery = MediaGallery(directory)
            source = Path(directory) / "video-1.mp4"
            source.write_bytes(b"original-video")
            gallery._items = [{
                "id": "video-1",
                "created_at": "2026-01-01T00:00:00+00:00",
                "operation": "txt2video",
                "kind": "video",
                "prompt": "A robot",
                "model_slug": "video-model",
                "remote_url": "https://media.example/video.mp4",
                "local_filename": source.name,
                "content_type": "video/mp4",
                "download_error": "",
            }]

            def fake_run(command, **_kwargs):
                Path(command[-1]).write_bytes(b"webm-preview")
                return SimpleNamespace(returncode=0)

            with patch("petey.media_jobs.subprocess.run", side_effect=fake_run) as run:
                preview = gallery.video_preview_path("video-1")
                cached = gallery.video_preview_path("video-1")

            self.assertEqual(preview, cached)
            self.assertEqual(preview.read_bytes(), b"webm-preview")
            self.assertEqual(run.call_count, 1)
            self.assertIn("libvpx", run.call_args.args[0])
            self.assertTrue(gallery.delete("video-1"))
            self.assertFalse(source.exists())
            self.assertFalse(preview.exists())


class MediaJobManagerTests(unittest.TestCase):
    def test_gemini_speech_runs_through_queue_and_gallery(self):
        generated = {
            "result_url": "", "data": b"RIFF-gemini", "content_type": "audio/wav",
        }
        with tempfile.TemporaryDirectory() as directory:
            gallery = MediaGallery(directory)
            with patch("petey.media_jobs.GeminiTTS.generate", return_value=generated) as generate:
                manager = MediaJobManager(gallery, max_workers=2)
                queued = manager.submit(
                    "txt2audio", "Hello", "desktop-test", "gemini-3.1-flash-tts-preview",
                    None, {"voice": "Kore", "style": "Friendly"},
                    speech_settings={"provider": "gemini"},
                    ai_config={"gemini": {"api_key": "secret"}},
                )
                deadline = time.time() + 3
                while time.time() < deadline and manager.get(queued["id"])["status"] != "completed":
                    time.sleep(0.02)
                job = manager.get(queued["id"])
                manager.close()

            self.assertEqual(job["status"], "completed")
            self.assertNotIn("data", job["result"])
            self.assertEqual(job["result"]["gallery_item"]["local_filename"].split(".")[-1], "wav")
            generate.assert_called_once()
            self.assertTrue(generate.call_args.args[4])

    def test_disabled_speech_is_rejected_before_queueing(self):
        with tempfile.TemporaryDirectory() as directory:
            manager = MediaJobManager(MediaGallery(directory), max_workers=2)
            with self.assertRaisesRegex(ValueError, "disabled"):
                manager.submit(
                    "txt2audio", "Hello", "desktop-test", "", None, {},
                    speech_settings={"provider": "disabled"},
                )
            manager.close()
    def test_provider_progress_is_normalized_and_exposed(self):
        with tempfile.TemporaryDirectory() as directory:
            manager = MediaJobManager(MediaGallery(directory), max_workers=2)
            with manager._lock:
                manager._jobs["job-1"] = {
                    "id": "job-1", "status": "running", "provider_status": "submitting",
                    "progress": None, "preview_url": "", "request_id": "",
                }
            manager._update_progress("job-1", {
                "request_id": "deapi-7", "status": "processing", "progress": 123.456,
                "preview_url": "https://media.example/preview.jpg",
            })
            job = manager.get("job-1")
            manager.close()

            self.assertEqual(job["progress"], 100.0)
            self.assertEqual(job["provider_status"], "processing")
            self.assertEqual(job["request_id"], "deapi-7")
            self.assertEqual(job["preview_url"], "https://media.example/preview.jpg")

    def test_multiple_jobs_run_concurrently(self):
        active = 0
        maximum_active = 0
        lock = threading.Lock()

        async def fake_execute(_manager, job):
            nonlocal active, maximum_active
            with lock:
                active += 1
                maximum_active = max(maximum_active, active)
            await asyncio.sleep(0.08)
            with lock:
                active -= 1
            result = {
                "result_url": f"https://media.example/{job['id']}.png",
                "kind": "image",
                "operation": job["operation"],
            }
            return result, {"id": job["id"], "local_filename": f"{job['id']}.png"}

        with tempfile.TemporaryDirectory() as directory:
            gallery = MediaGallery(directory)
            with patch.object(MediaJobManager, "_execute", new=fake_execute):
                manager = MediaJobManager(gallery, max_workers=3)
                jobs = [
                    manager.submit("txt2img", f"Robot {index}", "desktop-test", "", None, {})
                    for index in range(3)
                ]
                deadline = time.time() + 3
                while time.time() < deadline:
                    states = [manager.get(job["id"])["status"] for job in jobs]
                    if all(state == "completed" for state in states):
                        break
                    time.sleep(0.02)
                manager.close()

            self.assertTrue(all(manager.get(job["id"])["status"] == "completed" for job in jobs))
            self.assertGreaterEqual(maximum_active, 2)


if __name__ == "__main__":
    unittest.main()
