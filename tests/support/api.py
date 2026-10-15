"""A thin client for the expenses JSON API.

Every method returns the raw ``httpx.Response`` so a test can assert on the
status code, headers and body itself. No method raises on an error status.
``expect_ok(resp)`` is the one helper that asserts: use it for a setup step
that must succeed, so a broken step fails with the request and the reply.

    api = Api(base_url, erin)        # erin is a builders.User or a username
    resp = api.create_claim(claim_body(amount="75.00"))
    assert resp.status_code == 201

Prefer the ``api_as`` fixture, which binds the base URL and closes the client.
"""

from __future__ import annotations

from typing import Any, Protocol

import httpx


class HasUsername(Protocol):
    """Anything with a ``username``, such as ``builders.User``."""

    username: str


def expect_ok(resp: httpx.Response) -> httpx.Response:
    """Assert a 200 and return the response. The failure names the method, path and body."""
    request = resp.request
    assert resp.status_code == 200, (
        f"{request.method} {request.url.path} answered {resp.status_code}: {resp.text}"
    )
    return resp


def username_of(user: HasUsername | str | None) -> str | None:
    """Return the username of a User, or the string itself."""
    if user is None or isinstance(user, str):
        return user
    return user.username


class Api:
    """HTTP client signed in as one user through the ``X-User`` header.

    Pass ``None`` as the user for an anonymous client (for 401 tests).
    """

    def __init__(
        self, base_url: str, user: HasUsername | str | None, *, timeout: float = 10.0
    ) -> None:
        self.username = username_of(user)
        headers = {"X-User": self.username} if self.username else {}
        self.client = httpx.Client(base_url=base_url, headers=headers, timeout=timeout)

    def __repr__(self) -> str:
        return f"Api({str(self.client.base_url)!r}, {self.username!r})"

    def close(self) -> None:
        self.client.close()

    # Raw access, for requests the named methods do not cover (bad bodies, odd headers).

    def get(self, path: str, **kwargs: Any) -> httpx.Response:
        return self.client.get(path, **kwargs)

    def post(self, path: str, **kwargs: Any) -> httpx.Response:
        return self.client.post(path, **kwargs)

    def health(self) -> httpx.Response:
        return self.client.get("/health")

    def me(self) -> httpx.Response:
        return self.client.get("/api/me")

    def create_claim(self, body: Any) -> httpx.Response:
        """POST /api/claims with ``body`` as JSON. See ``builders.claim_body`` for a valid one."""
        return self.client.post("/api/claims", json=body)

    def list_claims(self, status: str | None = None) -> httpx.Response:
        """GET /api/claims, optionally with ``?status=``."""
        params = {"status": status} if status is not None else None
        return self.client.get("/api/claims", params=params)

    def get_claim(self, claim_id: int) -> httpx.Response:
        return self.client.get(f"/api/claims/{claim_id}")

    def approve(self, claim_id: int) -> httpx.Response:
        return self.client.post(f"/api/claims/{claim_id}/approve")

    def reject(self, claim_id: int, note: str | None = None) -> httpx.Response:
        """POST /api/claims/{id}/reject with ``{"note": note}``, or an empty object when None."""
        body = {} if note is None else {"note": note}
        return self.client.post(f"/api/claims/{claim_id}/reject", json=body)

    def pay(self, claim_id: int) -> httpx.Response:
        return self.client.post(f"/api/claims/{claim_id}/pay")

    def summary(self) -> httpx.Response:
        return self.client.get("/api/summary")

    def export_csv(self) -> httpx.Response:
        """GET /api/export.csv (finance only). The body is ``resp.text``."""
        return self.client.get("/api/export.csv")
