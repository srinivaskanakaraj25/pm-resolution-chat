"""Unit tests for AgentClient.restore_state() — ClaudeSDKClient is mocked."""
import json
from agent_client import AgentClient


def _make_agent(**kwargs) -> AgentClient:
    """Construct AgentClient with the already-mocked claude_agent_sdk SDK."""
    return AgentClient(**kwargs)


def test_restore_resolution_mode_with_context():
    agent = _make_agent()
    ctx = {"tool_error": {"status_code": 422, "detail": "unprocessable"}}
    agent.restore_state("resolution", json.dumps(ctx))
    assert agent.state.mode == "resolution"
    assert agent.state.failure_context == ctx


def test_restore_normal_mode_no_context():
    agent = _make_agent()
    agent.restore_state("normal", None)
    assert agent.state.mode == "normal"
    assert agent.state.failure_context is None
