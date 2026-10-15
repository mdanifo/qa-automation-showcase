"""The README's numbers are checked against the suite, so they cannot drift from it.

scripts/prove_tests_fail.py writes the seeded-bug table into the README after
a full run. These tests check what collection alone can confirm: each bug's
"Caught by" cell and marked-test count, the clean-run total, and the number of
tests per layer. When one fails, rerun the prove script, which rewrites the
table, and correct the layer counts by hand.

The prove script leaves this file out of its runs (it checks the script's own
output), so the README's clean-run total is the suite without these tests.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
from collections import Counter

import pytest

from expenses import bugs
from scripts.prove_tests_fail import (
    LAYERS,
    README,
    README_END,
    README_START,
    README_TESTS,
    REPO_ROOT,
    caught_by,
    layer_of,
    pytest_command,
)

BUG_ROW = re.compile(r"^\| `([a-z-]+)` \| (.+?) \| (.+?) \| (.+?) \|$", re.MULTILINE)
LAYER_ROW = re.compile(rf"^\| ({'|'.join(LAYERS)}) \| (\d+) \|", re.MULTILINE)
TOP_LEVEL = re.compile(
    r"^(\d+) more tests sit at the top of `tests/`: (\d+) smoke tests of the shared fixtures,"
    r" (\d+) of the prove script and (\d+) that check this README",
    re.MULTILINE,
)
TOP_LEVEL_FILES = ("tests/test_smoke.py", "tests/test_prove_script.py", README_TESTS)


@pytest.fixture(scope="module")
def collected(tmp_path_factory) -> tuple[list[str], dict[str, list[str]]]:
    """Every test id and the catches map, from a ``--collect-only`` run of the whole suite."""
    catches_path = tmp_path_factory.mktemp("collect") / "catches.json"
    # A worker's PYTEST_XDIST_* variables would make the child skip writing the map.
    env = {k: v for k, v in os.environ.items() if not k.startswith("PYTEST_")}
    proc = subprocess.run(
        pytest_command("--collect-only", "-q", f"--write-catches={catches_path}"),
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    node_ids = [line for line in proc.stdout.splitlines() if "::" in line]
    return node_ids, json.loads(catches_path.read_text(encoding="utf-8"))


def readme_table() -> str:
    text = README.read_text(encoding="utf-8")
    return text[text.index(README_START) + len(README_START) : text.index(README_END)]


def test_the_seeded_bug_table_matches_the_marked_tests(collected):
    node_ids, catches = collected
    table = readme_table()

    rows = {
        bug: (what, by, result.split(" · ")[0]) for bug, what, by, result in BUG_ROW.findall(table)
    }

    assert rows == {
        bug: (
            what,
            caught_by(catches[bug]),
            f"Caught: {len(catches[bug])} of {len(catches[bug])} failed",
        )
        for bug, what in bugs.CATALOG.items()
    }
    proven = [node_id for node_id in node_ids if not node_id.startswith(f"{README_TESTS}::")]
    assert f"Clean run: all {len(proven)} tests passed." in table


def test_the_test_counts_per_layer_match_the_suite(collected):
    node_ids, _ = collected
    text = README.read_text(encoding="utf-8")
    top_level = TOP_LEVEL.search(text)
    assert top_level is not None

    listed = {layer: int(count) for layer, count in LAYER_ROW.findall(text)}
    listed["other"] = int(top_level.group(1))
    listed_files = [int(count) for count in top_level.groups()[1:]]

    per_layer = Counter(layer_of(node_id) for node_id in node_ids)
    per_file = Counter(node_id.split("::")[0] for node_id in node_ids)
    assert listed == {layer: per_layer[layer] for layer in (*LAYERS, "other")}
    assert listed_files == [per_file[path] for path in TOP_LEVEL_FILES]
