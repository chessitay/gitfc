import sqlite3
import types
import uuid
from datetime import datetime
from unittest.mock import patch

import pytest


QUEUE_SCHEMA = """
    CREATE TABLE IF NOT EXISTS queue (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        message     TEXT NOT NULL,
        commit_date TEXT NOT NULL,
        push_at     TEXT,
        jitter_sec  INTEGER DEFAULT 0,
        branch      TEXT NOT NULL,
        commit_hash TEXT,
        status      TEXT DEFAULT 'committed',
        error       TEXT,
        created_at  TEXT NOT NULL,
        pushed_at   TEXT,
        stage_all   INTEGER DEFAULT 0,
        amend       INTEGER DEFAULT 0
    )
"""


@pytest.fixture
def mock_db():
    """Shared-cache in-memory SQLite DB with queue schema.

    Uses a shared-cache URI so multiple connections access the same in-memory
    database. The DB persists as long as at least one connection is open, so
    the real code can call conn.close() without destroying test data.
    """
    db_name = f"test_db_{uuid.uuid4().hex}"
    uri = f"file:{db_name}?mode=memory&cache=shared"

    def _make_conn():
        c = sqlite3.connect(uri, uri=True)
        c.row_factory = sqlite3.Row
        c.execute(QUEUE_SCHEMA)
        c.commit()
        return c

    # Anchor connection — keeps the shared-cache DB alive for the entire test
    test_conn = _make_conn()

    with patch("gitfc.queue.get_db", side_effect=_make_conn):
        yield test_conn

    test_conn.close()


def make_args(**overrides):
    """Build a namespace mimicking argparse output with sensible defaults."""
    defaults = dict(
        message="test commit",
        date=None,
        amend=False,
        force=False,
        reset=False,
        id=1,
        ids=None,
        interval="30m",
        jitter=None,
        at=None,
        daemon=False,
        poll=60,
        queue_action="list",
    )
    defaults.update(overrides)
    return types.SimpleNamespace(**defaults)


def insert_row(conn, **overrides):
    """Insert a queue row with defaults, return the row id."""
    defaults = dict(
        message="test commit",
        commit_date="2026-01-15 10:00:00",
        push_at=None,
        jitter_sec=0,
        branch="main",
        commit_hash="a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2",
        status="committed",
        error=None,
        created_at="2026-01-15 09:00:00",
        pushed_at=None,
        stage_all=0,
        amend=0,
    )
    defaults.update(overrides)
    d = defaults
    cur = conn.execute(
        """INSERT INTO queue
           (message, commit_date, push_at, jitter_sec, branch, commit_hash,
            status, error, created_at, pushed_at, stage_all, amend)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            d["message"], d["commit_date"], d["push_at"], d["jitter_sec"],
            d["branch"], d["commit_hash"], d["status"], d["error"],
            d["created_at"], d["pushed_at"], d["stage_all"], d["amend"],
        ),
    )
    conn.commit()
    return cur.lastrowid


class FakeDatetime(datetime):
    """datetime subclass with a fixed now() — strptime/strftime still work."""

    _fixed_now = datetime(2026, 1, 15, 12, 0, 0)

    @classmethod
    def now(cls, tz=None):
        return cls._fixed_now
