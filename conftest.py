"""Command line options for the suite.

Registered here rather than in tests/conftest.py: pytest parses the command
line before it loads that file, and only loads it early when the command line
points into tests/. Everything else is in tests/conftest.py.
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
