"""Unit tests for cli._chat_loop."""
import pytest
from unittest.mock import MagicMock, patch, call


def _make_http(responses=None):
    """Build a mock httpx.Client with preset responses."""
    http = MagicMock()
    if responses:
        http.post.side_effect = responses
    return http


def _ok_json(data):
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = data
    resp.raise_for_status = MagicMock()
    return resp


class TestChatLoopQuit:
    @patch("builtins.input", return_value="/quit")
    def test_quit_exits_loop(self, mock_input):
        from cli import _chat_loop
        http = _make_http()
        _chat_loop(http, "sess-1")
        http.post.assert_not_called()


class TestChatLoopNormal:
    @patch("builtins.input", side_effect=["/normal", "/quit"])
    def test_normal_calls_exit_resolution(self, mock_input):
        from cli import _chat_loop
        http = _make_http(responses=[_ok_json({"mode": "normal"})])
        _chat_loop(http, "sess-1")
        http.post.assert_called_once_with("/conversations/sess-1/exit-resolution")


class TestChatLoopMessage:
    @patch("builtins.input", side_effect=["Hello", "/quit"])
    def test_message_calls_message_endpoint(self, mock_input):
        from cli import _chat_loop
        http = _make_http(responses=[_ok_json({"response": "Hi there"})])
        _chat_loop(http, "sess-1")
        http.post.assert_called_once_with(
            "/conversations/sess-1/message", json={"message": "Hello"}
        )
