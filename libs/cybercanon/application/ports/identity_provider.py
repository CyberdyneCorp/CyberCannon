"""The `IdentityProvider` port — a credential in, a resolved actor out (D4).

One question: *who is the process running as*. The answer is a resolved
:class:`~cybercanon.domain.identity.Actor`, and the credential that produced it
stays on this side of the boundary — no claim name, group name, token field or
issuing service crosses it. That is what makes `agent-identity`'s promise
mechanical rather than aspirational: an authorization decision is verifiable
with no identity service running, because the decision only ever sees an actor.

Three properties the port is shaped by:

* **It may fail, and failing is ordinary.** A local-first read surface runs on
  laptops that are off the VPN. :class:`IdentityUnavailable` is the failure, and
  the resolution chain in
  :mod:`cybercanon.application.use_cases.resolve_actor` degrades past it rather
  than refusing a read.
* **It MAY describe git authorship.** `CyberdyneAuth` may one day carry a
  person's commit addresses as a claim; until it does, `.canon/actors.yaml`
  answers instead. D13 fixes the order — provider first, file second — so
  :class:`ResolvedIdentity` carries `git_emails` that are simply empty when the
  provider does not describe them.
* **Identity is never a parameter.** Nothing here accepts an actor id, a role or
  a group from a caller. The only input is the credential the process was
  launched with.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from cybercanon.application.errors import FailureKind, OperationFailed
from cybercanon.domain.identity import Actor


@dataclass(frozen=True)
class Credential:
    """The opaque launch credential. Nothing in the core reads inside it.

    `value` is excluded from the generated `repr` and `__str__` says only that a
    credential is present, so a secret cannot reach a log line, a prose response
    or a test failure by accident. Comparison still works, because the dataclass
    compares the field it does not print.
    """

    value: str = field(repr=False)

    def __post_init__(self) -> None:
        if not self.value or not self.value.strip():
            raise ValueError("a credential is a non-empty opaque string")

    def __str__(self) -> str:
        return "<credential>"


@dataclass(frozen=True)
class ResolvedIdentity:
    """What a provider answered: an actor, and optionally its git authorship.

    `git_emails` is empty when the provider does not describe the link between
    the subject and its commit addresses — which is the ordinary case today and
    the reason `.canon/actors.yaml` exists at all (D13). Empty is an answer, not
    a failure: the mapping file is consulted next.
    """

    actor: Actor
    git_emails: tuple[str, ...] = ()

    @property
    def describes_git_authorship(self) -> bool:
        """Whether this provider answered the question the mapping file answers."""
        return bool(self.git_emails)


class IdentityUnavailable(OperationFailed):
    """The credential could not be resolved to an actor, for any reason.

    One failure rather than a taxonomy, **for the local surface**: unreachable,
    timing out, expired and refused all produce the same behaviour in the
    resolution chain — fall through to the cached actor, then to the local one —
    so splitting them there would add names no caller branches on.

    The networked surface does need the distinction, because `auth-integration`
    refuses a bad credential *as unauthenticated* and an unreachable issuer *as
    unavailable*, and those are different answers. The two subclasses below
    supply it without changing what this port promises: every failure here is
    still an `IdentityUnavailable`, so the chain that degrades past it is
    untouched and the conformance contract still holds.

    `sentence` is a classmethod rather than an f-string in the body so a
    subclass can say something else without reaching into `message` after the
    fact — which matters for :class:`CredentialRejected`, whose whole point is
    that the sentence discloses less than the `reason` behind it.
    """

    kind = FailureKind.UNAVAILABLE
    identifier = "identity.unavailable"

    def __init__(self, subject: str, reason: str = "") -> None:
        super().__init__(self.sentence(subject, reason), subject)
        self.reason = reason

    @classmethod
    def sentence(cls, subject: str, reason: str) -> str:
        detail = f": {reason}" if reason else ""
        return f"the identity provider could not resolve {subject}{detail}"


PRESENTED_CREDENTIAL = "the presented credential"
"""What a rejection is *about*. Never the credential, which never prints."""

CREDENTIAL_REFUSED = "the credential presented was not accepted"
"""What a caller is told, whatever was wrong with the credential.

`auth-integration`: the reason *"SHALL be recorded without being disclosed in a
way that distinguishes between a wrong signature and a wrong audience to the
caller"*. So one sentence for every rejection, and the discriminating detail
lives on :attr:`IdentityUnavailable.reason`, where a log line reaches it and a
response body does not.
"""


class CredentialRejected(IdentityUnavailable):
    """The credential was read and is not acceptable — expired, wrong, unsigned.

    Unauthenticated rather than unavailable: nothing is down, and retrying with
    the same credential will fail identically. The caller is told one sentence
    (:data:`CREDENTIAL_REFUSED`); `reason` carries which check failed, for the
    record rather than for the response.
    """

    kind = FailureKind.UNAUTHENTICATED
    identifier = "identity.credential_rejected"

    def __init__(self, reason: str = "", subject: str = PRESENTED_CREDENTIAL) -> None:
        super().__init__(subject, reason)

    @classmethod
    def sentence(cls, subject: str, reason: str) -> str:
        return CREDENTIAL_REFUSED


class IdentityServiceUnavailable(IdentityUnavailable):
    """The identity service could not be reached, and the offline window is spent.

    Named separately because the specified refusal names *it*: beyond the
    bounded period, a request is refused *"with a message naming the identity
    service as unavailable"*, which is a different sentence from "your
    credential is wrong" and leads a person to a different action.
    """

    identifier = "identity.service_unavailable"

    @classmethod
    def sentence(cls, subject: str, reason: str) -> str:
        detail = f": {reason}" if reason else ""
        return f"the identity service is unavailable{detail}"


class IdentityProvider(Protocol):
    """Resolves the credential a process was launched with to an actor."""

    def resolve(self, credential: Credential) -> ResolvedIdentity:
        """The actor this credential belongs to, with its git emails when known.

        Raises :class:`IdentityUnavailable` when the credential cannot be
        resolved. It never returns ``None``: an absent answer is a failure the
        chain degrades past, not a value every call site has to handle.
        """
        ...


__all__ = [
    "CREDENTIAL_REFUSED",
    "PRESENTED_CREDENTIAL",
    "Credential",
    "CredentialRejected",
    "IdentityProvider",
    "IdentityServiceUnavailable",
    "IdentityUnavailable",
    "ResolvedIdentity",
]
