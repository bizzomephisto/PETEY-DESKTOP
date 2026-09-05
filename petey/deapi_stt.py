"""Low-cost deAPI Whisper transcription for desktop microphone clips."""

from __future__ import annotations

import os

import requests

from petey.gemini_stt import SUPPORTED_AUDIO_TYPES
from petey.http_client import SESSION as HTTP_SESSION


DEAPI_STT_MODELS = ("WhisperLargeV3",)


class DeapiSTTError(RuntimeError):
    pass


class DeapiSTT:
    def __init__(self):
        raw_key = str(os.getenv("DEAPI_KEY", "")).strip()
        self.api_key = raw_key if raw_key.startswith("dpn-sk-") else f"dpn-sk-{raw_key}"
        if not raw_key:
            self.api_key = ""

    def transcribe(
        self, audio: bytes, content_type: str,
        model: str = DEAPI_STT_MODELS[0], vocabulary: list[str] | None = None,
    ) -> str:
        if not self.api_key:
            raise DeapiSTTError("Microphone transcription needs DEAPI_KEY in the project .env file.")
        if not audio:
            raise DeapiSTTError("The microphone recording was empty.")
        model = str(model or DEAPI_STT_MODELS[0]).strip()
        if model not in DEAPI_STT_MODELS:
            raise DeapiSTTError("Choose a supported deAPI transcription model.")
        mime = str(content_type or "audio/wav").split(";", 1)[0].strip().lower()
        if mime not in SUPPORTED_AUDIO_TYPES:
            raise DeapiSTTError("This microphone audio format is not supported.")
        extension = {
            "audio/wav": ".wav", "audio/x-wav": ".wav", "audio/webm": ".webm",
            "audio/ogg": ".ogg", "audio/mpeg": ".mp3", "audio/mp3": ".mp3",
            "audio/mp4": ".m4a", "audio/m4a": ".m4a", "audio/aac": ".aac",
            "audio/flac": ".flac", "audio/opus": ".opus",
        }.get(mime, ".wav")
        try:
            response = HTTP_SESSION.post(
                "https://oai.deapi.ai/v1/audio/transcriptions",
                headers={"Authorization": f"Bearer {self.api_key}"},
                data={"model": model, "response_format": "json", "language": "en"},
                files={"file": (f"petey-microphone{extension}", audio, mime)},
                timeout=(20, 180),
            )
            response.raise_for_status()
            payload = response.json()
        except requests.HTTPError as exc:
            detail = self._error_detail(exc.response)
            raise DeapiSTTError(f"deAPI transcription returned an error: {detail}") from exc
        except requests.RequestException as exc:
            raise DeapiSTTError(f"Could not reach deAPI transcription: {exc}") from exc
        except (TypeError, ValueError) as exc:
            raise DeapiSTTError("deAPI returned an unreadable transcript.") from exc

        transcript = str(payload.get("text") or "").strip() if isinstance(payload, dict) else ""
        return transcript

    @staticmethod
    def _error_detail(response) -> str:
        if response is None:
            return "unknown HTTP error"
        try:
            payload = response.json()
            return str(payload.get("error", {}).get("message") or response.text)[:500]
        except (TypeError, ValueError):
            return str(response.text or f"HTTP {response.status_code}")[:500]
