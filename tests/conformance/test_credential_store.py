"""Task 8.6 — the `CredentialStore` contract, fake and real adapter.

`KeychainCredentialStore` is exercised against a stand-in for `keyring` rather
than against the machine's own keychain, and the reason is not squeamishness: a
suite that wrote to the real login keychain would prompt a human being in the
middle of a test run on macOS, and would silently do nothing on a CI box with no
Secret Service. Neither of those checks anything.

What *is* checked here is the whole of what the adapter contains: the
translation between `keyring`'s vocabulary and the port's. An absent secret is
`None` rather than an exception; a delete of nothing is *there was nothing*
rather than an outage; a locked store is
:class:`~cybercanon.application.ports.credential_store.CredentialStoreUnavailable`
rather than a leaked backend error. The stand-in raises `keyring`'s **real**
exception types, imported from `keyring.errors`, so a release that changed them
fails here rather than on somebody's laptop.

The last test is the one the requirement is actually about, and it needs a
repository rather than a contract: after a sign-in, `git status` in the working
copy is empty and no file under it contains the credential.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
from contract import implementation_fixture
from credential_store_contract import ISSUED, CredentialStoreContract
from keyring.errors import PasswordDeleteError

from cybercanon.adapters.outbound.auth.keychain import KeychainCredentialStore
from cybercanon.application.ports.credential_store import CredentialStoreUnavailable
from cybercanon.application.testing.credential_store import InMemoryCredentialStore


class StandInKeyring:
    """`keyring`, as far as this adapter is concerned: three calls and its errors."""

    def __init__(self) -> None:
        self.secrets: dict[tuple[str, str], str] = {}
        self.locked = False

    def get_password(self, service: str, account: str) -> str | None:
        self._unlocked()
        return self.secrets.get((service, account))

    def set_password(self, service: str, account: str, password: str) -> None:
        self._unlocked()
        self.secrets[(service, account)] = password

    def delete_password(self, service: str, account: str) -> None:
        self._unlocked()
        if (service, account) not in self.secrets:
            raise PasswordDeleteError("no such password")
        del self.secrets[(service, account)]

    def _unlocked(self) -> None:
        if self.locked:
            raise RuntimeError("the credential store is locked")


def in_memory(directory: Path) -> InMemoryCredentialStore:
    return InMemoryCredentialStore()


def keychain(directory: Path) -> KeychainCredentialStore:
    return KeychainCredentialStore(service="cybercanon-test", backend=StandInKeyring())


implementation = implementation_fixture(fake=in_memory, keychain=keychain)


class TestCredentialStore(CredentialStoreContract):
    """The `CredentialStore` contract, against both implementations."""


# --------------------------------------------------------------------------
# What only the real adapter has: a backend that can be locked or absent
# --------------------------------------------------------------------------


def test_a_locked_keychain_is_unavailable_rather_than_signed_out() -> None:
    """ "I could not ask" must not be spelled the same way as "nobody signed in"."""
    backend = StandInKeyring()
    store = KeychainCredentialStore(service="cybercanon-test", backend=backend)
    store.store(ISSUED)
    backend.locked = True

    with pytest.raises(CredentialStoreUnavailable):
        store.load()


def test_a_failure_carries_no_credential_and_no_backend_text() -> None:
    """A keyring error can quote the entry it was reading, and the entry is the token."""
    backend = StandInKeyring()
    store = KeychainCredentialStore(service="cybercanon-test", backend=backend)
    store.store(ISSUED)
    backend.locked = True

    with pytest.raises(CredentialStoreUnavailable) as raised:
        store.load()

    assert ISSUED.value not in raised.value.message
    assert "locked" not in raised.value.message


def test_deleting_what_is_not_there_is_not_an_outage() -> None:
    """`keyring` raises for a missing entry; the port's answer is `False`."""
    store = KeychainCredentialStore(service="cybercanon-test", backend=StandInKeyring())

    assert store.erase() is False


# --------------------------------------------------------------------------
# The prohibition, over a real repository (task 8.6)
# --------------------------------------------------------------------------


@pytest.fixture
def working_copy(tmp_path: Path) -> Path:
    """A real git working copy with a committed specification in it."""
    root = tmp_path / "game"
    (root / "characters" / "mech_scout").mkdir(parents=True)
    (root / "characters" / "mech_scout" / "asset.yaml").write_text(
        "id: mech_scout\nname: Scout Mech\n", encoding="utf-8"
    )
    _git(root, "init", "-q", "-b", "main")
    _git(root, "config", "user.email", "rafa@cyberdyne.com")
    _git(root, "config", "user.name", "Rafa")
    _git(root, "add", "-A")
    _git(root, "commit", "-qm", "the scout mech")
    return root


def _git(root: Path, *arguments: str) -> str:
    return subprocess.run(
        ("git", *arguments), cwd=root, check=True, capture_output=True, text=True
    ).stdout


@pytest.mark.parametrize("build", [in_memory, keychain], ids=["fake", "keychain"])
def test_storing_a_credential_leaves_the_working_tree_untouched(working_copy: Path, build) -> None:
    """The requirement, over a repository: nothing changes and nothing leaks into it."""
    store = build(working_copy)

    store.store(ISSUED)

    assert _git(working_copy, "status", "--porcelain") == ""
    for path in working_copy.rglob("*"):
        if path.is_file() and ".git" not in path.parts:
            assert ISSUED.value not in path.read_text(encoding="utf-8", errors="ignore")
