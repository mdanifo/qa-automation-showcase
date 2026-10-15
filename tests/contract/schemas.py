"""Load the JSON Schemas in contracts/ and check responses against them.

Every schema in contracts/ is registered under its file name, so one schema can
point at another with ``"$ref": "common.schema.json#/$defs/money"``. Formats
that the standard library can check (``date``) are enforced; timestamps are
pinned with a pattern instead, because ``date-time`` needs an extra package.

    assert problems(resp.json(), "claim") == []

A failing assertion lists every mismatch with its location, for example
``amount: 42.5 is not of type 'string'``.
"""

from __future__ import annotations

import json
from functools import cache
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, ValidationError
from referencing import Registry, Resource

CONTRACTS_DIR = Path(__file__).resolve().parents[2] / "contracts"
SUFFIX = ".schema.json"


def schema_names() -> list[str]:
    """The name of every schema in contracts/ (``claim`` for claim.schema.json), sorted."""
    return sorted(path.name.removesuffix(SUFFIX) for path in CONTRACTS_DIR.glob(f"*{SUFFIX}"))


def load(name: str) -> dict[str, Any]:
    """The parsed schema ``contracts/<name>.schema.json``."""
    return json.loads((CONTRACTS_DIR / f"{name}{SUFFIX}").read_text(encoding="utf-8"))


@cache
def _registry() -> Registry:
    return Registry().with_resources(
        (f"{name}{SUFFIX}", Resource.from_contents(load(name))) for name in schema_names()
    )


@cache
def validator(name: str) -> Draft202012Validator:
    """A validator for ``contracts/<name>.schema.json`` that resolves refs to the other files."""
    return Draft202012Validator(
        load(name),
        registry=_registry(),
        format_checker=Draft202012Validator.FORMAT_CHECKER,
    )


def _where(error: ValidationError) -> str:
    return ".".join(str(part) for part in error.absolute_path) or "(root)"


def problems(instance: Any, name: str) -> list[str]:
    """Every way ``instance`` breaks schema ``name``, as ``path: message``. Empty when it fits."""
    errors = validator(name).iter_errors(instance)
    return sorted(f"{_where(error)}: {error.message}" for error in errors)


def failed_checks(instance: Any, name: str) -> list[tuple[str, str]]:
    """Every failed check as ``(path, keyword)``, such as ``("amount", "type")``.

    For tests of the schemas themselves: the keyword names the rule that fired
    and, unlike the message text, does not change between jsonschema releases.
    """
    return sorted(
        (_where(error), str(error.validator)) for error in validator(name).iter_errors(instance)
    )
