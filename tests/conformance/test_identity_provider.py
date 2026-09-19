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
"""

from __future__ import annotations

from pathlib import Path

from contract import implementation_fixture
from identity_provider_contract import (
    ANA,
    BARE,
    DESCRIBED,
    RAFA,
    RAFA_EMAILS,
    IdentityProviderContract,
)

from cybercanon.application.testing.identity_provider import InMemoryIdentityProvider


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


implementation = implementation_fixture(fake=in_memory)
without_git_authorship = implementation_fixture(fake=in_memory_without_git_authorship)


class TestIdentityProvider(IdentityProviderContract):
    """The `IdentityProvider` contract, against the in-memory fake."""
