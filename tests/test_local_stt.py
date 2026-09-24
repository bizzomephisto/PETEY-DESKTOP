import unittest
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from petey.local_whisper import LocalWhisper, LocalWhisperError


class LocalWhisperTests(unittest.TestCase):
    def test_local_whisper_requires_explicit_model_download(self):
        with tempfile.TemporaryDirectory() as directory:
            engine = LocalWhisper(directory)
            with self.assertRaisesRegex(LocalWhisperError, "Download the small"):
                engine.transcribe(b"RIFF-audio", "audio/wav", "small")

    def test_local_whisper_download_and_transcription_use_private_model_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            engine = LocalWhisper(directory)
            model = MagicMock()
            model.transcribe.return_value = (
                iter([SimpleNamespace(text=" Hello"), SimpleNamespace(text=" shed ")]),
                MagicMock(),
            )
            with patch.object(engine, "_model", return_value=model) as load:
                status = engine.download("small", "cpu")
                transcript = engine.transcribe(
                    b"RIFF-audio", "audio/wav", "small", "cpu",
                    vocabulary=["Petey", "Bizzo"],
                )

            self.assertTrue(status["downloaded"])
            self.assertEqual(transcript, "Hello shed")
            self.assertEqual(load.call_args_list[0].kwargs["allow_download"], True)
            self.assertEqual(load.call_args_list[1].kwargs["allow_download"], False)
            self.assertTrue((Path(directory) / "local-whisper-models" / "small.ready").is_file())
            self.assertIn("Petey", model.transcribe.call_args.kwargs["initial_prompt"])


if __name__ == "__main__":
    unittest.main()
