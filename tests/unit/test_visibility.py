"""Who sees which claims: in a list, and when opening one by id."""

from __future__ import annotations

import pytest

from expenses import rules

ME = "viewer"
SOMEONE_ELSE = "someone-else"
OWNER = {"own": ME, "other": SOMEONE_ELSE}

LIST_VISIBILITY = [
    # role, whose claim, status, listed
    ("employee", "own", "submitted", True),
    ("employee", "own", "approved", True),
    ("employee", "own", "rejected", True),
    ("employee", "own", "paid", True),
    ("employee", "other", "submitted", False),
    ("employee", "other", "approved", False),
    ("employee", "other", "rejected", False),
    ("employee", "other", "paid", False),
    ("manager", "own", "submitted", True),
    ("manager", "own", "approved", True),
    ("manager", "own", "rejected", True),
    ("manager", "own", "paid", True),
    ("manager", "other", "submitted", True),
    ("manager", "other", "approved", False),
    ("manager", "other", "rejected", False),
    ("manager", "other", "paid", False),
    ("finance", "own", "submitted", False),
    ("finance", "own", "approved", True),
    ("finance", "own", "rejected", False),
    ("finance", "own", "paid", True),
    ("finance", "other", "submitted", False),
    ("finance", "other", "approved", True),
    ("finance", "other", "rejected", False),
    ("finance", "other", "paid", True),
]


@pytest.mark.parametrize(("role", "whose", "status", "listed"), LIST_VISIBILITY)
def test_claim_list_visibility_follows_the_role_table(role, whose, status, listed):
    assert rules.visible_in_list(viewer=ME, role=role, owner=OWNER[whose], status=status) is listed


@pytest.mark.parametrize(
    ("role", "owner", "can_open"),
    [
        pytest.param("employee", ME, True, id="employee-own"),
        pytest.param("employee", SOMEONE_ELSE, False, id="employee-other"),
        pytest.param("manager", SOMEONE_ELSE, True, id="manager-other"),
        pytest.param("finance", SOMEONE_ELSE, True, id="finance-other"),
        pytest.param("auditor", SOMEONE_ELSE, False, id="unknown-role-other"),
    ],
)
def test_opening_a_claim_by_id_is_allowed_for_its_owner_managers_and_finance(role, owner, can_open):
    assert rules.can_view(viewer=ME, role=role, owner=owner) is can_open


def test_an_unknown_role_lists_nothing():
    assert rules.visible_in_list(viewer=ME, role="auditor", owner=ME, status="paid") is False


@pytest.mark.parametrize("text", [None, ""])
def test_a_missing_or_empty_status_filter_means_no_filter(text):
    assert rules.parse_status_filter(text) is None


@pytest.mark.parametrize("status", ["submitted", "approved", "rejected", "paid"])
def test_each_status_is_a_valid_filter(status):
    assert rules.parse_status_filter(status) == status


@pytest.mark.parametrize("text", ["Submitted", "pending", "all", "paid,approved"])
def test_any_other_status_filter_is_refused(text):
    with pytest.raises(rules.ValidationError, match="status must be one of"):
        rules.parse_status_filter(text)
