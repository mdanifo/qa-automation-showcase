"""A refused action writes nothing: the claim row and its history stay exactly as they were.

A refusal that answers 403, 409 or 422 after a partial write would leave a row
the API reports as untouched. These tests compare the whole row and the whole
event history before and after.
"""

from __future__ import annotations

import pytest

from tests.support import claim_events, claim_row

ERROR_FOR_STATUS = {403: "forbidden", 409: "invalid_transition", 422: "validation"}
NOTE = {"note": "No receipt."}
LONG_NOTE = {"note": "x" * 501}
catches = pytest.mark.catches


@pytest.mark.parametrize(
    ("start", "role", "action", "body", "status"),
    [
        pytest.param("submitted", "employee", "approve", None, 403, id="employee-approves"),
        pytest.param("submitted", "finance", "approve", None, 403, id="finance-approves"),
        pytest.param("approved", "manager", "approve", None, 409, id="approve-approved"),
        pytest.param("rejected", "manager", "approve", None, 409, id="approve-rejected"),
        pytest.param("paid", "manager", "approve", None, 409, id="approve-paid"),
        pytest.param("submitted", "employee", "reject", NOTE, 403, id="employee-rejects"),
        pytest.param("approved", "manager", "reject", NOTE, 409, id="reject-approved"),
        pytest.param("paid", "manager", "reject", NOTE, 409, id="reject-paid"),
        pytest.param("submitted", "manager", "reject", {"note": ""}, 422, id="reject-empty-note",
                     marks=catches("reject-without-note")),
        pytest.param("submitted", "manager", "reject", {"note": "   "}, 422, id="reject-blank-note",
                     marks=catches("reject-without-note")),
        pytest.param("submitted", "manager", "reject", {}, 422, id="reject-no-note-key",
                     marks=catches("reject-without-note")),
        pytest.param("submitted", "manager", "reject", LONG_NOTE, 422, id="reject-501-char-note"),
        pytest.param("approved", "employee", "pay", None, 403, id="employee-pays"),
        pytest.param("approved", "manager", "pay", None, 403, id="manager-pays"),
        pytest.param("submitted", "finance", "pay", None, 409, id="pay-submitted",
                     marks=catches("pay-unapproved")),
        pytest.param("rejected", "finance", "pay", None, 409, id="pay-rejected",
                     marks=catches("pay-unapproved")),
        pytest.param("paid", "finance", "pay", None, 409, id="pay-paid"),
    ],
)  # fmt: skip
def test_refused_transition_leaves_the_claim_and_its_history_unchanged(
    db, claim_in, make_user, api_as, start, role, action, body, status
):
    claim = claim_in(start)
    row_before = claim_row(db, claim["id"])
    events_before = claim_events(db, claim["id"])

    resp = api_as(make_user(role)).post(f"/api/claims/{claim['id']}/{action}", json=body)

    assert resp.status_code == status, resp.text
    assert resp.json()["error"] == ERROR_FOR_STATUS[status]
    assert claim_row(db, claim["id"]) == row_before
    assert claim_events(db, claim["id"]) == events_before


@pytest.mark.parametrize(
    ("action", "body"),
    [
        pytest.param("approve", None, id="approve", marks=catches("self-approval")),
        pytest.param("reject", NOTE, id="reject"),
    ],
)
def test_manager_acting_on_their_own_claim_leaves_it_unchanged(
    db, claim_in, manager, api_as, action, body
):
    claim = claim_in("submitted", owner=manager)
    row_before = claim_row(db, claim["id"])
    events_before = claim_events(db, claim["id"])

    resp = api_as(manager).post(f"/api/claims/{claim['id']}/{action}", json=body)

    assert resp.status_code == 403, resp.text
    assert resp.json()["error"] == "forbidden"
    assert claim_row(db, claim["id"]) == row_before
    assert claim_events(db, claim["id"]) == events_before
