"""Fixtures for the browser tests.

Data is set up through the builders (``insert_claim``, ``submit_claim``) and
checked through the browser. Two places sign in through the form: the login
tests in test_sign_in.py, and ``page_for``, which test_journey.py uses
because an end-to-end run should start where a person does. Every other test
uses ``sign_in``, which sets the same ``user`` cookie the form sets, so a
broken login page fails those two files and nothing else.
"""

from __future__ import annotations

from collections.abc import Callable

import pytest
from playwright.sync_api import BrowserContext, Page, expect

from tests.support import User
from tests.ui.pages import ApprovalsPage, ClaimFormPage, DashboardPage, LoginPage, PaymentsPage

SignIn = Callable[[User], None]
PageFor = Callable[[User], Page]


@pytest.fixture
def sign_in(context: BrowserContext, base_url: str) -> SignIn:
    """``sign_in(user)`` signs the test's browser in as ``user`` without visiting /login."""

    def _sign_in(user: User) -> None:
        context.add_cookies([{"name": "user", "value": user.username, "url": base_url}])

    return _sign_in


@pytest.fixture
def page_for(new_context: Callable[..., BrowserContext]) -> PageFor:
    """``page_for(user)`` opens a separate browser, signed in as ``user`` through the form.

    For tests where several people act at once, each in their own browser.
    pytest-playwright records traces and video for every context it opens.
    """

    def _page_for(user: User) -> Page:
        page = new_context().new_page()
        LoginPage(page).open().sign_in_as(user)
        expect(DashboardPage(page).heading).to_have_text("My claims")  # the cookie is set
        return page

    return _page_for


@pytest.fixture
def login_page(page: Page) -> LoginPage:
    return LoginPage(page)


@pytest.fixture
def dashboard(page: Page) -> DashboardPage:
    return DashboardPage(page)


@pytest.fixture
def claim_form(page: Page) -> ClaimFormPage:
    return ClaimFormPage(page)


@pytest.fixture
def approvals(page: Page) -> ApprovalsPage:
    return ApprovalsPage(page)


@pytest.fixture
def payments(page: Page) -> PaymentsPage:
    return PaymentsPage(page)
