"""What each role can reach: the navigation it is shown and the pages it is refused."""

from __future__ import annotations

import pytest
from playwright.sync_api import expect

from tests.ui.pages import RefusedPage


@pytest.mark.parametrize(
    ("role", "links"),
    [
        pytest.param("employee", ["My claims"], id="employee"),
        pytest.param("manager", ["My claims", "Approvals"], id="manager"),
        pytest.param("finance", ["My claims", "Payments"], id="finance"),
    ],
)
def test_the_navigation_shows_only_the_pages_for_the_users_role(
    role, links, make_user, sign_in, dashboard
):
    sign_in(make_user(role))

    dashboard.open()

    expect(dashboard.navigation_links).to_have_text(links)


@pytest.mark.parametrize(
    ("role", "link", "path", "heading"),
    [
        pytest.param("manager", "Approvals", "/approvals", "Approvals", id="manager-approvals"),
        pytest.param("finance", "Payments", "/payments", "Payments", id="finance-payments"),
    ],
)
def test_a_navigation_link_opens_its_page_and_marks_it_current(
    role, link, path, heading, make_user, sign_in, dashboard, base_url
):
    sign_in(make_user(role))
    dashboard.open()

    dashboard.go_to(link)

    expect(dashboard.page).to_have_url(f"{base_url}{path}")
    expect(dashboard.heading).to_have_text(heading)
    expect(dashboard.navigation_link(link)).to_have_attribute("aria-current", "page")


@pytest.mark.parametrize(
    ("role", "path", "message"),
    [
        pytest.param(
            "employee", "/approvals", "This page is for the manager role.", id="employee-approvals"
        ),
        pytest.param(
            "employee", "/payments", "This page is for the finance role.", id="employee-payments"
        ),
        pytest.param(
            "finance", "/approvals", "This page is for the manager role.", id="finance-approvals"
        ),
        pytest.param(
            "manager", "/payments", "This page is for the finance role.", id="manager-payments"
        ),
    ],
)
def test_a_page_for_another_role_is_refused(role, path, message, make_user, sign_in, page):
    sign_in(make_user(role))

    response = page.goto(path)

    refused = RefusedPage(page)
    assert response is not None
    assert response.status == 403
    expect(refused.heading).to_have_text("Not allowed")
    expect(refused.message).to_have_text(message)
