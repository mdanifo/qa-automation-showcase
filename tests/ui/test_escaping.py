"""Claim titles show as text, never as markup, on every page that shows one.

A title is typed once and shown to other people: to its owner on My claims,
to a manager on Approvals, to finance on Payments. Markup in it must reach
each of them as the characters typed, or it is stored cross-site scripting.
The seeded bug unescaped-title breaks My claims only, so only those rows are
marked for it; Approvals and Payments are checked the same way.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import NamedTuple

import pytest
from playwright.sync_api import Locator, expect

from tests.support import insert_claim, submit_claim
from tests.ui.pages import BasePage

VIEWS = [
    pytest.param("my-claims", marks=pytest.mark.catches("unescaped-title")),
    pytest.param("approvals"),
    pytest.param("payments"),
]


class Shown(NamedTuple):
    page: BasePage
    title: Locator


@pytest.fixture
def show_title(
    db, api_as, sign_in, dashboard, approvals, payments, employee, manager, finance
) -> Callable[[str, str], Shown]:
    """``show_title(view, title)``: an employee's claim titled ``title``, opened in ``view``.

    The employee types the title through the API. My claims is opened as the
    employee, Approvals as a manager and Payments (after the claim is
    approved) as finance.
    """

    def show(view: str, title: str) -> Shown:
        if view == "payments":
            claim = insert_claim(db, employee, "approved", title=title)
            sign_in(finance)
            return Shown(payments, payments.open().claim(claim["id"]).title)
        claim = submit_claim(api_as(employee), title=title)
        if view == "approvals":
            sign_in(manager)
            return Shown(approvals, approvals.open().claim(claim["id"]).title)
        sign_in(employee)
        return Shown(dashboard, dashboard.open().claim(claim["id"]).title)

    return show


@pytest.mark.parametrize("view", VIEWS)
@pytest.mark.parametrize(
    "title",
    [
        pytest.param("<b>Team</b> lunch", id="tag"),
        pytest.param("Fish &amp; chips", id="entity"),
        pytest.param('<img src="/receipt.png" alt="receipt">', id="element-without-text"),
    ],
)
def test_a_title_containing_html_shows_as_literal_text(title, view, show_title):
    shown = show_title(view, title)

    expect(shown.title).to_have_text(title)


@pytest.mark.parametrize("view", VIEWS)
def test_a_script_in_a_title_does_not_run(view, show_title):
    """An inline script runs while the page is parsed, before ``open()`` returns,
    so checking for its side effect afterwards cannot race it.
    """
    script = '<script>document.body.dataset.injected="yes"</script>'

    shown = show_title(view, script)

    expect(shown.title).to_have_text(script)
    expect(shown.page.body).not_to_have_attribute("data-injected", "yes")
