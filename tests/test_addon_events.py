import time
import unittest

from petey.addon_events import AddonEventBroker, AddonEventError


class AddonEventBrokerTests(unittest.TestCase):
    def test_hidden_event_is_processed_and_published_once(self):
        received = []

        def handle(event):
            received.append(event)
            return {"text": "Now playing Kind of Blue.", "tool_events": []}

        broker = AddonEventBroker(handle)
        self.addCleanup(broker.close)
        result = broker.emit(
            "spotify", "Track changed", conversation_id="main", speak=True
        )
        duplicate = broker.emit(
            "spotify", "Track changed", conversation_id="main", speak=True
        )
        self.assertEqual(result["status"], "queued")
        self.assertEqual(duplicate["status"], "duplicate_ignored")
        deadline = time.time() + 1
        payload = {"events": []}
        while time.time() < deadline and not payload["events"]:
            time.sleep(0.01)
            payload = broker.events_after(0)
        self.assertEqual(len(received), 1)
        self.assertEqual(payload["events"][0]["text"], "Now playing Kind of Blue.")
        self.assertTrue(payload["events"][0]["speak"])

    def test_invalid_event_is_rejected(self):
        broker = AddonEventBroker(lambda _event: {"text": "unused"})
        self.addCleanup(broker.close)
        with self.assertRaises(AddonEventError):
            broker.emit("spotify", "", conversation_id="main")


if __name__ == "__main__":
    unittest.main()
