"""Transport-independent dispatcher for Petey's deAPI media operations."""

from __future__ import annotations

from dataclasses import dataclass

from petey.deapi_client import deapi


OPERATIONS = {
    "txt2img": {"label": "Generate image", "kind": "image", "file": None},
    "img2img": {"label": "Restyle image", "kind": "image", "file": "image"},
    "txt2video": {"label": "Generate video", "kind": "video", "file": None},
    "img2video": {"label": "Animate image", "kind": "video", "file": "image"},
    "vid2video": {"label": "Restyle video", "kind": "video", "file": "video"},
    "txt2music": {"label": "Generate music", "kind": "audio", "file": "optional_audio"},
    "txt2audio": {"label": "Text to speech", "kind": "audio", "file": None},
    "img-rmbg": {"label": "Remove background", "kind": "image", "file": "image"},
    "img-upscale": {"label": "Upscale image", "kind": "image", "file": "image"},
}


@dataclass(frozen=True)
class MediaInput:
    filename: str
    content_type: str
    data: bytes


class MediaService:
    def __init__(self, client=None):
        self.client = client or deapi

    @staticmethod
    def operation_catalog() -> dict:
        return OPERATIONS

    async def models(self, operation: str) -> list[dict]:
        self._require_operation(operation)
        return await self.client.get_models(operation)

    async def balance(self) -> float:
        return await self.client.get_balance()

    async def generate(
        self,
        operation: str,
        prompt: str,
        installation_id: str,
        model_slug: str = "",
        source: MediaInput | None = None,
        parameters: dict | None = None,
    ) -> dict:
        config = self._require_operation(operation)
        parameters = parameters or {}
        self._validate_source(config["file"], source)
        prompt = (prompt or "").strip()
        if operation not in {"img-rmbg", "img-upscale"} and not prompt:
            raise ValueError("A prompt or text value is required.")

        common = {"guild_id": installation_id, "model_slug": model_slug or None}
        visual = {
            **common,
            "width": self._integer(parameters, "width", 1024, 128, 2048),
            "height": self._integer(parameters, "height", 1024, 128, 2048),
            "steps": self._integer(parameters, "steps", 20, 1, 100),
            "guidance": self._number(parameters, "guidance", 3.5, 0, 30),
        }
        video = {
            **visual,
            "frames": self._integer(parameters, "frames", 120, 1, 600),
            "fps": self._integer(parameters, "fps", 24, 1, 60),
        }

        if operation == "txt2img":
            result = await self.client.generate_image(prompt, **visual)
        elif operation == "img2img":
            result = await self.client.generate_image_to_image(prompt, source.data, **visual)
        elif operation == "txt2video":
            result = await self.client.generate_video(prompt, **video)
        elif operation == "img2video":
            result = await self.client.generate_image_to_video(prompt, source.data, **video)
        elif operation == "vid2video":
            result = await self.client.generate_video_to_video(prompt, source.data, **video)
        elif operation == "img-rmbg":
            result = await self.client.generate_remove_bg(source.data, **common)
        elif operation == "img-upscale":
            result = await self.client.generate_upscale(
                source.data,
                scale=self._integer(parameters, "scale", 2, 2, 4),
                **common,
            )
        elif operation == "txt2music":
            result = await self.client.generate_music(
                prompt,
                lyrics=(parameters.get("lyrics") or "[Instrumental]").strip(),
                duration=self._integer(parameters, "duration", 30, 5, 300),
                reference_audio=source.data if source else None,
                **common,
            )
        elif operation == "txt2audio":
            result = await self.client.generate_speech(
                prompt[:5000],
                voice=str(parameters.get("voice") or "Vivian"),
                speed=self._number(parameters, "speed", 1.0, 0.5, 2.0),
                style=str(parameters.get("style") or "").strip()[:2000],
                **common,
            )
        else:  # pragma: no cover - guarded by _require_operation
            raise ValueError("Unsupported media operation.")

        if not isinstance(result, dict):
            raise RuntimeError("The media provider returned an invalid generation result.")
        result_url = result.get("result_url") or result.get("url")
        if not result_url:
            raise RuntimeError("The media provider completed without returning a media URL.")
        return {"result_url": result_url, "kind": config["kind"], "operation": operation}

    @staticmethod
    def _require_operation(operation: str) -> dict:
        if operation not in OPERATIONS:
            raise ValueError("Unsupported media operation.")
        return OPERATIONS[operation]

    @staticmethod
    def _validate_source(requirement: str | None, source: MediaInput | None) -> None:
        if requirement in {"image", "video"} and source is None:
            raise ValueError(f"This operation requires a source {requirement}.")
        if source is None:
            return
        if requirement == "image" and not source.content_type.startswith("image/"):
            raise ValueError("The source file must be an image.")
        if requirement == "video" and not (
            source.content_type.startswith("video/")
            or source.filename.lower().endswith((".mp4", ".mov", ".webm", ".avi"))
        ):
            raise ValueError("The source file must be a video.")
        if requirement == "optional_audio" and not (
            source.content_type.startswith("audio/")
            or source.filename.lower().endswith((".mp3", ".wav", ".ogg", ".m4a", ".flac"))
        ):
            raise ValueError("The optional reference file must be audio.")

    @staticmethod
    def _integer(values: dict, key: str, default: int, minimum: int, maximum: int) -> int:
        try:
            value = int(values.get(key, default))
        except (TypeError, ValueError):
            value = default
        return max(minimum, min(maximum, value))

    @staticmethod
    def _number(values: dict, key: str, default: float, minimum: float, maximum: float) -> float:
        try:
            value = float(values.get(key, default))
        except (TypeError, ValueError):
            value = default
        return max(minimum, min(maximum, value))
