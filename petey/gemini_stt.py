"""Gemini speech-to-text transport for short desktop microphone utterances."""

from __future__ import annotations

import base64
import os

import requests

from petey.http_client import SESSION as HTTP_SESSION


GEMINI_STT_MODELS = ("gemini-3.5-transcribe",)
SUPPORTED_AUDIO_TYPES = {
    "audio/wav", "audio/x-wav", "audio/webm", "audio/ogg", "audio/mpeg", "audio/mp3",
    "audio/mp4", "audio/m4a", "audio/aac", "audio/flac", "audio/opus",
}


class GeminiSTTError(RuntimeError):
    pass


class GeminiSTT:
    def __init__(self, ai_config: dict):
        gemini = dict((ai_config or {}).get("gemini") or {})
        self.api_key = str(gemini.get("api_key") or os.getenv("GEMINI_API_KEY", "")).strip()

    def transcribe(
        self, audio: bytes, content_type: str, model: str = GEMINI_STT_MODELS[0],
        vocabulary: list[str] | None = None,
    ) -> str:
        if not self.api_key:
            raise GeminiSTTError(
                "Microphone transcription needs a Gemini API key in Settings or GEMINI_API_KEY."
            )
        if not audio:
            raise GeminiSTTError("The microphone recording was empty.")
        model = str(model or GEMINI_STT_MODELS[0]).strip()
        if model not in GEMINI_STT_MODELS:
            raise GeminiSTTError("Choose a supported Gemini transcription model.")
        mime = str(content_type or "audio/wav").split(";", 1)[0].strip().lower()
        if mime not in SUPPORTED_AUDIO_TYPES:
            raise GeminiSTTError("This microphone audio format is not supported.")
        words = [str(word).strip()[:100] for word in (vocabulary or []) if str(word).strip()]
        try:
            response = HTTP_SESSION.post(
                "https://generativelanguage.googleapis.com/v1beta/interactions",
                headers={
                    "Content-Type": "application/json",
                    "x-goog-api-key": self.api_key,
                    "Api-Revision": "2026-05-20",
                },
                json={
                    "model": model,
                    "input": [{
                        "type": "audio",
                        "data": base64.b64encode(audio).decode("ascii"),
                        "mime_type": mime,
                    }],
                    "generation_config": {
                        "transcription_config": {
                            "language_codes": [],
                            "mode": "smart",
                            "custom_vocabulary": words[:100],
                        }
                    },
                },
                timeout=(30, 120),
            )
            response.raise_for_status()
            transcript = self._output_text(response.json()).strip()
        except requests.HTTPError as exc:
            detail = exc.response.text[:500] if exc.response is not None else str(exc)
            raise GeminiSTTError(f"Gemini transcription returned an error: {detail}") from exc
        except requests.RequestException as exc:
            raise GeminiSTTError(f"Could not reach Gemini transcription: {exc}") from exc
        except (TypeError, ValueError) as exc:
            raise GeminiSTTError("Gemini returned an unreadable transcript.") from exc
        if not transcript:
            raise GeminiSTTError("No speech was detected.")
        return transcript

    @classmethod
    def _output_text(cls, value) -> str:
        if isinstance(value, dict):
            direct = value.get("output_text")
            if isinstance(direct, str):
                return direct
            if value.get("type") in {"text", "output_text"} and isinstance(value.get("text"), str):
                return value["text"]
            for key in (
                "steps", "outputs", "output", "content", "parts", "candidates", "response"
            ):
                if key in value:
                    found = cls._output_text(value[key])
                    if found:
                        return found
        elif isinstance(value, list):
            texts = [cls._output_text(item) for item in value]
            return " ".join(text for text in texts if text)
        return ""
