"""The in-memory `CredentialStore` — one slot, and an outage on demand.

It holds the credential in an attribute rather than anywhere a path could reach,
which is the fake honouring the port's actual promise: the specified behaviour
is *"not written into the repository or any file inside it"*, and a fake that
wrote a temporary file would be conforming to a weaker port than the real one.

:meth:`fail_with` exists because a locked keychain is specified behaviour on the
adapter side — "I could not ask" is a failure and "nobody has signed in" is an
answer, and a fake that could only produce the second would let the difference
rot.
"""

from __future__ import annotations

from cybercanon.application.ports.identity_provider import Credential


class InMemoryCredentialStore:
    """One person's credential, kept nowhere a repository could see it."""

    def __init__(self, service: str = "cybercanon") -> None:
        self.service = service
        self._credential: Credential | None = None
        self._failure: Exception | None = None
        self.writes = 0
        self.erasures = 0

    # -- seeding ---------------------------------------------------------

    def fail_with(self, error: Exception | None) -> None:
        """Make every operation raise. ``None`` clears it."""
        self._failure = error

    # -- port ------------------------------------------------------------

    def store(self, credential: Credential) -> None:
        self._raise_if_failing()
        self._credential = credential
        self.writes += 1

    def load(self) -> Credential | None:
        self._raise_if_failing()
        return self._credential

    def erase(self) -> bool:
        self._raise_if_failing()
        had = self._credential is not None
        self._credential = None
        self.erasures += 1
        return had

    def _raise_if_failing(self) -> None:
        if self._failure is not None:
            raise self._failure


__all__ = ["InMemoryCredentialStore"]
