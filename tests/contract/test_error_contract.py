"""Every kind of error response, checked against contracts/error.schema.json.

The framework's own 400, 404, 405 and 422 are included: a client should not
need a second error parser for the cases the app did not raise itself.
"""

from __future__ import annotations

from tests.contract.schemas import problems
from tests.support import MISSING_CLAIM_ID, claim_body, insert_claim


def test_400_for_a_malformed_form_post_matches_the_error_contract(api_as):
    """A multipart body with no boundary is refused by the form parser, before any route code."""
    resp = api_as(None).post(
        "/login", content=b"user=erin", headers={"Content-Type": "multipart/form-data"}
    )

    assert resp.status_code == 400
    assert problems(resp.json(), "error") == []


def test_401_unauthenticated_matches_the_error_contract(api_as):
    resp = api_as(None).me()

    assert resp.status_code == 401
    assert problems(resp.json(), "error") == []


def test_403_forbidden_matches_the_error_contract(db, api_as, employee, finance):
    claim = insert_claim(db, employee, "submitted")

    resp = api_as(finance).approve(claim["id"])

    assert resp.status_code == 403
    assert problems(resp.json(), "error") == []


def test_404_for_a_missing_claim_matches_the_error_contract(api_as, manager):
    resp = api_as(manager).get_claim(MISSING_CLAIM_ID)

    assert resp.status_code == 404
    assert problems(resp.json(), "error") == []


def test_404_for_an_unknown_route_matches_the_error_contract(api_as, employee):
    resp = api_as(employee).get("/api/no-such-endpoint")

    assert resp.status_code == 404
    assert problems(resp.json(), "error") == []


def test_405_for_a_wrong_method_matches_the_error_contract(api_as, employee):
    resp = api_as(employee).client.delete("/api/claims")

    assert resp.status_code == 405
    assert problems(resp.json(), "error") == []


def test_409_invalid_transition_matches_the_error_contract(db, api_as, employee, finance):
    claim = insert_claim(db, employee, "paid")

    resp = api_as(finance).pay(claim["id"])

    assert resp.status_code == 409
    assert problems(resp.json(), "error") == []


def test_422_from_a_business_rule_matches_the_error_contract(api_as, employee):
    resp = api_as(employee).create_claim(claim_body(amount="0.00"))

    assert resp.status_code == 422
    assert problems(resp.json(), "error") == []


def test_422_from_request_parsing_matches_the_error_contract(api_as, employee):
    resp = api_as(employee).get("/api/claims/not-a-number")

    assert resp.status_code == 422
    assert problems(resp.json(), "error") == []
