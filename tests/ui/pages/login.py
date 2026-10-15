"""The sign-in page: pick a user from the list, no password."""

from __future__ import annotations

from playwright.sync_api import Locator

from tests.support import User
from tests.ui.pages.base import BasePage


class LoginPage(BasePage):
    path = "/login"

    @property
    def user_select(self) -> Locator:
        return self.page.get_by_label("User", exact=True)

    @property
    def sign_in_button(self) -> Locator:
        return self.page.get_by_role("button", name="Sign in")

    def sign_in_as(self, user: User) -> None:
        """Choose ``user`` by the text a person sees ("Name (role)") and press Sign in."""
        self.user_select.select_option(label=f"{user.display_name} ({user.role})")
        self.sign_in_button.click()
