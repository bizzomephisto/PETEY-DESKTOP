"""Provider-neutral tool schemas, availability policies, and dispatch."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable


class ToolError(ValueError):
    pass


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    parameters: dict
    handler: Callable[[dict], dict]
    available_when: Callable[[str], bool] = lambda _message: True

    def schema(self) -> dict:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }


class ToolRegistry:
    """Small registry: adding a capability does not change chat orchestration."""

    def __init__(self, tools: list[ToolSpec] | None = None):
        self._tools: dict[str, ToolSpec] = {}
        for tool in tools or []:
            self.register(tool)

    def register(self, tool: ToolSpec) -> None:
        if not tool.name or tool.name in self._tools:
            raise ToolError(f"Tool name is empty or already registered: {tool.name}")
        self._tools[tool.name] = tool

    def schemas_for(self, user_message: str) -> list[dict]:
        return [tool.schema() for tool in self._tools.values() if tool.available_when(user_message)]

    def execute(self, name: str, arguments: dict, user_message: str) -> dict:
        tool = self._tools.get(str(name or ""))
        if tool is None or not tool.available_when(user_message):
            raise ToolError("That tool is unavailable for this request.")
        if not isinstance(arguments, dict):
            raise ToolError("Tool arguments must be a JSON object.")
        missing = [
            key for key in tool.parameters.get("required", [])
            if arguments.get(key) in {None, ""}
        ]
        if missing:
            raise ToolError(f"Missing required tool argument: {missing[0]}")
        result = tool.handler(arguments)
        if not isinstance(result, dict):
            raise ToolError("The tool returned an invalid result.")
        return result
