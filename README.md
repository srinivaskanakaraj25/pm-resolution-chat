# PM Resolution Chat

FastAPI service backed by Anthropic's Python Claude Agent SDK. The app persists
conversation state in Postgres and switches into a guided resolution mode when a
tool call fails with a 422-style validation error.

## Local setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Required environment variables:

- `ANTHROPIC_API_KEY`
- `DATABASE_URL`
- `API_KEY`

Optional but recommended:

- `CLAUDE_CONFIG_DIR`
  Use `/data` in Railway when a persistent volume is mounted.
  Local development falls back to `./.claude-runtime` when this is unset.
- `AGENT_ALLOWED_TOOLS`
  Comma-separated allowlist for external MCP tools. Leave empty to run the
  agent with no external tool access.

## Claude agent configuration

The runtime is intentionally locked down:

- Built-in Claude Code filesystem, shell, web, and task tools are disabled.
- The agent prompt is appended to the official Claude Code preset instead of
  replacing it.
- Project settings are loaded from [`.claude/settings.json`](/Users/srinivaskanakaraj/Desktop/Code/PM%20Chat/PM-Resolution%20chat/.claude/settings.json).
- External Rocketlane or MCP tools must be explicitly allowlisted with
  `AGENT_ALLOWED_TOOLS`.

This prevents the deployed agent from claiming access to host tools that should
not be exposed in a Rocketlane-facing environment.

## Running the API

```bash
.venv/bin/uvicorn api:app --reload --host 0.0.0.0 --port 8000
```

Health check:

```bash
curl http://localhost:8000/health
```

## CLI usage

```bash
.venv/bin/python cli.py           # show available commands
.venv/bin/python cli.py start     # start a new conversation
.venv/bin/python cli.py ls        # list previous conversations
.venv/bin/python cli.py resume 1  # resume by index or UUID
```

Type `/quit` to exit and `/normal` to leave resolution mode.

## Railway deployment

This repo is configured for Railway's GitHub integration with Nixpacks.

Set these Railway variables:

- `ANTHROPIC_API_KEY`
- `DATABASE_URL`
- `API_KEY`
- `CLAUDE_CONFIG_DIR=/data`
- `AGENT_ALLOWED_TOOLS=...` only if you have Rocketlane/MCP tools configured

Operational notes:

- Mount a persistent Railway volume at `/data` so Claude session transcripts
  survive restarts and conversation history can be restored.
- The service exposes `GET /health` for health checks.
- `nixpacks.toml` installs Python dependencies and the Claude Code CLI, then
  starts `uvicorn api:app`.
