"""The in-memory `DocumentPlatform` — a document platform with no network.

It answers the same questions the real outbound adapter answers, over documents
handed to it rather than fetched, so a unit test and a BDD scenario can say
*"this document exists and Bruno may not read it"* in one line.

Four behaviours are modelled deliberately, because they are the four the
specification makes assertions about and the four a fake is most likely to
quietly get wrong:

* **per-actor permissions** — a credential resolves to an actor, and a document
  a given actor may not read comes back `FORBIDDEN` *with no title and no
  summary*. A fake that returned the title anyway would make D3's cache-keying
  test pass for the wrong reason;
* **deletion** — a deleted document is `MISSING`, which is a different answer
  from being forbidden and from the platform being down;
* **rejection** — the platform refusing a credential outright, and refusing a
  creation in a workspace this person may not write in;
* **delay** — measured against the caller's budget rather than slept through, so
  the time-budget tests take microseconds and are not flaky.

Every call is recorded in :attr:`InMemoryDocumentPlatform.requests`, which is
how the token-forwarding and payload-boundary tests assert what actually went
out rather than what the code appears to send.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta

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
from cybercanon.domain.documents import DocumentRef, DocumentRevision, DocumentState, newest_first

ANONYMOUS = ""
"""What an absent credential resolves to. It is granted nothing, ever."""


@dataclass
class _Document:
    """One document this fake holds, and who may read it."""

    workspace: str
    document_id: str
    title: str
    summary: str = ""
    url: str = ""
    body: str = ""
    trashed: bool = False
    readers: set[str] = field(default_factory=set)
    revisions: list[DocumentRevision] = field(default_factory=list)

    @property
    def key(self) -> tuple[str, str]:
        return (self.workspace, self.document_id)


@dataclass(frozen=True)
class Request:
    """One outbound call, as the platform received it.

    `payload` holds what was sent and nothing the caller merely had available,
    so a test can assert that a delegated search carried the query and the scope
    and *not* a specification.
    """

    operation: str
    token: str
    payload: tuple[tuple[str, str], ...] = ()

    def value(self, name: str) -> str:
        return dict(self.payload).get(name, "")


class InMemoryDocumentPlatform:
    """Documents in a dict, permissions per actor, failures on request."""

    WRITES = ("create",)
    """The only outbound operations that change anything at the platform (D10)."""

    def __init__(self) -> None:
        self._documents: dict[tuple[str, str], _Document] = {}
        self._actors: dict[str, str] = {}
        self._may_create: set[tuple[str, str]] = set()
        self._failure: UnavailabilityReason | None = None
        self._delay = timedelta(0)
        self._serial = 0
        self.requests: list[Request] = []

    # -- seeding ---------------------------------------------------------

    def add_actor(self, token: str, actor: str) -> None:
        """Bind a bearer token to the person it authenticates."""
        self._actors[token] = actor

    def add_document(
        self,
        workspace: str,
        document_id: str,
        title: str,
        *,
        summary: str = "",
        url: str = "",
        body: str = "",
        readers: tuple[str, ...] = (),
    ) -> DocumentRef:
        """A document that exists, readable by the named actors, and its reference."""
        document = _Document(
            workspace=workspace,
            document_id=document_id,
            title=title,
            summary=summary,
            url=url or self.address(workspace, document_id),
            body=body,
            readers=set(readers),
        )
        self._documents[document.key] = document
        self.add_revision(workspace, document_id, label="created")
        return DocumentRef(workspace=workspace, document_id=document_id, url=document.url)

    def add_revision(self, workspace: str, document_id: str, label: str = "") -> DocumentRevision:
        """One more entry in a document's history — the platform's, never ours."""
        document = self._documents[(workspace, document_id)]
        revision = DocumentRevision(
            id=f"snap_{len(document.revisions) + 1}",
            seq=len(document.revisions) + 1,
            created_at=f"2026-09-2{min(len(document.revisions) + 1, 9)}T09:00:00+00:00",
            label=label,
        )
        document.revisions.append(revision)
        return revision

    def permit(self, actor: str, workspace: str, document_id: str) -> None:
        """Grant one actor read access to one document."""
        self._documents[(workspace, document_id)].readers.add(actor)

    def permit_creation(self, actor: str, workspace: str) -> None:
        """Grant one actor the right to create documents in one workspace."""
        self._may_create.add((actor, workspace))

    def rename(self, workspace: str, document_id: str, title: str) -> None:
        """A rename at the source — the event D1 refuses to mirror into the repo."""
        self._documents[(workspace, document_id)].title = title

    def delete(self, workspace: str, document_id: str) -> None:
        """Trash a document. It resolves `MISSING` from now on."""
        self._documents[(workspace, document_id)].trashed = True

    def fail_with(self, reason: UnavailabilityReason | None) -> None:
        """Make every call fail this way, to prove a caller's degradation."""
        self._failure = reason

    def set_delay(self, delay: timedelta) -> None:
        """How long this platform takes to answer, compared against the budget."""
        self._delay = delay

    def address(self, workspace: str, document_id: str) -> str:
        """The address this fake hands out. One shape, so tests can predict it."""
        return f"https://documents.invalid/w/{workspace}/d/{document_id}"

    @property
    def created(self) -> tuple[CreatedDocument, ...]:
        """Every document created through the port, in the order they were made."""
        return tuple(
            CreatedDocument(
                workspace=document.workspace,
                document_id=document.document_id,
                url=document.url,
                title=document.title,
            )
            for document in self._documents.values()
            if document.document_id.startswith("made_")
        )

    def title_of(self, workspace: str, document_id: str) -> str:
        """What the platform currently calls this document. For assertions only."""
        return self._documents[(workspace, document_id)].title

    def exists(self, workspace: str, document_id: str) -> bool:
        document = self._documents.get((workspace, document_id))
        return document is not None and not document.trashed

    # -- port ------------------------------------------------------------

    def resolve(
        self, refs: list[DocumentRef] | tuple[DocumentRef, ...], credential: Credential
    ) -> tuple[ResolvedDocument, ...]:
        actor = self._actor(credential, "resolve", ())
        return tuple(self._resolved(ref, actor) for ref in refs)

    def create(self, workspace: str, title: str, credential: Credential) -> CreatedDocument:
        actor = self._actor(credential, "create", (("workspace", workspace), ("title", title)))
        if (actor, workspace) not in self._may_create:
            raise DocumentCreationRefused(
                workspace, f"{actor or 'this caller'} may not create documents there"
            )
        self._serial += 1
        document_id = f"made_{self._serial}"
        self.add_document(workspace, document_id, title, readers=(actor,))
        return CreatedDocument(
            workspace=workspace,
            document_id=document_id,
            url=self.address(workspace, document_id),
            title=title,
        )

    def search(
        self,
        query: str,
        credential: Credential,
        budget: timedelta = DEFAULT_BUDGET,
        workspace: str = "",
    ) -> tuple[Passage, ...]:
        actor = self._actor(credential, "search", (("query", query), ("workspace", workspace)))
        if self._delay > budget:
            raise PlatformUnavailable(
                UnavailabilityReason.TIMED_OUT, f"no answer within {budget.total_seconds()}s"
            )
        return tuple(
            Passage(
                workspace=document.workspace,
                document_id=document.document_id,
                title=document.title,
                url=document.url,
                text=document.body,
            )
            for document in self._visible(actor, workspace)
            if _retrieves(query, document.body)
        )

    def revisions(self, ref: DocumentRef, credential: Credential) -> tuple[DocumentRevision, ...]:
        actor = self._actor(credential, "revisions", (("document_id", ref.document_id),))
        document = self._documents.get(ref.key)
        if document is None or document.trashed or actor not in document.readers:
            return ()
        return newest_first(document.revisions)

    # -- internals -------------------------------------------------------

    def _actor(
        self, credential: Credential, operation: str, payload: tuple[tuple[str, str], ...]
    ) -> str:
        """Record the call, refuse the whole of it when configured to, name the caller."""
        self.requests.append(Request(operation=operation, token=credential.token, payload=payload))
        if self._failure is not None:
            raise PlatformUnavailable(self._failure, "the fake was configured to fail")
        if not credential.is_present:
            raise PlatformUnavailable(
                UnavailabilityReason.REJECTED, "no end-user credential was forwarded"
            )
        actor = self._actors.get(credential.token)
        if actor is None:
            raise PlatformUnavailable(
                UnavailabilityReason.REJECTED, "that credential is not accepted"
            )
        return actor

    def _resolved(self, ref: DocumentRef, actor: str) -> ResolvedDocument:
        document = self._documents.get(ref.key)
        if document is None or document.trashed:
            return ResolvedDocument(
                workspace=ref.workspace,
                document_id=ref.document_id,
                state=DocumentState.MISSING,
            )
        if actor not in document.readers:
            return ResolvedDocument(
                workspace=ref.workspace,
                document_id=ref.document_id,
                state=DocumentState.FORBIDDEN,
            )
        return ResolvedDocument(
            workspace=ref.workspace,
            document_id=ref.document_id,
            title=document.title,
            summary=document.summary,
            state=DocumentState.READABLE,
        )

    def _visible(self, actor: str, workspace: str) -> tuple[_Document, ...]:
        return tuple(
            document
            for document in self._documents.values()
            if not document.trashed
            and actor in document.readers
            and workspace in ("", document.workspace)
        )


RETRIEVAL_WORD = 4
"""How long a word must be before it counts as a term this fake retrieves on.

Short enough to keep `mech` and `look`, long enough to drop `why`, `the` and
`does`, which is the whole of the modelling: a retrieval service answers a
*question* with passages that share its subject, and a fake that only matched
the question verbatim would make every delegated search in the suite pass or
fail for a reason the real one does not have.
"""


def _retrieves(query: str, body: str) -> bool:
    """Whether this body is an approximate answer to this query.

    Word overlap rather than substring, and *approximate* is the point: the one
    property every caller of this port has to handle is that a semantic answer
    is a guess about prose. A fake that answered exactly would let a test assert
    things about semantic results that are only true of exact ones.
    """
    text = body.lower()
    terms = [word.strip(".,:;?!()").lower() for word in query.split()]
    return any(len(term) >= RETRIEVAL_WORD and term in text for term in terms)


__all__ = ["ANONYMOUS", "RETRIEVAL_WORD", "InMemoryDocumentPlatform", "Request"]
