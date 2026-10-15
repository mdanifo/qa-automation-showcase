"""Dates measured the way the app measures them: in UTC.

The app's "today" is ``datetime.now(UTC).date()``. Use these helpers rather
than ``date.today()``, which is local time and disagrees with the server for
part of every day.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

FIXED_TODAY = date(2026, 3, 1)
"""The "today" unit tests pass to the rules as ``today=``, so no result depends on the clock."""
FIXED_YESTERDAY = FIXED_TODAY - timedelta(days=1)


def today_utc() -> date:
    """Today's date in UTC, the same formula the app uses."""
    return datetime.now(UTC).date()


def days_ago(n: int) -> date:
    """The UTC date ``n`` days before today. ``days_ago(90)`` is the oldest allowed expense."""
    return today_utc() - timedelta(days=n)


def days_ahead(n: int) -> date:
    """The UTC date ``n`` days after today. ``days_ahead(1)`` is tomorrow."""
    return today_utc() + timedelta(days=n)
