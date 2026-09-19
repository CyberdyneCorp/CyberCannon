"""The operating system's credential store — the only place a person's token lives.

`auth-integration` is prescriptive about the location and about two things that
must never happen: the credential *"SHALL be stored in the operating system's
credential store, SHALL NOT be written into the repository or any file inside
it, and SHALL be removable by an explicit sign-out."*

So this adapter has **no path**. There is no directory to configure, no file to
name, and nothing that could be pointed at a working copy by a well-meaning
`--config`. It knows a service name and an account, and `keyring` knows where
the machine keeps such things — Keychain on macOS, the Secret Service or
KWallet on Linux, the Credential Manager on Windows.

`backend` is injected so the adapter's own translation — an absent secret is
``None``, a locked store is a failure, deleting nothing is not an error — can be
tested without a real keychain prompting a human being in the middle of a test
run. It defaults to `keyring` itself, so nothing in production supplies it.
"""

from __future__ import annotations

from typing import Any, Protocol

from cybercanon.application.ports.credential_store import CredentialStoreUnavailable
from cybercanon.application.ports.identity_provider import Credential

SERVICE = "cybercanon"
"""How CyberCanon's entry is named in the machine's credential store."""

ACCOUNT = "credential"
"""One entry per service: a machine's `canon` is signed in as one person."""


class Keyring(Protocol):
    """The three operations this adapter needs from a credential store library."""

    def get_password(self, service: str, account: str) -> str | None: ...

    def set_password(self, service: str, account: str, password: str) -> None: ...

    def delete_password(self, service: str, account: str) -> None: ...


class KeychainCredentialStore:
    """A person's credential, in the machine's own store and nowhere else."""

    def __init__(
        self,
        *,
        service: str = SERVICE,
        account: str = ACCOUNT,
        backend: Keyring | None = None,
    ) -> None:
        self.service = service
        self.account = account
        self._backend = backend

    @property
    def description(self) -> str:
        """How a message names this store to a person, for `canon auth status`."""
        return f"the operating system credential store, as {self.service!r}"

    @property
    def backend(self) -> Any:
        """The library doing the work, imported on first use.

        Deferred because `canon validate` must never need it: importing
        `keyring` opens the platform backend, and a validator that touched a
        locked keychain would fail for a reason that has nothing to do with the
        asset it was asked about.
        """
        if self._backend is None:
            import keyring

            self._backend = keyring
        return self._backend

    # -- port ------------------------------------------------------------

    def store(self, credential: Credential) -> None:
        try:
            self.backend.set_password(self.service, self.account, credential.value)
        except Exception as failure:
            raise CredentialStoreUnavailable(self.service, _why(failure)) from failure

    def load(self) -> Credential | None:
        try:
            stored = self.backend.get_password(self.service, self.account)
        except Exception as failure:
            raise CredentialStoreUnavailable(self.service, _why(failure)) from failure
        return Credential(stored) if stored else None

    def erase(self) -> bool:
        """Remove the entry, answering whether there was one. Twice is not an error.

        `keyring` raises when asked to delete nothing, and that raise is not a
        failure of this operation: the person asked for no credential to be
        stored here, and after both calls none is. So the absence is looked up
        first and the raise is read as *there was nothing*, never as an outage.
        """
        if self.load() is None:
            return False
        try:
            self.backend.delete_password(self.service, self.account)
        except Exception as failure:
            if self._gone():
                return True
            raise CredentialStoreUnavailable(self.service, _why(failure)) from failure
        return True

    def _gone(self) -> bool:
        """Whether the entry is absent now, whatever the delete said."""
        try:
            return self.backend.get_password(self.service, self.account) is None
        except Exception:
            return False


def _why(failure: Exception) -> str:
    """The failure's type, never its text.

    A keyring error can quote the entry it was reading, and the entry is the
    credential. The type is enough to tell a locked store from an absent one and
    carries nothing a log should not hold.
    """
    return type(failure).__name__


__all__ = ["ACCOUNT", "SERVICE", "KeychainCredentialStore", "Keyring"]
