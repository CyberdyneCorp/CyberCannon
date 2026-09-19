"""The operation matrix: who may do what, decided here and nowhere else.

`project.md` fixes the matrix under **Gate Decisions (G4)** and fixes where it
lives: *"Group→role mapping stays configuration in the CyberdyneAuth adapter;
the matrix above is domain policy and is decided in the core."* This module is
that core. It knows an :class:`~cybercanon.domain.identity.Actor`, an
:class:`Operation` and a :class:`Subject`, and it knows nothing about tokens,
groups, claims, routers or status codes — which is what makes the whole policy
suite runnable with no identity service, no HTTP and no database.

Three shapes are worth reading before the table:

* **One entry point.** :func:`decide` answers every operation. A per-operation
  function would be pleasant right up to the fourth surface, where one of them
  gets a check the others do not and the CLI and the web app start disagreeing
  about who may accept a request.
* **A refusal names what would be required.** `asset-requests` demands it in so
  many words — *"refused ... with a message naming what would be required"* —
  so the required role travels in the rule rather than being reconstructed by
  each surface.
* **Human-only is a registry, not a habit** (D13). `HUMAN_ONLY` is an explicit
  enumeration and `MUTATING` is another, and a test walks `MUTATING` asserting
  every member declares itself one way or the other. An absence cannot be
  enforced by absence: the day somebody adds a mutating operation, the build
  fails until they say whether automation may call it.

The order of the checks matters and is fixed here rather than per operation:
tenancy, then read entitlement, then whether the operation needs a person, then
whether it needs a mapped git identity, then the role rule. Tenancy first keeps
a cross-organisation address from learning anything; the human-only check before
the role rule is what makes *"a service credential holding every role"* still a
refusal rather than an accident of how the roles were listed.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from enum import Enum

from cybercanon.domain.authorization import ALLOWED, Decision, may_read_project
from cybercanon.domain.identity import Actor, ActorId, AgentId, Role
from cybercanon.domain.tenancy import ProjectRef, project_ref

REQUIRES_PERSON = "requires a person"
"""The words a human-only refusal carries, whatever refused it."""

NEEDS_GIT_IDENTITY = (
    "has no entry in the project's actors mapping, so the change could not be "
    "attributed to a git identity"
)
"""Why an unmapped person may read everything and write nothing (D8)."""


class Operation(Enum):
    """Every operation the matrix decides, named as G4 names it.

    A closed set, and closed on purpose: an operation nobody added here has no
    policy, and a surface that invented one would be deciding for itself.
    """

    READ_PROJECT = "read_project"
    SEARCH_ASSETS = "search_assets"
    LOOKUP_ASSET = "lookup_asset"
    COMPILE_SPEC = "compile_spec"
    VALIDATE_EXPORT = "validate_export"
    CREATE_ANNOTATION = "create_annotation"
    REPLY_IN_THREAD = "reply_in_thread"
    RESOLVE_ISSUE = "resolve_issue"
    PROMOTE_TO_RULE = "promote_to_rule"
    ACCEPT_SUGGESTED_ALIAS = "accept_suggested_alias"
    TRANSITION_ASSET_STATUS = "transition_asset_status"
    RAISE_REQUEST = "raise_request"
    DECIDE_REQUEST = "decide_request"

    @classmethod
    def values(cls) -> tuple[str, ...]:
        """Every operation, in declaration order — what a message may name."""
        return tuple(member.value for member in cls)

    def __str__(self) -> str:
        return self.value


READ_ONLY: frozenset[Operation] = frozenset(
    {
        Operation.READ_PROJECT,
        Operation.SEARCH_ASSETS,
        Operation.LOOKUP_ASSET,
        Operation.COMPILE_SPEC,
        Operation.VALIDATE_EXPORT,
    }
)
"""G4's first two rows: *never role-gated*, and that is the whole rule.

Search, lookup, compilation and validation are exactly as available as reading,
which is what keeps the validator honest — the moment validating needed a role,
an artist off the VPN could not commit.
"""

MUTATING: frozenset[Operation] = frozenset(Operation) - READ_ONLY
"""Every operation that changes something. Derived, so it cannot fall behind.

A new member of :class:`Operation` is mutating unless it is listed as read-only,
which is the safe direction to be wrong in.
"""

HUMAN_ONLY: frozenset[Operation] = frozenset(
    {
        Operation.PROMOTE_TO_RULE,
        Operation.ACCEPT_SUGGESTED_ALIAS,
        Operation.DECIDE_REQUEST,
    }
)
"""The registry D13 requires: operations no automated caller may perform.

Three, each from a stated requirement rather than from taste:

* **promotion** — `project.md`: *"Promotion is never agent-callable, not even
  for an art director's agent"*, because promotion writes durable constraints;
* **accepting a suggestion** — the bridge between derived and authored content
  *is a human accepting it*, so an automated acceptance would make the bridge
  a pipe;
* **deciding a request** — `http-api` names it: *"including promoting an
  annotation to a durable rule, accepting a derived suggestion, and deciding an
  asset request"*.

Membership is checked before roles, so a service credential holding every role
is still refused. `tests/unit/test_domain_policy.py` asserts every member of
:data:`MUTATING` declares itself, which is how this list stays complete.
"""

NEEDS_GIT_MAPPING: frozenset[Operation] = frozenset(MUTATING)
"""Every write needs a mapped git identity, because every write is a commit.

D7 states the consequence and accepts it: *"because every write needs an
actors-mapping entry (D8), a person who has never been mapped cannot even accept
a request"*. Derived from :data:`MUTATING` rather than listed, so a write that
somehow escaped the mapping requirement would have to be written down as an
exception rather than acquired by forgetting.
"""


@dataclass(frozen=True)
class Subject:
    """What an operation is being performed *on*, as far as policy cares.

    Everything here is already resolved: the project it belongs to, the people
    the domain compares the actor against, and whether the actor has a git
    identity in this project's mapping. Resolving an owner's declared address
    into an :class:`~cybercanon.domain.identity.ActorId` is the application's
    job through `.canon/actors.yaml`; a policy that did it would need the
    mapping, and then the decision would stop being answerable from the actor
    alone.
    """

    project: str | ProjectRef = ""
    author: ActorId | None = None
    assignee: ActorId | None = None
    discipline_owner: ActorId | None = None
    has_git_identity: bool = True
    description: str = ""

    @property
    def ref(self) -> ProjectRef:
        """The project this subject belongs to, tenant included when it has one."""
        return project_ref(self.project)

    @property
    def named(self) -> str:
        """What a refusal calls this subject: its description, or its project."""
        return self.description or self.ref.name


Rule = Callable[[Actor, Subject], Decision]
"""One operation's role rule, evaluated after the checks every operation shares."""


def decide(
    actor: Actor,
    operation: Operation,
    subject: Subject,
    *,
    via: AgentId | None = None,
) -> Decision:
    """Whether this actor may perform this operation on this subject.

    Pure, total, and dependent on nothing but its three arguments (`via` names
    the instrument, which can only ever narrow the answer — an agent is
    permitted exactly what its person is permitted, and less).
    """
    readable = may_read_project(actor, subject.ref)
    if readable.refused or operation in READ_ONLY:
        return readable
    return _mutating(actor, operation, subject, via)


def requires_person(operation: Operation) -> bool:
    """Whether this operation is one the project reserves to a person (D13)."""
    return operation in HUMAN_ONLY


def declares_human_only(operation: Operation) -> bool:
    """Whether this operation has made the declaration D13 requires of it.

    Every operation has: a read is not mutating, and every mutating one is
    either in :data:`HUMAN_ONLY` or deliberately outside it. The function exists
    so the assertion reads as the specification phrases it — *each declares
    whether it requires a person* — rather than as a set membership test that
    passes for an operation nobody thought about.
    """
    return operation in READ_ONLY or operation in MUTATING


def _mutating(
    actor: Actor,
    operation: Operation,
    subject: Subject,
    via: AgentId | None,
) -> Decision:
    """The three checks a write adds to a read, in the order that keeps them true."""
    if requires_person(operation) and (actor.is_automation or via is not None):
        return _refuse(f"{_caller(actor, via)} may not {operation}: it {REQUIRES_PERSON}")
    if operation in NEEDS_GIT_MAPPING and not subject.has_git_identity:
        return _refuse(f"{actor.display} {NEEDS_GIT_IDENTITY}")
    return _RULES[operation](actor, subject)


def _refuse(reason: str) -> Decision:
    return Decision(allowed=False, reason=reason)


def _caller(actor: Actor, via: AgentId | None) -> str:
    """How a refusal names an automated caller: the instrument, or the actor."""
    return f"{via}, acting as {actor.display}," if via is not None else actor.display


def _anyone_who_may_read(actor: Actor, subject: Subject) -> Decision:
    """G4: *"Raise an asset request — any mapped actor with read access"*."""
    return ALLOWED


def _art_director_only(actor: Actor, subject: Subject) -> Decision:
    """G4: *"Promote to a rule — ART_DIRECTOR only"*."""
    return _role_or_refuse(actor, subject, allowed=actor.holds(Role.ART_DIRECTOR))


def _author_or_art_director(actor: Actor, subject: Subject) -> Decision:
    """G4: *"Resolve an issue — its author, or ART_DIRECTOR"*."""
    return _role_or_refuse(
        actor,
        subject,
        allowed=actor.id == subject.author or actor.holds(Role.ART_DIRECTOR),
    )


def _owner_or_art_director(actor: Actor, subject: Subject) -> Decision:
    """G4: the owner of the relevant discipline, or `ART_DIRECTOR`.

    Two rows share it — accepting a suggested alias and transitioning an asset's
    status — because G4 gives them the same rule, and two copies of one rule is
    how the two rows start differing.
    """
    return _role_or_refuse(
        actor,
        subject,
        allowed=actor.id == subject.discipline_owner or actor.holds(Role.ART_DIRECTOR),
    )


def _assignee_or_art_director(actor: Actor, subject: Subject) -> Decision:
    """G4: *"Accept or decline a request — the assigned discipline owner, or ART_DIRECTOR"*."""
    return _role_or_refuse(
        actor,
        subject,
        allowed=(
            actor.id in (subject.assignee, subject.discipline_owner)
            or actor.holds(Role.ART_DIRECTOR)
        ),
    )


def _role_or_refuse(actor: Actor, subject: Subject, *, allowed: bool) -> Decision:
    """Allowed, or the one refusal shape — which always names the role that would do."""
    if allowed:
        return ALLOWED
    return _refuse(f"{actor.display} may not act on {subject.named}: {Role.ART_DIRECTOR} required")


_RULES: Mapping[Operation, Rule] = {
    Operation.CREATE_ANNOTATION: _anyone_who_may_read,
    Operation.REPLY_IN_THREAD: _anyone_who_may_read,
    Operation.RAISE_REQUEST: _anyone_who_may_read,
    Operation.RESOLVE_ISSUE: _author_or_art_director,
    Operation.PROMOTE_TO_RULE: _art_director_only,
    Operation.ACCEPT_SUGGESTED_ALIAS: _owner_or_art_director,
    Operation.TRANSITION_ASSET_STATUS: _owner_or_art_director,
    Operation.DECIDE_REQUEST: _assignee_or_art_director,
}
"""The matrix itself, one entry per mutating operation.

A dispatch table rather than a chain of branches: a missing entry is a
`KeyError` the moment the operation is exercised, and
`tests/unit/test_domain_policy.py` asserts the table covers :data:`MUTATING`
exactly — so the failure arrives at the build rather than at a caller.
"""


__all__ = [
    "HUMAN_ONLY",
    "MUTATING",
    "NEEDS_GIT_IDENTITY",
    "NEEDS_GIT_MAPPING",
    "READ_ONLY",
    "REQUIRES_PERSON",
    "Operation",
    "Rule",
    "Subject",
    "decide",
    "declares_human_only",
    "requires_person",
]
