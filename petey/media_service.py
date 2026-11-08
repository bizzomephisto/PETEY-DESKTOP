"""Transport-independent dispatcher for Petey's deAPI media operations."""

from __future__ import annotations

from dataclasses import dataclass

from petey.deapi_client import DEFAULT_MEDIA_PROMPT_LENGTH, H3_MODEL, deapi


OPERATIONS = {
    "txt2img": {"label": "Generate image", "kind": "image", "file": None},
    "img2img": {"label": "Edit / combine images", "kind": "image", "file": "images"},
    "txt2video": {"label": "Generate video", "kind": "video", "file": None},
    "img2video": {"label": "Animate image", "kind": "video", "file": "image"},
    "ref2vid": {"label": "Reference to video", "kind": "video", "file": "references"},
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
        inference_type = "img2video" if operation == "ref2vid" else operation
        models = await self.client.get_models(inference_type)
        if operation == "ref2vid":
            return [item for item in models if item.get("slug") == H3_MODEL]
        return models

    async def balance(self) -> float:
        return await self.client.get_balance()

    async def estimate(self, operation, model_slug="", parameters=None, prompt="", source=None):
        from petey.deapi_client import DeapiClient
        if operation not in DeapiClient.PRICE_ENDPOINTS:
            raise ValueError("Price lookup is unavailable for this operation.")
        parameters = parameters or {}
        if not isinstance(parameters, dict):
            raise ValueError("Media parameters must be an object.")
        values = {}
        if operation in {"txt2img", "img2img", "txt2video", "img2video", "ref2vid"}:
            values = {
                "width": self._integer(parameters, "width", 1024, 128, 2048),
                "height": self._integer(parameters, "height", 1024, 128, 2048),
                "steps": self._integer(parameters, "steps", 20, 1, 100),
                "guidance": self._number(parameters, "guidance", 3.5, 0, 30),
            }
        if operation in {"txt2img", "img2img"}:
            values = self._image_options(parameters)
        if operation in {"txt2video", "img2video", "ref2vid"}:
            values.update(frames=self._integer(parameters, "frames", 120, 1, 600),
                          fps=self._integer(parameters, "fps", 24, 1, 60))
        if operation == "ref2vid":
            values.update(
                ref_images_count=self._integer(parameters, "ref_images_count", 0, 0, 9),
                ref_videos_count=self._integer(parameters, "ref_videos_count", 0, 0, 1),
            )
        if operation in {"img-rmbg", "img-upscale"}:
            self._validate_source("image", source)
            if len(source.data) > 10 * 1024 * 1024:
                raise ValueError("Price lookup accepts source images up to 10 MB.")
            if operation == "img-upscale":
                values["scale"] = self._integer(parameters, "scale", 2, 2, 4)
        return await self.client.estimate_price(operation, model_slug, values, prompt, source)

    async def generate(
        self,
        operation: str,
        prompt: str,
        installation_id: str,
        model_slug: str = "",
        source: MediaInput | None = None,
        references: list[MediaInput] | None = None,
        parameters: dict | None = None,
    ) -> dict:
        config = self._require_operation(operation)
        parameters = parameters or {}
        references = list(references or [])
        self.validate_inputs(operation, source, references)
        if operation == "ref2vid":
            self._validate_references(references)
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

        if operation in {"txt2img", "img2img"}:
            visual = {**common, **self._image_options(parameters)}
        if operation == "txt2img":
            result = await self.client.generate_image(prompt, **visual)
        elif operation == "img2img":
            result = await self.client.generate_image_to_image(prompt, source.data if source else None, references=references, **visual)
        elif operation == "txt2video":
            result = await self.client.generate_video(prompt, **video)
        elif operation == "img2video":
            result = await self.client.generate_image_to_video(prompt, source.data, **video)
        elif operation == "ref2vid":
            result = await self.client.generate_reference_to_video(prompt, references, **video)
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
                prompt,
                voice=str(parameters.get("voice") or "Vivian"),
                speed=self._number(parameters, "speed", 1.0, 0.5, 2.0),
                style=str(parameters.get("style") or "").strip()[:DEFAULT_MEDIA_PROMPT_LENGTH],
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

    @classmethod
    def _image_options(cls, parameters):
        """Keep omitted values omitted so the model can supply its own defaults."""
        result = {}
        bounds = {"width": (1024, 128, 4096), "height": (1024, 128, 4096),
                  "steps": (20, 1, 100), "seed": (-1, -1, 2**32 - 1)}
        for name, (default, minimum, maximum) in bounds.items():
            if name in parameters:
                result[name] = cls._integer(parameters, name, default, minimum, maximum)
        if "guidance" in parameters:
            result["guidance"] = cls._number(parameters, "guidance", 3.5, 0, 30)
        for name in ("quality", "negative_prompt"):
            if name in parameters:
                result[name] = str(parameters[name])[:32000]
        return result

    @staticmethod
    def validate_inputs(operation, source, references):
        if operation != "img2img":
            MediaService._validate_source(OPERATIONS[operation]["file"], source)
            return
        if source and references:
            raise ValueError("Choose a source image or reference images, not both.")
        images = [source] if source else references
        if not images:
            raise ValueError("This operation requires a source image.")
        if len(images) > 16:
            raise ValueError("Image editing accepts at most 16 input images.")
        for image in images:
            MediaService._validate_source("image", image)
            if not image.data or len(image.data) > 10 * 1024 * 1024:
                raise ValueError("Each input image must be nonempty and at most 10 MB.")
            if image.content_type not in {"image/jpeg", "image/png", "image/gif", "image/bmp", "image/webp"}:
                raise ValueError("Use JPG, PNG, GIF, BMP, or WebP input images.")

    @staticmethod
    def _validate_source(requirement: str | None, source: MediaInput | None) -> None:
        if requirement == "references":
            return
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
    def _validate_references(references: list[MediaInput]) -> None:
        if not references:
            raise ValueError("Reference to video requires at least one image or video reference.")
        counts = {"image": 0, "video": 0, "audio": 0}
        limits = {"image": (9, 10 * 1024 * 1024), "video": (1, None), "audio": (3, 15 * 1024 * 1024)}
        if len(references) > 12:
            raise ValueError("Reference to video accepts at most 12 files.")
        for reference in references:
            kind = reference.content_type.split("/", 1)[0]
            if kind not in counts:
                raise ValueError(f"Unsupported reference file: {reference.filename}.")
            counts[kind] += 1
            maximum_count, maximum_size = limits[kind]
            if len(reference.data) < 1024:
                raise ValueError(f"Reference file {reference.filename} must be at least 1 KB.")
            if maximum_size is not None and len(reference.data) > maximum_size:
                raise ValueError(f"Reference file {reference.filename} exceeds the {maximum_size // (1024 * 1024)} MB limit.")
            if counts[kind] > maximum_count:
                noun = {"image": "images", "video": "video", "audio": "audio files"}[kind]
                raise ValueError(f"Reference to video accepts at most {maximum_count} {noun}.")
        if not counts["image"] and not counts["video"]:
            raise ValueError("Audio cannot be the only reference; add an image or video.")

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
