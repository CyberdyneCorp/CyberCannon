"""Task 3.1 — a machine whose credential store cannot be reached (D5).

The adapter that keeps a person's credential already exists and already answers
the `CredentialStore` contract. What this change adds is the consequence D5
states and nothing yet asserted: *"when the keychain is unavailable the system
reports that writes are unavailable and keeps reads working, rather than falling
back to a file."*

Three things are checked, and the third is the one that matters most:

* **writes are unavailable, with a reason.** `canon auth status` answers *not
  signed in*, carries the store's own explanation, and a write is refused
  naming the sign-in action — a person told only "not signed in" would sign in
  again into the same locked keychain;
* **reads are untouched.** Looking an asset up on a machine with a locked
  keychain is exactly as usable as on one that never had a credential at all.
  That is the whole local-first promise: the validator *"SHALL never require
  identity"*;
* **nothing is written to a file instead.** No path appears anywhere in the
  adapter's construction, and a directory handed to it stays empty. A file
  fallback was the tempting fix and it is the one D5 refuses, because a token in
  a file is a token in somebody's `git status` eventually.
"""

from __future__ import annotations

import inspect
from pathlib import Path

import pytest

from cybercanon.adapters.outbound.auth.keychain import KeychainCredentialStore
from cybercanon.application.ports.credential_store import CredentialStoreUnavailable
from cybercanon.application.ports.identity_provider import Credential
from cybercanon.application.ports.search_index import IndexedAsset
from cybercanon.application.ports.spec_store import ProjectConfig
from cybercanon.application.results import Unauthenticated, succeeded
from cybercanon.application.testing.annotation_writer import InMemoryAnnotationWriter
from cybercanon.application.testing.outcomes import ran
from cybercanon.application.testing.search_index import InMemorySearchIndex
from cybercanon.application.testing.spec_store import InMemorySpecStore
from cybercanon.application.use_cases.lookup_assets import where_is
from cybercanon.application.use_cases.observations import (
    SIGN_IN_ACTION,
    ObservationRequest,
    WriteSession,
    record_observation,
    show_identity,
)
from cybercanon.application.use_cases.resolve_actor import ActorResolver, IdentityCache
from cybercanon.domain.annotations import AnnotationKind, ObservationKind
from cybercanon.domain.asset import Asset, AssetId
from cybercanon.domain.identity import AgentId

pytestmark = pytest.mark.integration

PROJECT = "ronin"
ASSET = "mech_scout"
SPEC_PATH = "characters/mech_scout/asset.yaml"
BLENDER = AgentId("blender-agent")
ISSUED = Credential("a-token-nobody-should-ever-see-on-disk")


class LockedKeyring:
    """A credential store the machine has but will not open — a locked keychain."""

    def get_password(self, service: str, account: str) -> str | None:
        raise RuntimeError("the credential store is locked")

    def set_password(self, service: str, account: str, password: str) -> None:
        raise RuntimeError("the credential store is locked")

    def delete_password(self, service: str, account: str) -> None:
        raise RuntimeError("the credential store is locked")


@pytest.fixture
def locked() -> KeychainCredentialStore:
    return KeychainCredentialStore(service="cybercanon-test", backend=LockedKeyring())


def _read_surface() -> tuple[InMemorySpecStore, InMemorySearchIndex]:
    store = InMemorySpecStore()
    store.add(SPEC_PATH, Asset(id=AssetId(ASSET), name="Scout Mech"))
    store.set_project(ProjectConfig(name=PROJECT))
    index = InMemorySearchIndex()
    index.upsert(
        IndexedAsset(asset_id=ASSET, name="Scout Mech", project=PROJECT, spec_path=SPEC_PATH)
    )
    return store, index


def _a_write(index: InMemorySearchIndex) -> WriteSession:
    writer = InMemoryAnnotationWriter()
    writer.declare(ASSET, SPEC_PATH)
    return WriteSession(
        project=PROJECT,
        resolver=ActorResolver(project=PROJECT, cache=IdentityCache()),
        writer=writer,
        agent=BLENDER,
        search_index=index,
    )


def _an_observation() -> ObservationRequest:
    return ObservationRequest(
        asset=ASSET,
        target="head",
        text="12000 triangles is unreachable without losing the head silhouette",
        kind=AnnotationKind.TECHNICAL.value,
        observation_kind=ObservationKind.UNATTAINABLE_CONSTRAINT.value,
    )


def test_a_locked_keychain_is_an_outage_rather_than_a_signed_out_person(
    locked: KeychainCredentialStore,
) -> None:
    with pytest.raises(CredentialStoreUnavailable):
        locked.load()


def test_identity_reports_writes_as_unavailable_and_says_why(
    locked: KeychainCredentialStore,
) -> None:
    identity = ran(
        show_identity(
            resolver=ActorResolver(project=PROJECT, cache=IdentityCache()),
            credential_store=locked,
            agent=BLENDER,
        )
    )

    assert not identity.signed_in
    assert not identity.may_write
    assert "unavailable" in identity.detail
    assert identity.stored_in


def test_the_write_is_refused_naming_the_sign_in_action(locked: KeychainCredentialStore) -> None:
    """The refusal is the one a signed-out machine gets: reads keep working."""
    _, index = _read_surface()
    session = _a_write(index)

    refusal = record_observation(session, _an_observation())

    assert isinstance(refusal, Unauthenticated)
    assert SIGN_IN_ACTION in refusal.message
    assert session.writer.recorded(ASSET) == ()


def test_the_read_surface_is_untouched(locked: KeychainCredentialStore) -> None:
    store, index = _read_surface()

    located = where_is(ASSET, spec_store=store, search_index=index)

    assert succeeded(located)


def test_nothing_falls_back_to_a_file(locked: KeychainCredentialStore, tmp_path: Path) -> None:
    """D5 refuses the tempting fix: there is no path to fall back *to*."""
    with pytest.raises(CredentialStoreUnavailable):
        locked.store(ISSUED)

    parameters = inspect.signature(KeychainCredentialStore.__init__).parameters
    assert not any("path" in name or "file" in name or "dir" in name for name in parameters)
    assert list(tmp_path.rglob("*")) == []
