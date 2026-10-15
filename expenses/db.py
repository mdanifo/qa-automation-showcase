"""Database access: the connection helper, schema setup and the demo users."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import psycopg
from psycopg.rows import dict_row

DEFAULT_DATABASE_URL = "postgresql://showcase:showcase@127.0.0.1:5433/showcase"
SCHEMA_PATH = Path(__file__).with_name("schema.sql")

# Serializes schema setup when several app processes start at once (one per test worker).
_SCHEMA_LOCK_ID = 74_210_001

DEMO_USERS: tuple[tuple[str, str, str], ...] = (
    ("erin", "Erin Park", "employee"),
    ("eli", "Eli Ward", "employee"),
    ("maya", "Maya Chen", "manager"),
    ("omar", "Omar Haddad", "manager"),
    ("fran", "Fran Lopez", "finance"),
)

Connection = psycopg.Connection[dict[str, Any]]


def database_url() -> str:
    """The Postgres URL from ``DATABASE_URL``, or the local docker compose default."""
    return os.environ.get("DATABASE_URL") or DEFAULT_DATABASE_URL


def connect(**kwargs: Any) -> Connection:
    """Open a connection whose rows come back as dicts.

    Use it as a context manager: the transaction commits on a clean exit and
    rolls back on an exception.
    """
    return psycopg.connect(database_url(), row_factory=dict_row, **kwargs)


def init_db(conn: Connection | None = None) -> None:
    """Apply schema.sql and add any missing demo users. Safe to run repeatedly and concurrently."""
    if conn is None:
        with connect() as own:
            init_db(own)
        return
    with conn.transaction():
        conn.execute("SELECT pg_advisory_xact_lock(%s)", (_SCHEMA_LOCK_ID,))
        conn.execute(SCHEMA_PATH.read_text())
        with conn.cursor() as cur:
            cur.executemany(
                "INSERT INTO users (username, display_name, role) VALUES (%s, %s, %s)"
                " ON CONFLICT (username) DO NOTHING",
                DEMO_USERS,
            )
