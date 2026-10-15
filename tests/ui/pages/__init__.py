"""Page objects for the UI tests: one class per page, locators as properties.

Tests talk to pages through these, so a changed label or layout is fixed in
one place. Page objects find things and press things; tests make the
assertions with Playwright's ``expect``.
"""

from tests.ui.pages.approvals import ApprovalRow, ApprovalsPage
from tests.ui.pages.base import BasePage
from tests.ui.pages.claim_form import ClaimFormPage
from tests.ui.pages.dashboard import ClaimRow, DashboardPage
from tests.ui.pages.login import LoginPage
from tests.ui.pages.payments import PaymentRow, PaymentsPage, csv_rows_by_id
from tests.ui.pages.refused import RefusedPage

__all__ = [
    "ApprovalRow",
    "ApprovalsPage",
    "BasePage",
    "ClaimFormPage",
    "ClaimRow",
    "DashboardPage",
    "LoginPage",
    "PaymentRow",
    "PaymentsPage",
    "RefusedPage",
    "csv_rows_by_id",
]
