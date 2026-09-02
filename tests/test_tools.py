import unittest
from unittest.mock import MagicMock, patch

from petey.tools.media import build_media_tools, explicit_image_request
from petey.tools.registry import ToolError, ToolRegistry, ToolSpec


class ToolRegistryTests(unittest.TestCase):
    def test_tool_is_only_offered_when_its_policy_allows_it(self):
        tool = ToolSpec(
            name="echo",
            description="Echo text.",
            parameters={"type": "object", "required": ["text"]},
            handler=lambda arguments: {"text": arguments["text"]},
            available_when=lambda message: message == "allowed",
        )
        registry = ToolRegistry([tool])

        self.assertEqual(registry.schemas_for("blocked"), [])
        self.assertEqual(registry.schemas_for("allowed")[0]["function"]["name"], "echo")
        with self.assertRaises(ToolError):
            registry.execute("echo", {"text": "hi"}, "blocked")
        self.assertEqual(
            registry.execute("echo", {"text": "hi"}, "allowed"), {"text": "hi"}
        )

    def test_image_intent_gate_requires_an_explicit_creation_request(self):
        self.assertTrue(explicit_image_request("Generate an image of a tiny moon base"))
        self.assertTrue(explicit_image_request("Draw me a portrait of Petey"))
        self.assertFalse(explicit_image_request("Tell me how image generation works"))
        self.assertFalse(explicit_image_request("That photograph looks great"))

    def test_generate_image_queues_existing_deapi_job_manager(self):
        state = MagicMock()
        state.installation_id = "desktop-test"
        state.person_id = "owner"
        state.selected_model.return_value = "flux-model"
        jobs = MagicMock()
        jobs.submit.return_value = {"id": "job-12345678"}
        memory = MagicMock()
        registry = ToolRegistry(build_media_tools(state, lambda: jobs, memory))

        with patch.dict("os.environ", {"DEAPI_KEY": "configured"}):
            result = registry.execute(
                "generate_image",
                {"prompt": "A desktop robot", "width": 9000, "steps": 0},
                "Create an image of a desktop robot",
            )

        self.assertEqual(result["status"], "queued")
        self.assertEqual(jobs.submit.call_args.kwargs["model_slug"], "flux-model")
        self.assertEqual(jobs.submit.call_args.kwargs["parameters"]["width"], 2048)
        self.assertEqual(jobs.submit.call_args.kwargs["parameters"]["steps"], 1)
        memory.record_image_generation.assert_called_once_with(
            "desktop-test", "owner", "A desktop robot"
        )

    def test_generate_image_requires_deapi_configuration(self):
        state = MagicMock()
        registry = ToolRegistry(build_media_tools(state, MagicMock(), MagicMock()))
        with patch.dict("os.environ", {}, clear=True):
            with self.assertRaisesRegex(ToolError, "Media generation is not configured"):
                registry.execute(
                    "generate_image",
                    {"prompt": "A robot"},
                    "Generate an image of a robot",
                )

    def test_temporary_generation_does_not_write_memory_metric(self):
        state = MagicMock()
        state.installation_id = "desktop-test"
        state.person_id = "owner"
        jobs = MagicMock()
        jobs.submit.return_value = {"id": "job-temp"}
        memory = MagicMock()
        registry = ToolRegistry(
            build_media_tools(state, lambda: jobs, memory, record_memory=False)
        )

        with patch.dict("os.environ", {"DEAPI_KEY": "configured"}):
            registry.execute(
                "generate_image",
                {"prompt": "An ephemeral robot"},
                "Generate an image of an ephemeral robot",
            )

        memory.record_image_generation.assert_not_called()


if __name__ == "__main__":
    unittest.main()
