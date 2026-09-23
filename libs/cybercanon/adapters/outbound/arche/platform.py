"""`DocumentPlatform` over CyberArche's HTTP API — the only place it exists by name.

Everything CyberArche's data model calls things stops here: `workspace_id`,
`/api/v1/documents`, `blocks`, `snapshots`, `search/content`, the bearer header
and every status code. What continues into the application is a
:class:`~cybercanon.domain.documents.DocumentState`, a title, a short summary, a
passage and a revision — which is why
`tests/tooling/test_document_platform_boundary.py` can assert that no domain or
application module mentions this platform at all.

Four operations, and the inventory is the point (D10):

| Operation | Method | Writes? |
|---|---|---|
| resolve a reference | `GET /api/v1/documents/{id}` (+ `/blocks`) | no |
| create a document | `POST /api/v1/documents` | **the only one** |
| search | `GET /api/v1/workspaces/{id}/search/content` | no |
| revisions | `GET /api/v1/documents/{id}/snapshots` | no |

There is **no ingestion path**: nothing here uploads a specification, an
annotation or a compiled briefing, and `WRITES` is a class attribute so a test
can enumerate the outbound operations and assert it.

The version history is CyberArche's. `revisions` lists the snapshots it already
keeps; there is no method here that copies one, stores one, or diffs one —
those live behind the link, in the application that owns them.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any

from cybercanon.adapters.outbound.arche.config import ArcheSettings
from cybercanon.adapters.outbound.arche.transport import ArcheTransport, Response
from cybercanon.application.ports.document_platform import (
    DEFAULT_BUDGET,
    CreatedDocument,
    Credential,
    DocumentCreationRefused,
    Passage,
    PlatformUnavailable,
    ResolvedDocument,
    UnavailabilityReason,
)
from cybercanon.domain.documents import (
    SUMMARY_MAX_CHARS,
    DocumentRef,
    DocumentRevision,
    DocumentState,
    newest_first,
)

DOCUMENTS = "/api/v1/documents"
WORKSPACES = "/api/v1/workspaces"

SEARCH_LIMIT = 10
"""How many passages one delegated call asks for. Bounded, because a fan-out is."""

SUMMARY_BLOCKS = 4
"""How many leading blocks a summary is drawn from — *at most a few lines*."""

TEXT_BLOCK_TYPES = ("paragraph", "header", "quote")
"""Block types whose text reads as prose. Anything else is skipped, not rendered."""

STATE_BY_STATUS: Mapping[int, DocumentState] = {
    403: DocumentState.FORBIDDEN,
    404: DocumentState.MISSING,
    410: DocumentState.MISSING,
}
"""Per-document status mapping. 401 is deliberately absent: see :func:`_state_of`."""

REFUSED_STATUSES = (403,)
"""Statuses that mean *this caller may not*, for a call scoped to a workspace.

A delegated search is scoped to one workspace, and the live platform answers
`403` for a workspace the caller cannot read — which says something about *this
person*, not about the service. Reporting it as `UNREACHABLE` would send
somebody away to wait for a retrieval service that is working perfectly well,
so it is `REJECTED`, which is one of the four reasons the specification requires
a caller to be able to tell apart.
"""


@dataclass
class ArcheDocumentPlatform:
    """CyberArche, asked as whoever is asking (D2).

    **No credential is held here.** The constructor takes an address, a
    workspace and a budget, and every method takes the caller's own
    :class:`~cybercanon.application.ports.document_platform.Credential`. A
    conformance test asserts the absence structurally, because an adapter that
    held a service token would make the permission model decorative while
    looking exactly like this one.
    """

    settings: ArcheSettings
    transport: ArcheTransport = field(init=False)
    client: Any | None = None

    WRITES: tuple[str, ...] = ("create",)
    """Every outbound operation that changes anything at the platform (D10)."""

    def __post_init__(self) -> None:
        self.transport = ArcheTransport(
            base_url=self.settings.api_root,
            timeout=self.settings.timeout,
            client=self.client,
        )

    # -- reads -----------------------------------------------------------

    def resolve(
        self, refs: Sequence[DocumentRef], credential: Credential
    ) -> tuple[ResolvedDocument, ...]:
        """One answer per reference, each carrying its own state.

        A reference that answers 403 comes back `FORBIDDEN` **with no title and
        no summary** — the card type would clear them anyway, and not asking for
        them is the cheaper half of the same rule. A 404 is `MISSING`. Only a
        401, a transport failure or a timeout stops the whole call, because
        those are the three that say nothing about any particular document.
        """
        return tuple(self._resolved(ref, credential) for ref in refs)

    def revisions(self, ref: DocumentRef, credential: Credential) -> tuple[DocumentRevision, ...]:
        """The document's snapshots, newest first — CyberArche's history, read.

        Nothing is stored and nothing is restored from here: a person opens the
        document to move between revisions, in the application that owns them.
        """
        response = self.transport.get(f"{DOCUMENTS}/{ref.document_id}/snapshots", credential)
        if not response.is_ok:
            return ()
        return newest_first(
            DocumentRevision(
                id=str(entry.get("id", "")),
                seq=int(entry.get("seq", 0) or 0),
                created_at=str(entry.get("created_at", "") or ""),
                label=str(entry.get("label", "") or ""),
            )
            for entry in _entries(response.payload)
        )

    def search(
        self,
        query: str,
        credential: Credential,
        budget: timedelta = DEFAULT_BUDGET,
        workspace: str = "",
    ) -> tuple[Passage, ...]:
        """Passages matching a prose query, within this caller's own visibility.

        The request carries **the query text and the routing scope, and nothing
        else** — no specification, no annotation, no compiled briefing, no asset
        identifier the caller happened to have. That is asserted by capturing a
        request rather than by reading this docstring.
        """
        scope = workspace or self.settings.default_workspace
        response = self._within(budget).get(
            f"{WORKSPACES}/{scope}/search/content",
            credential,
            params={"q": query, "limit": SEARCH_LIMIT},
        )
        self._refused_outright(response, scope)
        if response.status in REFUSED_STATUSES:
            raise PlatformUnavailable(
                UnavailabilityReason.REJECTED,
                f"this caller may not search workspace {scope!r}",
                scope,
            )
        if not response.is_ok:
            raise PlatformUnavailable(
                UnavailabilityReason.UNREACHABLE, f"search answered {response.status}"
            )
        return tuple(
            Passage(
                workspace=scope,
                document_id=str(entry.get("id", "")),
                title=str(entry.get("title", "") or ""),
                url=self.settings.address_of(scope, str(entry.get("id", ""))),
                text=str(entry.get("snippet", "") or ""),
            )
            for entry in _entries(response.payload)
            if entry.get("id")
        )

    # -- the one write (D10) ---------------------------------------------

    def create(self, workspace: str, title: str, credential: Credential) -> CreatedDocument:
        """Create one empty, pre-titled document under the caller's own authority.

        Empty: the body is `{workspace_id, title}` and there is no parameter
        here that could carry content. CyberCanon never publishes canon into a
        permission domain it does not own.
        """
        scope = workspace or self.settings.default_workspace
        response = self.transport.post(
            DOCUMENTS, credential, {"workspace_id": scope, "title": title}
        )
        self._refused_outright(response, scope)
        if response.status in (400, 403, 422):
            refusal = _detail(response) or f"it answered {response.status}"
            raise DocumentCreationRefused(scope, refusal)
        if not response.is_ok:
            raise PlatformUnavailable(
                UnavailabilityReason.UNREACHABLE,
                f"creating a document answered {response.status}",
                scope,
            )
        document_id = str(_mapping(response.payload).get("id", ""))
        if not document_id:
            raise PlatformUnavailable(
                UnavailabilityReason.MALFORMED, "the created document had no identifier", scope
            )
        return CreatedDocument(
            workspace=scope,
            document_id=document_id,
            url=self.settings.address_of(scope, document_id),
            title=title,
        )

    # -- internals -------------------------------------------------------

    def _resolved(self, ref: DocumentRef, credential: Credential) -> ResolvedDocument:
        response = self.transport.get(f"{DOCUMENTS}/{ref.document_id}", credential)
        self._refused_outright(response, ref.document_id)
        state = _state_of(response)
        if state is not DocumentState.READABLE:
            return ResolvedDocument(
                workspace=ref.workspace, document_id=ref.document_id, state=state
            )
        document = _mapping(response.payload)
        if document.get("trashed"):
            return ResolvedDocument(
                workspace=ref.workspace,
                document_id=ref.document_id,
                state=DocumentState.MISSING,
            )
        return ResolvedDocument(
            workspace=ref.workspace,
            document_id=ref.document_id,
            title=str(document.get("title", "") or ""),
            summary=self._summary(ref, credential),
            state=DocumentState.READABLE,
        )

    def _summary(self, ref: DocumentRef, credential: Credential) -> str:
        """A few lines of the document's leading prose, for display only.

        Best effort by design: a document whose blocks cannot be read still
        resolves with its title, because a missing summary is a smaller failure
        than a link that will not resolve. Nothing drawn from here is ever
        written anywhere durable — it reaches a
        :class:`~cybercanon.domain.documents.DocumentCard` and stops.
        """
        try:
            response = self.transport.get(f"{DOCUMENTS}/{ref.document_id}/blocks", credential)
        except PlatformUnavailable:
            return ""
        if not response.is_ok:
            return ""
        blocks = _mapping(response.payload).get("blocks") or []
        texts = [
            text
            for block in blocks
            if isinstance(block, Mapping) and block.get("type") in TEXT_BLOCK_TYPES
            if (text := str(_mapping(block.get("data")).get("text", "") or "").strip())
        ]
        return " ".join(texts[:SUMMARY_BLOCKS])[:SUMMARY_MAX_CHARS]

    def _within(self, budget: timedelta) -> ArcheTransport:
        """The transport, bounded by whichever is tighter — the budget or the setting."""
        if budget >= self.settings.timeout:
            return self.transport
        return ArcheTransport(base_url=self.settings.api_root, timeout=budget, client=self.client)

    @staticmethod
    def _refused_outright(response: Response, subject: str) -> None:
        """A 401 is about the *credential*, so it stops the call rather than one link."""
        if response.status == 401:
            raise PlatformUnavailable(
                UnavailabilityReason.REJECTED,
                "the document platform did not accept the caller's credential",
                subject,
            )


def _state_of(response: Response) -> DocumentState:
    """Which state one document's status line means.

    A 5xx is `UNREACHABLE` for that document alone: the platform is having a bad
    time, and the other links in the same list may well answer.
    """
    if response.is_ok:
        return DocumentState.READABLE
    return STATE_BY_STATUS.get(response.status, DocumentState.UNREACHABLE)


def _entries(payload: Any) -> tuple[Mapping[str, Any], ...]:
    """A list payload as mappings, tolerating the shapes a list can arrive in."""
    if isinstance(payload, Mapping):
        payload = payload.get("items") or payload.get("results") or ()
    if not isinstance(payload, Sequence) or isinstance(payload, str | bytes):
        return ()
    return tuple(entry for entry in payload if isinstance(entry, Mapping))


def _mapping(payload: Any) -> Mapping[str, Any]:
    return payload if isinstance(payload, Mapping) else {}


def _detail(response: Response) -> str:
    return str(_mapping(response.payload).get("detail", "") or "")


__all__ = [
    "DOCUMENTS",
    "REFUSED_STATUSES",
    "SEARCH_LIMIT",
    "STATE_BY_STATUS",
    "SUMMARY_BLOCKS",
    "WORKSPACES",
    "ArcheDocumentPlatform",
]
