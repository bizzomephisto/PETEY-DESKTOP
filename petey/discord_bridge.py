"""Single-channel Discord bot worker controlled by the PETEY desktop app."""

from collections import deque
import os
import re
import threading
import time
import uuid

from petey.ai_provider import AIProvider, AIProviderError
from petey.discord_media import parse_media_interaction
from petey.room_chat import RoomActivity, RoomConversation
from petey.discord_transport import DiscordError, DiscordTransport


class DiscordBridge:
    def __init__(self, state, transport_factory=DiscordTransport, provider_factory=AIProvider,
                 typing_interval=8, media_jobs_getter=None):
        self.state = state
        self.transport_factory = transport_factory
        self.provider_factory = provider_factory
        self.typing_interval = typing_interval
        self.media_jobs_getter = media_jobs_getter
        self.lock = threading.RLock()
        self.stop = threading.Event()
        self.thread = None
        self.phase = "disconnected"
        self.error = ""
        self.paused = False
        self.pace = state.discord_pace
        self.watched_topics = state.discord_watched_topics
        self.room_prompt = state.discord_room_prompt
        self.auto_connect = state.discord_auto_connect
        last_location = state.discord_last_location
        self.selection = {
            "guild_id": str(last_location.get("guild_id") or ""),
            "channel_id": str(last_location.get("channel_id") or ""),
            "guild": str(last_location.get("guild") or ""),
            "channel": str(last_location.get("channel") or ""),
            "bot_name": "PETEY",
        }
        self.instructions = deque(maxlen=20)
        self.events = deque(maxlen=100)
        self.admin_proposals = deque(maxlen=20)
        self.revision = 0
        self.sequence = 0
        if (self.auto_connect and state.discord_bot_token
                and self.selection["guild_id"] and self.selection["channel_id"]):
            self.connect(**{
                key: self.selection[key]
                for key in ("guild_id", "channel_id", "guild", "channel")
            })

    def credential_status(self):
        return self.state.discord_bot_token_status

    def update_token(self, token="", clear=False):
        with self.lock:
            if self.thread is not None and self.thread.is_alive():
                raise ValueError("Disconnect Discord before changing its bot token.")
        if clear:
            return self.state.update_discord_bot_token(clear=True)
        transport = self.transport_factory(token)
        try:
            transport.identity()
        finally:
            transport.close()
        return self.state.update_discord_bot_token(token)

    def catalog(self, guild_id=""):
        transport = self.transport_factory(self.state.discord_bot_token)
        try:
            return transport.catalog(guild_id)
        finally:
            transport.close()

    def status(self):
        with self.lock:
            return {
                "phase": self.phase, "error": self.error, "paused": self.paused,
                "pace": self.pace,
                "watched_topics": list(self.watched_topics),
                "room_prompt": self.room_prompt,
                "auto_connect": self.auto_connect,
                **self.selection, "credential": self.credential_status(),
                "instructions": [dict(item) for item in self.instructions],
                "admin_proposals": [
                    {key: value for key, value in item.items() if key != "created_at"}
                    for item in self.admin_proposals
                ],
                "events": [dict(item) for item in self.events],
            }

    def _event(self, kind, text, nickname=""):
        with self.lock:
            self.sequence += 1
            self.events.append({"id": self.sequence, "kind": kind, "text": text,
                                "nickname": nickname, "time": time.time()})

    def connect(self, guild_id, channel_id, guild="", channel=""):
        if not self.state.discord_bot_token:
            raise ValueError("Save a Discord bot token first.")
        with self.lock:
            if self.thread is not None and self.thread.is_alive():
                raise ValueError("Disconnect the current Discord channel before connecting again.")
            self.stop.clear()
            self.phase, self.error, self.paused = "connecting", "", False
            self.selection = {
                "guild_id": str(guild_id or ""), "channel_id": str(channel_id or ""),
                "guild": str(guild or "")[:100], "channel": str(channel or "")[:100],
                "bot_name": "PETEY",
            }
            self.instructions.clear()
            self.events.clear()
            self.revision += 1
            config, personality, token = self.state.ai_provider, self.state.system_prompt, self.state.discord_bot_token
            self.thread = threading.Thread(
                target=self._run, args=(token, config, personality), daemon=True,
                name="petey-discord",
            )
            self.thread.start()
        return self.status()

    def disconnect(self):
        with self.lock:
            self.stop.set()
            self.revision += 1
            if self.thread is not None and self.thread.is_alive():
                self.phase = "stopping"
        return self.status()

    def set_paused(self, paused):
        if not isinstance(paused, bool):
            raise ValueError("Paused must be true or false.")
        with self.lock:
            if self.phase != "connected":
                raise ValueError("Connect PETEY to a Discord channel first.")
            self.paused = paused
            self.revision += 1
        return self.status()

    def set_pace(self, pace):
        pace = self.state.update_discord_pace(pace)
        with self.lock:
            self.pace = pace
            self.revision += 1
        return self.status()

    def set_watched_topics(self, topics):
        topics = self.state.update_discord_watched_topics(topics)
        with self.lock:
            self.watched_topics = topics
        return self.status()

    def set_room_prompt(self, prompt="", reset=False):
        prompt = self.state.update_discord_room_prompt(prompt, reset=reset)
        with self.lock:
            self.room_prompt = prompt
            self.revision += 1
        return self.status()

    def set_auto_connect(self, enabled):
        enabled = self.state.update_discord_auto_connect(enabled)
        with self.lock:
            self.auto_connect = enabled
        return self.status()

    def enhance_room_prompt(self, prompt):
        if not isinstance(prompt, str) or not 1 <= len(prompt.strip()) <= 12000:
            raise ValueError("Enter a room prompt of 1–12,000 characters to enhance.")
        system = (
            "You improve system prompts for an AI participating in a public Discord room. "
            "Preserve the owner's intent while making rules clear, concise, and non-conflicting. "
            "Keep useful boundaries about public messages, conversational continuity, games, and "
            "remaining silent when no reply is useful. Do not invent capabilities or credentials. "
            "Return only the complete enhanced prompt with no introduction or code fence."
        )
        result = self.provider_factory(self.state.ai_provider).complete(
            prompt.strip(), system, []
        )
        result = str(result or "").strip()
        if not result or len(result) > 12000:
            raise AIProviderError("The model did not return a usable enhanced room prompt.")
        return {"prompt": result}

    def _matches_watched_topic(self, text):
        with self.lock:
            topics = tuple(self.watched_topics)
        return any(re.search(r"(?<!\w)" + re.escape(topic) + r"(?!\w)", text, re.I)
                   for topic in topics)

    def instruct(self, text):
        if not isinstance(text, str) or not 1 <= len(text.strip()) <= 2000:
            raise ValueError("Enter an instruction of 1–2000 characters.")
        text = text.strip()
        with self.lock:
            if self.phase != "connected":
                raise ValueError("Connect PETEY to Discord before giving instructions.")
            proposal = self._admin_proposal(text)
            if proposal is not None:
                self.admin_proposals.append(proposal)
                self._event("status", "Server action prepared for your approval.")
                return self.status()
            if sum(item["status"] == "queued" for item in self.instructions) >= 10:
                raise ValueError("Ten instructions are already queued. Wait for them to finish.")
            self.sequence += 1
            self.instructions.append({"id": self.sequence, "text": text, "status": "queued"})
            self.revision += 1
        return self.status()

    def _admin_proposal(self, text):
        prefix = r"(?:petey[,:]?\s*)?(?:please\s+)?"
        create = re.fullmatch(
            prefix + r"(?:create|make|add)\s+(?:a\s+)?(?:new\s+)?(?:text\s+)?channel(?:\s+(?:called|named))?\s+[#`\"]?([a-z0-9][a-z0-9 _-]{0,99})[`\"]?[.!]?",
            text, re.I,
        )
        action = data = summary = None
        if create:
            name = "-".join(create.group(1).strip().lower().split()).rstrip("-_.")
            action, data, summary = "create_channel", {"name": name}, f"Create text channel #{name}"
        else:
            delete = re.fullmatch(
                prefix + r"delete\s+(?:the\s+)?(?:current\s+|this\s+)?channel(?:\s+[#`\"]?([a-z0-9_-]+)[`\"]?)?[.!]?",
                text, re.I,
            )
            clear = re.fullmatch(
                prefix + r"(?:prune|clear|clean)\s+(?:(?:the|a)\s+)?(?:current\s+|this\s+)?channel(?:['’]s)?(?:\s+(?:of\s+)?(?:the\s+)?(?:last\s+)?(\d{1,3})\s+messages?)?[.!]?",
                text, re.I,
            )
            if delete:
                selected = self.selection["channel"].lstrip("#")
                named = str(delete.group(1) or selected)
                if named.casefold() != selected.casefold():
                    raise ValueError("Select the channel you want to delete, then ask PETEY to delete this channel.")
                action = "delete_channel"
                data = {"channel_id": self.selection["channel_id"], "name": selected}
                summary = f"Permanently delete #{selected}"
            elif clear:
                count = int(clear.group(1) or 50)
                if not 1 <= count <= 100:
                    raise ValueError("Choose 1–100 recent messages to clear.")
                action = "clear_messages"
                data = {"channel_id": self.selection["channel_id"], "count": count}
                summary = f"Delete up to {count} recent messages from {self.selection['channel']}"
        if action is None:
            return None
        return {
            "id": uuid.uuid4().hex, "action": action, "summary": summary,
            "data": data, "guild_id": self.selection["guild_id"],
            "status": "pending", "created_at": time.time(),
        }

    def resolve_admin_proposal(self, proposal_id, approve=False):
        with self.lock:
            proposal = next((item for item in self.admin_proposals if item["id"] == proposal_id), None)
            if proposal is None or proposal["status"] != "pending":
                raise ValueError("That Discord server-action proposal is no longer pending.")
            if time.time() - proposal["created_at"] > 600:
                proposal["status"] = "expired"
                raise ValueError("That Discord server-action proposal expired. Ask PETEY again.")
            if not approve:
                proposal["status"] = "rejected"
                return self.status()
            proposal["status"] = "running"
        transport = self.transport_factory(self.state.discord_bot_token)
        try:
            if proposal["action"] == "create_channel":
                result = transport.create_text_channel(proposal["guild_id"], proposal["data"]["name"])
            elif proposal["action"] == "delete_channel":
                result = transport.delete_channel(proposal["data"]["channel_id"])
            else:
                result = transport.clear_recent_messages(
                    proposal["data"]["channel_id"], proposal["data"]["count"]
                )
        except Exception as exc:
            with self.lock:
                proposal["status"] = "failed"
                proposal["error"] = str(exc) if isinstance(exc, DiscordError) else "Discord could not complete this action."
            raise
        finally:
            transport.close()
        with self.lock:
            proposal["status"] = "completed"
            proposal["result"] = result
            self._event("status", proposal["summary"] + " completed.")
        return self.status()

    @staticmethod
    def _is_transient_model_error(exc):
        detail = str(exc).casefold()
        return any(marker in detail for marker in (
            "http 503", '"code": 503', "high demand", "temporarily unavailable",
            '"status": "unavailable"',
        ))

    def _reply_with_typing(self, transport, conversation, turn, guidance, owner_instruction):
        """Generate a reply while periodically refreshing Discord's typing indicator."""
        try:
            transport.typing()
        except DiscordError:
            pass

        finished = threading.Event()
        outcome = {}

        def generate():
            try:
                for attempt, delay in enumerate((2, 5, 0)):
                    try:
                        outcome["text"] = conversation.reply(
                            turn, guidance, owner_instruction
                        )
                        return
                    except AIProviderError as exc:
                        detail = str(exc).casefold()
                        if "empty response" in detail or "returned no text" in detail:
                            outcome["text"] = ""
                            return
                        if self._is_transient_model_error(exc) and attempt < 2:
                            if self.stop.wait(delay):
                                outcome["text"] = ""
                                return
                            continue
                        outcome["error"] = exc
                        return
                    except Exception as exc:
                        outcome["error"] = exc
                        return
            finally:
                finished.set()

        generator = threading.Thread(target=generate, daemon=True, name="petey-discord-reply")
        generator.start()
        while not finished.wait(self.typing_interval):
            if self.stop.is_set():
                continue
            try:
                transport.typing()
            except DiscordError:
                pass
        if "error" in outcome:
            raise outcome["error"]
        return outcome.get("text", "")

    def _handle_media_interaction(self, interaction):
        parsed = parse_media_interaction(interaction)
        if parsed is None:
            return
        transport = self.transport_factory(self.state.discord_bot_token)
        interaction_id = str(interaction.get("id") or "")
        interaction_token = str(interaction.get("token") or "")
        application_id = str(interaction.get("application_id") or "")
        deferred = False
        try:
            transport.defer_interaction(interaction_id, interaction_token)
            deferred = True
            if str(interaction.get("guild_id") or "") != self.selection["guild_id"]:
                raise ValueError("PETEY Desktop is connected to a different Discord server.")
            if self.media_jobs_getter is None:
                raise ValueError("Discord media commands are unavailable in this PETEY session.")
            deapi = self.state.ai_provider.get("deapi", {})
            if (parsed["operation"] != "txt2audio"
                    and not (deapi.get("api_key") or os.getenv("DEAPI_KEY", "").strip())):
                raise ValueError("Add a deAPI key in PETEY Desktop before using media commands.")
            source = None
            if parsed["source_kind"]:
                source = transport.download_interaction_attachment(
                    parsed["attachment"], parsed["source_kind"]
                )
            operation = parsed["operation"]
            job = self.media_jobs_getter().submit(
                operation=operation,
                prompt=parsed["prompt"],
                installation_id=self.state.installation_id,
                model_slug=self.state.selected_model(operation),
                source=source,
                parameters=parsed["parameters"],
                speech_settings=self.state.speech,
                ai_config=self.state.ai_provider,
            )
            transport.edit_interaction(
                application_id, interaction_token,
                f"PETEY queued /{parsed['command']} as {job['id'][:8]}. Generating…",
            )
            self._event("status", f"Discord /{parsed['command']} queued media job {job['id'][:8]}.")
            threading.Thread(
                target=self._watch_media_interaction,
                args=(job["id"], application_id, interaction_token, parsed["command"]),
                daemon=True, name=f"petey-discord-media-{job['id'][:8]}",
            ).start()
        except Exception as exc:
            message = str(exc) if isinstance(exc, (ValueError, DiscordError)) else "PETEY could not queue this media command."
            if deferred:
                try:
                    transport.edit_interaction(application_id, interaction_token, f"/{parsed['command']} failed: {message}")
                except Exception:
                    pass
            self._event("error", f"Discord /{parsed['command']} failed: {message}")
        finally:
            transport.close()

    def _watch_media_interaction(self, job_id, application_id, interaction_token, command):
        # Discord interaction tokens last 15 minutes. Leave time to post a final
        # progress message before the token expires.
        deadline = time.monotonic() + 840
        while time.monotonic() < deadline:
            job = self.media_jobs_getter().get(job_id)
            if not job:
                message = f"/{command} failed: the desktop media job disappeared."
                break
            if job["status"] == "completed":
                result = job.get("result") or {}
                url = str(result.get("result_url") or "")
                message = f"/{command} completed. {url}" if url else f"/{command} completed. Open PETEY's Gallery to view it."
                break
            if job["status"] == "failed":
                message = f"/{command} failed: {job.get('error') or 'the media provider returned an error.'}"
                break
            time.sleep(2)
        else:
            message = f"/{command} is still running. Check PETEY Desktop's Media screen for progress."
        transport = self.transport_factory(self.state.discord_bot_token)
        try:
            transport.edit_interaction(application_id, interaction_token, message)
        except Exception as exc:
            self._event("error", f"Discord could not post the /{command} result: {exc}")
        finally:
            transport.close()

    def _run(self, token, config, personality=""):
        transport = None
        failed = False
        try:
            transport = self.transport_factory(token)
            if hasattr(transport, "set_interaction_handler"):
                transport.set_interaction_handler(self._handle_media_interaction)
            connected = transport.connect(self.selection["guild_id"], self.selection["channel_id"])
            identity = connected["identity"]
            with self.lock:
                if self.stop.is_set():
                    return
                self.selection["bot_name"] = identity["name"]
                self.selection["channel"] = "#" + connected["channel_name"]
                self.phase = "connected"
            self.state.update_discord_last_location(
                self.selection["guild_id"], self.selection["channel_id"],
                self.selection["guild"], self.selection["channel"],
            )
            if self.media_jobs_getter is not None and hasattr(transport, "register_media_commands"):
                try:
                    transport.register_media_commands(identity["id"], self.selection["guild_id"])
                    self._event("status", "Discord media slash commands are ready.")
                except (DiscordError, ValueError) as exc:
                    self._event("error", f"Discord slash commands could not be registered: {exc}")
            self._event("status", "Connected. Listening to the channel before joining in.")
            activity = RoomActivity(
                identity["name"], time.monotonic(), pace=self.pace,
                priority_bypasses_ceiling=True,
                priority_delay_cap=2,
            )
            conversation = RoomConversation(
                self.provider_factory(config), personality, self.room_prompt
            )
            next_poll = 0

            def observe(messages):
                now = time.monotonic()
                for message in messages:
                    if not message.addressed and self._matches_watched_topic(message.text):
                        message = type(message)(
                            message.id, message.nickname, message.text, addressed=True
                        )
                    if activity.observe(message, now):
                        self._event("received", message.text, message.nickname)

            while not self.stop.is_set():
                now = time.monotonic()
                if now >= next_poll:
                    observe(transport.poll())
                    next_poll = time.monotonic() + 4
                with self.lock:
                    paused = self.paused
                    pace = self.pace
                    room_prompt = self.room_prompt
                    revision = self.revision
                    instruction = next((item for item in self.instructions if item["status"] == "queued"), None)
                    guidance = "\n".join(item["text"] for item in self.instructions
                                         if item["status"] in {"completed", "queued"})[-8000:]
                conversation.room_prompt = room_prompt
                if paused:
                    activity.pending.clear()
                    self.stop.wait(1)
                    continue
                activity.set_pace(pace)
                turn = activity.next_turn(time.monotonic(), instructed=instruction is not None)
                if turn is None:
                    self.stop.wait(1)
                    continue
                delivered = False
                try:
                    try:
                        text = self._reply_with_typing(
                            transport, conversation, turn, guidance,
                            instruction["text"] if instruction else "",
                        )
                    except Exception as exc:
                        if instruction is not None:
                            with self.lock:
                                instruction["status"] = "failed"
                        if isinstance(exc, AIProviderError) and self._is_transient_model_error(exc):
                            detail = "The chat model is temporarily busy after automatic retries"
                        elif isinstance(exc, AIProviderError):
                            detail = str(exc).rstrip(".")
                        else:
                            detail = f"unexpected {type(exc).__name__} from the chat model"
                        self._event(
                            "error", f"Reply cancelled: {detail}. Discord remains connected."
                        )
                        continue
                    with self.lock:
                        if self.stop.is_set() or self.paused or revision != self.revision:
                            continue
                        if text:
                            transport.send(text)
                            delivered = True
                            conversation.delivered(text)
                            self._event("sent", text, identity["name"])
                        if instruction is not None:
                            instruction["status"] = "completed"
                            self._event("status", "Instruction completed." if text else "Instruction applied; no public message needed.")
                finally:
                    activity.finish(time.monotonic(), sent=delivered)
        except Exception as exc:
            failed = True
            with self.lock:
                self.error = str(exc) if isinstance(exc, (DiscordError, ValueError)) else (
                    "Discord or the chat model could not complete the operation. Check the channel and model settings, then reconnect. No message was retried."
                )
                self.phase = "error"
                for instruction in self.instructions:
                    if instruction["status"] == "queued":
                        instruction["status"] = "failed"
            self._event("error", self.error)
        finally:
            if transport is not None:
                transport.close()
            with self.lock:
                if not failed:
                    self.phase = "disconnected"
                for instruction in self.instructions:
                    if instruction["status"] == "queued":
                        instruction["status"] = "cancelled"

    def close(self):
        self.disconnect()
        if self.thread is not None:
            self.thread.join(timeout=5)
