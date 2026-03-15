import os
import sys
import json
import time
import logging
import httpx
import anthropic
from pathlib import Path

logger = logging.getLogger(__name__)

ROCKETLANE_MCP_URL = "https://rocket-mcp.rl-platforms.rocketlane.com/mcp"

_TOOL_INDEX: list[dict] = []
_MCP_SESSION_ID: str | None = None  # reused across all tool calls in this process

_CACHE_DIR = Path(os.environ.get("RAILWAY_VOLUME_MOUNT_PATH", "/data")) / "cache"
_CACHE_FILE = _CACHE_DIR / "tool_index_cache.json"
_CACHE_TTL = 24 * 3600  # 24 hours


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
        logger.info("MCP session created: %s", _MCP_SESSION_ID)
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


def _load_tool_index_cached() -> list[dict]:
    """Return tool index from disk cache if < 24h old, else fetch and cache."""
    try:
        if _CACHE_FILE.exists():
            if time.time() - _CACHE_FILE.stat().st_mtime < _CACHE_TTL:
                cached = json.loads(_CACHE_FILE.read_text())
                if isinstance(cached, list) and cached:
                    logger.info("Tool index loaded from cache (%d tools).", len(cached))
                    return cached
    except Exception as e:
        logger.warning("Cache read error: %s", e)

    tools = _fetch_tool_index_sync()

    try:
        _CACHE_DIR.mkdir(parents=True, exist_ok=True)
        tmp = _CACHE_FILE.with_suffix(".tmp")
        tmp.write_text(json.dumps(tools))
        tmp.rename(_CACHE_FILE)
    except Exception as e:
        logger.warning("Cache write error: %s", e)

    return tools


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
        logger.error("tools/call HTTP %d: %s", e.response.status_code, e.response.text[:500])
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
    index_map = {t["name"]: t for t in _TOOL_INDEX}
    try:
        start = text.find("[")
        end = text.rfind("]") + 1
        if start == -1 or end == 0:
            raise ValueError("No JSON array found in response")
        names = json.loads(text[start:end])
    except (json.JSONDecodeError, ValueError):
        logger.warning("Failed to parse tool search response, returning first %d tools", top_n)
        return [
            {
                "name": t["name"],
                "description": t.get("description", ""),
                "inputSchema": t.get("inputSchema", {}),
            }
            for t in _TOOL_INDEX[:top_n]
        ]
    return [
        {
            "name": n,
            "description": index_map[n].get("description", ""),
            "inputSchema": index_map[n].get("inputSchema", {}),
        }
        for n in names
        if n in index_map
    ]


# --- Two-track response: summary for LLM, full data for frontend ---

_TOOL_RESULTS_DIR = Path(os.environ.get("RAILWAY_VOLUME_MOUNT_PATH", "/data")) / "tool_results"
_REQUEST_ID: str = ""  # set from CLI args at proxy startup

_SUMMARY_SAMPLE_ITEMS = 5
_SUMMARY_FIELD_MAX_LEN = 200
_MAX_LIST_ITEMS = 20
_MAX_STR_LEN = 500
_MAX_RESULT_BYTES = 50_000


def _store_full_result(tool_name: str, raw: str) -> None:
    """Write full tool result to shared dir for API to retrieve."""
    if not _REQUEST_ID:
        return
    try:
        _TOOL_RESULTS_DIR.mkdir(parents=True, exist_ok=True)
        filename = f"{_REQUEST_ID}_{tool_name}_{int(time.time() * 1000)}.json"
        (_TOOL_RESULTS_DIR / filename).write_text(raw)
    except Exception as e:
        logger.warning("Failed to store tool result: %s", e)


def _extract_list(data) -> list | None:
    """Find the primary list inside a tool response."""
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for key in ("data", "items", "results", "tasks", "entries", "content"):
            if isinstance(data.get(key), list):
                return data[key]
    return None


def _extract_samples(items: list) -> list:
    """Key fields only from sample items, drop verbose/nested content."""
    samples = []
    for item in items:
        if isinstance(item, dict):
            sample = {}
            for k, v in item.items():
                if isinstance(v, str) and len(v) > _SUMMARY_FIELD_MAX_LEN:
                    sample[k] = v[:_SUMMARY_FIELD_MAX_LEN] + "..."
                elif isinstance(v, (dict, list)):
                    continue
                else:
                    sample[k] = v
            samples.append(sample)
        else:
            samples.append(item)
    return samples


def _aggregate_field(items: list, field: str) -> dict | None:
    """Count occurrences of a field value across items."""
    counts: dict[str, int] = {}
    for item in items:
        if isinstance(item, dict) and field in item:
            val = str(item[field])
            counts[val] = counts.get(val, 0) + 1
    return counts if len(counts) > 1 else None


def _summarize_for_llm(raw: str, tool_name: str) -> str:
    """Create compact summary for LLM. Full data stored on disk for frontend."""
    _store_full_result(tool_name, raw)

    try:
        data = json.loads(raw)
    except Exception:
        if len(raw) > 5000:
            return raw[:5000] + "...[truncated]"
        return raw

    items = _extract_list(data)

    if items is not None and len(items) > _SUMMARY_SAMPLE_ITEMS:
        summary: dict = {
            "_summary": True,
            "total_count": len(items),
            "sample_items": _extract_samples(items[:_SUMMARY_SAMPLE_ITEMS]),
        }
        for field in ("status", "state", "type", "priority"):
            agg = _aggregate_field(items, field)
            if agg:
                summary.setdefault("aggregates", {})[f"by_{field}"] = agg
        return json.dumps(summary)

    # Small response — use safe iterative truncation
    return _compact_tool_result_safe(raw)


def _truncate_value(val, depth=0, max_items=_MAX_LIST_ITEMS, max_str_len=_MAX_STR_LEN):
    if depth > 5:
        return "..."
    if isinstance(val, list):
        truncated = [_truncate_value(v, depth + 1, max_items, max_str_len) for v in val[:max_items]]
        if len(val) > max_items:
            truncated.append({"_note": f"...{len(val) - max_items} more items omitted"})
        return truncated
    if isinstance(val, dict):
        return {k: _truncate_value(v, depth + 1, max_items, max_str_len) for k, v in val.items()}
    if isinstance(val, str) and len(val) > max_str_len:
        return val[:max_str_len] + "...[truncated]"
    return val


def _compact_tool_result_safe(raw: str) -> str:
    """Iteratively truncate until result is valid JSON under the byte limit."""
    try:
        data = json.loads(raw)
    except Exception:
        if len(raw) > _MAX_RESULT_BYTES:
            return raw[:_MAX_RESULT_BYTES] + "...[truncated]"
        return raw

    max_items, max_str = _MAX_LIST_ITEMS, _MAX_STR_LEN
    for _ in range(5):
        truncated = _truncate_value(data, max_items=max_items, max_str_len=max_str)
        compacted = json.dumps(truncated)
        if len(compacted.encode()) <= _MAX_RESULT_BYTES:
            return compacted
        max_items = max(1, max_items // 2)
        max_str = max(50, max_str // 2)

    return json.dumps({"_truncated": True, "_note": f"Exceeded {_MAX_RESULT_BYTES} bytes"})


def _cleanup_stale_results(max_age_seconds: int = 3600) -> None:
    """Delete tool result files older than max_age_seconds."""
    if not _TOOL_RESULTS_DIR.exists():
        return
    cutoff = time.time() - max_age_seconds
    for path in _TOOL_RESULTS_DIR.glob("*.json"):
        try:
            if path.stat().st_mtime < cutoff:
                path.unlink()
        except Exception:
            pass


def _run_proxy_server():
    from mcp.server.fastmcp import FastMCP

    _cleanup_stale_results()

    global _TOOL_INDEX
    logger.info("Fetching Rocketlane tool index...")
    try:
        _TOOL_INDEX = _load_tool_index_cached()
        schemas_present = sum(1 for t in _TOOL_INDEX if "inputSchema" in t)
        logger.info("Loaded %d tools (%d with schemas).", len(_TOOL_INDEX), schemas_present)
    except Exception as e:
        logger.error("Failed to fetch tool index: %s", e)
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
            result = _call_tool_sync(name, parsed)
            return _summarize_for_llm(result, name)
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 422:
                raise  # Propagate as MCP tool error → PostToolUseFailure hook
            return json.dumps({"error": f"HTTP {e.response.status_code}: {str(e)}"})
        except Exception as e:
            return json.dumps({"error": str(e)})

    proxy.run("stdio")


def start_proxy(rocketlane_api_key: str, request_id: str = "") -> dict:
    """Returns McpStdioServerConfig for the Claude Agent SDK."""
    anthropic_key = os.environ.get("ANTHROPIC_API_KEY", "")
    return {
        "command": sys.executable,
        "args": [
            str(Path(__file__).resolve()),
            "--proxy",
            "--rocketlane-key", rocketlane_api_key,
            "--anthropic-key", anthropic_key,
            "--request-id", request_id,
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
        idx = sys.argv.index("--request-id") if "--request-id" in sys.argv else -1
        if idx != -1:
            _REQUEST_ID = sys.argv[idx + 1]
        _run_proxy_server()
