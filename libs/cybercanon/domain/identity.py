"""Who is acting: actors, roles, agents, and the attribution of an action.

An automated caller has no identity of its own. It acts **as a person**, with
exactly that person's permissions, so the domain knows two things and nothing
else: an :class:`Actor` — an identifier, a display name, the roles it holds and
the projects it may see — and an :class:`AgentId` naming the instrument that
performed an action on its behalf. No claim name, group name, token field or
issuing service reaches this module, which is what makes every authorization
decision verifiable with no identity service running.

Three kinds of actor exist, and the distinction is about *provenance*, never
about privilege:

* **person** — resolved from a credential or from the project's actor mapping;
* **local** — the unauthenticated actor a machine with no configured credential
  resolves to, holding no roles and entitled to read the project it is standing
  in (D4). Reads work offline; anything needing a role does not;
* **unmapped** — a git author nobody has bound to a person yet (D14). It carries
  the raw email verbatim, holds no roles, and every presentation of it says so.
  It exists so that authorship is never dropped and never guessed.

:class:`Attribution` is the last piece and the one with teeth: it pairs the
responsible person with the instrument, and the actor slot has no default (D5),
so there is no constructor path that records an action anonymously.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any


class Role(Enum):
    """The defined role set. A role outside it is a reportable violation."""

    ART_DIRECTOR = "ART_DIRECTOR"
    ARTIST = "ARTIST"
    DESIGNER = "DESIGNER"
    ENGINEER = "ENGINEER"

    @classmethod
    def values(cls) -> tuple[str, ...]:
        """Every accepted role, in declaration order — what a message must name."""
        return tuple(member.value for member in cls)

    @classmethod
    def from_value(cls, value: str) -> Role | None:
        """The role this text declares, or ``None`` when it declares none.

        Matching ignores surrounding space and case: `artist` and `ARTIST` are
        the same role, written by two people with different habits. Returning
        ``None`` rather than raising follows
        :meth:`~cybercanon.domain.status.Status.from_value` — an unknown role is
        a violation of the mapping file, and raising would deny every other
        finding in the same run.
        """
        return _ROLES_BY_VALUE.get(value.strip().upper())

    def __str__(self) -> str:
        return self.value


_ROLES_BY_VALUE = {member.value: member for member in Role}


class ActorKind(Enum):
    """Where an actor came from. Never a privilege — privilege is `roles`."""

    PERSON = "person"
    LOCAL = "local"
    UNMAPPED = "unmapped"


UNMAPPED_MARK = "unmapped"
"""The word every presentation of an unknown actor carries (D14)."""

LOCAL_ACTOR_ID = "local"
LOCAL_ACTOR_NAME = "local (unauthenticated)"


@dataclass(frozen=True)
class ActorId:
    """A stable identifier for a person — the identity subject, not their email.

    A value object for the same reason :class:`~cybercanon.domain.asset.AssetId`
    is one: it is what authorization and attribution agree on, and a bare `str`
    is confusable with a display name, an email or a chat handle.
    """

    value: str

    def __post_init__(self) -> None:
        if not self.value or self.value.strip() != self.value:
            raise ValueError(f"actor id {self.value!r} must be non-empty and unpadded")
        if any(character.isspace() for character in self.value):
            raise ValueError(f"actor id {self.value!r} must not contain whitespace")

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True)
class AgentId:
    """The instrument that performed an action — `blender-agent`, `claude-code`.

    It is never a principal: an agent id answers *what performed this*, and the
    :class:`ActorId` beside it answers *who is accountable*.
    """

    value: str

    def __post_init__(self) -> None:
        if not self.value or self.value.strip() != self.value:
            raise ValueError(f"agent id {self.value!r} must be non-empty and unpadded")

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True)
class Actor:
    """A resolved person: who they are, what they hold, what they may see.

    `roles` and `projects` are tuples rather than sets so that two resolutions
    of the same person compare equal and render in a stable order — the round
    trip through the actor mapping is asserted on equality.

    `kind` and `unmapped_as` exist for the unknown actor (D14): an unmatched git
    author resolves to an `Actor` marked `UNMAPPED` carrying the raw email
    verbatim, so no call site has to handle a ``None`` and no renderer can
    present it as an ordinary person.
    """

    id: ActorId
    display_name: str
    roles: tuple[Role, ...] = ()
    projects: tuple[str, ...] = ()
    kind: ActorKind = ActorKind.PERSON
    unmapped_as: str | None = None

    @property
    def is_unmapped(self) -> bool:
        """Whether this actor is a git author nobody has bound to a person."""
        return self.kind is ActorKind.UNMAPPED

    @property
    def display(self) -> str:
        """How any surface names this actor, marker included.

        A mapped person is their display name. An unknown actor is the raw
        email followed by the unmapped marker, because the specification
        requires every presentation of one to say so — putting it here is what
        keeps the four renderers from each deciding differently.
        """
        if self.is_unmapped and self.unmapped_as:
            return f"{self.unmapped_as} ({UNMAPPED_MARK})"
        return self.display_name

    def holds(self, role: Role) -> bool:
        """Whether this actor holds the role. The only question about roles."""
        return role in self.roles

    def may_see(self, project: str) -> bool:
        """Whether this project is among the ones this actor was resolved with.

        The raw membership test. The policy that reads it, and the refusal it
        produces, live in :mod:`cybercanon.domain.authorization`.
        """
        return project in self.projects


def local_actor(project: str) -> Actor:
    """The unauthenticated actor a machine with no configured credential uses.

    It is entitled to read the project it is standing in and holds no role, so
    reads work with no identity and no network while anything needing a role is
    refused for want of one (D4). The entitlement is an ordinary `projects`
    entry rather than a special case in the policy: a kind that skipped the
    check would be a privilege, and this actor has none.
    """
    return Actor(
        id=ActorId(LOCAL_ACTOR_ID),
        display_name=LOCAL_ACTOR_NAME,
        roles=(),
        projects=(project,),
        kind=ActorKind.LOCAL,
    )


def unmapped_actor(identifier: str) -> Actor:
    """The explicitly unknown actor an unmatched git author resolves to (D14).

    `identifier` is kept verbatim — case included — because it is the evidence
    somebody needs in order to add the missing mapping entry. It holds no roles
    and no projects, so it can read nothing and author nothing; it exists to
    carry authorship, not to exercise it.
    """
    normalized = identifier.strip()
    if not normalized:
        raise ValueError("an unmapped actor must carry the identifier it failed to match")
    return Actor(
        id=ActorId(normalized),
        display_name=identifier,
        roles=(),
        projects=(),
        kind=ActorKind.UNMAPPED,
        unmapped_as=identifier,
    )


@dataclass(frozen=True)
class Attribution:
    """Who is accountable for an action, and what performed it (D5).

    `actor` has no default and is validated at construction, so there is no
    constructor path — positional, keyword, or
    :func:`dataclasses.replace` — that produces an attribution without a person.
    That is the whole point: an action that cannot be attributed is refused
    here, at the type, rather than by a validation somebody forgets to call.

    `via` is ``None`` for a person acting directly and an :class:`AgentId` when
    an instrument acted on their behalf, which is what makes a record read
    "rafa, via blender-agent" and keeps the human accountable.
    """

    actor: ActorId
    via: AgentId | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.actor, ActorId):
            raise ValueError(
                "an attribution names the accountable actor; an action with no "
                "resolvable actor is refused rather than recorded anonymously"
            )
        if self.via is not None and not isinstance(self.via, AgentId):
            raise ValueError("the instrument of an attribution is an AgentId or nothing")

    @property
    def responsible(self) -> ActorId:
        """The person the record holds accountable."""
        return self.actor

    @property
    def instrument(self) -> AgentId | None:
        """The agent that performed the action, when one did."""
        return self.via

    @property
    def is_automated(self) -> bool:
        """Whether an automated caller performed this action."""
        return self.via is not None

    def __str__(self) -> str:
        return f"{self.actor}, via {self.via}" if self.via else str(self.actor)


def attribute(actor: Any, via: AgentId | None = None) -> Attribution:
    """Build an attribution, refusing anything that is not a resolved actor.

    The convenience the recording surfaces use: it accepts an :class:`Actor` or
    an :class:`ActorId` and refuses ``None``, so "record this action" has one
    entry point and no way in through the back.
    """
    if isinstance(actor, Actor):
        return Attribution(actor=actor.id, via=via)
    return Attribution(actor=actor, via=via)


__all__ = [
    "LOCAL_ACTOR_ID",
    "LOCAL_ACTOR_NAME",
    "UNMAPPED_MARK",
    "Actor",
    "ActorId",
    "ActorKind",
    "AgentId",
    "Attribution",
    "Role",
    "attribute",
    "local_actor",
    "unmapped_actor",
]
