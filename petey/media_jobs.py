"""Concurrent desktop media jobs and persistent local gallery storage."""

from __future__ import annotations

import asyncio
import json
import mimetypes
import queue
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path

import aiohttp

from petey.deapi_client import DeapiClient
from petey.media_service import MediaInput, MediaService


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class MediaGallery:
    """Store generated files and a small JSON index under Petey's data directory."""

    MAX_DOWNLOAD_BYTES = 500 * 1024 * 1024

    def __init__(self, directory: str | Path):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.index_path = self.directory / "index.json"
        self._lock = threading.RLock()
        self._items = self._load()

    def _load(self) -> list[dict]:
        try:
            value = json.loads(self.index_path.read_text(encoding="utf-8"))
            return value if isinstance(value, list) else []
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            return []

    def _write_locked(self) -> None:
        temporary = self.index_path.with_suffix(".json.tmp")
        temporary.write_text(json.dumps(self._items, indent=2), encoding="utf-8")
        temporary.replace(self.index_path)

    def list_items(self) -> list[dict]:
        with self._lock:
            return [dict(item) for item in sorted(self._items, key=lambda item: item["created_at"], reverse=True)]

    def get(self, item_id: str) -> dict | None:
        with self._lock:
            item = next((item for item in self._items if item["id"] == item_id), None)
            return dict(item) if item else None

    async def capture(
        self,
        item_id: str,
        result: dict,
        prompt: str,
        model_slug: str,
    ) -> dict:
        remote_url = result["result_url"]
        content_type = ""
        local_filename = ""
        download_error = ""
        partial = self.directory / f"{item_id}.part"
        try:
            timeout = aiohttp.ClientTimeout(total=None, connect=30, sock_read=120)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(remote_url) as response:
                    response.raise_for_status()
                    content_type = response.headers.get("Content-Type", "").split(";", 1)[0]
                    extension = self._extension(content_type, result["kind"])
                    local_filename = f"{item_id}{extension}"
                    total = 0
                    with partial.open("wb") as output:
                        async for chunk in response.content.iter_chunked(1024 * 1024):
                            total += len(chunk)
                            if total > self.MAX_DOWNLOAD_BYTES:
                                raise ValueError("Generated file exceeded the 500 MB local gallery limit.")
                            output.write(chunk)
            partial.replace(self.directory / local_filename)
        except Exception as exc:
            download_error = str(exc)
            local_filename = ""
            try:
                partial.unlink(missing_ok=True)
            except OSError:
                pass

        item = {
            "id": item_id,
            "created_at": _now(),
            "operation": result["operation"],
            "kind": result["kind"],
            "prompt": prompt,
            "model_slug": model_slug,
            "remote_url": remote_url,
            "local_filename": local_filename,
            "content_type": content_type,
            "download_error": download_error,
        }
        with self._lock:
            self._items = [existing for existing in self._items if existing["id"] != item_id]
            self._items.append(item)
            self._write_locked()
        return dict(item)

    def delete(self, item_id: str) -> bool:
        with self._lock:
            item = next((item for item in self._items if item["id"] == item_id), None)
            if not item:
                return False
            if item.get("local_filename"):
                try:
                    (self.directory / item["local_filename"]).unlink(missing_ok=True)
                except OSError as exc:
                    print(f"[GALLERY] Could not delete media file: {exc}")
            self._items = [existing for existing in self._items if existing["id"] != item_id]
            self._write_locked()
            return True

    def file_path(self, item_id: str) -> Path | None:
        item = self.get(item_id)
        if not item or not item.get("local_filename"):
            return None
        path = self.directory / item["local_filename"]
        return path if path.is_file() else None

    @staticmethod
    def _extension(content_type: str, kind: str) -> str:
        known = {
            "image/png": ".png", "image/jpeg": ".jpg", "image/webp": ".webp",
            "video/mp4": ".mp4", "video/webm": ".webm",
            "audio/mpeg": ".mp3", "audio/wav": ".wav", "audio/ogg": ".ogg",
        }
        return known.get(content_type) or mimetypes.guess_extension(content_type) or {
            "image": ".png", "video": ".mp4", "audio": ".mp3"
        }[kind]


class MediaJobManager:
    """Run multiple isolated deAPI clients on daemon workers."""

    def __init__(self, gallery: MediaGallery, max_workers: int = 3):
        self.gallery = gallery
        self.max_workers = max(2, int(max_workers))
        self._jobs: dict[str, dict] = {}
        self._lock = threading.RLock()
        self._queue: queue.Queue = queue.Queue()
        self._closed = False
        self._workers = [
            threading.Thread(target=self._worker, name=f"petey-media-{index + 1}", daemon=True)
            for index in range(self.max_workers)
        ]
        for worker in self._workers:
            worker.start()

    def submit(
        self,
        operation: str,
        prompt: str,
        installation_id: str,
        model_slug: str,
        source: MediaInput | None,
        parameters: dict,
    ) -> dict:
        if self._closed:
            raise RuntimeError("The media job manager is shutting down.")
        with self._lock:
            pending = sum(
                job["status"] in {"queued", "running"} for job in self._jobs.values()
            )
        if pending >= 20:
            raise ValueError("The media queue is full. Wait for a generation to finish.")
        # Validate immediately so a malformed request does not occupy a queue slot.
        config = MediaService._require_operation(operation)
        MediaService._validate_source(config["file"], source)
        if operation not in {"img-rmbg", "img-upscale"} and not (prompt or "").strip():
            raise ValueError("A prompt or text value is required.")

        job_id = uuid.uuid4().hex
        job = {
            "id": job_id,
            "status": "queued",
            "provider_status": "queued",
            "progress": None,
            "preview_url": "",
            "request_id": "",
            "created_at": _now(),
            "started_at": None,
            "completed_at": None,
            "operation": operation,
            "kind": config["kind"],
            "prompt": (prompt or "").strip(),
            "model_slug": model_slug or "",
            "source_name": source.filename if source else "",
            "result": None,
            "error": "",
            "_installation_id": installation_id,
            "_source": source,
            "_parameters": dict(parameters),
        }
        with self._lock:
            self._jobs[job_id] = job
            self._prune_locked()
        self._queue.put(job_id)
        return self._public(job)

    def list_jobs(self) -> list[dict]:
        with self._lock:
            return [
                self._public(job)
                for job in sorted(self._jobs.values(), key=lambda item: item["created_at"], reverse=True)
            ]

    def get(self, job_id: str) -> dict | None:
        with self._lock:
            job = self._jobs.get(job_id)
            return self._public(job) if job else None

    def close(self) -> None:
        self._closed = True
        for _worker in self._workers:
            self._queue.put(None)

    def _worker(self) -> None:
        while True:
            job_id = self._queue.get()
            if job_id is None:
                return
            with self._lock:
                job = self._jobs.get(job_id)
                if not job:
                    continue
                job["status"] = "running"
                job["provider_status"] = "submitting"
                job["started_at"] = _now()
            try:
                result, gallery_item = asyncio.run(self._execute(job))
                with self._lock:
                    job["status"] = "completed"
                    job["provider_status"] = "done"
                    job["progress"] = 100.0
                    job["result"] = {**result, "gallery_item": gallery_item}
                    job["completed_at"] = _now()
                    job["_source"] = None
            except Exception as exc:
                print(f"[MEDIA JOB] {job_id} failed: {exc}")
                with self._lock:
                    job["status"] = "failed"
                    job["provider_status"] = "error"
                    job["error"] = str(exc)
                    job["completed_at"] = _now()
                    job["_source"] = None

    async def _execute(self, job: dict) -> tuple[dict, dict]:
        client = DeapiClient(
            progress_callback=lambda update: self._update_progress(job["id"], update)
        )
        try:
            result = await MediaService(client).generate(
                operation=job["operation"],
                prompt=job["prompt"],
                installation_id=job["_installation_id"],
                model_slug=job["model_slug"],
                source=job["_source"],
                parameters=job["_parameters"],
            )
            gallery_item = await self.gallery.capture(
                job["id"], result, job["prompt"], job["model_slug"]
            )
            return result, gallery_item
        finally:
            await client.close()

    def _update_progress(self, job_id: str, update: dict) -> None:
        progress = update.get("progress")
        if progress is not None:
            try:
                progress = round(max(0.0, min(100.0, float(progress))), 1)
            except (TypeError, ValueError):
                progress = None
        with self._lock:
            job = self._jobs.get(job_id)
            if not job or job["status"] not in {"queued", "running"}:
                return
            job["provider_status"] = str(update.get("status") or "processing")[:40]
            job["progress"] = progress
            job["request_id"] = str(update.get("request_id") or "")[:100]
            preview_url = str(update.get("preview_url") or "")
            if preview_url.startswith(("http://", "https://")):
                job["preview_url"] = preview_url

    def _prune_locked(self) -> None:
        if len(self._jobs) <= 100:
            return
        finished = sorted(
            (job for job in self._jobs.values() if job["status"] in {"completed", "failed"}),
            key=lambda item: item["created_at"],
        )
        for job in finished[: max(0, len(self._jobs) - 100)]:
            self._jobs.pop(job["id"], None)

    @staticmethod
    def _public(job: dict) -> dict:
        return {key: value for key, value in job.items() if not key.startswith("_")}
