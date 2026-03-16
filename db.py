import os
import psycopg2
import psycopg2.extras
import psycopg2.pool
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Optional


def init_db() -> psycopg2.pool.ThreadedConnectionPool:
    """Create a connection pool and run schema migrations."""
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise RuntimeError("DATABASE_URL is required")

    pool = psycopg2.pool.ThreadedConnectionPool(
        minconn=1,
        maxconn=int(os.environ.get("DB_POOL_MAX", "10")),
        dsn=database_url,
    )
    conn = pool.getconn()
    try:
        conn.autocommit = False
        with conn.cursor() as cur:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS conversations (
                    session_id VARCHAR PRIMARY KEY,
                    title VARCHAR NOT NULL,
                    mode VARCHAR NOT NULL DEFAULT 'normal',
                    failure_context TEXT,
                    project_id INTEGER,
                    created_at VARCHAR NOT NULL,
                    updated_at VARCHAR NOT NULL
                )
                """
            )
            cur.execute(
                "ALTER TABLE conversations ADD COLUMN IF NOT EXISTS project_id INTEGER"
            )
        conn.commit()
    finally:
        pool.putconn(conn)
    return pool


@contextmanager
def get_conn(pool: psycopg2.pool.ThreadedConnectionPool):
    """Checkout a connection from the pool, yield it, then return it."""
    conn = pool.getconn()
    try:
        yield conn
    except Exception:
        conn.rollback()
        raise
    finally:
        pool.putconn(conn)


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
