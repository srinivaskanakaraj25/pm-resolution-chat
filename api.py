import os
os.environ["PATH"] = f"/root/.npm-global/bin:/usr/local/bin:{os.environ.get('PATH', '')}"

from dotenv import load_dotenv
load_dotenv()
from fastapi import FastAPI, HTTPException, Security
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import APIKeyHeader
from pathlib import Path
from pydantic import BaseModel
from db import init_db, list_conversations, get_conversation, update_conversation
from agent_client import AgentClient

app = FastAPI(title="PM Resolution Chat")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "https://*.vercel.app", "https://*.railway.app"],
    allow_origin_regex=r"https://.*\.(vercel\.app|railway\.app)",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

db_conn = init_db()

api_key_header = APIKeyHeader(name="X-API-Key")

def verify_api_key(api_key: str = Security(api_key_header)):
    if api_key != os.environ["API_KEY"]:
        raise HTTPException(status_code=401, detail="Invalid API key")
    return api_key


class MessageRequest(BaseModel):
    message: str
    rocketlane_api_key: str | None = None
    project_id: int | None = None


@app.post("/conversations")
async def start_conversation(body: MessageRequest, _: str = Security(verify_api_key)):
    """Start a new conversation."""
    agent = AgentClient(db_conn=db_conn, rocketlane_api_key=body.rocketlane_api_key, project_id=body.project_id)
    await agent.connect()
    try:
        response = await agent.send(body.message)
        return {"session_id": agent.session_id, "response": response}
    finally:
        await agent.disconnect()


@app.post("/conversations/{id}/message")
async def send_message(id: str, body: MessageRequest, _: str = Security(verify_api_key)):
    """Send a message to an existing conversation."""
    conv = get_conversation(db_conn, id)
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")

    agent = AgentClient(
        db_conn=db_conn,
        resume_session_id=conv["session_id"],
        rocketlane_api_key=body.rocketlane_api_key,
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
    import json as _json
    claude_dir = Path(os.environ.get("CLAUDE_CONFIG_DIR", "/root/.claude"))
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
    return list_conversations(db_conn)



@app.get("/conversations/{id}")
async def get_conversation_detail(id: str, _: str = Security(verify_api_key)):
    """Get a conversation with its full message history."""
    conv = get_conversation(db_conn, id)
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")
    messages = _read_session_messages(conv["session_id"])
    return {**conv, "messages": messages}


@app.post("/conversations/{id}/exit-resolution")
async def exit_resolution(id: str, _: str = Security(verify_api_key)):
    """Manually exit resolution mode for a conversation."""
    conv = get_conversation(db_conn, id)
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")

    update_conversation(db_conn, conv["session_id"], "normal", None)
    return {"mode": "normal"}
