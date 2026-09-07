import json
import base64
import unittest
from unittest.mock import MagicMock, patch

import requests

from petey.ai_provider import AIProvider, AIProviderError


class AIProviderTests(unittest.TestCase):
    def test_gemini_vision_follows_chat_even_with_older_saved_vision(self):
        provider = AIProvider({"provider": "gemini", "gemini": {
            "model": "gemini-new-flash", "vision_model": "gemini-2.5-flash", "api_key": "test",
        }})
        response = MagicMock()
        response.json.return_value = {"candidates": [{"content": {"parts": [{"text": "A cat"}]}}]}
        with patch("petey.ai_provider.HTTP_SESSION.post", return_value=response) as post:
            self.assertEqual(provider.describe_image(b"image", "image/png"), "A cat")
        self.assertIn("/gemini-new-flash:generateContent", post.call_args.args[0])
        self.assertEqual(provider.public_config()["vision_model"], "gemini-new-flash")

    def test_streaming_providers_deliver_deltas_before_completion(self):
        for name in ("gemini", "openai", "local"):
            received = []
            response = MagicMock()
            def lines(**kwargs):
                if name == "gemini":
                    yield b'data: {"candidates":[{"content":{"parts":[{"text":"private","thought":true},{"text":"Hello "}]}}]}'
                else:
                    yield b'data: {"choices":[{"delta":{"content":"Hello "}}]}'
                yield b''
                self.assertEqual(received, ["Hello "])
                if name == "gemini":
                    yield b'data: {"candidates":[{"content":{"parts":[{"text":"world"}]},"finishReason":"STOP"}]}'
                else:
                    yield b'data: {"choices":[{"delta":{"content":"world"},"finish_reason":"stop"}]}'
                yield b''
            response.iter_lines.side_effect = lines
            provider = AIProvider({"provider": name, name: {"api_key": "test", "model": "test-model"}})
            with patch("petey.ai_provider.HTTP_SESSION.post", return_value=response) as post:
                self.assertEqual(provider.complete_stream("Hi", "System", [], received.append), "Hello world")
            self.assertTrue(post.call_args.kwargs["stream"])
            response.close.assert_called_once()

    def test_truncated_stream_fails_and_closes_response(self):
        response = MagicMock()
        response.iter_lines.return_value = [b'data: {"choices":[{"delta":{"content":"Partial"}}]}', b'']
        received = []
        with self.assertRaisesRegex(AIProviderError, "ended early"):
            AIProvider._stream_text(response, False, received.append)
        self.assertEqual(received, ["Partial"])
        response.close.assert_called_once()

    def test_stream_accepts_final_event_without_trailing_blank_line(self):
        response = MagicMock()
        response.iter_lines.return_value = [
            b'data: {"choices":[{"delta":{"content":"Complete"},"finish_reason":"stop"}]}'
        ]
        received = []

        self.assertEqual(AIProvider._stream_text(response, False, received.append), "Complete")
        self.assertEqual(received, ["Complete"])
        response.close.assert_called_once()

    def test_stream_interruption_retries_once_with_buffered_completion(self):
        provider = AIProvider({"provider": "gemini"})
        received = []
        with (
            patch.object(provider, "_gemini", side_effect=[AIProviderError("interrupted"), "Recovered"])
            as gemini,
        ):
            result = provider.complete_stream("Hi", "System", [], received.append)

        self.assertEqual(result, "Recovered")
        self.assertEqual(received, ["Recovered"])
        self.assertEqual(gemini.call_count, 2)
        self.assertIsNotNone(gemini.call_args_list[0].args[3])
        self.assertEqual(len(gemini.call_args_list[1].args), 3)

    def test_gemini_model_catalog_paginates_and_filters_specialized_models(self):
        first = MagicMock()
        first.json.return_value = {"models": [
            {"name": "models/gemini-new-flash", "supportedGenerationMethods": ["generateContent"]},
            {"name": "models/gemini-embedding", "supportedGenerationMethods": ["embedContent"]},
            {"name": "models/gemini-preview-tts", "supportedGenerationMethods": ["generateContent"]},
            {"name": "models/gemini-image", "supportedGenerationMethods": ["generateContent"]},
        ], "nextPageToken": "next"}
        second = MagicMock()
        second.json.return_value = {"models": [
            {"name": "models/gemini-new-pro", "supportedGenerationMethods": ["generateContent"]},
            {"name": "models/gemini-new-flash", "supportedGenerationMethods": ["generateContent"]},
        ]}
        provider = AIProvider({"provider": "gemini", "gemini": {"api_key": "test-key"}})
        with patch("petey.ai_provider.HTTP_SESSION.get", side_effect=[first, second]) as get:
            self.assertEqual(provider.list_models(), ["gemini-new-flash", "gemini-new-pro"])
        self.assertEqual(get.call_args.kwargs["params"]["pageToken"], "next")
        self.assertEqual(get.call_args.kwargs["headers"], {"x-goog-api-key": "test-key"})
        self.assertNotIn("test-key", get.call_args.args[0])

    def test_gemini_catalog_requires_key_and_hides_transport_secrets(self):
        provider = AIProvider({"provider": "gemini"})
        with patch.dict("os.environ", {}, clear=True), patch("petey.ai_provider.HTTP_SESSION.get") as get:
            with self.assertRaisesRegex(AIProviderError, "API key"):
                provider.list_models()
            get.assert_not_called()
        provider = AIProvider({"provider": "gemini", "gemini": {"api_key": "secret"}})
        with patch("petey.ai_provider.HTTP_SESSION.get", side_effect=requests.Timeout("secret")):
            with self.assertRaises(AIProviderError) as error:
                provider.list_models()
        self.assertNotIn("secret", str(error.exception))

    def test_local_model_can_call_a_tool_and_receive_its_result(self):
        tool_response = MagicMock()
        tool_response.raise_for_status.return_value = None
        tool_response.json.return_value = {
            "choices": [{
                "message": {
                    "content": "",
                    "tool_calls": [{
                        "id": "call-1",
                        "type": "function",
                        "function": {
                            "name": "generate_image",
                            "arguments": '{"prompt":"a friendly robot"}',
                        },
                    }],
                }
            }]
        }
        final_response = MagicMock()
        final_response.raise_for_status.return_value = None
        final_response.json.return_value = {
            "choices": [{"message": {"content": "I queued your image."}}]
        }
        provider = AIProvider({
            "provider": "local",
            "local": {"model": "qwen3-8b", "base_url": "http://localhost:1234/v1"},
        })
        executor = MagicMock(return_value={
            "status": "queued", "job_id": "job-1", "message": "Queued."
        })
        tools = [{
            "type": "function",
            "function": {
                "name": "generate_image",
                "description": "Generate an image.",
                "parameters": {"type": "object", "properties": {}},
            },
        }]

        with patch(
            "petey.ai_provider.HTTP_SESSION.post",
            side_effect=[tool_response, final_response],
        ) as post:
            text, events = provider.complete_with_tools(
                "Generate an image", "You are Petey", [], tools, executor
            )

        self.assertEqual(text, "I queued your image.")
        self.assertEqual(events[0]["result"]["job_id"], "job-1")
        executor.assert_called_once_with("generate_image", {"prompt": "a friendly robot"})
        self.assertEqual(post.call_count, 2)
        self.assertEqual(post.call_args_list[0].kwargs["json"]["tools"], tools)
        followup_messages = post.call_args_list[1].kwargs["json"]["messages"]
        self.assertEqual(followup_messages[-1]["role"], "tool")
        self.assertEqual(followup_messages[-1]["tool_call_id"], "call-1")

    def test_gemini_can_call_a_tool_and_receive_its_result(self):
        tool_response = MagicMock()
        tool_response.raise_for_status.return_value = None
        tool_response.json.return_value = {
            "candidates": [{"content": {"role": "model", "parts": [{
                "functionCall": {
                    "name": "mcp_filesystem__read_text_file",
                    "args": {"path": "/approved/notes.txt"},
                }
            }]}}]
        }
        final_response = MagicMock()
        final_response.raise_for_status.return_value = None
        final_response.json.return_value = {
            "candidates": [{"content": {"parts": [{"text": "The note says hello."}]}}]
        }
        provider = AIProvider({
            "provider": "gemini",
            "gemini": {"model": "gemini-test", "api_key": "test-key"},
        })
        executor = MagicMock(return_value={"result": "hello"})
        tools = [{
            "type": "function",
            "function": {
                "name": "mcp_filesystem__read_text_file",
                "description": "Read an approved text file.",
                "parameters": {"type": "object", "properties": {"path": {"type": "string"}}},
            },
        }]

        with patch(
            "petey.ai_provider.HTTP_SESSION.post",
            side_effect=[tool_response, final_response],
        ) as post:
            text, events = provider.complete_with_tools(
                "Read the note", "You are Petey", [], tools, executor
            )

        self.assertEqual(text, "The note says hello.")
        self.assertEqual(events[0]["result"], {"result": "hello"})
        executor.assert_called_once_with(
            "mcp_filesystem__read_text_file", {"path": "/approved/notes.txt"}
        )
        declaration = post.call_args_list[0].kwargs["json"]["tools"][0]["functionDeclarations"][0]
        self.assertEqual(declaration["name"], "mcp_filesystem__read_text_file")
        followup = post.call_args_list[1].kwargs["json"]["contents"][-1]
        self.assertEqual(followup["parts"][0]["functionResponse"]["response"], {"result": "hello"})

    def test_qwen_tool_call_markup_is_normalized(self):
        calls = AIProvider._normalize_tool_calls(
            None,
            '<tool_call>{"name":"generate_image","arguments":{"prompt":"a cat"}}</tool_call>',
        )

        self.assertEqual(calls[0]["function"]["name"], "generate_image")
        self.assertEqual(
            calls[0]["function"]["arguments"], '{"prompt": "a cat"}'
        )

    def test_openai_compatible_request_contains_system_history_and_prompt(self):
        response = MagicMock()
        response.raise_for_status.return_value = None
        response.json.return_value = {"choices": [{"message": {"content": "Local reply"}}]}
        config = {
            "provider": "local",
            "local": {"model": "qwen", "base_url": "http://localhost:11434/v1", "api_key": ""},
        }
        with patch("petey.ai_provider.HTTP_SESSION.post", return_value=response) as post:
            result = AIProvider(config).complete(
                "Now", "Be helpful", [{"role": "user", "content": "Earlier"}]
            )

        self.assertEqual(result, "Local reply")
        self.assertEqual(post.call_args.args[0], "http://localhost:11434/v1/chat/completions")
        messages = post.call_args.kwargs["json"]["messages"]
        self.assertEqual([item["role"] for item in messages], ["system", "user", "user"])
        self.assertNotIn("Authorization", post.call_args.kwargs["headers"])

    def test_gemini_uses_saved_key_without_exposing_it(self):
        response = MagicMock()
        response.raise_for_status.return_value = None
        response.json.return_value = {
            "candidates": [{"content": {"parts": [{"text": "Gemini reply"}]}}]
        }
        config = {
            "provider": "gemini",
            "gemini": {"model": "gemini-test", "api_key": "private-key"},
        }
        provider = AIProvider(config)
        with patch("petey.ai_provider.HTTP_SESSION.post", return_value=response) as post:
            self.assertEqual(provider.complete("Hi", "System", []), "Gemini reply")

        self.assertEqual(post.call_args.kwargs["headers"]["x-goog-api-key"], "private-key")
        self.assertNotIn("private-key", str(provider.public_config()))

    def test_gemini_vision_uses_separate_model_with_local_chat_provider(self):
        response = MagicMock()
        response.raise_for_status.return_value = None
        response.json.return_value = {
            "candidates": [{"content": {"parts": [{"text": "A green robot."}]}}]
        }
        provider = AIProvider({
            "provider": "local",
            "gemini": {
                "api_key": "vision-key",
                "vision_model": "gemini-vision-test",
            },
            "local": {"model": "qwen", "base_url": "http://localhost:1234/v1"},
        })

        with patch("petey.ai_provider.HTTP_SESSION.post", return_value=response) as post:
            result = provider.describe_image(b"image-bytes", "image/png", "What is this?")

        self.assertEqual(result, "A green robot.")
        self.assertIn("gemini-vision-test:generateContent", post.call_args.args[0])
        parts = post.call_args.kwargs["json"]["contents"][0]["parts"]
        self.assertIn("What is this?", parts[0]["text"])
        self.assertEqual(parts[1]["inlineData"]["mimeType"], "image/png")
        self.assertEqual(parts[1]["inlineData"]["data"], base64.b64encode(b"image-bytes").decode("ascii"))
        self.assertEqual(provider.public_config()["vision_model"], "gemini-vision-test")
        self.assertNotIn("vision-key", str(provider.public_config()))

    def test_openai_requires_an_api_key(self):
        provider = AIProvider({"provider": "openai", "openai": {"model": "gpt-test"}})
        with patch.dict("os.environ", {}, clear=True):
            with self.assertRaises(AIProviderError):
                provider.complete("Hi", "System", [])

    def test_ollama_connection_error_has_actionable_instructions(self):
        provider = AIProvider(
            {
                "provider": "local",
                "local": {"model": "llama3.2", "base_url": "http://localhost:11434/v1"},
            }
        )
        with patch("petey.ai_provider.HTTP_SESSION.get", side_effect=requests.ConnectionError("refused")):
            with self.assertRaisesRegex(AIProviderError, "ollama serve"):
                provider.list_models()

    def test_disabled_thinking_is_requested_and_hidden_from_output(self):
        response = MagicMock()
        response.raise_for_status.return_value = None
        response.json.return_value = {
            "choices": [{"message": {"content": "<think>private reasoning</think>Final answer"}}]
        }
        provider = AIProvider(
            {
                "provider": "local",
                "local": {
                    "model": "qwen-thinking",
                    "base_url": "http://localhost:11434/v1",
                    "thinking_enabled": False,
                },
            }
        )
        with patch("petey.ai_provider.HTTP_SESSION.post", return_value=response) as post:
            result = provider.complete("Hi", "System", [])

        self.assertEqual(result, "Final answer")
        self.assertEqual(post.call_args.kwargs["json"]["reasoning_effort"], "none")


if __name__ == "__main__":
    unittest.main()
