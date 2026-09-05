"""Universal local memory store for Petey's standalone desktop runtime."""

from __future__ import annotations

import datetime as dt
import heapq
import json
import math
import queue
import sqlite3
import threading
from array import array
from collections import OrderedDict
from pathlib import Path
from typing import Callable


EmbeddingFactory = Callable[[str], dict | None]

class _DaemonTaskPool:
    """Small lazy worker pool that never delays process shutdown."""

    def __init__(self, workers=2, capacity=512):
        self._worker_count = workers
        self._queue: queue.Queue = queue.Queue(maxsize=capacity)
        self._start_lock = threading.Lock()
        self._started = False

    def submit(self, function) -> bool:
        with self._start_lock:
            if not self._started:
                for index in range(self._worker_count):
                    threading.Thread(
                        target=self._work,
                        name=f"petey-embed-{index + 1}",
                        daemon=True,
                    ).start()
                self._started = True
        try:
            self._queue.put_nowait(function)
            return True
        except queue.Full:
            print("[MEMORY] Embedding queue is full; leaving this item available for rebuild.")
            return False

    def _work(self) -> None:
        while True:
            function = self._queue.get()
            try:
                function()
            except Exception as exc:
                print(f"[MEMORY] Background indexing failed: {exc}")
            finally:
                self._queue.task_done()


# An unbounded thread-per-message model can overwhelm local model servers during
# a fast conversation. This pool preserves background indexing with backpressure.
_EMBEDDING_EXECUTOR = _DaemonTaskPool()
MAX_CACHED_VECTORS = 3000


class DesktopMemory:
    """SQLite-backed messages, documents, metrics, and dimension-agnostic vectors."""

    def __init__(self, path: str | Path, embedding_factory: EmbeddingFactory):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.embedding_factory = embedding_factory
        self._write_lock = threading.RLock()
        self._vector_cache_lock = threading.Lock()
        self._vector_cache: OrderedDict[int, tuple[int, array, float]] = OrderedDict()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=30)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA busy_timeout=30000")
        return connection

    def init_db(self) -> None:
        with self._connect() as connection:
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute("PRAGMA synchronous=NORMAL")
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS memory_items (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    installation_id TEXT NOT NULL,
                    conversation_id TEXT,
                    user_id TEXT NOT NULL,
                    kind TEXT NOT NULL CHECK(kind IN ('message', 'document')),
                    source_name TEXT,
                    content TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    embedding_json TEXT,
                    embedding_provider TEXT,
                    embedding_model TEXT,
                    embedding_dimensions INTEGER
                );
                CREATE INDEX IF NOT EXISTS idx_memory_conversation
                    ON memory_items(installation_id, conversation_id, id);
                CREATE INDEX IF NOT EXISTS idx_memory_source
                    ON memory_items(installation_id, kind, source_name);
                CREATE INDEX IF NOT EXISTS idx_memory_embedding_signature
                    ON memory_items(installation_id, embedding_provider, embedding_model, embedding_dimensions);
                CREATE TABLE IF NOT EXISTS image_generations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    installation_id TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    prompt TEXT,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS metadata (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );
                INSERT OR REPLACE INTO metadata(key, value) VALUES ('schema_version', '1');
                """
            )

    def _insert_item(
        self,
        installation_id: str,
        conversation_id: str | None,
        user_id: str,
        kind: str,
        content: str,
        source_name: str | None = None,
    ) -> int:
        with self._write_lock, self._connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO memory_items(
                    installation_id, conversation_id, user_id, kind, source_name, content, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(installation_id),
                    str(conversation_id) if conversation_id is not None else None,
                    str(user_id),
                    kind,
                    source_name,
                    content.strip(),
                    dt.datetime.now(dt.timezone.utc).isoformat(),
                ),
            )
            return int(cursor.lastrowid)

    def _embed_item(self, item_id: int, content: str) -> bool:
        result = self.embedding_factory(content)
        if not result:
            return False
        values = [float(value) for value in result["values"]]
        with self._write_lock, self._connect() as connection:
            connection.execute(
                """
                UPDATE memory_items SET embedding_json=?, embedding_provider=?,
                    embedding_model=?, embedding_dimensions=? WHERE id=?
                """,
                (
                    json.dumps(values, separators=(",", ":")),
                    result["provider"],
                    result["model"],
                    len(values),
                    item_id,
                ),
            )
        return True

    def _embed_in_background(self, item_id: int, content: str) -> None:
        def work():
            try:
                self._embed_item(item_id, content)
            except Exception as exc:
                print(f"[MEMORY] Local embedding failed for item {item_id}: {exc}")

        _EMBEDDING_EXECUTOR.submit(work)

    def store_memory(self, installation_id, conversation_id, user_id, content: str) -> None:
        item_id = self.store_memory_deferred(
            installation_id, conversation_id, user_id, content
        )
        if item_id is not None:
            self.queue_embedding(item_id, content)

    def store_memory_deferred(
        self, installation_id, conversation_id, user_id, content: str
    ) -> int | None:
        if not content or not content.strip():
            return None
        return self._insert_item(
            str(installation_id), str(conversation_id), str(user_id), "message", content
        )

    def queue_embedding(self, item_id: int, content: str) -> None:
        self._embed_in_background(item_id, content)

    @staticmethod
    def chunk_text(text: str, size: int = 800, overlap: int = 150) -> list[str]:
        chunks = []
        step = max(1, size - overlap)
        for index in range(0, len(text), step):
            chunk = text[index:index + size]
            if chunk:
                chunks.append(chunk)
        return chunks

    def store_document(self, installation_id: str, filename: str, content: str) -> None:
        if not content or not content.strip():
            return

        def work():
            chunks = self.chunk_text(content.strip())
            for index, chunk in enumerate(chunks, 1):
                formatted = f"[From {filename} part {index}] {chunk}"
                item_id = self._insert_item(
                    installation_id, None, "SYSTEM_DOC", "document", formatted, filename
                )
                try:
                    self._embed_item(item_id, formatted)
                except Exception as exc:
                    print(f"[MEMORY] Document embedding failed for {filename} part {index}: {exc}")
            print(f"[MEMORY] Stored {len(chunks)} local chunks for {filename}")

        _EMBEDDING_EXECUTOR.submit(work)

    def get_documents(self, installation_id: str) -> list[str]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT DISTINCT source_name FROM memory_items
                WHERE installation_id=? AND kind='document' AND source_name IS NOT NULL
                ORDER BY source_name COLLATE NOCASE
                """,
                (str(installation_id),),
            ).fetchall()
        return [str(row["source_name"]) for row in rows]

    def delete_document(self, installation_id: str, filename: str) -> bool:
        with self._write_lock, self._connect() as connection:
            connection.execute(
                "DELETE FROM memory_items WHERE installation_id=? AND kind='document' AND source_name=?",
                (str(installation_id), filename),
            )
        self._discard_cached_vectors()
        return True

    def clear_conversation(self, installation_id: str, conversation_id: str) -> int:
        with self._write_lock, self._connect() as connection:
            cursor = connection.execute(
                "DELETE FROM memory_items WHERE installation_id=? AND kind='message' AND conversation_id=?",
                (str(installation_id), str(conversation_id)),
            )
            deleted = max(0, int(cursor.rowcount or 0))
        if deleted:
            self._discard_cached_vectors()
        return deleted

    def get_conversation_messages(self, installation_id, conversation_id, limit=50) -> list[dict]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT id, user_id, content, created_at FROM memory_items
                WHERE installation_id=? AND kind='message' AND conversation_id=?
                ORDER BY id DESC LIMIT ?
                """,
                (str(installation_id), str(conversation_id), int(limit)),
            ).fetchall()
        return [
            {
                "id": row["id"],
                "user_id": row["user_id"],
                "message": row["content"],
                "timestamp": row["created_at"],
            }
            for row in reversed(rows)
        ]

    @staticmethod
    def _cosine(left: list[float], right: list[float]) -> float:
        if len(left) != len(right) or not left:
            return -1.0
        dot = sum(a * b for a, b in zip(left, right))
        left_norm = math.sqrt(sum(value * value for value in left))
        right_norm = math.sqrt(sum(value * value for value in right))
        return dot / (left_norm * right_norm) if left_norm and right_norm else -1.0

    def _cached_vector(self, row: sqlite3.Row) -> tuple[array, float]:
        item_id = int(row["id"])
        encoded = str(row["embedding_json"])
        signature = hash(encoded)
        with self._vector_cache_lock:
            cached = self._vector_cache.get(item_id)
            if cached is not None and cached[0] == signature:
                self._vector_cache.move_to_end(item_id)
                return cached[1], cached[2]
        vector = array("d", (float(value) for value in json.loads(encoded)))
        norm = math.sqrt(sum(value * value for value in vector))
        with self._vector_cache_lock:
            self._vector_cache[item_id] = (signature, vector, norm)
            self._vector_cache.move_to_end(item_id)
            while len(self._vector_cache) > MAX_CACHED_VECTORS:
                self._vector_cache.popitem(last=False)
        return vector, norm

    def _semantic_score(self, query: tuple[float, ...], query_norm: float, row: sqlite3.Row) -> float:
        vector, vector_norm = self._cached_vector(row)
        if len(query) != len(vector) or not query_norm or not vector_norm:
            return -1.0
        return sum(left * right for left, right in zip(query, vector)) / (query_norm * vector_norm)

    def _discard_cached_vectors(self, item_ids=None) -> None:
        with self._vector_cache_lock:
            if item_ids is None:
                self._vector_cache.clear()
            else:
                for item_id in item_ids:
                    self._vector_cache.pop(int(item_id), None)

    def search_memories(
        self, query: str, installation_id: str, limit=5,
        exclude_conversation_id: str | None = None,
    ) -> str:
        if not query or not query.strip():
            return ""
        with self._connect() as connection:
            if exclude_conversation_id is None:
                available = connection.execute(
                    "SELECT 1 FROM memory_items WHERE installation_id=? LIMIT 1",
                    (str(installation_id),),
                ).fetchone()
            else:
                available = connection.execute(
                    """
                    SELECT 1 FROM memory_items
                    WHERE installation_id=?
                      AND (conversation_id IS NULL OR conversation_id<>?)
                    LIMIT 1
                    """,
                    (str(installation_id), str(exclude_conversation_id)),
                ).fetchone()
        if available is None:
            return ""
        try:
            query_result = self.embedding_factory(query)
        except Exception as exc:
            print(f"[MEMORY] Query embedding unavailable; using text search: {exc}")
            query_result = None

        with self._connect() as connection:
            if query_result:
                conversation_clause = ""
                parameters = [
                    str(installation_id),
                    query_result["provider"],
                    query_result["model"],
                    query_result["dimensions"],
                ]
                if exclude_conversation_id is not None:
                    conversation_clause = "AND (conversation_id IS NULL OR conversation_id<>?)"
                    parameters.append(str(exclude_conversation_id))
                rows = connection.execute(
                    f"""
                    SELECT id, content, created_at, kind, source_name, embedding_json
                    FROM memory_items
                    WHERE installation_id=? AND embedding_provider=? AND embedding_model=?
                      AND embedding_dimensions=? AND embedding_json IS NOT NULL
                      {conversation_clause}
                    ORDER BY id DESC LIMIT 3000
                    """,
                    parameters,
                ).fetchall()
                query_vector = tuple(float(value) for value in query_result["values"])
                query_norm = math.sqrt(sum(value * value for value in query_vector))
                scored = heapq.nlargest(
                    int(limit),
                    ((self._semantic_score(query_vector, query_norm, row), row) for row in rows),
                    key=lambda pair: pair[0],
                )
                selected = [row for score, row in scored if score > 0.15]
            else:
                words = [word for word in query.strip().split() if len(word) > 2][:5]
                if not words:
                    return ""
                clauses = " OR ".join("content LIKE ?" for _ in words)
                conversation_clause = ""
                parameters = [str(installation_id), *(f"%{word}%" for word in words)]
                if exclude_conversation_id is not None:
                    conversation_clause = "AND (conversation_id IS NULL OR conversation_id<>?)"
                    parameters.append(str(exclude_conversation_id))
                parameters.append(int(limit))
                selected = connection.execute(
                    f"""
                    SELECT content, created_at, kind, source_name FROM memory_items
                    WHERE installation_id=? AND ({clauses}) {conversation_clause}
                    ORDER BY id DESC LIMIT ?
                    """,
                    parameters,
                ).fetchall()

        lines = []
        for row in selected:
            try:
                timestamp = dt.datetime.fromisoformat(row["created_at"]).strftime("%Y-%m-%d %H:%M")
            except ValueError:
                timestamp = row["created_at"]
            label = (
                f"[📄 {row['source_name']} — {timestamp}]"
                if row["kind"] == "document"
                else f"[{timestamp}]"
            )
            lines.append(f"{label} {row['content']}")
        return "\n".join(lines)

    def get_memory_stats(self, installation_id: str, conversation_id: str) -> dict:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT
                    SUM(CASE WHEN kind='message' AND conversation_id=? THEN 1 ELSE 0 END) conversation_messages,
                    SUM(CASE WHEN kind='document' THEN 1 ELSE 0 END) document_chunks,
                    SUM(CASE WHEN embedding_json IS NOT NULL THEN 1 ELSE 0 END) embedded_memories,
                    SUM(CASE WHEN embedding_json IS NULL THEN 1 ELSE 0 END) unembedded_memories
                FROM memory_items WHERE installation_id=?
                """,
                (str(conversation_id), str(installation_id)),
            ).fetchone()
        return {key: int(row[key] or 0) for key in row.keys()}

    def record_image_generation(self, installation_id: str, user_id: str, prompt: str) -> None:
        with self._write_lock, self._connect() as connection:
            connection.execute(
                "INSERT INTO image_generations(installation_id, user_id, prompt, created_at) VALUES (?, ?, ?, ?)",
                (str(installation_id), str(user_id), prompt, dt.datetime.now(dt.timezone.utc).isoformat()),
            )

    def rebuild_embeddings(self, installation_id: str) -> int:
        with self._write_lock, self._connect() as connection:
            connection.execute(
                """
                UPDATE memory_items SET embedding_json=NULL, embedding_provider=NULL,
                    embedding_model=NULL, embedding_dimensions=NULL WHERE installation_id=?
                """,
                (str(installation_id),),
            )
            rows = connection.execute(
                "SELECT id, content FROM memory_items WHERE installation_id=? ORDER BY id",
                (str(installation_id),),
            ).fetchall()
        self._discard_cached_vectors()

        def work():
            for row in rows:
                try:
                    self._embed_item(int(row["id"]), row["content"])
                except Exception as exc:
                    print(f"[MEMORY] Rebuild stopped at item {row['id']}: {exc}")
                    break

        _EMBEDDING_EXECUTOR.submit(work)
        return len(rows)

    def reset(self, installation_id: str) -> int:
        with self._write_lock, self._connect() as connection:
            cursor = connection.execute(
                "DELETE FROM memory_items WHERE installation_id=?", (str(installation_id),)
            )
            connection.execute(
                "DELETE FROM image_generations WHERE installation_id=?", (str(installation_id),)
            )
            deleted = max(0, int(cursor.rowcount or 0))
        if deleted:
            self._discard_cached_vectors()
        return deleted
