"""How each export field is written: money with two decimals, dates in ISO 8601."""

from __future__ import annotations

from datetime import UTC, date, datetime

import pytest

from tests.support import insert_claim

catches = pytest.mark.catches


@pytest.mark.parametrize(
    ("cents", "written"),
    [
        pytest.param(4250, "42.50", id="trailing-zero", marks=catches("csv-amount-format")),
        pytest.param(700, "7.00", id="whole-dollars", marks=catches("csv-amount-format")),
        pytest.param(10, "0.10", id="ten-cents", marks=catches("csv-amount-format")),
        pytest.param(150000, "1500.00", id="1500-dollars", marks=catches("csv-amount-format")),
        pytest.param(5, "0.05", id="five-cents"),
        pytest.param(123456, "1234.56", id="no-thousands-separator"),
    ],
)
def test_amount_is_written_with_two_decimals_and_a_period(db, employee, export_row, cents, written):
    """A float formatter gets 0.05 and 1234.56 right, so the table needs trailing zeros too."""
    claim = insert_claim(db, employee, "approved", category="travel", amount_cents=cents)

    assert export_row(claim)["amount"] == written


def test_expense_date_is_written_as_an_iso_date(db, employee, export_row):
    claim = insert_claim(db, employee, "approved", expense_date=date(2026, 3, 7))

    assert export_row(claim)["expense_date"] == "2026-03-07"


def test_paid_at_is_an_iso_timestamp_of_the_payment(db, employee, export_row):
    paid_at = datetime(2026, 3, 9, 14, 5, 7, 250000, tzinfo=UTC)
    claim = insert_claim(db, employee, "paid", paid_at=paid_at)

    written = datetime.fromisoformat(export_row(claim)["paid_at"])

    assert written.tzinfo is not None, "paid_at carries no UTC offset"
    assert written == paid_at


def test_paid_at_is_empty_for_an_approved_claim(db, employee, export_row):
    claim = insert_claim(db, employee, "approved")

    assert export_row(claim)["paid_at"] == ""
