"""deAPI media tools offered to Petey's language model."""

from __future__ import annotations

import os
import re

from petey.tools.registry import ToolError, ToolSpec


_IMAGE_REQUEST = re.compile(
    r"(?:\b(?:generate|create|make|draw|render|produce|design)\b.{0,80}\b(?:image|picture|photo|art|illustration|wallpaper|portrait)\b)"
    r"|(?:\b(?:image|picture|photo|art|illustration|wallpaper|portrait)\b.{0,80}\b(?:generate|create|make|draw|render|produce|design)\b)"
    r"|(?:\b(?:show|give)\s+me\b.{0,80}\b(?:image|picture|photo|illustration|portrait)\b)",
    re.IGNORECASE | re.DOTALL,
)


def explicit_image_request(message: str) -> bool:
    """Paid generation is available only after an explicit image request."""
    return bool(_IMAGE_REQUEST.search(str(message or "")))


def _integer(arguments: dict, key: str, default: int, minimum: int, maximum: int) -> int:
    try:
        value = int(arguments.get(key, default))
    except (TypeError, ValueError):
        value = default
    return max(minimum, min(maximum, value))


def _number(arguments: dict, key: str, default: float, minimum: float, maximum: float) -> float:
    try:
        value = float(arguments.get(key, default))
    except (TypeError, ValueError):
        value = default
    return max(minimum, min(maximum, value))


def build_media_tools(
    state, media_jobs_getter, memory, record_memory: bool = True,
    surface: str = "petey_desktop",
) -> list[ToolSpec]:
    capability_definitions = [{
        "id": "generate_image", "label": "Generate images",
        "metered": True, "default_daily_limit": 5,
    }]

    def control_available(message: str) -> bool:
        try:
            state.authorize_petey_control(
                "deapi-media", "generate_image", surface,
                explicit=explicit_image_request(message),
                capabilities=capability_definitions,
            )
            return True
        except ValueError:
            return False

    def authorize_control(message: str) -> None:
        try:
            state.authorize_petey_control(
                "deapi-media", "generate_image", surface,
                explicit=explicit_image_request(message),
                capabilities=capability_definitions,
                consume=True,
            )
        except ValueError as exc:
            raise ToolError(str(exc)) from exc

    def generate_image(arguments: dict) -> dict:
        if not (state.ai_provider.get("deapi", {}).get("api_key") or os.getenv("DEAPI_KEY", "").strip()):
            raise ToolError("Media generation is not configured. Add the media service key before generating images.")
        prompt = str(arguments.get("prompt") or "").strip()[:2000]
        if not prompt:
            raise ToolError("An image prompt is required.")
        parameters = {
            "width": _integer(arguments, "width", 1024, 128, 2048),
            "height": _integer(arguments, "height", 1024, 128, 2048),
            "steps": _integer(arguments, "steps", 20, 1, 100),
            "guidance": _number(arguments, "guidance", 3.5, 0, 30),
        }
        job = media_jobs_getter().submit(
            operation="txt2img",
            prompt=prompt,
            installation_id=state.installation_id,
            model_slug=state.selected_model("txt2img"),
            source=None,
            parameters=parameters,
            ai_config=state.ai_provider,
        )
        if record_memory:
            memory.record_image_generation(state.installation_id, state.person_id, prompt)
        return {
            "status": "queued",
            "job_id": job["id"],
            "prompt": prompt,
            "message": (
                f"Image generation queued as {job['id'][:8]}. "
                "The result will appear in this chat and remain available in Gallery."
            ),
        }

    return [
        ToolSpec(
            name="generate_image",
            description=(
                "Generate a new image through deAPI. An explicit user request always "
                "overrides Petey's autonomous daily allowance. When autonomous access is "
                "enabled and available, you may also create an image when it clearly adds "
                "value to the conversation; use that allowance thoughtfully."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "prompt": {
                        "type": "string",
                        "description": "A detailed visual prompt describing the requested image.",
                    },
                    "width": {"type": "integer", "minimum": 128, "maximum": 2048, "default": 1024},
                    "height": {"type": "integer", "minimum": 128, "maximum": 2048, "default": 1024},
                    "steps": {"type": "integer", "minimum": 1, "maximum": 100, "default": 20},
                    "guidance": {"type": "number", "minimum": 0, "maximum": 30, "default": 3.5},
                },
                "required": ["prompt"],
                "additionalProperties": False,
            },
            handler=generate_image,
            available_when=control_available,
            authorize_when=authorize_control,
            explicit_when=explicit_image_request,
            control_capability="generate_image",
            control_label="Generate images",
            metered=True,
            default_daily_limit=5,
        )
    ]
