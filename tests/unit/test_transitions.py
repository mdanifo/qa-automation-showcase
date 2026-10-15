"""Who may approve, reject and pay, and from which status.

Checks run in a fixed order, so each error is the most useful one: wrong role,
then own claim, then wrong status, then a bad reason.
"""

from __future__ import annotations

import pytest

from expenses import rules
from tests.support import DECIDED


def test_a_manager_may_approve_someone_elses_submitted_claim():
    assert (
        rules.check_approve(actor="maya", role="manager", owner="erin", status="submitted") is None
    )


@pytest.mark.parametrize("role", ["employee", "finance"])
def test_only_a_manager_may_approve(role):
    with pytest.raises(rules.Forbidden, match="Only a manager can approve"):
        rules.check_approve(actor="fran", role=role, owner="erin", status="submitted")


@pytest.mark.catches("self-approval")
def test_a_manager_may_not_approve_their_own_claim():
    with pytest.raises(rules.Forbidden, match="cannot approve your own claim"):
        rules.check_approve(actor="maya", role="manager", owner="maya", status="submitted")


@pytest.mark.parametrize("status", DECIDED)
def test_only_a_submitted_claim_may_be_approved(status):
    with pytest.raises(rules.InvalidTransition, match=f"This one is {status}"):
        rules.check_approve(actor="maya", role="manager", owner="erin", status=status)


@pytest.mark.catches("self-approval")
def test_approving_your_own_decided_claim_is_forbidden_before_the_status_is_checked():
    with pytest.raises(rules.Forbidden, match="cannot approve your own claim"):
        rules.check_approve(actor="maya", role="manager", owner="maya", status="approved")


def test_approving_as_the_wrong_role_is_forbidden_before_the_status_is_checked():
    with pytest.raises(rules.Forbidden, match="Only a manager can approve"):
        rules.check_approve(actor="erin", role="employee", owner="eli", status="paid")


def test_a_manager_may_reject_someone_elses_submitted_claim_and_gets_the_cleaned_reason():
    reason = rules.check_reject(
        actor="maya", role="manager", owner="erin", status="submitted", note="  No receipt. "
    )

    assert reason == "No receipt."


@pytest.mark.parametrize("role", ["employee", "finance"])
def test_only_a_manager_may_reject(role):
    with pytest.raises(rules.Forbidden, match="Only a manager can reject"):
        rules.check_reject(
            actor="fran", role=role, owner="erin", status="submitted", note="No receipt."
        )


def test_a_manager_may_not_reject_their_own_claim():
    with pytest.raises(rules.Forbidden, match="cannot reject your own claim"):
        rules.check_reject(
            actor="maya", role="manager", owner="maya", status="submitted", note="No receipt."
        )


@pytest.mark.parametrize("status", DECIDED)
def test_only_a_submitted_claim_may_be_rejected(status):
    with pytest.raises(rules.InvalidTransition, match=f"This one is {status}"):
        rules.check_reject(
            actor="maya", role="manager", owner="erin", status=status, note="No receipt."
        )


@pytest.mark.catches("reject-without-note")
@pytest.mark.parametrize(
    "note",
    [pytest.param("", id="empty"), pytest.param("   ", id="blank"), pytest.param(None, id="none")],
)
def test_a_rejection_without_a_reason_is_refused(note):
    with pytest.raises(rules.ValidationError, match="needs a reason"):
        rules.check_reject(
            actor="maya", role="manager", owner="erin", status="submitted", note=note
        )


def test_rejecting_a_decided_claim_reports_the_status_before_the_missing_reason():
    with pytest.raises(rules.InvalidTransition, match="This one is approved"):
        rules.check_reject(actor="maya", role="manager", owner="erin", status="approved", note="")


def test_finance_may_pay_an_approved_claim():
    assert rules.check_pay(role="finance", status="approved") is None


@pytest.mark.parametrize("role", ["employee", "manager"])
def test_only_finance_may_pay(role):
    with pytest.raises(rules.Forbidden, match="Only finance can pay"):
        rules.check_pay(role=role, status="approved")


@pytest.mark.parametrize(
    "status",
    [
        pytest.param("submitted", marks=pytest.mark.catches("pay-unapproved")),
        pytest.param("rejected", marks=pytest.mark.catches("pay-unapproved")),
        pytest.param("paid"),
    ],
)
def test_only_an_approved_claim_may_be_paid(status):
    with pytest.raises(rules.InvalidTransition, match=f"This one is {status}"):
        rules.check_pay(role="finance", status=status)
