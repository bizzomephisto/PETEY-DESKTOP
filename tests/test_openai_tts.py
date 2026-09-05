import unittest
from unittest.mock import MagicMock, patch

from petey.openai_tts import OpenAITTS


class OpenAITTSTests(unittest.TestCase):
    def test_generates_mp3_with_voice_and_delivery_directions(self):
        response = MagicMock()
        response.content = b"openai-mp3"
        response.headers = {"Content-Type": "audio/mpeg"}
        response.raise_for_status.return_value = None
        client = OpenAITTS({"openai": {"api_key": "openai-secret"}})

        with patch("petey.openai_tts.HTTP_SESSION.post", return_value=response) as post:
            result = client.generate(
                "Hello", "gpt-4o-mini-tts", "marin", "Warm and relaxed"
            )

        self.assertEqual(result["data"], b"openai-mp3")
        self.assertEqual(result["content_type"], "audio/mpeg")
        request = post.call_args.kwargs
        self.assertEqual(request["json"]["voice"], "marin")
        self.assertEqual(request["json"]["instructions"], "Warm and relaxed")
        self.assertEqual(request["headers"]["Authorization"], "Bearer openai-secret")

    def test_requires_key_and_valid_voice(self):
        with patch.dict("os.environ", {}, clear=True):
            with self.assertRaisesRegex(Exception, "API key"):
                OpenAITTS({}).generate("Hello")
        with self.assertRaisesRegex(Exception, "supported OpenAI voice"):
            OpenAITTS({"openai": {"api_key": "key"}}).generate(
                "Hello", voice="not-a-voice"
            )


if __name__ == "__main__":
    unittest.main()
