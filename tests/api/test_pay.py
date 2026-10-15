"""POST /api/claims/{id}/pay: finance only, approved claims only."""

from __future__ import annotations

import pytest

from tests.api.expect import error_of, status_of
from tests.support import insert_claim

NOT_APPROVED = [
    pytest.param("submitted", marks=pytest.mark.catches("pay-unapproved")),
    pytest.param("rejected", marks=pytest.mark.catches("pay-unapproved")),
    pytest.param("paid"),
]


def test_finance_pays_an_approved_claim(db, api_as, employee, manager, finance):
    claim = insert_claim(db, employee, "approved", decided_by=manager)

    resp = api_as(finance).pay(claim["id"])

    paid = resp.json()
    assert status_of(resp) == (200, "paid")
    assert (paid["paidBy"], paid["decidedBy"]) == (finance.username, manager.username)
    assert paid["paidAt"] is not None


@pytest.mark.parametrize("status", NOT_APPROVED)
def test_only_an_approved_claim_may_be_paid(status, db, api_as, employee, finance):
    claim = insert_claim(db, employee, status)
    api = api_as(finance)

    resp = api.pay(claim["id"])

    assert error_of(resp) == (409, "invalid_transition")
    assert api.get_claim(claim["id"]).json()["status"] == status


@pytest.mark.parametrize("role", ["employee", "manager"])
def test_only_finance_may_pay(role, db, api_as, employee, make_user):
    claim = insert_claim(db, employee, "approved")

    resp = api_as(make_user(role)).pay(claim["id"])

    assert error_of(resp) == (403, "forbidden")


def test_a_claim_is_paid_only_once(db, api_as, employee, finance):
    claim = insert_claim(db, employee, "approved")
    api = api_as(finance)

    first, second = api.pay(claim["id"]), api.pay(claim["id"])

    assert (status_of(first), error_of(second)) == ((200, "paid"), (409, "invalid_transition"))
