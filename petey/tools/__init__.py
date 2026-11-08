"""Modular capabilities Petey may offer to language models."""

from petey.tools.media import build_media_tools
from petey.tools.registry import ToolRegistry, ToolSpec


def build_desktop_tool_registry(
    state, media_jobs_getter, memory, temporary: bool = False, mcp_manager=None,
    addon_manager=None, surface: str = "petey_desktop", general_mcp_manager=None,
    image_references=(),
) -> ToolRegistry:
    """Compose Petey's built-in capabilities in one extension point."""
    tools = []
    tools.extend(
        build_media_tools(
            state,
            media_jobs_getter,
            memory,
            record_memory=not temporary,
            surface=surface,
            image_references=image_references,
        )
    )
    if mcp_manager is not None:
        tools.extend(mcp_manager.tool_specs())
    if general_mcp_manager is not None:
        tools.extend(general_mcp_manager.tool_specs(surface=surface))
    if addon_manager is not None:
        tools.extend(addon_manager.tool_specs(surface=surface))
    return ToolRegistry(tools)


__all__ = [
    "ToolRegistry",
    "ToolSpec",
    "build_desktop_tool_registry",
    "build_media_tools",
]
