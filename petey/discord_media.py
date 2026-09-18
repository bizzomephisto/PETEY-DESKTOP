"""Discord slash-command contracts for PETEY's desktop deAPI media queue."""

from __future__ import annotations


STRING = 3
INTEGER = 4
ATTACHMENT = 11


def _option(name, description, kind, *, required=False, minimum=None, maximum=None):
    option = {
        "name": name, "description": description, "type": kind,
        "required": required,
    }
    if minimum is not None:
        option["min_value"] = minimum
    if maximum is not None:
        option["max_value"] = maximum
    return option


PROMPT = _option("prompt", "Describe what PETEY should create", STRING, required=True)
IMAGE = _option("image", "Source image", ATTACHMENT, required=True)
VIDEO = _option("video", "Source video", ATTACHMENT, required=True)
WIDTH = _option("width", "Output width in pixels", INTEGER, minimum=128, maximum=2048)
HEIGHT = _option("height", "Output height in pixels", INTEGER, minimum=128, maximum=2048)


MEDIA_COMMANDS = {
    "genimg": {
        "description": "Generate an image with PETEY's desktop deAPI account",
        "operation": "txt2img", "options": [PROMPT, WIDTH, HEIGHT],
    },
    "img2img": {
        "description": "Restyle an image with PETEY's desktop deAPI account",
        "operation": "img2img", "options": [PROMPT, IMAGE, WIDTH, HEIGHT],
        "source": "image",
    },
    "genvid": {
        "description": "Generate a video with PETEY's desktop deAPI account",
        "operation": "txt2video", "options": [PROMPT, WIDTH, HEIGHT],
    },
    "img2vid": {
        "description": "Animate an image with PETEY's desktop deAPI account",
        "operation": "img2video", "options": [PROMPT, IMAGE, WIDTH, HEIGHT],
        "source": "image",
    },
    "vid2vid": {
        "description": "Restyle a video with PETEY's desktop deAPI account",
        "operation": "vid2video", "options": [PROMPT, VIDEO],
        "source": "video",
    },
    "genmusic": {
        "description": "Generate music with PETEY's desktop deAPI account",
        "operation": "txt2music",
        "options": [
            PROMPT,
            _option("lyrics", "Lyrics or [Instrumental]", STRING),
            _option("duration", "Duration in seconds", INTEGER, minimum=5, maximum=300),
        ],
    },
    "tts": {
        "description": "Generate speech with PETEY's desktop media settings",
        "operation": "txt2audio",
        "options": [_option("text", "Text PETEY should speak", STRING, required=True)],
    },
    "rmbg": {
        "description": "Remove an image background with PETEY's desktop deAPI account",
        "operation": "img-rmbg", "options": [IMAGE], "source": "image",
    },
    "upscale": {
        "description": "Upscale an image with PETEY's desktop deAPI account",
        "operation": "img-upscale",
        "options": [IMAGE, _option("scale", "Upscale factor", INTEGER, minimum=2, maximum=4)],
        "source": "image",
    },
}


def command_schemas() -> list[dict]:
    return [
        {
            "name": name, "description": command["description"], "type": 1,
            "options": command["options"],
        }
        for name, command in MEDIA_COMMANDS.items()
    ]


def parse_media_interaction(interaction: dict) -> dict | None:
    data = interaction.get("data") if isinstance(interaction, dict) else None
    if not isinstance(data, dict):
        return None
    name = str(data.get("name") or "").lower()
    command = MEDIA_COMMANDS.get(name)
    if command is None:
        return None
    values = {
        str(option.get("name") or ""): option.get("value")
        for option in data.get("options") or [] if isinstance(option, dict)
    }
    prompt = str(values.get("prompt") or values.get("text") or "").strip()
    parameters = {
        key: values[key] for key in (
            "width", "height", "steps", "guidance", "frames", "fps",
            "lyrics", "duration", "scale",
        ) if key in values
    }
    source_name = command.get("source")
    attachment_id = str(values.get(source_name) or "") if source_name else ""
    attachments = (data.get("resolved") or {}).get("attachments") or {}
    attachment = attachments.get(attachment_id) if attachment_id else None
    return {
        "command": name, "operation": command["operation"], "prompt": prompt,
        "parameters": parameters, "attachment": attachment,
        "source_kind": command.get("source", ""),
    }
