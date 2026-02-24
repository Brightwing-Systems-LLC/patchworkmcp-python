"""PatchworkMCP — Drop-in feedback tool for Python MCP servers."""

__version__ = "0.1.0"

from .feedback_tool import (
    FASTMCP_TOOL_KWARGS,
    TOOL_DESCRIPTION,
    TOOL_INPUT_SCHEMA,
    TOOL_NAME,
    get_tool_definition,
    register_feedback_tool,
    send_feedback,
    send_feedback_sync,
)

__all__ = [
    "FASTMCP_TOOL_KWARGS",
    "TOOL_DESCRIPTION",
    "TOOL_INPUT_SCHEMA",
    "TOOL_NAME",
    "get_tool_definition",
    "register_feedback_tool",
    "send_feedback",
    "send_feedback_sync",
]
