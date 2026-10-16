"""Expense dates: ISO format, not after today, at most 90 days back, all measured in UTC."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta, timezone

import pytest

from expenses import rules
from tests.support import FIXED_TODAY

TODAY_IN_A_LEAP_YEAR = date(2024, 3, 1)
HAWAII = timezone(timedelta(hours=-10), "HST")


class FrozenClock:
    """Stands in for ``datetime`` inside rules, so "now" is one fixed instant.

    Asked for local time (``now()`` with no zone) it answers for UTC-10, as
    the real ``datetime.now()`` answers for the machine's zone. CI runners
    sit at UTC, where local and UTC dates agree and a local-time bug would
    hide; the fixed zone keeps the test meaningful there.
    """

    def __init__(self, instant: datetime, local_zone: timezone = HAWAII) -> None:
        self.instant = instant
        self.local_zone = local_zone

    def now(self, tz: timezone | None = None) -> datetime:
        if tz is None:
            return self.instant.astimezone(self.local_zone).replace(tzinfo=None)
        return self.instant.astimezone(tz)


@pytest.mark.parametrize(
    ("text", "parsed"),
    [
        pytest.param("2026-03-01", date(2026, 3, 1), id="today"),
        pytest.param("2026-02-28", date(2026, 2, 28), id="yesterday"),
        pytest.param("2025-12-02", date(2025, 12, 2), id="89-days-ago"),
        pytest.param("2025-12-01", date(2025, 12, 1), id="90-days-ago"),
    ],
)
def test_a_date_from_today_back_to_90_days_ago_is_accepted(text, parsed):
    assert rules.parse_expense_date(text, today=FIXED_TODAY) == parsed


@pytest.mark.parametrize(
    "text",
    [
        pytest.param("2026-03-02", id="tomorrow", marks=pytest.mark.catches("future-date")),
        pytest.param("2026-03-03", id="day-after-tomorrow"),
        pytest.param("2027-03-01", id="next-year"),
    ],
)
def test_a_date_after_today_is_refused(text):
    with pytest.raises(rules.ValidationError, match="cannot be in the future"):
        rules.parse_expense_date(text, today=FIXED_TODAY)


@pytest.mark.parametrize(
    "text",
    [
        pytest.param("2025-11-30", id="91-days-ago"),
        pytest.param("2025-03-01", id="a-year-ago"),
    ],
)
def test_a_date_more_than_90_days_ago_is_refused(text):
    with pytest.raises(rules.ValidationError, match="more than 90 days ago"):
        rules.parse_expense_date(text, today=FIXED_TODAY)


def test_february_29_is_a_real_date_in_a_leap_year():
    assert rules.parse_expense_date("2024-02-29", today=TODAY_IN_A_LEAP_YEAR) == date(2024, 2, 29)


def test_the_90_day_window_counts_calendar_days_across_a_leap_day():
    """With a 29-day February, 90 days before 1 March 2024 is 2 December, not 1 December."""
    assert rules.parse_expense_date("2023-12-02", today=TODAY_IN_A_LEAP_YEAR) == date(2023, 12, 2)
    with pytest.raises(rules.ValidationError, match="more than 90 days ago"):
        rules.parse_expense_date("2023-12-01", today=TODAY_IN_A_LEAP_YEAR)


@pytest.mark.parametrize(
    "value",
    [
        pytest.param("2026-3-1", id="no-zero-padding"),
        pytest.param("2026/03/01", id="slashes"),
        pytest.param("01-03-2026", id="day-first"),
        pytest.param("20260301", id="no-separators"),
        pytest.param("2026-03-01T00:00:00", id="timestamp"),
        pytest.param(" 2026-03-01", id="leading-space"),
        pytest.param("", id="empty"),
        pytest.param(None, id="none"),
        pytest.param(20260301, id="number"),
    ],
)
def test_a_date_not_in_yyyy_mm_dd_form_is_refused(value):
    with pytest.raises(rules.ValidationError, match="YYYY-MM-DD"):
        rules.parse_expense_date(value, today=FIXED_TODAY)


@pytest.mark.parametrize(
    "text",
    [
        pytest.param("2026-02-29", id="feb-29-in-a-common-year"),
        pytest.param("2026-02-30", id="feb-30"),
        pytest.param("2026-04-31", id="april-31"),
        pytest.param("2026-13-01", id="month-13"),
        pytest.param("2026-00-10", id="month-0"),
    ],
)
def test_a_well_formed_date_that_is_not_on_the_calendar_is_refused(text):
    with pytest.raises(rules.ValidationError, match="not a real calendar date"):
        rules.parse_expense_date(text, today=FIXED_TODAY)


def test_today_is_the_utc_calendar_date(monkeypatch):
    """At 01:30 UTC on 2 March it is still 1 March across the Americas. The rules use 2 March.

    ``datetime.now().date()`` would give 1 March here on any machine, because
    the frozen clock's local zone is UTC-10.
    """
    monkeypatch.setattr(rules, "datetime", FrozenClock(datetime(2026, 3, 2, 1, 30, tzinfo=UTC)))

    assert rules.today_utc() == date(2026, 3, 2)


@pytest.mark.catches("future-date")
def test_by_default_tomorrow_is_measured_from_the_utc_date(monkeypatch):
    monkeypatch.setattr(rules, "today_utc", lambda: FIXED_TODAY)

    with pytest.raises(rules.ValidationError, match="cannot be in the future"):
        rules.parse_expense_date("2026-03-02")


def test_by_default_the_utc_date_itself_is_accepted(monkeypatch):
    monkeypatch.setattr(rules, "today_utc", lambda: FIXED_TODAY)

    assert rules.parse_expense_date("2026-03-01") == FIXED_TODAY
