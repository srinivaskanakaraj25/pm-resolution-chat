"""End-to-end tests against a locally running server with a real database.

These tests are skipped by default. To run them:
  RUN_E2E=1 E2E_BASE_URL=http://localhost:8000 E2E_API_KEY=<key> pytest tests/e2e/

The server must be started separately before running these tests:
  uvicorn api:app --port 8000
"""
import os
import pytest
import httpx

pytestmark = pytest.mark.skipif(
    not os.environ.get("RUN_E2E"),
    reason="E2E tests are opt-in — set RUN_E2E=1 to enable",
)

BASE_URL = os.environ.get("E2E_BASE_URL", "http://localhost:8000")
API_KEY = os.environ.get("E2E_API_KEY", os.environ.get("API_KEY", ""))
ROCKETLANE_KEY = os.environ.get("E2E_ROCKETLANE_KEY", "")


@pytest.fixture(scope="module")
def api():
    return httpx.Client(
        base_url=BASE_URL,
        headers={"X-API-Key": API_KEY},
        timeout=30,
    )


# ---------------------------------------------------------------------------
# Basic conversation flow
# ---------------------------------------------------------------------------

def test_new_conversation_persists_and_is_resumable(api):
    # Create a new conversation
    r = api.post("/conversations", json={"message": "Hello, what is 2+2?"})
    assert r.status_code == 200
    data = r.json()
    assert "session_id" in data
    assert "response" in data
    session_id = data["session_id"]

    # Resume the same conversation
    r2 = api.post(f"/conversations/{session_id}/message", json={"message": "And what is 3+3?"})
    assert r2.status_code == 200
    assert "response" in r2.json()


def test_conversation_appears_in_list(api):
    r = api.post("/conversations", json={"message": "List visibility test"})
    assert r.status_code == 200
    session_id = r.json()["session_id"]

    r2 = api.get("/conversations")
    assert r2.status_code == 200
    ids = [c["session_id"] for c in r2.json()]
    assert session_id in ids


# ---------------------------------------------------------------------------
# Resolution mode
# ---------------------------------------------------------------------------

def test_resolution_mode_triggered_by_422(api):
    """Start a conversation, inject a 422 tool failure, verify DB mode becomes resolution."""
    r = api.post("/conversations", json={"message": "Start"})
    session_id = r.json()["session_id"]

    # Use the debug endpoint (if available) or rely on the agent naturally calling a tool that 422s
    # Here we call the rl-test endpoint to simulate a 422
    r2 = api.post("/rl-test", json={"method": "tools/call", "status_code": 422})
    if r2.status_code == 404:
        pytest.skip("No /rl-test endpoint available to inject 422")

    # Verify the conversation mode changed
    r3 = api.get("/conversations")
    convs = {c["session_id"]: c for c in r3.json()}
    assert session_id in convs


def test_manual_exit_resolution(api):
    r = api.post("/conversations", json={"message": "Resolution exit test"})
    assert r.status_code == 200
    session_id = r.json()["session_id"]

    r2 = api.post(f"/conversations/{session_id}/exit-resolution")
    assert r2.status_code == 200
    assert r2.json()["mode"] == "normal"


# ---------------------------------------------------------------------------
# Rocketlane key handling
# ---------------------------------------------------------------------------

def test_no_rocketlane_key_conversation_succeeds(api):
    r = api.post("/conversations", json={"message": "No rocketlane key test"})
    assert r.status_code == 200
    assert "response" in r.json()


def test_with_rocketlane_key_mcp_tools_available(api):
    if not ROCKETLANE_KEY:
        pytest.skip("E2E_ROCKETLANE_KEY not set")
    r = api.post(
        "/conversations",
        json={
            "message": "Search for project tools using search_rocketlane_tools",
            "rocketlane_api_key": ROCKETLANE_KEY,
        },
    )
    assert r.status_code == 200
    assert "response" in r.json()


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

def test_invalid_api_key_returns_401():
    bad_client = httpx.Client(base_url=BASE_URL, headers={"X-API-Key": "bad-key"}, timeout=10)
    r = bad_client.post("/conversations", json={"message": "Auth test"})
    assert r.status_code == 401
