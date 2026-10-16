"""Fixtures for the database layer.

These tests act through the API and then read what Postgres holds. Claims in
a starting state come from ``claim_in`` in tests/conftest.py.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime

import pytest

from tests.support.builders import Db


@pytest.fixture
def db_now(db: Db) -> Callable[[], datetime]:
    """``db_now()`` returns the database clock.

    The app stamps decided_at, paid_at and events with the database's now(),
    so a test brackets a request with two readings of the same clock. The
    test connection is in autocommit, so each reading is a fresh time.
    """

    def now() -> datetime:
        row = db.execute("SELECT now() AS now").fetchone()
        assert row is not None
        return row["now"]

    return now
