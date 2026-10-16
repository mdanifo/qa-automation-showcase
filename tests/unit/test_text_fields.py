"""Titles (1 to 80 characters) and rejection reasons (1 to 500), both measured after stripping.

Neither may hold control characters, apart from line breaks and tabs in a reason.
"""

from __future__ import annotations

import pytest

from expenses import rules

REFUSED_AS_BLANK = [
    pytest.param("", id="empty"),
    pytest.param("   ", id="spaces"),
    pytest.param("\t\n", id="tab-and-newline"),
    pytest.param(None, id="none"),
]


def test_a_title_is_stripped_of_surrounding_whitespace():
    assert rules.clean_title("  Taxi to the airport \n") == "Taxi to the airport"


@pytest.mark.parametrize(
    "text",
    [
        pytest.param("x", id="1-character"),
        pytest.param("x" * 80, id="80-characters"),
        pytest.param("  " + "x" * 80 + "  ", id="80-characters-plus-padding"),
    ],
)
def test_a_title_of_1_to_80_characters_is_accepted(text):
    assert rules.clean_title(text) == text.strip()


def test_a_title_of_81_characters_is_refused():
    with pytest.raises(rules.ValidationError, match="at most 80 characters"):
        rules.clean_title("x" * 81)


@pytest.mark.parametrize("value", [*REFUSED_AS_BLANK, pytest.param(42, id="number")])
def test_a_blank_or_missing_title_is_refused(value):
    with pytest.raises(rules.ValidationError, match="A title is required"):
        rules.clean_title(value)


def test_a_reason_is_stripped_of_surrounding_whitespace():
    assert rules.clean_note("  Receipt is missing.  ") == "Receipt is missing."


@pytest.mark.parametrize(
    "text",
    [
        pytest.param("x", id="1-character"),
        pytest.param("x" * 500, id="500-characters"),
        pytest.param(" " + "x" * 500 + " ", id="500-characters-plus-padding"),
    ],
)
def test_a_reason_of_1_to_500_characters_is_accepted(text):
    assert rules.clean_note(text) == text.strip()


def test_a_reason_of_501_characters_is_refused():
    with pytest.raises(rules.ValidationError, match="at most 500 characters"):
        rules.clean_note("x" * 501)


@pytest.mark.catches("reject-without-note")
@pytest.mark.parametrize("value", REFUSED_AS_BLANK)
def test_a_blank_or_missing_reason_is_refused(value):
    with pytest.raises(rules.ValidationError, match="needs a reason"):
        rules.clean_note(value)


def test_a_reason_that_is_not_text_is_refused():
    with pytest.raises(rules.ValidationError, match="must be text"):
        rules.clean_note(["Receipt is missing."])


CONTROL_CHARACTERS = [
    pytest.param("\x00", id="nul"),
    pytest.param("\x07", id="bell"),
    pytest.param("\x1b", id="escape"),
    pytest.param("\x7f", id="delete"),
]


@pytest.mark.catches("control-chars-accepted")
@pytest.mark.parametrize("char", [*CONTROL_CHARACTERS, pytest.param("\n", id="line-break")])
def test_a_title_with_a_control_character_is_refused(char):
    with pytest.raises(rules.ValidationError, match="title cannot contain control characters"):
        rules.clean_title(f"Team{char}lunch")


@pytest.mark.catches("control-chars-accepted")
@pytest.mark.parametrize("char", CONTROL_CHARACTERS)
def test_a_reason_with_a_control_character_is_refused(char):
    with pytest.raises(rules.ValidationError, match="reason cannot contain control characters"):
        rules.clean_note(f"No{char}receipt.")


@pytest.mark.parametrize(
    "text",
    [
        pytest.param("Receipt is for two people.\nOnly one was on the trip.", id="line-break"),
        pytest.param("Receipt is for two people.\r\nOnly one was on the trip.", id="crlf"),
        pytest.param("Item\tAmount", id="tab"),
    ],
)
def test_a_reason_keeps_its_line_breaks_and_tabs(text):
    assert rules.clean_note(text) == text
