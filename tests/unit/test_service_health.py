"""Task 2.1 — which dependency may withhold traffic, decided over values.

The rule `deployment-operations` states is one sentence — *"A service's
readiness SHALL depend only on the dependencies that service owns"* — and the
whole difficulty is that "owns" is not the same as "cannot serve without". The
index and the blob mirror are owned and rebuildable; the working copy is owned
and load-bearing; the model gateway, the identity provider and the document
platform belong to somebody else. The specification enumerates the cases and
they are enumerated here, one test each.

No process, no socket, no container: the classification is a pure function over
observations, which is exactly why it can be exhaustively checked.
"""

from __future__ import annotations

import pytest

from cybercanon.application.use_cases.service_health import (
    DOCUMENT_PLATFORM,
    IDENTITY_SERVICE,
    LANGUAGE_MODEL,
    OBJECT_STORE,
    RELIANCE,
    SEARCH_INDEX,
    WORKING_COPY,
    ComponentStatus,
    Reliance,
    available,
    describe_service_health,
    reliance_of,
    unavailable,
)

OPTIONAL = (LANGUAGE_MODEL, IDENTITY_SERVICE, DOCUMENT_PLATFORM)
REBUILDABLE = (SEARCH_INDEX, OBJECT_STORE)
EVERY = (*OPTIONAL, *REBUILDABLE, WORKING_COPY)


# --------------------------------------------------------------------------
# The classification
# --------------------------------------------------------------------------


def test_only_the_working_copy_gates_readiness() -> None:
    """The one component whose loss means this service cannot answer at all."""
    gating = {name for name, reliance in RELIANCE.items() if reliance.gates}

    assert gating == {WORKING_COPY}


@pytest.mark.parametrize("name", REBUILDABLE)
def test_rebuildable_state_is_owned_but_never_gates(name: str) -> None:
    """Git is the source of truth, so losing either is a rebuild, not an outage."""
    assert reliance_of(name) is Reliance.REBUILDABLE
    assert not reliance_of(name).gates


@pytest.mark.parametrize("name", OPTIONAL)
def test_somebody_elses_service_never_gates(name: str) -> None:
    assert reliance_of(name) is Reliance.OPTIONAL
    assert not reliance_of(name).gates


def test_an_unclassified_component_does_not_gate() -> None:
    """Guessing the other way blocks a deploy on something nobody decided about."""
    assert reliance_of("a-component-added-next-year") is Reliance.OPTIONAL


# --------------------------------------------------------------------------
# All up, owned down, optional down
# --------------------------------------------------------------------------


def test_everything_available_is_ready_and_degrades_nothing() -> None:
    health = describe_service_health([available(name) for name in EVERY])

    assert health.live
    assert health.ready
    assert health.degraded == ()
    assert health.withholding == ()


def test_an_owned_dependency_down_withholds_traffic_and_names_itself() -> None:
    health = describe_service_health(
        [available(SEARCH_INDEX), unavailable(WORKING_COPY, "volume not mounted")]
    )

    assert not health.ready
    assert health.withholding == (WORKING_COPY,)


@pytest.mark.parametrize("name", (*OPTIONAL, *REBUILDABLE))
def test_anything_else_down_stays_ready_and_reports_degraded(name: str) -> None:
    """Another team's outage — or a lost cache — may not fail a deploy."""
    health = describe_service_health([available(WORKING_COPY), unavailable(name, "refused")])

    assert health.ready
    assert health.degraded == (name,)


def test_liveness_is_a_property_of_the_process_not_of_its_dependencies() -> None:
    health = describe_service_health([unavailable(name) for name in EVERY])

    assert health.live
    assert not health.ready


def test_a_component_can_be_looked_up_by_name_with_its_detail() -> None:
    health = describe_service_health([unavailable(LANGUAGE_MODEL, "CANON_LLM_ENABLED is off")])
    found = health.named(LANGUAGE_MODEL)

    assert found is not None
    assert found.detail == "CANON_LLM_ENABLED is off"
    assert found.state == "unavailable"
    assert health.named("nothing-observed-this") is None


def test_an_observation_may_declare_its_own_reliance() -> None:
    """A component the table does not know can still be declared load-bearing."""
    declared = ComponentStatus("a-future-volume", available=False, reliance=Reliance.OWNED)

    assert describe_service_health([declared]).withholding == ("a-future-volume",)
