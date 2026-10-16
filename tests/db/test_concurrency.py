"""Two requests for one claim at the same moment: only the first may act.

Approve, reject and pay read the claim with ``SELECT ... FOR UPDATE``, so a
second request waits for the first to commit and then sees the new status.
Without the lock both requests read "approved" and both pay.

The test holds the claim's row lock on a connection of its own, sends the
requests one at a time, waits until Postgres reports each one blocked behind
that lock, then lets go. Postgres wakes waiters in queue order, so the first
request goes first. Code without the lock still blocks, on the UPDATE rather
than the read, and then both writes go through; the status codes show it.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable

import httpx
import psycopg

from expenses import db as app_db
from tests.support import claim_events, claim_row
from tests.support.builders import Db

WAIT_S = 10.0
Request = Callable[[], httpx.Response]


def blocked_behind(db: Db, holder_pid: int) -> set[int]:
    """Backends waiting on ``holder_pid``'s locks, directly or behind another waiter."""
    waiting = db.execute(
        "SELECT pid, pg_blocking_pids(pid) AS blockers FROM pg_stat_activity"
        " WHERE datname = current_database() AND wait_event_type = 'Lock'"
    ).fetchall()
    blocked: set[int] = set()
    grew = True
    while grew:
        grew = False
        for row in waiting:
            if row["pid"] not in blocked and ({holder_pid} | blocked) & set(row["blockers"]):
                blocked.add(row["pid"])
                grew = True
    return blocked


def wait_until_blocked(db: Db, holder_pid: int, threads: list[threading.Thread]) -> None:
    """Return once as many backends wait behind the holder as there are requests in flight."""
    deadline = time.monotonic() + WAIT_S
    while len(blocked_behind(db, holder_pid)) < len(threads):
        finished = [thread.name for thread in threads if not thread.is_alive()]
        assert not finished, f"{finished} answered while the claim was locked: no row lock taken"
        assert time.monotonic() < deadline, f"requests not blocked on the row after {WAIT_S}s"
        threads[-1].join(timeout=0.01)  # a short wait before polling again


def race(db: Db, claim_id: int, *requests: Request) -> list[int]:
    """Queue ``requests`` behind a lock on the claim, in order, release it, return their codes."""
    responses: dict[int, httpx.Response] = {}
    threads: list[threading.Thread] = []

    def send(index: int, request: Request) -> None:
        responses[index] = request()

    holder = psycopg.connect(app_db.database_url())
    try:
        holder.execute("SELECT id FROM claims WHERE id = %s FOR UPDATE", (claim_id,))
        for index, request in enumerate(requests):
            thread = threading.Thread(
                target=send, args=(index, request), name=f"request {index + 1}", daemon=True
            )
            threads.append(thread)
            thread.start()
            wait_until_blocked(db, holder.info.backend_pid, threads)
    finally:
        holder.rollback()  # releases the row lock
        holder.close()
        for thread in threads:
            thread.join(timeout=WAIT_S)
    assert len(responses) == len(requests), "a request raised instead of answering"
    return [responses[index].status_code for index in range(len(requests))]


def test_two_payments_at_once_pay_the_claim_once(db, claim_in, make_user, api_as):
    claim = claim_in("approved")
    first, second = api_as(make_user("finance")), api_as(make_user("finance"))

    codes = race(db, claim["id"], lambda: first.pay(claim["id"]), lambda: second.pay(claim["id"]))

    assert codes == [200, 409]
    assert claim_row(db, claim["id"])["paid_by"] == first.username
    assert [event["action"] for event in claim_events(db, claim["id"])] == [
        "submitted",
        "approved",
        "paid",
    ]


def test_an_approval_and_a_rejection_at_once_decide_the_claim_once(db, claim_in, make_user, api_as):
    claim = claim_in("submitted")
    approver, rejecter = api_as(make_user("manager")), api_as(make_user("manager"))

    codes = race(
        db,
        claim["id"],
        lambda: approver.approve(claim["id"]),
        lambda: rejecter.reject(claim["id"], note="Duplicate of another claim."),
    )

    assert codes == [200, 409]
    stored = claim_row(db, claim["id"])
    assert (stored["status"], stored["decided_by"]) == ("approved", approver.username)
    assert [event["action"] for event in claim_events(db, claim["id"])] == [
        "submitted",
        "approved",
    ]
