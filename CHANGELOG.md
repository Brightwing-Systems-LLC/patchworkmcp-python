# Changelog

## 0.1.0 (2026-02-24)

- Initial release
- FastMCP integration via `register_feedback_tool()`
- Raw MCP SDK integration via `get_tool_definition()` + `send_feedback()`
- Django/sync support via `send_feedback_sync()`
- Retry logic with exponential backoff
- Structured logging for failed submissions
