"""``python -m expenses.seed --demo``: what it adds, and that a second run adds nothing.

The shared test database already holds whatever the demo users have, so the
seed runs against a scratch database created for the test and dropped
afterwards, with ``DATABASE_URL`` pointed at it for the duration.
"""

from __future__ import annotations

import secrets
from collections.abc import Iterator
from urllib.parse import urlsplit

import psycopg
import pytest

from expenses import db as app_db
from expenses import seed
from tests.support.builders import Db

DEMO_CLAIMS_BY_STATUS = {"submitted": 3, "approved": 2, "rejected": 1, "paid": 1}


@pytest.fixture
def scratch_database_url(db: Db) -> Iterator[str]:
    """The URL of an empty database that exists only for this test."""
    name = f"showcase_seed_{secrets.token_hex(4)}"
    db.execute(f'CREATE DATABASE "{name}"')
    try:
        yield urlsplit(app_db.database_url())._replace(path=f"/{name}").geturl()
    finally:
        db.execute(f'DROP DATABASE "{name}" WITH (FORCE)')


def claims_by_status(url: str) -> dict[str, int]:
    with psycopg.connect(url) as conn:
        rows = conn.execute("SELECT status, count(*) AS n FROM claims GROUP BY status").fetchall()
    return dict(rows)


@pytest.mark.catches("demo-seed-repeats")
def test_the_demo_seed_adds_a_claim_in_every_status_and_nothing_on_a_second_run(
    scratch_database_url, monkeypatch
):
    monkeypatch.setenv("DATABASE_URL", scratch_database_url)

    seed.main(["--demo"])
    after_first_run = claims_by_status(scratch_database_url)
    added_again = seed.add_demo_claims()

    assert after_first_run == DEMO_CLAIMS_BY_STATUS
    assert (added_again, claims_by_status(scratch_database_url)) == (0, DEMO_CLAIMS_BY_STATUS)
