"""Mileage pays 67 cents a mile, rounded half up to the cent, with miles capped at 1000."""

from __future__ import annotations

import re
from decimal import Decimal

import pytest

from expenses import rules
from tests.support import FIXED_TODAY, FIXED_YESTERDAY, claim_body

FLOAT_LOSES_THE_HALF_CENT = pytest.mark.catches("mileage-float-rounding")


@pytest.mark.parametrize(
    ("miles", "cents"),
    [
        pytest.param("0.1", 7, id="0.067-rounds-up"),
        pytest.param("0.3", 20, id="0.201-rounds-down"),
        pytest.param("1", 67, id="one-mile"),
        pytest.param("1.5", 101, id="1.005-half-up"),
        pytest.param("10.0", 670, id="no-rounding"),
        pytest.param("13.5", 905, id="9.045-half-up", marks=FLOAT_LOSES_THE_HALF_CENT),
        pytest.param("14.5", 972, id="9.715-half-up", marks=FLOAT_LOSES_THE_HALF_CENT),
        pytest.param("15.5", 1039, id="10.385-half-up", marks=FLOAT_LOSES_THE_HALF_CENT),
        pytest.param("746.2", 49995, id="largest-claim-under-the-limit"),
        pytest.param("1000", 67000, id="most-miles-allowed"),
    ],
)
def test_mileage_pay_is_miles_times_67_cents_rounded_half_up(miles, cents):
    """Every half-mile lands on a half cent, but float math loses it only on some inputs
    (13.5, 14.5 and 15.5 come out a cent short, 1.5 does not), so only those rows are marked.
    """
    assert rules.mileage_cents(Decimal(miles)) == cents


@pytest.mark.parametrize(
    ("text", "miles"),
    [
        ("13.5", Decimal("13.5")),
        ("0.1", Decimal("0.1")),
        ("42", Decimal("42")),
        ("1000", Decimal("1000")),
        ("1000.0", Decimal("1000.0")),
    ],
)
def test_miles_parse_with_at_most_one_decimal(text, miles):
    assert rules.parse_miles(text) == miles


@pytest.mark.parametrize(
    "value",
    [
        pytest.param("13.55", id="two-decimals"),
        pytest.param("13.", id="trailing-point"),
        pytest.param(".5", id="no-whole-miles"),
        pytest.param("-1", id="negative"),
        pytest.param("1e2", id="exponent"),
        pytest.param("", id="empty"),
        pytest.param(13.5, id="float"),
        pytest.param(None, id="none"),
    ],
)
def test_miles_that_are_not_a_one_decimal_string_are_refused(value):
    with pytest.raises(rules.ValidationError, match="at most one decimal"):
        rules.parse_miles(value)


@pytest.mark.parametrize("text", ["0", "0.0"])
def test_zero_miles_are_refused(text):
    with pytest.raises(rules.ValidationError, match="greater than zero"):
        rules.parse_miles(text)


def test_more_than_1000_miles_are_refused():
    with pytest.raises(rules.ValidationError, match="at most 1000 miles"):
        rules.parse_miles("1000.1")


@pytest.mark.catches("mileage-float-rounding")
def test_a_mileage_claim_for_13_5_miles_is_stored_as_905_cents():
    body = claim_body(category="mileage", miles="13.5", expenseDate=FIXED_YESTERDAY)

    new = rules.validate_new_claim(body, today=FIXED_TODAY)

    assert (new.miles, new.amount_cents) == (Decimal("13.5"), 905)


def test_a_mileage_claim_over_the_500_dollar_limit_is_refused():
    """746.3 miles is under the 1000-mile cap but pays $500.02, over the mileage limit."""
    body = claim_body(category="mileage", miles="746.3", expenseDate=FIXED_YESTERDAY)

    with pytest.raises(
        rules.ValidationError, match=re.escape("Mileage claims are limited to $500.00 each.")
    ):
        rules.validate_new_claim(body, today=FIXED_TODAY)
