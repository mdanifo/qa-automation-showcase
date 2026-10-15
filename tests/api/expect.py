"""Readers that turn a response into a value worth comparing, so each assertion is one line.

    assert error_of(resp) == (403, "forbidden")
    assert claim_ids(resp) == [first["id"], second["id"]]

A wrong answer shows up as a plain diff, for example ``(200, None) != (403,
"forbidden")`` when a request that should have been refused succeeded.
"""

from __future__ import annotations

import httpx


def error_of(resp: httpx.Response) -> tuple[int, str | None]:
    """``(status code, error code)``. The error code is None when the body has none."""
    return resp.status_code, resp.json().get("error")


def claim_ids(resp: httpx.Response) -> list[int]:
    """The claim ids in a ``GET /api/claims`` response, in the order returned."""
    return [claim["id"] for claim in resp.json()["claims"]]


def status_of(resp: httpx.Response) -> tuple[int, str | None]:
    """``(status code, claim status)`` of a claim response."""
    return resp.status_code, resp.json().get("status")
