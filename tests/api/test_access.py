"""Sign-in: who the caller is, and what happens without a known user.

Sign-in is an X-User header or the ``user`` cookie the login page sets. Any
endpoint called without one, or with a name that is not a user, is a 401, and
the login form sets no cookie for a name that is not a user.
"""

from __future__ import annotations

import pytest

from tests.api.expect import error_of

EVERY_API_ENDPOINT = [
    ("GET", "/api/me"),
    ("GET", "/api/claims"),
    ("POST", "/api/claims"),
    ("GET", "/api/claims/1"),
    ("POST", "/api/claims/1/approve"),
    ("POST", "/api/claims/1/reject"),
    ("POST", "/api/claims/1/pay"),
    ("GET", "/api/summary"),
    ("GET", "/api/export.csv"),
]


@pytest.mark.parametrize(("method", "path"), EVERY_API_ENDPOINT)
def test_every_endpoint_refuses_a_caller_who_is_not_signed_in(method, path, api_as):
    resp = api_as(None).client.request(method, path)

    assert error_of(resp) == (401, "unauthenticated")


@pytest.mark.parametrize(("method", "path"), EVERY_API_ENDPOINT)
def test_every_endpoint_refuses_a_username_that_does_not_exist(method, path, api_as):
    resp = api_as("nobody-by-this-name").client.request(method, path)

    assert error_of(resp) == (401, "unauthenticated")


@pytest.mark.parametrize("role", ["employee", "manager", "finance"])
def test_me_returns_the_signed_in_user(role, make_user, api_as):
    user = make_user(role, display_name=f"Shown As {role.capitalize()}")

    resp = api_as(user).me()

    assert resp.status_code == 200
    assert resp.json() == {
        "username": user.username,
        "displayName": f"Shown As {role.capitalize()}",
        "role": role,
    }


def test_the_user_cookie_signs_in_without_a_header(api_as, employee):
    api = api_as(None)
    api.client.cookies.set("user", employee.username)

    resp = api.me()

    assert (resp.status_code, resp.json()["username"]) == (200, employee.username)


def test_a_cookie_naming_an_unknown_user_is_refused(api_as):
    api = api_as(None)
    api.client.cookies.set("user", "nobody-by-this-name")

    assert error_of(api.me()) == (401, "unauthenticated")


@pytest.mark.catches("login-trusts-the-form")
def test_the_sign_in_form_refuses_a_name_that_is_not_a_user(api_as):
    resp = api_as(None).post("/login", data={"user": "nobody-by-this-name"})

    assert (resp.status_code, resp.headers.get("set-cookie")) == (400, None)
    assert "Pick a user from the list." in resp.text
