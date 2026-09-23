import tempfile
import unittest
import sqlite3
from pathlib import Path
from unittest.mock import patch

from petey.desktop_memory import DesktopMemory


def embedding(text):
    lowered = text.lower()
    return {
        "values": [float("robot" in lowered), float("garden" in lowered), 1.0],
        "provider": "local",
        "model": "test-embed",
        "dimensions": 3,
    }


class DesktopMemoryTests(unittest.TestCase):
    def test_existing_database_is_migrated_with_desktop_surface_default(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "memory.sqlite3"
            with sqlite3.connect(path) as connection:
                connection.execute("""
                    CREATE TABLE memory_items (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        installation_id TEXT NOT NULL, conversation_id TEXT,
                        user_id TEXT NOT NULL, kind TEXT NOT NULL,
                        source_name TEXT, content TEXT NOT NULL, created_at TEXT NOT NULL,
                        embedding_json TEXT, embedding_provider TEXT,
                        embedding_model TEXT, embedding_dimensions INTEGER
                    )
                """)
            store = DesktopMemory(path, lambda _text: None)
            store.init_db()
            store.store_memory("desktop-1", "main", "owner", "Migrated message")

            self.assertEqual(
                store.get_conversation_messages("desktop-1", "main")[0]["source_surface"],
                "petey_desktop",
            )

    def test_dimension_agnostic_vectors_and_raw_messages_live_in_sqlite(self):
        with tempfile.TemporaryDirectory() as directory:
            store = DesktopMemory(Path(directory) / "memory.sqlite3", embedding)
            store.init_db()
            first = store._insert_item("desktop-1", "main", "owner", "message", "My robot is blue")
            second = store._insert_item("desktop-1", "other", "owner", "message", "The garden is green")
            store._embed_item(first, "My robot is blue")
            store._embed_item(second, "The garden is green")

            result = store.search_memories("robot details", "desktop-1", 1)
            history = store.get_conversation_messages("desktop-1", "main", 10)

            self.assertIn("robot is blue", result)
            self.assertEqual(history[0]["message"], "My robot is blue")
            self.assertEqual(store.get_memory_stats("desktop-1", "main")["embedded_memories"], 2)

    def test_message_metadata_survives_reload(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "memory.sqlite3"
            store = DesktopMemory(path, lambda _text: None)
            store.init_db()
            store.store_memory(
                "desktop-1", "main", "PETEY", "Image queued",
                metadata={"tool_events": [{"name": "generate_image", "result": {"job_id": "job-1"}}]},
            )
            reloaded = DesktopMemory(path, lambda _text: None)
            reloaded.init_db()
            metadata = reloaded.get_conversation_messages("desktop-1", "main")[0]["metadata"]
            self.assertEqual(metadata["tool_events"][0]["result"]["job_id"], "job-1")

    def test_keyword_memory_works_when_semantic_embeddings_are_disabled(self):
        with tempfile.TemporaryDirectory() as directory:
            store = DesktopMemory(Path(directory) / "memory.sqlite3", lambda _text: None)
            store.init_db()
            store._insert_item("desktop-1", "main", "owner", "message", "The launch code is persimmon")

            self.assertIn("persimmon", store.search_memories("launch code", "desktop-1", 5))

    def test_retrieval_labels_surfaces_and_orders_corrections_oldest_to_newest(self):
        with tempfile.TemporaryDirectory() as directory:
            store = DesktopMemory(Path(directory) / "memory.sqlite3", lambda _text: None)
            store.init_db()
            store.store_memory(
                "desktop-1", "old", "owner", "My favorite color is blue",
                source_surface="petey_desktop",
            )
            store.store_memory(
                "desktop-1", "new", "owner", "Correction: my favorite color is green",
                source_surface="mobile_petey",
            )

            result = store.search_memories("favorite color", "desktop-1", 5)

            self.assertIn("[Petey Desktop", result)
            self.assertIn("[Mobile Petey", result)
            self.assertLess(result.index("blue"), result.index("green"))

    def test_empty_memory_skips_remote_embedding_work(self):
        with tempfile.TemporaryDirectory() as directory:
            calls = []
            store = DesktopMemory(
                Path(directory) / "memory.sqlite3", lambda text: calls.append(text)
            )
            store.init_db()

            self.assertEqual(store.search_memories("anything", "desktop-1"), "")
            self.assertEqual(calls, [])

    def test_repeated_semantic_search_reuses_decoded_vectors(self):
        with tempfile.TemporaryDirectory() as directory:
            store = DesktopMemory(Path(directory) / "memory.sqlite3", embedding)
            store.init_db()
            item_id = store._insert_item(
                "desktop-1", "main", "owner", "message", "My robot is blue"
            )
            store._embed_item(item_id, "My robot is blue")

            with patch("petey.desktop_memory.json.loads", wraps=__import__("json").loads) as loads:
                store.search_memories("robot", "desktop-1", 1)
                first_count = loads.call_count
                store.search_memories("robot", "desktop-1", 1)

            self.assertEqual(first_count, 1)
            self.assertEqual(loads.call_count, first_count)

    def test_reembedding_invalidates_the_compact_vector_cache(self):
        with tempfile.TemporaryDirectory() as directory:
            first = {
                "provider": "test", "model": "tiny", "dimensions": 2,
                "values": [1.0, 0.0],
            }
            second = {**first, "values": [0.0, 1.0]}
            store = DesktopMemory(Path(directory) / "memory.sqlite3", lambda _text: first)
            store.init_db()
            item_id = store._insert_item(
                "desktop-1", "main", "owner", "message", "Cache changes"
            )
            store._embed_item(item_id, "Cache changes")
            self.assertIn("Cache changes", store.search_memories("query", "desktop-1", 1))
            self.assertEqual(store._vector_cache[item_id][0].typecode, "f")

            store.embedding_factory = lambda _text: second
            store._embed_item(item_id, "Cache changes")

            self.assertIn("Cache changes", store.search_memories("query", "desktop-1", 1))
            self.assertEqual(list(store._vector_cache[item_id][0]), [0.0, 1.0])

    def test_retrieval_can_exclude_messages_already_in_current_chat_history(self):
        with tempfile.TemporaryDirectory() as directory:
            store = DesktopMemory(Path(directory) / "memory.sqlite3", embedding)
            store.init_db()
            current = store._insert_item(
                "desktop-1", "current", "owner", "message", "Current robot detail"
            )
            other = store._insert_item(
                "desktop-1", "other", "owner", "message", "Older robot detail"
            )
            store._embed_item(current, "Current robot detail")
            store._embed_item(other, "Older robot detail")

            result = store.search_memories(
                "robot", "desktop-1", 5, exclude_conversation_id="current"
            )

            self.assertNotIn("Current robot detail", result)
            self.assertIn("Older robot detail", result)

    def test_retrieval_can_exclude_exact_current_turn_content(self):
        with tempfile.TemporaryDirectory() as directory:
            store = DesktopMemory(Path(directory) / "memory.sqlite3", lambda _text: None)
            store.init_db()
            store.store_memory_deferred(
                "desktop-1", "discord:room", "discord:Guest",
                "Guest: the porch light is blue", source_surface="discord",
            )
            store.store_memory_deferred(
                "desktop-1", "discord:room", "discord:Guest",
                "Guest: the older porch code is seven", source_surface="discord",
            )

            result = store.search_memories(
                "porch", "desktop-1", limit=5,
                exclude_contents=("Guest: the porch light is blue",),
            )

            self.assertNotIn("light is blue", result)
            self.assertIn("older porch code is seven", result)

    def test_reset_is_scoped_to_one_installation(self):
        with tempfile.TemporaryDirectory() as directory:
            store = DesktopMemory(Path(directory) / "memory.sqlite3", lambda _text: None)
            store.init_db()
            store._insert_item("desktop-1", "main", "owner", "message", "Delete me")
            store._insert_item("desktop-2", "main", "owner", "message", "Keep me")

            self.assertEqual(store.reset("desktop-1"), 1)
            self.assertEqual(store.get_conversation_messages("desktop-1", "main"), [])
            self.assertEqual(len(store.get_conversation_messages("desktop-2", "main")), 1)


if __name__ == "__main__":
    unittest.main()
