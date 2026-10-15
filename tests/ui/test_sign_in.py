"""Signing in, signing out, and what a browser that is not signed in gets."""

from __future__ import annotations

import pytest
from playwright.sync_api import expect


def test_signing_in_opens_my_claims_as_that_user(login_page, dashboard, employee, base_url):
    login_page.open().sign_in_as(employee)

    expect(dashboard.page).to_have_url(f"{base_url}/")
    expect(dashboard.heading).to_have_text("My claims")
    expect(dashboard.current_user).to_have_text(f"{employee.display_name} (employee)")


@pytest.mark.parametrize("path", ["/", "/claims/new", "/approvals", "/payments"])
def test_a_page_opened_without_signing_in_redirects_to_sign_in(path, page, login_page, base_url):
    page.goto(path)

    expect(page).to_have_url(f"{base_url}/login")
    expect(login_page.heading).to_have_text("Sign in")


def test_a_cookie_naming_an_unknown_user_redirects_to_sign_in(page, context, base_url):
    """The cookie is only a username; a name the app does not know must not get a page."""
    context.add_cookies([{"name": "user", "value": "nobody-00000000", "url": base_url}])

    page.goto("/")

    expect(page).to_have_url(f"{base_url}/login")


def test_signing_out_returns_to_sign_in_and_stays_signed_out(
    sign_in, dashboard, employee, base_url
):
    sign_in(employee)
    dashboard.open()

    dashboard.sign_out()

    expect(dashboard.page).to_have_url(f"{base_url}/login")
    dashboard.open()
    expect(dashboard.page).to_have_url(f"{base_url}/login")
