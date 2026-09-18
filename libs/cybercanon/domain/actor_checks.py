"""Structural checks over the actor mapping — pure functions, no I/O.

`.canon/actors.yaml` is authored content, so it is validated the way every other
authored file is: small pure functions returning
:class:`~cybercanon.domain.violations.SpecViolation` values with the same
identifier, severity, subject and message shape as any other finding. That is
the requirement, not a convenience — the mapping's defects must surface in the
existing lint path rather than in a report only an identity feature knows how to
print, and validation must need neither identity nor network.

Four defects are visible in a parsed mapping and one is not:

* two entries declaring the same identity subject;
* two entries listing the same git author email, which would make one commit
  resolve to two people;
* a `default_role` outside the defined role set;
* an entry with no git author email, which binds nothing and so explains nothing.

The fifth — a file that cannot be parsed at all — is discovered by the adapter
that reads it, so :func:`mapping_unparseable` is the factory that adapter calls.
The violation belongs here because its shape is a domain decision; the failure
that produced it is not.
"""

from __future__ import annotations

from collections.abc import Callable

from cybercanon.domain.actors import ACTORS_PATH, ActorBinding, ActorMapping
from cybercanon.domain.identity import Role
from cybercanon.domain.violations import Severity, SpecViolation

RULE_DUPLICATE_SUBJECT = "actors.duplicate_subject"
RULE_DUPLICATE_EMAIL = "actors.duplicate_email"
RULE_UNKNOWN_ROLE = "actors.unknown_role"
RULE_NO_EMAIL = "actors.no_email"
RULE_UNPARSEABLE = "actors.unparseable"

RULE_IDS = (
    RULE_DUPLICATE_SUBJECT,
    RULE_DUPLICATE_EMAIL,
    RULE_UNKNOWN_ROLE,
    RULE_NO_EMAIL,
    RULE_UNPARSEABLE,
)
"""Every mapping rule, so the inventory can be printed and asserted."""


def subject_of(binding: ActorBinding) -> str:
    """How a violation names the offending entry — `actors[auth|rafa]`."""
    return f"actors[{binding.subject}]"


def check_duplicate_subjects(mapping: ActorMapping) -> tuple[SpecViolation, ...]:
    """One identity subject, one entry: a subject twice is two people or none."""
    counted = _grouped(mapping, lambda binding: (binding.subject,))
    return tuple(
        SpecViolation(
            rule_id=RULE_DUPLICATE_SUBJECT,
            severity=Severity.ERROR,
            subject=f"actors[{subject}]",
            message=(
                f"identity subject {subject!r} is declared by {len(entries)} entries "
                f"({_listed(entries)}); each subject binds exactly one person"
            ),
            observed=_listed(entries),
            expected="one entry per identity subject",
        )
        for subject, entries in counted
    )


def check_duplicate_emails(mapping: ActorMapping) -> tuple[SpecViolation, ...]:
    """One git author email, one entry: otherwise a commit resolves to two people."""
    counted = _grouped(mapping, lambda binding: binding.keys)
    return tuple(
        SpecViolation(
            rule_id=RULE_DUPLICATE_EMAIL,
            severity=Severity.ERROR,
            subject=f"actors[{email}]",
            message=(
                f"git author email {email!r} is listed by {len(entries)} entries "
                f"({_listed(entries)}); a commit must resolve to one person"
            ),
            observed=_listed(entries),
            expected="one entry per git author email",
        )
        for email, entries in counted
    )


def check_default_roles(mapping: ActorMapping) -> tuple[SpecViolation, ...]:
    """A `default_role` outside the defined set names the roles that exist."""
    allowed = ", ".join(Role.values())
    return tuple(
        SpecViolation(
            rule_id=RULE_UNKNOWN_ROLE,
            severity=Severity.ERROR,
            subject=f"{subject_of(binding)}.default_role",
            message=(
                f"entry {binding.subject!r} declares the default role "
                f"{binding.default_role!r}, which is not one of: {allowed}"
            ),
            observed=binding.default_role,
            expected=allowed,
        )
        for binding in mapping.bindings
        if binding.default_role and binding.role is None
    )


def check_emails_declared(mapping: ActorMapping) -> tuple[SpecViolation, ...]:
    """An entry with no git author email binds nothing, so it explains nothing."""
    return tuple(
        SpecViolation(
            rule_id=RULE_NO_EMAIL,
            severity=Severity.ERROR,
            subject=f"{subject_of(binding)}.emails",
            message=(
                f"entry {binding.subject!r} declares no git author email, so no "
                "commit can ever resolve to it"
            ),
            observed="no email",
            expected="at least one git author email",
        )
        for binding in mapping.bindings
        if not [email for email in binding.emails if email.strip()]
    )


def mapping_unparseable(detail: str, path: str = ACTORS_PATH) -> tuple[SpecViolation, ...]:
    """The mapping could not be read at all — reported, never raised.

    Called by the adapter that failed to parse the file. A project whose mapping
    is broken still reads its specifications; it simply reports every author as
    unmapped until somebody fixes the file.
    """
    return (
        SpecViolation(
            rule_id=RULE_UNPARSEABLE,
            severity=Severity.ERROR,
            subject=path,
            message=f"{path} could not be parsed: {detail}",
            observed=detail,
            expected="a readable actor mapping",
        ),
    )


def check_mapping(mapping: ActorMapping) -> tuple[SpecViolation, ...]:
    """Every structural check the parsed mapping can answer on its own.

    Needs no identity service, no network and no file — which is the point: the
    mapping is validated wherever the specifications are.
    """
    return (
        *check_duplicate_subjects(mapping),
        *check_duplicate_emails(mapping),
        *check_default_roles(mapping),
        *check_emails_declared(mapping),
    )


def _grouped(
    mapping: ActorMapping, keys_of: Callable[[ActorBinding], tuple[str, ...]]
) -> tuple[tuple[str, tuple[str, ...]], ...]:
    """Keys declared by more than one entry, with the subjects declaring them."""
    entries: dict[str, list[str]] = {}
    for binding in mapping.bindings:
        for key in keys_of(binding):
            entries.setdefault(key, []).append(binding.subject)
    return tuple(
        (key, tuple(subjects)) for key, subjects in sorted(entries.items()) if len(subjects) > 1
    )


def _listed(subjects: tuple[str, ...]) -> str:
    return ", ".join(repr(subject) for subject in subjects)


__all__ = [
    "RULE_DUPLICATE_EMAIL",
    "RULE_DUPLICATE_SUBJECT",
    "RULE_IDS",
    "RULE_NO_EMAIL",
    "RULE_UNKNOWN_ROLE",
    "RULE_UNPARSEABLE",
    "check_default_roles",
    "check_duplicate_emails",
    "check_duplicate_subjects",
    "check_emails_declared",
    "check_mapping",
    "mapping_unparseable",
    "subject_of",
]
