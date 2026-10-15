"""GET /api/summary: totals of the caller's own claims. Rejected claims count nowhere."""

from __future__ import annotations

import pytest

from tests.support import insert_claim

ZERO = {"pending": "0.00", "approved": "0.00", "paid": "0.00"}


def test_a_user_with_no_claims_has_zero_totals(api_as, employee):
    resp = api_as(employee).summary()

    assert (resp.status_code, resp.json()) == (200, ZERO)


@pytest.mark.parametrize(
    ("status", "totals"),
    [
        pytest.param("submitted", {**ZERO, "pending": "42.50"}, id="submitted-is-pending"),
        pytest.param("approved", {**ZERO, "approved": "42.50"}, id="approved"),
        pytest.param("paid", {**ZERO, "paid": "42.50"}, id="paid"),
    ],
)
def test_each_status_counts_toward_its_own_total(status, totals, db, api_as, employee):
    insert_claim(db, employee, status, amount="42.50")

    assert api_as(employee).summary().json() == totals


@pytest.mark.catches("pending-total-includes-rejected")
def test_a_rejected_claim_counts_toward_no_total(db, api_as, employee):
    insert_claim(db, employee, "rejected", amount="42.50")

    assert api_as(employee).summary().json() == ZERO


@pytest.mark.catches("pending-total-includes-rejected")
def test_totals_add_up_each_status_and_leave_rejected_out(db, api_as, employee):
    insert_claim(db, employee, "submitted", amount="20.00")
    insert_claim(db, employee, "submitted", amount="5.25")
    insert_claim(db, employee, "approved", amount="42.50")
    insert_claim(db, employee, "rejected", amount="60.00")
    insert_claim(db, employee, "paid", amount="100.00")

    assert api_as(employee).summary().json() == {
        "pending": "25.25",
        "approved": "42.50",
        "paid": "100.00",
    }


def test_totals_count_only_the_callers_own_claims(db, api_as, employee, manager):
    """A manager can see others' submitted claims, but they are not the manager's money."""
    insert_claim(db, employee, "submitted", amount="30.00")
    insert_claim(db, manager, "submitted", amount="12.00")

    assert api_as(manager).summary().json() == {**ZERO, "pending": "12.00"}


def test_a_total_over_a_thousand_has_no_thousands_separator(db, api_as, employee):
    insert_claim(db, employee, "approved", category="travel", amount="1500.00")
    insert_claim(db, employee, "approved", category="travel", amount="1499.99")

    assert api_as(employee).summary().json() == {**ZERO, "approved": "2999.99"}
