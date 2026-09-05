import tempfile
import unittest
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

    def test_keyword_memory_works_when_semantic_embeddings_are_disabled(self):
        with tempfile.TemporaryDirectory() as directory:
            store = DesktopMemory(Path(directory) / "memory.sqlite3", lambda _text: None)
            store.init_db()
            store._insert_item("desktop-1", "main", "owner", "message", "The launch code is persimmon")

            self.assertIn("persimmon", store.search_memories("launch code", "desktop-1", 5))

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
