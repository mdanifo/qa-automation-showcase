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


@pytest.mark.catches("login-trusts-the-form")
def test_a_name_that_is_not_a_user_cannot_sign_in_even_from_a_tampered_form(
    login_page, page, base_url
):
    """The list offers real users only, but a form can post anything. The server decides."""
    login_page.open().offer("nobody-00000000")
    login_page.user_select.select_option("nobody-00000000")

    login_page.sign_in_button.click()

    expect(page).to_have_url(f"{base_url}/login")
    expect(login_page.error).to_have_text("Pick a user from the list.")
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
