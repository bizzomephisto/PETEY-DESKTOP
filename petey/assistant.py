"""Discord-independent conversational core for Petey."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional
from urllib.parse import urlencode

import aiohttp

from petey.ai_provider import AIProvider


PETEY_USER_ID = "PETEY"


class _EmptyMemory:
    """Safe fallback for temporary/tests; desktop mode injects DesktopMemory."""

    @staticmethod
    def get_conversation_messages(*_args):
        return []

    @staticmethod
    def search_memories(*_args):
        return ""

    @staticmethod
    def store_memory(*_args):
        return None


@dataclass(frozen=True)
class AssistantIdentity:
    installation_id: str
    conversation_id: str
    person_id: str
    display_name: str = "You"


@dataclass(frozen=True)
class AssistantAttachment:
    filename: str
    content_type: str
    data: bytes


@dataclass(frozen=True)
class AssistantReply:
    text: str
    gif_url: Optional[str] = None


class AssistantService:
    """Build prompts, retrieve memory, call the LLM, and persist both speakers."""

    def __init__(self, system_prompt: str, ai_config: dict | None = None, memory=None):
        self.system_prompt = system_prompt or "You are Petey, a friendly chatbot."
        self.ai = AIProvider(ai_config)
        self.memory = memory or _EmptyMemory()

    async def respond(
        self,
        message: str,
        identity: AssistantIdentity,
        attachment: AssistantAttachment | None = None,
        temporary: bool = False,
        temporary_history: list[dict] | None = None,
    ) -> AssistantReply:
        cleaned = (message or "").strip()
        if cleaned.endswith("+++"):
            cleaned = cleaned[:-3].strip()
        if not cleaned and attachment is None:
            raise ValueError("A message or attachment is required.")

        # Desktop requests already run outside the UI thread. Keeping database and
        # Gemini calls synchronous here avoids leaking executor threads when the
        # short-lived request event loop closes.
        messages = [] if temporary else self.memory.get_conversation_messages(
            identity.installation_id, identity.conversation_id, 8
        )
        semantic_memory = "" if temporary else self.memory.search_memories(
            cleaned or attachment.filename, identity.installation_id, 5
        )
        image_description = await self._describe_image(attachment, identity.installation_id)

        if temporary:
            history = []
            for item in (temporary_history or [])[-12:]:
                role = "assistant" if item.get("role") == "assistant" else "user"
                content = str(item.get("content") or "").strip()[:12000]
                if content:
                    history.append({"role": role, "content": content})
        else:
            history = []
            for item in messages:
                role = "assistant" if item["user_id"] == PETEY_USER_ID else "user"
                content = item["message"]
                if role == "user":
                    content = f"User {identity.display_name} said: {content}"
                history.append({"role": role, "content": content})

        stored_user_text = cleaned
        if attachment:
            stored_user_text = stored_user_text or f"[Attached {attachment.filename}]"
        if not temporary:
            self.memory.store_memory(
                identity.installation_id,
                identity.conversation_id,
                identity.person_id,
                stored_user_text,
            )

        if image_description:
            user_prompt = (
                f"User {identity.display_name} said: {cleaned}\n"
                f"[Attachment: {attachment.filename}; image description: {image_description}]"
            )
        elif attachment:
            user_prompt = (
                f"User {identity.display_name} said: {cleaned}\n"
                f"[Attachment: {attachment.filename}; type: {attachment.content_type}]"
            )
        else:
            user_prompt = f"User {identity.display_name} said: {cleaned}"

        system_parts = [
            self.system_prompt,
            f"This is Petey's standalone desktop installation {identity.installation_id}.",
            "Temporary mode is active. Do not claim to remember this conversation." if temporary else "",
            f"Relevant past context:\n{semantic_memory}" if semantic_memory else "",
            (
                "You are PETEY. Respond only to the last user message. Talk directly to the "
                "user and never prefix your answer with your own name. You can chat, remember "
                "past conversations, inspect attached images, search the web, and generate "
                "media through the desktop application's tools."
            ),
            "If you want to send a GIF or meme, include [GIF: <search query>] in your response.",
        ]
        final_system = "\n".join(part for part in system_parts if part)
        response = self.ai.complete(
            user_prompt + "\nRespond as Petey:",
            final_system,
            history,
        )
        response = self._clean_model_response(response)
        gif_query, response = self._extract_gif(response)
        gif_url = await self._fetch_gif(gif_query) if gif_query else None

        if not response and not gif_url:
            response = "I don't have anything to say right now."
        if response and not temporary:
            self.memory.store_memory(
                identity.installation_id,
                identity.conversation_id,
                PETEY_USER_ID,
                response,
            )
        return AssistantReply(text=response, gif_url=gif_url)

    async def _describe_image(
        self, attachment: AssistantAttachment | None, installation_id: str
    ) -> str | None:
        if attachment is None or not attachment.content_type.startswith("image/"):
            return None
        from petey.deapi_client import deapi
        try:
            result = await deapi.image_to_text(
                attachment.data, guild_id=installation_id
            )
            return result.strip() if result else None
        except Exception as exc:
            print(f"[ASSISTANT] Image description failed: {exc}")
            return None

    @staticmethod
    def _clean_model_response(response: str) -> str:
        response = re.sub(r"<\|[^|>]+\|>", "", response or "")
        response = re.sub(r"<\|start\|>.*", "", response, flags=re.DOTALL)
        response = re.sub(r"<\|channel\|>.*?(?=\n|$)", "", response)
        response = re.sub(r"<\|constrain\|>[\d\s.]+", "", response)
        return response.strip()

    @staticmethod
    def _extract_gif(response: str) -> tuple[str | None, str]:
        match = re.search(r"\[GIF:\s*(.*?)]", response, re.IGNORECASE)
        if not match:
            return None, response
        query = match.group(1).strip()
        cleaned = re.sub(r"\[GIF:\s*.*?]", "", response, flags=re.IGNORECASE).strip()
        return query, cleaned

    @staticmethod
    async def _fetch_gif(query: str) -> str | None:
        params = urlencode({"api_key": "dc6zaTOxFJmzC", "tag": query, "rating": "r"})
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f"https://api.giphy.com/v1/gifs/random?{params}") as response:
                    if response.status != 200:
                        return None
                    payload = await response.json()
                    return payload.get("data", {}).get("images", {}).get("original", {}).get("url")
        except aiohttp.ClientError:
            return None
