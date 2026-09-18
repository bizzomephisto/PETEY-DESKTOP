import threading
import unittest
from unittest.mock import Mock, patch

from petey.room_chat import RoomActivity, RoomMessage
from petey.room_chat import ROOM_PROMPT
from petey.ai_provider import AIProviderError
from petey.discord_bridge import DiscordBridge
from petey.discord_transport import DiscordError


class State:
    ai_provider = {"provider": "local", "deapi": {"api_key": "de-key"}}
    system_prompt = "Be PETEY."
    installation_id = "desktop-test"
    speech = {"provider": "deapi"}
    discord_bot_token = "secret-token"
    discord_bot_token_status = {"has_token": True, "has_saved_token": True, "source": "saved"}
    discord_pace = "auto"
    discord_watched_topics = []
    discord_room_prompt = ROOM_PROMPT
    discord_auto_connect = False
    discord_last_location = {}

    def selected_model(self, operation):
        return {"txt2img": "image-model", "img2img": "edit-model"}.get(operation, "")

    def update_discord_bot_token(self, token="", clear=False):
        self.last_token = (token, clear)
        return self.discord_bot_token_status

    def update_discord_pace(self, pace):
        self.discord_pace = pace
        return pace

    def update_discord_watched_topics(self, topics):
        self.discord_watched_topics = topics
        return topics

    def update_discord_room_prompt(self, prompt="", reset=False):
        self.discord_room_prompt = ROOM_PROMPT if reset else prompt
        return self.discord_room_prompt

    def update_discord_auto_connect(self, enabled):
        if not isinstance(enabled, bool):
            raise ValueError("enabled must be a bool")
        self.discord_auto_connect = enabled
        return enabled

    def update_discord_last_location(self, guild_id, channel_id, guild="", channel=""):
        self.discord_last_location = {
            "guild_id": guild_id, "channel_id": channel_id,
            "guild": guild, "channel": channel,
        }
        return self.discord_last_location


class DiscordBridgeTests(unittest.TestCase):
    def setUp(self):
        self.transport = Mock()
        self.provider = Mock()
        self.state = State()
        self.bridge = DiscordBridge(
            self.state, lambda token: self.transport, lambda _: self.provider,
            typing_interval=0.01,
        )
        self.bridge.selection = {
            "guild_id": "222222222222222222", "channel_id": "333333333333333333",
            "guild": "Friends", "channel": "#general", "bot_name": "PETEY",
        }

    def run_turn(self, before_reply=None, messages=None):
        self.transport.connect.return_value = {
            "identity": {"id": "111111111111111111", "name": "PETEY", "invite_url": "https://discord.com/x"},
            "channel_name": "general",
        }
        self.transport.poll.return_value = messages or [
            RoomMessage(str(i), "Guest", f"Hello {i}") for i in range(3)
        ]
        self.provider.complete.return_value = "Hello Discord!"
        if before_reply:
            self.provider.complete.side_effect = before_reply
        self.transport.send.side_effect = lambda text: self.bridge.stop.set() or []
        with patch(
            "petey.discord_bridge.RoomActivity",
            side_effect=lambda nick, now, **kwargs: RoomActivity(nick, now - 100, **kwargs),
        ):
            self.bridge._run("secret-token", {"provider": "local"}, "Be PETEY.")

    def test_worker_reads_generates_sends_and_closes(self):
        self.run_turn()
        self.transport.connect.assert_called_once_with("222222222222222222", "333333333333333333")
        self.transport.typing.assert_called()
        self.transport.send.assert_called_once_with("Hello Discord!")
        self.transport.close.assert_called_once()
        status = self.bridge.status()
        self.assertEqual(status["phase"], "disconnected")
        self.assertNotIn("secret-token", str(status))
        self.assertEqual(self.state.discord_last_location["channel_id"], "333333333333333333")

    def test_worker_registers_media_commands_when_queue_is_available(self):
        self.bridge.media_jobs_getter = Mock()
        self.run_turn()
        self.transport.set_interaction_handler.assert_called_once_with(
            self.bridge._handle_media_interaction
        )
        self.transport.register_media_commands.assert_called_once_with(
            "111111111111111111", "222222222222222222"
        )

    def test_pause_or_disconnect_during_generation_discards_reply(self):
        def pause(*_):
            self.bridge.set_paused(True)
            self.bridge.stop.set()
            return "Too late"
        self.run_turn(pause)
        self.transport.send.assert_not_called()

    def test_typing_is_refreshed_during_a_slow_reply(self):
        release = threading.Event()

        def complete(*_):
            release.wait(1)
            return "Finished"

        def typing():
            if self.transport.typing.call_count >= 2:
                release.set()

        self.transport.typing.side_effect = typing
        self.run_turn(complete)
        self.assertGreaterEqual(self.transport.typing.call_count, 2)
        self.transport.send.assert_called_once_with("Finished")

    def test_typing_failure_does_not_discard_reply(self):
        self.transport.typing.side_effect = DiscordError("typing unavailable")
        self.run_turn()
        self.transport.send.assert_called_once_with("Hello Discord!")

    def test_malformed_silence_marker_is_cancelled_before_send(self):
        def silent(*_):
            self.bridge.stop.set()
            return "["
        self.run_turn(silent)
        self.transport.send.assert_not_called()

    def test_empty_provider_response_is_cancelled_without_connection_error(self):
        def empty(*_):
            self.bridge.stop.set()
            raise AIProviderError("The model returned an empty response.")
        self.run_turn(empty)
        self.transport.send.assert_not_called()
        self.assertEqual(self.bridge.phase, "disconnected")
        self.assertFalse(any(event["kind"] == "error" for event in self.bridge.events))

    def test_model_failure_cancels_one_turn_without_connection_error(self):
        def failure(*_):
            self.bridge.stop.set()
            raise AIProviderError("The local model stopped early")
        self.run_turn(failure)
        self.transport.send.assert_not_called()
        self.assertEqual(self.bridge.phase, "disconnected")
        self.assertTrue(any(
            "Discord remains connected" in event["text"]
            for event in self.bridge.events if event["kind"] == "error"
        ))

    def test_transient_model_demand_is_retried_before_sending(self):
        attempts = 0

        def busy_then_ready(*_):
            nonlocal attempts
            attempts += 1
            if attempts < 3:
                raise AIProviderError(
                    'Gemini returned HTTP 503: {"status": "UNAVAILABLE", "message": "high demand"}'
                )
            return "Hi after retry!"

        with patch.object(self.bridge.stop, "wait", return_value=False):
            self.run_turn(busy_then_ready)
        self.assertEqual(attempts, 3)
        self.transport.send.assert_called_once_with("Hi after retry!")

    def test_persistent_high_demand_uses_short_status_without_raw_json(self):
        def busy(*_):
            if self.provider.complete.call_count >= 3:
                self.bridge.stop.set()
            raise AIProviderError(
                'Gemini returned HTTP 503: {"status": "UNAVAILABLE", "message": "high demand"}'
            )

        with patch.object(self.bridge.stop, "wait", return_value=False):
            self.run_turn(busy)
        errors = [event["text"] for event in self.bridge.events if event["kind"] == "error"]
        self.assertTrue(any("temporarily busy after automatic retries" in text for text in errors))
        self.assertNotIn("UNAVAILABLE", " ".join(errors))

    def test_failure_is_redacted_and_not_retried(self):
        self.transport.connect.side_effect = RuntimeError("secret-token")
        self.bridge._run("secret-token", {}, "")
        self.assertEqual(self.bridge.phase, "error")
        self.assertNotIn("secret-token", self.bridge.error)
        self.transport.connect.assert_called_once()

    def test_discord_errors_are_actionable(self):
        self.transport.connect.side_effect = DiscordError("Missing Send Messages permission.")
        self.bridge._run("secret-token", {}, "")
        self.assertEqual(self.bridge.error, "Missing Send Messages permission.")

    def test_token_is_validated_before_being_saved_and_never_returned(self):
        self.transport.identity.return_value = {"id": "1", "name": "PETEY"}
        status = self.bridge.update_token("new-secret")
        self.transport.identity.assert_called_once()
        self.assertEqual(self.state.last_token, ("new-secret", False))
        self.assertNotIn("new-secret", str(status))
        self.transport.identity.side_effect = DiscordError("bad token")
        with self.assertRaises(DiscordError):
            self.bridge.update_token("bad-secret")
        self.assertEqual(self.state.last_token, ("new-secret", False))

    def test_catalog_uses_effective_token_and_closes_client(self):
        self.transport.catalog.return_value = {"guilds": [], "channels": []}
        self.assertEqual(self.bridge.catalog(), {"guilds": [], "channels": []})
        self.transport.close.assert_called_once()

    def test_instructions_and_controls_require_connection(self):
        with self.assertRaises(ValueError):
            self.bridge.instruct("Start trivia")
        with self.assertRaises(ValueError):
            self.bridge.set_paused(True)
        self.bridge.phase = "connected"
        self.bridge.instruct("Start made-up trivia")
        self.assertEqual(self.bridge.instructions[0]["status"], "queued")
        with self.assertRaises(ValueError):
            self.bridge.set_paused("yes")
        self.assertEqual(self.bridge.set_pace("fast")["pace"], "fast")

    def test_watched_topics_are_saved_and_match_complete_words(self):
        status = self.bridge.set_watched_topics(["Linux", "retro games"])
        self.assertEqual(status["watched_topics"], ["Linux", "retro games"])
        self.assertTrue(self.bridge._matches_watched_topic("I switched to linux yesterday"))
        self.assertTrue(self.bridge._matches_watched_topic("Any good retro games?"))
        self.assertFalse(self.bridge._matches_watched_topic("A clinical inux test"))

    def test_room_prompt_updates_live_bridge_state(self):
        status = self.bridge.set_room_prompt("Be concise and talk about robots.")
        self.assertEqual(status["room_prompt"], "Be concise and talk about robots.")
        self.assertEqual(self.bridge.set_room_prompt(reset=True)["room_prompt"], ROOM_PROMPT)

    def test_auto_connect_setting_is_saved(self):
        self.assertTrue(self.bridge.set_auto_connect(True)["auto_connect"])
        self.assertTrue(self.state.discord_auto_connect)
        with self.assertRaises(ValueError):
            self.bridge.set_auto_connect("yes")

    def test_last_location_auto_connects_during_startup(self):
        state = State()
        state.discord_auto_connect = True
        state.discord_last_location = {
            "guild_id": "222222222222222222", "channel_id": "333333333333333333",
            "guild": "Friends", "channel": "#general",
        }
        with patch.object(DiscordBridge, "connect", return_value={}) as connect:
            DiscordBridge(state, lambda token: self.transport, lambda _: self.provider)
        connect.assert_called_once_with(
            guild_id="222222222222222222", channel_id="333333333333333333",
            guild="Friends", channel="#general",
        )

    def test_room_prompt_enhancement_returns_an_unsaved_draft(self):
        self.provider.complete.return_value = "Be warm, brief, and follow the room's pace."
        original = self.state.discord_room_prompt
        result = self.bridge.enhance_room_prompt("be nice and don't spam")
        self.assertEqual(result["prompt"], "Be warm, brief, and follow the room's pace.")
        self.assertEqual(self.state.discord_room_prompt, original)
        self.assertEqual(self.provider.complete.call_args.args[0], "be nice and don't spam")
        self.assertIn("Return only", self.provider.complete.call_args.args[1])

    def test_watched_topic_gets_a_priority_reply(self):
        self.bridge.set_watched_topics(["linux"])
        self.run_turn(messages=[RoomMessage("1", "Guest", "I installed Linux")])
        self.transport.send.assert_called_once_with("Hello Discord!")
        prompt = self.provider.complete.call_args.args[0]
        self.assertIn("I installed Linux [priority message]", prompt)

    def test_media_slash_command_queues_desktop_deapi_job(self):
        jobs = Mock()
        jobs.submit.return_value = {"id": "abcd1234efgh5678", "kind": "image"}
        self.bridge.media_jobs_getter = lambda: jobs
        attachment = {
            "id": "44", "filename": "cat.png", "content_type": "image/png",
            "url": "https://cdn.discordapp.com/attachments/1/2/cat.png",
        }
        source = Mock()
        self.transport.download_interaction_attachment.return_value = source
        interaction = {
            "id": "555555555555555555", "application_id": "111111111111111111",
            "guild_id": "222222222222222222", "token": "interaction-token",
            "data": {
                "name": "img2img",
                "options": [
                    {"name": "prompt", "value": "make it neon"},
                    {"name": "image", "value": "44"},
                ],
                "resolved": {"attachments": {"44": attachment}},
            },
        }
        with patch("petey.discord_bridge.threading.Thread") as thread:
            self.bridge._handle_media_interaction(interaction)
        self.transport.defer_interaction.assert_called_once_with(
            "555555555555555555", "interaction-token"
        )
        self.transport.download_interaction_attachment.assert_called_once_with(attachment, "image")
        jobs.submit.assert_called_once_with(
            operation="img2img", prompt="make it neon", installation_id="desktop-test",
            model_slug="edit-model", source=source, parameters={},
            speech_settings={"provider": "deapi"}, ai_config=self.state.ai_provider,
        )
        self.assertIn("queued /img2img", self.transport.edit_interaction.call_args.args[2])
        thread.return_value.start.assert_called_once_with()

    def test_completed_slash_job_posts_result_url(self):
        jobs = Mock()
        jobs.get.return_value = {
            "status": "completed", "result": {"result_url": "https://media.example/result.png"},
        }
        self.bridge.media_jobs_getter = lambda: jobs
        self.bridge._watch_media_interaction(
            "job-1", "111111111111111111", "interaction-token", "genimg"
        )
        self.assertIn("https://media.example/result.png", self.transport.edit_interaction.call_args.args[2])

    def test_owner_admin_request_requires_approval(self):
        self.bridge.phase = "connected"
        status = self.bridge.instruct("create a new channel called talkytalk")
        proposal = status["admin_proposals"][0]
        self.assertEqual(proposal["status"], "pending")
        self.assertEqual(proposal["data"]["name"], "talkytalk")
        self.transport.create_text_channel.assert_not_called()
        self.transport.create_text_channel.return_value = {"id": "4", "name": "linux"}
        completed = self.bridge.resolve_admin_proposal(proposal["id"], approve=True)
        self.transport.create_text_channel.assert_called_once_with(
            "222222222222222222", "talkytalk"
        )
        self.assertEqual(completed["admin_proposals"][0]["status"], "completed")

    def test_common_create_channel_wording_is_recognized(self):
        self.bridge.phase = "connected"
        for wording in (
            "create a channel named linux",
            "make a new text channel called retro games",
            "please add channel general-2",
        ):
            proposal = self.bridge._admin_proposal(wording)
            self.assertIsNotNone(proposal, wording)
            self.assertEqual(proposal["action"], "create_channel")

    def test_failed_admin_action_keeps_discord_error_on_proposal(self):
        self.bridge.phase = "connected"
        proposal = self.bridge.instruct("create a new channel called talkytalk")["admin_proposals"][0]
        self.transport.create_text_channel.side_effect = DiscordError(
            "Missing Manage Channels permission."
        )
        with self.assertRaises(DiscordError):
            self.bridge.resolve_admin_proposal(proposal["id"], approve=True)
        failed = self.bridge.status()["admin_proposals"][0]
        self.assertEqual(failed["status"], "failed")
        self.assertEqual(failed["error"], "Missing Manage Channels permission.")

    def test_destructive_admin_request_can_be_rejected(self):
        self.bridge.phase = "connected"
        status = self.bridge.instruct("delete this channel")
        proposal = status["admin_proposals"][0]
        rejected = self.bridge.resolve_admin_proposal(proposal["id"], approve=False)
        self.assertEqual(rejected["admin_proposals"][0]["status"], "rejected")
        self.transport.delete_channel.assert_not_called()

    def test_prune_request_means_recent_messages_and_needs_approval(self):
        self.bridge.phase = "connected"
        status = self.bridge.instruct("clear this channel's last 50 messages")
        proposal = status["admin_proposals"][0]
        self.assertEqual(proposal["action"], "clear_messages")
        self.assertIn("50 recent messages", proposal["summary"])
        self.transport.clear_recent_messages.assert_not_called()


if __name__ == "__main__":
    unittest.main()
