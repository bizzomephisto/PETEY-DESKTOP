"""Provider-neutral text generation for the standalone assistant."""

from __future__ import annotations

import base64
import os
import re
import json
import uuid
from urllib.parse import urlparse

import requests


class AIProviderError(RuntimeError):
    pass


class AIProvider:
    def __init__(self, config: dict | None = None):
        self.config = config or {}

    @property
    def provider(self) -> str:
        return str(self.config.get("provider") or "gemini")

    def _selected(self) -> dict:
        return dict(self.config.get(self.provider) or {})

    def _api_key(self) -> str:
        selected = self._selected()
        environment_keys = {
            "gemini": "GEMINI_API_KEY",
            "openai": "OPENAI_API_KEY",
            "local": "LOCAL_AI_API_KEY",
        }
        return str(selected.get("api_key") or os.getenv(environment_keys[self.provider], "")).strip()

    def public_config(self) -> dict:
        providers = {}
        environment_keys = {
            "gemini": "GEMINI_API_KEY",
            "openai": "OPENAI_API_KEY",
            "local": "LOCAL_AI_API_KEY",
        }
        for name in ("gemini", "openai", "local"):
            selected = dict(self.config.get(name) or {})
            effective_key = str(selected.get("api_key") or os.getenv(environment_keys[name], "")).strip()
            providers[name] = {
                "model": str(selected.get("model") or ""),
                "base_url": str(selected.get("base_url") or "") if name == "local" else "",
                "has_api_key": bool(effective_key),
                "api_key_source": "saved" if selected.get("api_key") else "environment" if effective_key else "none",
                "thinking_enabled": bool(selected.get("thinking_enabled", True)),
            }
        return {
            "provider": self.provider,
            "providers": providers,
            "vision_model": str(
                (self.config.get("gemini") or {}).get("vision_model")
                or "gemini-2.5-flash"
            ),
            "vision_has_api_key": providers["gemini"]["has_api_key"],
            **providers[self.provider],
        }

    def complete(self, prompt: str, system_message: str, history: list[dict] | None = None) -> str:
        if self.provider == "gemini":
            return self._gemini(prompt, system_message, history or [])
        if self.provider in {"openai", "local"}:
            return self._openai_compatible(prompt, system_message, history or [])
        raise AIProviderError("Unsupported AI provider.")

    def complete_with_tools(
        self,
        prompt: str,
        system_message: str,
        history: list[dict] | None,
        tools: list[dict],
        execute_tool,
        max_rounds: int = 3,
    ) -> tuple[str, list[dict]]:
        """Run an OpenAI-compatible tool loop with duplicate-call protection."""
        if not tools or self.provider not in {"openai", "local"}:
            return self.complete(prompt, system_message, history), []

        selected = self._selected()
        api_key = self._api_key()
        if self.provider == "openai" and not api_key:
            raise AIProviderError("OpenAI needs an API key in Settings or OPENAI_API_KEY.")
        model = str(selected.get("model") or "").strip()
        if not model:
            raise AIProviderError("Choose or enter a model name.")
        base_url = (
            "https://api.openai.com/v1"
            if self.provider == "openai"
            else str(selected.get("base_url") or "http://localhost:1234/v1").rstrip("/")
        )
        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        messages = [{"role": "system", "content": system_message}]
        messages.extend(
            {
                "role": "assistant" if item.get("role") == "assistant" else "user",
                "content": str(item.get("content") or ""),
            }
            for item in (history or [])
        )
        messages.append({"role": "user", "content": prompt})
        events = []
        executed = {}

        for _round in range(max(1, min(5, int(max_rounds)))):
            request_payload = {
                "model": model,
                "messages": messages,
                "tools": tools,
                "tool_choice": "auto",
            }
            if not bool(selected.get("thinking_enabled", True)):
                if self.provider == "local" or model.startswith(("gpt-5", "o1", "o3", "o4")):
                    request_payload["reasoning_effort"] = "none"
            try:
                response = requests.post(
                    f"{base_url}/chat/completions",
                    headers=headers,
                    json=request_payload,
                    timeout=120,
                )
                response.raise_for_status()
                message = response.json()["choices"][0]["message"]
            except requests.RequestException as exc:
                if self.provider == "local":
                    raise AIProviderError(self._local_connection_help(base_url, exc)) from exc
                raise AIProviderError(f"Could not reach OpenAI: {exc}") from exc
            except (ValueError, KeyError, IndexError, TypeError) as exc:
                raise AIProviderError("The model returned an unreadable tool response.") from exc

            content = self._message_content(message.get("content", ""))
            tool_calls = self._normalize_tool_calls(message.get("tool_calls"), content)
            if not tool_calls:
                if not content:
                    raise AIProviderError("The model returned an empty response.")
                return self._clean_output(content), events

            assistant_content = re.sub(
                r"<tool_call>.*?</tool_call>", "", content, flags=re.DOTALL
            ).strip()
            messages.append(
                {
                    "role": "assistant",
                    "content": assistant_content or None,
                    "tool_calls": tool_calls,
                }
            )
            for call in tool_calls:
                function = call["function"]
                try:
                    arguments = json.loads(function.get("arguments") or "{}")
                    if not isinstance(arguments, dict):
                        raise ValueError
                    cache_key = f"{function['name']}:{json.dumps(arguments, sort_keys=True)}"
                    if cache_key in executed:
                        result = {**executed[cache_key], "duplicate_call_ignored": True}
                    else:
                        result = execute_tool(function["name"], arguments)
                        executed[cache_key] = result
                except (ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
                    result = {"status": "error", "error": f"Invalid tool call: {exc}"}
                except Exception as exc:
                    result = {"status": "error", "error": str(exc)}
                events.append({"name": function["name"], "result": result})
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": call["id"],
                        "content": json.dumps(result, ensure_ascii=False),
                    }
                )

        if events:
            final = events[-1]["result"]
            return str(final.get("message") or final.get("error") or "The tool request finished."), events
        raise AIProviderError("The model did not finish its tool request.")

    @staticmethod
    def _message_content(content) -> str:
        if isinstance(content, list):
            return "".join(
                str(part.get("text") or "") for part in content if isinstance(part, dict)
            ).strip()
        return str(content or "").strip()

    @staticmethod
    def _normalize_tool_calls(raw_calls, content: str) -> list[dict]:
        calls = raw_calls if isinstance(raw_calls, list) else []
        if not calls and "<tool_call>" in content:
            calls = []
            for match in re.findall(r"<tool_call>\s*(.*?)\s*</tool_call>", content, re.DOTALL):
                try:
                    parsed = json.loads(match)
                    calls.append({"function": parsed})
                except (json.JSONDecodeError, TypeError):
                    continue
        normalized = []
        for call in calls:
            function = call.get("function") if isinstance(call, dict) else None
            if not isinstance(function, dict) or not function.get("name"):
                continue
            arguments = function.get("arguments", "{}")
            if isinstance(arguments, dict):
                arguments = json.dumps(arguments)
            normalized.append(
                {
                    "id": str(call.get("id") or f"call_{uuid.uuid4().hex}"),
                    "type": "function",
                    "function": {
                        "name": str(function["name"]),
                        "arguments": str(arguments or "{}"),
                    },
                }
            )
        return normalized

    def _gemini(self, prompt: str, system_message: str, history: list[dict]) -> str:
        selected = self._selected()
        api_key = self._api_key()
        if not api_key:
            raise AIProviderError("Gemini needs an API key in Settings or GEMINI_API_KEY.")
        model = str(selected.get("model") or "gemini-2.5-flash")
        contents = []
        for item in history:
            contents.append(
                {
                    "role": "model" if item.get("role") == "assistant" else "user",
                    "parts": [{"text": str(item.get("content") or "")}],
                }
            )
        contents.append({"role": "user", "parts": [{"text": prompt}]})
        generation_config = {"temperature": 0.8}
        if not bool(selected.get("thinking_enabled", True)):
            if model.startswith("gemini-2.5") and "pro" not in model.lower():
                generation_config["thinkingConfig"] = {"thinkingBudget": 0}
            elif model.startswith("gemini-3"):
                generation_config["thinkingConfig"] = {"thinkingLevel": "minimal"}
        try:
            response = requests.post(
                f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
                headers={"Content-Type": "application/json", "x-goog-api-key": api_key},
                json={
                    "systemInstruction": {"parts": [{"text": system_message}]},
                    "contents": contents,
                    "generationConfig": generation_config,
                },
                timeout=90,
            )
        except requests.RequestException as exc:
            raise AIProviderError(f"Could not reach Gemini: {exc}") from exc
        return self._response_text(response, "Gemini")

    def describe_image(
        self,
        image_data: bytes,
        content_type: str,
        user_request: str = "",
    ) -> str:
        """Inspect an image with the independently configured Gemini vision model."""
        gemini = dict(self.config.get("gemini") or {})
        api_key = str(gemini.get("api_key") or os.getenv("GEMINI_API_KEY", "")).strip()
        if not api_key:
            raise AIProviderError(
                "Gemini vision needs an API key. Select Google Gemini in Settings, save "
                "its key, then switch back to your preferred chat provider if needed."
            )
        model = str(gemini.get("vision_model") or "gemini-2.5-flash").strip()
        if not model:
            raise AIProviderError("Choose a Gemini vision model in Settings.")
        mime_type = str(content_type or "").split(";", 1)[0].strip().lower()
        if not mime_type.startswith("image/"):
            raise AIProviderError("Gemini vision can only inspect image attachments.")
        if not image_data:
            raise AIProviderError("The attached image is empty.")

        request_context = str(user_request or "").strip()
        instruction = (
            "Inspect this image carefully for another assistant. Describe the visible people, "
            "objects, text, setting, composition, colors, and any details relevant to the user's "
            "request. Be factual, mention uncertainty, and do not invent hidden details."
        )
        if request_context:
            instruction += f"\nThe user's request is: {request_context}"
        try:
            response = requests.post(
                f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
                headers={"Content-Type": "application/json", "x-goog-api-key": api_key},
                json={
                    "contents": [{
                        "role": "user",
                        "parts": [
                            {"text": instruction},
                            {
                                "inlineData": {
                                    "mimeType": mime_type,
                                    "data": base64.b64encode(image_data).decode("ascii"),
                                }
                            },
                        ],
                    }],
                    "generationConfig": {"temperature": 0.2},
                },
                timeout=120,
            )
        except requests.RequestException as exc:
            raise AIProviderError(f"Could not reach Gemini vision: {exc}") from exc
        return self._response_text(response, "Gemini vision")

    def _openai_compatible(self, prompt: str, system_message: str, history: list[dict]) -> str:
        selected = self._selected()
        api_key = self._api_key()
        if self.provider == "openai" and not api_key:
            raise AIProviderError("OpenAI needs an API key in Settings or OPENAI_API_KEY.")
        model = str(selected.get("model") or "").strip()
        if not model:
            raise AIProviderError("Choose or enter a model name.")
        base_url = (
            "https://api.openai.com/v1"
            if self.provider == "openai"
            else str(selected.get("base_url") or "http://localhost:1234/v1").rstrip("/")
        )
        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        messages = [{"role": "system", "content": system_message}]
        messages.extend(
            {"role": "assistant" if item.get("role") == "assistant" else "user", "content": str(item.get("content") or "")}
            for item in history
        )
        messages.append({"role": "user", "content": prompt})
        request_payload = {"model": model, "messages": messages}
        if not bool(selected.get("thinking_enabled", True)):
            if self.provider == "local" or model.startswith(("gpt-5", "o1", "o3", "o4")):
                request_payload["reasoning_effort"] = "none"
        try:
            response = requests.post(
                f"{base_url}/chat/completions",
                headers=headers,
                json=request_payload,
                timeout=120,
            )
        except requests.RequestException as exc:
            if self.provider == "local":
                raise AIProviderError(self._local_connection_help(base_url, exc)) from exc
            raise AIProviderError(f"Could not reach OpenAI: {exc}") from exc
        return self._response_text(response, "OpenAI" if self.provider == "openai" else "Local AI")

    def list_models(self) -> list[str]:
        if self.provider == "gemini":
            return []
        selected = self._selected()
        base_url = (
            "https://api.openai.com/v1"
            if self.provider == "openai"
            else str(selected.get("base_url") or "http://localhost:1234/v1").rstrip("/")
        )
        headers = {}
        if self._api_key():
            headers["Authorization"] = f"Bearer {self._api_key()}"
        try:
            response = requests.get(f"{base_url}/models", headers=headers, timeout=15)
            response.raise_for_status()
            return sorted(str(item["id"]) for item in response.json().get("data", []) if item.get("id"))
        except requests.HTTPError as exc:
            label = "Local AI server" if self.provider == "local" else "OpenAI"
            raise AIProviderError(f"{label} returned HTTP {exc.response.status_code}: {exc.response.text[:300]}") from exc
        except (requests.ConnectionError, requests.Timeout) as exc:
            if self.provider == "local":
                raise AIProviderError(self._local_connection_help(base_url, exc)) from exc
            raise AIProviderError(f"Could not list OpenAI models: {exc}") from exc
        except requests.RequestException as exc:
            raise AIProviderError(f"Could not list models: {exc}") from exc
        except (ValueError, KeyError) as exc:
            raise AIProviderError(f"Could not list models: {exc}") from exc

    def embed(
        self, text: str, provider_name: str, model: str, base_url_override: str = ""
    ) -> dict:
        """Return a provider-tagged embedding with no dimension assumptions."""
        provider_name = str(provider_name)
        if provider_name not in {"gemini", "openai", "local"}:
            raise AIProviderError("Unsupported embedding provider.")
        selected = dict(self.config.get(provider_name) or {})
        environment_keys = {
            "gemini": "GEMINI_API_KEY",
            "openai": "OPENAI_API_KEY",
            "local": "LOCAL_AI_API_KEY",
        }
        api_key = str(selected.get("api_key") or os.getenv(environment_keys[provider_name], "")).strip()
        model = str(model or "").strip()
        if not model:
            raise AIProviderError("Choose an embedding model.")
        try:
            if provider_name == "gemini":
                if not api_key:
                    raise AIProviderError("Gemini embeddings need a Gemini API key.")
                response = requests.post(
                    f"https://generativelanguage.googleapis.com/v1beta/models/{model}:embedContent",
                    headers={"Content-Type": "application/json", "x-goog-api-key": api_key},
                    json={
                        "model": f"models/{model}",
                        "content": {"parts": [{"text": text}]},
                    },
                    timeout=60,
                )
                response.raise_for_status()
                vector = response.json()["embedding"]["values"]
            else:
                if provider_name == "openai" and not api_key:
                    raise AIProviderError("OpenAI embeddings need an OpenAI API key.")
                base_url = (
                    "https://api.openai.com/v1"
                    if provider_name == "openai"
                    else str(
                        base_url_override
                        or selected.get("base_url")
                        or "http://localhost:1234/v1"
                    ).rstrip("/")
                )
                headers = {"Content-Type": "application/json"}
                if api_key:
                    headers["Authorization"] = f"Bearer {api_key}"
                response = requests.post(
                    f"{base_url}/embeddings",
                    headers=headers,
                    json={"model": model, "input": text},
                    timeout=60,
                )
                response.raise_for_status()
                vector = response.json()["data"][0]["embedding"]
            values = [float(value) for value in vector]
            if not values:
                raise ValueError("empty vector")
            return {
                "values": values,
                "provider": provider_name,
                "model": model,
                "dimensions": len(values),
            }
        except AIProviderError:
            raise
        except requests.RequestException as exc:
            if provider_name == "local":
                base_url = str(
                    base_url_override
                    or selected.get("base_url")
                    or "http://localhost:1234/v1"
                ).rstrip("/")
                raise AIProviderError(self._local_connection_help(base_url, exc)) from exc
            raise AIProviderError(f"Could not create {provider_name} embedding: {exc}") from exc
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            raise AIProviderError(f"{provider_name.title()} returned an unreadable embedding.") from exc

    @staticmethod
    def _local_connection_help(base_url: str, exc: Exception) -> str:
        parsed = urlparse(base_url)
        try:
            port = parsed.port
        except ValueError:
            port = None
        if port == 11434:
            return (
                "Ollama is not reachable at http://localhost:11434. Start it with "
                "'ollama serve', then pull a model with 'ollama pull llama3.2'."
            )
        if port == 1234:
            return (
                "LM Studio is not reachable at http://localhost:1234. Open LM Studio, load a "
                "model, then start the server from the Developer tab."
            )
        return f"The local AI server is not reachable at {base_url}. Start its API server and try again."

    def _response_text(self, response: requests.Response, label: str) -> str:
        try:
            response.raise_for_status()
            data = response.json()
            if "candidates" in data:
                return self._clean_output(data["candidates"][0]["content"]["parts"][0]["text"])
            content = data["choices"][0]["message"].get("content", "")
            if isinstance(content, list):
                content = "".join(str(part.get("text") or "") for part in content if isinstance(part, dict))
            if not str(content).strip():
                raise KeyError("empty model response")
            return self._clean_output(str(content))
        except requests.HTTPError as exc:
            detail = response.text[:500]
            raise AIProviderError(f"{label} returned HTTP {response.status_code}: {detail}") from exc
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            raise AIProviderError(f"{label} returned an unreadable response.") from exc

    def _clean_output(self, content: str) -> str:
        content = str(content or "").strip()
        if not bool(self._selected().get("thinking_enabled", True)):
            content = re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL | re.IGNORECASE)
            content = re.sub(r"^.*?</think>", "", content, flags=re.DOTALL | re.IGNORECASE)
        return content.strip()
