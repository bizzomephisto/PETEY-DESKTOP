"""Fish Audio speech transport; credentials remain in local provider settings."""
from __future__ import annotations

import os
import re

import requests

from petey.http_client import SESSION as HTTP_SESSION

FISH_TTS_MODELS = ("s2.1-pro-free", "s2.1-pro", "s2-pro", "s1", "drama-3")
FISH_TTS_LATENCIES = ("normal", "balanced", "low")


# Namespaced internal markers distinguish speech directions from links, code and
# ordinary [bracketed text]. Only these markers may be hidden in the chat feed.
FISH_CUE = re.compile(r"\[\[fish:([A-Za-z][A-Za-z ,'-]{0,79})\]\]")


# Fish's documented S2 emotion, delivery, vocal-event and pause vocabulary.
# S2 also accepts concise natural-language directions; this is guidance, not an allowlist.
FISH_EMOTIONS = (
    "happy sad angry excited calm nervous confident surprised satisfied delighted "
    "scared worried upset frustrated depressed empathetic embarrassed disgusted moved "
    "proud relaxed grateful curious sarcastic disdainful unhappy anxious hysterical "
    "indifferent uncertain doubtful confused disappointed regretful guilty ashamed "
    "jealous envious hopeful optimistic pessimistic nostalgic lonely bored contemptuous "
    "sympathetic compassionate determined resigned"
)
FISH_DELIVERY = (
    "in a hurry tone; shouting; screaming; whispering; soft tone; emphasis"
)
FISH_VOCAL_EVENTS = (
    "laughing; chuckling; sobbing; crying loudly; sighing; groaning; panting; "
    "gasping; yawning; snoring; clear throat; break; long-break"
)
FISH_SPAN = re.compile(
    r"\[\[fish:<(/?)(whisper|emphasis|soft|fast|slow|stress|forceful)>\]\]"
)
S2_SPAN_DIRECTIONS = {
    "whisper": "whispering", "emphasis": "emphasis", "soft": "soft tone",
    "fast": "in a hurry tone", "slow": "slow delivery", "stress": "emphasis",
    "forceful": "forceful tone",
}


def fish_speech_text(text: str, enabled: bool = True, model: str = "s2.1-pro-free") -> str:
    source = str(text or "")
    # Only balanced namespaced spans become model controls. Never interpret HTML,
    # Markdown, or ordinary user brackets as private speech markup.
    stack = []
    paired = set()
    for match in FISH_SPAN.finditer(source):
        if not match[1]:
            stack.append(match)
        elif stack and stack[-1][2] == match[2]:
            paired.update((stack.pop().start(), match.start()))
    def span(match):
        if not enabled or match.start() not in paired:
            return ""
        if model in {"drama-3", "drama-3-preview"}:
            return f"<{match[1]}{match[2]}>"
        return "" if match[1] else f"[{S2_SPAN_DIRECTIONS[match[2]]}]"
    source = FISH_SPAN.sub(span, source)
    return FISH_CUE.sub(lambda m: f"[{m[1]}]" if enabled else "", source)


def fish_expression_prompt(prompt: str, speech: dict) -> str:
    model = str(speech.get("fish_model", "s2.1-pro-free"))
    drama = model in {"drama-3", "drama-3-preview"}
    if (speech.get("provider") != "fish" or not speech.get("fish_emotions", True)
            or not (model.startswith("s2") or drama)):
        return prompt + "\nDo not add internal [[fish:...]] speech markers to your response."
    directions = (
        "For Drama 3 only, limit delivery to selected words with balanced internal spans: "
        "[[fish:<emphasis>]]those words[[fish:</emphasis>]]. Supported paired names: "
        "whisper, emphasis, soft, fast, slow, stress, forceful. They become the matching "
        "Fish <tag>...</tag> controls. Keep spans short, balanced, and unnested. "
        "Example, only after a genuinely startling success and if the profile fits: "
        "[[fish:surprised]] Wait, [[fish:<emphasis>]]HOLY SHIT![[fish:</emphasis>]] "
        "It actually worked. Do not copy this reaction into unrelated replies."
        if drama else
        "For S2/S2.1, put [[fish:emphasis]] directly before the important word or phrase. "
        "Example when correcting a real requirement: You need [[fish:emphasis]]both "
        "files, [[fish:soft tone]]then we can continue. S2 uses [bracket] directions; "
        "do not generate paired <emphasis> tags or internal paired spans for S2. "
        "Exact word-scoped paired tags are documented for Drama 3, not S2.1."
    )
    return prompt + (
        "\nFISH AUDIO EXPRESSION: Your reply will be spoken by Fish Audio " + model + ". "
        "Use EXACTLY [[fish:cue words]] for internal directions, converted to [cue words] "
        "for speech and hidden from chat unless the user shows cues. "
        "Select emotions from the actual meaning of the current words, the user's situation, "
        "and the current profile. There is no tag quota and no one-cue-per-sentence limit. "
        "Use one coherent primary emotion when useful, combine compatible delivery cues, "
        "and place inline emphasis, vocal sounds, pauses, or a justified tone change "
        "at the exact point they apply, including within a sentence. Up to three combined "
        "cues is a guideline, not a requirement. Space changes naturally; neutral passages "
        "need no cues. Never alternate emotions merely for variety or tag every sentence. "
        "Use sympathy or calm support for distress, measured delivery for factual explanations, "
        "and excitement only for genuinely exciting content. Do not laugh at distress or "
        "pair contradictory emotions on the same words. Sarcasm must suit the relationship, "
        "intent and profile; profanity or shouting requires contextual justification. "
        "Do not add audience/background effects to ordinary conversation or invent user feelings. "
        "Preserve your profile. Never put internal cues in code, URLs, tool arguments, "
        "source quotations or factual data; do not explain or speak the markup. "
        "Documented emotion vocabulary: " + FISH_EMOTIONS + ". "
        "Delivery: " + FISH_DELIVERY + ". Vocal events and pauses: " + FISH_VOCAL_EVENTS + ". "
        "Concise natural-language modifiers are also supported, e.g. [[fish:slightly worried]]. "
        "Compatible layering example for sharing a secret: "
        "[[fish:curious]][[fish:whispering]] Did you hear that? " + directions
    )


class FishTTSError(RuntimeError):
    pass


def validate_voice_id(value: str) -> str:
    voice = str(value or "").strip()
    if voice and not re.fullmatch(r"[A-Za-z0-9_-]{1,200}", voice):
        raise ValueError("Enter a Fish Audio voice model ID, rather than a voice URL.")
    return voice


class FishTTS:
    def __init__(self, ai_config: dict):
        fish = dict((ai_config or {}).get("fish") or {})
        self.api_key = str(fish.get("api_key") or os.getenv("FISH_API_KEY", "")).strip()

    def generate(self, text: str, model: str = "s2.1-pro-free", voice: str = "", latency: str = "balanced") -> dict:
        model = "drama-3" if model == "drama-3-preview" else model
        if not self.api_key:
            raise FishTTSError("Fish Audio speech needs a key in Models & API keys or FISH_API_KEY.")
        transcript = str(text or "").strip()
        if not transcript or len(transcript) > 32000:
            raise FishTTSError("Enter between 1 and 32,000 characters for Fish Audio to speak.")
        if model not in FISH_TTS_MODELS:
            raise FishTTSError("Choose a supported Fish Audio TTS model.")
        try:
            voice = validate_voice_id(voice)
        except ValueError as exc:
            raise FishTTSError(str(exc)) from exc
        if not voice:
            raise FishTTSError("Enter a Fish Audio voice model ID in Personality & voice.")
        if latency not in FISH_TTS_LATENCIES:
            raise FishTTSError("Choose Normal, Balanced, or Low latency for Fish Audio.")
        try:
            response = HTTP_SESSION.post(
                "https://api.fish.audio/v1/tts",
                headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json", "model": model},
                json={"text": transcript, "reference_id": voice, "format": "mp3", "latency": latency},
                timeout=(20, 180),
            )
            response.raise_for_status()
        except requests.HTTPError as exc:
            status = exc.response.status_code if exc.response is not None else "unknown"
            raise FishTTSError(f"Fish Audio speech returned HTTP {status}. Check the API key, voice model access, and account credits.") from exc
        except requests.RequestException as exc:
            raise FishTTSError("Could not reach Fish Audio speech. Check the connection and try again.") from exc
        content_type = (response.headers.get("Content-Type") or "audio/mpeg").split(";", 1)[0].lower()
        if not response.content or content_type not in {"audio/mpeg", "audio/mp3", "application/octet-stream"}:
            raise FishTTSError("Fish Audio did not return MP3 audio.")
        return {"data": response.content, "content_type": "audio/mpeg", "result_url": ""}


    def stream_pcm(self, text: str, model: str = "s2.1-pro-free", voice: str = "",
                   latency: str = "balanced"):
        """Yield 24 kHz mono PCM16 as Fish generates it; close on disconnect."""
        model = "drama-3" if model == "drama-3-preview" else model
        if not self.api_key:
            raise FishTTSError("Fish Audio speech needs a key in Models & API keys or FISH_API_KEY.")
        text = str(text or "").strip()
        if not text or len(text) > 32000:
            raise FishTTSError("Enter between 1 and 32,000 characters for Fish Audio to speak.")
        try:
            voice = validate_voice_id(voice)
        except ValueError as exc:
            raise FishTTSError(str(exc)) from exc
        if not voice or model not in FISH_TTS_MODELS or latency not in FISH_TTS_LATENCIES:
            raise FishTTSError("Choose a supported Fish model, voice model ID, and latency.")
        response = None
        try:
            response = HTTP_SESSION.post(
                "https://api.fish.audio/v1/tts",
                headers={"Authorization": f"Bearer {self.api_key}",
                         "Content-Type": "application/json", "model": model},
                json={"text": text, "reference_id": voice, "format": "pcm",
                      "sample_rate": 24000, "latency": latency},
                stream=True, timeout=(20, 60),
            )
            response.raise_for_status()
            content_type = response.headers.get("Content-Type", "").split(";", 1)[0].lower()
            if content_type not in {"audio/pcm", "audio/pcm16", "audio/x-pcm",
                                    "application/octet-stream"}:
                raise FishTTSError("Fish Audio did not return PCM audio.")
            pending = b""
            total = 0
            for chunk in response.iter_content(chunk_size=4096):
                if not chunk:
                    continue
                total += len(chunk)
                if total > 64 * 1024 * 1024:
                    raise FishTTSError("Fish Audio speech exceeded the audio limit.")
                pending += chunk
                size = len(pending) - len(pending) % 2
                if size:
                    yield pending[:size]
                    pending = pending[size:]
            if pending:
                raise FishTTSError("Fish Audio returned incomplete PCM audio.")
            if not total:
                raise FishTTSError("Fish Audio finished without returning audio.")
        except requests.HTTPError as exc:
            status = exc.response.status_code if exc.response is not None else "unknown"
            raise FishTTSError(f"Fish Audio speech returned HTTP {status}. Check the key, voice access, and credits.") from exc
        except requests.RequestException as exc:
            raise FishTTSError("Fish Audio speech stream disconnected. Check the connection and try again.") from exc
        finally:
            if response is not None:
                response.close()
