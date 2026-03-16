"""Shared pytest fixtures and setup for all test tiers."""
import sys
import os
from unittest.mock import MagicMock, AsyncMock
import pytest

# Add project root to sys.path so test files can import source modules
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

# Fall back to a mock SDK only when the real package isn't installed.
try:
    import claude_agent_sdk  # noqa: F401
except ImportError:
    if "claude_agent_sdk" not in sys.modules:
        mock_sdk = MagicMock()
        sys.modules["claude_agent_sdk"] = mock_sdk

# Provide a default API_KEY so api.py and auth tests have something to work with
os.environ.setdefault("API_KEY", "test-api-key")
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost:5432/test")


@pytest.fixture
def mock_sdk_client():
    """Patch ClaudeSDKClient in agent_client's namespace so the constructor doesn't connect."""
    from unittest.mock import patch
    with patch("agent_client.ClaudeSDKClient") as mock_cls:
        yield mock_cls


@pytest.fixture
def mock_agent():
    """Pre-configured MagicMock standing in for AgentClient."""
    agent = MagicMock()
    agent.connect = AsyncMock()
    agent.disconnect = AsyncMock()
    agent.send = AsyncMock(return_value="Test response")
    agent.session_id = "test-session-id"
    agent.state = MagicMock()
    agent.state.mode = "normal"
    agent.restore_state = MagicMock()
    return agent
