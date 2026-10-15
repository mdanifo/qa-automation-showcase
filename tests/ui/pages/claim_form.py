"""The new-claim form.

The form has ``novalidate``, so whatever a test types reaches the server and
the server's own message comes back in the alert. The server is the authority
on every rule; the browser only reports it.
"""

from __future__ import annotations

from datetime import date

from playwright.sync_api import Locator

from tests.ui.pages.base import BasePage


class ClaimFormPage(BasePage):
    path = "/claims/new"

    @property
    def title_field(self) -> Locator:
        return self.page.get_by_label("Title", exact=True)

    @property
    def category_field(self) -> Locator:
        return self.page.get_by_label("Category", exact=True)

    @property
    def amount_field(self) -> Locator:
        return self.page.get_by_label("Amount", exact=True)

    @property
    def miles_field(self) -> Locator:
        return self.page.get_by_label("Miles", exact=True)

    @property
    def expense_date_field(self) -> Locator:
        return self.page.get_by_label("Expense date", exact=True)

    @property
    def submit_button(self) -> Locator:
        return self.page.get_by_role("button", name="Submit claim")

    @property
    def error(self) -> Locator:
        """The server's reason for refusing the claim."""
        return self.page.get_by_role("alert")

    def choose_category(self, label: str) -> None:
        """Pick a category by the label a person sees, such as "Mileage"."""
        self.category_field.select_option(label=label)

    def fill_claim(
        self,
        *,
        title: str,
        category: str = "Meals",
        amount: str | None = None,
        miles: str | None = None,
        expense_date: date,
    ) -> None:
        """Fill the form the way a person would: category first, then the field it shows.

        ``category`` is the visible label. Pass ``amount`` for every category
        except Mileage, which takes ``miles``. An empty string leaves a field blank.
        """
        self.title_field.fill(title)
        self.choose_category(category)
        if amount is not None:
            self.amount_field.fill(amount)
        if miles is not None:
            self.miles_field.fill(miles)
        self.expense_date_field.fill(expense_date.isoformat())

    def submit(self) -> None:
        self.submit_button.click()
