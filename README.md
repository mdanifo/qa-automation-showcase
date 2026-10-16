# QA automation showcase

[![CI](https://github.com/mdanifo/qa-automation-showcase/actions/workflows/ci.yml/badge.svg)](https://github.com/mdanifo/qa-automation-showcase/actions/workflows/ci.yml)

A small expense-reimbursement web app (FastAPI, Postgres, server-rendered pages) and the pytest and Playwright suite that tests it in six layers: unit, API, contract, database, CSV export and UI. The app carries sixteen seeded bugs behind an environment variable. CI runs the suite once per bug and fails the build unless every test written for that bug fails.

## Proving the suite can fail

A suite that passes proves nothing until it has been seen to fail. A test written to catch a seeded bug is marked `@pytest.mark.catches("<bug>")`. `scripts/prove_tests_fail.py` turns each bug on in turn with `SEEDED_BUG=<bug>`, runs the whole suite, and requires every marked test to fail. With no bug set, everything must pass.

<!-- seeded-bugs:start -->
The table from the last full run, on 2026-10-16:

| Seeded bug | What breaks | Caught by | Result |
|---|---|---|---|
| `limit-off-by-one` | A claim for exactly the category limit is rejected. | unit 11 · api 5 | Caught: 16 of 16 failed |
| `mileage-float-rounding` | Mileage is computed in float: 13.5 miles pays $9.04, not $9.05. | unit 4 · api 2 · db 1 · ui 1 | Caught: 8 of 8 failed |
| `self-approval` | A manager can approve their own claim. | unit 2 · api 2 · db 1 | Caught: 5 of 5 failed |
| `reject-without-note` | A claim can be rejected with a blank note. | unit 7 · api 5 · db 3 · ui 2 | Caught: 17 of 17 failed |
| `pay-unapproved` | Finance can pay a claim that was never approved. | unit 2 · api 2 · db 2 | Caught: 6 of 6 failed |
| `future-date` | An expense dated tomorrow is accepted. | unit 2 · api 1 · ui 1 | Caught: 4 of 4 failed |
| `amount-as-number` | The API returns amount as a JSON number (42.5), not the string "42.50". | api 5 · contract 10 | Caught: 15 of 15 failed · 5 other tests failed too |
| `approval-not-saved` | Approve answers 200 with status approved but never commits it. | api 1 · db 3 · ui 2 | Caught: 6 of 6 failed · 13 other tests failed too |
| `missing-audit-event` | Paying a claim writes no claim_events row. | db 3 | Caught: 3 of 3 failed · 1 other test failed too |
| `pending-total-includes-rejected` | The pending total counts rejected claims. | api 2 · ui 2 | Caught: 4 of 4 failed |
| `unescaped-title` | The dashboard renders claim titles as raw HTML. | ui 4 | Caught: 4 of 4 failed |
| `csv-amount-format` | The CSV export writes 42.5 instead of 42.50. | export 4 · ui 1 | Caught: 5 of 5 failed |
| `control-chars-accepted` | A title or reason with a NUL byte is accepted; Postgres then fails the request with a 500. | unit 9 · api 3 | Caught: 12 of 12 failed |
| `page-ignores-refusal` | A refused Approve, Reject or Pay from the pages reports success. | ui 4 | Caught: 4 of 4 failed |
| `login-trusts-the-form` | The sign-in form sets the cookie for any posted name, user or not. | api 1 · ui 1 | Caught: 2 of 2 failed |
| `demo-seed-repeats` | The demo seed adds its sample claims again on every run. | db 1 | Caught: 1 of 1 failed |

16 of 16 seeded bugs caught. Clean run: all 707 tests passed.
<!-- seeded-bugs:end -->

"Caught by" counts the marked tests per layer. A test is marked when the rule the bug breaks is the rule it checks. "Other tests failed too" counts unmarked tests that failed or errored in the same run, mostly later steps that depend on the broken one (with approval not saved, nothing can be paid). They are listed in `reports/seeded-bugs.md` and do not count as catches.

A few guards keep the table honest:

- Each bug is one `if bugs.active("<name>"):` branch in the app, at the spot where someone would plausibly make that mistake. Search the code for `SEEDED BUG`.
- An unknown `SEEDED_BUG` value stops both the app and pytest at startup, and an unknown name in a `catches` marker is a collection error.
- Only a failure counts. A marked test that errors in a fixture, or does not run, is reported as not caught.
- The server fixture checks that the app under test reports the same seeded bug as the test run before any test runs.
- `tests/test_prove_script.py` runs a throwaway suite with one test of each outcome and checks that the prove script reads each one correctly from the JUnit XML.
- The prove script writes the table above after a full run. `tests/test_readme.py` checks it, and the test counts below, against the collected suite, so adding or removing a test without rerunning the script fails the build.

## Test layers

| Layer | Tests | What it checks |
|---|---|---|
| unit | 259 | The rules in `expenses/rules.py` with no server: amount parsing, category limits, mileage rounding, the 90-day date window, title and reason rules, transitions and visibility. Dates use a fixed today, one of them in a leap year. |
| api | 201 | Status and error codes, who may see and do what, which error wins when several apply, totals, the sign-in form, and one claim's lifecycle read back after each step. |
| contract | 64 | Every response against the JSON Schemas in `contracts/`, and the schemas themselves against near misses. |
| db | 56 | What Postgres holds after each action: the stored row, the audit trail, refused actions leaving nothing behind, integrity queries over a claim in every status, two requests racing for one claim, and the demo seed. The race tests hold the row lock themselves and release it once Postgres shows both requests waiting. |
| export | 19 | The finance CSV: header, columns, which claims, order, money and date formats, access, and rows reconciled with the database. |
| ui | 97 | Playwright against the server-rendered pages, through page objects in `tests/ui/pages/`: escaping on every page that shows a title, totals, form errors, sign-in, the approve and pay flows (including from a page that has gone stale), and no sideways scrolling at 375 px. |

13 more tests sit at the top of `tests/`: 5 smoke tests of the shared fixtures, 6 of the prove script and 2 that check this README. The prove script leaves the README tests out of its runs (they check its own output) and runs them last, so its clean-run total is the suite without them.

UI tests locate elements with `get_by_role` and `get_by_label` first, then `get_by_test_id`, and wait through Playwright's `expect`; no test sleeps. Only `test_sign_in.py` and the end-to-end `test_journey.py` (one browser context each for the employee, the manager and finance) go through the login form. Every other UI test sets the `user` cookie the form would set.

## Test data

Every test creates its own users (`make_user("manager")` gives `manager-3fa2b1c9`) and its own claims, and a cleanup fixture deletes them afterwards, claims first. No test depends on another, so the suite runs in parallel (`pytest -n auto`) against one database. Lists that every test shares (pending approvals, payments, the CSV) also hold other tests' rows, and tests find their own rows by id rather than counting them.

A test gets a claim in one of two ways. `submit_claim(api, ...)` goes through the API, the way a user would. `insert_claim(db, owner, status="approved")` writes the row straight into the state the test needs, which keeps a test of pay from depending on approve. The `claim_in("paid")` fixture does the same and also fills in who decided and paid the claim, with its audit trail.

Expected values are computed apart from the app. The test library does its own `Decimal` mileage arithmetic rather than asking `rules.py`.

## Diagnosing a failure

- Assertions compare values, so a failure reads as a diff: `(200, None) != (403, 'forbidden')` when a refused request succeeded, or `{'pending': '42.50'} != {'pending': '0.00'}` when a rejected claim was counted.
- The test job in CI uploads a `test-reports` artifact, even when tests fail. Its `reports/` folder holds the JUnit XML, a self-contained HTML report and the app's log from each test worker. Its `test-results/` folder holds a Playwright trace, a screenshot and a video for every failed UI test. A trace opens in the Playwright trace viewer (trace.playwright.dev) and steps through the page, network and console at each action.
- The prove job uploads `seeded-bugs.md` and adds the same table to the run's summary page.

## Run it locally

You need Docker and Python 3.12 or newer.

```bash
docker compose up -d db          # Postgres 16 on 127.0.0.1:5433
python3 -m venv .venv && .venv/bin/pip install -e ".[test]"
.venv/bin/playwright install chromium
```

Then:

```bash
.venv/bin/pytest -n auto                              # everything
.venv/bin/pytest -m api                               # one layer: unit, api, contract, db, export or ui
SEEDED_BUG=self-approval .venv/bin/pytest -n auto     # one bug on: the tests marked for it fail
.venv/bin/python scripts/prove_tests_fail.py          # a clean run, then the suite once per bug
.venv/bin/python scripts/prove_tests_fail.py --skip-clean future-date   # only the bugs named
.venv/bin/ruff check . && .venv/bin/ruff format --check .
```

On a four-core machine the suite takes under two minutes, and the prove script runs it seventeen times.

To keep traces, screenshots, video and an HTML report the way CI does:

```bash
.venv/bin/pytest -n auto --html=reports/report.html --self-contained-html --tracing retain-on-failure --screenshot only-on-failure --video retain-on-failure --output test-results
```

To test a server you already started (next section) instead of one per worker:

```bash
BASE_URL=http://127.0.0.1:8000 .venv/bin/pytest -m api
```

`docker compose down` stops the database. Its data stays in the `pgdata` volume.

## Run the app

```bash
.venv/bin/python -m expenses.seed --demo                    # optional: sample claims in every status
.venv/bin/python -m uvicorn expenses.main:app --port 8000
```

Open http://127.0.0.1:8000 and pick a user; there are no passwords. The demo users are two employees, `erin` (Erin Park) and `eli` (Eli Ward), who submit claims and follow them on the dashboard; two managers, `maya` (Maya Chen) and `omar` (Omar Haddad), who approve or reject other people's claims; and `fran` (Fran Lopez) in finance, who pays approved claims and downloads the CSV.

The API takes the user in a header:

```bash
curl -H "X-User: erin" http://127.0.0.1:8000/api/summary
```

To see a bug for yourself, start the app with it on, submit a claim titled `<b>Team</b> lunch` and look at the dashboard:

```bash
SEEDED_BUG=unescaped-title .venv/bin/python -m uvicorn expenses.main:app --port 8000
```

## The rules under test

- Per-claim limits, inclusive: meals $75, lodging $300, travel $1,500, software $500, other $250, mileage $500.
- Amounts are strings like `"42.50"`, parsed with `Decimal` and stored as integer cents. A JSON number is refused.
- Mileage pays $0.67 a mile, rounded half up: 13.5 miles is $9.05.
- The expense date can be today or up to 90 days back, in UTC.
- Titles are 1 to 80 characters and rejection reasons 1 to 500, after trimming. Control characters are refused (a NUL byte would otherwise fail in Postgres), except for line breaks and tabs in a reason.
- A manager approves or rejects other people's submitted claims, not their own, and a rejection needs a reason. Finance pays approved claims only. Every change writes one row to the `claim_events` audit trail.

## Layout

```
expenses/               the app (FastAPI, Jinja templates, psycopg)
  rules.py              pure business rules
  service.py            claim operations shared by the API and the pages
  bugs.py               the seeded-bug catalog and the SEEDED_BUG switch
  main.py               routes and error handlers
  db.py, schema.sql     connection, schema and demo users
  seed.py               python -m expenses.seed --demo
  templates/, static/   server-rendered pages, one CSS file, one small script
contracts/              JSON Schemas for every response
tests/
  conftest.py           server per worker, database, users, the catches marker
  support/              API client, test-data builders, cleanup, UTC dates
  unit/ api/ contract/ db/ export/ ui/
  ui/pages/             page objects
scripts/
  prove_tests_fail.py   one run per seeded bug, and the table above
.github/workflows/ci.yml  lint, test, prove-tests-fail
```

## About

Mike Danifo, a QA automation engineer with twenty years in software quality.
[danifo.dev](https://danifo.dev) · [LinkedIn](https://www.linkedin.com/in/mdanifo)

MIT licensed.
