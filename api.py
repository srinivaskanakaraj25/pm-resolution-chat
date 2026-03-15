import os
os.environ["PATH"] = f"/root/.npm-global/bin:/usr/local/bin:{os.environ.get('PATH', '')}"

from dotenv import load_dotenv
load_dotenv()
from fastapi import FastAPI, HTTPException, Security
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import APIKeyHeader
import json as _json
import logging
from pathlib import Path
from pydantic import BaseModel
from db import init_db, get_conn, list_conversations, get_conversation, update_conversation
from agent_client import AgentClient

logger = logging.getLogger(__name__)

app = FastAPI(title="PM Resolution Chat")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "https://*.vercel.app", "https://*.railway.app"],
    allow_origin_regex=r"https://.*\.(vercel\.app|railway\.app)",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

db_pool = init_db()

api_key_header = APIKeyHeader(name="X-API-Key")

def verify_api_key(api_key: str = Security(api_key_header)):
    if api_key != os.environ["API_KEY"]:
        raise HTTPException(status_code=401, detail="Invalid API key")
    return api_key


class MessageRequest(BaseModel):
    message: str
    rocketlane_api_key: str | None = None
    project_id: int | None = None


def _read_tool_results(request_id: str) -> list[dict]:
    """Read and cleanup full tool results written by the proxy for this request."""
    results_dir = Path(os.environ.get("RAILWAY_VOLUME_MOUNT_PATH", "/data")) / "tool_results"
    if not results_dir.exists():
        return []
    results = []
    for path in sorted(results_dir.glob(f"{request_id}_*.json")):
        try:
            data = _json.loads(path.read_text())
            # filename: {request_id}_{tool_name}_{timestamp}.json
            parts = path.stem.split("_", 1)
            tool_name = parts[1].rsplit("_", 1)[0] if len(parts) > 1 else "unknown"
            results.append({"tool_name": tool_name, "data": data})
            path.unlink()
        except Exception:
            continue
    return results


@app.post("/conversations")
async def start_conversation(body: MessageRequest, _: str = Security(verify_api_key)):
    """Start a new conversation."""
    with get_conn(db_pool) as conn:
        agent = AgentClient(db_conn=conn, rocketlane_api_key=body.rocketlane_api_key, project_id=body.project_id)
        await agent.connect()
        try:
            response = await agent.send(body.message)
            tool_data = _read_tool_results(agent.request_id)
            return {"session_id": agent.session_id, "response": response, "tool_data": tool_data}
        finally:
            await agent.disconnect()


@app.post("/conversations/{id}/message")
async def send_message(id: str, body: MessageRequest, _: str = Security(verify_api_key)):
    """Send a message to an existing conversation."""
    with get_conn(db_pool) as conn:
        conv = get_conversation(conn, id)
        if not conv:
            raise HTTPException(status_code=404, detail="Conversation not found")

        agent = AgentClient(
            db_conn=conn,
            resume_session_id=conv["session_id"],
            rocketlane_api_key=body.rocketlane_api_key,
            project_id=body.project_id or conv.get("project_id"),
        )
        agent.restore_state(conv["mode"], conv["failure_context"])
        await agent.connect()
        try:
            response = await agent.send(body.message)
            tool_data = _read_tool_results(agent.request_id)
            return {"response": response, "mode": agent.state.mode, "tool_data": tool_data}
        finally:
            await agent.disconnect()


def _read_session_messages(session_id: str) -> list[dict]:
    """Read message history from the Claude SDK JSONL file on the volume."""
    claude_dir = Path(os.environ.get("CLAUDE_CONFIG_DIR", "/data"))
    cwd = os.path.dirname(os.path.abspath(__file__))
    project_hash = cwd.replace("/", "-")
    session_file = claude_dir / "projects" / project_hash / f"{session_id}.jsonl"
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


@app.get("/conversations")
async def list_all(_: str = Security(verify_api_key)):
    """List all conversations."""
    with get_conn(db_pool) as conn:
        return list_conversations(conn)


@app.get("/conversations/{id}")
async def get_conversation_detail(id: str, _: str = Security(verify_api_key)):
    """Get a conversation with its full message history."""
    with get_conn(db_pool) as conn:
        conv = get_conversation(conn, id)
        if not conv:
            raise HTTPException(status_code=404, detail="Conversation not found")
        messages = _read_session_messages(conv["session_id"])
        return {**conv, "messages": messages}


@app.get("/debug/sessions")
async def debug_sessions(_: str = Security(verify_api_key)):
    """List Claude session files on disk for diagnosis."""
    import glob as _glob
    claude_config_dir = os.environ.get("CLAUDE_CONFIG_DIR", "/data")
    cwd = os.path.dirname(os.path.abspath(__file__))
    project_hash = cwd.replace("/", "-")
    session_dir = Path(claude_config_dir) / "projects" / project_hash
    files = sorted(_glob.glob(str(session_dir / "*.jsonl")))
    return {
        "claude_config_dir": claude_config_dir,
        "session_dir": str(session_dir),
        "session_dir_exists": session_dir.exists(),
        "session_files": [Path(f).name for f in files],
        "count": len(files),
    }


@app.post("/conversations/{id}/exit-resolution")
async def exit_resolution(id: str, _: str = Security(verify_api_key)):
    """Manually exit resolution mode for a conversation."""
    with get_conn(db_pool) as conn:
        conv = get_conversation(conn, id)
        if not conv:
            raise HTTPException(status_code=404, detail="Conversation not found")

        update_conversation(conn, conv["session_id"], "normal", None)
        return {"mode": "normal"}
