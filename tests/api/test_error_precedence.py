"""When a request breaks more than one rule, which error wins.

The order is: the claim must exist (404), then the caller must hold the right
role (403), then it must not be their own claim (403), then the claim must be
in the right status (409), then the reason must be valid (422).
"""

from __future__ import annotations

import pytest

from tests.api.expect import error_of
from tests.support import MISSING_CLAIM_ID, insert_claim

ACTIONS = [
    pytest.param("approve", {}, id="approve"),
    pytest.param("reject", {"json": {"note": "Receipt is missing."}}, id="reject"),
    pytest.param("pay", {}, id="pay"),
]


@pytest.mark.parametrize(("action", "request_body"), ACTIONS)
@pytest.mark.parametrize("role", ["employee", "manager", "finance"])
def test_a_missing_claim_is_404_for_every_role_and_action(
    role, action, request_body, api_as, make_user
):
    api = api_as(make_user(role))

    resp = api.post(f"/api/claims/{MISSING_CLAIM_ID}/{action}", **request_body)

    assert error_of(resp) == (404, "not_found")


@pytest.mark.parametrize(("action", "request_body"), ACTIONS)
def test_an_employee_acting_on_someone_elses_claim_gets_403_not_404(
    action, request_body, db, api_as, make_user
):
    """Role is checked before visibility, so the answer is the same whether or not
    the employee could open the claim. (The id's existence shows; see test_visibility.py.)"""
    claim = insert_claim(db, make_user("employee"), "approved")
    api = api_as(make_user("employee"))

    resp = api.post(f"/api/claims/{claim['id']}/{action}", **request_body)

    assert error_of(resp) == (403, "forbidden")


def test_the_wrong_role_wins_over_the_wrong_status(db, api_as, employee, finance):
    claim = insert_claim(db, employee, "paid")

    resp = api_as(finance).approve(claim["id"])

    assert error_of(resp) == (403, "forbidden")


@pytest.mark.catches("self-approval")
def test_approving_your_own_decided_claim_is_403_not_409(db, api_as, manager):
    claim = insert_claim(db, manager, "approved")

    resp = api_as(manager).approve(claim["id"])

    assert error_of(resp) == (403, "forbidden")


def test_rejecting_your_own_decided_claim_is_403_not_409(db, api_as, manager):
    claim = insert_claim(db, manager, "rejected")

    resp = api_as(manager).reject(claim["id"], note="Again.")

    assert error_of(resp) == (403, "forbidden")


def test_the_wrong_status_wins_over_a_missing_reason(db, api_as, employee, manager):
    claim = insert_claim(db, employee, "approved")

    resp = api_as(manager).reject(claim["id"], note="")

    assert error_of(resp) == (409, "invalid_transition")
