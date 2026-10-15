"""The dashboard: each claim's row, which claims are listed and in what order, and the totals.

Claims are written with ``insert_claim`` in the state each test needs, so a
dashboard test never depends on approve, reject or pay working.
"""

from __future__ import annotations

import pytest
from playwright.sync_api import expect

from tests.support import days_ago, insert_claim


def test_a_user_with_no_claims_sees_zero_totals_and_an_empty_list(sign_in, dashboard, employee):
    sign_in(employee)

    dashboard.open()

    expect(dashboard.pending_total).to_have_text("$0.00")
    expect(dashboard.approved_total).to_have_text("$0.00")
    expect(dashboard.paid_total).to_have_text("$0.00")
    expect(dashboard.claim_rows).to_have_count(0)
    expect(dashboard.empty_message).to_be_visible()


def test_a_claim_row_shows_its_title_category_amount_date_and_status(
    db, sign_in, dashboard, employee
):
    spent_on = days_ago(3)
    claim = insert_claim(
        db,
        employee,
        "approved",
        title="Hotel, two nights",
        category="lodging",
        amount="123.40",
        expense_date=spent_on,
    )
    sign_in(employee)

    dashboard.open()

    row = dashboard.claim(claim["id"])
    expect(row.title).to_have_text("Hotel, two nights")
    expect(row.category).to_have_text("Lodging")
    expect(row.amount).to_have_text("$123.40")
    expect(row.date).to_have_text(spent_on.isoformat())
    expect(row.status).to_have_text("Approved")


@pytest.mark.parametrize(
    ("status", "label"),
    [
        pytest.param("submitted", "Submitted", id="submitted"),
        pytest.param("approved", "Approved", id="approved"),
        pytest.param("rejected", "Rejected", id="rejected"),
        pytest.param("paid", "Paid", id="paid"),
    ],
)
def test_a_claim_row_names_its_status(status, label, db, sign_in, dashboard, employee):
    claim = insert_claim(db, employee, status)
    sign_in(employee)

    dashboard.open()

    expect(dashboard.claim(claim["id"]).status).to_have_text(label)


def test_the_new_claim_link_opens_the_form(sign_in, dashboard, claim_form, employee, base_url):
    sign_in(employee)
    dashboard.open()

    dashboard.new_claim_link.click()

    expect(claim_form.page).to_have_url(f"{base_url}/claims/new")
    expect(claim_form.heading).to_have_text("New claim")


def test_claims_are_listed_newest_first(db, sign_in, dashboard, employee):
    for title in ("First", "Second", "Third"):
        insert_claim(db, employee, title=title)
    sign_in(employee)

    dashboard.open()

    expect(dashboard.claim_titles).to_have_text(["Third", "Second", "First"])


def test_the_list_holds_only_the_signed_in_users_claims(db, make_user, sign_in, dashboard):
    erin, eli = make_user("employee"), make_user("employee")
    insert_claim(db, erin, title="Erin's lunch")
    insert_claim(db, eli, title="Eli's lunch")
    sign_in(erin)

    dashboard.open()

    expect(dashboard.claim_titles).to_have_text(["Erin's lunch"])


@pytest.mark.parametrize(
    ("status", "pending", "approved", "paid"),
    [
        pytest.param("submitted", "$42.50", "$0.00", "$0.00", id="submitted-is-pending"),
        pytest.param("approved", "$0.00", "$42.50", "$0.00", id="approved"),
        pytest.param("paid", "$0.00", "$0.00", "$42.50", id="paid"),
    ],
)
def test_a_claim_counts_toward_the_total_for_its_status(
    status, pending, approved, paid, db, sign_in, dashboard, employee
):
    insert_claim(db, employee, status, amount="42.50")
    sign_in(employee)

    dashboard.open()

    expect(dashboard.pending_total).to_have_text(pending)
    expect(dashboard.approved_total).to_have_text(approved)
    expect(dashboard.paid_total).to_have_text(paid)


@pytest.mark.catches("pending-total-includes-rejected")
def test_a_rejected_claim_counts_toward_no_total(db, sign_in, dashboard, employee):
    insert_claim(db, employee, "rejected", amount="42.50")
    sign_in(employee)

    dashboard.open()

    expect(dashboard.pending_total).to_have_text("$0.00")
    expect(dashboard.approved_total).to_have_text("$0.00")
    expect(dashboard.paid_total).to_have_text("$0.00")


@pytest.mark.catches("pending-total-includes-rejected")
def test_the_pending_total_adds_submitted_claims_and_leaves_rejected_ones_out(
    db, sign_in, dashboard, employee
):
    insert_claim(db, employee, "submitted", amount="20.00")
    insert_claim(db, employee, "submitted", amount="5.25")
    insert_claim(db, employee, "rejected", amount="60.00")
    insert_claim(db, employee, "approved", amount="42.50")
    insert_claim(db, employee, "paid", amount="100.00")
    sign_in(employee)

    dashboard.open()

    expect(dashboard.pending_total).to_have_text("$25.25")
    expect(dashboard.approved_total).to_have_text("$42.50")
    expect(dashboard.paid_total).to_have_text("$100.00")


def test_a_total_over_a_thousand_dollars_has_a_thousands_separator(
    db, sign_in, dashboard, employee
):
    insert_claim(db, employee, "approved", category="travel", amount="1500.00")
    insert_claim(db, employee, "approved", category="travel", amount="1499.99")
    sign_in(employee)

    dashboard.open()

    expect(dashboard.approved_total).to_have_text("$2,999.99")


def test_totals_count_only_the_signed_in_users_claims(db, sign_in, dashboard, employee, manager):
    """A manager sees other people's claims on Approvals, but that money is not theirs."""
    insert_claim(db, employee, "submitted", amount="30.00")
    insert_claim(db, manager, "submitted", amount="12.00")
    sign_in(manager)

    dashboard.open()

    expect(dashboard.pending_total).to_have_text("$12.00")
