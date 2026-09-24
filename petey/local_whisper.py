"""Optional, fully local transcription through faster-whisper."""

from __future__ import annotations

import importlib.util
import tempfile
import threading
from pathlib import Path

from petey.gemini_stt import SUPPORTED_AUDIO_TYPES


LOCAL_WHISPER_MODELS = (
    "tiny", "base", "small", "medium", "large-v3", "large-v3-turbo",
)
LOCAL_WHISPER_DEVICES = ("auto", "cpu", "cuda")


class LocalWhisperError(RuntimeError):
    pass


class LocalWhisper:
    _models: dict[tuple[str, str, str], object] = {}
    _lock = threading.RLock()

    def __init__(self, data_dir: str | Path):
        self.root = Path(data_dir) / "local-whisper-models"
        self.root.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def installed() -> bool:
        return importlib.util.find_spec("faster_whisper") is not None

    def status(self, model: str) -> dict:
        model = self._validated_model(model)
        return {
            "installed": self.installed(),
            "downloaded": self._marker(model).is_file(),
            "model": model,
            "model_directory": str(self.root),
        }

    def download(self, model: str, device: str = "auto") -> dict:
        model = self._validated_model(model)
        device = self._validated_device(device)
        self._model(model, device, allow_download=True)
        self._marker(model).write_text("ready\n", encoding="utf-8")
        return self.status(model)

    def transcribe(
        self, audio: bytes, content_type: str, model: str = "small",
        device: str = "auto", vocabulary: list[str] | None = None,
    ) -> str:
        model = self._validated_model(model)
        device = self._validated_device(device)
        if not audio:
            raise LocalWhisperError("The microphone recording was empty.")
        mime = str(content_type or "audio/wav").split(";", 1)[0].strip().lower()
        if mime not in SUPPORTED_AUDIO_TYPES:
            raise LocalWhisperError("This microphone audio format is not supported.")
        if not self._marker(model).is_file():
            raise LocalWhisperError(
                f"Download the {model} Local Whisper model in Settings before using it."
            )
        extension = {
            "audio/wav": ".wav", "audio/x-wav": ".wav", "audio/webm": ".webm",
            "audio/ogg": ".ogg", "audio/mpeg": ".mp3", "audio/mp3": ".mp3",
            "audio/mp4": ".m4a", "audio/m4a": ".m4a", "audio/aac": ".aac",
            "audio/flac": ".flac", "audio/opus": ".opus",
        }.get(mime, ".wav")
        prompt = ", ".join(
            str(word).strip() for word in (vocabulary or []) if str(word).strip()
        )[:1000]
        path = None
        try:
            with tempfile.NamedTemporaryFile(suffix=extension, delete=False) as handle:
                handle.write(audio)
                path = Path(handle.name)
            engine = self._model(model, device, allow_download=False)
            segments, _info = engine.transcribe(
                str(path), language="en", beam_size=1,
                initial_prompt=prompt or None, condition_on_previous_text=False,
            )
            transcript = " ".join(str(segment.text).strip() for segment in segments).strip()
        except LocalWhisperError:
            raise
        except Exception as exc:
            raise LocalWhisperError(f"Local Whisper failed: {exc}") from exc
        finally:
            if path is not None:
                path.unlink(missing_ok=True)
        if not transcript:
            raise LocalWhisperError("Local Whisper did not detect speech.")
        return transcript

    def _model(self, model: str, device: str, *, allow_download: bool):
        if not self.installed():
            raise LocalWhisperError(
                "faster-whisper is not installed. Use the setup link in Speech recognition settings."
            )
        key = (str(self.root.resolve()), model, device)
        with self._lock:
            cached = self._models.get(key)
            if cached is not None:
                return cached
            try:
                from faster_whisper import WhisperModel

                engine = WhisperModel(
                    model, device=device, compute_type="default",
                    download_root=str(self.root), local_files_only=not allow_download,
                )
            except Exception as exc:
                action = "download or load" if allow_download else "load"
                raise LocalWhisperError(
                    f"Could not {action} Local Whisper model {model}: {exc}"
                ) from exc
            self._models[key] = engine
            return engine

    def _marker(self, model: str) -> Path:
        return self.root / f"{model}.ready"

    @staticmethod
    def _validated_model(model: str) -> str:
        value = str(model or "small").strip()
        if value not in LOCAL_WHISPER_MODELS:
            raise LocalWhisperError("Choose a supported Local Whisper model.")
        return value

    @staticmethod
    def _validated_device(device: str) -> str:
        value = str(device or "auto").strip().lower()
        if value not in LOCAL_WHISPER_DEVICES:
            raise LocalWhisperError("Choose Automatic, CPU, or NVIDIA CUDA.")
        return value
