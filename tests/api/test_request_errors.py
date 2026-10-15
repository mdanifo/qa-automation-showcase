"""Requests the routes cannot serve: unknown paths, wrong methods, and ids that cannot exist.

Each one gets the documented error shape with the right status, never a 500.
"""

from __future__ import annotations

import pytest

from tests.api.expect import error_of


def test_an_unknown_api_path_is_404(api_as, employee):
    assert error_of(api_as(employee).get("/api/claim")) == (404, "not_found")


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("DELETE", "/api/claims/1"),
        ("PUT", "/api/claims/1"),
        ("GET", "/api/claims/1/approve"),
        ("POST", "/api/summary"),
    ],
)
def test_an_unsupported_method_is_405(method, path, api_as, employee):
    resp = api_as(employee).client.request(method, path)

    assert error_of(resp) == (405, "method_not_allowed")


@pytest.mark.parametrize("claim_id", ["abc", "1.5", "1e3"])
def test_a_claim_id_that_is_not_an_integer_is_422(claim_id, api_as, manager):
    assert error_of(api_as(manager).get(f"/api/claims/{claim_id}")) == (422, "validation")


@pytest.mark.parametrize(
    "claim_id",
    [
        pytest.param(0, id="zero"),
        pytest.param(-1, id="negative"),
        pytest.param(2**31, id="past-the-32-bit-id-range"),
        pytest.param(10**30, id="far-past-any-integer-column"),
    ],
)
@pytest.mark.parametrize(
    ("method", "path"),
    [("GET", "/api/claims/{}"), ("POST", "/api/claims/{}/approve")],
    ids=["get", "approve"],
)
def test_an_id_that_no_claim_can_have_is_404_not_500(claim_id, method, path, api_as, manager):
    resp = api_as(manager).client.request(method, path.format(claim_id))

    assert error_of(resp) == (404, "not_found")
