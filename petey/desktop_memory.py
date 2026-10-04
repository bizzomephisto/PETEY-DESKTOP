"""Universal local memory store for Petey's standalone desktop runtime."""

from __future__ import annotations

import datetime as dt
import heapq
import json
import math
import queue
import re
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
_SEARCH_STOP_WORDS = frozenset({
    "a", "about", "all", "an", "and", "are", "as", "at", "be", "by", "can",
    "did", "do", "does", "for", "from", "had", "has", "have", "how", "i",
    "in", "is", "it", "me", "my", "of", "on", "or", "our", "that", "the",
    "their", "them", "there", "these", "this", "to", "was", "we", "were",
    "what", "when", "where", "which", "who", "why", "with", "you", "your",
})


MAX_MEMORY_CONTEXT_CHARS = 6000
_BROAD_TIME_RECALL = re.compile(
    r"\b(?:what happened|what did (?:we|i|you) do|recap|summari[sz]e)\b",
    re.IGNORECASE,
)


def _recall_window(query: str, now: dt.datetime | None = None):
    local_now = (now or dt.datetime.now().astimezone()).astimezone()
    day = local_now.replace(hour=0, minute=0, second=0, microsecond=0)
    lowered = query.casefold()
    if re.search(r"\blast night\b", lowered):
        label = "last night"
        start = day - dt.timedelta(days=1) + dt.timedelta(hours=18)
        end = day + dt.timedelta(hours=6)
    elif re.search(r"\byesterday\b", lowered):
        label = "yesterday"
        start, end = day - dt.timedelta(days=1), day
    elif re.search(r"\btoday\b", lowered):
        label = "today"
        start, end = day, day + dt.timedelta(days=1)
    else:
        return None
    return label, start.astimezone(dt.timezone.utc), end.astimezone(dt.timezone.utc)


class DesktopMemory:
    """SQLite-backed messages, documents, metrics, and dimension-agnostic vectors."""

    def __init__(self, path: str | Path, embedding_factory: EmbeddingFactory):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.embedding_factory = embedding_factory
        self._write_lock = threading.RLock()
        self._vector_cache_lock = threading.Lock()
        self._vector_cache: OrderedDict[int, tuple[array, float]] = OrderedDict()

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
                    embedding_dimensions INTEGER,
                    source_surface TEXT NOT NULL DEFAULT 'petey_desktop',
                    metadata_json TEXT NOT NULL DEFAULT '{}'
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
            columns = {
                row["name"]
                for row in connection.execute("PRAGMA table_info(memory_items)").fetchall()
            }
            if "source_surface" not in columns:
                connection.execute(
                    "ALTER TABLE memory_items ADD COLUMN source_surface TEXT NOT NULL "
                    "DEFAULT 'petey_desktop'"
                )
            if "metadata_json" not in columns:
                connection.execute(
                    "ALTER TABLE memory_items ADD COLUMN metadata_json TEXT NOT NULL DEFAULT '{}'"
                )

    def _insert_item(
        self,
        installation_id: str,
        conversation_id: str | None,
        user_id: str,
        kind: str,
        content: str,
        source_name: str | None = None,
        source_surface: str = "petey_desktop",
        metadata: dict | None = None,
    ) -> int:
        with self._write_lock, self._connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO memory_items(
                    installation_id, conversation_id, user_id, kind, source_name, content,
                    created_at, source_surface, metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(installation_id),
                    str(conversation_id) if conversation_id is not None else None,
                    str(user_id),
                    kind,
                    source_name,
                    content.strip(),
                    dt.datetime.now(dt.timezone.utc).isoformat(),
                    source_surface if source_surface in {
                        "petey_desktop", "mobile_petey", "discord", "petey_life"
                    } else "petey_desktop",
                    json.dumps(metadata or {}, separators=(",", ":")),
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
        self._discard_cached_vectors((item_id,))
        return True

    def _embed_in_background(self, item_id: int, content: str) -> None:
        def work():
            try:
                self._embed_item(item_id, content)
            except Exception as exc:
                print(f"[MEMORY] Local embedding failed for item {item_id}: {exc}")

        _EMBEDDING_EXECUTOR.submit(work)

    def store_memory(
        self, installation_id, conversation_id, user_id, content: str,
        source_surface: str = "petey_desktop",
        metadata: dict | None = None,
    ) -> None:
        item_id = self.store_memory_deferred(
            installation_id, conversation_id, user_id, content,
            source_surface=source_surface, metadata=metadata,
        )
        if item_id is not None:
            self.queue_embedding(item_id, content)

    def store_memory_deferred(
        self, installation_id, conversation_id, user_id, content: str,
        source_surface: str = "petey_desktop",
        metadata: dict | None = None,
    ) -> int | None:
        if not content or not content.strip():
            return None
        return self._insert_item(
            str(installation_id), str(conversation_id), str(user_id), "message", content,
            source_surface=source_surface, metadata=metadata,
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

    def move_conference_messages(self, installation_id: str, session_id: str, sink) -> int:
        """Move legacy Conference events out of shared recall after saving their replies."""
        if not re.fullmatch(r"[a-f0-9]{32}", str(session_id or "")):
            return 0
        with self._write_lock, self._connect() as connection:
            rows = connection.execute(
                """
                SELECT id, user_id, content, metadata_json FROM memory_items
                WHERE installation_id=? AND kind='message' AND metadata_json LIKE ?
                ORDER BY id
                """,
                (str(installation_id), f"%{session_id}%"),
            ).fetchall()
            matched = [
                row for row in rows
                if (metadata := self._metadata(row["metadata_json"]))
                and metadata.get("conference_session_id") == session_id
                and metadata.get("addon_event_source") == "petey-conference"
            ]
            for row in matched:
                if row["user_id"] == "PETEY":
                    sink({"id": int(row["id"]), "message": row["content"]})
            if matched:
                connection.executemany(
                    "DELETE FROM memory_items WHERE id=?",
                    ((int(row["id"]),) for row in matched),
                )
                self._discard_cached_vectors(int(row["id"]) for row in matched)
            return len(matched)

    def delete_conference_messages(self, installation_id: str, session_id: str) -> int:
        """Remove any remaining legacy Conference rows when their session is deleted."""
        return self.move_conference_messages(installation_id, session_id, lambda _item: None)

    def get_conversation_messages(self, installation_id, conversation_id, limit=50) -> list[dict]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT id, user_id, content, created_at, source_surface, metadata_json FROM memory_items
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
                "source_surface": row["source_surface"],
                "metadata": self._metadata(row["metadata_json"]),
            }
            for row in reversed(rows)
        ]

    @staticmethod
    def _metadata(value: str) -> dict:
        try:
            parsed = json.loads(value or "{}")
            return parsed if isinstance(parsed, dict) else {}
        except (json.JSONDecodeError, TypeError):
            return {}

    def _cached_vector(self, item_id: int, encoded: str | None = None) -> tuple[array, float] | None:
        with self._vector_cache_lock:
            cached = self._vector_cache.get(item_id)
            if cached is not None:
                self._vector_cache.move_to_end(item_id)
                return cached
        if encoded is None:
            return None
        # Embeddings are ranking signals, so single precision retains useful cosine
        # accuracy while halving the hot cache's memory footprint.
        vector = array("f", (float(value) for value in json.loads(encoded)))
        norm = math.sqrt(math.sumprod(vector, vector))
        with self._vector_cache_lock:
            self._vector_cache[item_id] = (vector, norm)
            self._vector_cache.move_to_end(item_id)
            while len(self._vector_cache) > MAX_CACHED_VECTORS:
                self._vector_cache.popitem(last=False)
        return vector, norm

    def _vectors_for_rows(
        self, connection: sqlite3.Connection, rows: list[sqlite3.Row]
    ) -> dict[int, tuple[array, float]]:
        vectors = {}
        missing = []
        for row in rows:
            item_id = int(row["id"])
            cached = self._cached_vector(item_id)
            if cached is None:
                missing.append(item_id)
            else:
                vectors[item_id] = cached
        for offset in range(0, len(missing), 500):
            chunk = missing[offset:offset + 500]
            placeholders = ",".join("?" for _ in chunk)
            encoded_rows = connection.execute(
                f"SELECT id, embedding_json FROM memory_items WHERE id IN ({placeholders})",
                chunk,
            ).fetchall()
            for encoded_row in encoded_rows:
                item_id = int(encoded_row["id"])
                cached = self._cached_vector(item_id, str(encoded_row["embedding_json"]))
                if cached is not None:
                    vectors[item_id] = cached
        return vectors

    @staticmethod
    def _semantic_score(
        query: tuple[float, ...], query_norm: float,
        vector_data: tuple[array, float] | None,
    ) -> float:
        if vector_data is None:
            return -1.0
        vector, vector_norm = vector_data
        if len(query) != len(vector) or not query_norm or not vector_norm:
            return -1.0
        return math.sumprod(query, vector) / (query_norm * vector_norm)

    def _discard_cached_vectors(self, item_ids=None) -> None:
        with self._vector_cache_lock:
            if item_ids is None:
                self._vector_cache.clear()
            else:
                for item_id in item_ids:
                    self._vector_cache.pop(int(item_id), None)

    def _direct_timeline(self, installation_id: str, temporal, exclude_contents, query: str) -> str:
        label, start, end = temporal
        with self._connect() as connection:
            surface_filter = "" if "discord" in query.casefold() else "AND source_surface<>'discord'"
            rows = connection.execute(
                f"""
                SELECT content, created_at, source_surface, metadata_json
                FROM memory_items
                WHERE installation_id=? AND kind='message'
                  AND user_id NOT IN ('PETEY', 'SYSTEM_DOC')
                  AND user_id NOT LIKE 'ADDON:%'
                  {surface_filter}
                  AND created_at>=? AND created_at<?
                ORDER BY created_at LIMIT 2000
                """,
                (str(installation_id), start.isoformat(), end.isoformat()),
            ).fetchall()
        excluded = set(exclude_contents)
        rows = [
            row for row in rows
            if len(row["content"].strip()) >= 3
            and row["content"] not in excluded
            and not self._metadata(row["metadata_json"]).get("hidden_from_chat")
        ]
        if not rows:
            return ""
        if len(rows) > 24:
            count = len(rows)
            indices = set(range(6)) | set(range(count - 6, count))
            indices.update(6 + round((count - 13) * index / 11) for index in range(12))
            rows = [rows[index] for index in sorted(indices)]
        lines = [
            f"Time scope: {label}. Direct user statements from that period, oldest first. "
            "A question, plan, or requested story does not prove an event happened."
        ]
        used = len(lines[0]) + 1
        for row in rows:
            try:
                local_time = dt.datetime.fromisoformat(row["created_at"]).astimezone().strftime("%Y-%m-%d %H:%M")
            except ValueError:
                local_time = row["created_at"]
            content = re.sub(r"\s+", " ", row["content"]).strip()[:180]
            entry = f"[User — {local_time} — {row['source_surface']}] {content}"
            if used + len(entry) > MAX_MEMORY_CONTEXT_CHARS:
                break
            lines.append(entry)
            used += len(entry) + 1
        return "\n".join(lines)

    def search_memories(
        self, query: str, installation_id: str, limit=5,
        exclude_conversation_id: str | None = None,
        exclude_contents: list[str] | tuple[str, ...] = (),
        *, include_assistant: bool = False,
    ) -> str:
        if not query or not query.strip():
            return ""
        limit = max(1, min(int(limit), 20))
        excluded_content = [
            value for value in exclude_contents
            if isinstance(value, str) and value
        ][:40]
        temporal = _recall_window(query)
        if temporal and _BROAD_TIME_RECALL.search(query) and not include_assistant:
            return self._direct_timeline(installation_id, temporal, excluded_content, query)
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

        # Keep exact-name and keyword matches in play even when embeddings work.
        # Background indexing can lag, and an embedding alone can overlook an
        # older fact whose wording is more precise than its semantic neighbors.
        terms = list(dict.fromkeys(
            word for word in re.findall(r"[^\W_]+", query.casefold())
            if len(word) > 2 and word not in _SEARCH_STOP_WORDS
        ))[:6]
        candidates: dict[int, sqlite3.Row] = {}
        semantic_scores: dict[int, float] = {}
        with self._connect() as connection:
            conditions = ["installation_id=?"]
            filters: list[object] = [str(installation_id)]
            if not include_assistant:
                conditions.append("user_id<>'PETEY'")
            if exclude_conversation_id is not None:
                conditions.append("(conversation_id IS NULL OR conversation_id<>?)")
                filters.append(str(exclude_conversation_id))
            if excluded_content:
                conditions.append(
                    "content NOT IN (" + ",".join("?" for _ in excluded_content) + ")"
                )
                filters.extend(excluded_content)
            base_where = " AND ".join(conditions)
            columns = (
                "id, user_id, content, created_at, kind, source_name, "
                "source_surface, conversation_id"
            )
            if query_result:
                rows = connection.execute(
                    f"""
                    SELECT {columns}
                    FROM memory_items
                    WHERE {base_where}
                      AND embedding_provider=? AND embedding_model=?
                      AND embedding_dimensions=? AND embedding_json IS NOT NULL
                    ORDER BY id DESC LIMIT 3000
                    """,
                    (*filters, query_result["provider"], query_result["model"],
                     query_result["dimensions"]),
                ).fetchall()
                vectors = self._vectors_for_rows(connection, rows)
                query_vector = tuple(float(value) for value in query_result["values"])
                query_norm = math.sqrt(math.sumprod(query_vector, query_vector))
                scored = heapq.nlargest(
                    max(20, limit * 4),
                    ((self._semantic_score(
                        query_vector, query_norm, vectors.get(int(row["id"]))
                    ), row) for row in rows),
                    key=lambda pair: pair[0],
                )
                for score, row in scored:
                    if score > 0.15:
                        item_id = int(row["id"])
                        candidates[item_id] = row
                        semantic_scores[item_id] = score
            # Search each term separately: a rare name in an old row must not be
            # crowded out by recent rows that mention only a common term.
            for term in terms:
                for row in connection.execute(
                    f"""
                    SELECT {columns}
                    FROM memory_items
                    WHERE {base_where} AND content LIKE ?
                    ORDER BY id DESC LIMIT 100
                    """,
                    (*filters, f"%{term}%"),
                ):
                    candidates[int(row["id"])] = row

        content_terms = {
            item_id: set(re.findall(r"[^\W_]+", row["content"].casefold()))
            for item_id, row in candidates.items()
        }
        term_weights = {
            term: 1.0 + math.log(
                (len(candidates) + 1)
                / (1 + sum(term in words for words in content_terms.values()))
            )
            for term in terms
        }

        def rank(row: sqlite3.Row) -> tuple[float, int]:
            item_id = int(row["id"])
            content = row["content"].casefold()
            content_words = content_terms[item_id]
            lexical = sum(
                term_weights[term] * (
                    1.0 if term in content_words else 0.6 if term in content else 0.0
                )
                for term in terms
            ) / sum(term_weights.values()) if terms else 0.0
            source_bonus = 0.12 if row["kind"] == "document" or row["user_id"] != "PETEY" else 0.0
            return (
                lexical + semantic_scores.get(item_id, 0.0) * 0.55
                + source_bonus,
                item_id,
            )

        ranked = sorted(candidates.values(), key=rank, reverse=True)
        selected = []
        source_counts: dict[str, int] = {}
        for row in ranked:
            source = (
                f"document:{row['source_name']}"
                if row["kind"] == "document" else
                f"conversation:{row['conversation_id']}"
            )
            if source_counts.get(source, 0) >= 3:
                continue
            selected.append(row)
            source_counts[source] = source_counts.get(source, 0) + 1
            if len(selected) >= limit:
                break
        if len(selected) < limit:
            selected_ids = {int(row["id"]) for row in selected}
            selected.extend(
                row for row in ranked
                if int(row["id"]) not in selected_ids
            )
            selected = selected[:limit]

        # Present facts chronologically so a later direct correction has the final
        # word while older text remains available as an audit trail.
        selected = sorted(selected, key=lambda row: int(row["id"]))
        surface_labels = {
            "petey_desktop": "Petey Desktop",
            "mobile_petey": "Mobile Petey",
            "discord": "Discord",
            "petey_life": "Petey Life",
        }
        lines = []
        for row in selected:
            try:
                timestamp = dt.datetime.fromisoformat(row["created_at"]).strftime("%Y-%m-%d %H:%M")
            except ValueError:
                timestamp = row["created_at"]
            label = (
                f"[📄 {row['source_name']} — {timestamp}]"
                if row["kind"] == "document"
                else (
                    f"[{surface_labels.get(row['source_surface'], 'Petey Desktop')} — "
                    f"{'Petey' if row['user_id'] == 'PETEY' else 'User'} — {timestamp}]"
                )
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
