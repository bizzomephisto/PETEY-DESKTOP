"""Bounded delivery of hidden add-on events to PETEY conversations."""

from __future__ import annotations

from collections import deque
import queue
import threading
import time


class AddonEventError(ValueError):
    pass


class AddonEventBroker:
    """Serialize autonomous add-on prompts and publish their visible replies."""

    def __init__(self, handler, *, max_queue: int = 32, history_size: int = 100):
        self._handler = handler
        self._queue = queue.Queue(maxsize=max(1, min(100, int(max_queue))))
        self._events = deque(maxlen=max(10, min(500, int(history_size))))
        self._lock = threading.RLock()
        self._closed = threading.Event()
        self._next_id = 1
        self._recent_keys: dict[str, float] = {}
        self._worker = threading.Thread(
            target=self._run, name="petey-addon-events", daemon=True
        )
        self._worker.start()

    @property
    def latest_id(self) -> int:
        with self._lock:
            return self._next_id - 1

    def emit(
        self,
        addon_id: str,
        message: object,
        *,
        conversation_id: str,
        surface: str = "petey_desktop",
        speak: bool = False,
        metadata: dict | None = None,
        user_initiated: bool = False,
    ) -> dict:
        source = str(addon_id or "").strip()[:64]
        text = str(message or "").strip()
        target = str(conversation_id or "").strip()
        if not source or not text or len(text) > 5000:
            raise AddonEventError("Add-on events require a source and a message up to 5,000 characters.")
        if not target:
            raise AddonEventError("Add-on events require a conversation.")
        safe_surface = surface if surface in {"petey_desktop", "mobile_petey"} else "petey_desktop"
        safe_metadata = {
            str(key)[:80]: value
            for key, value in (metadata or {}).items()
            if isinstance(key, str) and isinstance(value, (str, int, float, bool, type(None)))
        }
        dedupe_key = f"{source}:{target}:{safe_surface}:{text}"
        now = time.monotonic()
        with self._lock:
            self._recent_keys = {
                key: seen for key, seen in self._recent_keys.items() if now - seen < 30
            }
            if dedupe_key in self._recent_keys:
                return {"status": "duplicate_ignored"}
            self._recent_keys[dedupe_key] = now
        try:
            self._queue.put_nowait({
                "addon_id": source,
                "message": text,
                "conversation_id": target,
                "surface": safe_surface,
                "speak": bool(speak),
                "metadata": safe_metadata,
                "user_initiated": bool(user_initiated),
            })
        except queue.Full as exc:
            raise AddonEventError("PETEY's add-on event queue is full.") from exc
        return {"status": "queued"}

    def events_after(self, cursor: object) -> dict:
        try:
            after = max(0, int(cursor or 0))
        except (TypeError, ValueError):
            after = 0
        with self._lock:
            return {
                "cursor": self.latest_id,
                "events": [dict(item) for item in self._events if item["id"] > after],
            }

    def _run(self) -> None:
        while not self._closed.is_set():
            try:
                event = self._queue.get(timeout=0.25)
            except queue.Empty:
                continue
            if event is None:
                break
            try:
                reply = self._handler(event)
                if not isinstance(reply, dict) or not str(reply.get("text") or "").strip():
                    continue
                with self._lock:
                    published = {
                        "id": self._next_id,
                        "addon_id": event["addon_id"],
                        "conversation_id": event["conversation_id"],
                        "surface": event["surface"],
                        "text": str(reply["text"]),
                        "speak": event["speak"],
                        "tool_events": list(reply.get("tool_events") or []),
                        "metadata": dict(event.get("metadata") or {}),
                    }
                    self._next_id += 1
                    self._events.append(published)
            except Exception as exc:
                print(f"[ADDON EVENT] {event['addon_id']} failed: {exc}")
            finally:
                self._queue.task_done()

    def close(self) -> None:
        if self._closed.is_set():
            return
        self._closed.set()
        try:
            self._queue.put_nowait(None)
        except queue.Full:
            pass
        self._worker.join(timeout=3)
