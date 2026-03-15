"""Integration tests for FastAPI endpoints using TestClient.

AgentClient is mocked; no real Claude SDK or DB connection is needed.
The module-level patch of db.init_db prevents a real DB call when api.py is imported.
"""
import sys
import os
from unittest.mock import MagicMock, AsyncMock, patch, call
import pytest
from fastapi.testclient import TestClient

# Ensure API_KEY is set before api.py is imported
os.environ["API_KEY"] = "test-api-key"

# Force a fresh import so module-level code (init_db()) runs under our patch
sys.modules.pop("api", None)
_mock_db = MagicMock()
# get_conn calls pool.getconn()/putconn(); make getconn return the same mock
_mock_db.getconn.return_value = _mock_db
_init_db_patcher = patch("db.init_db", return_value=_mock_db)
_init_db_patcher.start()
import api  # noqa: E402 — must come after patch
_init_db_patcher.stop()

client = TestClient(api.app)
_error_client = TestClient(api.app, raise_server_exceptions=False)

HEADERS = {"X-API-Key": "test-api-key"}
WRONG_HEADERS = {"X-API-Key": "wrong-key"}


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

def test_missing_api_key_returns_401():
    # FastAPI's APIKeyHeader treats a missing header the same as a wrong key → 401
    r = client.post("/conversations", json={"message": "Hi"})
    assert r.status_code == 401


def test_wrong_api_key_returns_401():
    r = client.post("/conversations", json={"message": "Hi"}, headers=WRONG_HEADERS)
    assert r.status_code == 401


def test_correct_api_key_passes_through(mock_agent, mocker):
    mocker.patch("api.AgentClient", return_value=mock_agent)
    r = client.post("/conversations", json={"message": "Hi"}, headers=HEADERS)
    assert r.status_code == 200


# ---------------------------------------------------------------------------
# POST /conversations
# ---------------------------------------------------------------------------

def test_start_conversation_returns_session_id_and_response(mock_agent, mocker):
    mocker.patch("api.AgentClient", return_value=mock_agent)
    r = client.post("/conversations", json={"message": "Hello"}, headers=HEADERS)

    assert r.status_code == 200
    data = r.json()
    assert data["session_id"] == "test-session-id"
    assert data["response"] == "Test response"
    assert "tool_data" in data


def test_start_conversation_with_rocketlane_key_passes_key_to_agent(mock_agent, mocker):
    mock_cls = mocker.patch("api.AgentClient", return_value=mock_agent)
    client.post(
        "/conversations",
        json={"message": "Hello", "rocketlane_api_key": "rl-key-123"},
        headers=HEADERS,
    )
    _, kwargs = mock_cls.call_args
    assert kwargs.get("rocketlane_api_key") == "rl-key-123"


def test_start_conversation_agent_error_propagates(mocker):
    bad_agent = MagicMock()
    bad_agent.connect = AsyncMock()
    bad_agent.disconnect = AsyncMock()
    bad_agent.send = AsyncMock(side_effect=RuntimeError("boom"))
    mocker.patch("api.AgentClient", return_value=bad_agent)

    r = _error_client.post("/conversations", json={"message": "Hello"}, headers=HEADERS)
    assert r.status_code == 500


# ---------------------------------------------------------------------------
# POST /conversations/{id}/message
# ---------------------------------------------------------------------------

def test_send_message_unknown_id_returns_404(mocker):
    mocker.patch("api.get_conversation", return_value=None)
    r = client.post(
        "/conversations/no-such-id/message",
        json={"message": "Hello"},
        headers=HEADERS,
    )
    assert r.status_code == 404


def test_send_message_known_id_returns_response_and_mode(mock_agent, mocker):
    conv = {"session_id": "sess-abc", "mode": "normal", "failure_context": None}
    mocker.patch("api.get_conversation", return_value=conv)
    mocker.patch("api.AgentClient", return_value=mock_agent)

    r = client.post(
        "/conversations/sess-abc/message",
        json={"message": "Hello"},
        headers=HEADERS,
    )
    assert r.status_code == 200
    data = r.json()
    assert "response" in data
    assert "mode" in data


def test_send_message_restores_state_from_db(mock_agent, mocker):
    fc_json = '{"tool_error": {"status": 422}}'
    conv = {"session_id": "sess-abc", "mode": "resolution", "failure_context": fc_json}
    mocker.patch("api.get_conversation", return_value=conv)
    mocker.patch("api.AgentClient", return_value=mock_agent)

    client.post(
        "/conversations/sess-abc/message",
        json={"message": "Help"},
        headers=HEADERS,
    )
    mock_agent.restore_state.assert_called_once_with("resolution", fc_json)


def test_send_message_forwards_rocketlane_key(mock_agent, mocker):
    conv = {"session_id": "sess-abc", "mode": "normal", "failure_context": None}
    mocker.patch("api.get_conversation", return_value=conv)
    mock_cls = mocker.patch("api.AgentClient", return_value=mock_agent)

    client.post(
        "/conversations/sess-abc/message",
        json={"message": "Hi", "rocketlane_api_key": "rl-forwarded"},
        headers=HEADERS,
    )
    _, kwargs = mock_cls.call_args
    assert kwargs.get("rocketlane_api_key") == "rl-forwarded"


# ---------------------------------------------------------------------------
# GET /conversations
# ---------------------------------------------------------------------------

def test_list_conversations_empty(mocker):
    mocker.patch("api.list_conversations", return_value=[])
    r = client.get("/conversations", headers=HEADERS)
    assert r.status_code == 200
    assert r.json() == []


def test_list_conversations_newest_first(mocker):
    convs = [
        {"session_id": "a", "title": "Newer", "mode": "normal", "created_at": "t1", "updated_at": "2024-01-02"},
        {"session_id": "b", "title": "Older", "mode": "normal", "created_at": "t0", "updated_at": "2024-01-01"},
    ]
    mocker.patch("api.list_conversations", return_value=convs)
    r = client.get("/conversations", headers=HEADERS)
    data = r.json()
    assert len(data) == 2
    assert data[0]["session_id"] == "a"
    assert data[1]["session_id"] == "b"


# ---------------------------------------------------------------------------
# POST /conversations/{id}/exit-resolution
# ---------------------------------------------------------------------------

def test_exit_resolution_unknown_id_returns_404(mocker):
    mocker.patch("api.get_conversation", return_value=None)
    r = client.post("/conversations/no-such/exit-resolution", headers=HEADERS)
    assert r.status_code == 404


def test_exit_resolution_resets_mode_to_normal(mocker):
    conv = {"session_id": "sess-res", "mode": "resolution"}
    mocker.patch("api.get_conversation", return_value=conv)
    mock_update = mocker.patch("api.update_conversation")

    r = client.post("/conversations/sess-res/exit-resolution", headers=HEADERS)
    assert r.status_code == 200
    assert r.json() == {"mode": "normal"}
    mock_update.assert_called_once_with(_mock_db, "sess-res", "normal", None)
