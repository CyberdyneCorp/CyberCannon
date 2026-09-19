"""Task 1.8 — the mapping's structural defects, reported like any other violation.

Each defect is asserted on the violation a reader acts on: the rule id a project
configures severity against, the subject naming the offending entry, and a
message carrying the values somebody needs in order to fix the file. The
violations are ordinary :class:`SpecViolation` values so the existing lint path
prints them without learning anything about identity.
"""

from __future__ import annotations

import socket

import pytest

from cybercanon.domain.actor_checks import (
    RULE_DUPLICATE_EMAIL,
    RULE_DUPLICATE_SUBJECT,
    RULE_IDS,
    RULE_NO_EMAIL,
    RULE_PROVIDER_DISAGREEMENT,
    RULE_UNKNOWN_ROLE,
    RULE_UNPARSEABLE,
    check_mapping,
    mapping_unparseable,
    provider_disagreement,
    subject_of,
)
from cybercanon.domain.actors import ACTORS_PATH, ActorBinding, ActorMapping
from cybercanon.domain.identity import Role
from cybercanon.domain.violations import Severity

SHARED_EMAIL = "rafa@cyberdyne.com"

RAFA = ActorBinding(subject="auth|rafa", display_name="Rafa", emails=(SHARED_EMAIL,))
ANA = ActorBinding(subject="auth|ana", display_name="Ana", emails=("ana@cyberdyne.com",))


def test_every_rule_is_in_the_inventory() -> None:
    assert set(RULE_IDS) == {
        RULE_DUPLICATE_SUBJECT,
        RULE_DUPLICATE_EMAIL,
        RULE_UNKNOWN_ROLE,
        RULE_NO_EMAIL,
        RULE_UNPARSEABLE,
        RULE_PROVIDER_DISAGREEMENT,
    }


def test_a_provider_disagreement_names_the_entry_and_both_lists() -> None:
    """D13 — the provider wins and the stale file entry is reported, not merged."""
    (violation,) = provider_disagreement(RAFA, ("rafa@newdomain.dev",))

    assert violation.rule_id == RULE_PROVIDER_DISAGREEMENT
    assert violation.severity is Severity.WARNING
    assert "auth|rafa" in violation.message
    assert SHARED_EMAIL in violation.message
    assert "rafa@newdomain.dev" in violation.message
    assert violation.subject.startswith(subject_of(RAFA))


def test_a_well_formed_mapping_reports_nothing() -> None:
    assert check_mapping(ActorMapping((RAFA, ANA))) == ()
    assert check_mapping(ActorMapping()) == ()


def test_a_duplicate_email_names_the_address_and_both_entries() -> None:
    borrowed = ActorBinding(subject="auth|ana", display_name="Ana", emails=("RAFA@Cyberdyne.com",))

    (violation,) = check_mapping(ActorMapping((RAFA, borrowed)))

    assert violation.rule_id == RULE_DUPLICATE_EMAIL
    assert violation.severity is Severity.ERROR
    assert SHARED_EMAIL in violation.message
    assert "auth|rafa" in violation.message
    assert "auth|ana" in violation.message


def test_a_duplicate_subject_names_the_subject() -> None:
    twin = ActorBinding(subject="auth|rafa", display_name="Rafael", emails=("other@x.dev",))

    (violation,) = check_mapping(ActorMapping((RAFA, twin)))

    assert violation.rule_id == RULE_DUPLICATE_SUBJECT
    assert "auth|rafa" in violation.message
    assert violation.subject == "actors[auth|rafa]"


def test_an_unknown_role_names_the_entry_and_the_available_roles() -> None:
    entry = ActorBinding(
        subject="auth|zoe", display_name="Zoe", emails=("zoe@x.dev",), default_role="BOSS"
    )

    (violation,) = check_mapping(ActorMapping((entry,)))

    assert violation.rule_id == RULE_UNKNOWN_ROLE
    assert violation.subject == f"{subject_of(entry)}.default_role"
    assert "BOSS" in violation.message
    for role in Role.values():
        assert role in violation.message


@pytest.mark.parametrize("emails", [(), ("",), ("  ",)])
def test_an_entry_with_no_git_email_is_a_violation(emails: tuple[str, ...]) -> None:
    entry = ActorBinding(subject="auth|zoe", display_name="Zoe", emails=emails)

    (violation,) = check_mapping(ActorMapping((entry,)))

    assert violation.rule_id == RULE_NO_EMAIL
    assert violation.subject == "actors[auth|zoe].emails"
    assert "auth|zoe" in violation.message


def test_a_well_known_role_written_in_lower_case_is_not_a_violation() -> None:
    entry = ActorBinding(
        subject="auth|zoe", display_name="Zoe", emails=("zoe@x.dev",), default_role="artist"
    )

    assert check_mapping(ActorMapping((entry,))) == ()


def test_an_unparseable_mapping_is_reported_rather_than_raised() -> None:
    (violation,) = mapping_unparseable("line 4: found unexpected ':'")

    assert violation.rule_id == RULE_UNPARSEABLE
    assert violation.subject == ACTORS_PATH
    assert ACTORS_PATH in violation.message
    assert "line 4" in violation.message


def test_several_defects_are_all_reported_in_one_pass() -> None:
    broken = ActorMapping(
        (
            RAFA,
            ActorBinding(subject="auth|rafa", display_name="R", emails=(SHARED_EMAIL,)),
            ActorBinding(subject="auth|zoe", display_name="Zoe", default_role="BOSS"),
        )
    )

    reported = {violation.rule_id for violation in check_mapping(broken)}

    assert reported == {
        RULE_DUPLICATE_SUBJECT,
        RULE_DUPLICATE_EMAIL,
        RULE_UNKNOWN_ROLE,
        RULE_NO_EMAIL,
    }


def test_validation_needs_neither_identity_nor_network(monkeypatch: pytest.MonkeyPatch) -> None:
    """The mapping is validated wherever the specifications are — offline."""

    def refuse(*args: object, **kwargs: object) -> None:
        raise AssertionError("validating the actor mapping opened a network connection")

    monkeypatch.setattr(socket, "socket", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)
    borrowed = ActorBinding(subject="auth|ana", display_name="Ana", emails=(SHARED_EMAIL,))

    violations = check_mapping(ActorMapping((RAFA, borrowed)))

    assert [violation.rule_id for violation in violations] == [RULE_DUPLICATE_EMAIL]
