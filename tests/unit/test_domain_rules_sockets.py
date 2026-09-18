"""Task 3.8 — `socket.missing`, the closed loop the product exists for.

Design declares two sockets, the export carries one: exactly one violation,
naming the missing one. An extra attachment point nobody asked for is not a
violation — the specification says what must exist, never what may not.
"""

from __future__ import annotations

from cybercanon.domain.asset import Asset, AssetId
from cybercanon.domain.design import Design, Socket
from cybercanon.domain.effective_spec import EffectiveSpec, merge
from cybercanon.domain.format_matrix import facts_for
from cybercanon.domain.mesh_facts import MeshFormat
from cybercanon.domain.rules import sockets
from cybercanon.domain.violations import Severity

MUZZLE = "SOCKET_muzzle_l"
JET = "SOCKET_jet_r"


def a_spec(*required: str) -> EffectiveSpec:
    return EffectiveSpec(asset_id="mech_scout", required_sockets=required)


def an_export(*empties: str):
    return facts_for(MeshFormat.GLB, empties=empties)


def test_exactly_one_violation_names_the_missing_socket() -> None:
    (violation,) = tuple(sockets.check_sockets(a_spec(MUZZLE, JET), an_export(JET)))

    assert violation.rule_id == sockets.SOCKET_MISSING
    assert violation.severity is Severity.ERROR
    assert violation.subject == MUZZLE
    assert MUZZLE in violation.message
    assert JET not in violation.message


def test_every_declared_socket_present_is_silence() -> None:
    assert tuple(sockets.check_sockets(a_spec(MUZZLE, JET), an_export(JET, MUZZLE))) == ()


def test_an_extra_attachment_point_is_not_a_violation() -> None:
    assert tuple(sockets.check_sockets(a_spec(MUZZLE), an_export(MUZZLE, "SOCKET_spare"))) == ()


def test_declaring_no_sockets_is_nothing_to_check() -> None:
    assert tuple(sockets.check_sockets(a_spec(), an_export("SOCKET_spare"))) == ()


def test_the_rule_reads_the_design_block_not_a_separate_engineering_list() -> None:
    """The loop only closes because these are the *declared* sockets, merged once."""
    asset = Asset(
        id=AssetId("mech_scout"),
        name="Scout Mech",
        design=Design(sockets=(Socket(name=MUZZLE, purpose="muzzle flash"),)),
    )

    (violation,) = tuple(sockets.check_sockets(merge(asset), an_export()))

    assert violation.subject == MUZZLE
