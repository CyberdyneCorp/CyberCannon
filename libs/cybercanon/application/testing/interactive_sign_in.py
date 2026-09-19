"""The in-memory `InteractiveSignIn` — a grant, an approval, and the two refusals.

A sign-in has three interesting endings and only one of them is success, so the
fake models all three: the person approves and a credential is issued, the
person declines or lets the grant expire (:class:`SignInFailed`), or the issuer
cannot be reached at all (:class:`SignInUnavailable`).

What it deliberately cannot do is accept a password. There is no method here
that takes one, which is the same structural refusal
:meth:`~cybercanon.application.use_cases.resolve_actor.ActorResolver.resolve`
makes about identity parameters: a shape with no slot for the wrong thing cannot
be handed the wrong thing by accident.
"""

from __future__ import annotations

from cybercanon.application.ports.identity_provider import Credential
from cybercanon.application.ports.interactive_sign_in import DeviceGrant, SignInFailed

VERIFICATION_URI = "https://auth.cyberdynecorp.ai/activate"
USER_CODE = "WDJB-MJHT"
DEVICE_CODE = "device-code-for-this-terminal"


class InMemoryInteractiveSignIn:
    """A device grant a test approves, declines or leaves hanging."""

    def __init__(self, issues: Credential | None = None) -> None:
        self._issues = issues or Credential("a-credential-the-issuer-signed")
        self._approved = True
        self._declined_because = ""
        self._failure: Exception | None = None
        self.grants = 0
        self.redemptions = 0

    # -- seeding ---------------------------------------------------------

    def approves(self, credential: Credential | None = None) -> None:
        """The person approves the grant, and this is what they are issued."""
        self._approved = True
        if credential is not None:
            self._issues = credential

    def declines(self, reason: str = "the person declined the device authorization") -> None:
        """The person refuses, or the grant expires before they answer."""
        self._approved = False
        self._declined_because = reason

    def fail_with(self, error: Exception | None) -> None:
        """Make both steps raise — the issuer being unreachable. ``None`` clears it."""
        self._failure = error

    # -- port ------------------------------------------------------------

    def begin(self) -> DeviceGrant:
        self._raise_if_failing()
        self.grants += 1
        return DeviceGrant(
            verification_uri=VERIFICATION_URI, user_code=USER_CODE, device_code=DEVICE_CODE
        )

    def redeem(self, grant: DeviceGrant) -> Credential:
        self._raise_if_failing()
        self.redemptions += 1
        if not self._approved:
            raise SignInFailed(self._declined_because)
        return self._issues

    def _raise_if_failing(self) -> None:
        if self._failure is not None:
            raise self._failure


__all__ = ["DEVICE_CODE", "USER_CODE", "VERIFICATION_URI", "InMemoryInteractiveSignIn"]
