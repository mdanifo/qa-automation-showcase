"""Only finance can download the export.

The 401 for a caller who is not signed in is checked for every endpoint,
the export included, in tests/api/test_access.py.
"""

from __future__ import annotations

import pytest

from tests.api.expect import error_of


@pytest.mark.parametrize("role", ["employee", "manager"])
def test_export_is_refused_to_roles_other_than_finance(make_user, api_as, role):
    resp = api_as(make_user(role)).export_csv()

    assert error_of(resp) == (403, "forbidden")
