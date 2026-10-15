"""Money on the way in and out: a dollar string becomes integer cents, and cents print as "0.00"."""

from __future__ import annotations

import pytest

from expenses import rules


@pytest.mark.parametrize(
    ("text", "cents"),
    [
        ("42.50", 4250),
        ("42.5", 4250),
        ("42", 4200),
        ("0.01", 1),
        ("0.5", 50),
        ("007.10", 710),
        ("1500.00", 150000),
        ("99999.99", 9999999),
    ],
)
def test_a_dollar_string_parses_to_exact_cents(text, cents):
    assert rules.parse_amount(text) == cents


@pytest.mark.parametrize(
    "text",
    [
        pytest.param("42.505", id="three-decimals"),
        pytest.param("42.", id="trailing-point"),
        pytest.param(".50", id="no-dollars"),
        pytest.param("-5.00", id="negative"),
        pytest.param("+5.00", id="plus-sign"),
        pytest.param("1,000.00", id="thousands-separator"),
        pytest.param("1e3", id="exponent"),
        pytest.param("NaN", id="nan"),
        pytest.param("Infinity", id="infinity"),
        pytest.param("$42.50", id="currency-symbol"),
        pytest.param(" 42.50", id="leading-space"),
        pytest.param("42.50\n", id="trailing-newline"),
        pytest.param("", id="empty"),
        pytest.param("\u0664\u0662.\u0665\u0660", id="arabic-indic-digits"),
    ],
)
def test_an_amount_that_is_not_plain_dollars_and_cents_is_refused(text):
    with pytest.raises(rules.ValidationError, match="up to two decimals"):
        rules.parse_amount(text)


@pytest.mark.parametrize(
    "value",
    [
        pytest.param(42.5, id="float"),
        pytest.param(42, id="int"),
        pytest.param(None, id="none"),
        pytest.param(True, id="bool"),
        pytest.param(["42.50"], id="list"),
    ],
)
def test_an_amount_that_is_not_a_string_is_refused(value):
    """A JSON number is refused outright, so binary floating point never reaches the ledger."""
    with pytest.raises(rules.ValidationError, match="must be a string"):
        rules.parse_amount(value)


@pytest.mark.parametrize("text", ["0", "0.0", "0.00", "000"])
def test_a_zero_amount_is_refused(text):
    with pytest.raises(rules.ValidationError, match="greater than zero"):
        rules.parse_amount(text)


@pytest.mark.parametrize(
    ("cents", "text"),
    [
        (0, "0.00"),
        (1, "0.01"),
        (10, "0.10"),
        (100, "1.00"),
        (4250, "42.50"),
        (150000, "1500.00"),
        (123456789, "1234567.89"),
    ],
)
def test_cents_format_with_two_decimals_and_no_thousands_separator(cents, text):
    assert rules.format_cents(cents) == text
