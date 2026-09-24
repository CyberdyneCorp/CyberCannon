"""Who is acting — the resolution chain and what it is allowed to do (D4, D13).

Reads must work with no credential, no network and no services, and must keep
working when the identity service that was answering a minute ago stops. Both
are specified behaviour, and the way they stop being a scatter of
``if provider is None`` checks is to make the degradation a **chain of named
links** whose selection is asserted one link at a time:

    configured credential  ->  cached actor within its TTL  ->  local actor

Each link answers or declines, the first answer wins, and the :class:`Resolution`
says which link produced it and whether the identity behind it is currently
*verified*. That last word is the whole difference between "reads survive an
identity outage" and "role-requiring actions are refused as unverifiable": both
sentences are about the same cached actor, and only `verified` separates them.

**Identity is never a parameter.** :meth:`ActorResolver.resolve` takes no
arguments at all, so there is no signature through which a tool argument could
reach it — the refusal is structural rather than a filter somebody remembers to
call. :func:`strip_identity_claims` exists for the other half: an inbound
adapter hands the caller's arguments through it before mapping them onto a use
case, so a claimed actor or role is dropped and *named* rather than silently
tolerated.

The git-authorship half follows D13's order — provider claims, then the mapping
file, then the unmapped actor — and reports a disagreement rather than merging
it, which is what keeps `.canon/actors.yaml` a fallback instead of a second
source of truth.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Protocol

from cybercanon.application.ports.identity_provider import (
    Credential,
    IdentityProvider,
    ResolvedIdentity,
)
from cybercanon.application.ports.search_index import SearchIndex
from cybercanon.application.ports.spec_store import SpecStore
from cybercanon.application.results import as_result
from cybercanon.application.use_cases.lookup_assets import list_assets, recorded_owners
from cybercanon.domain.actor_checks import provider_disagreement
from cybercanon.domain.actors import (
    ActorBinding,
    ActorMapping,
    GitAuthor,
    binding_for_subject,
    normalize_email,
    unmapped_authors,
)
from cybercanon.domain.authorization import ALLOWED, Decision, may_read_project
from cybercanon.domain.identity import Actor, Role, local_actor
from cybercanon.domain.violations import SpecViolation

Clock = Callable[[], float]
"""Monotonic seconds. Injected so a TTL can be tested without waiting for one."""

AuthorSource = Callable[[], tuple[str, ...]]
"""How a caller answers *who has committed to this repository*.

Injected for the same reason :data:`~cybercanon.application.use_cases.index_assets.Fingerprinter`
is: reading git history is file-system work, the core does none, and
:func:`list_unmapped_authors` deliberately takes the authors as an argument
rather than growing a second port for identity. The composition root passes one
backed by the git adapter; everything else uses :func:`no_authors`, for which
the honest answer is *this store has no history*.
"""


def no_authors() -> tuple[str, ...]:
    """The default author source: no history is reachable from here."""
    return ()


DEFAULT_TTL_SECONDS = 900.0
"""How long a resolved actor stays usable while the provider is unreachable.

A configuration value, per the design's open questions — the *behaviour* it
governs is specified, the number is not.
"""

UNVERIFIABLE = "unverifiable"
"""The word a refusal carries when the identity behind it could not be checked."""

IDENTITY_CLAIM_PARAMETERS: tuple[str, ...] = (
    "actor",
    "actor_id",
    "as_actor",
    "on_behalf_of",
    "subject",
    "identity",
    "user",
    "role",
    "roles",
    "group",
    "groups",
    "projects",
    "permission",
    "permissions",
    "entitlement",
    "entitlements",
)
"""Argument names that would claim authority, and are therefore ignored.

Singular ``project`` is deliberately absent: a project argument *scopes* a
listing, and scoping cannot widen access because the resolved actor is still
authorized against that project by
:func:`~cybercanon.domain.authorization.may_read_project`. Plural ``projects`` —
the entitlement field on :class:`~cybercanon.domain.identity.Actor` — is here,
because a caller sending it would be claiming entitlement rather than asking for
a scope.
"""


class IdentitySource(Enum):
    """Which link of the chain produced a resolution. Never a privilege."""

    PROVIDER = "provider"
    CACHE = "cache"
    LOCAL = "local"


class GitIdentitySource(Enum):
    """Where a person's commit addresses came from, in D13's order."""

    PROVIDER = "provider"
    MAPPING = "mapping"
    UNMAPPED = "unmapped"


@dataclass(frozen=True)
class Resolution:
    """The acting actor, the link that produced it, and whether it is verified.

    `verified` is false for the local actor and for a cached one past its TTL.
    It gates roles and nothing else: a read is authorized from the actor's
    entitlements exactly as it always was, which is what lets the validator and
    the read surface keep working offline.
    """

    actor: Actor
    source: IdentitySource
    verified: bool
    git_emails: tuple[str, ...] = ()
    detail: str = ""

    @property
    def is_degraded(self) -> bool:
        """Whether this came from anything other than a live provider answer."""
        return self.source is not IdentitySource.PROVIDER


@dataclass(frozen=True)
class CachedIdentity:
    """A provider answer and when it was taken, so its age can be judged."""

    identity: ResolvedIdentity
    resolved_at: float

    def age(self, now: float) -> float:
        return now - self.resolved_at


class IdentityCache:
    """The middle link: the last provider answer, usable for a bounded period.

    One entry, because one process runs as one person. Its whole job is to make
    "the identity service went away" survivable without making it invisible —
    an expired entry is still returned, and is returned *unverified*.
    """

    def __init__(self, clock: Clock | None = None, ttl: float = DEFAULT_TTL_SECONDS) -> None:
        self._clock: Clock = clock or time.monotonic
        self._ttl = ttl
        self._entry: CachedIdentity | None = None

    @property
    def ttl(self) -> float:
        return self._ttl

    def remember(self, identity: ResolvedIdentity, at: float | None = None) -> CachedIdentity:
        """Keep this answer, optionally stamped with a time a test chose."""
        entry = CachedIdentity(identity=identity, resolved_at=self._clock() if at is None else at)
        self._entry = entry
        return entry

    def forget(self) -> None:
        self._entry = None

    def cached(self) -> CachedIdentity | None:
        return self._entry

    def is_fresh(self, entry: CachedIdentity) -> bool:
        return entry.age(self._clock()) <= self._ttl


@dataclass
class ActorResolver:
    """The chain of D4, wired once and asked the same question every time.

    `project` is the project this machine is standing in — the entitlement the
    local actor is resolved with, so a read works with no identity while holding
    no role. `provider` and `credential` are both optional, and either being
    absent simply means the first link declines.
    """

    project: str
    provider: IdentityProvider | None = None
    credential: Credential | None = None
    cache: IdentityCache = field(default_factory=IdentityCache)
    last_failure: str = ""

    def resolve(self) -> Resolution:
        """Who is acting.

        It takes no arguments, and that is the point (task 2.4): there is no
        parameter — tool argument, request field or environment hint — through
        which a caller could influence the answer.
        """
        return self._from_provider() or self._from_cache() or self._local()

    # -- the links -------------------------------------------------------

    def _from_provider(self) -> Resolution | None:
        """A configured credential, resolved live. Declines on any failure."""
        if self.provider is None or self.credential is None:
            return None
        try:
            identity = self.provider.resolve(self.credential)
        except Exception as failure:  # any provider failure degrades, none refuses a read
            self.last_failure = str(failure)
            return None
        self.cache.remember(identity)
        return Resolution(
            actor=identity.actor,
            source=IdentitySource.PROVIDER,
            verified=True,
            git_emails=identity.git_emails,
        )

    def _from_cache(self) -> Resolution | None:
        """The last resolved actor: verified while fresh, still served when stale."""
        entry = self.cache.cached()
        if entry is None:
            return None
        fresh = self.cache.is_fresh(entry)
        return Resolution(
            actor=entry.identity.actor,
            source=IdentitySource.CACHE,
            verified=fresh,
            git_emails=entry.identity.git_emails,
            detail=(
                self.last_failure or "the identity provider is unreachable"
                if fresh
                else f"the cached identity is older than the permitted {self.cache.ttl:g}s"
            ),
        )

    def _local(self) -> Resolution:
        """The last link, and it always answers: reads never wait for identity."""
        return Resolution(
            actor=local_actor(self.project),
            source=IdentitySource.LOCAL,
            verified=False,
            detail="no credential is configured",
        )


class Resolver(Protocol):
    """Anything that can answer *who is acting*, asked with no arguments.

    :class:`ActorResolver` is the local one — the chain that degrades to an
    unauthenticated actor so a laptop off the VPN keeps reading. A networked
    surface has already done the resolution before the request reached a use
    case, and hands in :class:`AlreadyResolved` instead.

    The protocol exists so that fact is expressible in a type rather than
    carried by duck typing: a composition root that wires a resolver is saying
    *this is where identity comes from on this surface*, and there are exactly
    two answers.
    """

    def resolve(self) -> Resolution:
        """Who is acting. No parameters, here as everywhere (task 2.4)."""
        ...


@dataclass(frozen=True)
class AlreadyResolved:
    """A resolution taken before the use case was called, and simply carried.

    The networked surface verifies a credential once per request, at the edge,
    through :func:`~cybercanon.application.use_cases.authenticate.authenticate`;
    a use case that re-resolved would ask an identity service again per read and
    could get a different answer halfway through one request. So the actor is
    resolved once and this carries it, unchanged, to every use case the request
    touches.

    It takes no arguments to :meth:`resolve` for the same reason the chain does:
    there must be no signature through which a caller could influence who they
    are.
    """

    resolution: Resolution

    def resolve(self) -> Resolution:
        return self.resolution


def verified_as(actor: Actor, git_emails: tuple[str, ...] = ()) -> Resolution:
    """The resolution for an actor a verified credential already produced.

    `verified` is true because the credential was checked — signature, issuer,
    audience and validity — by the identity adapter before this was built. That
    word gates roles and nothing else, so saying it here is what lets a
    role-requiring action succeed over HTTP while the same action from a laptop
    with no credential is refused as unverifiable.
    """
    return Resolution(
        actor=actor,
        source=IdentitySource.PROVIDER,
        verified=True,
        git_emails=git_emails,
    )


# --------------------------------------------------------------------------
# What a resolution may do
# --------------------------------------------------------------------------


def may_read(resolution: Resolution, project: str) -> Decision:
    """Whether this resolution may read that project — the domain policy, unchanged.

    Deliberately not gated on `verified`: a read that required a live identity
    service would make the tool the enemy the day auth is down, which is the one
    outcome `project.md` refuses.
    """
    return may_read_project(resolution.actor, project)


def may_act_in_role(resolution: Resolution, role: Role, action: str = "this action") -> Decision:
    """Whether this resolution may take an action that requires `role`.

    Two refusals, and both name the required role because that is what the
    caller has to act on: an actor that simply does not hold it, and an identity
    that cannot currently be verified — the local actor, or a cached one past
    its TTL.
    """
    if resolution.verified and resolution.actor.holds(role):
        return ALLOWED
    return Decision(allowed=False, reason=_refusal(resolution, role, action))


def _refusal(resolution: Resolution, role: Role, action: str) -> str:
    required = f"{action} requires the {role} role"
    if not resolution.verified:
        detail = f" ({resolution.detail})" if resolution.detail else ""
        return (
            f"{resolution.actor.display} may not perform it: {required}, and this "
            f"identity is {UNVERIFIABLE}{detail}"
        )
    return f"{resolution.actor.display} may not perform it: {required}"


def strip_identity_claims(parameters: Mapping[str, Any]) -> tuple[dict[str, Any], tuple[str, ...]]:
    """The caller's arguments with every identity claim removed, and their names.

    An inbound adapter calls this before mapping arguments onto a use case, so a
    supplied actor, role or entitlement is dropped rather than tolerated. The
    names are returned rather than discarded because a caller that sent one
    should be told it had no effect — silence there reads as acceptance.
    """
    claimed = tuple(name for name in parameters if name.lower() in IDENTITY_CLAIM_PARAMETERS)
    kept = {name: value for name, value in parameters.items() if name not in claimed}
    return kept, claimed


# --------------------------------------------------------------------------
# Git authorship — provider claims, then the file, then unmapped (D13, D14)
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class GitIdentity:
    """A person's commit addresses, where they came from, and what disagreed.

    `emails` is empty only for the unmapped case, which is an answer and never a
    failure: the actor is still here, carrying whatever identified it.

    `name` is the name a commit is authored under, and it is carried rather than
    taken from the actor because the two can come from different places. An
    identity resolved from `.canon/actors.yaml` takes its addresses from that
    file, and the name has to come from the same entry: an actor resolved from a
    credential CyberdyneAuth issues has no display name at all — that service
    sends no `name` claim — so its `display_name` falls back to the subject, and
    authoring with it produced commits reading `968a70af-8b4c-… <leo@…>`. A
    commit whose address is the file's and whose name is the token's describes
    nobody. Empty means *use the actor's*, which is right for the provider and
    unmapped cases, where the actor is the only source there is.
    """

    actor: Actor
    emails: tuple[str, ...]
    source: GitIdentitySource
    violations: tuple[SpecViolation, ...] = ()
    name: str = ""

    @property
    def author(self) -> GitAuthor | None:
        """The identity a change is committed with — the first listed address.

        Name and address come from the same source. Where they did not, `git
        blame` answered with a subject nobody recognises beside an address
        everybody does.
        """
        if not self.emails:
            return None
        return GitAuthor(name=self.name or self.actor.display_name, email=self.emails[0])

    @property
    def is_unmapped(self) -> bool:
        return self.source is GitIdentitySource.UNMAPPED


def resolve_git_identity(resolution: Resolution, mapping: ActorMapping) -> GitIdentity:
    """A resolved actor's git authorship, in D13's fixed order.

    Provider claims first, so the day CyberdyneAuth carries commit addresses the
    file quietly stops mattering — no migration and no ambiguity about which one
    is true. The file second, for the people the provider does not describe. The
    unmapped actor last, because resolution always returns something (D14).
    """
    binding = binding_for_subject(mapping, resolution.actor.id.value)
    if resolution.git_emails:
        return GitIdentity(
            actor=resolution.actor,
            emails=resolution.git_emails,
            source=GitIdentitySource.PROVIDER,
            violations=_disagreement(binding, resolution.git_emails),
        )
    if binding and binding.emails:
        return GitIdentity(
            actor=resolution.actor,
            emails=tuple(binding.emails),
            source=GitIdentitySource.MAPPING,
            name=binding.display_name,
        )
    return GitIdentity(actor=resolution.actor, emails=(), source=GitIdentitySource.UNMAPPED)


def _disagreement(
    binding: ActorBinding | None, supplied: tuple[str, ...]
) -> tuple[SpecViolation, ...]:
    """The file's entry contradicts the provider — reported, never merged."""
    if binding is None:
        return ()
    declared = {normalize_email(email) for email in binding.emails}
    if not declared or declared == {normalize_email(email) for email in supplied}:
        return ()
    return provider_disagreement(binding, supplied)


# --------------------------------------------------------------------------
# The mapping, and the authors nobody has bound yet
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class UnmappedAuthors:
    """A project's git authors that `.canon/actors.yaml` does not bind.

    Retrievable by specification, because an empty mapping has to be a visible
    defect rather than an invisible one: this list is what somebody works
    through to complete the file.
    """

    authors: tuple[Actor, ...] = ()
    violations: tuple[SpecViolation, ...] = ()

    @property
    def emails(self) -> tuple[str, ...]:
        """Each unmatched address, once, in the order it was first seen."""
        return tuple(actor.unmapped_as or actor.display_name for actor in self.authors)

    def __len__(self) -> int:
        return len(self.authors)


@as_result
def list_unmapped_authors(
    emails: Sequence[str], *, spec_store: SpecStore, root: str = ""
) -> UnmappedAuthors:
    """The distinct authors among `emails` that the project's mapping does not bind.

    `emails` are the commit authors a caller collected — git history, the owners
    recorded in specification files, or both. They are an argument rather than
    another port method because the mapping is the only thing this needs to
    read: what counts as "the project's authors" is the caller's question, and
    the answer to "which of them are unknown" is the same either way.
    """
    loaded = spec_store.load_actor_mapping(root)
    return UnmappedAuthors(
        authors=unmapped_authors(loaded.mapping, tuple(emails)),
        violations=loaded.violations,
    )


@as_result
def list_unmapped_people(
    *,
    spec_store: SpecStore,
    search_index: SearchIndex,
    authors: Sequence[str] = (),
    project: str | None = None,
    root: str = "",
) -> UnmappedAuthors:
    """Every address this project will render as somebody and cannot yet name.

    Two sources, because a project has two kinds of author: the people in its
    git history, which the composition root collects, and the people its
    specification files name as owners, which come from the listing. Composed
    here rather than at the composition root for the reason
    :func:`~cybercanon.application.use_cases.diff_spec.diff_asset_spec` gives —
    a chained call evaluates the first as an argument, and its failure would
    escape the second's outcome vocabulary entirely.
    """
    listing = list_assets.raising(spec_store=spec_store, search_index=search_index, project=project)
    return list_unmapped_authors.raising(
        (*authors, *recorded_owners(listing)), spec_store=spec_store, root=root
    )


__all__ = [
    "DEFAULT_TTL_SECONDS",
    "IDENTITY_CLAIM_PARAMETERS",
    "UNVERIFIABLE",
    "ActorResolver",
    "AlreadyResolved",
    "AuthorSource",
    "CachedIdentity",
    "Clock",
    "GitIdentity",
    "GitIdentitySource",
    "IdentityCache",
    "IdentitySource",
    "Resolution",
    "Resolver",
    "UnmappedAuthors",
    "list_unmapped_authors",
    "list_unmapped_people",
    "may_act_in_role",
    "may_read",
    "no_authors",
    "resolve_git_identity",
    "strip_identity_claims",
    "verified_as",
]
