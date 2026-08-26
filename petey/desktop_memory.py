"""Universal local memory store for Petey's standalone desktop runtime."""

from __future__ import annotations

import datetime as dt
import json
import math
import sqlite3
import threading
from pathlib import Path
from typing import Callable


EmbeddingFactory = Callable[[str], dict | None]


class DesktopMemory:
    """SQLite-backed messages, documents, metrics, and dimension-agnostic vectors."""

    def __init__(self, path: str | Path, embedding_factory: EmbeddingFactory):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.embedding_factory = embedding_factory
        self._write_lock = threading.RLock()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=30)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA foreign_keys=ON")
        return connection

    def init_db(self) -> None:
        with self._connect() as connection:
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

        threading.Thread(target=work, name=f"petey-embed-{item_id}", daemon=True).start()

    def store_memory(self, installation_id, conversation_id, user_id, content: str) -> None:
        if not content or not content.strip():
            return
        item_id = self._insert_item(
            str(installation_id), str(conversation_id), str(user_id), "message", content
        )
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

        threading.Thread(target=work, name="petey-document-index", daemon=True).start()

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
        return True

    def clear_conversation(self, installation_id: str, conversation_id: str) -> int:
        with self._write_lock, self._connect() as connection:
            cursor = connection.execute(
                "DELETE FROM memory_items WHERE installation_id=? AND kind='message' AND conversation_id=?",
                (str(installation_id), str(conversation_id)),
            )
            return max(0, int(cursor.rowcount or 0))

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

    def search_memories(self, query: str, installation_id: str, limit=5) -> str:
        if not query or not query.strip():
            return ""
        try:
            query_result = self.embedding_factory(query)
        except Exception as exc:
            print(f"[MEMORY] Query embedding unavailable; using text search: {exc}")
            query_result = None

        with self._connect() as connection:
            if query_result:
                rows = connection.execute(
                    """
                    SELECT content, created_at, kind, source_name, embedding_json
                    FROM memory_items
                    WHERE installation_id=? AND embedding_provider=? AND embedding_model=?
                      AND embedding_dimensions=? AND embedding_json IS NOT NULL
                    ORDER BY id DESC LIMIT 3000
                    """,
                    (
                        str(installation_id),
                        query_result["provider"],
                        query_result["model"],
                        query_result["dimensions"],
                    ),
                ).fetchall()
                scored = sorted(
                    (
                        (self._cosine(query_result["values"], json.loads(row["embedding_json"])), row)
                        for row in rows
                    ),
                    key=lambda pair: pair[0],
                    reverse=True,
                )[: int(limit)]
                selected = [row for score, row in scored if score > 0.15]
            else:
                words = [word for word in query.strip().split() if len(word) > 2][:5]
                if not words:
                    return ""
                clauses = " OR ".join("content LIKE ?" for _ in words)
                selected = connection.execute(
                    f"""
                    SELECT content, created_at, kind, source_name FROM memory_items
                    WHERE installation_id=? AND ({clauses}) ORDER BY id DESC LIMIT ?
                    """,
                    (str(installation_id), *(f"%{word}%" for word in words), int(limit)),
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

        def work():
            for row in rows:
                try:
                    self._embed_item(int(row["id"]), row["content"])
                except Exception as exc:
                    print(f"[MEMORY] Rebuild stopped at item {row['id']}: {exc}")
                    break

        threading.Thread(target=work, name="petey-memory-rebuild", daemon=True).start()
        return len(rows)

    def reset(self, installation_id: str) -> int:
        with self._write_lock, self._connect() as connection:
            cursor = connection.execute(
                "DELETE FROM memory_items WHERE installation_id=?", (str(installation_id),)
            )
            connection.execute(
                "DELETE FROM image_generations WHERE installation_id=?", (str(installation_id),)
            )
            return max(0, int(cursor.rowcount or 0))
