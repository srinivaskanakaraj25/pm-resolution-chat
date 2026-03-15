import os
import sys
import json
import httpx
import anthropic
from pathlib import Path

ROCKETLANE_MCP_URL = "https://rocket-mcp.rl-platforms.rocketlane.com/mcp"

_TOOL_INDEX: list[dict] = []


def _fetch_tool_index_sync() -> list[dict]:
    api_key = os.environ.get("ROCKETLANE_API_KEY", "")
    resp = httpx.post(
        ROCKETLANE_MCP_URL,
        headers={"api-key": api_key, "Content-Type": "application/json"},
        json={"jsonrpc": "2.0", "method": "tools/list", "params": {}, "id": 1},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json().get("result", {}).get("tools", [])


def _search_tools_sync(query: str, top_n: int = 8) -> list[dict]:
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
    start = text.find("[")
    end = text.rfind("]") + 1
    names = json.loads(text[start:end])
    index_map = {t["name"]: t for t in _TOOL_INDEX}
    return [
        {"name": n, "description": index_map[n].get("description", "")}
        for n in names
        if n in index_map
    ]


def _call_tool_sync(name: str, params: dict) -> str:
    valid_names = {t["name"] for t in _TOOL_INDEX}
    if name not in valid_names:
        return json.dumps({"error": f"Unknown tool: {name}"})
    api_key = os.environ.get("ROCKETLANE_API_KEY", "")
    resp = httpx.post(
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
    return json.dumps(resp.json().get("result", {}))


def _run_proxy_server():
    from mcp.server.fastmcp import FastMCP

    global _TOOL_INDEX
    print("Fetching Rocketlane tool index...", file=sys.stderr, flush=True)
    try:
        _TOOL_INDEX = _fetch_tool_index_sync()
        print(f"Loaded {len(_TOOL_INDEX)} tools.", file=sys.stderr, flush=True)
    except Exception as e:
        print(f"Failed to fetch tool index: {e}", file=sys.stderr, flush=True)
        _TOOL_INDEX = []

    proxy = FastMCP("rocketlane-proxy")

    @proxy.tool()
    def search_rocketlane_tools(query: str) -> str:
        """Search for relevant Rocketlane tools by describing what you want to do."""
        try:
            results = _search_tools_sync(query)
            return json.dumps(results)
        except Exception as e:
            return json.dumps({"error": str(e)})

    @proxy.tool()
    def call_rocketlane_tool(name: str, params: str) -> str:
        """Call a Rocketlane tool by name. Pass params as a JSON string."""
        try:
            parsed = json.loads(params) if isinstance(params, str) else params
        except json.JSONDecodeError:
            parsed = {}
        try:
            return _call_tool_sync(name, parsed)
        except Exception as e:
            return json.dumps({"error": str(e)})

    proxy.run("stdio")


def start_proxy() -> dict:
    """Returns McpStdioServerConfig for the Claude Agent SDK."""
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
        _run_proxy_server()
