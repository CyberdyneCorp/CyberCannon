"""Tasks 2.1-2.5 — every domain type is a frozen value object, and violations read.

The sweep is over the package rather than a list: a value object added tomorrow
without `frozen=True` fails this test the day it lands. Shared mutable state
between rules is the failure D2 rejected a class hierarchy to avoid, and a
mutable spec object is the same bug one level up.
"""

from __future__ import annotations

import dataclasses
import importlib
import pkgutil

import pytest

import cybercanon.domain
from cybercanon.domain.violations import Severity, SpecViolation, errors


def domain_dataclasses() -> list[type]:
    found: dict[str, type] = {}
    for module_info in pkgutil.walk_packages(
        cybercanon.domain.__path__, prefix=f"{cybercanon.domain.__name__}."
    ):
        module = importlib.import_module(module_info.name)
        for name in dir(module):
            value = getattr(module, name)
            if isinstance(value, type) and dataclasses.is_dataclass(value):
                found[f"{value.__module__}.{value.__qualname__}"] = value
    return [found[key] for key in sorted(found)]


def test_the_domain_declares_value_objects_at_all() -> None:
    """Non-vacuity: the sweep below would pass on an empty package."""
    assert len(domain_dataclasses()) >= 10


@pytest.mark.parametrize(
    "value_object", domain_dataclasses(), ids=lambda item: f"{item.__module__}.{item.__name__}"
)
def test_every_domain_value_object_is_frozen(value_object: type) -> None:
    assert value_object.__dataclass_params__.frozen, (  # type: ignore[attr-defined]
        f"{value_object.__module__}.{value_object.__name__} is mutable; the spec "
        "contract is a value, and a mutable one is shared state between rules."
    )


def test_only_an_error_fails_a_run() -> None:
    error = SpecViolation(
        rule_id="spec.unknown_status",
        severity=Severity.ERROR,
        subject="status",
        message="status 'wip' is not one of the allowed values",
    )
    warning = dataclasses.replace(error, severity=Severity.WARNING)

    assert error.is_error
    assert not warning.is_error
    assert errors((warning, error, warning)) == (error,)
    assert errors(()) == ()


def test_a_severity_renders_as_the_word_a_project_configures() -> None:
    assert (str(Severity.ERROR), str(Severity.WARNING)) == ("error", "warning")
