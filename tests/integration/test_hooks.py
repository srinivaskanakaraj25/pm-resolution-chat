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
    assert agent.state.failure_context["tool_error"]["status_code"] == 422


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


async def test_422_in_string_input_data_triggers_resolution():
    agent = _agent()
    await agent.post_tool_use_failure("HTTP 422: Unprocessable Entity", None, None)
    assert agent.state.mode == "resolution"
    assert agent.state.failure_context["tool_error"]["error_text"] == "HTTP 422: Unprocessable Entity"


async def test_current_sdk_failure_payload_triggers_resolution():
    agent = _agent()
    payload = {
        "tool_name": "rocketlane.create_task",
        "tool_input": {"title": ""},
        "error": "422 Unprocessable Entity: title is required",
    }
    result = await agent.post_tool_use_failure(payload, None, None)
    assert agent.state.mode == "resolution"
    assert agent.state.failure_context["tool_error"]["tool_name"] == "rocketlane.create_task"
    assert result["hookSpecificOutput"]["hookEventName"] == "PostToolUseFailure"


async def test_non_422_string_does_not_trigger_resolution():
    agent = _agent()
    await agent.post_tool_use_failure("HTTP 500: Internal Server Error", None, None)
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

    mock_create.assert_called_once_with(mock_db, "sess-123", "First message", project_id=None)


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


# ---------------------------------------------------------------------------
# user_prompt_submit — project_id context injection
# ---------------------------------------------------------------------------

async def test_project_id_injected_in_normal_mode():
    agent = _agent(project_id=42)
    agent._title_saved = True
    agent.state.mode = "normal"
    agent.state.mode_changed = False

    result = await agent.user_prompt_submit({}, None, None)

    ctx = result["hookSpecificOutput"]["additionalContext"]
    assert "42" in ctx


async def test_project_id_combined_with_mode_prompt():
    agent = _agent(project_id=99)
    agent._title_saved = True
    agent.state.mode = "resolution"
    agent.state.mode_changed = True

    result = await agent.user_prompt_submit({}, None, None)

    ctx = result["hookSpecificOutput"]["additionalContext"]
    # Must contain both the resolution entry prompt and the project context
    assert agent.prompts["entry"] in ctx
    assert "99" in ctx


async def test_no_project_id_does_not_inject_context():
    agent = _agent()  # no project_id
    agent._title_saved = True
    agent.state.mode = "normal"
    agent.state.mode_changed = False

    result = await agent.user_prompt_submit({}, None, None)

    assert result == {}


async def test_project_id_stored_in_db_on_first_turn(mocker):
    mock_create = mocker.patch("agent_client.create_conversation")
    mock_db = MagicMock()
    agent = _agent(db_conn=mock_db, project_id=7)

    await agent.user_prompt_submit({"session_id": "sess-p7", "prompt": "Hello"}, None, None)

    _, kwargs = mock_create.call_args
    assert kwargs.get("project_id") == 7


def test_sdk_client_is_built_with_locked_down_tools(mock_sdk_client):
    _agent()

    options = mock_sdk_client.call_args.kwargs["options"]
    assert options.tools == []
    assert options.allowed_tools == []
    assert "Read" in options.disallowed_tools
    assert options.setting_sources == ["project"]
    assert options.system_prompt["preset"] == "claude_code"


# ---------------------------------------------------------------------------
# send() timeout behavior
# ---------------------------------------------------------------------------

async def test_send_timeout_returns_timeout_message(mocker):
    import asyncio
    agent = _agent()
    agent.session_id = "sess-timeout"

    async def slow_query(text):
        await asyncio.sleep(10)

    agent.client.connect = mocker.AsyncMock()
    agent.client.query = slow_query
    agent._SEND_TIMEOUT = 0.01  # very short timeout

    result = await agent.send("Hello")
    assert "timed out" in result.lower()


async def test_send_timeout_persists_state(mocker):
    import asyncio
    mock_update = mocker.patch("agent_client.update_conversation")
    mock_db = MagicMock()
    agent = _agent(db_conn=mock_db)
    agent.session_id = "sess-timeout-db"

    async def slow_query(text):
        await asyncio.sleep(10)

    agent.client.connect = mocker.AsyncMock()
    agent.client.query = slow_query
    agent._SEND_TIMEOUT = 0.01

    await agent.send("Hello")
    mock_update.assert_called_once()
