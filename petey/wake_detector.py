"""Streaming, local wake-word detection backed by sherpa-onnx."""

from __future__ import annotations

import shutil
import tarfile
import threading
import time
import uuid
from array import array
from pathlib import Path

import requests


MODEL_NAME = "sherpa-onnx-kws-zipformer-gigaspeech-3.3M-2024-01-01"
MODEL_URL = (
    "https://github.com/k2-fsa/sherpa-onnx/releases/download/kws-models/"
    f"{MODEL_NAME}.tar.bz2"
)
MODEL_FILES = {
    "bpe.model",
    "tokens.txt",
    "encoder-epoch-12-avg-2-chunk-16-left-64.int8.onnx",
    "decoder-epoch-12-avg-2-chunk-16-left-64.int8.onnx",
    "joiner-epoch-12-avg-2-chunk-16-left-64.int8.onnx",
}


class WakeDetectorError(RuntimeError):
    pass


class LocalWakeDetector:
    """Owns one small KWS model and independent browser audio streams."""

    def __init__(self, data_dir: str | Path):
        self.model_dir = Path(data_dir) / "wake-word" / MODEL_NAME
        self._spotter = None
        self._processor = None
        self._sessions: dict[str, dict] = {}
        self._lock = threading.RLock()

    def _model_ready(self) -> bool:
        return all((self.model_dir / name).is_file() for name in MODEL_FILES)

    def _install_model(self) -> None:
        if self._model_ready():
            return
        parent = self.model_dir.parent
        parent.mkdir(parents=True, exist_ok=True)
        archive = parent / f".{MODEL_NAME}-{uuid.uuid4().hex}.tar.bz2"
        staging = parent / f".{MODEL_NAME}-{uuid.uuid4().hex}"
        staging.mkdir()
        try:
            with requests.get(MODEL_URL, stream=True, timeout=(10, 90)) as response:
                response.raise_for_status()
                with archive.open("wb") as output:
                    for chunk in response.iter_content(1024 * 1024):
                        if chunk:
                            output.write(chunk)
            with tarfile.open(archive, "r:bz2") as bundle:
                members = {
                    Path(member.name).name: member
                    for member in bundle.getmembers()
                    if member.isfile() and Path(member.name).name in MODEL_FILES
                }
                if set(members) != MODEL_FILES:
                    raise WakeDetectorError("The downloaded wake model is incomplete.")
                for name, member in members.items():
                    source = bundle.extractfile(member)
                    if source is None:
                        raise WakeDetectorError("The downloaded wake model is invalid.")
                    with source, (staging / name).open("wb") as output:
                        shutil.copyfileobj(source, output)
            if self.model_dir.exists():
                shutil.rmtree(self.model_dir)
            staging.replace(self.model_dir)
        except (OSError, requests.RequestException, tarfile.TarError) as exc:
            raise WakeDetectorError(f"Could not install the local wake model: {exc}") from exc
        finally:
            archive.unlink(missing_ok=True)
            if staging.exists():
                shutil.rmtree(staging, ignore_errors=True)

    def _load(self) -> None:
        if self._spotter is not None:
            return
        self._install_model()
        try:
            import sentencepiece
            import sherpa_onnx
        except ImportError as exc:
            raise WakeDetectorError(
                "Local wake detection could not import sherpa-onnx and sentencepiece: "
                f"{exc}."
            ) from exc
        self._processor = sentencepiece.SentencePieceProcessor(
            model_file=str(self.model_dir / "bpe.model")
        )
        base_keywords = self.model_dir / "base-keywords.txt"
        if not base_keywords.exists():
            base_keywords.touch()
        self._spotter = sherpa_onnx.KeywordSpotter(
            tokens=str(self.model_dir / "tokens.txt"),
            encoder=str(self.model_dir / "encoder-epoch-12-avg-2-chunk-16-left-64.int8.onnx"),
            decoder=str(self.model_dir / "decoder-epoch-12-avg-2-chunk-16-left-64.int8.onnx"),
            joiner=str(self.model_dir / "joiner-epoch-12-avg-2-chunk-16-left-64.int8.onnx"),
            keywords_file=str(base_keywords),
            num_threads=1,
            keywords_score=3.0,
            keywords_threshold=0.05,
            num_trailing_blanks=0,
        )

    def _keywords(self, wake_word: str) -> str:
        cleaned = " ".join(str(wake_word or "Petey").upper().split())[:40] or "PETEY"
        phrases = [cleaned, f"HEY {cleaned}"]
        if cleaned == "PETEY":
            # The compact English model may render the name as ordinary spelling
            # or as spoken letter sounds. PETE is intentionally excluded because
            # it creates conversational false wakes in the bundled model.
            aliases = ("PETTY", "P T", "P T Y", "PEE TEE")
            for alias in aliases:
                phrases.extend((alias, f"HEY {alias}"))
        encoded = []
        for phrase in phrases:
            pieces = self._processor.encode(phrase, out_type=str)
            if pieces:
                encoded.append(f"{' '.join(pieces)} @{phrase.replace(' ', '_')}")
        if not encoded:
            raise WakeDetectorError("The wake name could not be encoded.")
        return "/".join(encoded)

    def start(self, wake_word: str) -> str:
        with self._lock:
            self._load()
            session_id = uuid.uuid4().hex
            self._sessions[session_id] = {
                "stream": self._spotter.create_stream(self._keywords(wake_word)),
                "seen": time.monotonic(),
            }
            self._prune()
            return session_id

    def feed(self, session_id: str, pcm: bytes, sample_rate: int = 16000) -> bool:
        if not pcm or len(pcm) > 256 * 1024 or len(pcm) % 2:
            raise WakeDetectorError("Wake audio must be bounded 16-bit PCM.")
        if sample_rate < 8000 or sample_rate > 48000:
            raise WakeDetectorError("Wake audio sample rate is unsupported.")
        samples = array("h")
        samples.frombytes(pcm)
        if samples.itemsize != 2:
            raise WakeDetectorError("This platform cannot decode 16-bit wake audio.")
        scale = 1.0 / 32768.0
        waveform = [sample * scale for sample in samples]
        with self._lock:
            session = self._sessions.get(session_id)
            if session is None:
                raise WakeDetectorError("The local wake session expired.")
            session["seen"] = time.monotonic()
            stream = session["stream"]
            stream.accept_waveform(sample_rate, waveform)
            while self._spotter.is_ready(stream):
                self._spotter.decode_stream(stream)
                if self._spotter.get_result(stream):
                    self._spotter.reset_stream(stream)
                    return True
            return False

    def stop(self, session_id: str) -> None:
        with self._lock:
            self._sessions.pop(session_id, None)

    def _prune(self) -> None:
        cutoff = time.monotonic() - 120
        for session_id, session in list(self._sessions.items()):
            if session["seen"] < cutoff:
                self._sessions.pop(session_id, None)
