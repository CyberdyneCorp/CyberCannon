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

from cybercanon.application.errors import OperationFailed
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

    One failure rather than a taxonomy: unreachable, timing out, expired and
    refused all produce the same behaviour in the chain — fall through to the
    cached actor, then to the local one — so splitting them would add names no
    caller branches on. `subject` carries which of them it was, for the message.
    """

    def __init__(self, subject: str, reason: str = "") -> None:
        detail = f": {reason}" if reason else ""
        super().__init__(f"the identity provider could not resolve {subject}{detail}", subject)
        self.reason = reason


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
    "Credential",
    "IdentityProvider",
    "IdentityUnavailable",
    "ResolvedIdentity",
]
