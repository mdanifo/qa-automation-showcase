"""The endpoints that return no claim: /health, /api/me, /api/summary, and an empty list."""

from __future__ import annotations

import pytest

from tests.contract.schemas import problems
from tests.support import insert_claim


def test_health_matches_the_contract(api_as):
    resp = api_as(None).health()

    assert resp.status_code == 200
    assert problems(resp.json(), "health") == []


@pytest.mark.parametrize("role", ["employee", "manager", "finance"])
def test_me_matches_the_contract_for_every_role(role, make_user, api_as):
    user = make_user(role)

    resp = api_as(user).me()

    assert resp.status_code == 200
    assert problems(resp.json(), "me") == []


def test_summary_matches_the_contract(db, api_as, employee):
    insert_claim(db, employee, "submitted", amount="12.30")
    insert_claim(db, employee, "approved", amount="1200.00", category="travel")
    insert_claim(db, employee, "paid", amount="0.05")

    resp = api_as(employee).summary()

    assert resp.status_code == 200
    assert problems(resp.json(), "summary") == []


def test_an_empty_claim_list_matches_the_contract(api_as, employee):
    resp = api_as(employee).list_claims()

    assert resp.json() == {"claims": []}
    assert problems(resp.json(), "claim-list") == []
