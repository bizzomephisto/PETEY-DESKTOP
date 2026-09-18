"""Small Discord REST client for PETEY's explicitly connected bot account."""

from __future__ import annotations

import asyncio
import json
import platform
import random
import re
import threading
import time
from urllib.parse import quote, urlencode, urlsplit

import aiohttp
import requests

from petey.room_chat import RoomMessage
from petey.discord_media import command_schemas
from petey.media_service import MediaInput
from petey.version import __version__


API = "https://discord.com/api/v10"
SNOWFLAKE = re.compile(r"[0-9]{5,24}")
TEXT_CHANNEL_TYPES = {0, 5}
BOT_PERMISSIONS = 8  # Administrator; the bridge itself exposes chat operations only.
GATEWAY = "wss://gateway.discord.gg/?v=10&encoding=json"


class DiscordError(RuntimeError):
    pass


class DiscordGateway:
    """Minimal Gateway presence connection with heartbeat and reconnect handling."""

    def __init__(self, token: str):
        self.token = token
        self.stop_event = threading.Event()
        self.startup_done = threading.Event()
        self.ready = threading.Event()
        self.error = ""
        self.thread = None
        self.on_dispatch = None

    async def _connect_once(self):
        timeout = aiohttp.ClientTimeout(total=None, connect=15, sock_connect=15, sock_read=None)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.ws_connect(GATEWAY, heartbeat=None, autoclose=True) as socket:
                hello = await asyncio.wait_for(socket.receive_json(), timeout=20)
                if hello.get("op") != 10:
                    raise RuntimeError("Discord Gateway did not send Hello.")
                interval = max(float(hello.get("d", {}).get("heartbeat_interval", 45000)) / 1000, 1)
                await socket.send_json({
                    "op": 2,
                    "d": {
                        "token": self.token,
                        "intents": 0,
                        "properties": {
                            "os": platform.system().lower(),
                            "browser": "petey-desktop",
                            "device": "petey-desktop",
                        },
                        "presence": {
                            "since": None, "activities": [], "status": "online", "afk": False,
                        },
                    },
                })
                sequence = None
                next_heartbeat = time.monotonic() + random.random() * interval
                while not self.stop_event.is_set():
                    now = time.monotonic()
                    if now >= next_heartbeat:
                        await socket.send_json({"op": 1, "d": sequence})
                        next_heartbeat = now + interval
                    try:
                        message = await socket.receive(timeout=min(max(next_heartbeat - now, 0.1), 1))
                    except asyncio.TimeoutError:
                        continue
                    if message.type == aiohttp.WSMsgType.TEXT:
                        payload = json.loads(message.data)
                        if payload.get("s") is not None:
                            sequence = payload["s"]
                        opcode = payload.get("op")
                        if opcode == 0 and payload.get("t") == "READY":
                            self.ready.set()
                            self.startup_done.set()
                        elif (opcode == 0 and payload.get("t") == "INTERACTION_CREATE"
                              and callable(self.on_dispatch)):
                            threading.Thread(
                                target=self.on_dispatch, args=(payload.get("d") or {},),
                                daemon=True, name="petey-discord-interaction",
                            ).start()
                        elif opcode == 1:
                            await socket.send_json({"op": 1, "d": sequence})
                            next_heartbeat = time.monotonic() + interval
                        elif opcode in {7, 9}:
                            return
                    elif message.type in {
                        aiohttp.WSMsgType.CLOSE, aiohttp.WSMsgType.CLOSED,
                        aiohttp.WSMsgType.ERROR,
                    }:
                        return

    async def _run(self):
        while not self.stop_event.is_set():
            try:
                await self._connect_once()
                self.error = ""
            except Exception:
                self.error = "Discord Gateway presence could not connect."
                if not self.ready.is_set():
                    self.startup_done.set()
            if not self.stop_event.is_set():
                await asyncio.sleep(2)

    def start(self):
        self.thread = threading.Thread(
            target=lambda: asyncio.run(self._run()), daemon=True, name="petey-discord-gateway"
        )
        self.thread.start()
        if not self.startup_done.wait(12) or not self.ready.is_set():
            self.close()
            raise DiscordError(
                "Discord connected over HTTPS but could not establish its online presence. "
                "Check the network and bot configuration."
            )

    def close(self):
        self.stop_event.set()
        if self.thread is not None and self.thread is not threading.current_thread():
            self.thread.join(timeout=3)


class DiscordTransport:
    def __init__(self, token: str, gateway_factory=DiscordGateway):
        token = str(token or "").strip()
        if not token:
            raise DiscordError("Save a Discord bot token first.")
        self.session = requests.Session()
        self.token = token
        self.gateway_factory = gateway_factory
        self.gateway = None
        self.session.headers.update({
            "Authorization": f"Bot {token}",
            "User-Agent": (
                "DiscordBot (https://github.com/bizzomephisto/PETEY-DESKTOP, "
                f"{__version__})"
            ),
        })
        self.bot = {}
        self.guild_id = ""
        self.channel_id = ""
        self.cursor = ""
        self.interaction_handler = None

    def set_interaction_handler(self, handler):
        self.interaction_handler = handler

    @staticmethod
    def _id(value, label):
        value = str(value or "")
        if not SNOWFLAKE.fullmatch(value):
            raise ValueError(f"Choose a Discord {label} from the list.")
        return value

    def _request(self, method: str, path: str, *, params=None, payload=None,
                 forbidden_message=""):
        url = API + path
        for attempt in range(2):
            try:
                response = self.session.request(
                    method, url, params=params, json=payload, timeout=(10, 20)
                )
            except requests.RequestException:
                raise DiscordError(
                    "The Discord connection failed. Check the network and reconnect; no message was retried."
                ) from None
            if response.status_code == 429 and attempt == 0:
                try:
                    delay = min(max(float(response.json().get("retry_after", 1)), 0), 10)
                except (TypeError, ValueError, requests.JSONDecodeError):
                    delay = 1
                time.sleep(delay)
                continue
            if response.status_code == 401:
                raise DiscordError("Discord rejected the bot token. Save a current token and try again.")
            if response.status_code == 403:
                raise DiscordError(
                    forbidden_message or
                    "Discord denied access. Give PETEY View Channel, Read Message History, and Send Messages in this channel."
                )
            if response.status_code == 404:
                raise DiscordError("The Discord server or channel is no longer available to this bot.")
            if response.status_code >= 400:
                raise DiscordError(f"Discord returned an error ({response.status_code}). Try again later.")
            if response.status_code == 204:
                return None
            try:
                return response.json()
            except requests.JSONDecodeError:
                raise DiscordError("Discord returned an unreadable response.") from None
        raise DiscordError("Discord is rate limiting the connection. Wait a moment and try again.")

    def identity(self) -> dict:
        user = self._request("GET", "/users/@me")
        if (not isinstance(user, dict) or not user.get("bot")
                or not SNOWFLAKE.fullmatch(str(user.get("id") or ""))):
            raise DiscordError("This credential is not a Discord bot token. User-account automation is not supported.")
        self.bot = user
        name = str(user.get("global_name") or user.get("username") or "PETEY")[:64]
        return {
            "id": str(user.get("id") or ""),
            "name": name,
            "invite_url": "https://discord.com/oauth2/authorize?" + urlencode({
                "client_id": str(user.get("id") or ""),
                "scope": "bot applications.commands",
                "permissions": str(BOT_PERMISSIONS),
            }),
        }

    def guilds(self) -> list[dict]:
        self.identity()
        rows, after = [], ""
        for _ in range(5):
            params = {"limit": 200}
            if after:
                params["after"] = after
            page = self._request("GET", "/users/@me/guilds", params=params)
            if not isinstance(page, list):
                raise DiscordError("Discord returned an invalid server list.")
            rows.extend(page)
            if len(page) < 200:
                break
            after = str(page[-1].get("id") or "")
        return sorted(
            ({"id": str(item["id"]), "label": str(item.get("name") or "Unnamed server")[:100]}
             for item in rows if SNOWFLAKE.fullmatch(str(item.get("id") or ""))),
            key=lambda item: item["label"].casefold(),
        )

    def channels(self, guild_id: str) -> list[dict]:
        guild_id = self._id(guild_id, "server")
        rows = self._request("GET", f"/guilds/{guild_id}/channels")
        if not isinstance(rows, list):
            raise DiscordError("Discord returned an invalid channel list.")
        channels = []
        for item in rows:
            channel_id = str(item.get("id") or "")
            if item.get("type") in TEXT_CHANNEL_TYPES and SNOWFLAKE.fullmatch(channel_id):
                channels.append({
                    "id": channel_id,
                    "label": "#" + str(item.get("name") or "unnamed")[:100],
                    "position": int(item.get("position") or 0),
                })
        channels.sort(key=lambda item: (item["position"], item["label"].casefold()))
        for item in channels:
            item.pop("position", None)
        return channels

    def catalog(self, guild_id: str = "") -> dict:
        guilds = self.guilds()
        if not guild_id and guilds:
            guild_id = guilds[0]["id"]
        channels = self.channels(guild_id) if guild_id else []
        identity = {
            "id": str(self.bot.get("id") or ""),
            "name": str(self.bot.get("global_name") or self.bot.get("username") or "PETEY")[:64],
            "invite_url": "https://discord.com/oauth2/authorize?" + urlencode({
                "client_id": str(self.bot.get("id") or ""),
                "scope": "bot applications.commands",
                "permissions": str(BOT_PERMISSIONS),
            }),
        }
        return {"identity": identity, "guilds": guilds, "channels": channels, "guild_id": guild_id}

    def connect(self, guild_id: str, channel_id: str) -> dict:
        guild_id = self._id(guild_id, "server")
        channel_id = self._id(channel_id, "channel")
        identity = self.identity()
        channel = self._request("GET", f"/channels/{channel_id}")
        if (not isinstance(channel, dict) or str(channel.get("guild_id") or "") != guild_id
                or channel.get("type") not in TEXT_CHANNEL_TYPES):
            raise DiscordError("Choose a text channel from the selected Discord server.")
        self.guild_id, self.channel_id = guild_id, channel_id
        recent = self._request("GET", f"/channels/{channel_id}/messages", params={"limit": 100})
        recent_ids = [str(item.get("id") or "") for item in recent] if isinstance(recent, list) else []
        recent_ids = [message_id for message_id in recent_ids if SNOWFLAKE.fullmatch(message_id)]
        if recent_ids:
            self.cursor = max(recent_ids, key=int)
        self.gateway = self.gateway_factory(self.token)
        self.gateway.on_dispatch = self.interaction_handler
        self.gateway.start()
        return {"identity": identity, "channel_name": str(channel.get("name") or "channel")[:100]}

    def register_media_commands(self, application_id: str, guild_id: str) -> None:
        application_id = self._id(application_id, "application")
        guild_id = self._id(guild_id, "server")
        base = f"/applications/{application_id}/guilds/{guild_id}/commands"
        permission_error = (
            "Discord denied slash-command registration. Use Add PETEY to a Discord server "
            "again to authorize the applications.commands scope."
        )
        existing = self._request("GET", base, forbidden_message=permission_error)
        existing = existing if isinstance(existing, list) else []
        by_name = {
            str(item.get("name") or ""): str(item.get("id") or "")
            for item in existing if isinstance(item, dict)
        }
        for schema in command_schemas():
            command_id = by_name.get(schema["name"])
            path = f"{base}/{command_id}" if SNOWFLAKE.fullmatch(command_id or "") else base
            self._request(
                "PATCH" if command_id else "POST", path, payload=schema,
                forbidden_message=permission_error,
            )

    def defer_interaction(self, interaction_id: str, interaction_token: str) -> None:
        interaction_id = self._id(interaction_id, "interaction")
        token = str(interaction_token or "").strip()
        if not token or len(token) > 512:
            raise ValueError("Discord supplied an invalid interaction token.")
        self._request(
            "POST", f"/interactions/{interaction_id}/{quote(token, safe='')}/callback",
            payload={"type": 5},
        )

    def edit_interaction(self, application_id: str, interaction_token: str, content: str) -> None:
        application_id = self._id(application_id, "application")
        token = str(interaction_token or "").strip()
        content = str(content or "").strip()[:2000]
        if not token or len(token) > 512 or not content:
            raise ValueError("Discord interaction reply is invalid.")
        self._request(
            "PATCH", f"/webhooks/{application_id}/{quote(token, safe='')}/messages/@original",
            payload={"content": content, "allowed_mentions": {"parse": []}},
        )

    def download_interaction_attachment(self, attachment: dict, expected_kind: str) -> MediaInput:
        if not isinstance(attachment, dict):
            raise ValueError(f"Attach a source {expected_kind} to this command.")
        url = str(attachment.get("url") or "")
        parsed = urlsplit(url)
        if parsed.scheme != "https" or parsed.hostname not in {
            "cdn.discordapp.com", "media.discordapp.net",
        }:
            raise ValueError("Discord supplied an invalid attachment URL.")
        declared_size = int(attachment.get("size") or 0)
        if declared_size > 25 * 1024 * 1024:
            raise ValueError("Discord media inputs are limited to 25 MB.")
        try:
            response = requests.get(url, timeout=(10, 30), stream=True)
            response.raise_for_status()
            chunks, total = [], 0
            for chunk in response.iter_content(1024 * 1024):
                total += len(chunk)
                if total > 25 * 1024 * 1024:
                    raise ValueError("Discord media inputs are limited to 25 MB.")
                chunks.append(chunk)
        except requests.RequestException:
            raise DiscordError("PETEY could not download the Discord attachment.") from None
        content_type = str(
            attachment.get("content_type") or response.headers.get("Content-Type")
            or "application/octet-stream"
        ).split(";", 1)[0]
        filename = str(attachment.get("filename") or f"source-{expected_kind}")[:200]
        source = MediaInput(filename, content_type, b"".join(chunks))
        if expected_kind == "image" and not content_type.startswith("image/"):
            raise ValueError("Attach an image to this command.")
        if expected_kind == "video" and not content_type.startswith("video/"):
            raise ValueError("Attach a video to this command.")
        return source

    def _messages(self, rows) -> list[RoomMessage]:
        result = []
        for item in sorted(rows if isinstance(rows, list) else [], key=lambda row: int(row.get("id") or 0)):
            message_id = str(item.get("id") or "")
            author = item.get("author") or {}
            if not SNOWFLAKE.fullmatch(message_id) or author.get("bot") or item.get("webhook_id"):
                continue
            content = " ".join(str(item.get("content") or "").split())
            bot_id = str(self.bot.get("id") or "")
            addressed = any(
                str(mention.get("id") or "") == bot_id for mention in item.get("mentions") or []
            )
            referenced_author = (item.get("referenced_message") or {}).get("author") or {}
            addressed = addressed or str(referenced_author.get("id") or "") == bot_id
            for mention in item.get("mentions") or []:
                mention_id = str(mention.get("id") or "")
                if not SNOWFLAKE.fullmatch(mention_id):
                    continue
                mention_name = str(
                    mention.get("global_name") or mention.get("username") or "Discord user"
                )[:64]
                content = content.replace(f"<@{mention_id}>", f"@{mention_name}")
                content = content.replace(f"<@!{mention_id}>", f"@{mention_name}")
            attachments = item.get("attachments") or []
            if not content and attachments:
                names = [str(a.get("filename") or "attachment")[:120] for a in attachments[:3]]
                content = "[shared " + ", ".join(names) + "]"
            if not content:
                continue
            nickname = str(author.get("global_name") or author.get("username") or "Discord user")[:64]
            result.append(RoomMessage(message_id, nickname, content[:2000], addressed))
        return result

    def poll(self) -> list[RoomMessage]:
        params = {"limit": 100}
        if self.cursor:
            params["after"] = self.cursor
        rows = self._request("GET", f"/channels/{self.channel_id}/messages", params=params)
        row_ids = [str(item.get("id") or "") for item in rows] if isinstance(rows, list) else []
        row_ids = [message_id for message_id in row_ids if SNOWFLAKE.fullmatch(message_id)]
        if row_ids:
            self.cursor = max(row_ids, key=int)
        return self._messages(rows)

    def send(self, text: str) -> list[RoomMessage]:
        if not isinstance(text, str) or not text.strip() or len(text) > 280 or "\n" in text:
            raise ValueError("Only short, one-line Discord messages can be sent.")
        item = self._request("POST", f"/channels/{self.channel_id}/messages", payload={
            "content": text,
            "allowed_mentions": {"parse": []},
        })
        if not isinstance(item, dict) or str(item.get("content") or "") != text:
            raise DiscordError("Discord did not confirm the message. Stopped without retrying it.")
        message_id = str(item.get("id") or "")
        if SNOWFLAKE.fullmatch(message_id):
            self.cursor = message_id if not self.cursor or int(message_id) > int(self.cursor) else self.cursor
        return []

    def typing(self):
        if not self.channel_id:
            raise ValueError("Connect to a Discord channel before showing the typing indicator.")
        self._request("POST", f"/channels/{self.channel_id}/typing")

    def create_text_channel(self, guild_id: str, name: str) -> dict:
        guild_id = self._id(guild_id, "server")
        name = "-".join(str(name or "").strip().lower().split())
        if not re.fullmatch(r"[a-z0-9_-]{1,100}", name):
            raise ValueError("Use a channel name containing letters, numbers, hyphens, or underscores.")
        channel = self._request(
            "POST", f"/guilds/{guild_id}/channels",
            payload={"name": name, "type": 0},
            forbidden_message=(
                "Discord denied channel creation. In Discord, open Server Settings → Roles "
                "and give PETEY's bot role Manage Channels or Administrator, then try again."
            ),
        )
        if not isinstance(channel, dict) or not SNOWFLAKE.fullmatch(str(channel.get("id") or "")):
            raise DiscordError("Discord did not confirm the new channel.")
        return {"id": str(channel["id"]), "name": str(channel.get("name") or name)}

    def delete_channel(self, channel_id: str) -> dict:
        channel_id = self._id(channel_id, "channel")
        channel = self._request(
            "DELETE", f"/channels/{channel_id}",
            forbidden_message=(
                "Discord denied channel deletion. In Discord, open Server Settings → Roles "
                "and give PETEY's bot role Manage Channels or Administrator, then try again."
            ),
        )
        if not isinstance(channel, dict) or str(channel.get("id") or "") != channel_id:
            raise DiscordError("Discord did not confirm the channel deletion.")
        return {"id": channel_id, "name": str(channel.get("name") or "channel")}

    def clear_recent_messages(self, channel_id: str, count=50) -> dict:
        channel_id = self._id(channel_id, "channel")
        try:
            count = int(count)
        except (TypeError, ValueError):
            raise ValueError("Choose 1–100 recent messages to clear.") from None
        if not 1 <= count <= 100:
            raise ValueError("Choose 1–100 recent messages to clear.")
        rows = self._request("GET", f"/channels/{channel_id}/messages", params={"limit": count})
        cutoff_ms = int((time.time() - 13 * 86400) * 1000)
        ids = []
        for item in rows if isinstance(rows, list) else []:
            message_id = str(item.get("id") or "")
            if SNOWFLAKE.fullmatch(message_id):
                timestamp_ms = (int(message_id) >> 22) + 1420070400000
                if timestamp_ms >= cutoff_ms:
                    ids.append(message_id)
        if len(ids) == 1:
            self._request(
                "DELETE", f"/channels/{channel_id}/messages/{ids[0]}",
                forbidden_message=(
                    "Discord denied message cleanup. Give PETEY View Channel, Read Message "
                    "History, and Manage Messages in this channel, then try again."
                ),
            )
        elif ids:
            self._request(
                "POST", f"/channels/{channel_id}/messages/bulk-delete",
                payload={"messages": ids},
                forbidden_message=(
                    "Discord denied message cleanup. Give PETEY View Channel, Read Message "
                    "History, and Manage Messages in this channel, then try again."
                ),
            )
        return {"deleted": len(ids), "requested": count}

    def close(self):
        if self.gateway is not None:
            self.gateway.close()
        self.session.close()
