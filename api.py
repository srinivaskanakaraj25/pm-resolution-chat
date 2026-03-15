import os
os.environ["PATH"] = f"/root/.npm-global/bin:/usr/local/bin:{os.environ.get('PATH', '')}"

from dotenv import load_dotenv
load_dotenv()
from fastapi import FastAPI, HTTPException, Security
from fastapi.security import APIKeyHeader
from pydantic import BaseModel
from db import init_db, list_conversations, get_conversation, update_conversation
from agent_client import AgentClient

app = FastAPI(title="PM Resolution Chat")



db_conn = init_db()

api_key_header = APIKeyHeader(name="X-API-Key")

def verify_api_key(api_key: str = Security(api_key_header)):
    if api_key != os.environ["API_KEY"]:
        raise HTTPException(status_code=401, detail="Invalid API key")
    return api_key


class MessageRequest(BaseModel):
    message: str


@app.post("/conversations")
async def start_conversation(body: MessageRequest, _: str = Security(verify_api_key)):
    """Start a new conversation."""
    agent = AgentClient(db_conn=db_conn)
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

    agent = AgentClient(db_conn=db_conn, resume_session_id=conv["session_id"])
    agent.restore_state(conv["mode"], conv["failure_context"])
    await agent.connect()
    try:
        response = await agent.send(body.message)
        return {"response": response, "mode": agent.state.mode}
    finally:
        await agent.disconnect()


@app.get("/conversations")
async def list_all(_: str = Security(verify_api_key)):
    """List all conversations."""
    return list_conversations(db_conn)


@app.get("/debug/claude-log")
async def debug_log(_: str = Security(verify_api_key)):
    try:
        with open("/tmp/claude_debug.log") as f:
            return {"log": f.read()[-5000:]}
    except FileNotFoundError:
        return {"log": "no log yet"}



@app.get("/debug/env")
async def debug_env(_: str = Security(verify_api_key)):
    import subprocess, glob as g
    claude_path = subprocess.run(["which", "claude"], capture_output=True, text=True).stdout.strip()
    home = os.path.expanduser("~")
    projects_dir = os.path.join(home, ".claude", "projects")
    jsonl_files = g.glob(os.path.join(projects_dir, "**", "*.jsonl"), recursive=True)
    return {
        "claude_path": claude_path,
        "home": home,
        "claude_dir_exists": os.path.exists(os.path.join(home, ".claude")),
        "claude_projects_exists": os.path.exists(projects_dir),
        "jsonl_files": jsonl_files,
        "rocketlane_api_key_set": bool(os.environ.get("ROCKETLANE_API_KEY")),
    }


@app.get("/debug/rl-test")
async def rl_test(_: str = Security(verify_api_key)):
    import httpx
    api_key = os.environ.get("ROCKETLANE_API_KEY", "")
    url = "https://rocket-mcp.rl-platforms.rocketlane.com/mcp"
    headers = {"api-key": api_key, "Content-Type": "application/json", "Accept": "application/json, text/event-stream"}
    # Init session
    r1 = httpx.post(url, headers=headers, json={"jsonrpc":"2.0","method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"test","version":"1.0"}},"id":1}, timeout=15)
    session_id = r1.headers.get("mcp-session-id")
    if not session_id:
        return {"error": "No mcp-session-id in initialize response", "body": r1.text[:500]}
    headers["mcp-session-id"] = session_id
    # Send notifications/initialized to complete handshake
    r_notify = httpx.post(url, headers=headers, json={"jsonrpc":"2.0","method":"notifications/initialized"}, timeout=15)
    # Call tool
    r2 = httpx.post(url, headers=headers, json={"jsonrpc":"2.0","method":"tools/call","params":{"name":"get_all_projects","arguments":{}},"id":2}, timeout=30)
    return {"status": r2.status_code, "body": r2.text[:500]}


@app.post("/conversations/{id}/exit-resolution")
async def exit_resolution(id: str, _: str = Security(verify_api_key)):
    """Manually exit resolution mode for a conversation."""
    conv = get_conversation(db_conn, id)
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")

    update_conversation(db_conn, conv["session_id"], "normal", None)
    return {"mode": "normal"}
