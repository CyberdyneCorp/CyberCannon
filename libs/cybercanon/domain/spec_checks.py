"""Structural checks over a specification file — pure functions, no I/O.

These answer the one question `asset-spec` requires to be answerable offline:
is this specification file internally consistent? They need the file and the
project configuration and nothing else — no identity, no network, no derived
store, no export. Each is a small pure function returning
:class:`~cybercanon.domain.violations.SpecViolation` values whose `subject`
names the offending field, so the CLI, the MCP surface and the web app all
report the same thing.

Two of the checks need a value the parsed :class:`~cybercanon.domain.asset.Asset`
cannot carry:

* **unknown status** operates on the declared *text*, because an `Asset` already
  holds a parsed :class:`~cybercanon.domain.status.Status` and an unknown value
  never becomes one (see :meth:`Status.from_value`);
* **duplicate id** is a project-level question — one file cannot see another —
  so it takes the declarations the store discovered, and names every file path.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from cybercanon.domain.asset import Asset, AssetId
from cybercanon.domain.constraints import Constraints
from cybercanon.domain.design import Design
from cybercanon.domain.status import Status
from cybercanon.domain.violations import Severity, SpecViolation

RULE_UNKNOWN_STATUS = "spec.unknown_status"
RULE_LODS_NOT_DESCENDING = "spec.lods_not_descending"
RULE_LOD0_OVER_TRI_BUDGET = "spec.lod0_exceeds_tri_budget"
RULE_DUPLICATE_ID = "spec.duplicate_id"
RULE_STATE_CONSTRAINS_NOTHING = "spec.state_constrains_nothing"

RULE_IDS = (
    RULE_UNKNOWN_STATUS,
    RULE_LODS_NOT_DESCENDING,
    RULE_LOD0_OVER_TRI_BUDGET,
    RULE_DUPLICATE_ID,
    RULE_STATE_CONSTRAINS_NOTHING,
)
"""Every structural rule, so the inventory can be printed and asserted."""


@dataclass(frozen=True)
class SpecDeclaration:
    """One specification file and the id it declares, as the store found them."""

    path: str
    asset_id: AssetId


def check_declared_status(declared: str) -> tuple[SpecViolation, ...]:
    """A `status` outside the ordered set is a violation naming the allowed values."""
    if Status.from_value(declared) is not None:
        return ()
    allowed = ", ".join(Status.values())
    return (
        SpecViolation(
            rule_id=RULE_UNKNOWN_STATUS,
            severity=Severity.ERROR,
            subject="status",
            message=f"status {declared!r} is not one of the allowed values: {allowed}",
            observed=declared,
            expected=allowed,
        ),
    )


def check_lods_descending(constraints: Constraints | None) -> tuple[SpecViolation, ...]:
    """`lods` is an ordered list of triangle counts, and it must descend."""
    lods = constraints.lods if constraints else ()
    ascending = [index for index in range(1, len(lods)) if lods[index] >= lods[index - 1]]
    if not ascending:
        return ()
    return (
        SpecViolation(
            rule_id=RULE_LODS_NOT_DESCENDING,
            severity=Severity.ERROR,
            subject="constraints.lods",
            message=(
                "LOD triangle counts must be descending; "
                f"LOD{ascending[0]} is not smaller than LOD{ascending[0] - 1}"
            ),
            observed=", ".join(str(count) for count in lods),
            expected="each LOD smaller than the one before it",
        ),
    )


def check_first_lod_within_tri_budget(
    constraints: Constraints | None,
) -> tuple[SpecViolation, ...]:
    """LOD0 is the asset at full detail; it cannot exceed the triangle budget."""
    if constraints is None or constraints.tri_budget is None or not constraints.lods:
        return ()
    first = constraints.lods[0]
    if first <= constraints.tri_budget:
        return ()
    return (
        SpecViolation(
            rule_id=RULE_LOD0_OVER_TRI_BUDGET,
            severity=Severity.ERROR,
            subject="constraints.lods[0]",
            message=(
                f"LOD0 declares {first} triangles, above the declared "
                f"tri_budget of {constraints.tri_budget}"
            ),
            observed=str(first),
            expected=f"at most {constraints.tri_budget}",
        ),
    )


def check_states_are_checkable(
    design: Design | None, clip_naming: str | None = None
) -> tuple[SpecViolation, ...]:
    """A state resolves to a required clip or declares itself unanimated (D12)."""
    states = design.states if design else ()
    return tuple(
        SpecViolation(
            rule_id=RULE_STATE_CONSTRAINS_NOTHING,
            severity=Severity.ERROR,
            subject=f"design.states[{state.name}]",
            message=(
                f"state {state.name!r} resolves to no animation clip and does "
                "not declare itself unanimated, so it constrains nothing"
            ),
            observed="no clip, no naming convention, no 'animated: false'",
            expected="an explicit clip, a clip naming convention, or 'animated: false'",
        )
        for state in states
        if state.constrains_nothing(clip_naming)
    )


def check_duplicate_ids(
    declarations: Iterable[SpecDeclaration],
) -> tuple[SpecViolation, ...]:
    """An `id` is unique within its project; a clash names every file declaring it."""
    paths_by_id: dict[str, list[str]] = {}
    for declaration in declarations:
        paths_by_id.setdefault(declaration.asset_id.value, []).append(declaration.path)
    return tuple(
        _duplicate_id_violation(value, sorted(paths))
        for value, paths in sorted(paths_by_id.items())
        if len(paths) > 1
    )


def _duplicate_id_violation(value: str, paths: list[str]) -> SpecViolation:
    listed = ", ".join(paths)
    return SpecViolation(
        rule_id=RULE_DUPLICATE_ID,
        severity=Severity.ERROR,
        subject="id",
        message=f"id {value!r} is declared by more than one specification file: {listed}",
        observed=listed,
        expected="one specification file per id within a project",
    )


def check_asset(asset: Asset, clip_naming: str | None = None) -> tuple[SpecViolation, ...]:
    """Every structural check one specification file can answer on its own.

    `clip_naming` is the convention in force — the asset's own if it declares
    one, otherwise the project default. Duplicate ids are not here: no single
    file can see another.
    """
    convention = asset.clip_naming or clip_naming
    return (
        *check_lods_descending(asset.constraints),
        *check_first_lod_within_tri_budget(asset.constraints),
        *check_states_are_checkable(asset.design, convention),
    )


__all__ = [
    "RULE_DUPLICATE_ID",
    "RULE_IDS",
    "RULE_LOD0_OVER_TRI_BUDGET",
    "RULE_LODS_NOT_DESCENDING",
    "RULE_STATE_CONSTRAINS_NOTHING",
    "RULE_UNKNOWN_STATUS",
    "SpecDeclaration",
    "check_asset",
    "check_declared_status",
    "check_duplicate_ids",
    "check_first_lod_within_tri_budget",
    "check_lods_descending",
    "check_states_are_checkable",
]
