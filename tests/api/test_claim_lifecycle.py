"""One claim from submission to payment through the API, read back after every step."""

from __future__ import annotations

import pytest

from tests.support import submit_claim


@pytest.mark.catches("approval-not-saved")
def test_a_claim_goes_from_submitted_to_approved_to_paid(api_as, employee, manager, finance):
    """Each step is read back with a fresh GET, so a reply that was never committed shows up."""
    owner, approver, payer = api_as(employee), api_as(manager), api_as(finance)
    claim_id = submit_claim(owner, amount="64.20")["id"]

    approver.approve(claim_id)
    after_approve = owner.get_claim(claim_id).json()
    payer.pay(claim_id)
    after_pay = owner.get_claim(claim_id).json()

    assert (after_approve["status"], after_approve["decidedBy"]) == ("approved", manager.username)
    assert (after_pay["status"], after_pay["paidBy"]) == ("paid", finance.username)
    assert owner.summary().json() == {"pending": "0.00", "approved": "0.00", "paid": "64.20"}
