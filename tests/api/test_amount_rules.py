"""Amounts on submission: inclusive category limits, the two-decimal format, and mileage pay."""

from __future__ import annotations

import pytest

from tests.api.expect import error_of
from tests.support import claim_body

AT_THE_LIMIT = [
    pytest.param("meals", "75.00", id="meals"),
    pytest.param("lodging", "300.00", id="lodging"),
    pytest.param("travel", "1500.00", id="travel"),
    pytest.param("software", "500.00", id="software"),
    pytest.param("other", "250.00", id="other"),
]
ONE_CENT_UNDER = [
    pytest.param("meals", "74.99", id="meals"),
    pytest.param("lodging", "299.99", id="lodging"),
    pytest.param("travel", "1499.99", id="travel"),
    pytest.param("software", "499.99", id="software"),
    pytest.param("other", "249.99", id="other"),
]
ONE_CENT_OVER = [
    pytest.param("meals", "75.01", id="meals"),
    pytest.param("lodging", "300.01", id="lodging"),
    pytest.param("travel", "1500.01", id="travel"),
    pytest.param("software", "500.01", id="software"),
    pytest.param("other", "250.01", id="other"),
]


@pytest.mark.catches("limit-off-by-one")
@pytest.mark.parametrize(("category", "amount"), AT_THE_LIMIT)
def test_a_claim_for_exactly_the_category_limit_is_accepted(category, amount, api_as, employee):
    resp = api_as(employee).create_claim(claim_body(category=category, amount=amount))

    assert resp.status_code == 201, resp.text


@pytest.mark.parametrize(("category", "amount"), ONE_CENT_UNDER)
def test_a_claim_one_cent_under_the_category_limit_is_accepted(category, amount, api_as, employee):
    resp = api_as(employee).create_claim(claim_body(category=category, amount=amount))

    assert resp.status_code == 201, resp.text


@pytest.mark.parametrize(("category", "amount"), ONE_CENT_OVER)
def test_a_claim_one_cent_over_the_category_limit_is_refused(category, amount, api_as, employee):
    resp = api_as(employee).create_claim(claim_body(category=category, amount=amount))

    assert error_of(resp) == (422, "validation")


@pytest.mark.catches("amount-as-number")
@pytest.mark.parametrize(
    ("sent", "returned"),
    [("42.5", "42.50"), ("42", "42.00"), ("0.01", "0.01"), ("74.9", "74.90")],
)
def test_the_amount_comes_back_as_a_string_with_two_decimals(sent, returned, api_as, employee):
    resp = api_as(employee).create_claim(claim_body(amount=sent))

    assert resp.json()["amount"] == returned


@pytest.mark.parametrize(
    "amount",
    [
        pytest.param(42.5, id="json-number"),
        pytest.param(42, id="json-integer"),
        pytest.param("42.505", id="three-decimals"),
        pytest.param("-1.00", id="negative"),
        pytest.param("0.00", id="zero"),
        pytest.param("1,000.00", id="thousands-separator"),
        pytest.param("$42.50", id="currency-symbol"),
        pytest.param("", id="empty"),
    ],
)
def test_an_amount_that_is_not_a_positive_two_decimal_string_is_refused(amount, api_as, employee):
    resp = api_as(employee).create_claim(claim_body(amount=amount))

    assert error_of(resp) == (422, "validation")


@pytest.mark.parametrize(
    ("miles", "amount"),
    [
        pytest.param("10.0", "6.70", id="no-rounding"),
        pytest.param("0.1", "0.07", id="0.067-rounds-up"),
        pytest.param(
            "13.5", "9.05", id="9.045-half-up", marks=pytest.mark.catches("mileage-float-rounding")
        ),
        pytest.param(
            "14.5", "9.72", id="9.715-half-up", marks=pytest.mark.catches("mileage-float-rounding")
        ),
        pytest.param("746.2", "499.95", id="largest-under-the-limit"),
    ],
)
def test_mileage_pays_67_cents_a_mile_rounded_half_up(miles, amount, api_as, employee):
    resp = api_as(employee).create_claim(claim_body(category="mileage", miles=miles))

    assert resp.status_code == 201, resp.text
    assert (resp.json()["miles"], resp.json()["amount"]) == (miles, amount)


@pytest.mark.parametrize(
    "miles",
    [
        pytest.param("746.3", id="pays-500.02"),
        pytest.param("1000", id="most-miles-allowed-pays-670.00"),
    ],
)
def test_mileage_that_pays_over_the_500_dollar_limit_is_refused(miles, api_as, employee):
    resp = api_as(employee).create_claim(claim_body(category="mileage", miles=miles))

    assert error_of(resp) == (422, "validation")


@pytest.mark.parametrize(
    "miles",
    [
        pytest.param("13.55", id="two-decimals"),
        pytest.param("0", id="zero"),
        pytest.param("1000.1", id="over-1000"),
        pytest.param("-5", id="negative"),
        pytest.param(13.5, id="json-number"),
    ],
)
def test_miles_that_are_not_a_positive_one_decimal_string_are_refused(miles, api_as, employee):
    resp = api_as(employee).create_claim(claim_body(category="mileage", miles=miles))

    assert error_of(resp) == (422, "validation")
