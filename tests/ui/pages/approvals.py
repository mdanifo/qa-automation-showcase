"""The approvals page: other people's submitted claims, each with Approve and Reject."""

from __future__ import annotations

from playwright.sync_api import Locator

from tests.ui.pages.base import BasePage


class ApprovalRow:
    """One claim waiting for a decision. Each row has its own Reason box."""

    def __init__(self, root: Locator) -> None:
        self.root = root

    @property
    def owner(self) -> Locator:
        return self.root.get_by_test_id("claim-owner")

    @property
    def title(self) -> Locator:
        return self.root.get_by_test_id("claim-title")

    @property
    def category(self) -> Locator:
        return self.root.get_by_test_id("claim-category")

    @property
    def amount(self) -> Locator:
        return self.root.get_by_test_id("claim-amount")

    @property
    def date(self) -> Locator:
        return self.root.get_by_test_id("claim-date")

    @property
    def reason_field(self) -> Locator:
        return self.root.get_by_label("Reason", exact=True)

    def approve(self) -> None:
        self.root.get_by_role("button", name="Approve").click()

    def reject(self, reason: str) -> None:
        """Type ``reason`` (an empty string leaves it blank) and press Reject."""
        self.reason_field.fill(reason)
        self.root.get_by_role("button", name="Reject").click()


class ApprovalsPage(BasePage):
    path = "/approvals"

    def claim(self, claim_id: int) -> ApprovalRow:
        """The row for one claim. The page lists everyone's claims, so always look up by id."""
        return ApprovalRow(self.page.get_by_test_id(f"approval-row-{claim_id}"))
