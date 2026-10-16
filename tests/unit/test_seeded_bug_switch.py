"""The SEEDED_BUG switch: on, off, and a typo that must stop the run."""

from __future__ import annotations

import pytest

from expenses import bugs


def active_bugs():
    return [name for name in bugs.CATALOG if bugs.active(name)]


@pytest.mark.parametrize("value", ["", "   "])
def test_an_empty_switch_turns_on_no_bug(monkeypatch, value):
    monkeypatch.setenv("SEEDED_BUG", value)

    assert active_bugs() == []


def test_an_unset_switch_turns_on_no_bug(monkeypatch):
    monkeypatch.delenv("SEEDED_BUG", raising=False)

    assert active_bugs() == []


@pytest.mark.parametrize("name", list(bugs.CATALOG))
def test_naming_a_bug_turns_on_that_bug_alone(monkeypatch, name):
    monkeypatch.setenv("SEEDED_BUG", name)

    assert active_bugs() == [name]


def test_an_unknown_bug_in_the_switch_raises(monkeypatch):
    monkeypatch.setenv("SEEDED_BUG", "limit-of-by-one")

    with pytest.raises(bugs.UnknownBugError, match="not a known seeded bug"):
        bugs.active("limit-off-by-one")


def test_asking_about_a_bug_that_is_not_in_the_catalog_raises(monkeypatch):
    monkeypatch.delenv("SEEDED_BUG", raising=False)

    with pytest.raises(bugs.UnknownBugError, match=r"not in bugs\.CATALOG"):
        bugs.active("limit-of-by-one")
