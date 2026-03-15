from claude_agent_sdk import (
    ClaudeSDKClient,
    ClaudeAgentOptions,
    HookMatcher,
    AssistantMessage,
    TextBlock,
)
import os
import json
import psycopg2
from typing import Optional
from db import create_conversation, update_conversation


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
    ):
        self.state = AgentState()
        self.prompts = self._load_prompts()
        self.db_conn = db_conn
        self.session_id = resume_session_id
        self._title_saved = resume_session_id is not None

        hooks = {
            "PostToolUseFailure": [
                HookMatcher(hooks=[self.post_tool_use_failure])
            ],
            "UserPromptSubmit": [
                HookMatcher(hooks=[self.user_prompt_submit])
            ],
        }

        def _stderr_callback(line: str) -> None:
            with open("/tmp/claude_debug.log", "a") as f:
                f.write(line + "\n")

        from tools import start_proxy
        mcp_servers = {}
        if os.environ.get("ROCKETLANE_API_KEY"):
            mcp_servers["rocketlane-proxy"] = start_proxy()

        options = ClaudeAgentOptions(
            system_prompt=self.prompts["system"],
            hooks=hooks,
            resume=resume_session_id,
            stderr=_stderr_callback,
            cwd=os.path.dirname(os.path.abspath(__file__)),
            setting_sources=["project"],
            mcp_servers=mcp_servers or None,
            allowed_tools=[
                "mcp__rocketlane-proxy__search_rocketlane_tools",
                "mcp__rocketlane-proxy__call_rocketlane_tool",
            ],
        )

        self.client = ClaudeSDKClient(options=options)

    async def connect(self):
        await self.client.connect()

    async def disconnect(self):
        await self.client.disconnect()

    async def send(self, text: str) -> str:
        """Send text and return Claude's response."""
        await self.client.query(text)
        response_parts = []
        async for msg in self.client.receive_response():
            if isinstance(msg, AssistantMessage):
                for block in msg.content:
                    if isinstance(block, TextBlock):
                        response_parts.append(block.text)

        # Persist state after each turn
        if self.db_conn is not None and self.session_id is not None:
            fc = (
                json.dumps(self.state.failure_context)
                if self.state.failure_context
                else None
            )
            update_conversation(self.db_conn, self.session_id, self.state.mode, fc)

        response = "".join(response_parts)
        print(f"Claude: {response}")
        return response

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
        status = input_data.get("status_code") or input_data.get("status")
        if status == 422:
            self.state.enter_resolution({"tool_error": input_data})
        return {}

    async def user_prompt_submit(self, input_data, tool_use_id, context):
        if self.session_id is None:
            self.session_id = input_data.get("session_id")

        if not self._title_saved and self.db_conn is not None:
            title = (input_data.get("prompt", "") or "")[:50].strip() or "(no title)"
            create_conversation(self.db_conn, self.session_id, title)
            self._title_saved = True

        if self.state.mode == "resolution" and self.state.mode_changed:
            self.state.clear_transition_flag()
            return {
                "hookSpecificOutput": {
                    "hookEventName": "UserPromptSubmit",
                    "additionalContext": self.prompts["entry"],
                }
            }

        if self.state.mode == "normal" and self.state.mode_changed:
            self.state.clear_transition_flag()
            return {
                "hookSpecificOutput": {
                    "hookEventName": "UserPromptSubmit",
                    "additionalContext": self.prompts["exit"],
                }
            }

        if self.state.mode == "resolution":
            return {
                "hookSpecificOutput": {
                    "hookEventName": "UserPromptSubmit",
                    "additionalContext": self.prompts["steady"],
                }
            }

        return {}
