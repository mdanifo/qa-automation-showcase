"""Claim operations shared by the JSON API and the HTML pages.

Every state change writes its ``claim_events`` row in the same transaction.
"""

from __future__ import annotations

import csv
import io
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from expenses import bugs, db, rules

Claim = dict[str, Any]

MAX_ID = 2**31 - 1  # SERIAL is a 32-bit integer
EXPORT_COLUMNS = ("id", "owner", "category", "amount", "expense_date", "status", "paid_at")


@dataclass(frozen=True)
class User:
    """A signed-in user."""

    username: str
    display_name: str
    role: str


def get_user(username: str | None) -> User | None:
    """Look up a user by username. Returns None for a missing or unknown name."""
    if not username:
        return None
    with db.connect() as conn:
        row = conn.execute(
            "SELECT username, display_name, role FROM users WHERE username = %s", (username,)
        ).fetchone()
    return User(**row) if row else None


def list_users() -> list[User]:
    """Every user, for the sign-in list, ordered by role and then display name."""
    with db.connect() as conn:
        rows = conn.execute(
            "SELECT username, display_name, role FROM users ORDER BY role, display_name, username"
        ).fetchall()
    return [User(**row) for row in rows]


def _record_event(conn: db.Connection, claim_id: int, actor: str, action: str) -> None:
    conn.execute(
        "INSERT INTO claim_events (claim_id, actor, action) VALUES (%s, %s, %s)",
        (claim_id, actor, action),
    )


def _check_id(claim_id: int) -> None:
    """404 for an id no claim can have, before it reaches Postgres (which would overflow)."""
    if not 0 < claim_id <= MAX_ID:
        raise rules.NotFound(f"Claim {claim_id} does not exist.")


def _lock_claim(conn: db.Connection, claim_id: int) -> Claim:
    """Read the claim and hold its row lock until the transaction ends.

    A second request for the same claim waits here and then sees the new
    status, which gets it a 409 rather than a second decision or payment.
    """
    _check_id(claim_id)
    row = conn.execute("SELECT * FROM claims WHERE id = %s FOR UPDATE", (claim_id,)).fetchone()
    if row is None:
        raise rules.NotFound(f"Claim {claim_id} does not exist.")
    return row


def create_claim(actor: User, data: Mapping[str, object]) -> Claim:
    """Validate a submission and store it as a submitted claim owned by ``actor``."""
    new = rules.validate_new_claim(data)
    with db.connect() as conn:
        row = conn.execute(
            "INSERT INTO claims (owner, title, category, amount_cents, miles, expense_date)"
            " VALUES (%s, %s, %s, %s, %s, %s) RETURNING *",
            (
                actor.username,
                new.title,
                new.category,
                new.amount_cents,
                new.miles,
                new.expense_date,
            ),
        ).fetchone()
        assert row is not None
        _record_event(conn, row["id"], actor.username, "submitted")
    return row


def get_claim(actor: User, claim_id: int) -> Claim:
    """One claim. Employees get 404 for anyone else's claim; managers and finance see any."""
    _check_id(claim_id)
    with db.connect() as conn:
        row = conn.execute("SELECT * FROM claims WHERE id = %s", (claim_id,)).fetchone()
    if row is None or not rules.can_view(
        viewer=actor.username, role=actor.role, owner=row["owner"]
    ):
        raise rules.NotFound(f"Claim {claim_id} does not exist.")
    return row


def list_claims(actor: User, status: str | None = None) -> list[Claim]:
    """The claims ``actor`` may see in a list, ordered by id, optionally of one status.

    Filtered in Python with ``rules.visible_in_list`` rather than in SQL, to
    keep one copy of the rule. The table is small enough for that.
    """
    with db.connect() as conn:
        rows = conn.execute("SELECT * FROM claims ORDER BY id").fetchall()
    return [
        row
        for row in rows
        if rules.visible_in_list(
            viewer=actor.username, role=actor.role, owner=row["owner"], status=row["status"]
        )
        and (status is None or row["status"] == status)
    ]


def own_claims(actor: User) -> list[Claim]:
    """The claims ``actor`` submitted, newest first, for the dashboard."""
    with db.connect() as conn:
        return conn.execute(
            "SELECT * FROM claims WHERE owner = %s ORDER BY id DESC", (actor.username,)
        ).fetchall()


def awaiting_approval(actor: User) -> list[Claim]:
    """Submitted claims from other people, oldest first, with ``owner_name``. Managers only."""
    if actor.role != "manager":
        raise rules.Forbidden("Only managers can see approvals.")
    with db.connect() as conn:
        return conn.execute(
            "SELECT c.*, u.display_name AS owner_name FROM claims c"
            " JOIN users u ON u.username = c.owner"
            " WHERE c.status = 'submitted' AND c.owner <> %s ORDER BY c.id",
            (actor.username,),
        ).fetchall()


def awaiting_payment(actor: User) -> list[Claim]:
    """Approved claims, oldest first, with ``owner_name``. Finance only."""
    if actor.role != "finance":
        raise rules.Forbidden("Only finance can see payments.")
    with db.connect() as conn:
        return conn.execute(
            "SELECT c.*, u.display_name AS owner_name FROM claims c"
            " JOIN users u ON u.username = c.owner"
            " WHERE c.status = 'approved' ORDER BY c.id"
        ).fetchall()


def approve(actor: User, claim_id: int) -> Claim:
    """Approve a submitted claim as a manager who does not own it."""
    with db.connect() as conn:
        claim = _lock_claim(conn, claim_id)
        rules.check_approve(
            actor=actor.username, role=actor.role, owner=claim["owner"], status=claim["status"]
        )
        row = conn.execute(
            "UPDATE claims SET status = 'approved', decided_by = %s, decided_at = now()"
            " WHERE id = %s RETURNING *",
            (actor.username, claim_id),
        ).fetchone()
        _record_event(conn, claim_id, actor.username, "approved")
        if bugs.active("approval-not-saved"):
            # SEEDED BUG approval-not-saved: the work is rolled back, yet the reply says approved.
            conn.rollback()
    assert row is not None
    return row


def reject(actor: User, claim_id: int, note: object) -> Claim:
    """Reject a submitted claim as a manager who does not own it, with a reason."""
    with db.connect() as conn:
        claim = _lock_claim(conn, claim_id)
        clean = rules.check_reject(
            actor=actor.username,
            role=actor.role,
            owner=claim["owner"],
            status=claim["status"],
            note=note,
        )
        row = conn.execute(
            "UPDATE claims SET status = 'rejected', decided_by = %s, decided_at = now(),"
            " decision_note = %s WHERE id = %s RETURNING *",
            (actor.username, clean, claim_id),
        ).fetchone()
        _record_event(conn, claim_id, actor.username, "rejected")
    assert row is not None
    return row


def pay(actor: User, claim_id: int) -> Claim:
    """Mark an approved claim paid, as finance."""
    with db.connect() as conn:
        claim = _lock_claim(conn, claim_id)
        rules.check_pay(role=actor.role, status=claim["status"])
        row = conn.execute(
            "UPDATE claims SET status = 'paid', paid_by = %s, paid_at = now()"
            " WHERE id = %s RETURNING *",
            (actor.username, claim_id),
        ).fetchone()
        write_event = True
        if bugs.active("missing-audit-event"):
            # SEEDED BUG missing-audit-event: the payment path skips its audit row.
            write_event = False
        if write_event:
            _record_event(conn, claim_id, actor.username, "paid")
    assert row is not None
    return row


def summary_cents(actor: User) -> dict[str, int]:
    """Totals of ``actor``'s own claims in cents. Rejected claims count nowhere."""
    pending_statuses = ["submitted"]
    if bugs.active("pending-total-includes-rejected"):
        # SEEDED BUG pending-total-includes-rejected: "not approved or paid yet" takes in rejected.
        pending_statuses = ["submitted", "rejected"]
    with db.connect() as conn:
        row = conn.execute(
            "SELECT"
            " COALESCE(SUM(amount_cents) FILTER (WHERE status = ANY(%s)), 0) AS pending,"
            " COALESCE(SUM(amount_cents) FILTER (WHERE status = 'approved'), 0) AS approved,"
            " COALESCE(SUM(amount_cents) FILTER (WHERE status = 'paid'), 0) AS paid"
            " FROM claims WHERE owner = %s",
            (pending_statuses, actor.username),
        ).fetchone()
    assert row is not None
    return {key: int(row[key]) for key in ("pending", "approved", "paid")}


def _iso_timestamp(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.astimezone(UTC).isoformat(timespec="microseconds")


def export_csv(actor: User) -> str:
    """The finance export: every approved or paid claim, ordered by id. Finance only."""
    if actor.role != "finance":
        raise rules.Forbidden("Only finance can download the export.")
    with db.connect() as conn:
        rows = conn.execute(
            "SELECT * FROM claims WHERE status IN ('approved', 'paid') ORDER BY id"
        ).fetchall()
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(EXPORT_COLUMNS)
    for row in rows:
        amount = rules.format_cents(row["amount_cents"])
        if bugs.active("csv-amount-format"):
            # SEEDED BUG csv-amount-format: dividing to a float drops the trailing zero.
            amount = str(row["amount_cents"] / 100)
        writer.writerow(
            [
                row["id"],
                row["owner"],
                row["category"],
                amount,
                row["expense_date"].isoformat(),
                row["status"],
                _iso_timestamp(row["paid_at"]) or "",
            ]
        )
    return out.getvalue()


def claim_json(row: Claim) -> dict[str, Any]:
    """The API representation of a claim, with exactly the documented keys."""
    amount: str | float = rules.format_cents(row["amount_cents"])
    if bugs.active("amount-as-number"):
        # SEEDED BUG amount-as-number: the serializer hands back a float.
        amount = row["amount_cents"] / 100
    return {
        "id": row["id"],
        "owner": row["owner"],
        "title": row["title"],
        "category": row["category"],
        "amount": amount,
        "miles": None if row["miles"] is None else str(row["miles"]),
        "expenseDate": row["expense_date"].isoformat(),
        "status": row["status"],
        "submittedAt": _iso_timestamp(row["submitted_at"]),
        "decidedBy": row["decided_by"],
        "decidedAt": _iso_timestamp(row["decided_at"]),
        "decisionNote": row["decision_note"],
        "paidBy": row["paid_by"],
        "paidAt": _iso_timestamp(row["paid_at"]),
    }
