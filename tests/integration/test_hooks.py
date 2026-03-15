"""Integration tests for AgentClient hook methods.

ClaudeSDKClient is already mocked globally (conftest.py), so AgentClient
can be instantiated freely. DB calls are mocked per-test.
"""
import pytest
from unittest.mock import MagicMock, patch
from agent_client import AgentClient


def _agent(**kwargs) -> AgentClient:
    """Construct a fresh AgentClient with no real DB or SDK connection."""
    return AgentClient(**kwargs)


# ---------------------------------------------------------------------------
# post_tool_use_failure
# ---------------------------------------------------------------------------

async def test_422_via_status_code_key_triggers_resolution():
    agent = _agent()
    input_data = {"status_code": 422, "detail": "unprocessable entity"}
    await agent.post_tool_use_failure(input_data, None, None)
    assert agent.state.mode == "resolution"
    assert agent.state.failure_context == {"tool_error": input_data}


async def test_422_via_status_key_triggers_resolution():
    agent = _agent()
    input_data = {"status": 422, "detail": "unprocessable entity"}
    await agent.post_tool_use_failure(input_data, None, None)
    assert agent.state.mode == "resolution"


async def test_400_does_not_trigger_resolution():
    agent = _agent()
    await agent.post_tool_use_failure({"status_code": 400}, None, None)
    assert agent.state.mode == "normal"


async def test_500_does_not_trigger_resolution():
    agent = _agent()
    await agent.post_tool_use_failure({"status_code": 500}, None, None)
    assert agent.state.mode == "normal"


async def test_missing_status_does_not_trigger_resolution():
    agent = _agent()
    await agent.post_tool_use_failure({}, None, None)
    assert agent.state.mode == "normal"


# ---------------------------------------------------------------------------
# user_prompt_submit — session_id capture
# ---------------------------------------------------------------------------

async def test_session_id_captured_on_first_call():
    agent = _agent()
    assert agent.session_id is None
    await agent.user_prompt_submit({"session_id": "new-sess-abc", "prompt": "Hi"}, None, None)
    assert agent.session_id == "new-sess-abc"


# ---------------------------------------------------------------------------
# user_prompt_submit — DB persistence
# ---------------------------------------------------------------------------

async def test_create_conversation_called_once_on_first_turn(mocker):
    mock_create = mocker.patch("agent_client.create_conversation")
    mock_db = MagicMock()
    agent = _agent(db_conn=mock_db)

    await agent.user_prompt_submit({"session_id": "sess-123", "prompt": "First message"}, None, None)

    mock_create.assert_called_once_with(mock_db, "sess-123", "First message")


async def test_create_conversation_not_called_on_subsequent_turns(mocker):
    mock_create = mocker.patch("agent_client.create_conversation")
    mock_db = MagicMock()
    agent = _agent(db_conn=mock_db)

    await agent.user_prompt_submit({"session_id": "sess-123", "prompt": "First"}, None, None)
    assert mock_create.call_count == 1

    await agent.user_prompt_submit({"session_id": "sess-123", "prompt": "Second"}, None, None)
    assert mock_create.call_count == 1  # not incremented


async def test_empty_prompt_saves_no_title_placeholder(mocker):
    mock_create = mocker.patch("agent_client.create_conversation")
    mock_db = MagicMock()
    agent = _agent(db_conn=mock_db)
    agent.session_id = "sess-empty"

    await agent.user_prompt_submit({"prompt": ""}, None, None)

    args = mock_create.call_args[0]
    assert args[2] == "(no title)"


async def test_long_prompt_title_truncated_to_50_chars(mocker):
    mock_create = mocker.patch("agent_client.create_conversation")
    mock_db = MagicMock()
    agent = _agent(db_conn=mock_db)
    agent.session_id = "sess-long"

    await agent.user_prompt_submit({"prompt": "A" * 80}, None, None)

    args = mock_create.call_args[0]
    assert args[2] == "A" * 50


# ---------------------------------------------------------------------------
# user_prompt_submit — prompt injection based on mode
# ---------------------------------------------------------------------------

async def test_resolution_entry_prompt_on_mode_transition():
    agent = _agent()
    agent._title_saved = True
    agent.state.mode = "resolution"
    agent.state.mode_changed = True

    result = await agent.user_prompt_submit({}, None, None)

    assert "hookSpecificOutput" in result
    assert result["hookSpecificOutput"]["additionalContext"] == agent.prompts["entry"]
    assert agent.state.mode_changed is False  # flag cleared


async def test_resolution_steady_prompt_when_already_in_resolution():
    agent = _agent()
    agent._title_saved = True
    agent.state.mode = "resolution"
    agent.state.mode_changed = False  # no transition, steady state

    result = await agent.user_prompt_submit({}, None, None)

    assert "hookSpecificOutput" in result
    assert result["hookSpecificOutput"]["additionalContext"] == agent.prompts["steady"]


async def test_normal_exit_prompt_on_mode_transition():
    agent = _agent()
    agent._title_saved = True
    agent.state.mode = "normal"
    agent.state.mode_changed = True  # just exited resolution

    result = await agent.user_prompt_submit({}, None, None)

    assert "hookSpecificOutput" in result
    assert result["hookSpecificOutput"]["additionalContext"] == agent.prompts["exit"]
    assert agent.state.mode_changed is False  # flag cleared


async def test_normal_mode_no_change_returns_empty():
    agent = _agent()
    agent._title_saved = True
    agent.state.mode = "normal"
    agent.state.mode_changed = False

    result = await agent.user_prompt_submit({}, None, None)

    assert result == {}
