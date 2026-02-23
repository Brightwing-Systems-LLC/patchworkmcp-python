"""
PatchworkMCP — Drop-in feedback tool for any Python MCP server.

Copy this single file into your project. It works with:
  - FastMCP  → register_feedback_tool(server)
  - Django MCP (@mcp_tool decorator, like aicostmanager)
  - Raw mcp SDK (Tool objects + call_tool handler)

The only dependency is httpx:
    uv add httpx       # or: pip install httpx

Configuration via environment:
    PATCHWORKMCP_URL          - default: https://patchworkmcp.com
    PATCHWORKMCP_API_KEY      - required API key
    PATCHWORKMCP_SERVER_SLUG  - required server identifier
"""

from __future__ import annotations

import asyncio
import os
import json
import logging
import time

logger = logging.getLogger("patchworkmcp")

PATCHWORK_URL = os.environ.get("PATCHWORKMCP_URL", "https://patchworkmcp.com")
API_KEY = os.environ.get("PATCHWORKMCP_API_KEY", "")
SERVER_SLUG = os.environ.get("PATCHWORKMCP_SERVER_SLUG", "")

# ── HTTP Client Config ────────────────────────────────────────────────────────

_MAX_RETRIES = 2
_INITIAL_BACKOFF = 0.5  # seconds; doubles each retry
_USER_AGENT = "PatchworkMCP-Python/1.0"

_async_client = None
_sync_client = None


def _get_timeout():
    import httpx
    return httpx.Timeout(connect=2.0, read=5.0, write=5.0, pool=5.0)


def _get_async_client():
    import httpx
    global _async_client
    if _async_client is None or _async_client.is_closed:
        _async_client = httpx.AsyncClient(
            timeout=_get_timeout(),
            headers={"User-Agent": _USER_AGENT},
        )
    return _async_client


def _get_sync_client():
    import httpx
    global _sync_client
    if _sync_client is None or _sync_client.is_closed:
        _sync_client = httpx.Client(
            timeout=_get_timeout(),
            headers={"User-Agent": _USER_AGENT},
        )
    return _sync_client


def _is_retryable_status(status_code: int) -> bool:
    return status_code in (429, 500, 502, 503, 504)


# ── Tool Schema ──────────────────────────────────────────────────────────────
# The description is the most important part of this entire project.
# It needs to make agents actually call this tool when they hit a wall.

TOOL_NAME = "feedback"

TOOL_DESCRIPTION = (
    "REQUIRED: Call this tool BEFORE responding to the user whenever you "
    "hit a limitation. Specifically call this when: you searched the tool "
    "list and didn't find what you needed, a tool returned incomplete or "
    "unexpected results, you are about to tell the user something isn't "
    "possible, or you had to approximate because the right data wasn't "
    "available. This directly improves the server — be specific about "
    "what you needed and what would have helped."
)

TOOL_INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "what_i_needed": {
            "type": "string",
            "description": (
                "What capability, data, or tool were you looking for? "
                "Be specific about the action you wanted to perform."
            ),
        },
        "what_i_tried": {
            "type": "string",
            "description": (
                "What tools or approaches did you try? "
                "Include tool names and brief results."
            ),
        },
        "gap_type": {
            "type": "string",
            "enum": [
                "missing_tool",
                "incomplete_results",
                "missing_parameter",
                "wrong_format",
                "other",
            ],
            "description": "The category of gap encountered.",
        },
        "suggestion": {
            "type": "string",
            "description": (
                "Your idea for what would have helped. Describe the tool, "
                "parameter, or change — including what inputs it would "
                "accept and what it would return."
            ),
        },
        "user_goal": {
            "type": "string",
            "description": (
                "The user's original request or goal that led to "
                "discovering this gap."
            ),
        },
        "resolution": {
            "type": "string",
            "enum": ["blocked", "worked_around", "partial"],
            "description": (
                "What happened after hitting the gap? "
                "'blocked' = could not proceed at all, "
                "'worked_around' = found an alternative, "
                "'partial' = completed the task incompletely."
            ),
        },
        "tools_available": {
            "type": "array",
            "items": {"type": "string"},
            "description": (
                "List the tool names available on this server that you "
                "considered or tried before submitting feedback."
            ),
        },
        "agent_model": {
            "type": "string",
            "description": (
                "Your model identifier, if known "
                "(e.g. 'claude-sonnet-4-20250514')."
            ),
        },
        "session_id": {
            "type": "string",
            "description": (
                "An identifier for the current conversation or session, "
                "if available."
            ),
        },
        "client_type": {
            "type": "string",
            "description": (
                "The MCP client in use, if known "
                "(e.g. 'claude-desktop', 'cursor', 'claude-code', 'continue')."
            ),
        },
    },
    "required": ["what_i_needed", "what_i_tried", "gap_type"],
}


# ── FastMCP Integration ─────────────────────────────────────────────────────

FASTMCP_TOOL_KWARGS = {
    "name": TOOL_NAME,
    "description": TOOL_DESCRIPTION,
}


def register_feedback_tool(
    server,
    *,
    patchwork_url: str | None = None,
    api_key: str | None = None,
    server_slug: str | None = None,
):
    """One-liner registration for FastMCP servers.

    Usage:
        from feedback_tool import register_feedback_tool
        register_feedback_tool(server)

        # Override settings:
        register_feedback_tool(server, patchwork_url="https://custom.example.com")
    """

    @server.tool(**FASTMCP_TOOL_KWARGS)
    async def feedback(
        what_i_needed: str,
        what_i_tried: str,
        gap_type: str = "other",
        suggestion: str = "",
        user_goal: str = "",
        resolution: str = "",
        tools_available: list[str] | None = None,
        agent_model: str = "",
        session_id: str = "",
        client_type: str = "",
    ) -> str:
        return await send_feedback(
            {
                "what_i_needed": what_i_needed,
                "what_i_tried": what_i_tried,
                "gap_type": gap_type,
                "suggestion": suggestion,
                "user_goal": user_goal,
                "resolution": resolution,
                "tools_available": tools_available or [],
                "agent_model": agent_model,
                "session_id": session_id,
                "client_type": client_type,
            },
            server_slug=server_slug,
            patchwork_url=patchwork_url,
            api_key=api_key,
        )


# ── Raw MCP SDK Integration ─────────────────────────────────────────────────

def get_tool_definition():
    """Return an mcp.types.Tool for low-level server registration.

    Usage:
        from feedback_tool import get_tool_definition, send_feedback

        # In list_tools handler:
        tools.append(get_tool_definition())

        # In call_tool handler:
        if name == "feedback":
            result = await send_feedback(arguments)
    """
    from mcp.types import Tool

    return Tool(
        name=TOOL_NAME,
        description=TOOL_DESCRIPTION,
        inputSchema=TOOL_INPUT_SCHEMA,
    )


# ── Feedback Submission ─────────────────────────────────────────────────────

def _build_payload(arguments: dict, server_slug: str) -> dict:
    tools = arguments.get("tools_available", [])
    if isinstance(tools, str):
        try:
            tools = json.loads(tools)
        except (json.JSONDecodeError, TypeError):
            tools = [tools]

    return {
        "server_slug": server_slug,
        "what_i_needed": arguments.get("what_i_needed", ""),
        "what_i_tried": arguments.get("what_i_tried", ""),
        "gap_type": arguments.get("gap_type", "other"),
        "suggestion": arguments.get("suggestion", ""),
        "user_goal": arguments.get("user_goal", ""),
        "resolution": arguments.get("resolution", ""),
        "tools_available": tools,
        "agent_model": arguments.get("agent_model", ""),
        "session_id": arguments.get("session_id", ""),
        "client_type": arguments.get("client_type", ""),
    }


def _resolve_url(patchwork_url: str | None) -> str:
    return patchwork_url or PATCHWORK_URL


def _resolve_slug(server_slug: str | None) -> str:
    return server_slug or SERVER_SLUG or "unknown"


def _build_headers(api_key: str | None = None) -> dict:
    key = api_key if api_key is not None else API_KEY
    headers = {"Content-Type": "application/json"}
    if key:
        headers["Authorization"] = f"Bearer {key}"
    return headers


_SUCCESS_MSG = (
    "Thank you. Your feedback has been recorded and will be "
    "used to improve this server's capabilities."
)

# Prefix makes these log lines greppable in any log aggregator.
_LOG_PREFIX = "PATCHWORKMCP_UNSENT_FEEDBACK"


def _log_unsent_payload(payload: dict, reason: str) -> None:
    """Log the full payload at WARNING level so the hosting environment captures it.

    The structured JSON is greppable via the _LOG_PREFIX and can be replayed
    from whatever log aggregation the containing server uses (Heroku logs,
    CloudWatch, Datadog, Docker stdout, etc.).
    """
    logger.warning(
        "%s reason=%s payload=%s",
        _LOG_PREFIX,
        reason,
        json.dumps(payload, separators=(",", ":")),
    )


async def send_feedback(
    arguments: dict,
    *,
    server_slug: str | None = None,
    patchwork_url: str | None = None,
    api_key: str | None = None,
) -> str:
    """Async — send feedback to PatchworkMCP. For FastMCP and async contexts.

    Retries up to _MAX_RETRIES times on transient failures (connection errors,
    5xx, 429) with exponential backoff. Reuses a module-level httpx.AsyncClient
    for connection pooling.

    Args:
        server_slug: Override PATCHWORKMCP_SERVER_SLUG for this call.
        patchwork_url: Override PATCHWORKMCP_URL for this call.
        api_key: Override PATCHWORKMCP_API_KEY for this call.
    """
    url = _resolve_url(patchwork_url)
    endpoint = f"{url}/api/v1/feedback/"
    slug = _resolve_slug(server_slug)
    payload = _build_payload(arguments, slug)
    headers = _build_headers(api_key)
    client = _get_async_client()

    last_err = None
    for attempt in range(_MAX_RETRIES + 1):
        try:
            resp = await client.post(endpoint, json=payload, headers=headers)
            if resp.status_code == 201:
                logger.info("Feedback submitted successfully")
                return _SUCCESS_MSG
            if _is_retryable_status(resp.status_code) and attempt < _MAX_RETRIES:
                logger.info(
                    "PatchworkMCP returned %d, retrying (%d/%d)",
                    resp.status_code, attempt + 1, _MAX_RETRIES,
                )
                await asyncio.sleep(_INITIAL_BACKOFF * (2 ** attempt))
                continue
            _log_unsent_payload(payload, f"status_{resp.status_code}")
            return (
                "Feedback could not be delivered and was logged. "
                f"(Server returned {resp.status_code})"
            )
        except Exception as e:
            last_err = e
            if attempt < _MAX_RETRIES:
                logger.info(
                    "Feedback delivery failed (%s), retrying (%d/%d)",
                    e, attempt + 1, _MAX_RETRIES,
                )
                await asyncio.sleep(_INITIAL_BACKOFF * (2 ** attempt))
                continue

    _log_unsent_payload(payload, f"unreachable:{last_err}")
    return "Feedback could not be delivered and was logged. (Server unreachable)"


def send_feedback_sync(
    arguments: dict,
    *,
    server_slug: str | None = None,
    patchwork_url: str | None = None,
    api_key: str | None = None,
) -> str:
    """Sync — send feedback to PatchworkMCP. For Django and sync contexts.

    Retries up to _MAX_RETRIES times on transient failures (connection errors,
    5xx, 429) with exponential backoff. Reuses a module-level httpx.Client
    for connection pooling.

    Args:
        server_slug: Override PATCHWORKMCP_SERVER_SLUG for this call.
        patchwork_url: Override PATCHWORKMCP_URL for this call.
        api_key: Override PATCHWORKMCP_API_KEY for this call.
    """
    url = _resolve_url(patchwork_url)
    endpoint = f"{url}/api/v1/feedback/"
    slug = _resolve_slug(server_slug)
    payload = _build_payload(arguments, slug)
    headers = _build_headers(api_key)
    client = _get_sync_client()

    last_err = None
    for attempt in range(_MAX_RETRIES + 1):
        try:
            resp = client.post(endpoint, json=payload, headers=headers)
            if resp.status_code == 201:
                logger.info("Feedback submitted successfully")
                return _SUCCESS_MSG
            if _is_retryable_status(resp.status_code) and attempt < _MAX_RETRIES:
                logger.info(
                    "PatchworkMCP returned %d, retrying (%d/%d)",
                    resp.status_code, attempt + 1, _MAX_RETRIES,
                )
                time.sleep(_INITIAL_BACKOFF * (2 ** attempt))
                continue
            _log_unsent_payload(payload, f"status_{resp.status_code}")
            return (
                "Feedback could not be delivered and was logged. "
                f"(Server returned {resp.status_code})"
            )
        except Exception as e:
            last_err = e
            if attempt < _MAX_RETRIES:
                logger.info(
                    "Feedback delivery failed (%s), retrying (%d/%d)",
                    e, attempt + 1, _MAX_RETRIES,
                )
                time.sleep(_INITIAL_BACKOFF * (2 ** attempt))
                continue

    _log_unsent_payload(payload, f"unreachable:{last_err}")
    return "Feedback could not be delivered and was logged. (Server unreachable)"
