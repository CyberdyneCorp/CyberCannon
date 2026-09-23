"""The `DocumentPlatform` port — asking a document platform, as the asker (D2).

CyberCanon links to long-form documents it does not host. This is the whole of
its dependency on the platform that does, and three properties of the signature
below are the decisions rather than the mechanics.

* **The credential is a parameter on every method, never construction state**
  (D2). The specification forbids a service credential standing in as end-user
  authority, and a token held by the adapter would make every call silently run
  as the service — the permission model decorative, and the leak one mis-set
  header wide. As a parameter there is no call anybody can write without
  deciding whose authority it carries, which is why
  `tests/conformance/document_platform_contract.py` asserts the *absence* of
  such state structurally rather than trusting a review to notice it.
* **There is no method that returns a document's body** (D9). Titles, short
  summaries, search passages and revision metadata, and nothing else. *"The
  design block is never generated from the document"* is enforced by nothing if
  the body is reachable — somebody eventually adds a helpful "pre-fill from
  doc" button — so the temptation is made unimplementable without a port change
  that shows up in review.
* **The only write is creating an empty pre-titled document** (D10). Nothing is
  ever pushed: no specification, no annotation, no compiled briefing. CyberCanon
  does not control workspace membership, so anything it published would be
  governed by permissions it cannot see.

Absence is a *null adapter chosen at composition*, not a flag read at call sites
(D4): :class:`NullDocumentPlatform` answers every method with
:class:`PlatformUnavailable` carrying :attr:`UnavailabilityReason.UNCONFIGURED`,
so a use case never branches on configuration and "degrades to absent" is one
wiring decision that is tested once.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import timedelta
from enum import Enum
from typing import Protocol

from cybercanon.application.errors import FailureKind, OperationFailed
from cybercanon.domain.documents import DocumentRef, DocumentRevision, DocumentState

DEFAULT_BUDGET = timedelta(seconds=5)
"""How long a delegated call may take before the answer is *not this time* (D5)."""


@dataclass(frozen=True)
class Credential:
    """The caller's own bearer token, carried as an argument and never stored.

    A value object rather than a bare `str` so that *"whose authority is this"*
    is a type in every signature, and so that a token can never be confused with
    a workspace, a query or a title at a call site.
    """

    token: str = ""

    @property
    def is_present(self) -> bool:
        """Whether there is an end-user credential to forward at all."""
        return bool(self.token)

    def __repr__(self) -> str:
        """Never the token. A credential in a traceback is a credential in a log."""
        return f"Credential(present={self.is_present})"


NO_CREDENTIAL = Credential()
"""What an unauthenticated caller carries: nothing, and it says so."""


class UnavailabilityReason(Enum):
    """Why the platform did not answer — five, and each means something different.

    A caller renders the distinction, so the set is closed and every transport
    outcome maps onto exactly one member: an unconfigured deployment is not an
    outage, a refused credential is not a timeout, and a platform answering
    nonsense is not a platform that is down.
    """

    UNCONFIGURED = "unconfigured"
    UNREACHABLE = "unreachable"
    REJECTED = "rejected"
    TIMED_OUT = "timed_out"
    MALFORMED = "malformed"

    @classmethod
    def values(cls) -> tuple[str, ...]:
        return tuple(member.value for member in cls)

    @property
    def state(self) -> DocumentState:
        """The per-link state a whole-call failure leaves every reference in.

        `REJECTED` is the one that is not `UNREACHABLE`: a platform that refused
        the caller's credential has told us something about *this viewer*, and
        showing that as a temporary outage would send a person away to wait for
        a service that is working fine.
        """
        if self is UnavailabilityReason.REJECTED:
            return DocumentState.FORBIDDEN
        return DocumentState.UNREACHABLE

    def __str__(self) -> str:
        return self.value


class PlatformUnavailable(OperationFailed):
    """The document platform did not answer, and this is which way it did not.

    *Unavailable* rather than invalid: nothing the person asked for is wrong,
    and every caller's correct behaviour is to carry on with what it already has
    and say that the document half is missing.
    """

    kind = FailureKind.UNAVAILABLE
    identifier = "document_platform.unavailable"

    def __init__(self, reason: UnavailabilityReason, detail: str = "", subject: str = "") -> None:
        suffix = f": {detail}" if detail else ""
        super().__init__(f"the document platform is {reason}{suffix}", subject)
        self.reason = reason
        self.detail = detail


class DocumentCreationRefused(OperationFailed):
    """The platform refused to create the document, and said why.

    A distinct failure from :class:`PlatformUnavailable` because the person's
    next step is different: the platform is working, and this account may not
    write in that workspace.
    """

    kind = FailureKind.FORBIDDEN
    identifier = "document.creation_refused"

    def __init__(self, workspace: str, reason: str) -> None:
        super().__init__(
            f"the document platform refused to create a document in workspace "
            f"{workspace!r}: {reason}",
            workspace,
        )
        self.reason = reason


@dataclass(frozen=True)
class ResolvedDocument:
    """One reference as the platform answered for it, for display only.

    Carries its *own* state, because resolving three links is three independent
    answers: *"one broken link does not break the list"* is a property of this
    shape before it is a property of any caller.
    """

    workspace: str
    document_id: str
    title: str = ""
    summary: str = ""
    state: DocumentState = DocumentState.READABLE

    @property
    def key(self) -> tuple[str, str]:
        return (self.workspace, self.document_id)


@dataclass(frozen=True)
class CreatedDocument:
    """A document that now exists at the platform, and where to find it.

    `url` is the whole reason this is a value object: D8 accepts orphan
    documents as the price of never writing a dangling reference, and an orphan
    is only harmless if the failure that produced it can name its address.
    """

    workspace: str
    document_id: str
    url: str
    title: str = ""


@dataclass(frozen=True)
class Passage:
    """One approximate hit: some text, and the document it came from.

    Nothing structural about retrieval crosses this boundary — no score, no
    rank, no chunk index, no embedding. If the platform's retrieval changes
    shape, one adapter changes; and there is no number here that anybody could
    accidentally compare with an exact result (D6).
    """

    workspace: str
    document_id: str
    title: str
    url: str
    text: str = ""


class DocumentPlatform(Protocol):
    """Resolves references, creates one empty document, searches, lists history."""

    def resolve(
        self, refs: Sequence[DocumentRef], credential: Credential
    ) -> tuple[ResolvedDocument, ...]:
        """What these references currently are, asked with the viewer's authority.

        One answer per reference, in the order they were given, each carrying
        its own :class:`~cybercanon.domain.documents.DocumentState`. A reference
        the viewer may not see comes back `FORBIDDEN` with no title and no
        summary; one that no longer exists comes back `MISSING`.

        Raises :class:`PlatformUnavailable` only when *no* reference could be
        asked about — the platform being down, unconfigured or refusing the
        credential outright.
        """
        ...

    def create(self, workspace: str, title: str, credential: Credential) -> CreatedDocument:
        """Create one empty, pre-titled document under the caller's own authority.

        The only write this port has (D10). Raises
        :class:`DocumentCreationRefused` when the platform says this person may
        not, and :class:`PlatformUnavailable` when it does not answer.
        """
        ...

    def search(
        self,
        query: str,
        credential: Credential,
        budget: timedelta = DEFAULT_BUDGET,
        workspace: str = "",
    ) -> tuple[Passage, ...]:
        """Passages matching a prose query, within the caller's own visibility.

        The request carries the query text and the routing scope and nothing
        else: no specification, no annotation, no compiled briefing.
        """
        ...

    def revisions(self, ref: DocumentRef, credential: Credential) -> tuple[DocumentRevision, ...]:
        """The document's own version history, newest first — a read, never a copy.

        The platform owns the history, so this lists what it holds and stores
        none of it. There is deliberately no method to restore, diff or fetch a
        revision's content here: those are the platform's, reached by opening
        the document.
        """
        ...


class NullDocumentPlatform:
    """The platform when there is none: every method unavailable, unconfigured (D4).

    Wired by the composition root whenever configuration is absent or
    incomplete, so nothing downstream ever asks *"is the platform configured"*.
    One class whose body is trivial, against fifteen scattered checks, fourteen
    of which would be right.
    """

    def resolve(
        self, refs: Sequence[DocumentRef], credential: Credential
    ) -> tuple[ResolvedDocument, ...]:
        raise self._unavailable()

    def create(self, workspace: str, title: str, credential: Credential) -> CreatedDocument:
        raise self._unavailable(workspace)

    def search(
        self,
        query: str,
        credential: Credential,
        budget: timedelta = DEFAULT_BUDGET,
        workspace: str = "",
    ) -> tuple[Passage, ...]:
        raise self._unavailable()

    def revisions(self, ref: DocumentRef, credential: Credential) -> tuple[DocumentRevision, ...]:
        raise self._unavailable(ref.document_id)

    @staticmethod
    def _unavailable(subject: str = "") -> PlatformUnavailable:
        return PlatformUnavailable(
            UnavailabilityReason.UNCONFIGURED,
            "no document platform is configured for this deployment",
            subject,
        )


__all__ = [
    "DEFAULT_BUDGET",
    "NO_CREDENTIAL",
    "CreatedDocument",
    "Credential",
    "DocumentCreationRefused",
    "DocumentPlatform",
    "NullDocumentPlatform",
    "Passage",
    "PlatformUnavailable",
    "ResolvedDocument",
    "UnavailabilityReason",
]
