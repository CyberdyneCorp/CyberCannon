"""Tasks 1.5-1.7 — the actor mapping, resolved in both directions, with no file.

The mapping is domain data (D12): these tests build :class:`ActorMapping` values
by hand, which is the same boundary that lets the validator suite run over
hand-built `MeshFacts`. Nothing here parses YAML or touches disk.

The three properties the specification fixes are asserted separately because
they fail separately: both directions answer from one mapping, email comparison
ignores case, and an unmatched address becomes an explicitly unknown actor
rather than a null, an exception or the nearest similar person.
"""

from __future__ import annotations

import inspect

import pytest

from cybercanon.domain.actors import (
    EMPTY_MAPPING,
    ActorBinding,
    ActorMapping,
    GitAuthor,
    actor_for,
    binding_for_email,
    binding_for_subject,
    git_author_for,
    normalize_email,
    resolve_git_author,
    resolve_subject,
    unmapped_authors,
)
from cybercanon.domain.identity import Actor, Role

SUBJECT = "auth|rafa"
WORK_EMAIL = "rafa@cyberdyne.com"
PERSONAL_EMAIL = "rafa@personal.dev"
NEAR_MISS = "r.santos@cyberdyne.com"
STRANGER = "contractor@elsewhere.io"

RAFA = ActorBinding(
    subject=SUBJECT,
    display_name="Rafa",
    emails=(WORK_EMAIL, PERSONAL_EMAIL),
    chat_handle="@rafa",
    default_role="ARTIST",
)
ANA = ActorBinding(
    subject="auth|ana",
    display_name="Ana",
    emails=("ana@cyberdyne.com",),
    default_role="ART_DIRECTOR",
)

MAPPING = ActorMapping((RAFA, ANA))


# --------------------------------------------------------------------------
# One entry, two identities
# --------------------------------------------------------------------------


def test_an_entry_carries_both_identities_and_the_defaults() -> None:
    assert RAFA.primary_email == WORK_EMAIL
    assert RAFA.role is Role.ARTIST
    assert RAFA.chat_handle == "@rafa"
    assert RAFA.keys == (WORK_EMAIL, PERSONAL_EMAIL)


@pytest.mark.parametrize("identifier", [SUBJECT, WORK_EMAIL, PERSONAL_EMAIL])
def test_the_subject_and_either_email_resolve_to_the_same_actor(identifier: str) -> None:
    resolved = (
        resolve_subject(MAPPING, identifier)
        if identifier == SUBJECT
        else resolve_git_author(MAPPING, identifier)
    )

    assert resolved == actor_for(RAFA)
    assert resolved.display_name == "Rafa"
    assert resolved.roles == (Role.ARTIST,)


def test_an_entry_with_no_known_role_yields_an_actor_with_no_roles() -> None:
    """The defect is reported by the checks; resolution stays total."""
    binding = ActorBinding(
        subject="auth|x", display_name="X", emails=("x@y.z",), default_role="BOSS"
    )

    assert actor_for(binding).roles == ()


# --------------------------------------------------------------------------
# Both directions, one mapping
# --------------------------------------------------------------------------


@pytest.mark.parametrize("written", [WORK_EMAIL, "RAFA@Cyberdyne.com", "  rafa@CYBERDYNE.com "])
def test_a_commit_author_is_recognised_whatever_case_it_was_written_in(written: str) -> None:
    assert resolve_git_author(MAPPING, written) == actor_for(RAFA)


def test_the_git_identity_for_a_person_is_their_name_and_first_email() -> None:
    author = git_author_for(MAPPING, actor_for(RAFA))

    assert author == GitAuthor(name="Rafa", email=WORK_EMAIL)
    assert str(author) == f"Rafa <{WORK_EMAIL}>"
    assert author is not None and author.key == WORK_EMAIL


def test_the_round_trip_returns_the_original_actor() -> None:
    original = actor_for(RAFA)

    author = git_author_for(MAPPING, original)

    assert author is not None
    assert resolve_git_author(MAPPING, author.email) == original


def test_a_person_with_no_mapped_git_identity_has_none_to_commit_with() -> None:
    """The commit surface refuses; reading is unaffected."""
    unbound = Actor(id=actor_for(ANA).id, display_name="Ana")
    mapping = ActorMapping((ActorBinding(subject="auth|ana", display_name="Ana"),))

    assert git_author_for(mapping, unbound) is None


def test_lookup_helpers_answer_the_two_directions_from_the_same_entries() -> None:
    assert binding_for_subject(MAPPING, SUBJECT) is RAFA
    assert binding_for_email(MAPPING, "RAFA@Personal.dev") is RAFA
    assert binding_for_subject(MAPPING, "auth|nobody") is None
    assert binding_for_email(MAPPING, STRANGER) is None


def test_an_email_is_compared_trimmed_and_lower_cased() -> None:
    assert normalize_email("  RAFA@Cyberdyne.com ") == WORK_EMAIL


# --------------------------------------------------------------------------
# The unmapped path (D14)
# --------------------------------------------------------------------------


def test_an_unmatched_email_resolves_to_an_unknown_actor_carrying_it() -> None:
    resolved = resolve_git_author(MAPPING, STRANGER)

    assert resolved.is_unmapped
    assert resolved.unmapped_as == STRANGER
    assert resolved.roles == ()
    assert STRANGER in resolved.display and "unmapped" in resolved.display


def test_a_near_miss_is_never_resolved_to_the_similar_person() -> None:
    resolved = resolve_git_author(MAPPING, NEAR_MISS)

    assert resolved.is_unmapped
    assert resolved != actor_for(RAFA)
    assert resolved.unmapped_as == NEAR_MISS


def test_an_unknown_subject_resolves_to_an_unknown_actor_too() -> None:
    resolved = resolve_subject(MAPPING, "auth|nobody")

    assert resolved.is_unmapped
    assert resolved.unmapped_as == "auth|nobody"


def test_a_project_with_no_mapping_resolves_every_author_as_unmapped() -> None:
    assert EMPTY_MAPPING.is_empty
    assert resolve_git_author(EMPTY_MAPPING, WORK_EMAIL).is_unmapped
    assert not MAPPING.is_empty


@pytest.mark.parametrize("resolution", [resolve_git_author, resolve_subject])
def test_no_actor_resolution_signature_can_return_nothing(resolution: object) -> None:
    """D14 — an optional return would put the requirement at every call site."""
    annotation = inspect.signature(resolution).return_annotation  # type: ignore[arg-type]

    assert annotation == "Actor", f"{resolution} may return something other than an actor"


def test_the_unmapped_authors_of_a_project_are_listed_once_each() -> None:
    found = unmapped_authors(MAPPING, (STRANGER, WORK_EMAIL, "CONTRACTOR@Elsewhere.io", NEAR_MISS))

    assert tuple(actor.unmapped_as for actor in found) == (STRANGER, NEAR_MISS)


def test_an_unmapped_author_still_answers_the_git_identity_it_came_from() -> None:
    """The round trip holds for people the mapping does not know yet."""
    resolved = resolve_git_author(MAPPING, STRANGER)

    author = git_author_for(MAPPING, resolved)

    assert author is not None and author.email == STRANGER
    assert resolve_git_author(MAPPING, author.email) == resolved
