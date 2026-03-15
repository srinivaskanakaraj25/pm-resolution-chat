import os
import psycopg2
import psycopg2.extras
from datetime import datetime, timezone
from typing import Optional


def init_db() -> psycopg2.extensions.connection:
    """Open connection to Postgres database using DATABASE_URL env var."""
    conn = psycopg2.connect(os.environ["DATABASE_URL"])
    conn.autocommit = False
    with conn.cursor() as cur:
        cur.execute(
            "ALTER TABLE conversations ADD COLUMN IF NOT EXISTS project_id INTEGER"
        )
    conn.commit()
    return conn


def create_conversation(
    conn: psycopg2.extensions.connection,
    session_id: str,
    title: str,
    mode: str = "normal",
    failure_context: Optional[str] = None,
    project_id: Optional[int] = None,
) -> None:
    """Create a new conversation record. Uses INSERT OR IGNORE to be idempotent."""
    now = datetime.now(timezone.utc).isoformat()
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO conversations (session_id, title, mode, failure_context, project_id, created_at, updated_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (session_id) DO NOTHING
            """,
            (session_id, title, mode, failure_context, project_id, now, now),
        )
    conn.commit()


def update_conversation(
    conn: psycopg2.extensions.connection,
    session_id: str,
    mode: str,
    failure_context: Optional[str] = None,
) -> None:
    """Update mode and failure_context for an existing conversation."""
    now = datetime.now(timezone.utc).isoformat()
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE conversations
            SET mode = %s, failure_context = %s, updated_at = %s
            WHERE session_id = %s
            """,
            (mode, failure_context, now, session_id),
        )
    conn.commit()


def list_conversations(conn: psycopg2.extensions.connection) -> list[dict]:
    """List all conversations ordered by updated_at DESC."""
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(
            "SELECT session_id, title, mode, created_at, updated_at FROM conversations ORDER BY updated_at DESC"
        )
        return [dict(row) for row in cur.fetchall()]


def get_conversation(
    conn: psycopg2.extensions.connection, identifier: str
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
            return rows[index - 1]
        return None
    except ValueError:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                "SELECT session_id, title, mode, failure_context, project_id, created_at, updated_at FROM conversations WHERE session_id = %s",
                (identifier,),
            )
            row = cur.fetchone()
            return dict(row) if row else None
