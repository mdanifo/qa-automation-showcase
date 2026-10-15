"""Fixtures for the CSV export layer.

The export covers every approved and paid claim in the database, and the
database is shared with the rest of the suite, so tests pick their own rows
out of it by claim id. Claims are written with ``insert_claim``: the export
reads data, and its tests should not fail because approve or pay broke.
"""

from __future__ import annotations

import csv
import io
from collections.abc import Callable
from typing import Any

import pytest

from tests.support import Api, User

ExportRow = dict[str, str]


@pytest.fixture
def finance_api(api_as, finance: User) -> Api:
    """An API client signed in as a fresh finance user."""
    return api_as(finance)


@pytest.fixture
def download_export(finance_api: Api) -> Callable[[], list[ExportRow]]:
    """``download_export()`` fetches the whole export as finance, rows keyed by the header."""

    def download() -> list[ExportRow]:
        resp = finance_api.export_csv()
        assert resp.status_code == 200, resp.text
        return list(csv.DictReader(io.StringIO(resp.text, newline="")))

    return download


@pytest.fixture
def exported(download_export: Callable[[], list[ExportRow]]) -> Callable[..., list[ExportRow]]:
    """``exported(claim, ...)`` fetches the export and returns only these claims' rows.

    Rows keep the export's order. A claim the export left out has no row.
    """

    def rows_for(*claims: dict[str, Any]) -> list[ExportRow]:
        wanted = {str(claim["id"]) for claim in claims}
        return [row for row in download_export() if row["id"] in wanted]

    return rows_for


@pytest.fixture
def export_row(exported: Callable[..., list[ExportRow]]) -> Callable[[dict[str, Any]], ExportRow]:
    """``export_row(claim)`` returns the claim's only export row. Fails on none or several."""

    def only_row(claim: dict[str, Any]) -> ExportRow:
        rows = exported(claim)
        assert len(rows) == 1, f"claim {claim['id']} has {len(rows)} rows in the export: {rows}"
        return rows[0]

    return only_row
