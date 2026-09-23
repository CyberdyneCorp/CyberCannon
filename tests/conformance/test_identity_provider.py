"""Tasks 2.1 and 4.5 — the `IdentityProvider` contract, every implementation.

Two fakes today and no real adapter: the CyberdyneAuth adapter is a later
change, and it joins by adding one factory here. That is the point of writing
the contract now — the identity rules are specified before an identity provider
exists, so the suite that will judge the real adapter is written against the
behaviour the specification asks for rather than against whatever the adapter
turns out to do.

The two fakes are the two shapes the port permits (task 4.5): one that supplies
a person's git author emails and one that supplies none. Which of them
CyberdyneAuth turns out to be is a configuration outcome rather than a
requirement (D13), so both have to conform, and a change that quietly made
`git_emails` mandatory would fail here rather than in a repository whose
`.canon/actors.yaml` stopped being consulted.

**Group 8 adds the real adapter, and it joined by adding one factory — exactly
as this module predicted.** It needs one piece of scaffolding the fakes do not:
the contract addresses its people by opaque handles (`token-rafa-with-emails`),
and CyberdyneAuth reads a signed token. :class:`AsIssued` translates the handle
into a credential the fake issuer really minted and hands it to the real
adapter, which then does all of its own work — signature, issuer, audience,
validity, group mapping, claim translation. A handle it does not know is passed
through untouched, so the contract's unresolvable credential reaches the adapter
as the garbage it is and is refused by the adapter rather than by the shim.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from contract import implementation_fixture
from identity_provider_contract import (
    ANA,
    BARE,
    DESCRIBED,
    ORGANISATION,
    PROJECT,
    RAFA,
    RAFA_EMAILS,
    IdentityProviderContract,
)

from canon_issuer import ANOTHER_CLIENT_ID, EPOCH, PRO_MONTHLY, FakeIssuer, an_org
from cybercanon.adapters.outbound.auth.cyberdyne import CyberdyneAuth, Trust
from cybercanon.adapters.outbound.auth.keys import CachedKeySet
from cybercanon.application.ports.identity_provider import (
    Credential,
    IdentityProvider,
    ResolvedIdentity,
)
from cybercanon.application.testing.identity_provider import InMemoryIdentityProvider

ART_LEAD_KEY = "art_director"
ARTIST_KEY = "artist"
GROUP_ROLES = {ART_LEAD_KEY: "ART_DIRECTOR", ARTIST_KEY: "ARTIST"}
"""Role keys as CyberdyneAuth spells them, before the client-id prefix."""


class AsIssued:
    """The contract's opaque handles, minted into credentials the adapter can read.

    It is a translation and not a stub: every handle it knows becomes a real
    signed token, and `resolve` is the real adapter's. A handle it does not know
    is handed over unchanged, which is how the contract's unresolvable
    credential stays unresolvable.
    """

    def __init__(self, provider: IdentityProvider, issued: dict[str, Credential]) -> None:
        self._provider = provider
        self._issued = issued

    def resolve(self, credential: Credential) -> ResolvedIdentity:
        return self._provider.resolve(self._issued.get(credential.value, credential))


def in_memory(directory: Path) -> InMemoryIdentityProvider:
    """The fake, holding exactly the credentials the contract asks about."""
    provider = InMemoryIdentityProvider()
    provider.add(DESCRIBED, RAFA, git_emails=RAFA_EMAILS)
    provider.add(BARE, ANA)
    return provider


def in_memory_without_git_authorship(directory: Path) -> InMemoryIdentityProvider:
    """A provider that resolves the same people and describes no commit addresses.

    Conforming, and the shape CyberdyneAuth has today (D13): every credential
    resolves, and the link between a subject and its git emails comes from
    `.canon/actors.yaml` instead.
    """
    provider = InMemoryIdentityProvider()
    provider.add(DESCRIBED, RAFA)
    provider.add(BARE, ANA)
    return provider


def cyberdyne(directory: Path) -> AsIssued:
    """The real adapter, over a real issuer, resolving the contract's two people.

    The credentials are minted **in the shape CyberdyneAuth emits**: `roles`
    prefixed with the client id, `orgs` for the organisation the person belongs
    to, `entitlements` for the billing products they hold, and no `name` and no
    `git_emails`, because a real access token carries neither.

    The contract asks these people to be entitled to `PROJECT`, and nothing in a
    real token names a project: entitlement is `orgs` plus a role on this
    client. So the adapter is told the three things it cannot guess — the client
    id its roles are prefixed with, the organisation whose members it serves and
    the project they read — and the credentials carry the organisation it was
    told about.

    There used to be a `describes_git_authorship` switch here and a second
    factory built from it, so that CyberdyneAuth ran the contract as *both* of
    the shapes the port permits. It could only do that because this file minted
    a `git_emails` claim the issuer has never sent. The switch is gone: there is
    one CyberdyneAuth, it describes no commit addresses, and it therefore stands
    for the port's "describes none" shape while the fake stands for the other.

    Rafa also holds an art director role on **another client**, because that is
    what the claim really looks like — one list covering every application in
    the organisation — and the contract's `RAFA` holds `ARTIST` alone.
    """
    issuer = FakeIssuer()
    provider = CyberdyneAuth(
        trust=Trust(
            issuer=issuer.issuer,
            audience=issuer.audience,
            client_id=issuer.client_id,
            organisation=ORGANISATION,
        ),
        keys=CachedKeySet(issuer),
        project=PROJECT,
        group_roles=GROUP_ROLES,
        now=lambda: datetime.fromtimestamp(EPOCH, tz=UTC),
    )
    home = an_org(ORGANISATION, "contract-studio")
    return AsIssued(
        provider,
        {
            DESCRIBED.value: issuer.mint(
                RAFA.id.value,
                roles=[ARTIST_KEY, f"{ANOTHER_CLIENT_ID}:{ART_LEAD_KEY}"],
                orgs=[home],
                entitlements=[PRO_MONTHLY],
            ),
            BARE.value: issuer.mint(
                ANA.id.value,
                roles=[ART_LEAD_KEY],
                orgs=[home],
                entitlements=[PRO_MONTHLY],
            ),
        },
    )


implementation = implementation_fixture(fake=in_memory, cyberdyne=cyberdyne)
describes_git_authorship = implementation_fixture(fake=in_memory)
"""The providers that answer D13's first question at all.

CyberdyneAuth is deliberately absent, and its absence is the finding rather than
a gap: a real access token carries no commit addresses, so the only way this
adapter could have satisfied *"a provider may supply git author emails"* was for
this file to mint a claim the issuer never sends — which is exactly what it used
to do. It runs the other shape, below, and every implementation-agnostic
scenario in the contract.
"""

without_git_authorship = implementation_fixture(
    fake=in_memory_without_git_authorship, cyberdyne=cyberdyne
)


class TestIdentityProvider(IdentityProviderContract):
    """The `IdentityProvider` contract, against the in-memory fake."""
