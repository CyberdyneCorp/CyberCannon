"""The `InteractiveSignIn` port — a person proves who they are, in a browser.

`auth-integration` fixes the shape and forbids the shortcut: a person signing in
from a terminal *"SHALL be able to complete sign-in by approving a device
authorization in a browser, without pasting a credential"*, and the surface
*"SHALL NOT accept a password"*. So the port has exactly two steps and no field
for a secret the person types:

* :meth:`begin` asks the issuer to start a grant and returns what the person
  must be shown — a URL to open and a code to confirm;
* :meth:`redeem` waits for them to approve it and returns the issued credential.

Nothing here knows the credential's format. `begin` returns a
:class:`DeviceGrant` whose `device_code` is the issuer's own handle, opaque to
this layer exactly as :class:`~cybercanon.application.ports.identity_provider.Credential`
is, and `redeem` returns a `Credential` that only the verification adapter ever
looks inside.

The port is separate from `IdentityProvider` on purpose: *obtaining* a
credential and *verifying* one are different jobs with different failure modes,
and the surfaces that need them barely overlap — the command line signs in and
never verifies, the hosted API verifies and never signs in.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from cybercanon.application.errors import FailureKind, OperationFailed
from cybercanon.application.ports.identity_provider import Credential


@dataclass(frozen=True)
class DeviceGrant:
    """What a person must be shown to approve a sign-in, and for how long.

    `device_code` is excluded from the generated `repr` for the same reason a
    credential's value is: it is a bearer handle for the duration of the grant,
    and a handle in a log line is a sign-in somebody else can complete.
    """

    verification_uri: str
    user_code: str
    device_code: str = field(repr=False)
    expires_in_s: int = 300
    interval_s: int = 5

    def __post_init__(self) -> None:
        if not self.verification_uri.strip():
            raise ValueError("a device grant names the address the person opens")
        if not self.user_code.strip():
            raise ValueError("a device grant carries the code the person confirms")
        if not self.device_code.strip():
            raise ValueError("a device grant carries the issuer's own handle")


class SignInFailed(OperationFailed):
    """The sign-in did not complete — declined, expired, or never approved."""

    kind = FailureKind.UNAUTHENTICATED
    identifier = "sign_in.failed"

    def __init__(self, reason: str, subject: str = "the sign-in") -> None:
        super().__init__(f"the sign-in did not complete: {reason}", subject)
        self.reason = reason


class SignInUnavailable(OperationFailed):
    """The identity service could not be reached to start or finish a sign-in."""

    kind = FailureKind.UNAVAILABLE
    identifier = "sign_in.unavailable"

    def __init__(self, reason: str = "", subject: str = "the identity service") -> None:
        detail = f": {reason}" if reason else ""
        super().__init__(f"the identity service is unavailable{detail}", subject)
        self.reason = reason


class InteractiveSignIn(Protocol):
    """Starts a browser-approved sign-in and collects the credential it issues."""

    def begin(self) -> DeviceGrant:
        """Ask the issuer to start a grant. Raises :class:`SignInUnavailable`."""
        ...

    def redeem(self, grant: DeviceGrant) -> Credential:
        """Wait for approval and return the issued credential.

        Raises :class:`SignInFailed` when the person declined or let the grant
        expire, and :class:`SignInUnavailable` when the issuer could not be
        reached. It never returns ``None``: an absent credential is a failure
        with a reason, not a value every call site has to test.
        """
        ...


__all__ = [
    "DeviceGrant",
    "InteractiveSignIn",
    "SignInFailed",
    "SignInUnavailable",
]
