"""Set up the database for a demo.

``python -m expenses.seed`` applies the schema and adds the five demo users.
``python -m expenses.seed --demo`` also adds sample claims in every status,
created through the same service calls the app uses. It adds nothing when the
demo users already have claims, so it is safe to run twice.
"""

from __future__ import annotations

import argparse
from datetime import timedelta

from expenses import bugs, db, rules, service


def _user(username: str) -> service.User:
    user = service.get_user(username)
    if user is None:
        raise SystemExit(f"Demo user {username!r} is missing; run without --demo first.")
    return user


def _claim(owner: service.User, title: str, category: str, value: str, days_ago: int) -> int:
    day = (rules.today_utc() - timedelta(days=days_ago)).isoformat()
    data: dict[str, object] = {"title": title, "category": category, "expenseDate": day}
    data["miles" if category == "mileage" else "amount"] = value
    return int(service.create_claim(owner, data)["id"])


def add_demo_claims() -> int:
    """Add sample claims for the demo users. Returns how many were added."""
    erin, eli, maya, omar, fran = (_user(n) for n in ("erin", "eli", "maya", "omar", "fran"))
    with db.connect() as conn:
        existing = conn.execute(
            "SELECT count(*) AS n FROM claims WHERE owner = ANY(%s)",
            ([u.username for u in (erin, eli, maya, omar, fran)],),
        ).fetchone()
    already_seeded = bool(existing and existing["n"])
    if bugs.active("demo-seed-repeats"):
        # SEEDED BUG demo-seed-repeats: the guard is skipped and every run adds the claims again.
        already_seeded = False
    if already_seeded:
        return 0

    _claim(erin, "Team lunch", "meals", "42.50", 3)
    _claim(erin, "Client visit", "mileage", "13.5", 5)
    taxi = _claim(erin, "Taxi to the airport", "travel", "38.00", 12)
    service.reject(omar, taxi, "This trip was booked as a company car.")

    hotel = _claim(eli, "Hotel, two nights", "lodging", "240.00", 9)
    service.approve(maya, hotel)
    license_ = _claim(eli, "Test tool license", "software", "120.00", 20)
    service.approve(omar, license_)
    service.pay(fran, license_)
    _claim(eli, "Printer paper", "other", "18.25", 2)

    ticket = _claim(maya, "Conference ticket", "travel", "450.00", 30)
    service.approve(omar, ticket)

    created = [*_ids(erin), *_ids(eli), *_ids(maya)]
    return len(created)


def _ids(owner: service.User) -> list[int]:
    return [int(row["id"]) for row in service.own_claims(owner)]


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Set up the expenses database for a demo.")
    parser.add_argument("--demo", action="store_true", help="also add sample claims")
    args = parser.parse_args(argv)
    db.init_db()
    print(f"Schema ready, demo users present ({db.database_url().rsplit('@', 1)[-1]}).")
    if args.demo:
        added = add_demo_claims()
        if added:
            print(f"Added {added} sample claims.")
        else:
            print("The demo users already have claims; nothing added.")


if __name__ == "__main__":
    main()
