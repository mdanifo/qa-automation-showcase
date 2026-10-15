"""Command line options for the suite.

They live here, at the repository root, because pytest reads options before
it loads tests/conftest.py, and it only finds that file early when the
command line points into tests/. A root conftest is always found, so
``pytest --write-catches reports/catches.json`` works even after the file
exists. Everything else is in tests/conftest.py.
"""

from __future__ import annotations

import pytest


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--write-catches",
        metavar="PATH",
        default=None,
        help="write {bug: [nodeid, ...]} as JSON after collection (works with --collect-only)",
    )
