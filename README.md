# PatchworkMCP - Python

Drop-in feedback tool for Python MCP servers. Agents call this tool when they hit a limitation, and the feedback is sent to PatchworkMCP for review and action.

## Setup

1. Go to [patchworkmcp.com](https://patchworkmcp.com) and create an account
2. Create a team and generate an API key
3. Configure your server (you'll need the server slug and API key)

## Install

```bash
uv add httpx       # or: pip install httpx
```

Then copy `feedback_tool.py` into your project.

## Configure

Set these environment variables (or pass them as arguments):

| Variable | Description | Required |
|---|---|---|
| `PATCHWORKMCP_API_KEY` | Your API key from patchworkmcp.com | Yes |
| `PATCHWORKMCP_SERVER_SLUG` | Your server's slug from patchworkmcp.com | Yes |
| `PATCHWORKMCP_URL` | API endpoint (default: `https://patchworkmcp.com`) | No |

## Usage

### FastMCP

```python
from mcp.server.fastmcp import FastMCP
from feedback_tool import register_feedback_tool

INSTRUCTIONS = """
If you encounter a limitation — a missing tool, incomplete data, wrong format,
or any gap that prevents you from fully completing the user's request — call
the `feedback` tool BEFORE responding to the user. Be specific about what you
needed and what would have helped.
"""

server = FastMCP("my-server", instructions=INSTRUCTIONS)
register_feedback_tool(server)
```

### Raw MCP SDK

```python
from feedback_tool import get_tool_definition, send_feedback

# In list_tools handler:
tools.append(get_tool_definition())

# In call_tool handler:
if name == "feedback":
    result = await send_feedback(arguments)
```

### Django MCP (sync)

```python
from feedback_tool import send_feedback_sync

result = send_feedback_sync(arguments)
```

### Server Instructions (Critical)

**You must add instructions to your MCP server telling the agent to use the feedback tool.** This is the single most important step in the integration. Without explicit instructions, agents will silently ignore the feedback tool — even though it appears in their tool list. The tool's description alone is not enough to reliably trigger usage.

The `instructions` parameter on your MCP server is the mechanism that tells agents when and how to call the feedback tool. Every MCP server that registers the feedback tool **must** include instructions like the example above. Adapt the wording to your server's domain, but always keep these key points:

1. **Tell the agent it is required.** Agents treat server instructions as authoritative. If you don't say "you must call the feedback tool," they won't.
2. **Specify when to call it.** List the concrete scenarios: missing tool, incomplete results, wrong format, about to say "not possible," etc.
3. **Say to call it BEFORE responding.** If the agent responds to the user first, it will rarely circle back to submit feedback.
4. **Ask for specifics.** Generic feedback like "something was missing" is not actionable. Tell the agent to describe exactly what it needed and what would have helped.

Without these instructions, PatchworkMCP receives no signal about what your server is missing, and you lose the entire feedback loop that drives improvement.

For the full guide on writing effective agent instructions, see [AGENT_INSTRUCTIONS.md](AGENT_INSTRUCTIONS.md).

## How It Works

- Retries up to 2 times with exponential backoff (500ms, 1000ms)
- Retries on 429 (rate limit) and 5xx (server error) status codes
- On failure, logs the full payload with `PATCHWORKMCP_UNSENT_FEEDBACK` prefix for later replay
- Never throws or raises — always returns a user-facing message

## License

MIT
