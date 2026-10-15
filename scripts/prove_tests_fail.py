"""Run the suite once per seeded bug and require every test marked for that bug to fail.

The app carries twelve deliberate bugs, each behind ``SEEDED_BUG=<name>``
(see expenses/bugs.py), and a test written to catch one says so with
``@pytest.mark.catches("<name>")``. The script:

1. collects the ``{bug: [node id, ...]}`` map with
   ``pytest --collect-only --write-catches=PATH`` and stops if any bug in the
   catalog has no marked test;
2. runs the suite with no bug, where every test must pass (``--skip-clean``
   leaves this out, for CI, which has just run the clean suite);
3. runs the suite once per bug with ``SEEDED_BUG=<bug>`` and requires every
   marked test to fail, recording any other failures as collateral;
4. prints a Markdown table, writes it to reports/seeded-bugs.md, appends it to
   ``$GITHUB_STEP_SUMMARY`` when that is set, and exits 1 if any bug escaped;
5. after a full run (the clean run and all twelve bugs, every one caught),
   writes the table into README.md between its ``seeded-bugs`` markers and
   runs tests/test_readme.py to check the README against the suite.

tests/test_readme.py checks this script's output, so the runs above leave it
out and it runs only at the end, once the README is written.

Only a failure counts as a catch. A marked test that errored (a fixture broke,
the server never started) is reported as not caught.

    python scripts/prove_tests_fail.py                      # clean run, then all twelve bugs
    python scripts/prove_tests_fail.py --skip-clean         # the bugs only
    python scripts/prove_tests_fail.py self-approval future-date
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
from collections import Counter
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from expenses import bugs

REPO_ROOT = Path(__file__).resolve().parent.parent
REPORTS = REPO_ROOT / "reports"
RUNS = REPORTS / "prove"  # one JUnit XML and one log per run
CATCHES_MAP = RUNS / "catches.json"
TABLE_PATH = REPORTS / "seeded-bugs.md"
README = REPO_ROOT / "README.md"
README_START = "<!-- seeded-bugs:start -->"
README_END = "<!-- seeded-bugs:end -->"
README_TESTS = "tests/test_readme.py"  # checks the README this script writes; run last

LAYERS = ("unit", "api", "contract", "db", "export", "ui")

# pytest exit codes: 0 means every test passed, 1 means some failed. Any other
# code means the run itself broke (interrupted, internal error, usage error,
# nothing collected), and then its results prove nothing either way.
EXIT_ALL_PASSED = 0
EXIT_TESTS_FAILED = 1

# A test can appear in the XML more than once (a call failure plus a teardown
# error). The worst outcome wins.
SEVERITY = {"passed": 0, "skipped": 1, "error": 2, "failed": 3}

JunitKey = tuple[str, str]


def pytest_env(bug: str | None) -> dict[str, str]:
    """This process's environment with exactly one seeded bug, or none.

    BASE_URL is dropped: every run must start its own server with the bug set,
    not reuse one that is already running.
    """
    env = {k: v for k, v in os.environ.items() if k not in ("SEEDED_BUG", "BASE_URL")}
    if bug:
        env["SEEDED_BUG"] = bug
    return env


def pytest_command(*args: str) -> list[str]:
    # The cache plugin is off so seeded-bug failures never land in the
    # last-failed list that a later ``pytest --lf`` would rerun.
    return [sys.executable, "-m", "pytest", "-p", "no:cacheprovider", *args]


@dataclass
class Collection:
    node_ids: list[str]
    catches: dict[str, list[str]]


def collect() -> Collection:
    """Every test node id, and the catches map written by ``--write-catches``."""
    CATCHES_MAP.unlink(missing_ok=True)
    proc = subprocess.run(
        pytest_command(
            "--collect-only", "-q", f"--ignore={README_TESTS}", f"--write-catches={CATCHES_MAP}"
        ),
        cwd=REPO_ROOT,
        env=pytest_env(None),
        capture_output=True,
        text=True,
    )
    if proc.returncode != EXIT_ALL_PASSED or not CATCHES_MAP.exists():
        sys.exit(f"Collection failed (pytest exit {proc.returncode}):\n{proc.stdout}{proc.stderr}")
    node_ids = [line for line in proc.stdout.splitlines() if "::" in line]
    catches = json.loads(CATCHES_MAP.read_text(encoding="utf-8"))
    return Collection(node_ids, catches)


@dataclass
class Run:
    label: str
    exit_code: int
    outcomes: dict[JunitKey, str]
    seconds: float
    log: Path

    @property
    def broken(self) -> bool:
        return self.exit_code not in (EXIT_ALL_PASSED, EXIT_TESTS_FAILED) or not self.outcomes

    def outcome(self, node_id: str) -> str:
        return self.outcomes.get(junit_key(node_id), "not run")

    def failures(self) -> dict[JunitKey, str]:
        """Every test that failed or errored, with which of the two it was."""
        return {key: out for key, out in self.outcomes.items() if out in ("failed", "error")}

    def counts(self) -> Counter[str]:
        return Counter(self.outcomes.values())


def run_suite(label: str, bug: str | None, workers: str) -> Run:
    """Run the whole suite once, with ``bug`` seeded, and read the JUnit XML."""
    xml_path = RUNS / f"{label}.xml"
    log_path = RUNS / f"{label}.log"
    xml_path.unlink(missing_ok=True)
    started = time.monotonic()
    with log_path.open("w", encoding="utf-8") as log:
        proc = subprocess.run(
            pytest_command(
                "-n", workers, "-q", f"--ignore={README_TESTS}", f"--junitxml={xml_path}"
            ),
            cwd=REPO_ROOT,
            env=pytest_env(bug),
            stdout=log,
            stderr=subprocess.STDOUT,
        )
    outcomes = read_outcomes(xml_path) if xml_path.exists() else {}
    return Run(label, proc.returncode, outcomes, time.monotonic() - started, log_path)


def junit_key(node_id: str) -> JunitKey:
    """The (classname, name) pair that pytest's JUnit XML writes for a node id.

    It follows pytest's own rule: the file path becomes a dotted module name,
    any class joins it, and the parameter id stays on the test name.

        tests/ui/test_dashboard.py::test_x[chromium-tag]
        -> ("tests.ui.test_dashboard", "test_x[chromium-tag]")
    """
    path, bracket, params = node_id.partition("[")
    names = path.split("::")
    names[0] = re.sub(r"\.py$", "", names[0].replace("/", "."))
    names[-1] += bracket + params
    return ".".join(names[:-1]), names[-1]


def case_outcome(case: ET.Element) -> str:
    tags = {child.tag for child in case}
    for outcome in ("failure", "error", "skipped"):
        if outcome in tags:
            return "failed" if outcome == "failure" else outcome
    return "passed"


def read_outcomes(xml_path: Path) -> dict[JunitKey, str]:
    outcomes: dict[JunitKey, str] = {}
    for case in ET.parse(xml_path).getroot().iter("testcase"):
        key = (case.get("classname", ""), case.get("name", ""))
        outcome = case_outcome(case)
        if key not in outcomes or SEVERITY[outcome] > SEVERITY[outcomes[key]]:
            outcomes[key] = outcome
    return outcomes


@dataclass
class Verdict:
    bug: str
    marked: list[str]
    run: Run
    missed: dict[str, str] = field(default_factory=dict)  # marked test -> what it did instead
    collateral: dict[str, str] = field(default_factory=dict)  # other tests that failed or errored

    @property
    def caught(self) -> bool:
        return not self.run.broken and not self.missed


def judge(bug: str, marked: list[str], run: Run, names: dict[JunitKey, str]) -> Verdict:
    """Every marked test must have failed. Anything else that failed is collateral."""
    verdict = Verdict(bug, marked, run)
    for node_id in marked:
        outcome = run.outcome(node_id)
        if outcome != "failed":
            verdict.missed[node_id] = outcome
    marked_keys = {junit_key(node_id) for node_id in marked}
    verdict.collateral = {
        names.get(key, "::".join(key)): outcome
        for key, outcome in sorted(run.failures().items())
        if key not in marked_keys
    }
    return verdict


def check_clean_run(run: Run, node_ids: list[str]) -> list[str]:
    """Problems with the no-bug run. Empty means every collected test passed."""
    problems = [
        f"{node_id}: {run.outcome(node_id)}"
        for node_id in node_ids
        if run.outcome(node_id) != "passed"
    ]
    if run.exit_code != EXIT_ALL_PASSED:
        problems.insert(0, f"pytest exited {run.exit_code} (see {run.log.relative_to(REPO_ROOT)})")
    return problems


def layer_of(node_id: str) -> str:
    parts = node_id.split("::", 1)[0].split("/")
    return parts[1] if len(parts) > 2 and parts[1] in LAYERS else "other"


def caught_by(marked: list[str]) -> str:
    """Marked tests per layer, in suite order: ``unit 11 · api 5``."""
    per_layer = Counter(layer_of(node_id) for node_id in marked)
    order = [*LAYERS, "other"]
    return " · ".join(f"{layer} {per_layer[layer]}" for layer in order if per_layer[layer])


def result_cell(verdict: Verdict) -> str:
    total = len(verdict.marked)
    run = verdict.run
    if run.broken:
        return f"**NOT PROVEN**: the run broke (pytest exit {run.exit_code})"
    if verdict.missed:
        return f"**ESCAPED**: {len(verdict.missed)} of {total} marked tests did not fail"
    cell = f"Caught: {total} of {total} failed"
    if verdict.collateral:
        others = len(verdict.collateral)
        cell += f" · {others} other {'test' if others == 1 else 'tests'} failed too"
    return cell


def report_table(verdicts: list[Verdict], clean_line: str) -> str:
    """The results table and its one-line summary."""
    caught = sum(v.caught for v in verdicts)
    lines = [
        "| Seeded bug | What breaks | Caught by | Result |",
        "|---|---|---|---|",
        *(
            f"| `{v.bug}` | {bugs.CATALOG[v.bug]} | {caught_by(v.marked)} | {result_cell(v)} |"
            for v in verdicts
        ),
        "",
        f"{caught} of {len(verdicts)} seeded bugs caught. {clean_line}",
    ]
    return "\n".join(lines) + "\n"


def markdown_report(verdicts: list[Verdict], clean_line: str) -> str:
    """The table, then what went wrong or failed alongside, bug by bug."""
    lines = [report_table(verdicts, clean_line).rstrip("\n")]
    for v in verdicts:
        if not (v.missed or v.collateral or v.run.broken):
            continue
        lines += ["", f"### `{v.bug}`", ""]
        if v.run.broken:
            lines.append(f"The run broke: pytest exited {v.run.exit_code}.")
        lines += [f"- not caught: `{node_id}` ({outcome})" for node_id, outcome in v.missed.items()]
        lines += [f"- collateral: `{name}` ({outcome})" for name, outcome in v.collateral.items()]
    return "\n".join(lines) + "\n"


def write_report(report: str) -> None:
    TABLE_PATH.write_text("# Seeded bugs\n\n" + report, encoding="utf-8")
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as out:
            out.write("## Seeded bugs\n\n" + report)


def readme_with_table(readme: str, table: str, day: str) -> str:
    """``readme`` with the text between the seeded-bugs markers replaced by ``table``."""
    start = readme.index(README_START) + len(README_START)
    end = readme.index(README_END)
    block = f"\nThe table from the last full run, on {day}:\n\n{table}"
    return readme[:start] + block + readme[end:]


def update_readme(table: str) -> bool:
    """Write the table into the README, then check the README with its tests. True if it matches."""
    day = datetime.now(UTC).date().isoformat()
    text = README.read_text(encoding="utf-8")
    updated = readme_with_table(text, table, day)
    if updated != text:
        README.write_text(updated, encoding="utf-8")
        print(f"Updated the seeded-bug table in {README.relative_to(REPO_ROOT)}.")
    sys.stdout.flush()  # so pytest's output follows ours when stdout is a file or a CI log
    check = subprocess.run(pytest_command("-q", README_TESTS), cwd=REPO_ROOT, env=pytest_env(None))
    if check.returncode != EXIT_ALL_PASSED:
        print(f"README.md does not match the suite: see {README_TESTS} above.")
    return check.returncode == EXIT_ALL_PASSED


def tail(path: Path, lines: int = 30) -> str:
    return "\n".join(path.read_text(errors="replace").splitlines()[-lines:])


def summary_line(run: Run) -> str:
    counts = run.counts()
    parts = [f"{counts[k]} {k}" for k in ("passed", "failed", "error", "skipped") if counts[k]]
    return f"{', '.join(parts) or 'no results'} in {run.seconds:.0f}s"


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the suite once per seeded bug and fail if any bug goes uncaught."
    )
    parser.add_argument(
        "bugs",
        nargs="*",
        metavar="BUG",
        help=f"only these bugs (default: all). Known: {', '.join(bugs.CATALOG)}",
    )
    parser.add_argument(
        "--skip-clean", action="store_true", help="skip the no-bug run that must pass"
    )
    parser.add_argument(
        "-n", "--workers", default="auto", help="pytest-xdist workers per run (default: auto)"
    )
    args = parser.parse_args(argv)
    unknown = [name for name in args.bugs if name not in bugs.CATALOG]
    if unknown:
        parser.error(f"not seeded bugs: {', '.join(unknown)}")
    return args


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    RUNS.mkdir(parents=True, exist_ok=True)

    collection = collect()
    names = {junit_key(node_id): node_id for node_id in collection.node_ids}
    uncovered = [bug for bug in bugs.CATALOG if not collection.catches.get(bug)]
    marked_total = len({n for ids in collection.catches.values() for n in ids})
    print(f"Collected {len(collection.node_ids)} tests, {marked_total} marked to catch a bug.")
    if uncovered:
        print(f"No test is marked to catch: {', '.join(uncovered)}", file=sys.stderr)
        return 1

    if args.skip_clean:
        clean_line = "Clean run skipped here (--skip-clean)."
    else:
        print("Clean run, no seeded bug ...", end=" ", flush=True)
        clean = run_suite("clean", None, args.workers)
        print(summary_line(clean))
        problems = check_clean_run(clean, collection.node_ids)
        if problems:
            print("The suite must pass with no bug before a failure means anything:")
            print("\n".join(f"  {p}" for p in problems[:40]))
            print(tail(clean.log))
            return 1
        clean_line = f"Clean run: all {len(collection.node_ids)} tests passed."

    selected = args.bugs or list(bugs.CATALOG)
    verdicts: list[Verdict] = []
    for index, bug in enumerate(selected, start=1):
        print(f"[{index}/{len(selected)}] SEEDED_BUG={bug} ...", end=" ", flush=True)
        run = run_suite(bug, bug, args.workers)
        verdict = judge(bug, collection.catches[bug], run, names)
        verdicts.append(verdict)
        print(f"{summary_line(run)}: {result_cell(verdict)}")
        if run.broken:
            print(tail(run.log))

    report = markdown_report(verdicts, clean_line)
    write_report(report)
    print()
    print(report, end="")
    print(f"\nWritten to {TABLE_PATH.relative_to(REPO_ROOT)}")
    all_caught = all(v.caught for v in verdicts)
    if all_caught and not args.skip_clean and not args.bugs:
        return 0 if update_readme(report_table(verdicts, clean_line)) else 1
    return 0 if all_caught else 1


if __name__ == "__main__":
    sys.exit(main())
