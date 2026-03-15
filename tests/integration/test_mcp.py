"""Integration tests for tools.py MCP / Rocketlane functions.

HTTP calls are intercepted by respx; anthropic.Anthropic is patched with pytest-mock.
"""
import json
import pytest
import respx
import httpx
from unittest.mock import MagicMock, patch

import tools
from tools import (
    _mcp_init,
    _call_tool_sync,
    _search_tools_sync,
    ROCKETLANE_MCP_URL,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_sse_response(data: dict, **extra_headers) -> httpx.Response:
    """Wrap a dict as an SSE-formatted httpx.Response body."""
    text = f"data:{json.dumps(data)}"
    headers = {"Content-Type": "text/event-stream", **extra_headers}
    return httpx.Response(200, text=text, headers=headers)


def _respx_handler(*responses):
    """Return a side_effect callable that yields responses in order."""
    it = iter(responses)
    return lambda req: next(it)


# ---------------------------------------------------------------------------
# _mcp_init
# ---------------------------------------------------------------------------

@respx.mock
def test_mcp_init_returns_session_id():
    respx.post(ROCKETLANE_MCP_URL).mock(
        side_effect=_respx_handler(
            httpx.Response(200, headers={"mcp-session-id": "sess-xyz"}, json={}),
            httpx.Response(200, json={}),
        )
    )
    result = _mcp_init("test-key")
    assert result == "sess-xyz"


@respx.mock
def test_mcp_init_raises_if_no_session_id_header():
    respx.post(ROCKETLANE_MCP_URL).mock(return_value=httpx.Response(200, json={}))
    with pytest.raises(ValueError, match="mcp-session-id"):
        _mcp_init("test-key")


@respx.mock
def test_mcp_init_raises_on_non_2xx():
    respx.post(ROCKETLANE_MCP_URL).mock(return_value=httpx.Response(503, json={}))
    with pytest.raises(httpx.HTTPStatusError):
        _mcp_init("test-key")


@respx.mock
def test_mcp_init_sends_notifications_initialized():
    requests_captured = []

    def capture(request: httpx.Request):
        requests_captured.append(request)
        body = json.loads(request.content)
        if body.get("method") == "initialize":
            return httpx.Response(200, headers={"mcp-session-id": "sess-abc"}, json={})
        return httpx.Response(200, json={})

    respx.post(ROCKETLANE_MCP_URL).mock(side_effect=capture)

    _mcp_init("test-key")

    assert len(requests_captured) == 2
    second_body = json.loads(requests_captured[1].content)
    assert second_body["method"] == "notifications/initialized"
    assert requests_captured[1].headers.get("mcp-session-id") == "sess-abc"


# ---------------------------------------------------------------------------
# _call_tool_sync
# ---------------------------------------------------------------------------

def test_call_tool_unknown_name_returns_error_without_http_call(monkeypatch):
    monkeypatch.setattr(tools, "_TOOL_INDEX", [{"name": "known_tool", "description": "..."}])
    result = json.loads(_call_tool_sync("unknown_tool", {}))
    assert "error" in result
    assert "unknown_tool" in result["error"]


@respx.mock
def test_call_tool_valid_name_returns_result(monkeypatch):
    monkeypatch.setattr(tools, "_TOOL_INDEX", [{"name": "my_tool", "description": "does stuff"}])

    tool_result = {"content": [{"text": "success"}]}

    def handler(request: httpx.Request):
        body = json.loads(request.content)
        method = body.get("method")
        if method == "initialize":
            return httpx.Response(200, headers={"mcp-session-id": "s1"}, json={})
        if method == "notifications/initialized":
            return httpx.Response(200, json={})
        # tools/call
        return _make_sse_response({"result": tool_result})

    respx.post(ROCKETLANE_MCP_URL).mock(side_effect=handler)

    raw = _call_tool_sync("my_tool", {"param": "value"})
    assert json.loads(raw) == tool_result


@respx.mock
def test_call_tool_422_raises_http_error(monkeypatch):
    monkeypatch.setattr(tools, "_TOOL_INDEX", [{"name": "my_tool", "description": "..."}])

    def handler(request: httpx.Request):
        body = json.loads(request.content)
        method = body.get("method")
        if method == "initialize":
            return httpx.Response(200, headers={"mcp-session-id": "s1"}, json={})
        if method == "notifications/initialized":
            return httpx.Response(200, json={})
        return httpx.Response(422, json={"error": "unprocessable"})

    respx.post(ROCKETLANE_MCP_URL).mock(side_effect=handler)

    with pytest.raises(httpx.HTTPStatusError):
        _call_tool_sync("my_tool", {})


# ---------------------------------------------------------------------------
# _search_tools_sync
# ---------------------------------------------------------------------------

def test_search_tools_returns_matching_dicts(monkeypatch, mocker):
    monkeypatch.setattr(tools, "_TOOL_INDEX", [
        {"name": "tool_a", "description": "alpha"},
        {"name": "tool_b", "description": "beta"},
        {"name": "tool_c", "description": "gamma"},
    ])

    mock_msg = MagicMock()
    mock_msg.content = [MagicMock()]
    mock_msg.content[0].text = '["tool_a", "tool_c"]'

    mock_client = MagicMock()
    mock_client.messages.create.return_value = mock_msg
    mocker.patch("tools.anthropic.Anthropic", return_value=mock_client)

    result = _search_tools_sync("find tools")

    assert len(result) == 2
    assert result[0]["name"] == "tool_a"
    assert result[1]["name"] == "tool_c"


def test_search_tools_filters_out_unknown_names(monkeypatch, mocker):
    monkeypatch.setattr(tools, "_TOOL_INDEX", [
        {"name": "tool_a", "description": "alpha"},
    ])

    mock_msg = MagicMock()
    mock_msg.content = [MagicMock()]
    mock_msg.content[0].text = '["tool_a", "nonexistent_tool"]'

    mock_client = MagicMock()
    mock_client.messages.create.return_value = mock_msg
    mocker.patch("tools.anthropic.Anthropic", return_value=mock_client)

    result = _search_tools_sync("query")

    assert len(result) == 1
    assert result[0]["name"] == "tool_a"


def test_search_tools_malformed_json_raises(monkeypatch, mocker):
    monkeypatch.setattr(tools, "_TOOL_INDEX", [{"name": "tool_a", "description": "alpha"}])

    mock_msg = MagicMock()
    mock_msg.content = [MagicMock()]
    mock_msg.content[0].text = "[not valid json at all"

    mock_client = MagicMock()
    mock_client.messages.create.return_value = mock_msg
    mocker.patch("tools.anthropic.Anthropic", return_value=mock_client)

    with pytest.raises(json.JSONDecodeError):
        _search_tools_sync("query")
