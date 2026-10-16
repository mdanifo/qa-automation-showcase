"""Who sees which claims through the API.

Employees see only their own claims. Opening anyone else's is a 404 with the
same body as a claim that does not exist. Managers list their own claims plus
everyone's submitted ones; finance lists approved and paid. Managers and
finance may open any claim by id. (Approve, reject and pay check the role
first, so an employee gets 403 there for any claim that exists; see
test_error_precedence.py.)

The database is shared with other tests, so list assertions look only at the
claims this test created (``& created``), except where a rule holds for every row.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from tests.api.expect import claim_ids, error_of
from tests.support import STATUSES, days_ago, insert_claim


def at_days_ago(days):
    return datetime.now(UTC) - timedelta(days=days)


def one_of_each_status(db, owner):
    """Insert one claim per status for ``owner``; returns {status: id}."""
    return {status: insert_claim(db, owner, status)["id"] for status in STATUSES}


def test_an_employee_may_open_their_own_claim(db, api_as, employee):
    claim = insert_claim(db, employee, "submitted")

    resp = api_as(employee).get_claim(claim["id"])

    assert (resp.status_code, resp.json()["id"]) == (200, claim["id"])


def test_an_employee_gets_404_for_another_employees_claim(db, api_as, make_user):
    owner, snooper = make_user("employee"), make_user("employee")
    claim = insert_claim(db, owner, "submitted")

    resp = api_as(snooper).get_claim(claim["id"])

    assert error_of(resp) == (404, "not_found")
    assert resp.json()["detail"] == f"Claim {claim['id']} does not exist."


@pytest.mark.parametrize("role", ["manager", "finance"])
@pytest.mark.parametrize("status", STATUSES)
def test_managers_and_finance_may_open_any_claim_by_id(role, status, db, api_as, make_user):
    claim = insert_claim(db, make_user("employee"), status)

    resp = api_as(make_user(role)).get_claim(claim["id"])

    assert (resp.status_code, resp.json()["id"]) == (200, claim["id"])


def test_an_employee_lists_exactly_their_own_claims_in_id_order(db, api_as, make_user):
    me, someone_else = make_user("employee"), make_user("employee")
    mine = one_of_each_status(db, me)
    one_of_each_status(db, someone_else)

    resp = api_as(me).list_claims()

    assert claim_ids(resp) == sorted(mine.values())


def test_a_manager_lists_their_own_claims_and_others_submitted_claims(
    db, api_as, employee, manager
):
    own = one_of_each_status(db, manager)
    others = one_of_each_status(db, employee)
    created = set(own.values()) | set(others.values())

    listed = set(claim_ids(api_as(manager).list_claims()))

    assert listed & created == set(own.values()) | {others["submitted"]}


def test_finance_lists_approved_and_paid_claims_including_their_own(db, api_as, employee, finance):
    own = one_of_each_status(db, finance)
    others = one_of_each_status(db, employee)
    created = set(own.values()) | set(others.values())

    listed = set(claim_ids(api_as(finance).list_claims()))

    assert listed & created == {own["approved"], own["paid"], others["approved"], others["paid"]}


def test_finance_never_lists_a_submitted_or_rejected_claim(db, api_as, employee, finance):
    """Checked over every row, other tests' too. The list must hold this test's two first."""
    mine = one_of_each_status(db, employee)

    listed = api_as(finance).list_claims().json()["claims"]

    assert {claim["id"] for claim in listed} >= {mine["approved"], mine["paid"]}
    assert {claim["status"] for claim in listed} == {"approved", "paid"}


def test_the_list_is_ordered_by_id_not_by_date(db, api_as, employee):
    """Dated out of order, so a list sorted by either date, either way, would not match."""
    middle = insert_claim(db, employee, expense_date=days_ago(30), submitted_at=at_days_ago(30))
    newest = insert_claim(db, employee, expense_date=days_ago(1), submitted_at=at_days_ago(1))
    oldest = insert_claim(db, employee, expense_date=days_ago(60), submitted_at=at_days_ago(60))

    resp = api_as(employee).list_claims()

    assert claim_ids(resp) == [middle["id"], newest["id"], oldest["id"]]


@pytest.mark.parametrize("status", STATUSES)
def test_the_status_filter_returns_only_claims_in_that_status(status, db, api_as, employee):
    mine = one_of_each_status(db, employee)

    resp = api_as(employee).list_claims(status=status)

    assert claim_ids(resp) == [mine[status]]


def test_an_empty_status_filter_returns_every_claim(db, api_as, employee):
    mine = one_of_each_status(db, employee)

    resp = api_as(employee).list_claims(status="")

    assert claim_ids(resp) == sorted(mine.values())


@pytest.mark.parametrize("status", ["pending", "Submitted", "all"])
def test_an_unknown_status_filter_is_refused(status, api_as, employee):
    resp = api_as(employee).list_claims(status=status)

    assert error_of(resp) == (422, "validation")
