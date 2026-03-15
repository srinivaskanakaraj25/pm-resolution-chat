"""Unit tests for AgentState — pure state machine, no external dependencies."""
from agent_client import AgentState


def test_initial_state():
    s = AgentState()
    assert s.mode == "normal"
    assert s.mode_changed is False
    assert s.failure_context is None


def test_enter_resolution_from_normal():
    s = AgentState()
    s.enter_resolution()
    assert s.mode == "resolution"
    assert s.mode_changed is True
    assert s.previous_mode == "normal"


def test_enter_resolution_when_already_in_resolution():
    s = AgentState()
    s.enter_resolution()
    s.mode_changed = False  # reset the flag
    s.enter_resolution()
    assert s.mode == "resolution"
    assert s.mode_changed is False  # must not flip again


def test_enter_resolution_stores_context():
    s = AgentState()
    ctx = {"tool_error": {"status_code": 422}}
    s.enter_resolution(ctx)
    assert s.failure_context == ctx


def test_enter_resolution_twice_updates_context():
    s = AgentState()
    s.enter_resolution({"error": "first"})
    s.enter_resolution({"error": "second"})
    assert s.failure_context == {"error": "second"}


def test_exit_resolution_from_resolution():
    s = AgentState()
    s.enter_resolution()
    s.mode_changed = False  # reset so we can test exit independently
    s.exit_resolution()
    assert s.mode == "normal"
    assert s.mode_changed is True


def test_exit_resolution_from_normal_is_noop():
    s = AgentState()
    # already normal — exit should be a no-op
    s.exit_resolution()
    assert s.mode == "normal"
    assert s.mode_changed is False


def test_clear_transition_flag():
    s = AgentState()
    s.enter_resolution()
    assert s.mode_changed is True
    s.clear_transition_flag()
    assert s.mode_changed is False
