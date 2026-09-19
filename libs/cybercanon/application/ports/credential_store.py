"""The `CredentialStore` port — where a person's terminal credential lives.

`auth-integration` states the requirement as a place and two prohibitions: the
credential *"SHALL be stored in the operating system's credential store, SHALL
NOT be written into the repository or any file inside it, and SHALL be removable
by an explicit sign-out"*.

The prohibition is the reason this is a port rather than a helper. A store with
a path in its signature is a store somebody eventually points at the working
copy, and then a token is in `git status` — so there is **no path anywhere in
this module**, and the only way to name *where* is the `service` a store is
constructed with. The OS keychain is the adapter; the fake is a dictionary; and
`canon validate` never asks either of them anything, because validation requires
no identity at all.

Three operations, and they are deliberately not four: store, load, erase. There
is no "list" — a surface that could enumerate credentials is a surface that can
leak them, and one process signs in as one person.
"""

from __future__ import annotations

from typing import Protocol

from cybercanon.application.errors import FailureKind, OperationFailed
from cybercanon.application.ports.identity_provider import Credential


class CredentialStoreUnavailable(OperationFailed):
    """The credential store could not be reached — a locked or absent keychain.

    Unavailable rather than not-found: *"there is no credential stored"* is an
    answer (``None``), and *"I could not ask"* is a failure. Collapsing the two
    would make a locked keychain look like a signed-out person and send them
    through a sign-in that cannot succeed either.
    """

    kind = FailureKind.UNAVAILABLE
    identifier = "credential_store.unavailable"

    def __init__(self, subject: str, reason: str = "") -> None:
        detail = f": {reason}" if reason else ""
        super().__init__(f"the credential store for {subject} is unavailable{detail}", subject)
        self.reason = reason


class CredentialStore(Protocol):
    """Keeps one person's credential for one service, outside the repository."""

    def store(self, credential: Credential) -> None:
        """Keep this credential, replacing whatever was kept before."""
        ...

    def load(self) -> Credential | None:
        """The stored credential, or ``None`` when nobody has signed in here.

        ``None`` is an ordinary answer and never a failure: a machine that has
        never signed in is the machine `canon validate` is designed for.
        """
        ...

    def erase(self) -> bool:
        """Remove the stored credential. Answers whether there was one.

        Idempotent by contract — signing out twice is not an error, because the
        person's intent is *no credential here* and that intent is satisfied
        both times.
        """
        ...


__all__ = ["CredentialStore", "CredentialStoreUnavailable"]
