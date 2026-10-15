"""Expense dates on submission: today back to 90 days ago, in UTC, as YYYY-MM-DD."""

from __future__ import annotations

import pytest

from tests.api.expect import error_of
from tests.support import claim_body, days_ago, days_ahead


@pytest.mark.parametrize("days_back", [0, 1, 89, 90], ids=lambda n: f"{n}-days-ago")
def test_a_date_from_today_back_to_90_days_ago_is_accepted(days_back, api_as, employee):
    when = days_ago(days_back)

    resp = api_as(employee).create_claim(claim_body(expenseDate=when))

    assert (resp.status_code, resp.json()["expenseDate"]) == (201, when.isoformat())


@pytest.mark.catches("future-date")
def test_an_expense_dated_tomorrow_is_refused(api_as, employee):
    resp = api_as(employee).create_claim(claim_body(expenseDate=days_ahead(1)))

    assert error_of(resp) == (422, "validation")


def test_an_expense_dated_two_days_ahead_is_refused(api_as, employee):
    resp = api_as(employee).create_claim(claim_body(expenseDate=days_ahead(2)))

    assert error_of(resp) == (422, "validation")


def test_an_expense_dated_91_days_ago_is_refused(api_as, employee):
    resp = api_as(employee).create_claim(claim_body(expenseDate=days_ago(91)))

    assert error_of(resp) == (422, "validation")


@pytest.mark.parametrize(
    "expense_date",
    [
        pytest.param("2026/10/01", id="slashes"),
        pytest.param("10/01/2026", id="month-first"),
        pytest.param("2026-02-30", id="no-such-day"),
        pytest.param("yesterday", id="words"),
        pytest.param(20261001, id="json-number"),
        pytest.param(None, id="null"),
    ],
)
def test_a_date_that_is_not_a_real_yyyy_mm_dd_date_is_refused(expense_date, api_as, employee):
    resp = api_as(employee).create_claim(claim_body(expenseDate=expense_date))

    assert error_of(resp) == (422, "validation")
