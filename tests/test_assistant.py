import unittest
from unittest.mock import MagicMock, patch

from petey.assistant import AssistantIdentity, AssistantService, PETEY_USER_ID


class AssistantServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_response_uses_history_and_stores_both_speakers(self):
        stored = []

        def store_memory(server_id, channel_id, user_id, content):
            stored.append((server_id, channel_id, user_id, content))

        identity = AssistantIdentity("desktop-test", "main", "owner", "Pat")
        history = [
            {
                "id": 1,
                "user_id": "owner",
                "message": "Earlier message",
                "timestamp": "2026-01-01T00:00:00",
            },
            {
                "id": 2,
                "user_id": PETEY_USER_ID,
                "message": "Earlier answer",
                "timestamp": "2026-01-01T00:00:01",
            },
        ]

        memory = MagicMock()
        memory.get_conversation_messages.return_value = history
        memory.search_memories.return_value = "Remembered fact"
        memory.store_memory.side_effect = store_memory
        service = AssistantService("You are Petey.", memory=memory)

        with (
            patch("petey.assistant.AIProvider.complete", return_value="Hello from desktop") as llm,
        ):
            reply = await service.respond("Hello", identity)

        self.assertEqual(reply.text, "Hello from desktop")
        self.assertEqual(stored[0], ("desktop-test", "main", "owner", "Hello"))
        self.assertEqual(stored[1], ("desktop-test", "main", PETEY_USER_ID, "Hello from desktop"))
        self.assertEqual(llm.call_args.args[2][0]["content"], "User Pat said: Earlier message")
        self.assertEqual(llm.call_args.args[2][1]["role"], "assistant")

    async def test_empty_message_is_rejected(self):
        service = AssistantService("You are Petey.")
        identity = AssistantIdentity("desktop-test", "main", "owner")
        with self.assertRaises(ValueError):
            await service.respond("   ", identity)

    async def test_temporary_response_uses_ephemeral_history_without_database_access(self):
        service = AssistantService("You are Petey.")
        identity = AssistantIdentity("desktop-test", "main", "owner", "Pat")
        temporary_history = [{"role": "user", "content": "My temporary fact is blue."}]
        with (
            patch("petey.assistant.AIProvider.complete", return_value="Got it") as llm,
        ):
            reply = await service.respond(
                "What color?", identity, temporary=True, temporary_history=temporary_history
            )

        self.assertEqual(reply.text, "Got it")
        self.assertEqual(llm.call_args.args[2], temporary_history)

    def test_model_tokens_and_gif_directive_are_removed(self):
        cleaned = AssistantService._clean_model_response("Hi <|junk|> there")
        query, text = AssistantService._extract_gif(cleaned + " [GIF: happy robot]")
        self.assertEqual(cleaned, "Hi  there")
        self.assertEqual(query, "happy robot")
        self.assertEqual(text, "Hi  there")


if __name__ == "__main__":
    unittest.main()
