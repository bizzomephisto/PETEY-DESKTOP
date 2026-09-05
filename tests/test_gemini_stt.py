import base64
import unittest
from unittest.mock import MagicMock, patch

from petey.gemini_stt import GeminiSTT, GeminiSTTError


class GeminiSTTTests(unittest.TestCase):
    def test_transcribes_inline_wav_and_biases_wake_name(self):
        response = MagicMock()
        response.raise_for_status.return_value = None
        response.json.return_value = {"steps": [{
            "type": "model_output",
            "content": [{"type": "text", "text": "Petey, what time is it?"}],
        }]}
        client = GeminiSTT({"gemini": {"api_key": "gemini-secret"}})

        with patch("petey.gemini_stt.HTTP_SESSION.post", return_value=response) as post:
            transcript = client.transcribe(
                b"RIFF-audio", "audio/wav", vocabulary=["Petey"]
            )

        self.assertEqual(transcript, "Petey, what time is it?")
        request = post.call_args.kwargs["json"]
        self.assertEqual(request["model"], "gemini-3.5-transcribe")
        self.assertEqual(request["input"][0]["mime_type"], "audio/wav")
        self.assertEqual(
            base64.b64decode(request["input"][0]["data"]), b"RIFF-audio"
        )
        self.assertEqual(
            request["generation_config"]["transcription_config"]["custom_vocabulary"],
            ["Petey"],
        )

    def test_rejects_missing_key_and_unknown_audio_type(self):
        with self.assertRaises(GeminiSTTError):
            GeminiSTT({}).transcribe(b"audio", "audio/wav")
        with self.assertRaises(GeminiSTTError):
            GeminiSTT({"gemini": {"api_key": "key"}}).transcribe(
                b"audio", "application/octet-stream"
            )


if __name__ == "__main__":
    unittest.main()
