"""Smoke tests: the shared fixtures work before any layer depends on them."""

from __future__ import annotations

import pytest

from expenses import bugs
from tests.support import claim_events, claim_row, insert_claim, submit_claim, user_exists

pytestmark = pytest.mark.smoke


def test_server_is_healthy_and_reports_the_seeded_bug(api_as):
    resp = api_as(None).health()

    assert resp.status_code == 200
    assert resp.json() == {"status": "ok", "seededBug": bugs.current()}


def test_made_user_is_known_to_the_api(make_user, api_as):
    maya = make_user("manager", display_name="Smoke Manager")

    resp = api_as(maya).me()

    assert resp.status_code == 200
    assert resp.json() == {
        "username": maya.username,
        "displayName": "Smoke Manager",
        "role": "manager",
    }


def test_made_user_submits_a_claim_through_the_api(employee, api_as, db):
    claim = submit_claim(api_as(employee), title="Smoke lunch")

    assert claim["owner"] == employee.username
    assert claim["status"] == "submitted"
    stored = claim_row(db, claim["id"])
    assert stored is not None
    assert stored["title"] == "Smoke lunch"


def test_insert_claim_writes_the_row_in_the_requested_state(db, employee, finance):
    claim = insert_claim(
        db, employee, status="paid", amount="42.50", paid_by=finance, with_events=True
    )

    stored = claim_row(db, claim["id"])
    assert stored is not None
    assert stored["status"] == "paid"
    assert stored["amount_cents"] == 4250
    assert stored["paid_by"] == finance.username
    assert [e["action"] for e in claim_events(db, claim["id"])] == [
        "submitted",
        "approved",
        "paid",
    ]


def test_cleanup_removes_claims_and_users(db, cleanup, make_user, api_as):
    erin = make_user("employee")
    via_api = submit_claim(api_as(erin))
    direct = insert_claim(db, erin, status="approved")

    cleanup.run()  # the same call the fixture makes after every test

    assert claim_row(db, via_api["id"]) is None
    assert claim_row(db, direct["id"]) is None
    assert claim_events(db, via_api["id"]) == []
    assert not user_exists(db, erin)
