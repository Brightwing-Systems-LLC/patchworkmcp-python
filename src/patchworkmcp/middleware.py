"""PatchworkMCP middleware for Python MCP servers.

Provides heartbeat monitoring and feedback collection. Call `start_middleware()`
after your server starts. It handles:
  - Periodic heartbeat pings to PatchworkMCP
  - Automatic feedback collection from agents

Environment variables:
  PATCHWORKMCP_API_URL     - Base URL (default: https://app.patchworkmcp.com)
  PATCHWORKMCP_API_KEY     - Your team API key (required)
  PATCHWORKMCP_SERVER_SLUG - Your server slug (required)
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from typing import Any

import httpx

logger = logging.getLogger("patchworkmcp.middleware")

_API_URL = os.environ.get("PATCHWORKMCP_API_URL", "https://app.patchworkmcp.com")
_API_KEY = os.environ.get("PATCHWORKMCP_API_KEY", "")
_SERVER_SLUG = os.environ.get("PATCHWORKMCP_SERVER_SLUG", "")

_HEARTBEAT_INTERVAL = 60  # seconds
_MAX_RETRIES = 3


class PatchworkMiddleware:
    """Middleware that sends heartbeats and collects feedback."""

    def __init__(
        self,
        api_url: str = _API_URL,
        api_key: str = _API_KEY,
        server_slug: str = _SERVER_SLUG,
        tool_names: list[str] | None = None,
    ):
        self.api_url = api_url.rstrip("/")
        self.api_key = api_key
        self.server_slug = server_slug
        self.tool_names = tool_names or []
        self._heartbeat_task: asyncio.Task | None = None

    @property
    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    async def start(self) -> None:
        """Start the heartbeat loop."""
        if not self.api_key or not self.server_slug:
            logger.warning(
                "PatchworkMCP middleware not started: missing API_KEY or SERVER_SLUG"
            )
            return
        self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())
        logger.info("PatchworkMCP middleware started for %s", self.server_slug)

    async def stop(self) -> None:
        """Stop the heartbeat loop."""
        if self._heartbeat_task:
            self._heartbeat_task.cancel()
            self._heartbeat_task = None

    async def _heartbeat_loop(self) -> None:
        """Send heartbeat pings at regular intervals."""
        while True:
            try:
                await self._send_heartbeat()
            except Exception as e:
                logger.debug("Heartbeat failed: %s", e)
            await asyncio.sleep(_HEARTBEAT_INTERVAL)

    async def _send_heartbeat(self) -> None:
        """Send a single heartbeat ping."""
        payload = {
            "server_slug": self.server_slug,
            "tool_count": len(self.tool_names),
            "tool_names": self.tool_names,
        }
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                f"{self.api_url}/api/v1/heartbeat/",
                headers=self._headers,
                json=payload,
            )
            resp.raise_for_status()

    async def send_feedback(self, feedback: dict[str, Any]) -> dict | None:
        """Send feedback to PatchworkMCP API.

        Args:
            feedback: Dict with keys: what_i_needed, what_i_tried, gap_type, etc.

        Returns:
            API response dict or None on failure.
        """
        feedback["server_slug"] = self.server_slug

        for attempt in range(_MAX_RETRIES):
            try:
                async with httpx.AsyncClient(timeout=15.0) as client:
                    resp = await client.post(
                        f"{self.api_url}/api/v1/feedback/",
                        headers=self._headers,
                        json=feedback,
                    )
                    resp.raise_for_status()
                    return resp.json()
            except Exception as e:
                if attempt == _MAX_RETRIES - 1:
                    logger.error(
                        "UNSENT_FEEDBACK: %s — %s",
                        json.dumps(feedback),
                        e,
                    )
                    return None
                await asyncio.sleep(2**attempt)
        return None


def start_middleware(
    tool_names: list[str] | None = None,
    **kwargs: Any,
) -> PatchworkMiddleware:
    """Create and start the PatchworkMCP middleware.

    Call this after your MCP server starts. Pass the list of tool names
    your server exposes for accurate heartbeat reporting.
    """
    mw = PatchworkMiddleware(tool_names=tool_names, **kwargs)
    asyncio.create_task(mw.start())
    return mw
