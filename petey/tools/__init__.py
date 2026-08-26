"""Modular capabilities Petey may offer to language models."""

from petey.tools.media import build_media_tools
from petey.tools.registry import ToolRegistry, ToolSpec


def build_desktop_tool_registry(
    state, media_jobs_getter, memory, temporary: bool = False
) -> ToolRegistry:
    """Compose Petey's built-in capabilities in one extension point."""
    tools = []
    tools.extend(
        build_media_tools(
            state,
            media_jobs_getter,
            memory,
            record_memory=not temporary,
        )
    )
    return ToolRegistry(tools)


__all__ = [
    "ToolRegistry",
    "ToolSpec",
    "build_desktop_tool_registry",
    "build_media_tools",
]
