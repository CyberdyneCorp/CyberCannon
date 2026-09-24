"""Tasks 2.2-2.4, 2.8-2.10 — the resolution chain, its degradation, and D13.

Every test here runs with no file, no network and no service, which is the
property `agent-identity` demands of the whole identity path: an authorization
decision must be producible with nothing reachable. The provider is the
in-memory fake, the mapping is hand-built, and the clock is a list index.

The chain is asserted **one link at a time** — that is the point of D4. A test
that only proved "a read works offline" would pass over a chain that had
collapsed into a single `if provider is None`, and the degradation it hides is
exactly the one that matters when auth is down at 9am on a Monday.
"""

from __future__ import annotations

import inspect
import socket
from typing import Any

import pytest

from cybercanon.application.ports.identity_provider import Credential, IdentityUnavailable
from cybercanon.application.testing.identity_provider import InMemoryIdentityProvider
from cybercanon.application.testing.outcomes import ran
from cybercanon.application.testing.spec_store import InMemorySpecStore
from cybercanon.application.use_cases.resolve_actor import (
    IDENTITY_CLAIM_PARAMETERS,
    UNVERIFIABLE,
    ActorResolver,
    GitIdentity,
    GitIdentitySource,
    IdentityCache,
    IdentitySource,
    list_unmapped_authors,
    may_act_in_role,
    may_read,
    resolve_git_identity,
    strip_identity_claims,
    verified_as,
)
from cybercanon.domain.actor_checks import RULE_PROVIDER_DISAGREEMENT, RULE_UNPARSEABLE
from cybercanon.domain.actors import ActorBinding, ActorMapping
from cybercanon.domain.identity import Actor, ActorId, ActorKind, Role

PROJECT = "cyberdyne-game"
SUBJECT = "auth|rafa"
WORK_EMAIL = "rafa@cyberdyne.com"
PERSONAL_EMAIL = "rafa@personal.dev"
CLAIMED_EMAIL = "rafa@cyberdyne.ai"
TOKEN = Credential("opaque-launch-token")

RAFA = ActorBinding(
    subject=SUBJECT,
    display_name="Rafa",
    emails=(WORK_EMAIL, PERSONAL_EMAIL),
    default_role="ARTIST",
)
MAPPING = ActorMapping((RAFA,))


class Ticks:
    """A clock a test advances by hand, so a TTL costs no wall time."""

    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


def a_person(*roles: Role, projects: tuple[str, ...] = (PROJECT,)) -> Actor:
    return Actor(id=ActorId(SUBJECT), display_name="Rafa", roles=roles, projects=projects)


@pytest.fixture
def provider() -> InMemoryIdentityProvider:
    fake = InMemoryIdentityProvider()
    fake.add(TOKEN, a_person(Role.ARTIST))
    return fake


@pytest.fixture
def clock() -> Ticks:
    return Ticks()


@pytest.fixture
def resolver(provider: InMemoryIdentityProvider, clock: Ticks) -> ActorResolver:
    return ActorResolver(
        project=PROJECT,
        provider=provider,
        credential=TOKEN,
        cache=IdentityCache(clock=clock, ttl=60.0),
    )


# --------------------------------------------------------------------------
# 2.2 — each link of the chain is selected under its own conditions
# --------------------------------------------------------------------------


def test_a_configured_credential_resolves_through_the_provider(resolver: ActorResolver) -> None:
    resolved = resolver.resolve()

    assert resolved.source is IdentitySource.PROVIDER
    assert resolved.actor.id == ActorId(SUBJECT)
    assert resolved.verified
    assert not resolved.is_degraded


def test_no_credential_resolves_to_the_local_actor() -> None:
    resolved = ActorResolver(project=PROJECT).resolve()

    assert resolved.source is IdentitySource.LOCAL
    assert resolved.actor.kind is ActorKind.LOCAL
    assert resolved.actor.roles == ()
    assert "credential" in resolved.detail


def test_a_provider_with_no_credential_is_not_consulted(
    provider: InMemoryIdentityProvider,
) -> None:
    """The first link needs both halves; one alone declines rather than guesses."""
    resolved = ActorResolver(project=PROJECT, provider=provider).resolve()

    assert resolved.source is IdentitySource.LOCAL
    assert provider.resolutions == 0


def test_the_cached_link_is_selected_only_once_the_provider_declines(
    resolver: ActorResolver, provider: InMemoryIdentityProvider
) -> None:
    assert resolver.resolve().source is IdentitySource.PROVIDER

    provider.fail_with(IdentityUnavailable("cyberdyne-auth", "connection refused"))

    assert resolver.resolve().source is IdentitySource.CACHE


def test_an_unreachable_provider_with_nothing_cached_falls_through_to_local(
    resolver: ActorResolver, provider: InMemoryIdentityProvider
) -> None:
    provider.fail_with(IdentityUnavailable("cyberdyne-auth", "connection refused"))

    assert resolver.resolve().source is IdentitySource.LOCAL


def test_resolution_needs_no_network(
    resolver: ActorResolver, monkeypatch: pytest.MonkeyPatch
) -> None:
    def refuse(*args: object, **kwargs: object) -> None:
        raise AssertionError("resolving an actor opened a network connection")

    monkeypatch.setattr(socket, "socket", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)

    assert resolver.resolve().actor.id == ActorId(SUBJECT)


# --------------------------------------------------------------------------
# 2.3 — degradation: reads survive, roles do not
# --------------------------------------------------------------------------


def test_a_raising_provider_still_serves_reads_through_the_cached_actor(
    resolver: ActorResolver, provider: InMemoryIdentityProvider
) -> None:
    resolver.resolve()
    provider.fail_with(RuntimeError("the socket went away mid-handshake"))

    resolved = resolver.resolve()

    assert resolved.source is IdentitySource.CACHE
    assert may_read(resolved, PROJECT).allowed
    assert resolved.verified, "a cached actor within its TTL is still a verified one"


def test_an_expired_cached_actor_refuses_a_role_requiring_action_as_unverifiable(
    resolver: ActorResolver, provider: InMemoryIdentityProvider, clock: Ticks
) -> None:
    resolver.resolve()
    provider.fail_with(IdentityUnavailable("cyberdyne-auth"))
    clock.advance(61.0)

    resolved = resolver.resolve()
    decision = may_act_in_role(resolved, Role.ARTIST, action="promoting an annotation")

    assert resolved.source is IdentitySource.CACHE
    assert not resolved.verified
    assert decision.refused
    assert UNVERIFIABLE in decision.reason


def test_an_expired_cached_actor_still_serves_reads(
    resolver: ActorResolver, provider: InMemoryIdentityProvider, clock: Ticks
) -> None:
    """Only role-requiring actions are refused; a read is never held hostage."""
    resolver.resolve()
    provider.fail_with(IdentityUnavailable("cyberdyne-auth"))
    clock.advance(3600.0)

    assert may_read(resolver.resolve(), PROJECT).allowed


def test_the_local_actor_is_refused_a_role_with_the_role_named() -> None:
    resolved = ActorResolver(project=PROJECT).resolve()

    decision = may_act_in_role(resolved, Role.ART_DIRECTOR, action="promoting an annotation")

    assert decision.refused
    assert str(Role.ART_DIRECTOR) in decision.reason


def test_a_verified_actor_holding_the_role_is_allowed(resolver: ActorResolver) -> None:
    assert may_act_in_role(resolver.resolve(), Role.ARTIST).allowed


def test_a_verified_actor_without_the_role_is_refused_naming_it(
    resolver: ActorResolver,
) -> None:
    decision = may_act_in_role(resolver.resolve(), Role.ART_DIRECTOR)

    assert decision.refused
    assert str(Role.ART_DIRECTOR) in decision.reason
    assert UNVERIFIABLE not in decision.reason, "this identity was verified; it simply lacks a role"


def test_an_unentitled_actor_may_not_read(provider: InMemoryIdentityProvider) -> None:
    provider.add(TOKEN, a_person(Role.ARTIST, projects=("another-game",)))
    resolved = ActorResolver(project=PROJECT, provider=provider, credential=TOKEN).resolve()

    assert may_read(resolved, PROJECT).refused


# --------------------------------------------------------------------------
# 2.4 — no parameter can influence identity
# --------------------------------------------------------------------------


def test_resolution_accepts_no_parameter_at_all() -> None:
    """The structural half: there is no signature a claim could arrive through."""
    signature = inspect.signature(ActorResolver.resolve)

    assert list(signature.parameters) == ["self"]


def test_supplied_actor_and_role_parameters_leave_the_resolved_actor_unchanged(
    resolver: ActorResolver,
) -> None:
    before = resolver.resolve()
    arguments: dict[str, Any] = {
        "asset_id": "mech_scout",
        "actor": "auth|ana",
        "role": "ART_DIRECTOR",
        "roles": ["ART_DIRECTOR"],
        "projects": ["every-project"],
    }

    kept, claimed = strip_identity_claims(arguments)
    after = resolver.resolve()

    assert after.actor == before.actor
    assert after.actor.roles == (Role.ARTIST,)
    assert may_act_in_role(after, Role.ART_DIRECTOR).refused
    assert kept == {"asset_id": "mech_scout"}
    assert set(claimed) == {"actor", "role", "roles", "projects"}


def test_a_project_scope_is_not_an_identity_claim() -> None:
    """Scoping a listing narrows presentation; the actor is still authorized."""
    kept, claimed = strip_identity_claims({"project": PROJECT, "status": "modeling"})

    assert claimed == ()
    assert kept == {"project": PROJECT, "status": "modeling"}


def test_every_claim_name_is_recognised_case_insensitively() -> None:
    _, claimed = strip_identity_claims({name.upper(): "x" for name in IDENTITY_CLAIM_PARAMETERS})

    assert len(claimed) == len(IDENTITY_CLAIM_PARAMETERS)


# --------------------------------------------------------------------------
# 2.8, 2.9 — provider claims, then the file, then unmapped (D13)
# --------------------------------------------------------------------------


def test_provider_supplied_emails_win_and_the_file_does_not_change_the_result(
    provider: InMemoryIdentityProvider,
) -> None:
    provider.add(TOKEN, a_person(Role.ARTIST), git_emails=(WORK_EMAIL, PERSONAL_EMAIL))
    resolved = ActorResolver(project=PROJECT, provider=provider, credential=TOKEN).resolve()

    with_file = resolve_git_identity(resolved, MAPPING)
    without_file = resolve_git_identity(resolved, ActorMapping())

    assert with_file.source is GitIdentitySource.PROVIDER
    assert with_file.emails == (WORK_EMAIL, PERSONAL_EMAIL)
    assert with_file.emails == without_file.emails
    assert with_file.violations == ()


def test_the_file_answers_what_the_provider_does_not(resolver: ActorResolver) -> None:
    identity = resolve_git_identity(resolver.resolve(), MAPPING)

    assert identity.source is GitIdentitySource.MAPPING
    assert identity.emails == (WORK_EMAIL, PERSONAL_EMAIL)
    assert identity.author is not None
    assert identity.author.email == WORK_EMAIL


def test_neither_source_leaves_an_unmapped_identity_rather_than_nothing(
    resolver: ActorResolver,
) -> None:
    identity = resolve_git_identity(resolver.resolve(), ActorMapping())

    assert identity.is_unmapped
    assert identity.emails == ()
    assert identity.author is None
    assert identity.actor.id == ActorId(SUBJECT), "authorship is never dropped"


def test_a_disagreement_uses_the_provider_and_reports_the_file_entry(
    provider: InMemoryIdentityProvider,
) -> None:
    provider.add(TOKEN, a_person(Role.ARTIST), git_emails=(CLAIMED_EMAIL,))
    resolved = ActorResolver(project=PROJECT, provider=provider, credential=TOKEN).resolve()

    identity = resolve_git_identity(resolved, MAPPING)

    assert identity.emails == (CLAIMED_EMAIL,)
    (violation,) = identity.violations
    assert violation.rule_id == RULE_PROVIDER_DISAGREEMENT
    assert SUBJECT in violation.message
    assert WORK_EMAIL in violation.message
    assert CLAIMED_EMAIL in violation.message


def test_agreement_in_a_different_case_is_not_a_disagreement(
    provider: InMemoryIdentityProvider,
) -> None:
    provider.add(
        TOKEN, a_person(Role.ARTIST), git_emails=("RAFA@Cyberdyne.com", "Rafa@Personal.dev")
    )
    resolved = ActorResolver(project=PROJECT, provider=provider, credential=TOKEN).resolve()

    assert resolve_git_identity(resolved, MAPPING).violations == ()


# --------------------------------------------------------------------------
# 2.7, 2.10 — the mapping through the store, and the authors nobody bound
# --------------------------------------------------------------------------


@pytest.fixture
def store() -> InMemorySpecStore:
    return InMemorySpecStore()


def test_a_project_with_no_mapping_serves_an_empty_one(store: InMemorySpecStore) -> None:
    loaded = store.load_actor_mapping("")

    assert loaded.mapping.is_empty
    assert not loaded.is_declared
    assert loaded.is_readable


def test_an_unparseable_mapping_is_a_violation_rather_than_an_exception(
    store: InMemorySpecStore,
) -> None:
    store.set_actor_mapping_unparseable("line 4: found unexpected ':'")

    loaded = store.load_actor_mapping("")

    assert loaded.mapping.is_empty
    assert not loaded.is_readable
    assert [violation.rule_id for violation in loaded.violations] == [RULE_UNPARSEABLE]


def test_unmapped_authors_are_listed_once_each(store: InMemorySpecStore) -> None:
    store.set_actor_mapping(MAPPING)
    seen = (WORK_EMAIL, "ana@cyberdyne.com", "ANA@cyberdyne.com", "zoe@contractor.io")

    found = ran(list_unmapped_authors(seen, spec_store=store, root=""))

    assert found.emails == ("ana@cyberdyne.com", "zoe@contractor.io")
    assert len(found) == 2
    assert all(actor.is_unmapped for actor in found.authors)


def test_unmapped_authors_carry_the_mapping_violations(store: InMemorySpecStore) -> None:
    """A broken file lists every author as unmapped and says why."""
    store.set_actor_mapping_unparseable("not a mapping")

    found = ran(list_unmapped_authors((WORK_EMAIL,), spec_store=store))

    assert found.emails == (WORK_EMAIL,)
    assert [violation.rule_id for violation in found.violations] == [RULE_UNPARSEABLE]


# --------------------------------------------------------------------------
# The name and the address come from the same place
# --------------------------------------------------------------------------


def test_a_mapped_identity_is_authored_under_the_name_the_mapping_gives_it() -> None:
    """The defect the first real deployment wrote into history.

    CyberdyneAuth sends no `name` claim, so an actor resolved from one of its
    credentials falls back to its subject — a UUID. Taking the address from
    `.canon/actors.yaml` and the name from that actor produced commits reading
    `968a70af-8b4c-413c-… <leotest@test.com>`: an address everybody recognises
    beside a name nobody does, in the one file `git blame` reads.
    """
    mapping = ActorMapping(
        (
            ActorBinding(
                subject="968a70af-8b4c-413c-a502-fe0fbe9ce3ad",
                display_name="Leo Test",
                emails=("leotest@test.com",),
            ),
        )
    )
    from_token = Actor(id=ActorId("968a70af-8b4c-413c-a502-fe0fbe9ce3ad"), display_name="")
    resolved = resolve_git_identity(verified_as(from_token), mapping)

    author = resolved.author

    assert author is not None
    assert author.name == "Leo Test"
    assert author.email == "leotest@test.com"


def test_an_unmapped_identity_still_authors_under_whatever_named_it() -> None:
    """Empty `name` means *use the actor's*, which is all there is here."""
    actor = Actor(id=ActorId("auth|rafa"), display_name="Rafa")
    resolved = GitIdentity(
        actor=actor, emails=("rafa@cyberdyne.com",), source=GitIdentitySource.PROVIDER
    )

    author = resolved.author

    assert author is not None
    assert author.name == "Rafa"
