import unittest
from unittest.mock import MagicMock, patch

from petey.deapi_stt import DeapiSTT


class DeapiSTTTests(unittest.TestCase):
    def test_transcribes_microphone_audio_through_compatible_endpoint(self):
        response = MagicMock()
        response.raise_for_status.return_value = None
        response.json.return_value = {"text": "Hello Petey"}
        with patch.dict("os.environ", {"DEAPI_KEY": "account|secret"}, clear=True):
            client = DeapiSTT()

        with patch("petey.deapi_stt.HTTP_SESSION.post", return_value=response) as post:
            transcript = client.transcribe(b"RIFF-audio", "audio/x-wav")

        self.assertEqual(transcript, "Hello Petey")
        self.assertEqual(post.call_args.args[0], "https://oai.deapi.ai/v1/audio/transcriptions")
        self.assertEqual(
            post.call_args.kwargs["headers"]["Authorization"],
            "Bearer dpn-sk-account|secret",
        )
        self.assertEqual(post.call_args.kwargs["data"]["model"], "WhisperLargeV3")
        self.assertEqual(post.call_args.kwargs["files"]["file"][2], "audio/x-wav")

    def test_missing_key_is_rejected(self):
        with patch.dict("os.environ", {}, clear=True):
            client = DeapiSTT()
        with self.assertRaisesRegex(Exception, "DEAPI_KEY"):
            client.transcribe(b"RIFF-audio", "audio/wav")


if __name__ == "__main__":
    unittest.main()
