"""Finance pays approved claims from /payments and downloads the export from its CSV link.

The page lists every approved claim in the database, other tests' included,
so each test finds its rows by claim id. The export's format is tested in
tests/export; here the check is that the link hands the browser the export
for the signed-in finance user.
"""

from __future__ import annotations

import pytest
from playwright.sync_api import expect

from tests.support import claim_row, days_ago, expect_ok, insert_claim
from tests.ui.pages import csv_rows_by_id


def test_a_claim_waiting_for_payment_shows_whose_it_is_and_the_amount(
    db, sign_in, payments, employee, finance
):
    claim = insert_claim(db, employee, "approved", title="Conference ticket", amount="1250.00")
    sign_in(finance)

    row = payments.open().claim(claim["id"])

    expect(row.owner).to_have_text(employee.display_name)
    expect(row.title).to_have_text("Conference ticket")
    expect(row.amount).to_have_text("$1,250.00")


def test_paying_a_claim_confirms_it_and_takes_it_off_the_list(
    db, sign_in, payments, employee, finance
):
    claim = insert_claim(db, employee, "approved")
    sign_in(finance)

    payments.open().claim(claim["id"]).pay()

    expect(payments.flash).to_have_text(f"Claim #{claim['id']} paid.")
    expect(payments.claim(claim["id"]).root).to_have_count(0)


@pytest.mark.catches("page-ignores-refusal")
def test_paying_from_a_stale_page_shows_why_and_keeps_the_first_payment(
    db, api_as, make_user, sign_in, payments, employee, finance
):
    """Someone else pays the claim while this page sits open, and the stale Pay must say so."""
    claim = insert_claim(db, employee, "approved")
    sign_in(finance)
    row = payments.open().claim(claim["id"])
    expect(row.root).to_be_visible()
    other = make_user("finance")
    expect_ok(api_as(other).pay(claim["id"]))

    row.pay()

    expect(payments.flash_error).to_have_text(
        "Only an approved claim can be paid. This one is paid."
    )
    expect(payments.claim(claim["id"]).root).to_have_count(0)
    assert claim_row(db, claim["id"])["paid_by"] == other.username


def test_the_owner_sees_a_claim_paid_from_the_page_as_paid(
    db, sign_in, payments, dashboard, employee, finance
):
    claim = insert_claim(db, employee, "approved", amount="42.50")
    sign_in(finance)
    payments.open().claim(claim["id"]).pay()
    expect(payments.flash).to_have_text(f"Claim #{claim['id']} paid.")

    sign_in(employee)
    dashboard.open()

    expect(dashboard.claim(claim["id"]).status).to_have_text("Paid")
    expect(dashboard.paid_total).to_have_text("$42.50")


@pytest.mark.parametrize("status", ["submitted", "rejected", "paid"])
def test_only_approved_claims_wait_for_payment(status, db, sign_in, payments, employee, finance):
    approved = insert_claim(db, employee, "approved")
    other = insert_claim(db, employee, status)
    sign_in(finance)

    payments.open()

    expect(payments.claim(approved["id"]).root).to_be_visible()
    expect(payments.claim(other["id"]).root).to_have_count(0)


def test_download_csv_saves_the_export_as_claims_csv(sign_in, payments, finance):
    sign_in(finance)

    download = payments.open().download_csv()

    assert download.suggested_filename == "claims.csv"


@pytest.mark.catches("csv-amount-format")
def test_the_downloaded_csv_holds_an_approved_claim_awaiting_payment(
    db, sign_in, payments, employee, finance
):
    spent_on = days_ago(6)
    claim = insert_claim(
        db, employee, "approved", category="software", amount="49.90", expense_date=spent_on
    )
    sign_in(finance)

    rows = csv_rows_by_id(payments.open().download_csv())

    assert rows[str(claim["id"])] == {
        "id": str(claim["id"]),
        "owner": employee.username,
        "category": "software",
        "amount": "49.90",
        "expense_date": spent_on.isoformat(),
        "status": "approved",
        "paid_at": "",
    }
