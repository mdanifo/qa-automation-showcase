"""Every endpoint that returns a claim, checked against contracts/claim.schema.json."""

from __future__ import annotations

import pytest

from tests.contract.schemas import problems
from tests.support import STATUSES, claim_body, insert_claim


@pytest.mark.catches("amount-as-number")
def test_create_returns_a_claim_that_matches_the_contract(api_as, employee):
    resp = api_as(employee).create_claim(claim_body(category="meals", amount="42.50"))

    assert resp.status_code == 201
    assert problems(resp.json(), "claim") == []


@pytest.mark.catches("amount-as-number")
def test_create_returns_a_mileage_claim_that_matches_the_contract(api_as, employee):
    resp = api_as(employee).create_claim(claim_body(category="mileage", miles="13.5"))

    assert resp.status_code == 201
    assert problems(resp.json(), "claim") == []


@pytest.mark.catches("amount-as-number")
@pytest.mark.parametrize("status", STATUSES)
def test_get_returns_a_claim_that_matches_the_contract_in_every_status(
    status, claim_in, api_as, manager
):
    claim = claim_in(status)

    resp = api_as(manager).get_claim(claim["id"])

    assert resp.status_code == 200
    assert problems(resp.json(), "claim") == []


@pytest.mark.catches("amount-as-number")
def test_list_returns_claims_that_match_the_contract(claim_in, api_as, employee):
    stored = [claim_in(status)["id"] for status in STATUSES]

    resp = api_as(employee).list_claims()

    assert resp.status_code == 200
    assert [claim["id"] for claim in resp.json()["claims"]] == stored
    assert problems(resp.json(), "claim-list") == []


@pytest.mark.catches("amount-as-number")
def test_approve_returns_a_claim_that_matches_the_contract(db, api_as, employee, manager):
    claim = insert_claim(db, employee, "submitted")

    resp = api_as(manager).approve(claim["id"])

    assert resp.status_code == 200
    assert problems(resp.json(), "claim") == []


@pytest.mark.catches("amount-as-number")
def test_reject_returns_a_claim_that_matches_the_contract(db, api_as, employee, manager):
    claim = insert_claim(db, employee, "submitted")

    resp = api_as(manager).reject(claim["id"], note="Receipt is missing.")

    assert resp.status_code == 200
    assert problems(resp.json(), "claim") == []


@pytest.mark.catches("amount-as-number")
def test_pay_returns_a_claim_that_matches_the_contract(db, api_as, employee, manager, finance):
    claim = insert_claim(db, employee, "approved", decided_by=manager)

    resp = api_as(finance).pay(claim["id"])

    assert resp.status_code == 200
    assert problems(resp.json(), "claim") == []
