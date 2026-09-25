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
            "spotify", "Track changed", conversation_id="main", speak=True,
            metadata={"chat_image_url": "https://i.scdn.co/image/example"},
            user_initiated=True,
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
        self.assertTrue(received[0]["user_initiated"])
        self.assertEqual(payload["events"][0]["text"], "Now playing Kind of Blue.")
        self.assertEqual(payload["events"][0]["surface"], "petey_desktop")
        self.assertTrue(payload["events"][0]["speak"])
        self.assertEqual(
            payload["events"][0]["metadata"]["chat_image_url"],
            "https://i.scdn.co/image/example",
        )

    def test_same_event_on_different_surfaces_is_not_deduplicated(self):
        broker = AddonEventBroker(lambda event: {"text": event["surface"]})
        self.addCleanup(broker.close)
        desktop = broker.emit(
            "quick-actions", "Status", conversation_id="main", surface="petey_desktop"
        )
        mobile = broker.emit(
            "quick-actions", "Status", conversation_id="main", surface="mobile_petey"
        )
        self.assertEqual(desktop["status"], "queued")
        self.assertEqual(mobile["status"], "queued")
        deadline = time.time() + 1
        payload = {"events": []}
        while time.time() < deadline and len(payload["events"]) < 2:
            time.sleep(0.01)
            payload = broker.events_after(0)
        self.assertEqual(
            [event["surface"] for event in payload["events"]],
            ["petey_desktop", "mobile_petey"],
        )

    def test_invalid_event_is_rejected(self):
        broker = AddonEventBroker(lambda _event: {"text": "unused"})
        self.addCleanup(broker.close)
        with self.assertRaises(AddonEventError):
            broker.emit("spotify", "", conversation_id="main")


if __name__ == "__main__":
    unittest.main()
