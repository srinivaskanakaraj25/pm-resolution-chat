# PM Resolution Chat

Claude Agent SDK example with runtime resolution mode triggered by 422 tool failures.

## Setup

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

Copy `.env.example` to `.env` and fill in your values:
```bash
cp .env.example .env
```

## Usage

```bash
python cli.py           # show available commands
python cli.py start     # start a new conversation
python cli.py ls        # list previous conversations
python cli.py resume 1  # resume by index or UUID
```

Type `/quit` to exit, `/normal` to leave resolution mode.
