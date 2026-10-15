"""What the finance export contains: its columns, which claims, their order and their values."""

from __future__ import annotations

import csv
import io
from datetime import date, datetime
from decimal import Decimal
from typing import Any

import pytest

from tests.support import insert_claim

HEADER = ["id", "owner", "category", "amount", "expense_date", "status", "paid_at"]


def typed(row: dict[str, str]) -> dict[str, Any]:
    """An export row as database values, so it can be compared with a SELECT."""
    return {
        "id": int(row["id"]),
        "owner": row["owner"],
        "category": row["category"],
        "amount_cents": int(Decimal(row["amount"]) * 100),
        "expense_date": date.fromisoformat(row["expense_date"]),
        "status": row["status"],
        "paid_at": datetime.fromisoformat(row["paid_at"]) if row["paid_at"] else None,
    }


def test_export_is_csv_with_the_documented_header(finance_api):
    resp = finance_api.export_csv()

    assert resp.status_code == 200, resp.text
    assert resp.headers["content-type"].split(";")[0] == "text/csv"
    assert next(csv.reader(io.StringIO(resp.text, newline=""))) == HEADER


def test_every_line_has_one_field_per_column(db, employee, finance_api):
    """Checked over every line. The export must hold this test's two claims first."""
    approved = insert_claim(db, employee, "approved")
    paid = insert_claim(db, employee, "paid")

    lines = list(csv.reader(io.StringIO(finance_api.export_csv().text, newline="")))

    assert {line[0] for line in lines[1:]} >= {str(approved["id"]), str(paid["id"])}
    assert {len(line) for line in lines} == {len(HEADER)}


@pytest.mark.parametrize(
    ("status", "row_count"),
    [
        pytest.param("submitted", 0, id="submitted-left-out"),
        pytest.param("approved", 1, id="approved-listed"),
        pytest.param("rejected", 0, id="rejected-left-out"),
        pytest.param("paid", 1, id="paid-listed"),
    ],
)
def test_export_lists_only_approved_and_paid_claims(db, employee, exported, status, row_count):
    claim = insert_claim(db, employee, status)

    assert len(exported(claim)) == row_count


def test_export_is_ordered_by_claim_id_not_by_date_or_status(
    db, employee, exported, download_export
):
    first = insert_claim(db, employee, "paid", expense_date=date(2026, 9, 30))
    second = insert_claim(db, employee, "approved", expense_date=date(2026, 9, 1))
    third = insert_claim(db, employee, "paid", expense_date=date(2026, 9, 15))

    assert [int(row["id"]) for row in exported(first, second, third)] == [
        first["id"],
        second["id"],
        third["id"],
    ]
    every_id = [int(row["id"]) for row in download_export()]
    assert every_id == sorted(every_id)


def test_export_rows_reconcile_with_the_database(db, employee, exported):
    """Values only: the format of each field is checked in test_export_format.py."""
    claims = [
        insert_claim(db, employee, "submitted", amount="12.00"),
        insert_claim(db, employee, "approved", category="lodging", amount="189.40"),
        insert_claim(db, employee, "rejected", category="software", amount="49.99"),
        insert_claim(db, employee, "paid", category="mileage", miles="13.5"),
        insert_claim(db, employee, "paid", category="travel", amount="1500.00"),
    ]

    stored = db.execute(
        "SELECT id, owner, category, amount_cents, expense_date, status, paid_at"
        " FROM claims WHERE owner = %s AND status IN ('approved', 'paid') ORDER BY id",
        (employee.username,),
    ).fetchall()
    assert [typed(row) for row in exported(*claims)] == stored
