"""POST /api/claims: what a valid submission creates, and the request shapes that are refused."""

from __future__ import annotations

from unittest.mock import ANY

import pytest

from tests.api.expect import error_of
from tests.support import OMIT, claim_body, days_ago


@pytest.mark.catches("amount-as-number")
def test_a_valid_claim_is_created_as_submitted_and_owned_by_the_caller(api_as, employee):
    resp = api_as(employee).create_claim(
        claim_body(title="Team lunch", category="meals", amount="42.50", expenseDate=days_ago(3))
    )

    assert resp.status_code == 201
    assert resp.json() == {
        "id": ANY,
        "owner": employee.username,
        "title": "Team lunch",
        "category": "meals",
        "amount": "42.50",
        "miles": None,
        "expenseDate": days_ago(3).isoformat(),
        "status": "submitted",
        "submittedAt": ANY,
        "decidedBy": None,
        "decidedAt": None,
        "decisionNote": None,
        "paidBy": None,
        "paidAt": None,
    }


def test_the_created_claim_can_be_read_back_at_its_location(api_as, employee):
    api = api_as(employee)
    created = api.create_claim(claim_body())

    resp = api.get(created.headers["location"])

    assert created.headers["location"] == f"/api/claims/{created.json()['id']}"
    assert resp.json() == created.json()


@pytest.mark.parametrize("role", ["employee", "manager", "finance"])
def test_every_role_may_submit_a_claim(role, make_user, api_as):
    user = make_user(role)

    resp = api_as(user).create_claim(claim_body())

    assert (resp.status_code, resp.json()["owner"]) == (201, user.username)


def test_ownership_status_and_decision_fields_in_the_body_are_ignored(api_as, employee, manager):
    """A client cannot submit a claim on someone else's behalf or skip straight to paid."""
    body = claim_body(
        id=1,
        owner=manager.username,
        status="paid",
        decidedBy=manager.username,
        decisionNote="Looks fine.",
        paidBy=manager.username,
    )

    claim = api_as(employee).create_claim(body).json()

    assert (claim["owner"], claim["status"]) == (employee.username, "submitted")
    assert (claim["decidedBy"], claim["decisionNote"], claim["paidBy"]) == (None, None, None)


def test_the_title_is_stored_without_surrounding_whitespace(api_as, employee):
    resp = api_as(employee).create_claim(claim_body(title="   Taxi to the airport  "))

    assert resp.json()["title"] == "Taxi to the airport"


def test_the_api_returns_the_title_exactly_as_typed_including_markup(api_as, employee):
    """Escaping is the page's job. The API must not mangle the data it was given."""
    title = '<b>Lunch</b> & "drinks"'

    resp = api_as(employee).create_claim(claim_body(title=title))

    assert resp.json()["title"] == title


@pytest.mark.parametrize(
    "title",
    [pytest.param("x", id="1-character"), pytest.param("x" * 79 + "y", id="80-characters")],
)
def test_a_title_of_1_to_80_characters_is_accepted_whole(title, api_as, employee):
    """The last character differs, so a title cut short shows up in the diff."""
    resp = api_as(employee).create_claim(claim_body(title=title))

    assert (resp.status_code, resp.json()["title"]) == (201, title)


@pytest.mark.parametrize(
    "title",
    [
        pytest.param("x" * 81, id="81-characters"),
        pytest.param("   ", id="blank"),
        pytest.param("", id="empty"),
    ],
)
def test_a_title_that_is_blank_or_over_80_characters_is_refused(title, api_as, employee):
    resp = api_as(employee).create_claim(claim_body(title=title))

    assert error_of(resp) == (422, "validation")


@pytest.mark.parametrize(
    "overrides",
    [
        pytest.param({"title": OMIT}, id="no-title"),
        pytest.param({"category": OMIT}, id="no-category"),
        pytest.param({"category": "gifts"}, id="unknown-category"),
        pytest.param({"category": "MEALS"}, id="upper-case-category"),
        pytest.param({"amount": OMIT}, id="no-amount"),
        pytest.param({"miles": "10.0"}, id="miles-on-a-meals-claim"),
        pytest.param({"category": "mileage", "miles": OMIT}, id="mileage-without-miles"),
        pytest.param({"category": "mileage", "amount": "6.70"}, id="mileage-with-an-amount"),
        pytest.param({"expenseDate": OMIT}, id="no-date"),
    ],
)
def test_a_submission_with_missing_or_conflicting_fields_is_refused(overrides, api_as, employee):
    resp = api_as(employee).create_claim(claim_body(**overrides))

    assert error_of(resp) == (422, "validation")


@pytest.mark.parametrize(
    "content",
    [
        pytest.param(b"", id="empty-body"),
        pytest.param(b"{not json", id="not-json"),
        pytest.param(b'["Team lunch", "meals"]', id="json-array"),
        pytest.param(b'"Team lunch"', id="json-string"),
        pytest.param(b"null", id="json-null"),
    ],
)
def test_a_body_that_is_not_a_json_object_is_refused(content, api_as, employee):
    resp = api_as(employee).post(
        "/api/claims", content=content, headers={"Content-Type": "application/json"}
    )

    assert error_of(resp) == (422, "validation")
