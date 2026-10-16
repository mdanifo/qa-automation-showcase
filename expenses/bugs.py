"""The seeded-bug catalog.

Each entry is a mistake behind one ``if bugs.active("<name>"):`` branch in the
app. ``SEEDED_BUG=<name>`` turns it on; unset or empty is the correct app. An
unknown value is an error rather than "no bug", so a typo in a bug name cannot
look like a clean run.
"""

from __future__ import annotations

import os

ENV_VAR = "SEEDED_BUG"

CATALOG: dict[str, str] = {
    "limit-off-by-one": "A claim for exactly the category limit is rejected.",
    "mileage-float-rounding": "Mileage is computed in float: 13.5 miles pays $9.04, not $9.05.",
    "self-approval": "A manager can approve their own claim.",
    "reject-without-note": "A claim can be rejected with a blank note.",
    "pay-unapproved": "Finance can pay a claim that was never approved.",
    "future-date": "An expense dated tomorrow is accepted.",
    "amount-as-number": 'The API returns amount as a JSON number (42.5), not the string "42.50".',
    "approval-not-saved": "Approve answers 200 with status approved but never commits it.",
    "missing-audit-event": "Paying a claim writes no claim_events row.",
    "pending-total-includes-rejected": "The pending total counts rejected claims.",
    "unescaped-title": "The dashboard renders claim titles as raw HTML.",
    "csv-amount-format": "The CSV export writes 42.5 instead of 42.50.",
    "control-chars-accepted": (
        "A title or reason with a NUL byte is accepted; Postgres then fails the request with a 500."
    ),
    "page-ignores-refusal": "A refused Approve, Reject or Pay from the pages reports success.",
    "login-trusts-the-form": "The sign-in form sets the cookie for any posted name, user or not.",
    "demo-seed-repeats": "The demo seed adds its sample claims again on every run.",
}


class UnknownBugError(ValueError):
    """Raised for a bug name that is not in CATALOG."""


def current() -> str | None:
    """Return the active seeded bug from the environment, or None.

    Read at call time, so a test process that sets SEEDED_BUG sees it too.
    Raises UnknownBugError when the value is not in CATALOG.
    """
    name = os.environ.get(ENV_VAR, "").strip()
    if not name:
        return None
    if name not in CATALOG:
        known = ", ".join(CATALOG)
        raise UnknownBugError(f"{ENV_VAR}={name!r} is not a known seeded bug. Known: {known}")
    return name


def active(name: str) -> bool:
    """Return True when ``name`` is the active seeded bug.

    Raises UnknownBugError when ``name`` is not in CATALOG (a typo in a branch)
    or when SEEDED_BUG holds an unknown value.
    """
    if name not in CATALOG:
        raise UnknownBugError(f"{name!r} is not in bugs.CATALOG")
    return current() == name
