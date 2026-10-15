"""Shared test support: the API client, test-data builders, cleanup and UTC dates.

Import from here in any layer:

    from tests.support import OMIT, Api, claim_body, days_ago, insert_claim, submit_claim

Fixtures that wire these up (``base_url``, ``db``, ``cleanup``, ``make_user``,
``api_as``, ``employee``, ``manager``, ``finance``) live in ``tests/conftest.py``.
"""

from tests.support.api import Api, expect_ok, username_of
from tests.support.builders import (
    DECIDED,
    MISSING_CLAIM_ID,
    OMIT,
    STATUSES,
    Cleanup,
    User,
    UserFactory,
    claim_body,
    claim_events,
    claim_row,
    insert_claim,
    insert_claim_with_history,
    mileage_cents,
    submit_claim,
    user_exists,
)
from tests.support.dates import FIXED_TODAY, FIXED_YESTERDAY, days_ago, days_ahead, today_utc

__all__ = [
    "DECIDED",
    "FIXED_TODAY",
    "FIXED_YESTERDAY",
    "MISSING_CLAIM_ID",
    "OMIT",
    "STATUSES",
    "Api",
    "Cleanup",
    "User",
    "UserFactory",
    "claim_body",
    "claim_events",
    "claim_row",
    "days_ago",
    "days_ahead",
    "expect_ok",
    "insert_claim",
    "insert_claim_with_history",
    "mileage_cents",
    "submit_claim",
    "today_utc",
    "user_exists",
    "username_of",
]
