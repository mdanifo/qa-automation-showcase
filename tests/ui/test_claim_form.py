"""The new-claim form: a good claim lands on the dashboard, a refused one comes back with why.

The business rules themselves are tested through the API and in unit tests.
These tests check what only the browser can show: the form posts the right
fields, the server's message reaches the alert, and the page keeps the
person's input.
"""

from __future__ import annotations

import pytest
from playwright.sync_api import expect

from tests.support import days_ago, insert_claim


@pytest.fixture
def new_claim(sign_in, claim_form, employee):
    """The new-claim form, open and signed in as a fresh employee."""
    sign_in(employee)
    return claim_form.open()


def test_a_submitted_claim_appears_on_the_dashboard_as_submitted(new_claim, dashboard, base_url):
    spent_on = days_ago(2)
    new_claim.fill_claim(
        title="Client dinner", category="Meals", amount="42.50", expense_date=spent_on
    )

    new_claim.submit()

    expect(dashboard.page).to_have_url(f"{base_url}/")
    row = dashboard.claim(dashboard.submitted_claim_id())
    expect(row.title).to_have_text("Client dinner")
    expect(row.category).to_have_text("Meals")
    expect(row.amount).to_have_text("$42.50")
    expect(row.date).to_have_text(spent_on.isoformat())
    expect(row.status).to_have_text("Submitted")


def test_a_submitted_claim_adds_to_the_pending_total(db, employee, new_claim, dashboard):
    insert_claim(db, employee, "submitted", amount="20.00")
    new_claim.fill_claim(title="Client dinner", amount="42.50", expense_date=days_ago(1))

    new_claim.submit()

    expect(dashboard.pending_total).to_have_text("$62.50")
    expect(dashboard.approved_total).to_have_text("$0.00")
    expect(dashboard.paid_total).to_have_text("$0.00")


@pytest.mark.catches("mileage-float-rounding")
def test_a_mileage_claim_is_paid_for_its_miles(new_claim, dashboard):
    """13.5 miles at $0.67 is $9.045, which rounds half up to $9.05."""
    new_claim.fill_claim(
        title="Drive to a client", category="Mileage", miles="13.5", expense_date=days_ago(1)
    )

    new_claim.submit()

    row = dashboard.claim(dashboard.submitted_claim_id())
    expect(row.category).to_have_text("Mileage")
    expect(row.amount).to_have_text("$9.05")


@pytest.mark.parametrize(
    "days_back",
    [pytest.param(0, id="dated-today"), pytest.param(90, id="dated-90-days-ago")],
)
def test_the_form_accepts_an_expense_date_at_either_end_of_the_window(
    days_back, new_claim, dashboard
):
    """The date input's ``max`` is today; both edges must still reach the server and pass."""
    spent_on = days_ago(days_back)
    new_claim.fill_claim(title="Client dinner", amount="20.00", expense_date=spent_on)

    new_claim.submit()

    expect(dashboard.claim(dashboard.submitted_claim_id()).date).to_have_text(spent_on.isoformat())


@pytest.mark.parametrize(
    ("category", "amount_shown", "miles_shown"),
    [
        pytest.param("Meals", True, False, id="meals"),
        pytest.param("Lodging", True, False, id="lodging"),
        pytest.param("Travel", True, False, id="travel"),
        pytest.param("Software", True, False, id="software"),
        pytest.param("Other", True, False, id="other"),
        pytest.param("Mileage", False, True, id="mileage"),
    ],
)
def test_the_form_asks_for_miles_only_for_mileage(category, amount_shown, miles_shown, new_claim):
    new_claim.choose_category(category)

    expect(new_claim.amount_field).to_be_visible(visible=amount_shown)
    expect(new_claim.miles_field).to_be_visible(visible=miles_shown)


def test_leaving_mileage_for_another_category_asks_for_an_amount_again(new_claim):
    new_claim.choose_category("Mileage")

    new_claim.choose_category("Lodging")

    expect(new_claim.amount_field).to_be_visible()
    expect(new_claim.miles_field).to_be_hidden()


def test_an_amount_typed_before_choosing_mileage_is_not_sent(new_claim, dashboard):
    """The server refuses a mileage claim that carries an amount, so a stale one must not post."""
    new_claim.amount_field.fill("20.00")
    new_claim.fill_claim(
        title="Drive to a client", category="Mileage", miles="10.0", expense_date=days_ago(1)
    )

    new_claim.submit()

    expect(dashboard.claim(dashboard.submitted_claim_id()).amount).to_have_text("$6.70")


@pytest.mark.parametrize(
    ("title", "amount", "days_back", "message"),
    [
        pytest.param("   ", "20.00", 1, "A title is required.", id="blank-title"),
        pytest.param(
            "x" * 81, "20.00", 1, "The title can be at most 80 characters.", id="81-char-title"
        ),
        pytest.param("Lunch", "", 1, "An amount is required.", id="no-amount"),
        pytest.param("Lunch", "0.00", 1, "The amount must be greater than zero.", id="zero"),
        pytest.param(
            "Lunch",
            "12.345",
            1,
            "The amount must be dollars with up to two decimals, like 42.50.",
            id="three-decimals",
        ),
        pytest.param(
            "Lunch", "75.01", 1, "Meals claims are limited to $75.00 each.", id="a-cent-over"
        ),
        pytest.param(
            "Lunch",
            "20.00",
            -1,
            "The expense date cannot be in the future.",
            id="tomorrow",
            marks=pytest.mark.catches("future-date"),
        ),
        pytest.param(
            "Lunch",
            "20.00",
            91,
            "The expense date cannot be more than 90 days ago.",
            id="91-days-ago",
        ),
    ],
)
def test_a_refused_claim_shows_the_servers_reason_in_the_alert(
    title, amount, days_back, message, new_claim
):
    new_claim.fill_claim(title=title, amount=amount, expense_date=days_ago(days_back))

    new_claim.submit()

    expect(new_claim.heading).to_have_text("New claim")
    expect(new_claim.error).to_have_text(message)


def test_a_mileage_claim_without_miles_is_refused(new_claim):
    new_claim.fill_claim(
        title="Drive to a client", category="Mileage", miles="", expense_date=days_ago(1)
    )

    new_claim.submit()

    expect(new_claim.error).to_have_text("A mileage claim needs the number of miles.")


def test_a_refused_claim_keeps_what_was_typed(new_claim):
    spent_on = days_ago(5)
    new_claim.fill_claim(title="Client dinner", amount="75.01", expense_date=spent_on)

    new_claim.submit()

    expect(new_claim.error).to_be_visible()
    expect(new_claim.title_field).to_have_value("Client dinner")
    expect(new_claim.category_field).to_have_value("meals")
    expect(new_claim.amount_field).to_have_value("75.01")
    expect(new_claim.expense_date_field).to_have_value(spent_on.isoformat())


def test_a_refused_mileage_claim_comes_back_asking_for_miles(new_claim):
    """The page is rendered again by the server, which must keep the mileage layout."""
    new_claim.fill_claim(
        title="Long drive", category="Mileage", miles="1000.5", expense_date=days_ago(1)
    )

    new_claim.submit()

    expect(new_claim.error).to_have_text("A single claim can cover at most 1000 miles.")
    expect(new_claim.miles_field).to_have_value("1000.5")
    expect(new_claim.amount_field).to_be_hidden()


def test_a_refused_claim_is_not_saved(new_claim, dashboard):
    new_claim.fill_claim(title="Client dinner", amount="75.01", expense_date=days_ago(1))
    new_claim.submit()
    expect(new_claim.error).to_be_visible()

    dashboard.open()

    expect(dashboard.claim_rows).to_have_count(0)
