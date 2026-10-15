"""Integrity queries over claims the app produced through its own API.

Each query returns the claims that break one rule, so an empty result is a
pass and a failure names the offending rows. The queries look only at one
test owner's claims: the database is shared with every other test, and some
of those tests deliberately insert rows the API would refuse.
"""

from __future__ import annotations

import pytest

from tests.support import User, expect_ok, submit_claim

catches = pytest.mark.catches

DECIDED_WITHOUT_DECIDER = """
    SELECT id, status FROM claims
    WHERE owner = %(owner)s AND status <> 'submitted'
      AND (decided_by IS NULL OR decided_at IS NULL)
"""

PAID_WITHOUT_APPROVAL = """
    SELECT c.id, c.status FROM claims c
    WHERE c.owner = %(owner)s AND c.status = 'paid'
      AND NOT EXISTS (
        SELECT 1 FROM claim_events e WHERE e.claim_id = c.id AND e.action = 'approved'
      )
"""

PAYMENT_COLUMNS_DISAGREE_WITH_STATUS = """
    SELECT id, status FROM claims
    WHERE owner = %(owner)s
      AND ((status = 'paid' AND (paid_by IS NULL OR paid_at IS NULL))
        OR (status <> 'paid' AND (paid_by IS NOT NULL OR paid_at IS NOT NULL)))
"""

REJECTED_WITHOUT_REASON = """
    SELECT id, status FROM claims
    WHERE owner = %(owner)s AND status = 'rejected'
      AND coalesce(btrim(decision_note), '') = ''
"""

DECIDED_BY_OWNER = """
    SELECT id, status FROM claims
    WHERE owner = %(owner)s AND decided_by = owner
"""

TIMES_OUT_OF_ORDER = """
    SELECT id, status FROM claims
    WHERE owner = %(owner)s AND (decided_at < submitted_at OR paid_at < decided_at)
"""

HISTORY_DISAGREES_WITH_STATUS = """
    SELECT c.id, c.status FROM claims c
    WHERE c.owner = %(owner)s
      AND ARRAY(SELECT e.action FROM claim_events e WHERE e.claim_id = c.id ORDER BY e.id)
          IS DISTINCT FROM CASE c.status
            WHEN 'submitted' THEN ARRAY['submitted']
            WHEN 'approved' THEN ARRAY['submitted', 'approved']
            WHEN 'rejected' THEN ARRAY['submitted', 'rejected']
            WHEN 'paid' THEN ARRAY['submitted', 'approved', 'paid']
          END
"""

EVENT_ACTOR_DISAGREES_WITH_ROW = """
    SELECT c.id, c.status FROM claim_events e JOIN claims c ON c.id = e.claim_id
    WHERE c.owner = %(owner)s
      AND e.actor IS DISTINCT FROM CASE e.action
        WHEN 'submitted' THEN c.owner
        WHEN 'paid' THEN c.paid_by
        ELSE c.decided_by
      END
"""


@pytest.fixture
def lifecycle_owner(make_user, api_as) -> User:
    """An employee with four claims taken through the API, one ending in each status."""
    owner = make_user("employee")
    as_owner = api_as(owner)
    as_manager = api_as(make_user("manager"))
    as_finance = api_as(make_user("finance"))

    submit_claim(as_owner, title="Left waiting")
    approved = submit_claim(as_owner, title="Approved, not yet paid")
    rejected = submit_claim(as_owner, title="Rejected")
    paid = submit_claim(as_owner, title="Approved and paid")
    expect_ok(as_manager.approve(approved["id"]))
    expect_ok(as_manager.reject(rejected["id"], note="Duplicate of an earlier claim."))
    expect_ok(as_manager.approve(paid["id"]))
    expect_ok(as_finance.pay(paid["id"]))
    return owner


def test_lifecycle_data_holds_one_claim_in_every_status(db, lifecycle_owner):
    """Guards the queries below: a rule checked against no rows passes for nothing."""
    rows = db.execute(
        "SELECT status, count(*) AS claims FROM claims WHERE owner = %s GROUP BY status",
        (lifecycle_owner.username,),
    ).fetchall()

    assert {row["status"]: row["claims"] for row in rows} == {
        "submitted": 1,
        "approved": 1,
        "rejected": 1,
        "paid": 1,
    }


@pytest.mark.parametrize(
    "violations_query",
    [
        pytest.param(DECIDED_WITHOUT_DECIDER, id="decided-without-decider"),
        pytest.param(PAID_WITHOUT_APPROVAL, id="paid-without-approval"),
        pytest.param(PAYMENT_COLUMNS_DISAGREE_WITH_STATUS, id="payment-columns-vs-status"),
        pytest.param(REJECTED_WITHOUT_REASON, id="rejected-without-reason"),
        pytest.param(DECIDED_BY_OWNER, id="decided-by-owner"),
        pytest.param(TIMES_OUT_OF_ORDER, id="times-out-of-order"),
        pytest.param(
            HISTORY_DISAGREES_WITH_STATUS,
            id="history-vs-status",
            marks=catches("missing-audit-event"),
        ),
        pytest.param(EVENT_ACTOR_DISAGREES_WITH_ROW, id="event-actor-vs-row"),
    ],
)
def test_no_claim_breaks_the_integrity_rule(db, lifecycle_owner, violations_query):
    violations = db.execute(violations_query, {"owner": lifecycle_owner.username}).fetchall()

    assert violations == []
