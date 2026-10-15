"""The judge has to be right too: scripts/prove_tests_fail.py read against real pytest output.

A tiny throwaway suite with one test of each outcome runs in a subprocess, and
the script's own readers must find every test under the name it has in the
JUnit XML, with the right outcome. Then the rules: only a failure counts as a
catch, and a broken run proves nothing.
"""

from __future__ import annotations

import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

from scripts.prove_tests_fail import (
    README_END,
    README_START,
    Run,
    judge,
    junit_key,
    read_outcomes,
    readme_with_table,
)

DEMO_SUITE = """
    import pytest

    @pytest.fixture
    def broken_setup():
        raise RuntimeError("setup broke")

    @pytest.fixture
    def broken_teardown():
        yield
        raise RuntimeError("teardown broke")

    def test_passes():
        pass

    def test_fails():
        assert 1 == 2

    def test_setup_errors(broken_setup):
        pass

    def test_fails_then_teardown_errors(broken_teardown):
        assert 1 == 2

    def test_skips():
        pytest.skip("not today")

    @pytest.mark.parametrize("value", ["a", "b/c"])
    def test_param(value):
        assert value == "a"

    class TestGroup:
        def test_method(self):
            pass
"""

EXPECTED = {
    "tests/test_demo.py::test_passes": "passed",
    "tests/test_demo.py::test_fails": "failed",
    "tests/test_demo.py::test_setup_errors": "error",
    "tests/test_demo.py::test_fails_then_teardown_errors": "failed",
    "tests/test_demo.py::test_skips": "skipped",
    "tests/test_demo.py::test_param[a]": "passed",
    "tests/test_demo.py::test_param[b/c]": "failed",
    "tests/test_demo.py::TestGroup::test_method": "passed",
}


@pytest.fixture(scope="module")
def demo_run(tmp_path_factory: pytest.TempPathFactory) -> Run:
    root = tmp_path_factory.mktemp("demo")
    (root / "pytest.ini").write_text("[pytest]\n")  # makes this folder the rootdir
    (root / "tests").mkdir()
    (root / "tests" / "test_demo.py").write_text(textwrap.dedent(DEMO_SUITE))
    xml_path = root / "junit.xml"
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "-p", "no:cacheprovider", f"--junitxml={xml_path}"],
        cwd=root,
        capture_output=True,
        text=True,
    )
    return Run("demo", proc.returncode, read_outcomes(xml_path), 0.0, Path(xml_path))


def test_every_node_id_is_found_in_the_junit_xml_with_its_outcome(demo_run):
    found = {node_id: demo_run.outcome(node_id) for node_id in EXPECTED}

    assert found == EXPECTED
    assert set(demo_run.outcomes) == {junit_key(node_id) for node_id in EXPECTED}


def test_a_marked_test_counts_as_caught_only_when_it_failed(demo_run):
    marked = [
        "tests/test_demo.py::test_fails",
        "tests/test_demo.py::test_setup_errors",
        "tests/test_demo.py::test_passes",
        "tests/test_demo.py::test_not_in_the_run",
    ]

    verdict = judge("demo-bug", marked, demo_run, {})

    assert verdict.missed == {
        "tests/test_demo.py::test_setup_errors": "error",
        "tests/test_demo.py::test_passes": "passed",
        "tests/test_demo.py::test_not_in_the_run": "not run",
    }
    assert not verdict.caught


def test_other_failures_and_errors_are_recorded_as_collateral(demo_run):
    names = {junit_key(node_id): node_id for node_id in EXPECTED}

    verdict = judge("demo-bug", ["tests/test_demo.py::test_fails"], demo_run, names)

    assert verdict.caught
    assert verdict.collateral == {
        "tests/test_demo.py::test_fails_then_teardown_errors": "failed",
        "tests/test_demo.py::test_param[b/c]": "failed",
        "tests/test_demo.py::test_setup_errors": "error",
    }


@pytest.mark.parametrize(
    ("exit_code", "outcomes"),
    [
        pytest.param(4, {("tests.test_demo", "test_fails"): "failed"}, id="usage-error"),
        pytest.param(1, {}, id="no-results"),
    ],
)
def test_a_run_that_broke_proves_nothing(exit_code, outcomes):
    run = Run("broken", exit_code, outcomes, 0.0, Path("broken.log"))

    verdict = judge("demo-bug", ["tests/test_demo.py::test_fails"], run, {})

    assert run.broken
    assert not verdict.caught


def test_the_readme_table_is_replaced_between_its_markers_only():
    readme = f"# Title\n\nBefore.\n{README_START}\nold table\n{README_END}\n\nAfter.\n"

    updated = readme_with_table(readme, "| new | table |\n", "2026-10-15")

    assert updated == (
        f"# Title\n\nBefore.\n{README_START}\n"
        "The table from the last full run, on 2026-10-15:\n\n| new | table |\n"
        f"{README_END}\n\nAfter.\n"
    )
