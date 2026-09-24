"""Local, user-replaceable acknowledgement clips for wake-name mode."""

from __future__ import annotations

import re
from pathlib import Path

from petey.gemini_tts import GEMINI_TTS_VOICES


SUPPORTED_EXTENSIONS = {
    ".aac", ".flac", ".m4a", ".mp3", ".ogg", ".opus", ".wav", ".webm",
}
FALLBACK_PHRASES = ("Yeah?", "What's up?", "Mm-hmm?")
INTERRUPT_FALLBACK_PHRASES = ("Oh, sorry. Go ahead.", "Sorry, go ahead.", "Yep, I'm listening.")
README = """PETEY wake acknowledgement clips

Put short audio files directly inside the folder named for PETEY's current voice.
For example, Gemini's Kore uses voice-cues/Kore/ and deAPI's Vivian uses
voice-cues/Vivian/. PETEY creates the selected voice folder automatically.

Supported files: WAV, MP3, OGG, OPUS, M4A, AAC, FLAC, and WEBM.
PETEY chooses a clip at random. If the current voice folder has no clips, PETEY
uses clips from voice-cues/default/. If that is also empty, the browser speaks a
short built-in response such as “Yeah?” or “What's up?”.

Put interruption clips such as “Oh, sorry. Go ahead.” in the interrupts/
subfolder inside the current voice folder. PETEY falls back to
voice-cues/default/interrupts/ and chooses a clip at random.
"""


class VoiceCueLibrary:
    def __init__(self, data_dir: str | Path):
        self.root = Path(data_dir) / "voice-cues"
        self.root.mkdir(parents=True, exist_ok=True)
        (self.root / "default").mkdir(exist_ok=True)
        (self.root / "default" / "interrupts").mkdir(exist_ok=True)
        for voice in GEMINI_TTS_VOICES:
            (self.root / voice).mkdir(exist_ok=True)
            (self.root / voice / "interrupts").mkdir(exist_ok=True)
        readme = self.root / "README.txt"
        if not readme.exists():
            readme.write_text(README, encoding="utf-8")

    @staticmethod
    def selected_voice(speech: dict | None) -> str:
        settings = dict(speech or {})
        provider = str(settings.get("provider") or "automatic")
        voice_keys = {"deapi": ("deapi_voice", "Vivian"), "openai": ("openai_voice", "marin")}
        key, fallback = voice_keys.get(provider, ("gemini_voice", "Kore"))
        voice = str(settings.get(key) or fallback).strip()
        safe = re.sub(r"[^A-Za-z0-9._ -]+", "_", voice).strip(" .")[:80]
        return safe or "default"

    def catalog(self, speech: dict | None) -> dict:
        voice = self.selected_voice(speech)
        voice_dir = self.root / voice
        voice_dir.mkdir(exist_ok=True)
        (voice_dir / "interrupts").mkdir(exist_ok=True)
        clips = self._clips(voice_dir)
        source_voice = voice
        if not clips:
            source_voice = "default"
            clips = self._clips(self.root / "default")
        interrupt_source_voice = voice
        interrupt_clips = self._clips(voice_dir / "interrupts")
        if not interrupt_clips:
            interrupt_source_voice = "default"
            interrupt_clips = self._clips(self.root / "default" / "interrupts")
        return {
            "voice": voice,
            "source_voice": source_voice,
            "directory": str(voice_dir),
            "root_directory": str(self.root),
            "clips": clips,
            "fallback_phrases": list(FALLBACK_PHRASES),
            "interrupt_directory": str(voice_dir / "interrupts"),
            "interrupt_source_voice": interrupt_source_voice,
            "interrupt_clips": interrupt_clips,
            "interrupt_fallback_phrases": list(INTERRUPT_FALLBACK_PHRASES),
        }

    def resolve(self, voice: str, filename: str) -> Path:
        if voice not in {self.selected_voice({"gemini_voice": voice}), "default"}:
            raise ValueError("Invalid voice cue folder.")
        relative = Path(filename)
        if (
            relative.is_absolute()
            or len(relative.parts) not in {1, 2}
            or (len(relative.parts) == 2 and relative.parts[0] != "interrupts")
            or any(part in {"", ".", ".."} for part in relative.parts)
        ):
            raise ValueError("Invalid voice cue filename.")
        candidate = (self.root / voice / relative).resolve()
        root = self.root.resolve()
        if root not in candidate.parents or candidate.suffix.lower() not in SUPPORTED_EXTENSIONS:
            raise ValueError("Invalid voice cue file.")
        if not candidate.is_file():
            raise FileNotFoundError(filename)
        return candidate

    @staticmethod
    def _clips(directory: Path) -> list[Path]:
        return sorted(
            (path for path in directory.iterdir()
             if path.is_file() and path.suffix.lower() in SUPPORTED_EXTENSIONS),
            key=lambda path: path.name.casefold(),
        )
