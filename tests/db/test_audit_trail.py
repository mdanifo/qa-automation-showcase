"""The claim_events audit trail: one row per state change, naming who made it."""

from __future__ import annotations

from datetime import datetime

import pytest

from tests.support import claim_events, claim_row, expect_ok, submit_claim
from tests.support.builders import Db

NOTE = {"note": "No receipt."}
catches = pytest.mark.catches


def trail(db: Db, claim_id: int) -> list[tuple[str, str, datetime]]:
    """The claim's events, oldest first, as (action, actor, at)."""
    return [(e["action"], e["actor"], e["at"]) for e in claim_events(db, claim_id)]


def test_submitting_writes_one_submitted_event_by_the_owner(db, employee, api_as):
    claim = submit_claim(api_as(employee))

    submitted_at = claim_row(db, claim["id"])["submitted_at"]
    assert trail(db, claim["id"]) == [("submitted", employee.username, submitted_at)]


@pytest.mark.parametrize(
    ("start", "role", "action", "body", "event", "stamped"),
    [
        pytest.param("submitted", "manager", "approve", None, "approved", "decided_at",
                     id="approve", marks=catches("approval-not-saved")),
        pytest.param("submitted", "manager", "reject", NOTE, "rejected", "decided_at", id="reject"),
        pytest.param("approved", "finance", "pay", None, "paid", "paid_at", id="pay",
                     marks=catches("missing-audit-event")),
    ],
)  # fmt: skip
def test_transition_appends_exactly_one_event_by_the_actor(
    db, claim_in, make_user, api_as, start, role, action, body, event, stamped
):
    """The new event's time equals the row's decided_at or paid_at.

    Both come from now() in one transaction, so equal times show the event and
    the change were committed together.
    """
    claim = claim_in(start)
    history = trail(db, claim["id"])
    actor = make_user(role)

    resp = api_as(actor).post(f"/api/claims/{claim['id']}/{action}", json=body)

    assert resp.status_code == 200, resp.text
    changed_at = claim_row(db, claim["id"])[stamped]
    assert trail(db, claim["id"]) == [*history, (event, actor.username, changed_at)]


@catches("missing-audit-event")
def test_claim_paid_through_the_api_has_a_three_step_history(
    db, employee, manager, finance, api_as
):
    claim = submit_claim(api_as(employee))
    expect_ok(api_as(manager).approve(claim["id"]))
    expect_ok(api_as(finance).pay(claim["id"]))

    events = trail(db, claim["id"])

    assert [(action, actor) for action, actor, _ in events] == [
        ("submitted", employee.username),
        ("approved", manager.username),
        ("paid", finance.username),
    ]
    times = [at for _, _, at in events]
    assert times == sorted(times)
