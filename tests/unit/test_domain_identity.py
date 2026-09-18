"""Tasks 1.1 and 1.3 — actors, roles, agents, and attribution that cannot be empty.

The domain knows a person and an instrument and nothing about credentials, so
every assertion here is over hand-built values with no provider, no file and no
network. The load-bearing test is the last group: D5 requires that *no
constructor path* produces an attribution without an actor, which is a claim
about the type rather than about a validation somebody remembers to call.
"""

from __future__ import annotations

import dataclasses

import pytest

from cybercanon.domain.identity import (
    LOCAL_ACTOR_ID,
    UNMAPPED_MARK,
    Actor,
    ActorId,
    ActorKind,
    AgentId,
    Attribution,
    Role,
    attribute,
    local_actor,
    unmapped_actor,
)

PROJECT = "cyberdyne-game"
SUBJECT = "auth|rafa"
EMAIL = "rafa@cyberdyne.com"
BLENDER = AgentId("blender-agent")


def a_person(**overrides: object) -> Actor:
    fields: dict[str, object] = {
        "id": ActorId(SUBJECT),
        "display_name": "Rafa",
        "roles": (Role.ARTIST,),
        "projects": (PROJECT,),
    }
    fields.update(overrides)
    return Actor(**fields)  # type: ignore[arg-type]


# --------------------------------------------------------------------------
# Role — the defined set, and reading a declared one back
# --------------------------------------------------------------------------


def test_the_role_set_is_exactly_the_four_disciplines() -> None:
    assert Role.values() == ("ART_DIRECTOR", "ARTIST", "DESIGNER", "ENGINEER")


@pytest.mark.parametrize("declared", ["ARTIST", "artist", " Artist "])
def test_a_declared_role_is_read_case_insensitively(declared: str) -> None:
    assert Role.from_value(declared) is Role.ARTIST


@pytest.mark.parametrize("declared", ["BOSS", "lead artist", ""])
def test_a_role_outside_the_set_reads_as_no_role_rather_than_raising(declared: str) -> None:
    """A parse error would deny the reader every other finding in the same run."""
    assert Role.from_value(declared) is None


def test_a_role_renders_as_the_word_the_mapping_declares() -> None:
    assert str(Role.ART_DIRECTOR) == "ART_DIRECTOR"


# --------------------------------------------------------------------------
# Identifiers
# --------------------------------------------------------------------------


@pytest.mark.parametrize("value", ["", " ", " auth|rafa", "auth rafa"])
def test_an_actor_id_refuses_empty_padded_or_spaced_values(value: str) -> None:
    with pytest.raises(ValueError, match="actor id"):
        ActorId(value)


@pytest.mark.parametrize("value", ["", " ", " blender-agent"])
def test_an_agent_id_refuses_empty_or_padded_values(value: str) -> None:
    with pytest.raises(ValueError, match="agent id"):
        AgentId(value)


def test_identifiers_render_as_their_value() -> None:
    assert (str(ActorId(SUBJECT)), str(BLENDER)) == (SUBJECT, "blender-agent")


# --------------------------------------------------------------------------
# Actor — roles, projects, and how a surface names one
# --------------------------------------------------------------------------


def test_an_actor_holds_only_the_roles_it_was_resolved_with() -> None:
    actor = a_person()

    assert actor.holds(Role.ARTIST)
    assert not actor.holds(Role.ART_DIRECTOR)


def test_an_actor_sees_only_the_projects_it_was_resolved_with() -> None:
    actor = a_person()

    assert actor.may_see(PROJECT)
    assert not actor.may_see("another-game")


def test_a_mapped_person_is_named_by_their_display_name() -> None:
    assert a_person().display == "Rafa"
    assert not a_person().is_unmapped


def test_the_local_actor_reads_this_project_and_holds_no_role() -> None:
    """D4 — reads work with no credential; nothing needing a role does."""
    actor = local_actor(PROJECT)

    assert actor.kind is ActorKind.LOCAL
    assert actor.id.value == LOCAL_ACTOR_ID
    assert actor.roles == ()
    assert actor.may_see(PROJECT)


def test_an_unmapped_actor_carries_the_raw_email_and_no_roles() -> None:
    """D14 — authorship is never dropped, and never quietly given to someone."""
    actor = unmapped_actor("RAFA@Cyberdyne.com")

    assert actor.is_unmapped
    assert actor.unmapped_as == "RAFA@Cyberdyne.com", "the address is kept verbatim"
    assert actor.roles == ()
    assert actor.projects == ()


def test_every_presentation_of_an_unmapped_actor_says_so() -> None:
    presented = unmapped_actor(EMAIL).display

    assert EMAIL in presented
    assert UNMAPPED_MARK in presented


def test_an_unmapped_actor_must_carry_something_to_report() -> None:
    with pytest.raises(ValueError, match="identifier"):
        unmapped_actor("   ")


# --------------------------------------------------------------------------
# Attribution (D5) — the actor slot has no way of being empty
# --------------------------------------------------------------------------


def test_an_attribution_names_the_person_and_the_instrument() -> None:
    attribution = Attribution(actor=ActorId(SUBJECT), via=BLENDER)

    assert attribution.responsible == ActorId(SUBJECT)
    assert attribution.instrument == BLENDER
    assert attribution.is_automated
    assert str(attribution) == "auth|rafa, via blender-agent"


def test_a_person_acting_directly_has_no_instrument() -> None:
    attribution = Attribution(actor=ActorId(SUBJECT))

    assert not attribution.is_automated
    assert attribution.instrument is None
    assert str(attribution) == SUBJECT


def test_the_actor_slot_has_no_default() -> None:
    """The type refuses before any validation is reached."""
    field = next(f for f in dataclasses.fields(Attribution) if f.name == "actor")

    assert field.default is dataclasses.MISSING
    assert field.default_factory is dataclasses.MISSING


def test_no_constructor_path_produces_an_attribution_without_an_actor() -> None:
    """D5 — every way in, including the ones that go around the constructor."""
    with pytest.raises(TypeError):
        Attribution()  # type: ignore[call-arg]
    with pytest.raises(ValueError, match="accountable actor"):
        Attribution(actor=None)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="accountable actor"):
        Attribution(actor=SUBJECT)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="accountable actor"):
        dataclasses.replace(Attribution(actor=ActorId(SUBJECT)), actor=None)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="accountable actor"):
        attribute(None)


def test_an_instrument_is_an_agent_or_nothing() -> None:
    with pytest.raises(ValueError, match="instrument"):
        Attribution(actor=ActorId(SUBJECT), via="blender-agent")  # type: ignore[arg-type]


def test_attributing_accepts_a_resolved_actor_or_its_id() -> None:
    from_actor = attribute(a_person(), BLENDER)
    from_id = attribute(ActorId(SUBJECT), BLENDER)

    assert from_actor == from_id
