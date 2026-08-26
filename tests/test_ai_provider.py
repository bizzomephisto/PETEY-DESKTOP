import unittest
from unittest.mock import MagicMock, patch

import requests

from petey.ai_provider import AIProvider, AIProviderError


class AIProviderTests(unittest.TestCase):
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
            "petey.ai_provider.requests.post",
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
        with patch("petey.ai_provider.requests.post", return_value=response) as post:
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
        with patch("petey.ai_provider.requests.post", return_value=response) as post:
            self.assertEqual(provider.complete("Hi", "System", []), "Gemini reply")

        self.assertEqual(post.call_args.kwargs["headers"]["x-goog-api-key"], "private-key")
        self.assertNotIn("private-key", str(provider.public_config()))

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
        with patch("petey.ai_provider.requests.get", side_effect=requests.ConnectionError("refused")):
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
        with patch("petey.ai_provider.requests.post", return_value=response) as post:
            result = provider.complete("Hi", "System", [])

        self.assertEqual(result, "Final answer")
        self.assertEqual(post.call_args.kwargs["json"]["reasoning_effort"], "none")


if __name__ == "__main__":
    unittest.main()
