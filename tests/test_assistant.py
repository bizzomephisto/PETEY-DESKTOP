import unittest
from unittest.mock import MagicMock, patch

from petey.assistant import (
    AssistantAttachment,
    AssistantIdentity,
    AssistantService,
    PETEY_USER_ID,
)


class AssistantServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_stream_preserves_temporary_mode_and_stores_only_final_reply(self):
        for temporary in (False, True):
            memory = MagicMock()
            memory.get_conversation_messages.return_value = []
            memory.search_memories.return_value = ""
            service = AssistantService("System", memory=memory)
            received = []
            def stream(prompt, system, history, on_text):
                on_text("Hello ")
                on_text("world")
                return "Hello world"
            with patch("petey.assistant.AIProvider.complete_stream", side_effect=stream):
                reply = await service.respond("Hi", AssistantIdentity("test", "chat", "user"),
                                              temporary=temporary, on_text=received.append)
            self.assertEqual(received, ["Hello ", "world"])
            self.assertEqual(reply.text, "Hello world")
            if temporary:
                memory.store_memory.assert_not_called()
                memory.search_memories.assert_not_called()
                memory.get_conversation_messages.assert_not_called()
            else:
                self.assertEqual(memory.store_memory.call_count, 2)
                self.assertEqual(memory.store_memory.call_args.args[-1], "Hello world")

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

    async def test_explicit_request_uses_registered_model_tools(self):
        registry = MagicMock()
        registry.schemas_for.return_value = [{"type": "function", "function": {"name": "generate_image"}}]
        service = AssistantService("You are Petey.", tool_registry=registry)
        identity = AssistantIdentity("desktop-test", "main", "owner")
        event = {"name": "generate_image", "result": {"status": "queued"}}
        with patch(
            "petey.assistant.AIProvider.complete_with_tools",
            return_value=("Queued your image.", [event]),
        ) as complete:
            reply = await service.respond("Generate an image of a moon base", identity)

        self.assertEqual(reply.text, "Queued your image.")
        self.assertEqual(reply.tool_events, (event,))
        self.assertEqual(complete.call_args.args[3], registry.schemas_for.return_value)
        complete.call_args.args[4]("generate_image", {"prompt": "moon base"})
        registry.execute.assert_called_once_with(
            "generate_image", {"prompt": "moon base"}, "Generate an image of a moon base"
        )

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

    async def test_image_attachment_is_inspected_by_configured_gemini_vision(self):
        service = AssistantService("You are Petey.")
        identity = AssistantIdentity("desktop-test", "main", "owner", "Pat")
        attachment = AssistantAttachment("robot.png", "image/png", b"image-data")
        with (
            patch(
                "petey.assistant.AIProvider.describe_image",
                return_value="A small green robot on a desk.",
            ) as vision,
            patch("petey.assistant.AIProvider.complete", return_value="I see a robot.") as llm,
        ):
            reply = await service.respond("What is in this image?", identity, attachment)

        self.assertEqual(reply.text, "I see a robot.")
        vision.assert_called_once_with(
            b"image-data", "image/png", "What is in this image?"
        )
        self.assertIn("A small green robot on a desk.", llm.call_args.args[0])

    def test_model_and_legacy_gif_tokens_are_removed(self):
        cleaned = AssistantService._clean_model_response(
            "Hi <|junk|> there [GIF: happy robot]"
        )
        self.assertEqual(cleaned, "Hi  there")


if __name__ == "__main__":
    unittest.main()
