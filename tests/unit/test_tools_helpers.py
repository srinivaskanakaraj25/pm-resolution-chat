"""Unit tests for pure helper functions in tools.py — no HTTP calls made."""
import sys
import json
import pytest
from tools import _mcp_headers, _parse_sse, start_proxy


# ---------------------------------------------------------------------------
# _mcp_headers
# ---------------------------------------------------------------------------

def test_mcp_headers_without_session_id():
    h = _mcp_headers("my-api-key")
    assert h["api-key"] == "my-api-key"
    assert h["Content-Type"] == "application/json"
    assert "Accept" in h
    assert "mcp-session-id" not in h


def test_mcp_headers_with_session_id():
    h = _mcp_headers("my-api-key", "sess-abc-123")
    assert h["api-key"] == "my-api-key"
    assert h["Content-Type"] == "application/json"
    assert "Accept" in h
    assert h["mcp-session-id"] == "sess-abc-123"


# ---------------------------------------------------------------------------
# _parse_sse
# ---------------------------------------------------------------------------

def test_parse_sse_with_data_prefix():
    result = _parse_sse('data:{"result": "ok", "id": 1}')
    assert result == {"result": "ok", "id": 1}


def test_parse_sse_with_raw_json():
    result = _parse_sse('{"result": "ok", "id": 2}')
    assert result == {"result": "ok", "id": 2}


def test_parse_sse_malformed_raises():
    with pytest.raises(ValueError):
        _parse_sse("not json at all !!!!")


# ---------------------------------------------------------------------------
# start_proxy
# ---------------------------------------------------------------------------

def test_start_proxy_shape():
    result = start_proxy("some-key")
    assert "command" in result
    assert "args" in result
    assert result["command"] == sys.executable
    assert isinstance(result["args"], list)


def test_start_proxy_includes_rocketlane_key():
    result = start_proxy("rl-key-xyz")
    assert "--rocketlane-key" in result["args"]
    idx = result["args"].index("--rocketlane-key")
    assert result["args"][idx + 1] == "rl-key-xyz"
