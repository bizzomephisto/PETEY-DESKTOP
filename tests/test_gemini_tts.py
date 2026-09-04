import base64
import io
import unittest
import wave
from unittest.mock import MagicMock, patch

from petey.gemini_tts import GeminiTTS


class GeminiTTSTests(unittest.TestCase):
    def test_streams_pcm_from_interactions_events(self):
        response = MagicMock()
        response.raise_for_status.return_value = None
        response.iter_lines.return_value = [
            b"event: step.delta",
            b'data: {"delta":{"type":"audio","data":"AQACAA=="}}',
            b"data: [DONE]",
        ]
        response.__enter__.return_value = response
        client = GeminiTTS({"gemini": {"api_key": "gemini-secret"}})

        with patch("petey.gemini_tts.requests.post", return_value=response) as post:
            chunks = list(client.stream_pcm(
                "Hello", "gemini-3.1-flash-tts-preview", "Kore"
            ))

        self.assertEqual(chunks, [b"\x01\x00\x02\x00"])
        self.assertTrue(post.call_args.kwargs["json"]["stream"])
        self.assertIn("/interactions", post.call_args.args[0])

    def test_generates_wave_audio_with_selected_model_voice_and_style(self):
        response = MagicMock()
        response.raise_for_status.return_value = None
        response.json.return_value = {
            "candidates": [{
                "content": {"parts": [{"inlineData": {
                    "mimeType": "audio/L16;codec=pcm;rate=24000",
                    "data": base64.b64encode(b"\x01\x00\x02\x00").decode("ascii"),
                }}]}
            }]
        }
        client = GeminiTTS({"gemini": {"api_key": "gemini-secret"}})

        with patch("petey.gemini_tts.requests.post", return_value=response) as post:
            result = client.generate(
                "Hello there", "gemini-3.1-flash-tts-preview", "Sulafat", "Warm and calm"
            )

        self.assertEqual(result["content_type"], "audio/wav")
        with wave.open(io.BytesIO(result["data"]), "rb") as audio:
            self.assertEqual(audio.getframerate(), 24000)
            self.assertEqual(audio.getnchannels(), 1)
            self.assertEqual(audio.readframes(2), b"\x01\x00\x02\x00")
        request = post.call_args.kwargs
        self.assertIn("gemini-3.1-flash-tts-preview", post.call_args.args[0])
        self.assertEqual(request["headers"]["x-goog-api-key"], "gemini-secret")
        self.assertIn("Warm and calm", request["json"]["contents"][0]["parts"][0]["text"])
        voice = request["json"]["generationConfig"]["speechConfig"]
        self.assertEqual(voice["voiceConfig"]["prebuiltVoiceConfig"]["voiceName"], "Sulafat")

    def test_consistency_mode_anchors_the_selected_voice(self):
        client = GeminiTTS({"gemini": {"api_key": "gemini-secret"}})

        _model, _voice, prompt = client._validated_request(
            "Hello there", "gemini-3.1-flash-tts-preview", "Kore", "Warm", True
        )
        self.assertIn("same Kore speaker identity", prompt)
        self.assertIn("timbre consistent", prompt)
        self.assertIn("Warm", prompt)

        _model, _voice, prompt = client._validated_request(
            "Hello there", "gemini-3.1-flash-tts-preview", "Kore", "Warm", False
        )
        self.assertNotIn("VOICE IDENTITY", prompt)


if __name__ == "__main__":
    unittest.main()
