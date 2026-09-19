"""Signing in from a terminal, and signing out again (task 8.6).

Three operations over two ports, and the interesting thing about them is what
they refuse to have:

* **no password.** :func:`sign_in` takes no secret from the person. It asks the
  issuer for a device grant, shows them where to approve it, and collects
  whatever the issuer then issues.
* **no path.** Nothing here can be told where to put the credential; the
  :class:`~cybercanon.application.ports.credential_store.CredentialStore` knows,
  and the specified answer is the operating system's credential store rather
  than any file — least of all one inside the repository.
* **no effect on validation.** `canon validate` never calls any of this. That is
  the point of the third scenario in the requirement — *"validation SHALL
  complete normally"* on a machine that has never signed in — and it stays true
  because these use cases are reachable only from `canon auth`.

`announce` is a callback rather than a return value because the device flow has
a step in the middle: the person has to be shown a URL and a code *while the
process waits for them*. Returning the grant and asking the caller to come back
would put the flow's shape in the inbound adapter, which is where it would
diverge between surfaces.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from cybercanon.application.ports.credential_store import CredentialStore
from cybercanon.application.ports.interactive_sign_in import DeviceGrant, InteractiveSignIn
from cybercanon.application.results import as_result

Announce = Callable[[DeviceGrant], None]
"""How the person is shown what to approve. Defaults to telling them nothing."""


def announce_nothing(grant: DeviceGrant) -> None:
    """The default: a caller that wants the person to see something supplies one."""


@dataclass(frozen=True)
class SignedIn:
    """A completed sign-in: where it was approved, and where it was kept.

    It carries **no credential**. A sign-in's result is that a credential is in
    the credential store, and handing it back up would put it on a return path
    through the inbound adapter — which is how a token ends up in a log line or,
    with `--json`, on standard output.
    """

    verification_uri: str
    stored_in: str

    def __str__(self) -> str:
        return f"signed in; the credential is stored in {self.stored_in}"


@dataclass(frozen=True)
class SignedOut:
    """A sign-out, and whether there was anything to remove.

    `removed` is false for a machine that was already signed out, which is not a
    failure: the intent is *no credential here*, and it is satisfied either way.
    """

    stored_in: str
    removed: bool

    def __str__(self) -> str:
        if self.removed:
            return f"signed out; the credential was removed from {self.stored_in}"
        return f"no credential was stored in {self.stored_in}"


@dataclass(frozen=True)
class SignInStatus:
    """Whether this machine holds a credential, and where it holds it."""

    stored_in: str
    signed_in: bool

    def __str__(self) -> str:
        state = "a credential is stored" if self.signed_in else "no credential is stored"
        return f"{state} in {self.stored_in}"


@as_result
def sign_in(
    *,
    interactive_sign_in: InteractiveSignIn,
    credential_store: CredentialStore,
    announce: Announce = announce_nothing,
) -> SignedIn:
    """Approve a device authorization in a browser, and keep what it issues.

    The credential goes straight from the port that obtained it to the port that
    keeps it. It is never returned, never rendered and never written beside the
    repository — the three ways the specified prohibition is usually broken.
    """
    grant = interactive_sign_in.begin()
    announce(grant)
    credential = interactive_sign_in.redeem(grant)
    credential_store.store(credential)
    return SignedIn(verification_uri=grant.verification_uri, stored_in=_where(credential_store))


@as_result
def sign_out(*, credential_store: CredentialStore) -> SignedOut:
    """Remove this machine's stored credential. Twice is not an error."""
    return SignedOut(stored_in=_where(credential_store), removed=credential_store.erase())


@as_result
def sign_in_status(*, credential_store: CredentialStore) -> SignInStatus:
    """Whether a credential is stored here — never what it is."""
    return SignInStatus(
        stored_in=_where(credential_store), signed_in=credential_store.load() is not None
    )


def _where(credential_store: CredentialStore) -> str:
    """How a store names itself to a person, falling back to its type.

    A store *may* describe where it keeps things — "the macOS keychain, as
    `cybercanon`" — and the message is much more useful when it does. A store
    that describes nothing still produces a sentence, because a missing
    description is not a reason to refuse a sign-out.
    """
    return str(getattr(credential_store, "description", "") or type(credential_store).__name__)


__all__ = [
    "Announce",
    "SignInStatus",
    "SignedIn",
    "SignedOut",
    "announce_nothing",
    "sign_in",
    "sign_in_status",
    "sign_out",
]
