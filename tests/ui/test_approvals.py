"""Managers decide on other people's submitted claims from /approvals.

The page lists every submitted claim in the database, including other
tests' claims, so each test finds its rows by claim id. A test that checks a
claim is absent first checks one of its own claims is present, so an empty
or broken page cannot pass for a correct one.

No page shows a rejection's reason, so the one test that checks the typed
reason was stored reads it back from the database.
"""

from __future__ import annotations

import pytest
from playwright.sync_api import expect

from tests.support import claim_row, days_ago, insert_claim


def test_a_waiting_claim_shows_whose_it_is_and_what_it_is_for(
    db, sign_in, approvals, employee, manager
):
    spent_on = days_ago(4)
    claim = insert_claim(
        db,
        employee,
        title="Taxi to the airport",
        category="travel",
        amount="64.20",
        expense_date=spent_on,
    )
    sign_in(manager)

    row = approvals.open().claim(claim["id"])

    expect(row.owner).to_have_text(employee.display_name)
    expect(row.title).to_have_text("Taxi to the airport")
    expect(row.category).to_have_text("Travel")
    expect(row.amount).to_have_text("$64.20")
    expect(row.date).to_have_text(spent_on.isoformat())


@pytest.mark.catches("approval-not-saved")
def test_approving_a_claim_confirms_it_and_takes_it_off_the_list(
    db, sign_in, approvals, employee, manager
):
    claim = insert_claim(db, employee)
    sign_in(manager)

    approvals.open().claim(claim["id"]).approve()

    expect(approvals.flash).to_have_text(f"Claim #{claim['id']} approved.")
    expect(approvals.claim(claim["id"]).root).to_have_count(0)


@pytest.mark.catches("approval-not-saved")
def test_the_owner_sees_a_claim_approved_from_the_page_as_approved(
    db, sign_in, approvals, dashboard, employee, manager
):
    claim = insert_claim(db, employee, amount="42.50")
    sign_in(manager)
    approvals.open().claim(claim["id"]).approve()
    expect(approvals.flash).to_have_text(f"Claim #{claim['id']} approved.")

    sign_in(employee)
    dashboard.open()

    expect(dashboard.claim(claim["id"]).status).to_have_text("Approved")
    expect(dashboard.approved_total).to_have_text("$42.50")


def test_the_confirmation_shows_once(db, sign_in, approvals, employee, manager):
    claim = insert_claim(db, employee)
    sign_in(manager)
    approvals.open().claim(claim["id"]).approve()
    expect(approvals.flash).to_have_text(f"Claim #{claim['id']} approved.")

    approvals.open()

    expect(approvals.heading).to_have_text("Approvals")
    expect(approvals.flash).to_have_count(0)


def test_rejecting_a_claim_with_a_reason_confirms_it_and_takes_it_off_the_list(
    db, sign_in, approvals, employee, manager
):
    claim = insert_claim(db, employee)
    sign_in(manager)

    approvals.open().claim(claim["id"]).reject("  Personal meal, not a business expense.  ")

    expect(approvals.flash).to_have_text(f"Claim #{claim['id']} rejected.")
    expect(approvals.claim(claim["id"]).root).to_have_count(0)
    assert claim_row(db, claim["id"])["decision_note"] == "Personal meal, not a business expense."


def test_the_owner_sees_a_claim_rejected_from_the_page_as_rejected(
    db, sign_in, approvals, dashboard, employee, manager
):
    claim = insert_claim(db, employee)
    sign_in(manager)
    approvals.open().claim(claim["id"]).reject("Personal meal, not a business expense.")
    expect(approvals.flash).to_have_text(f"Claim #{claim['id']} rejected.")

    sign_in(employee)
    dashboard.open()

    expect(dashboard.claim(claim["id"]).status).to_have_text("Rejected")


@pytest.mark.catches("reject-without-note")
@pytest.mark.parametrize("reason", [pytest.param("", id="empty"), pytest.param("   ", id="spaces")])
def test_rejecting_without_a_reason_is_refused_and_the_claim_stays(
    reason, db, sign_in, approvals, employee, manager
):
    claim = insert_claim(db, employee)
    sign_in(manager)

    approvals.open().claim(claim["id"]).reject(reason)

    expect(approvals.flash_error).to_have_text("A rejection needs a reason.")
    expect(approvals.claim(claim["id"]).root).to_be_visible()


def test_a_manager_is_not_offered_their_own_claims(db, sign_in, approvals, employee, manager):
    others = insert_claim(db, employee)
    own = insert_claim(db, manager)
    sign_in(manager)

    approvals.open()

    expect(approvals.claim(others["id"]).root).to_be_visible()
    expect(approvals.claim(own["id"]).root).to_have_count(0)


@pytest.mark.parametrize("status", ["approved", "rejected", "paid"])
def test_a_claim_that_was_already_decided_is_not_listed(
    status, db, sign_in, approvals, employee, manager
):
    waiting = insert_claim(db, employee)
    decided = insert_claim(db, employee, status)
    sign_in(manager)

    approvals.open()

    expect(approvals.claim(waiting["id"]).root).to_be_visible()
    expect(approvals.claim(decided["id"]).root).to_have_count(0)
