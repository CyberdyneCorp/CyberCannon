"""Verified claims in, a domain :class:`Actor` out. The whole of the translation.

This module is the boundary `auth-integration` draws and D12 restates: *"the
adapter verifies ... then maps configured groups to `Role`s and the subject to an
`ActorId`, producing an `Actor` with a `Tenant`"*. Everything the identity
service's data model calls things stops here — claim names, role keys, the shape
of a token — and what continues is an actor the domain already knows how to
reason about.

**It is written against the token CyberdyneAuth really emits.** The version
before it read `groups` for roles, `projects` for entitlement and `gty` for
automation, and the issuer sends none of those three: the suites agreed with it
only because the fixtures minted the shape this module expected instead of the
shape the issuer produces. What a real access token carries is `roles` (every
entry prefixed with the client id it belongs to, covering *every* client the
person holds a role on), `type` (`access` or `service`), `orgs` and `org`,
`entitlements`, `is_admin`, `scope` and `jti` — and no display name, no email
and no commit addresses at all.

Five rules this module exists to keep, each of which is a scenario:

* **A role key with no configured mapping grants nothing**, and a credential
  whose keys are *all* unmapped resolves to an actor with no roles rather than a
  refusal. Refusing would make a mapping mistake look like an outage; resolving
  role-less makes it look like what it is, and the operation that needed a role
  refuses by naming the role.
* **No role key is named in code.** :func:`roles_from` reads a mapping supplied
  by configuration and has no opinion about its contents, so *"adding a mapping
  requires no code change"* is structural rather than a promise.
* **A role held on another client grants nothing here.** `roles` is one list for
  the whole organisation, so an entry is ours only when it carries our client
  id, and the prefix is stripped before configuration ever sees it. A reader
  that took the claim as given would hand somebody CyberCanon's art director
  because they are an art director in a different application.
* **Absence is not an answer.** No `roles` claim at all means IAM was not
  reached, and no `orgs` claim at all is a token minted before the claim
  existed. Both fail closed, and neither is the same as the empty list, which
  *is* an answer and is *no*.
* **The adapter never grants or denies.** Nothing here returns a decision, an
  allow, a deny or a permission. It returns an identifier, roles and the project
  this deployment serves when the credential is entitled to it, and
  :func:`~cybercanon.domain.policy.decide` does the rest.

:class:`ClaimNames` holds *which claim* each thing is read from. Those are
defaults rather than configuration because they are the shape of the credential
this adapter is written against; what a studio changes is :class:`Deployment` —
which client, which organisation, which project — and the role mapping.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from cybercanon.domain.identity import Actor, ActorId, Role, automation_actor
from cybercanon.domain.tenancy import Tenant

ACCESS = "access"
"""`type` on a credential issued for a person."""

SERVICE = "service"
"""`type` on a client-credentials credential. Background work, and no person.

Recognising automation from `type` is what lets background work be identified
*from the credential* rather than from a naming convention on the subject — a
convention an adapter can forget to apply, which is the reason
:class:`~cybercanon.domain.identity.ActorKind` exists at all. There is no
fallback to anything else: the `gty` claim this module used to read as a second
opinion was a guess, and a default that was a guess is worse than an absence.
"""

SERVICE_SUBJECT_PREFIX = "client:"
"""What `sub` says on a service credential: the client, never a person."""

ROLE_SEPARATOR = ":"
"""What separates the client id from the role key in one `roles` entry."""


@dataclass(frozen=True)
class ClaimNames:
    """Which claim carries which fact. The credential's shape, not a policy."""

    subject: str = "sub"
    kind: str = "type"
    roles: str = "roles"
    organisations: str = "orgs"
    organisation: str = "org"
    organisation_id: str = "id"


DEFAULT_CLAIMS = ClaimNames()


@dataclass(frozen=True)
class Deployment:
    """Which client, which organisation and which project this deployment is.

    All three are **configuration** and none of them is a constant: the client
    id is the prefix our own roles carry, the organisation is the one whose
    members may read what this deployment serves, and the project is what they
    read. A repository that named any of them would have to be edited by the
    second studio to install it, and an organisation identifier committed here
    would tie the suites to a record in somebody else's database.

    Every field is allowed to be empty, and empty fails closed rather than open:
    an adapter that has not been told which client it is cannot recognise a role
    as its own, and one that has not been told its organisation cannot decide
    that anybody belongs to it.
    """

    client_id: str = ""
    organisation: str = ""
    project: str = ""

    @property
    def prefix(self) -> str:
        """What one of *our* `roles` entries starts with, or nothing at all."""
        return f"{self.client_id}{ROLE_SEPARATOR}" if self.client_id else ""

    @property
    def projects(self) -> tuple[str, ...]:
        """The entitlement an admitted credential resolves with."""
        return (self.project,) if self.project else ()


UNCONFIGURED = Deployment()
"""A deployment that has been told nothing, which grants nothing and admits nobody."""


class ClaimsIncomplete(ValueError):
    """A verified credential does not describe an actor this adapter can resolve.

    Three shapes, one refusal: no subject, so there is nobody to act as; a
    `type` this adapter does not know, so it cannot tell a person from a service
    and must not guess; and a person's credential with no `roles` claim at all,
    which is the identity service failing to answer rather than answering
    *none*. Each of them fails closed, because a credential that cannot be read
    has never been a reason to let somebody in.
    """


def roles_from(keys: Iterable[str], mapping: Mapping[str, str]) -> tuple[Role, ...]:
    """The domain roles these role keys map to, in the role set's declared order.

    A key with no entry contributes nothing, and an entry naming something that
    is not a role contributes nothing either: a typo in configuration grants
    *less*, never more, which is the only direction a configuration mistake is
    allowed to fail in.

    The result is deduplicated and ordered by :class:`Role` rather than by the
    order the keys arrived in, so two credentials carrying the same roles in a
    different order resolve to actors that compare equal.
    """
    held = {
        role
        for key in keys
        if key in mapping
        if (role := Role.from_value(mapping[key])) is not None
    }
    return tuple(role for role in Role if role in held)


def held_by(
    claims: Mapping[str, Any],
    *,
    deployment: Deployment,
    names: ClaimNames = DEFAULT_CLAIMS,
) -> tuple[str, ...] | None:
    """The role keys this credential holds **on this client**, unprefixed.

    ``None`` when the claim is absent, which is not the same question as the
    empty tuple: `roles: []` says *this person holds nothing here*, and no
    `roles` claim says *nobody asked the identity service successfully*. Only
    the caller can decide what to do about the second, so this does not decide
    it here.

    A deployment that has not been told its client id recognises nothing, and
    that is the fail-closed direction: every entry in the claim belongs to some
    client, and an adapter that cannot say which one is ours must not assume
    that any of them is.
    """
    if names.roles not in claims:
        return None
    prefix = deployment.prefix
    if not prefix:
        return ()
    return tuple(
        entry[len(prefix) :] for entry in _strings(claims[names.roles]) if entry.startswith(prefix)
    )


def organisations_in(
    claims: Mapping[str, Any], names: ClaimNames = DEFAULT_CLAIMS
) -> tuple[str, ...] | None:
    """The identifiers of the organisations this person belongs to.

    ``None`` when there is no `orgs` claim at all — a credential from before the
    claim existed — which the entitlement rule refuses exactly as it refuses the
    empty list. Both are absence of proof, and neither has ever been a reason to
    admit anybody.

    Organisations are matched on `id` and never on `github_login`, which is
    nullable and is null for the only organisation that exists today: a reader
    keying on it would miss every member and could match ``None`` against
    ``None``.
    """
    if names.organisations not in claims:
        return None
    listed = claims[names.organisations]
    if not isinstance(listed, Sequence) or isinstance(listed, str):
        return ()
    return tuple(identifier for entry in listed if (identifier := _identifier(entry, names)))


def admits(
    claims: Mapping[str, Any],
    *,
    deployment: Deployment,
    names: ClaimNames = DEFAULT_CLAIMS,
) -> bool:
    """Whether this person may read the project this deployment serves.

    The rule, settled against the real issuer and implemented here and nowhere
    else: `orgs` carries the organisation this deployment belongs to **and**
    `roles` carries at least one entry prefixed with this deployment's client
    id. Both clauses, both failing closed.

    Four things it is deliberately not:

    * not `org`, which is the person's *primary* organisation only — keying on
      it locks out a member whose primary is elsewhere, which would have worked
      for one test account and for nobody else and would have read like an
      intermittent permissions problem rather than a design error;
    * not `entitlements`, which are billing products (`pro:monthly`) and have
      never been access;
    * not `github_login`, which is nullable;
    * not `is_admin`, which is never read here at all. An admin flag that
      quietly widens access is exactly what gets added later "to unblock
      someone", and the moment to refuse it is while nobody is blocked.
    """
    if not deployment.organisation:
        return False
    organisations = organisations_in(claims, names)
    if organisations is None or deployment.organisation not in organisations:
        return False
    return bool(held_by(claims, deployment=deployment, names=names))


def actor_from(
    claims: Mapping[str, Any],
    *,
    group_roles: Mapping[str, str],
    deployment: Deployment = UNCONFIGURED,
    names: ClaimNames = DEFAULT_CLAIMS,
) -> Actor:
    """The actor a verified credential resolves to — identifier, roles, project.

    A credential whose `type` is `service` produces the automation actor. That
    is decided by the claim and never by how the subject is spelled, and it is
    the sharper half of the specified behaviour: a service credential naming a
    person is still automation, and automation holding *every* role is still
    refused every human-only operation — the refusal lives in the domain
    registry rather than in a constructor that declined to give it any.
    """
    subject = _text(claims.get(names.subject))
    if not subject:
        raise ClaimsIncomplete(f"the credential carries no {names.subject!r} claim")
    kind = _text(claims.get(names.kind))
    if kind == SERVICE:
        return _automation(subject, deployment)
    if kind != ACCESS:
        raise ClaimsIncomplete(f"the credential carries no readable {names.kind!r} claim")
    return _person(claims, subject, group_roles=group_roles, deployment=deployment, names=names)


def _automation(subject: str, deployment: Deployment) -> Actor:
    """Background work: no person, no organisation, and no role anywhere.

    A client-credentials credential carries no `roles` claim and stands for no
    person, so there is nobody for it to be a member as and nothing for the
    membership rule to read. What admits it is the check the adapter has already
    made: the issuer signed it and it was minted for *this* audience. It reads
    the project this deployment serves and holds no role, which is exactly the
    shape `auth-integration` asks for — *"refused every operation the project
    reserves to a person"* — and the refusal is the domain's, not this line's.
    """
    if not subject.startswith(SERVICE_SUBJECT_PREFIX):
        raise ClaimsIncomplete("a service credential's subject names no client")
    return automation_actor(projects=deployment.projects, identifier=subject)


def _person(
    claims: Mapping[str, Any],
    subject: str,
    *,
    group_roles: Mapping[str, str],
    deployment: Deployment,
    names: ClaimNames,
) -> Actor:
    """A person: their roles on this client, and whether they may read at all."""
    keys = held_by(claims, deployment=deployment, names=names)
    if keys is None:
        raise ClaimsIncomplete(
            f"the credential carries no {names.roles!r} claim, so the identity "
            "service did not describe what this person holds"
        )
    member = admits(claims, deployment=deployment, names=names)
    return Actor(
        id=ActorId(subject),
        display_name=subject,
        roles=roles_from(keys, group_roles),
        projects=deployment.projects if member else (),
        tenant=_tenant(claims, deployment=deployment, member=member, names=names),
    )


def _tenant(
    claims: Mapping[str, Any],
    *,
    deployment: Deployment,
    member: bool,
    names: ClaimNames,
) -> Tenant | None:
    """The organisation this credential places the actor in, as an identifier.

    A member of this deployment's organisation is placed in it. Anybody else
    carries the organisation their own credential calls primary, which is the
    honest answer for somebody this deployment serves nothing to, and ``None``
    when the credential names none at all.

    It is the organisation's `id` in both cases: `short_name` and `github_login`
    are a display field and an integration field, and one of them is null today.
    """
    if member:
        return Tenant(deployment.organisation)
    primary = _identifier(claims.get(names.organisation), names)
    return Tenant(primary) if primary else None


def _identifier(entry: Any, names: ClaimNames = DEFAULT_CLAIMS) -> str:
    """One organisation's identifier, out of the object the claim carries."""
    if not isinstance(entry, Mapping):
        return ""
    return _text(entry.get(names.organisation_id))


def _strings(value: Any) -> tuple[str, ...]:
    """A claim that may be a list, a space-separated string, or neither.

    Both spellings are in the wild — `roles` as an array, `scope` as a
    space-separated string — and accepting either here keeps the alternative out
    of every call site. Anything that is neither is no roles at all, because a
    claim this cannot read must not be read as a grant.
    """
    if isinstance(value, str):
        return tuple(item for item in value.split() if item)
    if isinstance(value, Sequence):
        return tuple(_text(item) for item in value if _text(item))
    return ()


def _text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


__all__ = [
    "ACCESS",
    "DEFAULT_CLAIMS",
    "ROLE_SEPARATOR",
    "SERVICE",
    "SERVICE_SUBJECT_PREFIX",
    "UNCONFIGURED",
    "ClaimNames",
    "ClaimsIncomplete",
    "Deployment",
    "actor_from",
    "admits",
    "held_by",
    "organisations_in",
    "roles_from",
]
