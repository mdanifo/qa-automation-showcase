"""The finance payments page: approved claims with a Pay button, and the CSV download."""

from __future__ import annotations

import csv
from pathlib import Path

from playwright.sync_api import Download, Locator

from tests.ui.pages.base import BasePage


class PaymentRow:
    """One approved claim waiting to be paid."""

    def __init__(self, root: Locator) -> None:
        self.root = root

    @property
    def owner(self) -> Locator:
        return self.root.get_by_test_id("claim-owner")

    @property
    def title(self) -> Locator:
        return self.root.get_by_test_id("claim-title")

    @property
    def amount(self) -> Locator:
        return self.root.get_by_test_id("claim-amount")

    def pay(self) -> None:
        self.root.get_by_role("button", name="Pay").click()


class PaymentsPage(BasePage):
    path = "/payments"

    @property
    def download_csv_link(self) -> Locator:
        return self.page.get_by_role("link", name="Download CSV")

    def claim(self, claim_id: int) -> PaymentRow:
        """The row for one claim. The page lists everyone's claims, so always look up by id."""
        return PaymentRow(self.page.get_by_test_id(f"payment-row-{claim_id}"))

    def download_csv(self) -> Download:
        """Click "Download CSV" and return the download once the browser has it."""
        with self.page.expect_download() as download:
            self.download_csv_link.click()
        return download.value


def csv_rows_by_id(download: Download) -> dict[str, dict[str, str]]:
    """The downloaded export's rows keyed by claim id, values as the file holds them."""
    with Path(download.path()).open(newline="", encoding="utf-8") as handle:
        return {row["id"]: row for row in csv.DictReader(handle)}
