import glob
import os
import re
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated

import json as _json
import logging

def _configure_deploy_path():
    """Ensure Claude Code CLI is on PATH in Railway container."""
    if os.path.exists("/root/.npm-global/bin"):
        os.environ["PATH"] = f"/root/.npm-global/bin:/usr/local/bin:{os.environ.get('PATH', '')}"

_configure_deploy_path()

from dotenv import load_dotenv
load_dotenv()
from fastapi import FastAPI, HTTPException, Request, Security
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import APIKeyHeader
from pydantic import BaseModel, StringConstraints

from db import init_db, get_conn, list_conversations, get_conversation, update_conversation
from agent_client import AgentClient

logger = logging.getLogger(__name__)

_SANITIZE_RE = re.compile(r"[^a-zA-Z0-9]")
_LOCAL_CLAUDE_DIR = Path(__file__).resolve().parent / ".claude-runtime"


def _get_claude_config_dir() -> Path:
    configured = os.environ.get("CLAUDE_CONFIG_DIR")
    return Path(configured) if configured else _LOCAL_CLAUDE_DIR


def _sanitize_project_path(path: str) -> str:
    return _SANITIZE_RE.sub("-", path)


def _claude_project_dir() -> Path:
    claude_dir = _get_claude_config_dir()
    cwd = os.path.dirname(os.path.abspath(__file__))
    return claude_dir / "projects" / _sanitize_project_path(cwd)


@asynccontextmanager
async def lifespan(app: FastAPI):
    claude_dir = _get_claude_config_dir()
    claude_dir.mkdir(parents=True, exist_ok=True)
    app.state.db_pool = init_db()
    logger.info("Starting PM Resolution Chat with Claude config dir %s", claude_dir)
    try:
        yield
    finally:
        db_pool = getattr(app.state, "db_pool", None)
        if db_pool is not None:
            db_pool.closeall()


app = FastAPI(title="PM Resolution Chat", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_origin_regex=r"https://.*\.(vercel\.app|railway\.app)",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)

def verify_api_key(api_key: str = Security(api_key_header)):
    configured_api_key = os.environ.get("API_KEY")
    if not configured_api_key or api_key != configured_api_key:
        raise HTTPException(status_code=401, detail="Invalid API key")
    return api_key


def _db_pool(request: Request):
    pool = getattr(request.app.state, "db_pool", None)
    if pool is None:
        pool = init_db()
        request.app.state.db_pool = pool
    return pool


class MessageRequest(BaseModel):
    message: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
    project_id: int | None = None


@app.post("/conversations")
async def start_conversation(
    body: MessageRequest,
    request: Request,
    _: str = Security(verify_api_key),
):
    """Start a new conversation."""
    with get_conn(_db_pool(request)) as conn:
        agent = AgentClient(db_conn=conn, project_id=body.project_id)
        await agent.connect()
        try:
            response = await agent.send(body.message)
            return {"session_id": agent.session_id, "response": response}
        finally:
            await agent.disconnect()


@app.post("/conversations/{id}/message")
async def send_message(
    id: str,
    body: MessageRequest,
    request: Request,
    _: str = Security(verify_api_key),
):
    """Send a message to an existing conversation."""
    with get_conn(_db_pool(request)) as conn:
        conv = get_conversation(conn, id)
        if not conv:
            raise HTTPException(status_code=404, detail="Conversation not found")

        agent = AgentClient(
            db_conn=conn,
            resume_session_id=conv["session_id"],
            project_id=body.project_id or conv.get("project_id"),
        )
        agent.restore_state(conv["mode"], conv["failure_context"])
        await agent.connect()
        try:
            response = await agent.send(body.message)
            return {"response": response, "mode": agent.state.mode}
        finally:
            await agent.disconnect()


def _read_session_messages(session_id: str) -> list[dict]:
    """Read message history from the Claude SDK JSONL file on the volume."""
    session_file = _claude_project_dir() / f"{session_id}.jsonl"
    if not session_file.exists():
        return []
    messages = []
    for line in session_file.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            entry = _json.loads(line)
            role = entry.get("role")
            if role not in ("user", "assistant"):
                continue
            content = entry.get("message", {}).get("content") or entry.get("content", "")
            if isinstance(content, list):
                text = " ".join(
                    b.get("text", "") for b in content
                    if isinstance(b, dict) and b.get("type") == "text"
                )
            else:
                text = str(content)
            if text.strip():
                messages.append({"role": role, "text": text.strip()})
        except Exception:
            continue
    return messages


@app.get("/health")
async def healthcheck():
    """Railway-friendly health check."""
    return {"status": "ok"}


@app.get("/conversations")
async def list_all(request: Request, _: str = Security(verify_api_key)):
    """List all conversations."""
    with get_conn(_db_pool(request)) as conn:
        return list_conversations(conn)


@app.get("/conversations/{id}")
async def get_conversation_detail(
    id: str,
    request: Request,
    _: str = Security(verify_api_key),
):
    """Get a conversation with its full message history."""
    with get_conn(_db_pool(request)) as conn:
        conv = get_conversation(conn, id)
        if not conv:
            raise HTTPException(status_code=404, detail="Conversation not found")
        messages = _read_session_messages(conv["session_id"])
        return {**conv, "messages": messages}


@app.get("/debug/sessions")
async def debug_sessions(_: str = Security(verify_api_key)):
    """List Claude session files on disk for diagnosis."""
    claude_config_dir = str(_get_claude_config_dir())
    session_dir = _claude_project_dir()
    files = sorted(glob.glob(str(session_dir / "*.jsonl")))
    return {
        "claude_config_dir": claude_config_dir,
        "session_dir": str(session_dir),
        "session_dir_exists": session_dir.exists(),
        "session_files": [Path(f).name for f in files],
        "count": len(files),
    }


@app.post("/conversations/{id}/exit-resolution")
async def exit_resolution(id: str, request: Request, _: str = Security(verify_api_key)):
    """Manually exit resolution mode for a conversation."""
    with get_conn(_db_pool(request)) as conn:
        conv = get_conversation(conn, id)
        if not conv:
            raise HTTPException(status_code=404, detail="Conversation not found")

        update_conversation(conn, conv["session_id"], "normal", None)
        return {"mode": "normal"}
