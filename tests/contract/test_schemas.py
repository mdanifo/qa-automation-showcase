"""The contracts themselves: valid schemas that accept the documented shape and refuse near misses.

A schema that accepts everything would pass every contract test, so each one
is checked here, with no server, against near misses: every near miss must
break exactly one named check.
"""

from __future__ import annotations

import pytest
from jsonschema import Draft202012Validator

from tests.contract.schemas import failed_checks, load, schema_names

DOCUMENTED_CLAIM = {
    "id": 1,
    "owner": "erin",
    "title": "Team lunch",
    "category": "meals",
    "amount": "42.50",
    "miles": None,
    "expenseDate": "2026-10-01",
    "status": "submitted",
    "submittedAt": "2026-10-02T14:03:11.123456+00:00",
    "decidedBy": None,
    "decidedAt": None,
    "decisionNote": None,
    "paidBy": None,
    "paidAt": None,
}
DECIDED_AT = "2026-10-03T09:00:00.000000+00:00"
PAID_AT = "2026-10-04T16:30:00.000000+00:00"


def claim(**changes):
    """The documented example claim with some keys changed."""
    return {**DOCUMENTED_CLAIM, **changes}


def without(key):
    """The documented example claim with one key removed."""
    return {name: value for name, value in DOCUMENTED_CLAIM.items() if name != key}


@pytest.mark.parametrize("name", schema_names())
def test_every_contract_is_a_valid_draft_2020_12_schema(name):
    Draft202012Validator.check_schema(load(name))


@pytest.mark.parametrize(
    "instance",
    [
        pytest.param(DOCUMENTED_CLAIM, id="submitted"),
        pytest.param(claim(category="mileage", miles="13.5", amount="9.05"), id="mileage"),
        pytest.param(
            claim(status="approved", decidedBy="maya", decidedAt=DECIDED_AT), id="approved"
        ),
        pytest.param(
            claim(
                status="rejected",
                decidedBy="maya",
                decidedAt=DECIDED_AT,
                decisionNote="Not a business expense.",
            ),
            id="rejected",
        ),
        pytest.param(
            claim(
                status="paid", decidedBy="maya", decidedAt=DECIDED_AT, paidBy="fran", paidAt=PAID_AT
            ),
            id="paid",
        ),
        pytest.param(
            claim(status="approved", decidedBy=None, decidedAt=DECIDED_AT),
            id="decider-account-removed",
        ),
    ],
)
def test_claim_contract_accepts_the_documented_shape_in_every_status(instance):
    assert failed_checks(instance, "claim") == []


@pytest.mark.parametrize(
    ("instance", "broken_check"),
    [
        pytest.param(claim(amount=42.5), ("amount", "type"), id="amount-as-json-number"),
        pytest.param(claim(amount="42.5"), ("amount", "pattern"), id="amount-one-decimal"),
        pytest.param(
            claim(amount="1,042.50"), ("amount", "pattern"), id="amount-thousands-separator"
        ),
        pytest.param(claim(extra="x"), ("(root)", "additionalProperties"), id="unexpected-key"),
        pytest.param(without("paidAt"), ("(root)", "required"), id="missing-key"),
        pytest.param(claim(id="1"), ("id", "type"), id="id-as-string"),
        pytest.param(claim(title=""), ("title", "minLength"), id="empty-title"),
        pytest.param(claim(title="x" * 81), ("title", "maxLength"), id="title-81-characters"),
        pytest.param(claim(expenseDate="2026-02-30"), ("expenseDate", "format"), id="no-such-date"),
        pytest.param(
            claim(submittedAt="2026-10-02T14:03:11.123456"),
            ("submittedAt", "pattern"),
            id="timestamp-without-utc-offset",
        ),
        pytest.param(
            claim(category="mileage", miles="13.55"), ("miles", "pattern"), id="miles-two-decimals"
        ),
        pytest.param(claim(category="mileage"), ("miles", "type"), id="mileage-without-miles"),
        pytest.param(claim(miles="10.0"), ("miles", "type"), id="miles-on-a-meals-claim"),
        pytest.param(claim(status="pending"), ("status", "enum"), id="unknown-status"),
        pytest.param(claim(paidAt=PAID_AT), ("paidAt", "type"), id="submitted-but-paid"),
        pytest.param(claim(status="approved"), ("decidedAt", "type"), id="approved-without-time"),
        pytest.param(
            claim(status="rejected", decidedAt=DECIDED_AT),
            ("decisionNote", "type"),
            id="rejected-without-reason",
        ),
        pytest.param(
            claim(status="paid", decidedAt=DECIDED_AT),
            ("paidAt", "type"),
            id="paid-without-payment-time",
        ),
    ],
)
def test_claim_contract_refuses_a_near_miss_for_the_right_reason(instance, broken_check):
    assert failed_checks(instance, "claim") == [broken_check]


def test_claim_list_contract_checks_every_claim_in_the_list():
    instance = {"claims": [DOCUMENTED_CLAIM, claim(id=2, amount=20.0)]}

    assert failed_checks(instance, "claim-list") == [("claims.1.amount", "type")]


@pytest.mark.parametrize(
    ("instance", "broken_checks"),
    [
        pytest.param({"pending": "0.00", "approved": "42.50", "paid": "100.00"}, [], id="valid"),
        pytest.param(
            {"pending": 0, "approved": "42.50", "paid": "100.00"},
            [("pending", "type")],
            id="number",
        ),
        pytest.param(
            {"pending": "0.00", "approved": "42.50", "paid": "100.00", "rejected": "5.00"},
            [("(root)", "additionalProperties")],
            id="rejected-bucket",
        ),
    ],
)
def test_summary_contract_allows_exactly_three_money_strings(instance, broken_checks):
    assert failed_checks(instance, "summary") == broken_checks


@pytest.mark.parametrize(
    ("instance", "broken_checks"),
    [
        pytest.param({"error": "forbidden", "detail": "No."}, [], id="valid"),
        pytest.param(
            {"detail": "Not Found"}, [("(root)", "required")], id="framework-default-shape"
        ),
        pytest.param({"error": "forbidden", "detail": ""}, [("detail", "minLength")], id="empty"),
        pytest.param(
            {"error": "oops", "detail": "Something."}, [("error", "enum")], id="undocumented-code"
        ),
    ],
)
def test_error_contract_allows_only_a_documented_code_and_a_message(instance, broken_checks):
    assert failed_checks(instance, "error") == broken_checks
