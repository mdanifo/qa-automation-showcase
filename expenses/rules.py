"""Pure business rules: parsing, limits, mileage, dates, transitions and visibility.

Nothing here touches the database or HTTP, so every rule can be unit tested
directly. Money is Decimal or integer cents, never float.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal

from expenses import bugs

STATUSES = ("submitted", "approved", "rejected", "paid")

CATEGORY_LIMITS: dict[str, Decimal] = {
    "meals": Decimal("75.00"),
    "lodging": Decimal("300.00"),
    "travel": Decimal("1500.00"),
    "software": Decimal("500.00"),
    "other": Decimal("250.00"),
    "mileage": Decimal("500.00"),
}
CATEGORIES = tuple(CATEGORY_LIMITS)
CATEGORY_LABELS = {name: name.capitalize() for name in CATEGORIES}

MILEAGE_RATE = Decimal("0.67")
MAX_MILES = Decimal("1000")
MAX_AGE_DAYS = 90
TITLE_MAX = 80
NOTE_MAX = 500

CENT = Decimal("0.01")
_AMOUNT = re.compile(r"[0-9]+(\.[0-9]{1,2})?")
_MILES = re.compile(r"[0-9]+(\.[0-9])?")
_ISO_DATE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")


class ClaimError(Exception):
    """A rule violation. ``status`` and ``code`` become the HTTP error response."""

    status = 400
    code = "bad_request"

    def __init__(self, detail: str) -> None:
        super().__init__(detail)
        self.detail = detail


class ValidationError(ClaimError):
    """Bad input: 422 ``validation``."""

    status = 422
    code = "validation"


class Forbidden(ClaimError):
    """Wrong role, or acting on your own claim: 403 ``forbidden``."""

    status = 403
    code = "forbidden"


class InvalidTransition(ClaimError):
    """The claim is in the wrong status for this action: 409 ``invalid_transition``."""

    status = 409
    code = "invalid_transition"


class NotFound(ClaimError):
    """No such claim, or one the caller may not see: 404 ``not_found``."""

    status = 404
    code = "not_found"


class Unauthenticated(ClaimError):
    """Missing or unknown user: 401 ``unauthenticated``."""

    status = 401
    code = "unauthenticated"


@dataclass(frozen=True)
class NewClaim:
    """A claim that passed every submission rule, ready to store."""

    title: str
    category: str
    amount_cents: int
    miles: Decimal | None
    expense_date: date


def today_utc() -> date:
    """Today's date in UTC. Every date rule is measured from this."""
    return datetime.now(UTC).date()


def format_cents(cents: int) -> str:
    """Format integer cents as a plain decimal string with two places: 4250 -> "42.50"."""
    return str((Decimal(cents) / 100).quantize(CENT))


def limit_cents(category: str) -> int:
    """The per-claim limit for a category, in cents."""
    return int(CATEGORY_LIMITS[category] * 100)


def within_limit(amount_cents: int, category: str) -> bool:
    """True when the amount is at or under the category limit (the limit itself is allowed)."""
    limit = limit_cents(category)
    if bugs.active("limit-off-by-one"):
        # SEEDED BUG limit-off-by-one: strict comparison rejects the limit itself.
        return amount_cents < limit
    return amount_cents <= limit


def parse_amount(text: object) -> int:
    """Parse an amount string such as "42.50" into cents. Rejects floats, signs and zero."""
    if not isinstance(text, str):
        raise ValidationError('The amount must be a string, like "42.50", not a number.')
    if not _AMOUNT.fullmatch(text):
        raise ValidationError("The amount must be dollars with up to two decimals, like 42.50.")
    cents = int(Decimal(text) * 100)
    if cents <= 0:
        raise ValidationError("The amount must be greater than zero.")
    return cents


def parse_miles(text: object) -> Decimal:
    """Parse a miles string with at most one decimal place, above 0 and at most 1000."""
    if not isinstance(text, str) or not _MILES.fullmatch(text):
        raise ValidationError('Miles must be a number with at most one decimal, like "13.5".')
    miles = Decimal(text)
    if miles <= 0:
        raise ValidationError("Miles must be greater than zero.")
    if miles > MAX_MILES:
        raise ValidationError(f"A single claim can cover at most {MAX_MILES} miles.")
    return miles


def mileage_cents(miles: Decimal) -> int:
    """Mileage pay in cents: miles x 0.67, rounded half up to the cent (13.5 -> 905)."""
    if bugs.active("mileage-float-rounding"):
        # SEEDED BUG mileage-float-rounding: float math and round() lose the half cent.
        return round(round(float(miles) * float(MILEAGE_RATE), 2) * 100)
    amount = (miles * MILEAGE_RATE).quantize(CENT, rounding=ROUND_HALF_UP)
    return int(amount * 100)


def parse_expense_date(text: object, today: date | None = None) -> date:
    """Parse a YYYY-MM-DD date that is not after today and at most 90 days before it."""
    if not isinstance(text, str) or not _ISO_DATE.fullmatch(text):
        raise ValidationError("The expense date must be a date in YYYY-MM-DD form.")
    try:
        value = date.fromisoformat(text)
    except ValueError as exc:
        raise ValidationError("The expense date is not a real calendar date.") from exc
    today = today or today_utc()
    latest = today
    if bugs.active("future-date"):
        # SEEDED BUG future-date: a day of slack "for time zones" lets tomorrow through.
        latest = today + timedelta(days=1)
    if value > latest:
        raise ValidationError("The expense date cannot be in the future.")
    if value < today - timedelta(days=MAX_AGE_DAYS):
        raise ValidationError(f"The expense date cannot be more than {MAX_AGE_DAYS} days ago.")
    return value


def clean_title(text: object) -> str:
    """Strip a title and require 1 to 80 characters."""
    if not isinstance(text, str):
        raise ValidationError("A title is required.")
    title = text.strip()
    if not title:
        raise ValidationError("A title is required.")
    if len(title) > TITLE_MAX:
        raise ValidationError(f"The title can be at most {TITLE_MAX} characters.")
    return title


def clean_note(text: object) -> str:
    """Strip a rejection note and require it to be non-blank and at most 500 characters."""
    if text is None:
        text = ""
    if not isinstance(text, str):
        raise ValidationError("The rejection reason must be text.")
    note = text.strip()
    if not note:
        if bugs.active("reject-without-note"):
            # SEEDED BUG reject-without-note: a blank reason is returned, not refused.
            return note
        raise ValidationError("A rejection needs a reason.")
    if len(note) > NOTE_MAX:
        raise ValidationError(f"The reason can be at most {NOTE_MAX} characters.")
    return note


def parse_status_filter(text: str | None) -> str | None:
    """Validate the optional ``?status=`` filter. An empty value means no filter."""
    if not text:
        return None
    if text not in STATUSES:
        raise ValidationError(f"status must be one of: {', '.join(STATUSES)}.")
    return text


def validate_new_claim(data: object, today: date | None = None) -> NewClaim:
    """Check a submission (API field names) and return the claim to store.

    Mileage claims send ``miles`` and no ``amount``; every other category sends
    ``amount`` and no ``miles``. ``None`` counts as absent.
    """
    if not isinstance(data, Mapping):
        raise ValidationError("The request body must be a JSON object.")
    title = clean_title(data.get("title"))
    category = data.get("category")
    if not isinstance(category, str) or category not in CATEGORY_LIMITS:
        raise ValidationError(f"The category must be one of: {', '.join(CATEGORIES)}.")
    amount_text = data.get("amount")
    miles_text = data.get("miles")
    miles: Decimal | None = None
    if category == "mileage":
        if amount_text is not None:
            raise ValidationError("A mileage claim sends miles, not an amount.")
        if miles_text is None:
            raise ValidationError("A mileage claim needs the number of miles.")
        miles = parse_miles(miles_text)
        cents = mileage_cents(miles)
    else:
        if miles_text is not None:
            raise ValidationError("Miles are only for mileage claims.")
        if amount_text is None:
            raise ValidationError("An amount is required.")
        cents = parse_amount(amount_text)
    if not within_limit(cents, category):
        limit = format_cents(limit_cents(category))
        raise ValidationError(f"{CATEGORY_LABELS[category]} claims are limited to ${limit} each.")
    expense_date = parse_expense_date(data.get("expenseDate"), today)
    return NewClaim(title, category, cents, miles, expense_date)


def check_approve(*, actor: str, role: str, owner: str, status: str) -> None:
    """Allow approve only for a manager, on someone else's claim, while it is submitted."""
    if role != "manager":
        raise Forbidden("Only a manager can approve a claim.")
    own_claim = actor == owner
    if bugs.active("self-approval"):
        # SEEDED BUG self-approval: approve skips the owner check.
        own_claim = False
    if own_claim:
        raise Forbidden("You cannot approve your own claim.")
    if status != "submitted":
        raise InvalidTransition(f"Only a submitted claim can be approved. This one is {status}.")


def check_reject(*, actor: str, role: str, owner: str, status: str, note: object) -> str:
    """Allow reject on the same terms as approve, with a reason. Returns the cleaned note."""
    if role != "manager":
        raise Forbidden("Only a manager can reject a claim.")
    if actor == owner:
        raise Forbidden("You cannot reject your own claim.")
    if status != "submitted":
        raise InvalidTransition(f"Only a submitted claim can be rejected. This one is {status}.")
    return clean_note(note)


def check_pay(*, role: str, status: str) -> None:
    """Allow pay only for finance, on an approved claim."""
    if role != "finance":
        raise Forbidden("Only finance can pay a claim.")
    payable = status == "approved"
    if bugs.active("pay-unapproved"):
        # SEEDED BUG pay-unapproved: the check only guards against paying twice.
        payable = status != "paid"
    if not payable:
        raise InvalidTransition(f"Only an approved claim can be paid. This one is {status}.")


def can_view(*, viewer: str, role: str, owner: str) -> bool:
    """Whether a user may open one claim: managers and finance any, employees their own."""
    return role in ("manager", "finance") or viewer == owner


def visible_in_list(*, viewer: str, role: str, owner: str, status: str) -> bool:
    """Whether a claim appears in a user's claim list.

    Employees see their own. Managers see their own plus every submitted claim
    from others. Finance sees approved and paid claims.
    """
    if role == "employee":
        return owner == viewer
    if role == "manager":
        return owner == viewer or status == "submitted"
    if role == "finance":
        return status in ("approved", "paid")
    return False
