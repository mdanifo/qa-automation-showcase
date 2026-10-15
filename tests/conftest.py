"""Fixtures and collection rules shared by every test layer.

Fixtures
    server / base_url   The app's base URL (session scope, one server per xdist
                        worker). Starts ``uvicorn expenses.main:app`` on a free
                        port with this process's environment, so it inherits
                        DATABASE_URL and SEEDED_BUG. Set BASE_URL (or pass
                        --base-url) to test a server that is already running.
                        ``base_url`` is also what pytest-playwright uses, so
                        ``page.goto("/login")`` works.
    db                  A psycopg connection (session scope, autocommit, rows
                        as dicts) with the schema applied.
    cleanup             A builders.Cleanup that deletes what the test created.
    make_user           ``make_user("manager")`` inserts a fresh user.
    employee, manager, finance
                        One fresh user of that role, for the common case.
    claim_in            ``claim_in("paid")`` writes a claim of ``employee``
                        straight into that status, decided and paid by fresh
                        users, with its claim_events history.
    api_as              ``api_as(user)`` returns an Api signed in as ``user``
                        (``None`` for anonymous) and closes it afterwards.

Collection rules
    * Tests get a layer marker from their directory: tests/api/... is ``api``.
    * ``@pytest.mark.catches("<bug>", ...)`` names the seeded bugs a test is
      meant to catch. An unknown name stops the run before any test executes.
    * ``--write-catches=PATH`` writes ``{bug: [nodeid, ...]}`` as JSON once
      collection finishes. Every bug in the catalog is a key, so an empty list
      means nothing catches that bug. Works with ``--collect-only``. The option
      itself is registered in the root conftest.py (see there for why).
"""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import httpx
import psycopg
import pytest
from psycopg.rows import dict_row

from expenses import bugs
from expenses import db as app_db
from tests.support.api import Api, HasUsername
from tests.support.builders import Cleanup, Db, User, UserFactory, insert_claim_with_history

TESTS_DIR = Path(__file__).resolve().parent
REPO_ROOT = TESTS_DIR.parent
REPORTS_DIR = REPO_ROOT / "reports"
LAYERS = ("unit", "api", "contract", "db", "export", "ui")
HEALTH_TIMEOUT_S = 20.0


def pytest_configure() -> None:
    try:
        bugs.current()
    except bugs.UnknownBugError as exc:
        raise pytest.UsageError(str(exc)) from exc


def pytest_report_header(config: pytest.Config) -> list[str]:
    target = os.environ.get("BASE_URL") or config.getoption("base_url", None)
    return [
        f"seeded bug: {bugs.current() or 'none'}",
        f"database: {_redacted(app_db.database_url())}",
        f"app under test: {target or 'started per worker by the server fixture'}",
    ]


def _redacted(url: str) -> str:
    scheme, sep, rest = url.partition("://")
    if "@" in rest:
        rest = rest.rsplit("@", 1)[1]
    return f"{scheme}{sep}{rest}"


def _caught_bugs(item: pytest.Item) -> list[str]:
    names: list[str] = []
    for mark in item.iter_markers("catches"):
        for name in mark.args:
            if name not in names:
                names.append(name)
    return names


def _catches_problems(item: pytest.Item) -> list[str]:
    problems: list[str] = []
    for mark in item.iter_markers("catches"):
        if not mark.args:
            problems.append("@pytest.mark.catches needs at least one bug name")
        for name in mark.args:
            if not isinstance(name, str) or name not in bugs.CATALOG:
                problems.append(f"{name!r} is not a seeded bug in expenses.bugs.CATALOG")
    return problems


def _bad_catches_message(problems: list[str]) -> str:
    return (
        "Bad @pytest.mark.catches marker:\n  "
        + "\n  ".join(problems)
        + f"\nKnown bugs: {', '.join(bugs.CATALOG)}"
    )


@pytest.hookimpl(wrapper=True)
def pytest_pycollect_makeitem(collector: pytest.Module | pytest.Class) -> Any:
    """Turn an unknown bug name in a catches marker into a collection error for its module.

    A collection error stops the run (serially and under xdist) before any
    test executes, so a typo can never count as a bug that was caught.
    """
    result = yield
    made = result if isinstance(result, list) else [result]
    problems = [
        f"{item.name}: {problem}"
        for item in made
        if isinstance(item, pytest.Item)
        for problem in _catches_problems(item)
    ]
    if problems:
        raise collector.CollectError(_bad_catches_message(problems))
    return result


def _layer(item: pytest.Item) -> str | None:
    try:
        parts = Path(item.path).resolve().relative_to(TESTS_DIR).parts
    except ValueError:
        return None
    return parts[0] if len(parts) > 1 and parts[0] in LAYERS else None


@pytest.hookimpl(tryfirst=True)
def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    """Add layer markers from the directory, before -m filtering sees the items.

    Also re-checks catches markers, for any added after collection (for
    example by ``item.add_marker`` in a hook).
    """
    problems: list[str] = []
    for item in items:
        layer = _layer(item)
        if layer:
            item.add_marker(getattr(pytest.mark, layer))
        problems.extend(f"{item.nodeid}: {p}" for p in _catches_problems(item))
    if problems:
        raise pytest.UsageError(_bad_catches_message(problems))


def pytest_collection_finish(session: pytest.Session) -> None:
    """Write the --write-catches map from the final (selected) items.

    Nothing is written when collection had errors, and a map left by an
    earlier run is removed, so a broken collection cannot pass for a clean one.
    """
    target = session.config.getoption("--write-catches")
    if not target:
        return
    if os.environ.get("PYTEST_XDIST_WORKER", "gw0") != "gw0":
        return  # every worker collects the same items; one writer is enough
    path = Path(target)
    if session.testsfailed:
        path.unlink(missing_ok=True)
        return
    catches: dict[str, list[str]] = {name: [] for name in bugs.CATALOG}
    for item in session.items:
        for name in _caught_bugs(item):
            if name in catches:
                catches[name].append(item.nodeid)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(catches, indent=2) + "\n", encoding="utf-8")


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _tail(path: Path, lines: int = 40) -> str:
    try:
        return "\n".join(path.read_text(errors="replace").splitlines()[-lines:])
    except OSError:
        return "(no server log)"


def _check_seeded_bug(url: str, health: dict[str, Any]) -> None:
    expected = bugs.current()
    if health.get("seededBug") != expected:
        pytest.fail(
            f"The app at {url} runs seededBug={health.get('seededBug')!r} but this test run has "
            f"SEEDED_BUG={expected!r}. Results would be meaningless.",
            pytrace=False,
        )


def _wait_until_healthy(proc: subprocess.Popen[bytes], url: str, log: Path) -> dict[str, Any]:
    deadline = time.monotonic() + HEALTH_TIMEOUT_S
    while True:
        try:
            resp = httpx.get(f"{url}/health", timeout=1.0)
            if resp.status_code == 200:
                return resp.json()
        except httpx.TransportError:
            pass
        if time.monotonic() > deadline:
            pytest.fail(
                f"The app did not answer {url}/health within {HEALTH_TIMEOUT_S:.0f}s.\n"
                f"Server log ({log}):\n{_tail(log)}",
                pytrace=False,
            )
        try:
            code = proc.wait(timeout=0.1)  # doubles as the pause between polls
        except subprocess.TimeoutExpired:
            continue
        pytest.fail(
            f"The app exited with code {code} before it was healthy.\n"
            f"Server log ({log}):\n{_tail(log)}",
            pytrace=False,
        )


@pytest.fixture(scope="session")
def server(pytestconfig: pytest.Config) -> Iterator[str]:
    """Base URL of the app under test, without a trailing slash.

    Uses BASE_URL (or --base-url) when set. Otherwise starts one uvicorn
    process per xdist worker on a free port and stops it at the end of the
    session. The server log goes to reports/server-<worker>.log.
    """
    external = os.environ.get("BASE_URL") or pytestconfig.getoption("base_url", None)
    if external:
        url = str(external).rstrip("/")
        try:
            health = httpx.get(f"{url}/health", timeout=5.0).json()
        except (httpx.HTTPError, ValueError) as exc:
            pytest.fail(f"BASE_URL {url} did not answer /health: {exc}", pytrace=False)
        _check_seeded_bug(url, health)
        yield url
        return

    port = _free_port()
    url = f"http://127.0.0.1:{port}"
    REPORTS_DIR.mkdir(exist_ok=True)
    log_path = REPORTS_DIR / f"server-{os.environ.get('PYTEST_XDIST_WORKER', 'main')}.log"
    with log_path.open("wb") as log:
        proc = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "uvicorn",
                "expenses.main:app",
                "--host",
                "127.0.0.1",
                "--port",
                str(port),
                "--log-level",
                "warning",
            ],
            cwd=REPO_ROOT,
            env=os.environ.copy(),
            stdout=log,
            stderr=subprocess.STDOUT,
        )
    try:
        health = _wait_until_healthy(proc, url, log_path)
        _check_seeded_bug(url, health)
        yield url
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()


@pytest.fixture(scope="session")
def base_url(server: str) -> str:
    """The app's base URL. Overrides pytest-playwright's, so pages can use relative paths."""
    return server


@pytest.fixture(scope="session")
def _verify_url() -> None:
    """Disable pytest-base-url's autouse URL check, if that plugin is installed.

    Its check requests ``base_url`` for every test, which would start the
    server even for unit tests. The server fixture does its own health check.
    """


@pytest.fixture(scope="session")
def db() -> Iterator[Db]:
    """A psycopg connection for the session: autocommit, dict rows, schema applied.

    Autocommit means every statement is visible to the app immediately and a
    failed statement leaves no broken transaction behind.
    """
    conn: Db = psycopg.connect(app_db.database_url(), autocommit=True, row_factory=dict_row)
    try:
        app_db.init_db(conn)
        yield conn
    finally:
        conn.close()


@pytest.fixture
def cleanup(db: Db) -> Iterator[Cleanup]:
    """Deletes what the test registered (claims, then users) when the test ends."""
    tracker = Cleanup(db)
    yield tracker
    tracker.run()


@pytest.fixture
def make_user(db: Db, cleanup: Cleanup) -> UserFactory:
    """``make_user("employee" | "manager" | "finance", display_name=None) -> User``."""
    return UserFactory(db, cleanup)


@pytest.fixture
def employee(make_user: UserFactory) -> User:
    """A fresh employee for this test."""
    return make_user("employee")


@pytest.fixture
def manager(make_user: UserFactory) -> User:
    """A fresh manager for this test."""
    return make_user("manager")


@pytest.fixture
def finance(make_user: UserFactory) -> User:
    """A fresh finance user for this test."""
    return make_user("finance")


@pytest.fixture
def claim_in(db: Db, make_user: UserFactory, employee: User) -> Callable[..., dict[str, Any]]:
    """``claim_in(status, owner=employee)``: a claim written straight into ``status``.

    Built in SQL, so a test of pay does not depend on approve working, and
    filled in the way the app would have left it (see
    ``builders.insert_claim_with_history``).
    """

    def build(status: str, owner: User | None = None) -> dict[str, Any]:
        return insert_claim_with_history(db, make_user, owner or employee, status)

    return build


@pytest.fixture
def api_as(base_url: str) -> Iterator[Callable[[HasUsername | str | None], Api]]:
    """``api_as(user)`` returns an Api for ``user`` (or anonymous for None), closed afterwards."""
    clients: list[Api] = []

    def factory(user: HasUsername | str | None) -> Api:
        client = Api(base_url, user)
        clients.append(client)
        return client

    yield factory
    for client in clients:
        client.close()
