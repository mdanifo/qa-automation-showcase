"""The dashboard ("My claims"): the signed-in user's totals and their claims, newest first."""

from __future__ import annotations

import re

from playwright.sync_api import Locator, expect

from tests.ui.pages.base import BasePage

_SUBMITTED_FLASH = re.compile(r"^Claim #(\d+) submitted\.$")


class ClaimRow:
    """One row of the claims table, with a locator per column."""

    def __init__(self, root: Locator) -> None:
        self.root = root

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
    def status(self) -> Locator:
        return self.root.get_by_test_id("claim-status")


class DashboardPage(BasePage):
    path = "/"

    @property
    def pending_total(self) -> Locator:
        return self.page.get_by_test_id("total-pending")

    @property
    def approved_total(self) -> Locator:
        return self.page.get_by_test_id("total-approved")

    @property
    def paid_total(self) -> Locator:
        return self.page.get_by_test_id("total-paid")

    @property
    def claims_table(self) -> Locator:
        return self.page.get_by_test_id("claims-table")

    @property
    def claim_rows(self) -> Locator:
        """Body rows only, so the header row is never counted."""
        return self.claims_table.locator("tbody").get_by_role("row")

    @property
    def claim_titles(self) -> Locator:
        """The Title cell of every row, top to bottom."""
        return self.claims_table.get_by_test_id("claim-title")

    @property
    def empty_message(self) -> Locator:
        return self.page.get_by_text("No claims yet.", exact=True)

    @property
    def new_claim_link(self) -> Locator:
        return self.page.get_by_role("link", name="New claim")

    def claim(self, claim_id: int) -> ClaimRow:
        """The row for one claim, found by id rather than by position."""
        return ClaimRow(self.page.get_by_test_id(f"claim-row-{claim_id}"))

    def submitted_claim_id(self) -> int:
        """The claim id named by the "Claim #<id> submitted." flash, once it shows."""
        expect(self.flash).to_have_text(_SUBMITTED_FLASH)
        match = _SUBMITTED_FLASH.match(self.flash.inner_text().strip())
        assert match is not None
        return int(match.group(1))
