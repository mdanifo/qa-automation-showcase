"""One claim's whole life, from submission to payment, with each person in their own browser.

Every other UI test sets up its data directly and checks one page. This one
proves the pages work together: what the employee submits is what the
manager approves, what finance pays, and what the employee finally sees.
"""

from __future__ import annotations

from playwright.sync_api import expect

from tests.support import days_ago
from tests.ui.pages import ApprovalsPage, ClaimFormPage, DashboardPage, PaymentsPage


def test_a_claim_goes_from_submitted_to_paid_through_the_pages(page_for, make_user):
    employee, manager, finance = make_user("employee"), make_user("manager"), make_user("finance")
    employee_page = page_for(employee)

    form = ClaimFormPage(employee_page).open()
    form.fill_claim(
        title="Train to the workshop", category="Travel", amount="86.40", expense_date=days_ago(2)
    )
    form.submit()
    claim_id = DashboardPage(employee_page).submitted_claim_id()

    approvals = ApprovalsPage(page_for(manager)).open()
    expect(approvals.claim(claim_id).root).to_be_visible()
    approvals.claim(claim_id).approve()
    expect(approvals.flash).to_have_text(f"Claim #{claim_id} approved.")

    payments = PaymentsPage(page_for(finance)).open()
    expect(payments.claim(claim_id).root).to_be_visible()
    payments.claim(claim_id).pay()
    expect(payments.flash).to_have_text(f"Claim #{claim_id} paid.")

    dashboard = DashboardPage(employee_page).open()
    expect(dashboard.claim(claim_id).status).to_have_text("Paid")
    expect(dashboard.pending_total).to_have_text("$0.00")
    expect(dashboard.approved_total).to_have_text("$0.00")
    expect(dashboard.paid_total).to_have_text("$86.40")
