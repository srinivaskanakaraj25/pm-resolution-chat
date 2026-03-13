# Agent Project

Claude Agent SDK example with runtime resolution mode triggered by 422 tool failures.

## Setup

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

Create the database once:
```bash
sqlite3 conversations.db "CREATE TABLE conversations (session_id TEXT PRIMARY KEY, title TEXT NOT NULL, mode TEXT NOT NULL DEFAULT 'normal', failure_context TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL);"
```

## Usage

```bash
python cli.py           # show available commands
python cli.py start     # start a new conversation
python cli.py ls        # list previous conversations
python cli.py resume 1  # resume by index or UUID
```

Type `/quit` to exit, `/normal` to leave resolution mode.
