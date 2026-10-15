"""The page a signed-in user gets when they open a page meant for another role."""

from __future__ import annotations

from playwright.sync_api import Locator

from tests.ui.pages.base import BasePage


class RefusedPage(BasePage):
    """Rendered with status 403 in place of the page that was asked for."""

    @property
    def message(self) -> Locator:
        return self.page.get_by_role("alert")
