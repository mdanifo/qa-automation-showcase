"""POST /api/claims/{id}/approve: a manager, someone else's claim, still submitted.

Claims are written straight to the database in the state each test needs
(``insert_claim``), so these tests do not depend on submit working.
"""

from __future__ import annotations

import pytest

from tests.api.expect import error_of, status_of
from tests.support import insert_claim


def test_a_manager_approves_someone_elses_submitted_claim(db, api_as, employee, manager):
    claim = insert_claim(db, employee, "submitted")

    resp = api_as(manager).approve(claim["id"])

    approved = resp.json()
    assert status_of(resp) == (200, "approved")
    assert approved["decidedBy"] == manager.username
    assert approved["decidedAt"] is not None
    assert (approved["decisionNote"], approved["paidBy"], approved["paidAt"]) == (None, None, None)


def test_a_manager_may_approve_another_managers_claim(db, api_as, make_user):
    """The rule is "not your own claim", not "not a manager's claim"."""
    owner, approver = make_user("manager"), make_user("manager")
    claim = insert_claim(db, owner, "submitted")

    resp = api_as(approver).approve(claim["id"])

    assert status_of(resp) == (200, "approved")


@pytest.mark.catches("self-approval")
def test_a_manager_cannot_approve_their_own_claim(db, api_as, manager):
    claim = insert_claim(db, manager, "submitted")
    api = api_as(manager)

    resp = api.approve(claim["id"])

    assert error_of(resp) == (403, "forbidden")
    assert api.get_claim(claim["id"]).json()["status"] == "submitted"


@pytest.mark.parametrize("role", ["employee", "finance"])
def test_only_a_manager_may_approve(role, db, api_as, employee, make_user):
    claim = insert_claim(db, employee, "submitted")

    resp = api_as(make_user(role)).approve(claim["id"])

    assert error_of(resp) == (403, "forbidden")


@pytest.mark.parametrize("status", ["approved", "rejected", "paid"])
def test_only_a_submitted_claim_may_be_approved(status, db, api_as, employee, manager):
    claim = insert_claim(db, employee, status)

    resp = api_as(manager).approve(claim["id"])

    assert error_of(resp) == (409, "invalid_transition")
