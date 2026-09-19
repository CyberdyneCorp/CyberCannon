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
    PROJECT,
    RAFA,
    RAFA_EMAILS,
    IdentityProviderContract,
)

from canon_issuer import EPOCH, FakeIssuer
from cybercanon.adapters.outbound.auth.cyberdyne import CyberdyneAuth, Trust
from cybercanon.adapters.outbound.auth.keys import CachedKeySet
from cybercanon.application.ports.identity_provider import (
    Credential,
    IdentityProvider,
    ResolvedIdentity,
)
from cybercanon.application.testing.identity_provider import InMemoryIdentityProvider

ART_LEADS = "cyberdyne-art-leads"
ARTISTS = "cyberdyne-artists"
GROUP_ROLES = {ART_LEADS: "ART_DIRECTOR", ARTISTS: "ARTIST"}


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


def cyberdyne(directory: Path, *, describes_git_authorship: bool = True) -> AsIssued:
    """The real adapter, over a real issuer, resolving the contract's two people."""
    issuer = FakeIssuer()
    provider = CyberdyneAuth(
        trust=Trust(issuer=issuer.issuer, audience=issuer.audience),
        keys=CachedKeySet(issuer),
        group_roles=GROUP_ROLES,
        now=lambda: datetime.fromtimestamp(EPOCH, tz=UTC),
    )
    emails = RAFA_EMAILS if describes_git_authorship else ()
    return AsIssued(
        provider,
        {
            DESCRIBED.value: issuer.mint(
                RAFA.id.value,
                name=RAFA.display_name,
                groups=[ARTISTS],
                projects=[PROJECT],
                git_emails=emails,
            ),
            BARE.value: issuer.mint(
                ANA.id.value,
                name=ANA.display_name,
                groups=[ART_LEADS],
                projects=[PROJECT],
            ),
        },
    )


def cyberdyne_without_git_authorship(directory: Path) -> AsIssued:
    """The shape CyberdyneAuth has today: no commit addresses in any claim (D13)."""
    return cyberdyne(directory, describes_git_authorship=False)


implementation = implementation_fixture(fake=in_memory, cyberdyne=cyberdyne)
without_git_authorship = implementation_fixture(
    fake=in_memory_without_git_authorship, cyberdyne=cyberdyne_without_git_authorship
)


class TestIdentityProvider(IdentityProviderContract):
    """The `IdentityProvider` contract, against the in-memory fake."""
