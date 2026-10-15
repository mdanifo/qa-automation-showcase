"""validate_new_claim: the whole submission, including which money field each category sends."""

from __future__ import annotations

from decimal import Decimal

import pytest

from expenses import rules
from tests.support import FIXED_TODAY, FIXED_YESTERDAY, OMIT, claim_body


def body(**overrides):
    """A valid submission dated the day before FIXED_TODAY."""
    return claim_body(**{"expenseDate": FIXED_YESTERDAY, **overrides})


def test_a_valid_claim_becomes_a_new_claim_with_exact_values():
    submission = body(title="  Team lunch ", category="meals", amount="42.50")

    assert rules.validate_new_claim(submission, today=FIXED_TODAY) == rules.NewClaim(
        title="Team lunch",
        category="meals",
        amount_cents=4250,
        miles=None,
        expense_date=FIXED_YESTERDAY,
    )


def test_a_valid_mileage_claim_carries_its_miles_and_computed_amount():
    submission = body(category="mileage", miles="10.0")

    assert rules.validate_new_claim(submission, today=FIXED_TODAY) == rules.NewClaim(
        title="Team lunch",
        category="mileage",
        amount_cents=670,
        miles=Decimal("10.0"),
        expense_date=FIXED_YESTERDAY,
    )


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        pytest.param(
            {"category": "mileage", "amount": "9.05"},
            "sends miles, not an amount",
            id="mileage-with-amount",
        ),
        pytest.param(
            {"category": "mileage", "miles": OMIT},
            "needs the number of miles",
            id="mileage-without-miles",
        ),
        pytest.param({"miles": "10.0"}, "only for mileage claims", id="meals-with-miles"),
        pytest.param({"amount": OMIT}, "An amount is required", id="meals-without-amount"),
        pytest.param({"category": "Meals"}, "category must be one of", id="capitalized-category"),
        pytest.param({"category": "gifts"}, "category must be one of", id="unknown-category"),
        pytest.param({"category": OMIT}, "category must be one of", id="missing-category"),
        pytest.param({"category": 3}, "category must be one of", id="category-number"),
        pytest.param({"title": OMIT}, "A title is required", id="missing-title"),
        pytest.param({"expenseDate": OMIT}, "YYYY-MM-DD", id="missing-date"),
    ],
)
def test_a_submission_with_the_wrong_fields_is_refused(overrides, message):
    with pytest.raises(rules.ValidationError, match=message):
        rules.validate_new_claim(body(**overrides), today=FIXED_TODAY)


@pytest.mark.parametrize(
    ("overrides", "cents"),
    [
        pytest.param({"miles": None}, 2000, id="meals-with-null-miles"),
        pytest.param({"category": "mileage", "amount": None}, 670, id="mileage-with-null-amount"),
    ],
)
def test_a_null_money_field_counts_as_absent(overrides, cents):
    assert rules.validate_new_claim(body(**overrides), today=FIXED_TODAY).amount_cents == cents


@pytest.mark.parametrize(
    "value",
    [
        pytest.param([], id="list"),
        pytest.param("claim", id="string"),
        pytest.param(None, id="none"),
    ],
)
def test_a_submission_that_is_not_an_object_is_refused(value):
    with pytest.raises(rules.ValidationError, match="must be a JSON object"):
        rules.validate_new_claim(value, today=FIXED_TODAY)
