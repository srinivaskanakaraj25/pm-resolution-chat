import os
import sys
import json
import httpx
import anthropic
from pathlib import Path

ROCKETLANE_MCP_URL = "https://rocket-mcp.rl-platforms.rocketlane.com/mcp"

_TOOL_INDEX: list[dict] = []
_MCP_SESSION_ID: str | None = None  # reused across all tool calls in this process


def _mcp_headers(api_key: str, session_id: str | None = None) -> dict:
    h = {
        "api-key": api_key,
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
    }
    if session_id:
        h["mcp-session-id"] = session_id
    return h


def _parse_sse(text: str) -> dict:
    for line in text.splitlines():
        if line.startswith("data:"):
            return json.loads(line[5:])
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        raise ValueError(f"Response is neither SSE nor valid JSON: {text[:500]}")


def _mcp_init(api_key: str) -> str:
    """Initialize MCP session, returns session_id."""
    resp = httpx.post(
        ROCKETLANE_MCP_URL,
        headers=_mcp_headers(api_key),
        json={
            "jsonrpc": "2.0",
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "pm-chat", "version": "1.0"},
            },
            "id": 1,
        },
        timeout=30,
    )
    resp.raise_for_status()
    session_id = resp.headers.get("mcp-session-id")
    if not session_id:
        raise ValueError("MCP server did not return mcp-session-id header")
    # Send required notifications/initialized to complete the handshake
    notify_resp = httpx.post(
        ROCKETLANE_MCP_URL,
        headers=_mcp_headers(api_key, session_id),
        json={"jsonrpc": "2.0", "method": "notifications/initialized"},
        timeout=15,
    )
    notify_resp.raise_for_status()
    return session_id


def _get_or_create_session(api_key: str) -> str:
    """Return the cached MCP session, creating one if needed."""
    global _MCP_SESSION_ID
    if _MCP_SESSION_ID is None:
        _MCP_SESSION_ID = _mcp_init(api_key)
        print(f"MCP session created: {_MCP_SESSION_ID}", file=sys.stderr, flush=True)
    return _MCP_SESSION_ID


def _fetch_tool_index_sync() -> list[dict]:
    api_key = os.environ.get("ROCKETLANE_API_KEY", "")
    session_id = _get_or_create_session(api_key)
    resp = httpx.post(
        ROCKETLANE_MCP_URL,
        headers=_mcp_headers(api_key, session_id),
        json={"jsonrpc": "2.0", "method": "tools/list", "params": {}, "id": 2},
        timeout=30,
    )
    resp.raise_for_status()
    return _parse_sse(resp.text).get("result", {}).get("tools", [])


def _call_tool_sync(name: str, params: dict) -> str:
    valid_names = {t["name"] for t in _TOOL_INDEX}
    if name not in valid_names:
        return json.dumps({"error": f"Unknown tool: {name}"})
    api_key = os.environ.get("ROCKETLANE_API_KEY", "")
    session_id = _get_or_create_session(api_key)
    try:
        resp = httpx.post(
            ROCKETLANE_MCP_URL,
            headers=_mcp_headers(api_key, session_id),
            json={
                "jsonrpc": "2.0",
                "method": "tools/call",
                "params": {"name": name, "arguments": params},
                "id": 2,
            },
            timeout=120,
        )
        resp.raise_for_status()
    except httpx.HTTPStatusError as e:
        print(f"tools/call HTTP {e.response.status_code}: {e.response.text}", file=sys.stderr, flush=True)
        # Session may have expired — reset so next call creates a fresh one
        global _MCP_SESSION_ID
        _MCP_SESSION_ID = None
        raise
    return json.dumps(_parse_sse(resp.text).get("result", {}))


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


def start_proxy(rocketlane_api_key: str) -> dict:
    """Returns McpStdioServerConfig for the Claude Agent SDK."""
    anthropic_key = os.environ.get("ANTHROPIC_API_KEY", "")
    return {
        "command": sys.executable,
        "args": [
            str(Path(__file__).resolve()),
            "--proxy",
            "--rocketlane-key", rocketlane_api_key,
            "--anthropic-key", anthropic_key,
        ],
    }


if __name__ == "__main__":
    if "--proxy" in sys.argv:
        idx = sys.argv.index("--rocketlane-key") if "--rocketlane-key" in sys.argv else -1
        if idx != -1:
            os.environ["ROCKETLANE_API_KEY"] = sys.argv[idx + 1]
        idx = sys.argv.index("--anthropic-key") if "--anthropic-key" in sys.argv else -1
        if idx != -1:
            os.environ["ANTHROPIC_API_KEY"] = sys.argv[idx + 1]
        _run_proxy_server()
