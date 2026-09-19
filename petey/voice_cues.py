"""Local, user-replaceable acknowledgement clips for wake-name mode."""

from __future__ import annotations

import re
from pathlib import Path

from petey.gemini_tts import GEMINI_TTS_VOICES


SUPPORTED_EXTENSIONS = {
    ".aac", ".flac", ".m4a", ".mp3", ".ogg", ".opus", ".wav", ".webm",
}
FALLBACK_PHRASES = ("Yeah?", "What's up?", "Mm-hmm?")
README = """PETEY wake acknowledgement clips

Put short audio files directly inside the folder named for PETEY's current voice.
For example, the Gemini voice Kore uses voice-cues/Kore/.
PETEY creates an empty folder for every supported Gemini voice automatically.

Supported files: WAV, MP3, OGG, OPUS, M4A, AAC, FLAC, and WEBM.
PETEY chooses a clip at random. If the current voice folder has no clips, PETEY
uses clips from voice-cues/default/. If that is also empty, the browser speaks a
short built-in response such as “Yeah?” or “What's up?”.
"""


class VoiceCueLibrary:
    def __init__(self, data_dir: str | Path):
        self.root = Path(data_dir) / "voice-cues"
        self.root.mkdir(parents=True, exist_ok=True)
        (self.root / "default").mkdir(exist_ok=True)
        for voice in GEMINI_TTS_VOICES:
            (self.root / voice).mkdir(exist_ok=True)
        readme = self.root / "README.txt"
        if not readme.exists():
            readme.write_text(README, encoding="utf-8")

    @staticmethod
    def selected_voice(speech: dict | None) -> str:
        settings = dict(speech or {})
        provider = str(settings.get("provider") or "automatic")
        raw = settings.get("openai_voice") if provider == "openai" else settings.get("gemini_voice")
        voice = str(raw or ("marin" if provider == "openai" else "Kore")).strip()
        safe = re.sub(r"[^A-Za-z0-9._ -]+", "_", voice).strip(" .")[:80]
        return safe or "default"

    def catalog(self, speech: dict | None) -> dict:
        voice = self.selected_voice(speech)
        voice_dir = self.root / voice
        voice_dir.mkdir(exist_ok=True)
        clips = self._clips(voice_dir)
        source_voice = voice
        if not clips:
            source_voice = "default"
            clips = self._clips(self.root / "default")
        return {
            "voice": voice,
            "source_voice": source_voice,
            "directory": str(voice_dir),
            "root_directory": str(self.root),
            "clips": clips,
            "fallback_phrases": list(FALLBACK_PHRASES),
        }

    def resolve(self, voice: str, filename: str) -> Path:
        if voice not in {self.selected_voice({"gemini_voice": voice}), "default"}:
            raise ValueError("Invalid voice cue folder.")
        if Path(filename).name != filename:
            raise ValueError("Invalid voice cue filename.")
        candidate = (self.root / voice / filename).resolve()
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
