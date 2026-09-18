"""`socket.missing` — the closed loop, in eleven lines.

Design declares `SOCKET_muzzle_l` → art places an empty with that name → this
rule reads `MeshFacts.empties` and fails the export if it is missing → code never
discovers at integration time that the VFX has nothing to attach to.

The rule reads the sockets **design declared**, resolved into
:attr:`EffectiveSpec.required_sockets`, not a separate engineering list. That is
the whole point: a designer's requirement becomes a mechanically enforced gate
without an engineer restating it, and there is no second list to drift.

An attachment point nobody required is not a violation. Art is allowed to place
helpers; the specification says what must exist, never what may not.
"""

from __future__ import annotations

from collections.abc import Iterable

from cybercanon.domain.effective_spec import EffectiveSpec
from cybercanon.domain.mesh_facts import FactKind, MeshFacts
from cybercanon.domain.violations import Severity, Violation

SOCKET_MISSING = "socket.missing"
SOCKET_MISSING_SEVERITY = Severity.ERROR
SOCKET_MISSING_CONSUMES = frozenset({FactKind.EMPTIES})


def check_sockets(spec: EffectiveSpec, facts: MeshFacts) -> Iterable[Violation]:
    """One violation per declared socket with no attachment point in the export."""
    present = set(facts.empties)
    return tuple(
        _missing(spec, socket) for socket in spec.required_sockets if socket not in present
    )


def _missing(spec: EffectiveSpec, socket: str) -> Violation:
    return Violation(
        rule_id=SOCKET_MISSING,
        severity=SOCKET_MISSING_SEVERITY,
        subject=socket,
        message=(
            f"{spec.asset_id}: design declares socket {socket!r} and the export "
            "contains no attachment point of that name"
        ),
        observed="absent",
        expected=f"an attachment point named {socket}",
    )


__all__ = [
    "SOCKET_MISSING",
    "SOCKET_MISSING_CONSUMES",
    "SOCKET_MISSING_SEVERITY",
    "check_sockets",
]
