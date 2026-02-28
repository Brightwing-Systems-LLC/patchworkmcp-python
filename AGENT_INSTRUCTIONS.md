# Agent Instructions for the Feedback Tool

**You must add instructions to your MCP server telling the agent to use the feedback tool.** This is the single most important step in the integration. Without explicit instructions, agents will silently ignore the feedback tool — even though it appears in their tool list.

## Why This Matters

MCP servers expose tools to agents, but agents decide which tools to call based on the server's `instructions` field and each tool's description. The feedback tool's description helps, but it is not enough on its own. Agents routinely skip tools they don't have clear guidance to use.

If you register the feedback tool without adding server instructions:

- The agent sees the tool but has no directive to call it.
- When the agent hits a limitation, it responds to the user directly — no feedback is ever sent.
- PatchworkMCP receives zero signal about what your server is missing.
- You lose the entire feedback loop that drives improvement.

**In short: no instructions = no feedback.**

## What to Include in Your Instructions

Every MCP server that registers the feedback tool **must** set the `instructions` parameter. Here is the recommended template:

```
If you encounter a limitation — a missing tool, incomplete data, wrong format,
or any gap that prevents you from fully completing the user's request — call
the `feedback` tool BEFORE responding to the user. Be specific about what you
needed and what would have helped.
```

Adapt the wording to your domain, but always keep these four principles:

### 1. Tell the agent it is required

Agents treat server instructions as authoritative. If you don't say "you must call the feedback tool," they won't. Use direct, imperative language:

- "Call the `feedback` tool whenever..."
- "You must report any limitations using the `feedback` tool..."
- "Before telling the user something is not possible, call the `feedback` tool..."

### 2. Specify when to call it

List the concrete scenarios that should trigger feedback. For example:

- You searched the available tools and didn't find what you needed.
- A tool returned incomplete or unexpected results.
- You are about to tell the user something isn't possible.
- You had to approximate because the right data wasn't available.
- A required parameter is missing from an existing tool.
- The output format of a tool doesn't match what the user needs.

### 3. Say to call it BEFORE responding to the user

This is critical. If the agent responds to the user first, it will rarely circle back to submit feedback. The instruction must make it clear that the feedback call comes **before** the final response:

- "Call the `feedback` tool **BEFORE** responding to the user."
- "Submit feedback **first**, then respond to the user."

### 4. Ask for specifics

Generic feedback like "something was missing" is not actionable. Tell the agent to describe exactly what it needed and what would have helped:

- "Be specific about what capability, data, or tool was missing."
- "Describe what inputs the ideal tool would accept and what it would return."
- "Include which tools you tried and what they returned."

## Integration Examples

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

When using the raw SDK, set the instructions in your server's initialization or capabilities response. Then register the tool:

```python
from feedback_tool import get_tool_definition, send_feedback

# In list_tools handler:
tools.append(get_tool_definition())

# In call_tool handler:
if name == "feedback":
    result = await send_feedback(arguments)
```

### Domain-Specific Example

For a weather server, you might write:

```python
INSTRUCTIONS = """
You have access to weather and forecast tools. If a user asks for weather data
that you cannot retrieve — a location not covered, a time range not supported,
a metric not available — call the `feedback` tool BEFORE responding. Describe
exactly what data point was missing and what format it should be in.
"""
```

## Common Mistakes

| Mistake | Result |
|---|---|
| Registering the feedback tool but not setting `instructions` | Agents never call it |
| Putting feedback guidance only in the tool description | Agents may still skip it — instructions are stronger |
| Telling the agent to call feedback "if it wants to" | Agents interpret optional guidance as skippable |
| Not saying "BEFORE responding to the user" | Agent responds first and never submits feedback |
| Using vague instructions like "use feedback when appropriate" | Agent doesn't know when "appropriate" is — be explicit |

## Verifying It Works

After setting up your server with instructions:

1. Connect an agent (Claude Desktop, Cursor, Claude Code, etc.) to your server.
2. Ask the agent to do something your server **cannot** do yet.
3. Check your PatchworkMCP dashboard — you should see the feedback appear.

If no feedback appears, check that your `instructions` parameter is set and includes the directive to call the feedback tool.
