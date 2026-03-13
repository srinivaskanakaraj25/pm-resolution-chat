import sqlite3
from datetime import datetime, timezone
from typing import Optional


def init_db(path: str = "conversations.db") -> sqlite3.Connection:
    """Open connection to conversations database. Table must be created separately."""
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def create_conversation(
    conn: sqlite3.Connection,
    session_id: str,
    title: str,
    mode: str = "normal",
    failure_context: Optional[str] = None,
) -> None:
    """Create a new conversation record. Uses INSERT OR IGNORE to be idempotent."""
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        """
        INSERT OR IGNORE INTO conversations
        (session_id, title, mode, failure_context, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (session_id, title, mode, failure_context, now, now),
    )
    conn.commit()


def update_conversation(
    conn: sqlite3.Connection,
    session_id: str,
    mode: str,
    failure_context: Optional[str] = None,
) -> None:
    """Update mode and failure_context for an existing conversation."""
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        """
        UPDATE conversations
        SET mode = ?, failure_context = ?, updated_at = ?
        WHERE session_id = ?
        """,
        (mode, failure_context, now, session_id),
    )
    conn.commit()


def list_conversations(conn: sqlite3.Connection) -> list[dict]:
    """List all conversations ordered by updated_at DESC."""
    rows = conn.execute(
        "SELECT session_id, title, mode, created_at, updated_at FROM conversations ORDER BY updated_at DESC"
    ).fetchall()
    return [dict(row) for row in rows]


def get_conversation(
    conn: sqlite3.Connection, identifier: str
) -> Optional[dict]:
    """
    Get conversation by 1-based index or UUID.
    If identifier is numeric, treat as 1-based index into ordered list.
    Otherwise, treat as session_id.
    """
    try:
        index = int(identifier)
        rows = list_conversations(conn)
        if 1 <= index <= len(rows):
            return dict(rows[index - 1])
        return None
    except ValueError:
        # Not an integer, treat as session_id
        row = conn.execute(
            "SELECT session_id, title, mode, failure_context, created_at, updated_at FROM conversations WHERE session_id = ?",
            (identifier,),
        ).fetchone()
        return dict(row) if row else None
