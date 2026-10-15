"""POST /api/claims/{id}/reject: approve's rules, plus a reason of 1 to 500 characters."""

from __future__ import annotations

import pytest

from tests.api.expect import error_of, status_of
from tests.support import insert_claim


def reject_path(claim):
    return f"/api/claims/{claim['id']}/reject"


def test_a_manager_rejects_someone_elses_claim_with_a_reason(db, api_as, employee, manager):
    claim = insert_claim(db, employee, "submitted")

    resp = api_as(manager).reject(claim["id"], note="  Receipt is missing.  ")

    rejected = resp.json()
    assert status_of(resp) == (200, "rejected")
    assert (rejected["decidedBy"], rejected["decisionNote"]) == (
        manager.username,
        "Receipt is missing.",
    )
    assert rejected["decidedAt"] is not None


@pytest.mark.catches("reject-without-note")
@pytest.mark.parametrize(
    "request_body",
    [
        pytest.param({"json": {"note": ""}}, id="empty-note"),
        pytest.param({"json": {"note": "   "}}, id="blank-note"),
        pytest.param({"json": {"note": None}}, id="null-note"),
        pytest.param({"json": {}}, id="no-note-key"),
        pytest.param({}, id="no-body"),
    ],
)
def test_a_rejection_without_a_reason_is_refused(request_body, db, api_as, employee, manager):
    claim = insert_claim(db, employee, "submitted")
    api = api_as(manager)

    resp = api.post(reject_path(claim), **request_body)

    assert error_of(resp) == (422, "validation")
    assert api.get_claim(claim["id"]).json()["status"] == "submitted"


def test_a_reason_of_500_characters_is_kept_whole(db, api_as, employee, manager):
    """The last character differs, so a reason cut short shows up in the diff."""
    claim = insert_claim(db, employee, "submitted")
    reason = "x" * 499 + "y"

    resp = api_as(manager).reject(claim["id"], note=reason)

    assert (resp.status_code, resp.json()["decisionNote"]) == (200, reason)


def test_a_reason_of_501_characters_is_refused(db, api_as, employee, manager):
    claim = insert_claim(db, employee, "submitted")

    resp = api_as(manager).reject(claim["id"], note="x" * 501)

    assert error_of(resp) == (422, "validation")


def test_a_reason_sent_as_a_json_array_is_refused(db, api_as, employee, manager):
    claim = insert_claim(db, employee, "submitted")

    resp = api_as(manager).post(reject_path(claim), json=["Receipt is missing."])

    assert error_of(resp) == (422, "validation")


def test_a_manager_cannot_reject_their_own_claim(db, api_as, manager):
    claim = insert_claim(db, manager, "submitted")

    resp = api_as(manager).reject(claim["id"], note="Changed my mind.")

    assert error_of(resp) == (403, "forbidden")


@pytest.mark.parametrize("role", ["employee", "finance"])
def test_only_a_manager_may_reject(role, db, api_as, employee, make_user):
    claim = insert_claim(db, employee, "submitted")

    resp = api_as(make_user(role)).reject(claim["id"], note="Receipt is missing.")

    assert error_of(resp) == (403, "forbidden")


@pytest.mark.parametrize("status", ["approved", "rejected", "paid"])
def test_only_a_submitted_claim_may_be_rejected(status, db, api_as, employee, manager):
    claim = insert_claim(db, employee, status)

    resp = api_as(manager).reject(claim["id"], note="Receipt is missing.")

    assert error_of(resp) == (409, "invalid_transition")
