"""Test data: users, claim bodies, claims in any state, read-back helpers and cleanup.

Every test makes its own users (the ``make_user`` fixture) and its own claims,
so tests never share rows and the suite is safe under ``pytest -n auto``
against one database. Whatever a test creates is deleted afterwards by
``Cleanup``: the claims its users own first, then the users.

Three ways to get a claim:

* ``submit_claim(api, ...)`` goes through the API, the way a user would. Use it
  when submitting is part of what the test checks, or is harmless setup.
* ``insert_claim(db, owner, status=...)`` writes the row straight to the
  database in the state the test needs. A test of *pay* should not depend on
  *approve* working: when approve breaks, only the approve tests should fail.
  It writes no ``claim_events`` rows unless ``with_events=True``, and it does
  not apply business rules, so it can also build rows the API would refuse.
* ``insert_claim_with_history(db, make_user, owner, status)`` is
  ``insert_claim`` with the rest of a real claim's past: a fresh manager
  decided it, a fresh finance user paid it, and its claim_events are written.
  Use it when a test reads the whole row or the audit trail.

Expected values here (such as the mileage amount in ``insert_claim``) are
computed in this module, independently of ``expenses.rules``, so a bug in the
app cannot leak into the test's idea of the right answer.
"""

from __future__ import annotations

import secrets
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

import psycopg

from tests.support.api import Api, HasUsername, username_of
from tests.support.dates import days_ago

Db = psycopg.Connection[dict[str, Any]]

ROLES = ("employee", "manager", "finance")
STATUSES = ("submitted", "approved", "rejected", "paid")
DECIDED = ("approved", "rejected", "paid")
MISSING_CLAIM_ID = 2**31 - 1
"""The largest id a claim can have. Ids count up from 1, so no claim has this one."""
MILEAGE_RATE = Decimal("0.67")

DEFAULT_TITLE = "Team lunch"
DEFAULT_AMOUNT = "20.00"
DEFAULT_MILES = "10.0"
DEFAULT_REJECT_NOTE = "Not a business expense."


class _Omit:
    def __repr__(self) -> str:
        return "OMIT"


OMIT: Any = _Omit()
"""Pass as an override to leave a key out: ``claim_body(title=OMIT)``."""


@dataclass(frozen=True)
class User:
    """A user created for one test. ``str(user)`` is the username."""

    username: str
    display_name: str
    role: str

    def __str__(self) -> str:
        return self.username


class Cleanup:
    """Remembers what a test created and deletes it in ``run()``.

    The ``cleanup`` fixture calls ``run()`` after every test. Users from
    ``make_user`` are registered automatically, and every claim they own goes
    with them (and each claim's claim_events, by cascade).
    """

    def __init__(self, db: Db) -> None:
        self._db = db
        self.usernames: list[str] = []

    def user(self, user: HasUsername | str) -> None:
        """Delete this user, and every claim they own, after the test."""
        name = username_of(user)
        if name and name not in self.usernames:
            self.usernames.append(name)

    def run(self) -> None:
        """Delete the registered users' claims, then the users. Safe to call more than once."""
        if self.usernames:
            self._db.execute("DELETE FROM claims WHERE owner = ANY(%s::text[])", (self.usernames,))
            self._db.execute(
                "DELETE FROM users WHERE username = ANY(%s::text[])", (self.usernames,)
            )
        self.usernames.clear()


class UserFactory:
    """Inserts a fresh, uniquely named user and registers it for cleanup.

    The ``make_user`` fixture is one of these: ``maya = make_user("manager")``.
    Usernames look like ``manager-3fa2b1c9``.
    """

    def __init__(self, db: Db, cleanup: Cleanup) -> None:
        self._db = db
        self._cleanup = cleanup

    def __call__(self, role: str, display_name: str | None = None) -> User:
        """Create a user with ``role`` (employee, manager or finance)."""
        if role not in ROLES:
            raise ValueError(f"role must be one of {ROLES}, not {role!r}")
        suffix = secrets.token_hex(4)
        username = f"{role}-{suffix}"
        name = display_name or f"Test {role.capitalize()} {suffix}"
        self._db.execute(
            "INSERT INTO users (username, display_name, role) VALUES (%s, %s, %s)",
            (username, name, role),
        )
        self._cleanup.user(username)
        return User(username, name, role)


def claim_body(**overrides: Any) -> dict[str, Any]:
    """A valid ``POST /api/claims`` body: meals, "20.00", dated yesterday (UTC).

    Keys use the API's names (``expenseDate``), and ``date`` values become ISO
    strings. ``category="mileage"`` swaps the default amount for
    ``miles="10.0"``. Pass ``OMIT`` to drop a key.

        claim_body(amount="75.00")
        claim_body(category="mileage", miles="13.5")
        claim_body(expenseDate=days_ahead(1))
        claim_body(title=OMIT)
    """
    category = overrides.get("category", "meals")
    body: dict[str, Any] = {
        "title": DEFAULT_TITLE,
        "category": category,
        "expenseDate": days_ago(1).isoformat(),
    }
    if category == "mileage":
        body["miles"] = DEFAULT_MILES
    else:
        body["amount"] = DEFAULT_AMOUNT
    for key, value in overrides.items():
        if value is OMIT:
            body.pop(key, None)
        else:
            body[key] = value.isoformat() if isinstance(value, date) else value
    return body


def submit_claim(api: Api, **overrides: Any) -> dict[str, Any]:
    """Submit ``claim_body(**overrides)`` through the API and return the created claim JSON.

    Fails the test with the response body when the API does not answer 201,
    so use ``api.create_claim(claim_body(...))`` when the response itself is
    what you are testing.
    """
    resp = api.create_claim(claim_body(**overrides))
    assert resp.status_code == 201, f"submit_claim setup failed: {resp.status_code} {resp.text}"
    return resp.json()


_INSERTABLE = {
    "title",
    "category",
    "amount",
    "amount_cents",
    "miles",
    "expense_date",
    "submitted_at",
    "decided_by",
    "decided_at",
    "decision_note",
    "paid_by",
    "paid_at",
}


def _cents(amount: str | Decimal | int | float) -> int:
    value = Decimal(str(amount))
    return int((value * 100).to_integral_value(rounding=ROUND_HALF_UP))


def mileage_cents(miles: str | Decimal) -> int:
    """The right mileage pay in cents (miles x 0.67, half up), computed independently of the app."""
    amount = (Decimal(str(miles)) * MILEAGE_RATE).quantize(Decimal("0.01"), ROUND_HALF_UP)
    return int(amount * 100)


def insert_claim(
    db: Db,
    owner: HasUsername | str,
    status: str = "submitted",
    *,
    with_events: bool = False,
    **fields: Any,
) -> dict[str, Any]:
    """Write a claim row directly in ``status`` and return it (database column names).

    Defaults: meals, 20.00, dated yesterday. A decided status gets
    ``decided_at`` now; rejected gets a note; paid gets ``paid_at`` now. Who
    decided or paid is NULL unless you pass ``decided_by`` / ``paid_by`` (a
    User or username). Any column can be overridden by keyword, and
    ``amount="42.50"`` is accepted in place of ``amount_cents=4250``. A
    mileage claim without an amount is paid for ``miles`` (default "10.0").

    No business rule is applied, so this can build rows the API would refuse.
    With ``with_events=True`` it also writes the claim_events history for the
    status (submitted, then approved or rejected, then paid).
    """
    unknown = set(fields) - _INSERTABLE
    if unknown:
        raise TypeError(f"insert_claim got unknown fields: {sorted(unknown)}")
    if status not in STATUSES:
        raise ValueError(f"status must be one of {STATUSES}, not {status!r}")
    owner_name = username_of(owner)
    category = fields.pop("category", "meals")
    miles = fields.pop("miles", None)
    amount = fields.pop("amount", None)
    amount_cents = fields.pop("amount_cents", None)
    if amount_cents is None:
        if amount is not None:
            amount_cents = _cents(amount)
        elif category == "mileage":
            miles = DEFAULT_MILES if miles is None else miles
            amount_cents = mileage_cents(miles)
        else:
            amount_cents = _cents(DEFAULT_AMOUNT)
    now = datetime.now(UTC)
    row: dict[str, Any] = {
        "owner": owner_name,
        "title": fields.pop("title", DEFAULT_TITLE),
        "category": category,
        "amount_cents": amount_cents,
        "miles": None if miles is None else Decimal(str(miles)),
        "expense_date": fields.pop("expense_date", days_ago(1)),
        "status": status,
    }
    if status != "submitted":
        row["decided_at"] = now
    if status == "rejected":
        row["decision_note"] = DEFAULT_REJECT_NOTE
    if status == "paid":
        row["paid_at"] = now
    for key in ("decided_by", "paid_by"):
        if key in fields:
            fields[key] = username_of(fields[key])
    row.update(fields)

    columns = ", ".join(row)
    placeholders = ", ".join(["%s"] * len(row))
    inserted = db.execute(
        f"INSERT INTO claims ({columns}) VALUES ({placeholders}) RETURNING *",
        tuple(row.values()),
    ).fetchone()
    assert inserted is not None
    if with_events:
        _write_history(db, inserted)
    return inserted


def insert_claim_with_history(
    db: Db, make_user: UserFactory, owner: HasUsername | str, status: str, **fields: Any
) -> dict[str, Any]:
    """``insert_claim`` in ``status``, filled in the way the app would have left it.

    A fresh manager decided it (approved, rejected, paid), a fresh finance
    user paid it (paid), and its claim_events history is written.
    """
    people: dict[str, User] = {}
    if status in DECIDED:
        people["decided_by"] = make_user("manager")
    if status == "paid":
        people["paid_by"] = make_user("finance")
    return insert_claim(db, owner, status, with_events=True, **{**people, **fields})


def _write_history(db: Db, claim: dict[str, Any]) -> None:
    status = claim["status"]
    events = [(claim["owner"], "submitted")]
    if status in ("approved", "paid"):
        events.append((claim["decided_by"] or "fixture", "approved"))
    if status == "rejected":
        events.append((claim["decided_by"] or "fixture", "rejected"))
    if status == "paid":
        events.append((claim["paid_by"] or "fixture", "paid"))
    for actor, action in events:
        db.execute(
            "INSERT INTO claim_events (claim_id, actor, action) VALUES (%s, %s, %s)",
            (claim["id"], actor, action),
        )


def claim_row(db: Db, claim_id: int) -> dict[str, Any] | None:
    """The claim's row as stored (column names), or None when it does not exist."""
    return db.execute("SELECT * FROM claims WHERE id = %s", (claim_id,)).fetchone()


def claim_events(db: Db, claim_id: int) -> list[dict[str, Any]]:
    """The claim's claim_events rows, oldest first."""
    return db.execute(
        "SELECT * FROM claim_events WHERE claim_id = %s ORDER BY id", (claim_id,)
    ).fetchall()


def user_exists(db: Db, user: HasUsername | str) -> bool:
    """Whether a users row exists for this user."""
    row = db.execute(
        "SELECT 1 AS found FROM users WHERE username = %s", (username_of(user),)
    ).fetchone()
    return row is not None
