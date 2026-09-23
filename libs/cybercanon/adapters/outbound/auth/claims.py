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

Six rules this module exists to keep, each of which is a scenario:

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
* **A service credential is admitted by a list, never by its own say-so.**
  `type: service` says *this is a machine*; it has never said *this is our
  machine*. The issuer mints client credentials for every client it knows, and a
  client registered with no audience restriction may ask for this deployment's
  audience and be given it — so signature, issuer and audience, all three
  passing, still cannot tell this deployment's worker from a stranger's.
  :func:`_automation` admits a service credential only when the client it names
  is one this deployment was told to trust, and a deployment told of none trusts
  none. *Which* client it names is `sub`'s answer and `sub`'s alone, because
  `sub` is what the admitted actor is recorded as; a `client_id` claim that
  disagrees with it refuses rather than overrides.
* **The adapter never grants or denies.** Nothing here returns a decision, an
  allow, a deny or a permission. It returns an identifier, roles and the project
  this deployment serves when the credential is entitled to it, and
  :func:`~cybercanon.domain.policy.decide` does the rest.

:class:`ClaimNames` holds *which claim* each thing is read from. Those are
defaults rather than configuration because they are the shape of the credential
this adapter is written against; what a studio changes is :class:`Deployment` —
which client, which organisation, which project, which service clients — and the
role mapping.
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

It says *what kind of caller this is*, and it has never said *whether this
caller is ours*. :func:`_automation` asks the second question against
:attr:`Deployment.service_clients`.
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
    client: str = "client_id"
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
    service_clients: tuple[str, ...] = ()

    def trusts(self, client: str) -> bool:
        """Whether automation minted by this client id is admitted here at all.

        The whole of the entitlement decision for a service credential, and it
        is a list somebody wrote down rather than anything the token asserts. A
        deployment that has listed nothing trusts nothing, which is the same
        direction every other empty field here fails in.
        """
        return bool(client) and client in self.service_clients

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

    Five shapes, one refusal: no subject, so there is nobody to act as; a
    `type` this adapter does not know, so it cannot tell a person from a service
    and must not guess; a service credential whose `sub` is not `client:<id>`,
    so it names no client to be trusted as; a service credential whose `sub` and
    `client_id` claim name **two different clients**, or whose `client_id` claim
    names none at all, so there is no one client to check the allowlist about;
    and a person's credential with no `roles` claim at all, which is the
    identity service failing to answer rather than answering *none*. Each of
    them fails closed, because a credential that cannot be read has never been a
    reason to let somebody in.

    The disagreement is the newest of the five and the one that was a hole. The
    admission decision and the recorded identity have to come from the same
    claim; while they did not, a credential naming our worker in `client_id` and
    a stranger in `sub` was admitted on the first and written down as the
    second.
    """


class ServiceClientUnlisted(ValueError):
    """A verified service credential names a client this deployment does not list.

    Deliberately **not** a :class:`ClaimsIncomplete`, because nothing about the
    credential is wrong. The issuer signed it, it names this audience, it says
    which client it was minted for — and the answer is that this deployment does
    not trust that client. That is a configuration question with a configuration
    answer, and an operator sent looking for a malformed token would be looking
    in the wrong place entirely.

    :attr:`configured` says which of the two configuration answers it is: a
    deployment that lists *other* clients and not this one, or a deployment that
    lists none at all and therefore admits no automation whatsoever. The second
    is the shape a deployment has on the day it is stood up, and it has to read
    as a variable nobody set rather than as a broken credential.
    """

    def __init__(self, message: str, *, configured: bool) -> None:
        super().__init__(message)
        self.configured = configured


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

    A credential whose `type` is `service` produces the automation actor **when
    the client it names is one this deployment admits**, and is refused
    otherwise. That the credential is automation at all is decided by the claim
    and never by how the subject is spelled, which is the sharper half of the
    specified behaviour: a service credential naming a person is still
    automation, and automation holding *every* role is still refused every
    human-only operation — the refusal lives in the domain registry rather than
    in a constructor that declined to give it any. Whether *this* automation may
    act here at all is a separate question with a separate answer, and
    :func:`_automation` is where it is asked.
    """
    subject = _text(claims.get(names.subject))
    if not subject:
        raise ClaimsIncomplete(f"the credential carries no {names.subject!r} claim")
    kind = _text(claims.get(names.kind))
    if kind == SERVICE:
        return _automation(claims, subject, deployment=deployment, names=names)
    if kind != ACCESS:
        raise ClaimsIncomplete(f"the credential carries no readable {names.kind!r} claim")
    return _person(claims, subject, group_roles=group_roles, deployment=deployment, names=names)


def client_in(claims: Mapping[str, Any], subject: str, names: ClaimNames = DEFAULT_CLAIMS) -> str:
    """Which client a service credential was minted for, or nothing at all.

    **`sub` is the authority, and the `client_id` claim is a cross-check.** Not
    a preference between two sources, which is what it used to be, and which
    split the decision from the record: the allowlist was consulted about the
    `client_id` claim while the admitted actor was recorded as `sub`, so a
    credential naming our worker in one claim and a stranger in the other was
    admitted as ours and written down as theirs. `sub` decides because `sub` is
    what :func:`~cybercanon.domain.identity.automation_actor` is handed — the
    claim that is checked has to be the claim that is kept.

    Three ways a credential names no client this can decide about, each fatal:

    * `sub` is not `client:<id>`, or the id after the prefix is empty;
    * `sub` carries padding — `client: <id>` names no client rather than the
      same one with the space quietly removed, because the subject that would
      then be recorded is not the subject that was checked. Nothing arriving in
      a token is normalised; the **configured** list is where trimming belongs;
    * the `client_id` claim is present and disagrees, or is present and reads as
      nothing. A claim whose only job is to name the client and that names none
      is not an absent claim, and two claims naming two clients describe no
      actor at all.

    A token carrying no `client_id` claim still names its client — that is the
    claim-light service shape, and `sub` carries the id — so its absence is not
    a refusal. Its *disagreement* is.
    """
    if not subject.startswith(SERVICE_SUBJECT_PREFIX):
        return ""
    named = subject[len(SERVICE_SUBJECT_PREFIX) :]
    if not named or named != named.strip():
        return ""
    if names.client not in claims:
        return named
    claimed = _text(claims[names.client])
    if not claimed:
        raise ClaimsIncomplete(f"the credential's {names.client!r} claim names no client")
    if claimed != named:
        raise ClaimsIncomplete(
            f"the credential's {names.client!r} claim and its subject name two different clients"
        )
    return named


def _automation(
    claims: Mapping[str, Any],
    subject: str,
    *,
    deployment: Deployment,
    names: ClaimNames,
) -> Actor:
    """Background work: an allowlisted client, no organisation, and no role.

    A client-credentials credential carries no `roles` claim and stands for no
    person, so there is nobody for it to be a member as and nothing for the
    membership rule to read. **Which is exactly why it needs a rule of its
    own.** The signature, the issuer and the audience have all already agreed by
    the time execution reaches here, and none of the three can separate this
    deployment's own worker from any other service on the same issuer: an
    identity service issues client credentials to every client it knows, and one
    registered with no audience restriction may ask for *this* audience and be
    given it. An adapter that admitted every `type: service` token would hand
    the project to whatever background job asked, which is the inverse of the
    rule this product is built on — an agent reads constraints and never writes
    them.

    So automation is admitted by a list of client ids this deployment was told
    (`CANON_AUTH_SERVICE_CLIENTS`) and by nothing the credential asserts. The id
    the list is consulted about is the one inside `sub`, which is also the one
    the admitted actor is recorded as — checking one claim and recording another
    is a second way to hand the project to a stranger, and :func:`client_in`
    closes it by refusing a credential whose two claims disagree.

    Listing nothing admits nothing, and that is the answer on purpose: a
    deployment that has not said which background work it trusts has none, and
    its worker stops until somebody writes the list down. The alternative — an
    empty list meaning *anything* — is the hole with a configuration file in
    front of it.

    An admitted client reads the project this deployment serves and holds no
    role, which is exactly the shape `auth-integration` asks for — *"refused
    every operation the project reserves to a person"* — and that refusal is the
    domain's, not this line's. The list is an admission decision; it has never
    been a grant.
    """
    client = client_in(claims, subject, names)
    if not client:
        raise ClaimsIncomplete(
            f"a service credential's {names.subject!r} names no client to be trusted as"
        )
    if not deployment.trusts(client):
        raise ServiceClientUnlisted(
            f"{client!r} is not a service client this deployment admits",
            configured=bool(deployment.service_clients),
        )
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

    It is the organisation's `id` in both cases. The other fields are a display
    field and an integration field — `short_name`, and `github_login`, which is
    nullable, is null today and rides on `orgs` entries only: the `org` claim
    carries `id` and `short_name` and nothing else.
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
    "ServiceClientUnlisted",
    "actor_from",
    "admits",
    "client_in",
    "held_by",
    "organisations_in",
    "roles_from",
]
