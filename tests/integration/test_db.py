"""Integration tests for db.py against a real Postgres database.

Requires DATABASE_URL or TEST_DATABASE_URL to be set; tests are skipped otherwise.
Each test runs inside its own isolated Postgres schema that is dropped at teardown,
so production data in the default schema is never touched.
"""
import os
import time
import pytest
import psycopg2
import psycopg2.extras

from db import (
    create_conversation,
    update_conversation,
    list_conversations,
    get_conversation,
)


@pytest.fixture
def db_conn():
    url = os.environ.get("TEST_DATABASE_URL") or os.environ.get("DATABASE_URL")
    if not url:
        pytest.skip("No DATABASE_URL set — skipping DB integration tests")

    conn = psycopg2.connect(url)
    conn.autocommit = False

    # Create an isolated schema per test so the real conversations table is never touched.
    schema = f"test_{int(time.time() * 1000)}"
    with conn.cursor() as cur:
        cur.execute(f'CREATE SCHEMA "{schema}"')
        cur.execute(f'SET search_path = "{schema}"')
        cur.execute("""
            CREATE TABLE conversations (
                session_id VARCHAR PRIMARY KEY,
                title      VARCHAR,
                mode       VARCHAR DEFAULT 'normal',
                failure_context TEXT,
                created_at VARCHAR,
                updated_at VARCHAR
            )
        """)
    conn.commit()

    yield conn

    # Teardown: drop the entire schema — prod data is untouched.
    conn.rollback()
    conn.autocommit = True
    with conn.cursor() as cur:
        cur.execute(f'DROP SCHEMA "{schema}" CASCADE')
    conn.close()


# ---------------------------------------------------------------------------
# create_conversation
# ---------------------------------------------------------------------------

def test_create_conversation_inserts_row(db_conn):
    create_conversation(db_conn, "sess-001", "Hello world")
    row = get_conversation(db_conn, "sess-001")
    assert row is not None
    assert row["session_id"] == "sess-001"
    assert row["title"] == "Hello world"
    assert row["mode"] == "normal"


def test_create_conversation_is_idempotent(db_conn):
    create_conversation(db_conn, "sess-002", "First title")
    create_conversation(db_conn, "sess-002", "Second title")  # must not raise or duplicate

    rows = list_conversations(db_conn)
    matches = [r for r in rows if r["session_id"] == "sess-002"]
    assert len(matches) == 1


# ---------------------------------------------------------------------------
# update_conversation
# ---------------------------------------------------------------------------

def test_update_conversation_changes_mode_and_context(db_conn):
    create_conversation(db_conn, "sess-003", "Update test")
    update_conversation(db_conn, "sess-003", "resolution", '{"error": "oops"}')

    row = get_conversation(db_conn, "sess-003")
    assert row["mode"] == "resolution"
    assert row["failure_context"] == '{"error": "oops"}'


def test_update_conversation_advances_updated_at(db_conn):
    create_conversation(db_conn, "sess-004", "Timestamp test")
    row = get_conversation(db_conn, "sess-004")
    original_updated_at = row["updated_at"]

    time.sleep(0.002)  # ensure the clock advances
    update_conversation(db_conn, "sess-004", "resolution", None)

    row = get_conversation(db_conn, "sess-004")
    assert row["updated_at"] > original_updated_at


# ---------------------------------------------------------------------------
# list_conversations
# ---------------------------------------------------------------------------

def test_list_conversations_newest_first(db_conn):
    create_conversation(db_conn, "sess-old", "Older")
    time.sleep(0.002)
    create_conversation(db_conn, "sess-new", "Newer")

    rows = list_conversations(db_conn)
    our_rows = [r for r in rows if r["session_id"] in ("sess-old", "sess-new")]
    assert len(our_rows) == 2
    assert our_rows[0]["session_id"] == "sess-new"
    assert our_rows[1]["session_id"] == "sess-old"


def test_list_conversations_empty_table(db_conn):
    rows = list_conversations(db_conn)
    assert rows == []


# ---------------------------------------------------------------------------
# get_conversation
# ---------------------------------------------------------------------------

def test_get_conversation_by_uuid(db_conn):
    create_conversation(db_conn, "sess-uuid-abc", "UUID lookup")
    row = get_conversation(db_conn, "sess-uuid-abc")
    assert row is not None
    assert row["session_id"] == "sess-uuid-abc"
    assert row["title"] == "UUID lookup"


def test_get_conversation_by_valid_index(db_conn):
    create_conversation(db_conn, "sess-idx-a", "First created")
    time.sleep(0.002)
    create_conversation(db_conn, "sess-idx-b", "Second created (newest)")

    # list_conversations returns DESC by updated_at, so index 1 = newest
    row1 = get_conversation(db_conn, "1")
    assert row1 is not None
    assert row1["session_id"] == "sess-idx-b"

    row2 = get_conversation(db_conn, "2")
    assert row2 is not None
    assert row2["session_id"] == "sess-idx-a"


def test_get_conversation_by_out_of_range_index(db_conn):
    create_conversation(db_conn, "sess-single", "Only one row")
    row = get_conversation(db_conn, "99")
    assert row is None


def test_get_conversation_unknown_uuid(db_conn):
    row = get_conversation(db_conn, "does-not-exist-xyz-999")
    assert row is None
