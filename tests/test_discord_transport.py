import asyncio
import json
import time
import unittest
from unittest.mock import Mock, patch

from petey.discord_transport import (
    BOT_PERMISSIONS, DiscordError, DiscordGateway, DiscordTransport,
)


BOT = {"id": "111111111111111111", "username": "Petey", "global_name": "PETEY", "bot": True}
GUILD = {"id": "222222222222222222", "name": "Friends"}
CHANNEL = {"id": "333333333333333333", "guild_id": GUILD["id"], "name": "general", "type": 0}


class DiscordGatewayTests(unittest.TestCase):
    def test_gateway_identifies_online_and_reaches_ready(self):
        gateway = DiscordGateway("secret-token")
        sent = []

        class Socket:
            async def __aenter__(self): return self
            async def __aexit__(self, *_): return None
            async def receive_json(self):
                return {"op": 10, "d": {"heartbeat_interval": 45000}}
            async def send_json(self, payload): sent.append(payload)
            async def receive(self, timeout=None):
                gateway.stop_event.set()
                return type("Message", (), {
                    "type": 1,
                    "data": json.dumps({"op": 0, "t": "READY", "s": 1}),
                })()

        class Session:
            async def __aenter__(self): return self
            async def __aexit__(self, *_): return None
            def ws_connect(self, *_, **__): return Socket()

        with patch("petey.discord_transport.aiohttp.ClientSession", return_value=Session()):
            asyncio.run(gateway._connect_once())
        self.assertTrue(gateway.ready.is_set())
        identify = next(payload for payload in sent if payload["op"] == 2)
        self.assertEqual(identify["d"]["presence"]["status"], "online")
        self.assertEqual(identify["d"]["intents"], 0)

    def test_gateway_dispatches_slash_interactions(self):
        gateway = DiscordGateway("secret-token")
        gateway.on_dispatch = Mock()
        messages = [
            {"op": 0, "t": "READY", "s": 1, "d": {}},
            {"op": 0, "t": "INTERACTION_CREATE", "s": 2, "d": {"id": "interaction-1"}},
        ]

        class Socket:
            async def __aenter__(self): return self
            async def __aexit__(self, *_): return None
            async def receive_json(self):
                return {"op": 10, "d": {"heartbeat_interval": 45000}}
            async def send_json(self, _payload): return None
            async def receive(self, timeout=None):
                payload = messages.pop(0)
                if not messages:
                    gateway.stop_event.set()
                return type("Message", (), {"type": 1, "data": json.dumps(payload)})()

        class Session:
            async def __aenter__(self): return self
            async def __aexit__(self, *_): return None
            def ws_connect(self, *_, **__): return Socket()

        class ImmediateThread:
            def __init__(self, target, args=(), **_): self.target, self.args = target, args
            def start(self): self.target(*self.args)

        with patch("petey.discord_transport.aiohttp.ClientSession", return_value=Session()), patch(
            "petey.discord_transport.threading.Thread", ImmediateThread
        ):
            asyncio.run(gateway._connect_once())
        gateway.on_dispatch.assert_called_once_with({"id": "interaction-1"})


class DiscordTransportTests(unittest.TestCase):
    def setUp(self):
        self.gateway = Mock()
        self.transport = DiscordTransport("secret-token", gateway_factory=lambda _: self.gateway)
        self.transport._request = Mock()

    def tearDown(self):
        self.transport.close()

    def test_identity_requires_bot_and_builds_administrator_invite(self):
        self.transport._request.return_value = BOT
        identity = self.transport.identity()
        self.assertEqual(identity["name"], "PETEY")
        self.assertIn(f"permissions={BOT_PERMISSIONS}", identity["invite_url"])
        self.assertIn("applications.commands", identity["invite_url"])
        self.assertEqual(BOT_PERMISSIONS, 8)
        self.transport._request.return_value = {**BOT, "bot": False}
        with self.assertRaisesRegex(DiscordError, "User-account automation"):
            self.transport.identity()

    def test_request_uses_operation_specific_permission_error(self):
        transport = DiscordTransport("secret-token", gateway_factory=lambda _: self.gateway)
        response = Mock(status_code=403)
        transport.session.request = Mock(return_value=response)
        try:
            with self.assertRaisesRegex(DiscordError, "Manage Channels"):
                transport._request(
                    "POST", f"/guilds/{GUILD['id']}/channels",
                    forbidden_message="Give PETEY Manage Channels.",
                )
        finally:
            transport.close()

    def test_catalog_lists_guilds_and_text_channels_in_order(self):
        channels = [
            {**CHANNEL, "id": "333333333333333334", "name": "later", "position": 4},
            {**CHANNEL, "name": "general", "position": 1},
            {**CHANNEL, "id": "333333333333333335", "name": "voice", "type": 2},
        ]
        self.transport._request.side_effect = [BOT, [GUILD], channels]
        result = self.transport.catalog(GUILD["id"])
        self.assertEqual(result["guilds"], [{"id": GUILD["id"], "label": "Friends"}])
        self.assertEqual([item["label"] for item in result["channels"]], ["#general", "#later"])
        self.assertNotIn("secret-token", str(result))

    def test_connect_seeds_cursor_and_poll_returns_only_humans(self):
        old = {"id": "444444444444444440", "content": "old", "author": {"username": "Old"}}
        self.transport._request.side_effect = [BOT, CHANNEL, [old]]
        result = self.transport.connect(GUILD["id"], CHANNEL["id"])
        self.assertEqual(result["channel_name"], "general")
        self.gateway.start.assert_called_once_with()
        self.assertEqual(self.transport.cursor, old["id"])
        rows = [
            {"id": "444444444444444443", "content": "ignore bot", "author": {"username": "Bot", "bot": True}},
            {"id": "444444444444444442", "content": "", "attachments": [{"filename": "cat.png"}], "author": {"username": "Bob"}},
            {"id": "444444444444444441", "content": "hello   <@111111111111111111>",
             "mentions": [BOT], "author": {"username": "Alice", "global_name": "Al"}},
            {"id": "444444444444444444", "content": "ignore webhook", "webhook_id": "1", "author": {"username": "Hook"}},
        ]
        self.transport._request.side_effect = None
        self.transport._request.return_value = rows
        messages = self.transport.poll()
        self.assertEqual([(m.nickname, m.text) for m in messages], [("Al", "hello @PETEY"), ("Bob", "[shared cat.png]")])
        self.assertTrue(messages[0].addressed)
        self.assertFalse(messages[1].addressed)
        self.assertEqual(self.transport.cursor, "444444444444444444")
        self.assertEqual(self.transport._request.call_args.kwargs["params"]["after"], old["id"])

    def test_connect_rejects_channel_from_another_server(self):
        self.transport._request.side_effect = [BOT, {**CHANNEL, "guild_id": "999999999999999999"}]
        with self.assertRaisesRegex(DiscordError, "selected Discord server"):
            self.transport.connect(GUILD["id"], CHANNEL["id"])
        self.gateway.start.assert_not_called()

    def test_send_disables_mentions_and_requires_confirmation(self):
        sent = {"id": "555555555555555555", "content": "Hi @everyone"}
        self.transport.channel_id = CHANNEL["id"]
        self.transport._request.return_value = sent
        self.assertEqual(self.transport.send("Hi @everyone"), [])
        self.assertEqual(self.transport._request.call_args.kwargs["payload"]["allowed_mentions"], {"parse": []})
        self.transport._request.return_value = {**sent, "content": "different"}
        with self.assertRaisesRegex(DiscordError, "did not confirm"):
            self.transport.send("Hi @everyone")

    def test_typing_uses_the_connected_channel(self):
        self.transport.channel_id = CHANNEL["id"]
        self.transport.typing()
        self.transport._request.assert_called_once_with(
            "POST", f"/channels/{CHANNEL['id']}/typing"
        )

    def test_typing_requires_a_connected_channel(self):
        with self.assertRaisesRegex(ValueError, "Connect to a Discord channel"):
            self.transport.typing()
        self.transport._request.assert_not_called()

    def test_admin_channel_operations_validate_and_confirm(self):
        created = {"id": "666666666666666666", "name": "linux"}
        self.transport._request.return_value = created
        self.assertEqual(
            self.transport.create_text_channel(GUILD["id"], "Linux"),
            {"id": created["id"], "name": "linux"},
        )
        self.assertEqual(
            self.transport._request.call_args.kwargs["payload"],
            {"name": "linux", "type": 0},
        )
        self.assertIn(
            "Manage Channels",
            self.transport._request.call_args.kwargs["forbidden_message"],
        )

    def test_media_commands_are_created_or_updated_without_deleting_others(self):
        self.transport._request.side_effect = [
            [
                {"id": "777777777777777777", "name": "genimg"},
                {"id": "888888888888888888", "name": "unrelated"},
            ],
            *({"id": "999999999999999999"} for _ in range(9)),
        ]
        self.transport.register_media_commands(BOT["id"], GUILD["id"])
        calls = self.transport._request.call_args_list
        self.assertEqual(calls[0].args[0], "GET")
        genimg = next(call for call in calls if call.kwargs.get("payload", {}).get("name") == "genimg")
        self.assertEqual(genimg.args[0], "PATCH")
        self.assertIn("777777777777777777", genimg.args[1])
        self.assertFalse(any(call.args[0] == "DELETE" for call in calls))

    def test_interaction_reply_disables_mentions(self):
        self.transport.edit_interaction(BOT["id"], "interaction-token", "Done @everyone")
        payload = self.transport._request.call_args.kwargs["payload"]
        self.assertEqual(payload["allowed_mentions"], {"parse": []})

    def test_discord_attachment_download_is_bounded_and_typed(self):
        response = Mock()
        response.headers = {"Content-Type": "image/png"}
        response.iter_content.return_value = [b"image-bytes"]
        with patch("petey.discord_transport.requests.get", return_value=response):
            source = self.transport.download_interaction_attachment({
                "url": "https://cdn.discordapp.com/attachments/1/2/cat.png",
                "filename": "cat.png", "content_type": "image/png", "size": 11,
            }, "image")
        self.assertEqual(source.filename, "cat.png")
        self.assertEqual(source.content_type, "image/png")
        self.assertEqual(source.data, b"image-bytes")

        with self.assertRaisesRegex(ValueError, "invalid attachment URL"):
            self.transport.download_interaction_attachment({
                "url": "https://evil.example/cat.png", "size": 1,
            }, "image")
        self.transport._request.return_value = {**CHANNEL}
        self.assertEqual(self.transport.delete_channel(CHANNEL["id"])["id"], CHANNEL["id"])
        self.assertIn(
            "Manage Channels",
            self.transport._request.call_args.kwargs["forbidden_message"],
        )

    def test_clear_recent_messages_uses_bounded_bulk_delete(self):
        recent_id = str((int(time.time() * 1000) - 1420070400000) << 22)
        self.transport._request.side_effect = [[{"id": recent_id}], None]
        result = self.transport.clear_recent_messages(CHANNEL["id"], 20)
        self.assertEqual(result, {"deleted": 1, "requested": 20})
        self.assertEqual(
            self.transport._request.call_args.args,
            ("DELETE", f"/channels/{CHANNEL['id']}/messages/{recent_id}"),
        )

    def test_invalid_ids_and_long_or_multiline_messages_are_rejected(self):
        for guild in ("", "abc", "1/../../secret"):
            with self.assertRaises(ValueError):
                self.transport.channels(guild)
        for text in ("", "hello\nthere", "x" * 281):
            with self.assertRaises(ValueError):
                self.transport.send(text)
        self.transport._request.assert_not_called()


if __name__ == "__main__":
    unittest.main()
