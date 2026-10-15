"""Category limits are inclusive: exactly the limit is allowed, one cent more is not."""

from __future__ import annotations

import re
from decimal import Decimal

import pytest

from expenses import rules
from tests.support import FIXED_TODAY, FIXED_YESTERDAY, claim_body

PUBLISHED_LIMITS = {
    "meals": Decimal("75.00"),
    "lodging": Decimal("300.00"),
    "travel": Decimal("1500.00"),
    "software": Decimal("500.00"),
    "other": Decimal("250.00"),
    "mileage": Decimal("500.00"),
}
LIMITS_IN_CENTS = [
    pytest.param("meals", 7500, id="meals"),
    pytest.param("lodging", 30000, id="lodging"),
    pytest.param("travel", 150000, id="travel"),
    pytest.param("software", 50000, id="software"),
    pytest.param("other", 25000, id="other"),
    pytest.param("mileage", 50000, id="mileage"),
]

AMOUNT_LIMITS = [
    pytest.param("meals", "75.00", 7500, id="meals"),
    pytest.param("lodging", "300.00", 30000, id="lodging"),
    pytest.param("travel", "1500.00", 150000, id="travel"),
    pytest.param("software", "500.00", 50000, id="software"),
    pytest.param("other", "250.00", 25000, id="other"),
]


def test_the_limit_table_is_the_published_policy():
    assert rules.CATEGORY_LIMITS == PUBLISHED_LIMITS


@pytest.mark.catches("limit-off-by-one")
@pytest.mark.parametrize(("category", "limit"), LIMITS_IN_CENTS)
def test_an_amount_exactly_at_the_limit_is_within_it(category, limit):
    assert rules.within_limit(limit, category) is True


@pytest.mark.parametrize(("category", "limit"), LIMITS_IN_CENTS)
def test_an_amount_one_cent_under_the_limit_is_within_it(category, limit):
    assert rules.within_limit(limit - 1, category) is True


@pytest.mark.parametrize(("category", "limit"), LIMITS_IN_CENTS)
def test_an_amount_one_cent_over_the_limit_is_not_within_it(category, limit):
    assert rules.within_limit(limit + 1, category) is False


@pytest.mark.catches("limit-off-by-one")
@pytest.mark.parametrize(("category", "amount", "cents"), AMOUNT_LIMITS)
def test_a_claim_for_exactly_the_limit_is_accepted(category, amount, cents):
    body = claim_body(category=category, amount=amount, expenseDate=FIXED_YESTERDAY)

    assert rules.validate_new_claim(body, today=FIXED_TODAY).amount_cents == cents


@pytest.mark.parametrize(
    ("category", "amount", "message"),
    [
        pytest.param("meals", "75.01", "Meals claims are limited to $75.00 each.", id="meals"),
        pytest.param(
            "lodging", "300.01", "Lodging claims are limited to $300.00 each.", id="lodging"
        ),
        pytest.param(
            "travel", "1500.01", "Travel claims are limited to $1500.00 each.", id="travel"
        ),
        pytest.param(
            "software", "500.01", "Software claims are limited to $500.00 each.", id="software"
        ),
        pytest.param("other", "250.01", "Other claims are limited to $250.00 each.", id="other"),
    ],
)
def test_a_claim_one_cent_over_the_limit_is_refused_naming_the_limit(category, amount, message):
    body = claim_body(category=category, amount=amount, expenseDate=FIXED_YESTERDAY)

    with pytest.raises(rules.ValidationError, match=re.escape(message)):
        rules.validate_new_claim(body, today=FIXED_TODAY)
