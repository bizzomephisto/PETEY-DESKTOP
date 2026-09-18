import random
import unittest
from unittest.mock import Mock

from petey.room_chat import RoomActivity, RoomConversation, RoomMessage, Turn


class RoomActivityTests(unittest.TestCase):
    def setUp(self):
        self.room = RoomActivity("PETEY", 0, random.Random(1))

    def add(self, count, now, text="Hello everyone"):
        for i in range(count):
            self.room.observe(RoomMessage(f"{now}-{i}", f"Guest{i}", text), now)

    def test_quiet_room_waits_an_hour_and_does_not_repeat_each_tick(self):
        self.assertIsNone(self.room.next_turn(3599))
        self.assertEqual(self.room.next_turn(4200).reason, "quiet_invitation")
        self.assertIsNone(self.room.next_turn(4201))
        self.room.finish(4202, sent=True)
        self.assertIsNone(self.room.next_turn(7801))
        self.assertEqual(self.room.next_turn(8402).reason, "quiet_invitation")

    def test_new_human_activity_resets_quiet_clock(self):
        self.add(1, 3500)
        self.assertIsNone(self.room.next_turn(4200))
        self.assertIsNone(self.room.next_turn(7099))
        self.assertEqual(self.room.next_turn(7700).reason, "quiet_invitation")

    def test_joins_group_without_requiring_a_mention(self):
        self.add(2, 60)
        self.assertIsNone(self.room.next_turn(61))
        self.add(1, 62)
        self.assertEqual(self.room.next_turn(63).reason, "join_conversation")
        self.room.finish(64, sent=True)
        self.assertIsNone(self.room.next_turn(200))

    def test_mention_receives_reply_but_does_not_bypass_cooldown(self):
        self.add(1, 60, "PETEY, your turn!")
        self.assertEqual(self.room.next_turn(60).reason, "reply")
        self.room.finish(61, sent=True)
        self.add(1, 62, "petey?")
        self.assertIsNone(self.room.next_turn(63))
        self.assertEqual(self.room.next_turn(90).reason, "reply")

    def test_direct_message_bypasses_initial_listening_period(self):
        self.room.observe(RoomMessage("direct", "Guest", "A question", addressed=True), 2)
        self.assertIsNone(self.room.next_turn(2))
        self.assertEqual(self.room.next_turn(5).reason, "reply")

    def test_pacing_modes_change_direct_delay_and_message_ceiling(self):
        fast = RoomActivity("PETEY", 0, random.Random(1), pace="fast")
        fast.observe(RoomMessage("1", "Guest", "Question", addressed=True), 1)
        self.assertEqual(fast.next_turn(2).reason, "reply")
        relaxed = RoomActivity("PETEY", 0, random.Random(1), pace="relaxed")
        relaxed.observe(RoomMessage("1", "Guest", "Question", addressed=True), 1)
        self.assertIsNone(relaxed.next_turn(5))
        self.assertEqual(relaxed.next_turn(13).reason, "reply")

    def test_own_messages_and_duplicate_snapshots_do_not_drive_activity(self):
        own = RoomMessage("own", "petey", "Hello!")
        human = RoomMessage("human", "Guest", "Hi")
        self.assertFalse(self.room.observe(own, 60))
        self.assertTrue(self.room.observe(human, 60))
        self.assertFalse(self.room.observe(human, 61))
        self.assertEqual(len(self.room.pending), 1)
        self.assertIsNone(self.room.next_turn(100))

    def test_busy_room_has_hard_limit_even_with_direct_mentions(self):
        for now in range(60, 240, 30):
            self.add(1, now, "PETEY?")
            self.assertIsNotNone(self.room.next_turn(now))
            self.room.finish(now, sent=True)
        self.add(1, 240, "PETEY?")
        self.assertIsNone(self.room.next_turn(240))
        self.assertIsNotNone(self.room.next_turn(360))

    def test_priority_can_bypass_ceiling_for_discord(self):
        room = RoomActivity(
            "PETEY", 0, random.Random(1), pace="relaxed",
            priority_bypasses_ceiling=True,
        )
        for now in (60, 120, 180):
            room.observe(RoomMessage(str(now), "Guest", "PETEY?", addressed=True), now)
            self.assertIsNotNone(room.next_turn(now))
            room.finish(now, sent=True)
        room.observe(RoomMessage("final", "Guest", "linux", addressed=True), 240)
        self.assertEqual(room.next_turn(240).reason, "reply")

    def test_priority_delay_can_ignore_slow_spontaneous_pace(self):
        room = RoomActivity(
            "PETEY", 0, random.Random(1), pace="relaxed",
            priority_delay_cap=2,
        )
        room.observe(RoomMessage("1", "Guest", "linux", addressed=True), 1)
        self.assertIsNone(room.next_turn(1))
        self.assertEqual(room.next_turn(2).reason, "reply")

    def test_next_message_from_person_petey_answered_is_a_followup(self):
        room = RoomActivity(
            "PETEY", 0, random.Random(1), priority_delay_cap=2,
            priority_bypasses_ceiling=True,
        )
        room.observe(RoomMessage("1", "Me", "Hey PETEY, how's it going?"), 10)
        self.assertEqual(room.next_turn(10).reason, "reply")
        room.finish(11, sent=True)

        room.observe(RoomMessage("2", "Me", "Awesome, I'm doing great too!"), 20)
        self.assertTrue(room.pending[-1].addressed)
        self.assertEqual(room.next_turn(20).reason, "reply")

    def test_followup_window_is_person_specific_and_expires(self):
        room = RoomActivity("PETEY", 0, random.Random(1), followup_window=30)
        room.observe(RoomMessage("1", "Alice", "PETEY?"), 10)
        room.next_turn(10)
        room.finish(11, sent=True)
        room.observe(RoomMessage("2", "Bob", "Separate conversation"), 20)
        room.observe(RoomMessage("3", "Alice", "Much later"), 42)
        self.assertFalse(room.pending[0].addressed)
        self.assertFalse(room.pending[1].addressed)

    def test_pass_or_failure_consumes_turn_and_backs_off(self):
        self.add(3, 60)
        self.assertIsNotNone(self.room.next_turn(60))
        self.room.finish(65, sent=False)
        self.assertIsNone(self.room.next_turn(200))
        self.assertFalse(self.room.sent)

    def test_game_offers_are_occasional(self):
        self.add(3, 1200)
        self.assertEqual(self.room.next_turn(1200).reason, "optional_game_invitation")
        self.room.finish(1201, sent=True)
        self.add(3, 1300)
        self.assertEqual(self.room.next_turn(1300).reason, "join_conversation")

    def test_messages_arriving_during_generation_are_not_lost(self):
        self.add(3, 60)
        self.room.next_turn(60)
        self.add(1, 65, "PETEY, also this")
        self.room.finish(70, sent=True)
        turn = self.room.next_turn(100)
        self.assertEqual(len(turn.messages), 1)
        self.assertEqual(turn.messages[0].text, "PETEY, also this")


class RoomConversationTests(unittest.TestCase):
    def test_room_context_is_separate_and_delivery_is_acknowledged(self):
        provider = Mock()
        provider.complete.return_value = "Anyone up for made-up trivia?"
        room = RoomConversation(provider)
        turn = Turn("quiet_invitation", ())
        text = room.reply(turn)
        self.assertEqual(provider.complete.call_args.args[2], [])
        self.assertNotIn("assistant", [m["role"] for m in room.history])
        room.delivered(text)
        self.assertEqual(room.history[-1], {"role": "assistant", "content": text})

    def test_custom_room_prompt_replaces_default_behavior_prompt(self):
        provider = Mock()
        provider.complete.return_value = "Hello"
        RoomConversation(provider, "Persona", "Custom Discord behavior").reply(
            Turn("reply", ())
        )
        system = provider.complete.call_args.args[1]
        self.assertIn("Custom Discord behavior", system)
        self.assertNotIn("friendly AI participant", system)

    def test_pass_commands_and_empty_output_are_not_sent(self):
        provider = Mock()
        room = RoomConversation(provider)
        for response in (
            "[PASS]", "[Pass]", "pass", "(pass).", "**[PASS]**",
            "[ASSISTANT]", "[Assistant]", "Assistant:", "**[ASSISTANT]**",
            "[", "[A", "[ASSI", "<pas", "...", "()",
            " /quit ", "m Guest private message", "", None,
        ):
            provider.complete.return_value = response
            self.assertEqual(room.reply(Turn("reply", ())), "")
        provider.complete.return_value = "I'll pass this time."
        self.assertEqual(room.reply(Turn("reply", ())), "I'll pass this time.")
        provider.complete.return_value = "Assistant tools can help with that."
        self.assertEqual(
            room.reply(Turn("reply", ())), "Assistant tools can help with that."
        )
        provider.complete.return_value = "🙂"
        self.assertEqual(room.reply(Turn("reply", ())), "🙂")
        provider.complete.return_value = "[that was unexpected]"
        self.assertEqual(room.reply(Turn("reply", ())), "[that was unexpected]")

    def test_public_output_is_one_bounded_line(self):
        provider = Mock()
        provider.complete.return_value = "Funny answer\n" * 100
        text = RoomConversation(provider).reply(Turn("reply", ()))
        self.assertLessEqual(len(text), 280)
        self.assertNotIn("\n", text)

    def test_reply_prompt_prioritizes_latest_addressed_message(self):
        provider = Mock()
        provider.complete.return_value = "The latest answer"
        room = RoomConversation(provider)
        room.reply(Turn("reply", (
            RoomMessage("1", "Guest", "First question", addressed=True),
            RoomMessage("2", "Guest", "Actually, second question", addressed=True),
        )))
        self.assertIn("prioritize the last relevant line", provider.complete.call_args.args[0])
        self.assertIn("likely same-speaker follow-up", provider.complete.call_args.args[0])


if __name__ == "__main__":
    unittest.main()
