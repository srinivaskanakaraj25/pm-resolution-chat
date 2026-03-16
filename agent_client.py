from claude_agent_sdk import (
    ClaudeSDKClient,
    ClaudeAgentOptions,
    HookMatcher,
    AssistantMessage,
    TextBlock,
)
import asyncio
import os
import json
import logging
import psycopg2
from typing import Optional

logger = logging.getLogger(__name__)
from db import create_conversation, update_conversation

_DISALLOWED_CLAUDE_CODE_TOOLS = [
    "Bash",
    "Edit",
    "Glob",
    "Grep",
    "LS",
    "MultiEdit",
    "NotebookEdit",
    "NotebookRead",
    "Read",
    "Task",
    "TodoWrite",
    "WebFetch",
    "WebSearch",
    "Write",
]


def _parse_csv_env(name: str) -> list[str]:
    value = os.environ.get(name, "")
    return [item.strip() for item in value.split(",") if item.strip()]


class AgentState:
    def __init__(self):
        self.mode = "normal"
        self.previous_mode = None
        self.mode_changed = False
        self.failure_context = None

    def enter_resolution(self, ctx=None):
        if self.mode != "resolution":
            self.previous_mode = self.mode
            self.mode = "resolution"
            self.mode_changed = True
        self.failure_context = ctx

    def exit_resolution(self):
        if self.mode == "resolution":
            self.previous_mode = self.mode
            self.mode = "normal"
            self.mode_changed = True

    def clear_transition_flag(self):
        self.mode_changed = False


class AgentClient:
    def __init__(
        self,
        db_conn: Optional[psycopg2.extensions.connection] = None,
        resume_session_id: Optional[str] = None,
        project_id: Optional[int] = None,
    ):
        self.state = AgentState()
        self.prompts = self._load_prompts()
        self.db_conn = db_conn
        self.session_id = resume_session_id
        self.project_id = project_id
        self._title_saved = resume_session_id is not None

        hooks = {
            "PostToolUseFailure": [
                HookMatcher(hooks=[self.post_tool_use_failure])
            ],
            "UserPromptSubmit": [
                HookMatcher(hooks=[self.user_prompt_submit])
            ],
        }

        self._cwd = os.path.dirname(os.path.abspath(__file__))
        self._claude_config_dir = os.environ.get(
            "CLAUDE_CONFIG_DIR",
            os.path.join(self._cwd, ".claude-runtime"),
        )
        self._hooks = hooks
        self._resume_session_id = resume_session_id

        self.client = self._build_client(resume=resume_session_id)

    def _build_client(self, resume: Optional[str] = None) -> ClaudeSDKClient:
        options = ClaudeAgentOptions(
            system_prompt={
                "type": "preset",
                "preset": "claude_code",
                "append": self.prompts["system"],
            },
            tools=[],
            allowed_tools=_parse_csv_env("AGENT_ALLOWED_TOOLS"),
            disallowed_tools=_DISALLOWED_CLAUDE_CODE_TOOLS,
            hooks=self._hooks,
            resume=resume,
            cwd=self._cwd,
            setting_sources=["project"],
            stderr=lambda line: logger.warning("[claude stderr] %s", line),
            env={"CLAUDE_CONFIG_DIR": self._claude_config_dir},
        )
        return ClaudeSDKClient(options=options)

    async def connect(self):
        try:
            await self.client.connect()
        except Exception:
            if self._resume_session_id is None:
                raise
            logger.error(
                "Resume failed for session %s — falling back to new session",
                self._resume_session_id,
            )
            self.client = self._build_client(resume=None)
            await self.client.connect()

    async def disconnect(self):
        await self.client.disconnect()

    _SEND_TIMEOUT = float(os.environ.get("AGENT_SEND_TIMEOUT", "300"))

    async def send(self, text: str) -> str:
        """Send text and return Claude's response, with timeout."""
        try:
            return await asyncio.wait_for(
                self._send_inner(text), timeout=self._SEND_TIMEOUT
            )
        except asyncio.TimeoutError:
            logger.warning("send() timed out after %ss", self._SEND_TIMEOUT)
            self._persist_state()
            return "[Response timed out. Please try again or simplify your request.]"

    async def _send_inner(self, text: str) -> str:
        """Core send logic — query + collect response + persist state."""
        await self.client.query(text)
        response_parts = []
        async for msg in self.client.receive_response():
            if isinstance(msg, AssistantMessage):
                for block in msg.content:
                    if isinstance(block, TextBlock):
                        response_parts.append(block.text)

        self._persist_state()

        response = "".join(response_parts)
        logger.debug("Agent response: %.200s", response)
        return response

    def _persist_state(self):
        """Save current mode and failure context to DB."""
        if self.db_conn is not None and self.session_id is not None:
            fc = (
                json.dumps(self.state.failure_context)
                if self.state.failure_context
                else None
            )
            update_conversation(self.db_conn, self.session_id, self.state.mode, fc)

    def exit_resolution_mode(self):
        self.state.exit_resolution()

    def restore_state(self, mode: str, failure_context_json: Optional[str]) -> None:
        """Restore state when resuming a conversation."""
        self.state.mode = mode
        if failure_context_json:
            self.state.failure_context = json.loads(failure_context_json)

    def _load_prompts(self):
        base = os.path.join(os.path.dirname(__file__), "prompts")

        def load(name):
            with open(os.path.join(base, name)) as f:
                return f.read()

        return {
            "system": load("system.md"),
            "entry": load("resolution_entry.md"),
            "steady": load("resolution.md"),
            "exit": load("resolution_exit.md"),
        }

    async def post_tool_use_failure(self, input_data, tool_use_id, context):
        error_text = ""
        tool_error = {}
        status = None
        if isinstance(input_data, dict):
            status = input_data.get("status_code") or input_data.get("status")
            error_text = str(input_data.get("error", ""))
            tool_error = {
                **input_data,
                "tool_name": input_data.get("tool_name"),
                "tool_input": input_data.get("tool_input", {}),
                "error": error_text,
                "error_text": error_text,
            }
        else:
            error_text = str(input_data)
            tool_error = {"error": error_text, "error_text": error_text}

        if status == 422 or "422" in error_text or "unprocessable" in error_text.lower():
            self.state.enter_resolution({"tool_error": tool_error})
            return {
                "hookSpecificOutput": {
                    "hookEventName": "PostToolUseFailure",
                    "additionalContext": (
                        "A tool call failed with a 422-style validation error. "
                        "Stay in resolution mode and help the user identify the "
                        "missing or invalid input before retrying."
                    ),
                }
            }

        return {}

    async def user_prompt_submit(self, input_data, tool_use_id, context):
        if self.session_id is None:
            self.session_id = input_data.get("session_id")

        if not self._title_saved and self.db_conn is not None:
            title = (input_data.get("prompt", "") or "")[:50].strip() or "(no title)"
            create_conversation(self.db_conn, self.session_id, title, project_id=self.project_id)
            self._title_saved = True

        # Determine mode-based prompt injection
        mode_prompt = None
        if self.state.mode == "resolution" and self.state.mode_changed:
            self.state.clear_transition_flag()
            mode_prompt = self.prompts["entry"]
        elif self.state.mode == "normal" and self.state.mode_changed:
            self.state.clear_transition_flag()
            mode_prompt = self.prompts["exit"]
        elif self.state.mode == "resolution":
            mode_prompt = self.prompts["steady"]

        # Append project scope when a project_id is active
        project_ctx = (
            f"\n\n[Active project: {self.project_id}. "
            f"Scope all queries and actions to this project unless the user explicitly asks otherwise.]"
            if self.project_id else ""
        )

        additional = (mode_prompt or "") + project_ctx
        if additional:
            return {
                "hookSpecificOutput": {
                    "hookEventName": "UserPromptSubmit",
                    "additionalContext": additional,
                }
            }

        return {}
