"""OpenAI text-to-speech transport used as Petey's final speech fallback."""

from __future__ import annotations

import os

import requests

from petey.http_client import SESSION as HTTP_SESSION


OPENAI_TTS_MODELS = ("gpt-4o-mini-tts",)
OPENAI_TTS_VOICES = (
    "alloy", "ash", "ballad", "coral", "echo", "fable", "nova",
    "onyx", "sage", "shimmer", "verse", "marin", "cedar",
)


class OpenAITTSError(RuntimeError):
    pass


class OpenAITTS:
    def __init__(self, ai_config: dict):
        openai = dict((ai_config or {}).get("openai") or {})
        self.api_key = str(openai.get("api_key") or os.getenv("OPENAI_API_KEY", "")).strip()

    def generate(
        self, text: str, model: str = "gpt-4o-mini-tts",
        voice: str = "marin", style: str = "",
    ) -> dict:
        if not self.api_key:
            raise OpenAITTSError(
                "OpenAI speech needs an OpenAI API key in AI provider settings or OPENAI_API_KEY."
            )
        transcript = str(text or "").strip()
        if not transcript:
            raise OpenAITTSError("Enter text for OpenAI to speak.")
        model = str(model or OPENAI_TTS_MODELS[0]).strip()
        if model not in OPENAI_TTS_MODELS:
            raise OpenAITTSError("Choose a supported OpenAI TTS model.")
        voice = str(voice or "marin").strip().lower()
        if voice not in OPENAI_TTS_VOICES:
            raise OpenAITTSError("Choose a supported OpenAI voice.")

        payload = {
            "model": model,
            "voice": voice,
            "input": transcript,
            "response_format": "mp3",
        }
        directions = str(style or "").strip()[:2000]
        if directions:
            payload["instructions"] = directions
        try:
            response = HTTP_SESSION.post(
                "https://api.openai.com/v1/audio/speech",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
                timeout=(20, 180),
            )
            response.raise_for_status()
        except requests.HTTPError as exc:
            detail = self._error_detail(exc.response)
            raise OpenAITTSError(f"OpenAI speech returned an error: {detail}") from exc
        except requests.RequestException as exc:
            raise OpenAITTSError(f"Could not reach OpenAI speech: {exc}") from exc

        if not response.content:
            raise OpenAITTSError("OpenAI speech finished without returning audio.")
        return {
            "data": response.content,
            "content_type": (response.headers.get("Content-Type") or "audio/mpeg").split(";", 1)[0],
            "result_url": "",
        }

    @staticmethod
    def _error_detail(response) -> str:
        if response is None:
            return "unknown HTTP error"
        try:
            payload = response.json()
            return str(payload.get("error", {}).get("message") or response.text)[:500]
        except (TypeError, ValueError):
            return str(response.text or f"HTTP {response.status_code}")[:500]
