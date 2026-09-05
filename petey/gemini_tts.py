"""Google Gemini text-to-speech transport for the desktop media queue."""

from __future__ import annotations

import base64
import io
import json
import os
import wave

import requests

from petey.http_client import SESSION as HTTP_SESSION


GEMINI_TTS_MODELS = (
    "gemini-3.1-flash-tts-preview",
    "gemini-2.5-flash-preview-tts",
    "gemini-2.5-pro-preview-tts",
)

GEMINI_TTS_VOICES = {
    "Zephyr": "Bright", "Puck": "Upbeat", "Charon": "Informative",
    "Kore": "Firm", "Fenrir": "Excitable", "Leda": "Youthful",
    "Orus": "Firm", "Aoede": "Breezy", "Callirrhoe": "Easy-going",
    "Autonoe": "Bright", "Enceladus": "Breathy", "Iapetus": "Clear",
    "Umbriel": "Easy-going", "Algieba": "Smooth", "Despina": "Smooth",
    "Erinome": "Clear", "Algenib": "Gravelly", "Rasalgethi": "Informative",
    "Laomedeia": "Upbeat", "Achernar": "Soft", "Alnilam": "Firm",
    "Schedar": "Even", "Gacrux": "Mature", "Pulcherrima": "Forward",
    "Achird": "Friendly", "Zubenelgenubi": "Casual", "Vindemiatrix": "Gentle",
    "Sadachbia": "Lively", "Sadaltager": "Knowledgeable", "Sulafat": "Warm",
}


class GeminiTTSError(RuntimeError):
    pass


class GeminiTTS:
    def __init__(self, ai_config: dict):
        gemini = dict((ai_config or {}).get("gemini") or {})
        self.api_key = str(gemini.get("api_key") or os.getenv("GEMINI_API_KEY", "")).strip()

    def generate(
        self, text: str, model: str, voice: str, style: str = "",
        consistent_voice: bool = True,
    ) -> dict:
        model, voice, prompt = self._validated_request(
            text, model, voice, style, consistent_voice
        )
        try:
            response = HTTP_SESSION.post(
                f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
                headers={"Content-Type": "application/json", "x-goog-api-key": self.api_key},
                json={
                    "contents": [{"parts": [{"text": prompt}]}],
                    "generationConfig": {
                        "responseModalities": ["AUDIO"],
                        "speechConfig": {
                            "voiceConfig": {
                                "prebuiltVoiceConfig": {"voiceName": voice}
                            }
                        },
                    },
                },
                timeout=180,
            )
            response.raise_for_status()
            payload = response.json()
            inline = payload["candidates"][0]["content"]["parts"][0]["inlineData"]
            pcm = base64.b64decode(inline["data"], validate=True)
        except requests.HTTPError as exc:
            detail = exc.response.text[:500] if exc.response is not None else str(exc)
            raise GeminiTTSError(f"Gemini speech returned an error: {detail}") from exc
        except requests.RequestException as exc:
            raise GeminiTTSError(f"Could not reach Gemini speech: {exc}") from exc
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            raise GeminiTTSError("Gemini speech returned an unreadable audio response.") from exc

        output = io.BytesIO()
        with wave.open(output, "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(24000)
            wav.writeframes(pcm)
        return {
            "data": output.getvalue(),
            "content_type": "audio/wav",
            "result_url": "",
        }

    def stream_pcm(
        self, text: str, model: str, voice: str, style: str = "",
        consistent_voice: bool = True,
    ):
        """Yield 24 kHz mono PCM chunks from Gemini 3.1's streaming API."""
        model, voice, prompt = self._validated_request(
            text, model, voice, style, consistent_voice
        )
        if not model.startswith("gemini-3.1-"):
            raise GeminiTTSError("Streaming speech requires a Gemini 3.1 TTS model.")
        received_audio = False
        try:
            with HTTP_SESSION.post(
                "https://generativelanguage.googleapis.com/v1beta/interactions",
                headers={
                    "Content-Type": "application/json",
                    "x-goog-api-key": self.api_key,
                    "Api-Revision": "2026-05-20",
                },
                json={
                    "model": model,
                    "input": prompt,
                    "response_format": {"type": "audio"},
                    "generation_config": {"speech_config": [{"voice": voice}]},
                    "stream": True,
                },
                stream=True,
                timeout=(30, 180),
            ) as response:
                response.raise_for_status()
                for raw_line in response.iter_lines(decode_unicode=True):
                    if isinstance(raw_line, bytes):
                        line = raw_line.decode("utf-8", errors="replace").strip()
                    else:
                        line = str(raw_line or "").strip()
                    if not line.startswith("data:"):
                        continue
                    data = line[5:].strip()
                    if not data or data == "[DONE]":
                        continue
                    event = json.loads(data)
                    error = self._stream_error(event)
                    if error:
                        raise GeminiTTSError(f"Gemini streaming speech failed: {error}")
                    encoded = self._audio_data(event)
                    if encoded:
                        received_audio = True
                        yield base64.b64decode(encoded, validate=True)
            if not received_audio:
                raise GeminiTTSError("Gemini finished without returning audio.")
        except GeminiTTSError:
            raise
        except requests.HTTPError as exc:
            detail = exc.response.text[:500] if exc.response is not None else str(exc)
            raise GeminiTTSError(f"Gemini streaming speech returned an error: {detail}") from exc
        except requests.RequestException as exc:
            raise GeminiTTSError(f"Could not reach Gemini streaming speech: {exc}") from exc
        except (json.JSONDecodeError, TypeError, ValueError) as exc:
            raise GeminiTTSError("Gemini returned an unreadable speech stream.") from exc

    def _validated_request(
        self, text: str, model: str, voice: str, style: str,
        consistent_voice: bool = True,
    ):
        if not self.api_key:
            raise GeminiTTSError(
                "Gemini speech needs a Gemini API key in Settings or GEMINI_API_KEY."
            )
        model = str(model or GEMINI_TTS_MODELS[0]).strip()
        if model not in GEMINI_TTS_MODELS:
            raise GeminiTTSError("Choose a supported Gemini TTS model.")
        voice = str(voice or "Kore").strip()
        if voice not in GEMINI_TTS_VOICES:
            raise GeminiTTSError("Choose a supported Gemini voice.")
        transcript = str(text or "").strip()
        if not transcript:
            raise GeminiTTSError("Enter text for Gemini to speak.")
        directions = str(style or "").strip()[:2000]
        notes = []
        if consistent_voice:
            character = GEMINI_TTS_VOICES[voice]
            notes.append(
                f"VOICE IDENTITY: Always use the same {voice} speaker identity "
                f"({character}). Keep the perceived speaker, vocal age, accent, pitch "
                "range, vocal weight, resonance, and timbre consistent with previous "
                "responses. Do not adopt another speaker or character suggested by the "
                "transcript. Vary only the natural prosody needed to communicate it."
            )
        if directions:
            notes.append(directions)
        prompt = transcript
        if notes:
            prompt = f"# DIRECTOR'S NOTES\n{'\n\n'.join(notes)}\n\n# TRANSCRIPT\n{transcript}"
        return model, voice, prompt

    @classmethod
    def _audio_data(cls, value) -> str:
        if isinstance(value, dict):
            value_type = str(value.get("type") or "").lower()
            mime_type = str(value.get("mime_type") or value.get("mimeType") or "").lower()
            if (
                value_type in {"audio", "audio_delta", "output_audio"}
                or mime_type.startswith("audio/")
            ) and isinstance(value.get("data"), str):
                return value["data"]
            for key in ("output_audio", "outputAudio", "audio"):
                nested = value.get(key)
                if isinstance(nested, dict) and isinstance(nested.get("data"), str):
                    return nested["data"]
            for nested in value.values():
                found = cls._audio_data(nested)
                if found:
                    return found
        elif isinstance(value, list):
            for nested in value:
                found = cls._audio_data(nested)
                if found:
                    return found
        return ""

    @classmethod
    def _stream_error(cls, value) -> str:
        if not isinstance(value, dict):
            return ""
        event_type = str(value.get("event_type") or value.get("type") or "").lower()
        error = value.get("error")
        if isinstance(error, dict):
            return str(error.get("message") or error.get("code") or "unknown streaming error")[:500]
        if isinstance(error, str):
            return error[:500]
        interaction = value.get("interaction")
        if isinstance(interaction, dict) and (
            event_type.endswith((".failed", ".error"))
            or str(interaction.get("status") or "").lower() in {"failed", "error", "cancelled"}
        ):
            nested = interaction.get("error")
            if isinstance(nested, dict):
                return str(nested.get("message") or nested.get("code") or event_type)[:500]
            return str(nested or event_type or "interaction failed")[:500]
        return ""
