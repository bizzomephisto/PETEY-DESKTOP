"""deAPI media tools offered to Petey's language model."""

from __future__ import annotations

import os
import re

from petey.media_service import MediaInput, MediaService
from petey.tools.registry import ToolError, ToolSpec


_REQUEST_START = (
    r"^\s*(?:(?:hey[ ,]+)?petey[\s,:]+)?(?:please[ ,]+)?"
    r"(?:(?:can|could|would|will)\s+you\s+|(?:i want|i['’]d like|i would like)\s+(?:you\s+)?to\s+)?"
    r"(?:please\s+)?"
)
_IMAGE_SUBJECT = r"(?:images?|pictures?|photos?|art|illustrations?|wallpaper|portraits?|drawings?|sketch(?:es)?|collages?)"
_TEXT_TASK = (
    r"(?!(?:me\s+)?(?:(?:an?|the|some)\s+)?"
    r"(?:prompts?|captions?|descriptions?|instructions?|tutorials?|plans?|lists?|summar(?:y|ies))\b)"
)
_IMAGE_REQUEST = re.compile(
    _REQUEST_START
    + r"(?:(?:draw|illustrate)\s+(?!attention\b|(?:a\s+)?conclusions?\b)\S|"
    r"(?:generate|create|make|render|produce|design)\s+" + _TEXT_TASK
    + r"[^.!?\n]{0,64}\b" + _IMAGE_SUBJECT + r"\b)",
    re.IGNORECASE,
)
_EDIT_REQUEST = re.compile(
    _REQUEST_START
    + r"(?:(?:take|use)\s+[^.!?\n]{0,48}\b(?:images?|pictures?|photos?|these|them)\s+(?:and|to)\s+)?"
    r"(?:(?:edit|combine|merge|blend|composite|retouch|crop|recolor|restyle|upscale|sharpen|"
    r"brighten|darken)\s+\S|"
    r"(?:add|put|remove|replace|change|swap|turn|make|fix|give)\s+" + _TEXT_TASK
    + r"[^.!?\n]{0,100}\b(?:images?|pictures?|photos?|backgrounds?|hats?|outfits?|"
    r"colors?|colours?|lighting|collages?|them|both)\b)",
    re.IGNORECASE,
)


def explicit_image_request(message: str) -> bool:
    """Recognize direct requests that bypass the autonomous image allowance."""
    return bool(_IMAGE_REQUEST.search(str(message or "")))


def explicit_image_edit_request(message: str) -> bool:
    """Identify direct editing requests when the current turn has images."""
    return bool(_EDIT_REQUEST.search(str(message or "")) or explicit_image_request(message))


DEAPI_IMAGE_CONTROL = [{
    "id": "generate_image", "label": "Generate and edit images",
    "metered": True, "default_daily_limit": 5,
}]


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
    image_references: tuple[MediaInput, ...] = (),
) -> list[ToolSpec]:
    queued_job = None

    def control_available(explicit: bool) -> bool:
        try:
            state.authorize_petey_control(
                "deapi-media", "generate_image", surface,
                explicit=explicit,
                capabilities=DEAPI_IMAGE_CONTROL,
            )
            return True
        except ValueError:
            return False

    def authorize_control(explicit: bool) -> None:
        try:
            state.authorize_petey_control(
                "deapi-media", "generate_image", surface,
                explicit=explicit,
                capabilities=DEAPI_IMAGE_CONTROL,
                consume=queued_job is None,
            )
        except ValueError as exc:
            raise ToolError(str(exc)) from exc

    def queue_image(operation: str, prompt: str, parameters: dict) -> dict:
        nonlocal queued_job
        if queued_job is not None:
            return queued_job
        ai_config = state.ai_provider
        if not (ai_config.get("deapi", {}).get("api_key") or os.getenv("DEAPI_KEY", "").strip()):
            raise ToolError("Media generation is not configured. Add the media service key before generating images.")
        if not prompt:
            raise ToolError("An image prompt is required.")
        edit_options = {}
        if operation == "img2img":
            MediaService.validate_inputs(operation, None, image_references)
            edit_options = {
                "references": image_references,
                "select_compatible_edit_model": len(image_references) > 1,
            }
        job = media_jobs_getter().submit(
            operation=operation,
            prompt=prompt,
            installation_id=state.installation_id,
            model_slug=state.selected_model(operation),
            source=None,
            parameters=parameters,
            ai_config=ai_config,
            **edit_options,
        )
        queued_job = {
            "status": "queued",
            "job_id": job["id"],
            "operation": operation,
            "prompt": prompt,
            "message": (
                f"Image {'edit' if operation == 'img2img' else 'generation'} queued as {job['id'][:8]}. "
                "The result will appear in this chat and remain available in Gallery."
            ),
        }
        if record_memory:
            memory.record_image_generation(state.installation_id, state.person_id, prompt)
        return queued_job

    prompt_schema = {"type": "string", "description": "Describe the requested visual result."}
    if image_references:
        return [ToolSpec(
            name="edit_images",
            description=(
                f"Edit or combine the attached images ({len(image_references)} total), "
                "in their attachment order. PETEY supplies all original image files. "
                "Describe the requested changes and what should stay the same. Use first image, "
                "second image, and so on to distinguish references when needed. Queue one result."
            ),
            parameters={
                "type": "object", "properties": {"prompt": prompt_schema},
                "required": ["prompt"], "additionalProperties": False,
            },
            handler=lambda args: queue_image("img2img", str(args["prompt"]).strip(), {}),
            available_when=lambda message: explicit_image_edit_request(message) and control_available(True),
            required_when=lambda _message: True,
            authorize_when=lambda _message: authorize_control(True),
            explicit_when=explicit_image_edit_request,
            control_capability="generate_image",
        )]

    def generate_image(arguments: dict) -> dict:
        parameters = {}
        for key, default, minimum, maximum in (
            ("width", 1024, 128, 2048), ("height", 1024, 128, 2048), ("steps", 20, 1, 100),
        ):
            if key in arguments:
                parameters[key] = _integer(arguments, key, default, minimum, maximum)
        if "guidance" in arguments:
            parameters["guidance"] = _number(arguments, "guidance", 3.5, 0, 30)
        return queue_image("txt2img", str(arguments["prompt"]).strip(), parameters)

    return [
        ToolSpec(
            name="generate_image",
            description=(
                "Generate a new image through deAPI. An explicit user request always "
                "overrides Petey's autonomous daily allowance. When autonomous access is "
                "enabled and available, you may also create an image when it clearly adds "
                "value to the conversation. Never use it for inspection, advice, or prompts alone. "
                "Omit dimensions, steps and guidance unless needed so the model can use its defaults."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "prompt": prompt_schema,
                    "width": {"type": "integer", "minimum": 128, "maximum": 2048, "default": 1024},
                    "height": {"type": "integer", "minimum": 128, "maximum": 2048, "default": 1024},
                    "steps": {"type": "integer", "minimum": 1, "maximum": 100, "default": 20},
                    "guidance": {"type": "number", "minimum": 0, "maximum": 30, "default": 3.5},
                },
                "required": ["prompt"],
                "additionalProperties": False,
            },
            handler=generate_image,
            available_when=lambda message: control_available(explicit_image_request(message)),
            required_when=explicit_image_request,
            authorize_when=lambda message: authorize_control(explicit_image_request(message)),
            explicit_when=explicit_image_request,
            control_capability="generate_image",
            control_label=DEAPI_IMAGE_CONTROL[0]["label"],
            metered=True,
            default_daily_limit=5,
        )
    ]
