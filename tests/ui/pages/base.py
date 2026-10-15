"""What every signed-in page shares: the main navigation, the user badge and flash messages."""

from __future__ import annotations

from typing import ClassVar, Self

from playwright.sync_api import Locator, Page


class BasePage:
    """A page of the app. Subclasses set ``path``; ``open()`` goes there.

    Locators are properties, so each assertion queries the live page and
    Playwright's ``expect`` can wait on it.
    """

    path: ClassVar[str] = "/"

    def __init__(self, page: Page) -> None:
        self.page = page

    def open(self) -> Self:
        """Navigate to this page (relative to the base URL) and return self."""
        self.page.goto(self.path)
        return self

    @property
    def heading(self) -> Locator:
        """The page's one level-1 heading."""
        return self.page.get_by_role("heading", level=1)

    @property
    def navigation(self) -> Locator:
        """The main navigation bar (only shown when signed in)."""
        return self.page.get_by_role("navigation", name="Main")

    @property
    def navigation_links(self) -> Locator:
        """Every link in the main navigation, in order."""
        return self.navigation.get_by_role("link")

    def navigation_link(self, name: str) -> Locator:
        """One link in the main navigation, by its exact text."""
        return self.navigation.get_by_role("link", name=name, exact=True)

    @property
    def body(self) -> Locator:
        """The page's ``<body>``, for checks on the document as a whole."""
        return self.page.locator("body")

    def scroll_width(self) -> int:
        """The document's width in CSS pixels. Wider than the viewport scrolls sideways."""
        return int(self.page.evaluate("document.documentElement.scrollWidth"))

    @property
    def current_user(self) -> Locator:
        """The "Display Name (role)" badge in the header."""
        return self.page.get_by_test_id("current-user")

    @property
    def flash(self) -> Locator:
        """The success message shown after a redirect."""
        return self.page.get_by_role("status")

    @property
    def flash_error(self) -> Locator:
        """The error message shown after a refused button press."""
        return self.page.get_by_test_id("flash-error")

    def go_to(self, link_name: str) -> None:
        """Follow a link in the main navigation."""
        self.navigation_link(link_name).click()

    def sign_out(self) -> None:
        self.page.get_by_role("link", name="Sign out").click()
