"""What each operation writes to the claims table, read back with SQL."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

import pytest

from tests.support import claim_row, days_ago, submit_claim

catches = pytest.mark.catches

STATE_COLUMNS = ("status", "decided_by", "decided_at", "decision_note", "paid_by", "paid_at")


def changed_columns(before: dict[str, Any], after: dict[str, Any]) -> set[str]:
    """The names of the columns whose value differs between two reads of one row."""
    return {column for column in after if after[column] != before[column]}


def parse_timestamp(text: str | None) -> datetime | None:
    return None if text is None else datetime.fromisoformat(text)


def reply_state(reply: dict[str, Any]) -> dict[str, Any]:
    """A claim reply's status, decision and payment fields, under the database's column names."""
    return {
        "status": reply["status"],
        "decided_by": reply["decidedBy"],
        "decided_at": parse_timestamp(reply["decidedAt"]),
        "decision_note": reply["decisionNote"],
        "paid_by": reply["paidBy"],
        "paid_at": parse_timestamp(reply["paidAt"]),
    }


def test_submitted_claim_is_stored_trimmed_in_cents_and_undecided(db, db_now, employee, api_as):
    expense_date = days_ago(3)
    started = db_now()

    claim = submit_claim(
        api_as(employee),
        title="  Client dinner  ",
        category="meals",
        amount="42.50",
        expenseDate=expense_date,
    )

    finished = db_now()
    stored = claim_row(db, claim["id"])
    assert stored is not None
    submitted_at = stored.pop("submitted_at")
    assert stored == {
        "id": claim["id"],
        "owner": employee.username,
        "title": "Client dinner",
        "category": "meals",
        "amount_cents": 4250,
        "miles": None,
        "expense_date": expense_date,
        "status": "submitted",
        "decided_by": None,
        "decided_at": None,
        "decision_note": None,
        "paid_by": None,
        "paid_at": None,
    }
    assert started <= submitted_at <= finished


def test_a_title_of_80_characters_is_stored_whole(db, employee, api_as):
    title = "x" * 79 + "y"

    claim = submit_claim(api_as(employee), title=title)

    assert claim_row(db, claim["id"])["title"] == title


@pytest.mark.parametrize(
    ("category", "amount", "cents"),
    [
        pytest.param("meals", "0.01", 1, id="one-cent"),
        pytest.param("meals", "0.29", 29, id="float-gives-28"),
        pytest.param("meals", "19.99", 1999, id="float-gives-1998"),
        pytest.param("software", "4.10", 410, id="float-gives-409"),
        pytest.param("meals", "42.5", 4250, id="one-decimal"),
        pytest.param("lodging", "120", 12000, id="whole-dollars"),
        pytest.param("travel", "1234.56", 123456, id="four-digit-dollars"),
    ],
)
def test_amount_is_stored_as_exact_integer_cents(db, employee, api_as, category, amount, cents):
    """An id like float-gives-1998 names what ``int(float(amount) * 100)`` would store."""
    claim = submit_claim(api_as(employee), category=category, amount=amount)

    assert claim_row(db, claim["id"])["amount_cents"] == cents


@pytest.mark.parametrize(
    ("miles", "cents"),
    [
        pytest.param("0.1", 7, id="0.067-rounds-up"),
        pytest.param("1.0", 67, id="one-mile"),
        pytest.param("13.5", 905, id="9.045-half-up", marks=catches("mileage-float-rounding")),
        pytest.param("746.2", 49995, id="just-under-the-500-limit"),
    ],
)
def test_mileage_is_stored_as_miles_and_half_up_cents(db, employee, api_as, miles, cents):
    claim = submit_claim(api_as(employee), category="mileage", miles=miles)

    stored = claim_row(db, claim["id"])
    assert (stored["miles"], stored["amount_cents"]) == (Decimal(miles), cents)


@catches("approval-not-saved")
def test_approve_stores_the_decision_and_changes_nothing_else(
    db, db_now, claim_in, manager, api_as
):
    claim = claim_in("submitted")
    before = claim_row(db, claim["id"])
    started = db_now()

    resp = api_as(manager).approve(claim["id"])

    finished = db_now()
    assert resp.status_code == 200, resp.text
    after = claim_row(db, claim["id"])
    assert after["status"] == "approved"
    assert changed_columns(before, after) == {"status", "decided_by", "decided_at"}
    assert after["decided_by"] == manager.username
    assert started <= after["decided_at"] <= finished


def test_reject_stores_the_decision_with_the_trimmed_reason(db, db_now, claim_in, manager, api_as):
    claim = claim_in("submitted")
    before = claim_row(db, claim["id"])
    started = db_now()

    resp = api_as(manager).reject(claim["id"], note="  Duplicate of claim 4410.  ")

    finished = db_now()
    assert resp.status_code == 200, resp.text
    after = claim_row(db, claim["id"])
    assert after["status"] == "rejected"
    assert changed_columns(before, after) == {
        "status",
        "decided_by",
        "decided_at",
        "decision_note",
    }
    assert after["decided_by"] == manager.username
    assert after["decision_note"] == "Duplicate of claim 4410."
    assert started <= after["decided_at"] <= finished


def test_a_reason_of_500_characters_is_stored_whole(db, claim_in, manager, api_as):
    claim = claim_in("submitted")
    reason = "x" * 499 + "y"

    resp = api_as(manager).reject(claim["id"], note=reason)

    assert resp.status_code == 200, resp.text
    assert claim_row(db, claim["id"])["decision_note"] == reason


def test_pay_stores_the_payment_and_keeps_the_approval(db, db_now, claim_in, finance, api_as):
    claim = claim_in("approved")
    before = claim_row(db, claim["id"])
    started = db_now()

    resp = api_as(finance).pay(claim["id"])

    finished = db_now()
    assert resp.status_code == 200, resp.text
    after = claim_row(db, claim["id"])
    assert after["status"] == "paid"
    assert changed_columns(before, after) == {"status", "paid_by", "paid_at"}
    assert after["paid_by"] == finance.username
    assert started <= after["paid_at"] <= finished


@pytest.mark.parametrize(
    ("start", "role", "action", "body"),
    [
        pytest.param("submitted", "manager", "approve", None, id="approve",
                     marks=catches("approval-not-saved")),
        pytest.param("submitted", "manager", "reject", {"note": "No receipt."}, id="reject"),
        pytest.param("approved", "finance", "pay", None, id="pay"),
    ],
)  # fmt: skip
def test_transition_reply_matches_the_committed_row(
    db, claim_in, make_user, api_as, start, role, action, body
):
    """The API must never report a state the database does not hold."""
    claim = claim_in(start)

    resp = api_as(make_user(role)).post(f"/api/claims/{claim['id']}/{action}", json=body)

    assert resp.status_code == 200, resp.text
    stored = claim_row(db, claim["id"])
    assert {column: stored[column] for column in STATE_COLUMNS} == reply_state(resp.json())
