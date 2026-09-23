"""Task 2.2 and 5.5 — the `DocumentPlatform` contract against every implementation.

The fake is seeded with documents; `ArcheDocumentPlatform` is seeded with the
same documents behind a **stub of CyberArche's HTTP API** — real URL shapes, real
status codes, a real bearer header — so the adapter's own mapping is exercised
rather than described. That is the divergence the conformance layer exists to
catch: a fake that answered `FORBIDDEN` where the adapter answered `MISSING`
would make every caller test green and every real refusal wrong.

The stub answers the endpoints this adapter actually calls, and nothing else.
`tests/integration/test_arche_live.py` runs the same adapter against the real
deployment when credentials are present, which is what keeps the stub honest.
"""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path
from typing import Any

from contract import implementation_fixture
from document_platform_contract import (
    BRUNO,
    DELETED,
    FORBIDDEN,
    RAFA,
    READABLE,
    READABLE_BODY,
    READABLE_TITLE,
    WORKSPACE,
    DocumentPlatformContract,
)

from cybercanon.adapters.outbound.arche.config import ArcheSettings
from cybercanon.adapters.outbound.arche.platform import ArcheDocumentPlatform
from cybercanon.application.testing.document_platform import InMemoryDocumentPlatform

ACTORS = {RAFA: "rafa", BRUNO: "bruno"}


def in_memory(directory: Path) -> InMemoryDocumentPlatform:
    """The fake, holding exactly the documents the contract asks about."""
    platform = InMemoryDocumentPlatform()
    for token, actor in ACTORS.items():
        platform.add_actor(token, actor)
    platform.add_document(
        WORKSPACE, READABLE, READABLE_TITLE, body=READABLE_BODY, readers=("rafa",)
    )
    platform.add_revision(WORKSPACE, READABLE, label="before retopo")
    platform.add_document(WORKSPACE, FORBIDDEN, "somebody else's document", readers=("bruno",))
    platform.add_document(WORKSPACE, DELETED, "a document that was deleted", readers=("rafa",))
    platform.delete(WORKSPACE, DELETED)
    platform.permit_creation("rafa", WORKSPACE)
    return platform


# --------------------------------------------------------------------------
# A stub of CyberArche's HTTP API — the shapes the live deployment answers with
# --------------------------------------------------------------------------


class _Answer:
    """One HTTP response, in the two members the transport reads."""

    def __init__(self, status: int, payload: Any) -> None:
        self.status_code = status
        self._payload = payload

    def json(self) -> Any:
        if self._payload is None:
            raise ValueError("no body")
        return self._payload


class StubArche:
    """CyberArche's document endpoints, in memory, honouring the bearer header.

    Written against what the live deployment actually answers, probed rather
    than assumed: `GET /api/v1/documents/{id}` returns the document with a
    `trashed` flag, a deleted one answers 404, a missing bearer answers 401 with
    `{"error": "NotAuthenticated"}`, and `search/content` answers a list of
    `{id, title, field, snippet}`.
    """

    def __init__(self) -> None:
        self.documents: dict[str, dict[str, Any]] = {}
        self.serial = 0
        self.add(READABLE, READABLE_TITLE, body=READABLE_BODY, readers=("rafa",))
        self.add(FORBIDDEN, "somebody else's document", readers=("bruno",))
        self.add(DELETED, "a document that was deleted", readers=("rafa",), trashed=True)

    def add(
        self,
        document_id: str,
        title: str,
        *,
        body: str = "",
        readers: tuple[str, ...] = (),
        trashed: bool = False,
    ) -> None:
        self.documents[document_id] = {
            "id": document_id,
            "workspace_id": WORKSPACE,
            "title": title,
            "trashed": trashed,
            "readers": set(readers),
            "body": body,
            "snapshots": [
                {"id": f"{document_id}_s1", "seq": 1, "created_at": "2026-07-10T13:45:30Z"},
                {
                    "id": f"{document_id}_s2",
                    "seq": 2,
                    "created_at": "2026-07-19T11:39:00Z",
                    "label": "before retopo",
                },
            ],
        }

    # -- the transport's single entry point -----------------------------

    def request(self, method: str, url: str, **keywords: Any) -> _Answer:
        actor = self._actor(keywords.get("headers") or {})
        if actor is None:
            return _Answer(401, {"error": "NotAuthenticated", "detail": "missing bearer token"})
        path = url.split("//", 1)[-1].split("/", 1)[-1]
        if method == "POST":
            return self._create(actor, keywords.get("json") or {})
        return self._read(actor, path, keywords.get("params") or {})

    def _read(self, actor: str, path: str, params: dict[str, Any]) -> _Answer:
        if "/search/content" in path:
            return _Answer(200, self._search(actor, str(params.get("q", ""))))
        parts = path.rstrip("/").split("/")
        document = self.documents.get(parts[3]) if len(parts) > 3 else None
        if document is None or document["trashed"]:
            return _Answer(404, {"error": "NotFound", "detail": "document not found"})
        if actor not in document["readers"]:
            return _Answer(403, {"error": "Forbidden", "detail": "not permitted"})
        if path.endswith("/snapshots"):
            return _Answer(200, document["snapshots"])
        if path.endswith("/blocks"):
            return _Answer(
                200,
                {"blocks": [{"type": "paragraph", "data": {"text": document["body"]}}]},
            )
        visible = ("id", "workspace_id", "title", "trashed")
        return _Answer(200, {key: document[key] for key in visible})

    def _create(self, actor: str, body: dict[str, Any]) -> _Answer:
        if actor != "rafa":
            return _Answer(403, {"error": "Forbidden", "detail": "may not create documents here"})
        self.serial += 1
        document_id = f"made_{self.serial}"
        self.add(document_id, str(body.get("title", "")), readers=(actor,))
        return _Answer(201, dict(self.documents[document_id], readers=None, snapshots=None))

    def _search(self, actor: str, query: str) -> list[dict[str, Any]]:
        return [
            {
                "id": document["id"],
                "title": document["title"],
                "field": "content",
                "snippet": document["body"],
            }
            for document in self.documents.values()
            if not document["trashed"]
            and actor in document["readers"]
            and query.lower() in document["body"].lower()
        ]

    @staticmethod
    def _actor(headers: dict[str, str]) -> str | None:
        token = headers.get("Authorization", "").removeprefix("Bearer ").strip()
        return ACTORS.get(token)


def arche(directory: Path) -> ArcheDocumentPlatform:
    """The real adapter, over a stub of the API it was written against."""
    return ArcheDocumentPlatform(
        settings=ArcheSettings(
            enabled=True,
            base_url="https://arche.invalid",
            default_workspace=WORKSPACE,
            web_url="https://documents.invalid",
            timeout=timedelta(seconds=5),
        ),
        client=StubArche(),
    )


implementation = implementation_fixture(fake=in_memory, arche=arche)


class TestDocumentPlatform(DocumentPlatformContract):
    """The contract, against the fake and against the CyberArche adapter."""
