import os
import sys
import json
import asyncio
import httpx
import anthropic
from pathlib import Path

ROCKETLANE_MCP_URL = "https://rocket-mcp.rl-platforms.rocketlane.com/mcp"

_TOOL_INDEX: list[dict] = []


async def _fetch_tool_index() -> list[dict]:
    api_key = os.environ.get("ROCKETLANE_API_KEY", "")
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            ROCKETLANE_MCP_URL,
            headers={"api-key": api_key, "Content-Type": "application/json"},
            json={"jsonrpc": "2.0", "method": "tools/list", "params": {}, "id": 1},
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        return data.get("result", {}).get("tools", [])


async def _search_tools(query: str, top_n: int = 8) -> list[dict]:
    tool_list = "\n".join(
        f"{t['name']}: {t.get('description', '')}" for t in _TOOL_INDEX
    )
    prompt = (
        f"You are a tool selector. Given a user intent and a list of tools, "
        f"return the names of the top {top_n} most relevant tools as a JSON array of strings. "
        f"No explanation, just the JSON array.\n\n"
        f"Intent: {query}\n\nTools:\n{tool_list}"
    )
    client = anthropic.Anthropic()
    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=256,
        messages=[{"role": "user", "content": prompt}],
    )
    text = response.content[0].text.strip()
    # Extract JSON array from response
    start = text.find("[")
    end = text.rfind("]") + 1
    names = json.loads(text[start:end])
    index_map = {t["name"]: t for t in _TOOL_INDEX}
    return [
        {"name": n, "description": index_map[n].get("description", "")}
        for n in names
        if n in index_map
    ]


async def _call_tool(name: str, params: dict) -> str:
    valid_names = {t["name"] for t in _TOOL_INDEX}
    if name not in valid_names:
        return json.dumps({"error": f"Unknown tool: {name}"})
    api_key = os.environ.get("ROCKETLANE_API_KEY", "")
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            ROCKETLANE_MCP_URL,
            headers={"api-key": api_key, "Content-Type": "application/json"},
            json={
                "jsonrpc": "2.0",
                "method": "tools/call",
                "params": {"name": name, "arguments": params},
                "id": 1,
            },
            timeout=60,
        )
        resp.raise_for_status()
        data = resp.json()
        result = data.get("result", {})
        return json.dumps(result)


async def _run_proxy_server():
    from mcp.server.fastmcp import FastMCP

    global _TOOL_INDEX
    print("Fetching Rocketlane tool index...", file=sys.stderr)
    _TOOL_INDEX = await _fetch_tool_index()
    print(f"Loaded {len(_TOOL_INDEX)} tools.", file=sys.stderr)

    proxy = FastMCP("rocketlane-proxy")

    @proxy.tool()
    async def search_rocketlane_tools(query: str) -> str:
        """Search for relevant Rocketlane tools by describing what you want to do."""
        results = await _search_tools(query)
        return json.dumps(results)

    @proxy.tool()
    async def call_rocketlane_tool(name: str, params: str) -> str:
        """Call a Rocketlane tool by name with JSON params string."""
        try:
            parsed_params = json.loads(params) if isinstance(params, str) else params
        except json.JSONDecodeError:
            parsed_params = {}
        return await _call_tool(name, parsed_params)

    await proxy.run_async("stdio")


def start_proxy() -> dict:
    """Returns McpStdioServerConfig for the Claude Agent SDK to spawn the proxy."""
    return {
        "command": sys.executable,
        "args": [str(Path(__file__).resolve()), "--proxy"],
        "env": {
            **os.environ,
            "ROCKETLANE_API_KEY": os.environ.get("ROCKETLANE_API_KEY", ""),
            "ANTHROPIC_API_KEY": os.environ.get("ANTHROPIC_API_KEY", ""),
        },
    }


if __name__ == "__main__":
    if "--proxy" in sys.argv:
        asyncio.run(_run_proxy_server())
