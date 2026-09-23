"""The CyberArche adapter against the **real deployment** — opt-in, never required.

A conformance suite over a stub proves the adapter is self-consistent. It cannot
prove the stub is right, and the shapes a hosted API actually answers with are
exactly the thing nobody can check by reading a client. So this suite runs the
same adapter against the live instance, and everything it asserts was probed
before it was written.

**It is opt-in and skips cleanly.** The environment file lives outside the
repository, and with it absent `just check` behaves identically on a machine
that has never heard of CyberArche — which is the same rule the rest of this
integration follows: absent configuration is a feature being off, never a broken
build. No credential is read from, written to, or defaulted inside this
repository.

Set the five variables (or `source` a file that does) and the suite runs:

    CANON_ARCHE_BASE_URL   the API root
    CANON_ARCHE_WORKSPACE  a workspace this account can read and write
    CANON_ARCHE_EMAIL      an account
    CANON_ARCHE_PASSWORD   its password
    CANON_ARCHE_WEB_URL    (optional) where a document is opened

What it checks is the half a stub cannot: that the session endpoint really
returns a bearer token, that `GET /api/v1/documents/{id}` really carries a title
and a `trashed` flag, that a deleted document really answers 404, that
`/snapshots` really returns the version history this integration *links to*
rather than copies, and that the one write really creates an empty pre-titled
document. Anything this suite creates, it deletes.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from datetime import timedelta
from typing import Any

import pytest

from cybercanon.adapters.outbound.arche.config import ArcheSettings
from cybercanon.adapters.outbound.arche.platform import DOCUMENTS, ArcheDocumentPlatform
from cybercanon.application.ports.document_platform import (
    NO_CREDENTIAL,
    Credential,
    PlatformUnavailable,
    UnavailabilityReason,
)
from cybercanon.domain.documents import DocumentRef, DocumentState

pytestmark = pytest.mark.integration

BASE_URL = "CANON_ARCHE_BASE_URL"
WORKSPACE = "CANON_ARCHE_WORKSPACE"
EMAIL = "CANON_ARCHE_EMAIL"
PASSWORD = "CANON_ARCHE_PASSWORD"
WEB_URL = "CANON_ARCHE_WEB_URL"

REQUIRED = (BASE_URL, WORKSPACE, EMAIL, PASSWORD)

SESSION = "/api/v1/auth/session"

TITLE = "cybercanon integration probe — safe to delete"
"""What this suite calls the documents it creates, so a stray one is obvious."""


def _configured() -> dict[str, str]:
    return {name: os.environ.get(name, "").strip() for name in (*REQUIRED, WEB_URL)}


def _skip_unless_configured() -> dict[str, str]:
    values = _configured()
    missing = [name for name in REQUIRED if not values[name]]
    if missing:
        pytest.skip(
            "no CyberArche credentials in the environment "
            f"({', '.join(missing)} unset); this suite is opt-in"
        )
    return values


@pytest.fixture(scope="module")
def configuration() -> dict[str, str]:
    return _skip_unless_configured()


@pytest.fixture(scope="module")
def settings(configuration: dict[str, str]) -> ArcheSettings:
    return ArcheSettings(
        enabled=True,
        base_url=configuration[BASE_URL],
        default_workspace=configuration[WORKSPACE],
        web_url=configuration[WEB_URL],
        timeout=timedelta(seconds=20),
    )


@pytest.fixture(scope="module")
def credential(configuration: dict[str, str], settings: ArcheSettings) -> Credential:
    """A real bearer token, obtained the way a person's session obtains one.

    The token is never written anywhere: it lives in this fixture for the
    duration of the run and reaches the adapter only as a call argument (D2).
    """
    import httpx

    response = httpx.post(
        f"{settings.api_root}{SESSION}",
        json={"email": configuration[EMAIL], "password": configuration[PASSWORD]},
        timeout=30.0,
    )
    if response.status_code >= 400:
        pytest.skip(f"the document platform would not open a session ({response.status_code})")
    token = str(response.json().get("access_token", ""))
    assert token, "the session endpoint answered without an access token"
    return Credential(token)


@pytest.fixture
def platform(settings: ArcheSettings) -> ArcheDocumentPlatform:
    return ArcheDocumentPlatform(settings=settings)


@pytest.fixture
def a_document(
    platform: ArcheDocumentPlatform, credential: Credential, settings: ArcheSettings
) -> Iterator[DocumentRef]:
    """One document created for this test and deleted afterwards, always."""
    created = platform.create(settings.default_workspace, TITLE, credential)
    ref = DocumentRef(workspace=created.workspace, document_id=created.document_id, url=created.url)
    try:
        yield ref
    finally:
        _delete(settings, ref, credential)


def _delete(settings: ArcheSettings, ref: DocumentRef, credential: Credential) -> Any:
    import httpx

    return httpx.delete(
        f"{settings.api_root}{DOCUMENTS}/{ref.document_id}",
        headers={"Authorization": f"Bearer {credential.token}"},
        timeout=30.0,
    )


# --------------------------------------------------------------------------
# Resolution against the live workspace
# --------------------------------------------------------------------------


def test_a_real_document_resolves_to_its_current_title(
    platform: ArcheDocumentPlatform, credential: Credential, a_document: DocumentRef
) -> None:
    answer = platform.resolve((a_document,), credential)[0]

    assert answer.state is DocumentState.READABLE
    assert answer.title == TITLE
    assert answer.workspace == a_document.workspace


def test_an_identifier_no_document_carries_resolves_as_missing(
    platform: ArcheDocumentPlatform, credential: Credential, settings: ArcheSettings
) -> None:
    absent = DocumentRef(
        workspace=settings.default_workspace,
        document_id="00000000000000000000000000000000",
        url=settings.address_of(settings.default_workspace, "0" * 32),
    )

    answer = platform.resolve((absent,), credential)[0]

    assert answer.state is DocumentState.MISSING
    assert answer.title == ""


def test_a_deleted_document_becomes_missing_rather_than_unreachable(
    platform: ArcheDocumentPlatform,
    credential: Credential,
    settings: ArcheSettings,
) -> None:
    created = platform.create(settings.default_workspace, TITLE, credential)
    ref = DocumentRef(workspace=created.workspace, document_id=created.document_id, url=created.url)
    assert platform.resolve((ref,), credential)[0].state is DocumentState.READABLE

    _delete(settings, ref, credential)

    assert platform.resolve((ref,), credential)[0].state is DocumentState.MISSING


def test_resolving_several_references_answers_one_per_reference_in_order(
    platform: ArcheDocumentPlatform,
    credential: Credential,
    settings: ArcheSettings,
    a_document: DocumentRef,
) -> None:
    absent = DocumentRef(
        workspace=settings.default_workspace,
        document_id="0" * 32,
        url=settings.address_of(settings.default_workspace, "0" * 32),
    )

    answers = platform.resolve((a_document, absent), credential)

    assert [answer.document_id for answer in answers] == [
        a_document.document_id,
        absent.document_id,
    ]
    assert answers[0].state is DocumentState.READABLE
    assert answers[1].state is DocumentState.MISSING


# --------------------------------------------------------------------------
# The credential is the caller's, and an absent one is refused
# --------------------------------------------------------------------------


def test_with_no_forwarded_credential_the_platform_refuses_the_whole_call(
    platform: ArcheDocumentPlatform, a_document: DocumentRef
) -> None:
    """D2 against the real service: no token, no answer — and no service token."""
    with pytest.raises(PlatformUnavailable) as refusal:
        platform.resolve((a_document,), NO_CREDENTIAL)

    assert refusal.value.reason is UnavailabilityReason.REJECTED


def test_a_credential_the_platform_does_not_accept_is_rejected(
    platform: ArcheDocumentPlatform, a_document: DocumentRef
) -> None:
    with pytest.raises(PlatformUnavailable) as refusal:
        platform.resolve((a_document,), Credential("not-a-real-token"))

    assert refusal.value.reason is UnavailabilityReason.REJECTED


# --------------------------------------------------------------------------
# The one write (D10), and the version history this integration links to
# --------------------------------------------------------------------------


def test_creating_a_document_makes_an_empty_pre_titled_one(
    platform: ArcheDocumentPlatform, credential: Credential, a_document: DocumentRef
) -> None:
    answer = platform.resolve((a_document,), credential)[0]

    assert answer.title == TITLE
    assert answer.summary == "", "a document created from CyberCanon starts empty"


def test_the_version_history_is_the_platform_s_own_and_is_only_read(
    platform: ArcheDocumentPlatform, credential: Credential, settings: ArcheSettings
) -> None:
    """The requirement `versioned GDD` is met by linking to a real history.

    A freshly created document may have no snapshots yet, which is itself the
    answer: the history belongs to CyberArche, and CyberCanon reports what is
    there rather than creating one.
    """
    documents = _listed(settings, credential)
    if not documents:
        pytest.skip("the workspace holds no documents to read a history from")
    ref = DocumentRef(
        workspace=settings.default_workspace,
        document_id=str(documents[0]["id"]),
        url=settings.address_of(settings.default_workspace, str(documents[0]["id"])),
    )

    revisions = platform.revisions(ref, credential)

    assert [revision.seq for revision in revisions] == sorted(
        (revision.seq for revision in revisions), reverse=True
    )
    assert all(revision.id for revision in revisions)


def test_search_answers_within_the_caller_s_own_visibility(
    platform: ArcheDocumentPlatform, credential: Credential, settings: ArcheSettings
) -> None:
    """A prose query, the workspace scope, and nothing else on the wire."""
    passages = platform.search(
        "equations", credential, timedelta(seconds=20), settings.default_workspace
    )

    assert all(passage.document_id for passage in passages)
    assert all(passage.url.startswith("http") for passage in passages)
    assert all(passage.workspace == settings.default_workspace for passage in passages)


def _listed(settings: ArcheSettings, credential: Credential) -> list[dict[str, Any]]:
    import httpx

    response = httpx.get(
        f"{settings.api_root}{DOCUMENTS}",
        params={"workspace_id": settings.default_workspace},
        headers={"Authorization": f"Bearer {credential.token}"},
        timeout=30.0,
    )
    payload = response.json() if response.status_code < 400 else []
    return [entry for entry in payload if isinstance(entry, dict)]


# --------------------------------------------------------------------------
# Delegation, end to end, against the live deployment (group 4)
# --------------------------------------------------------------------------
#
# The tests above drive the adapter. These drive the **use case** — the routing
# gate, the fan-out ordering, the budget and the two groups — with the real
# index underneath for the local half and the real CyberArche for the other.
# What they can prove that a fake cannot is that the endpoint chosen for
# delegation really answers with passages, that a workspace this account cannot
# read really comes back as *rejected* rather than as an outage, and that an
# identifier query really puts nothing on the wire.


class _Watching:
    """`httpx` with a notebook: every request this adapter actually made."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def request(self, method: str, url: str, **keywords: Any):
        import httpx

        self.calls.append({"method": method, "url": url, **keywords})
        return httpx.request(method, url, **keywords)

    @property
    def everything_sent(self) -> str:
        return repr(self.calls)


@pytest.fixture
def watched(settings: ArcheSettings) -> tuple[ArcheDocumentPlatform, _Watching]:
    watching = _Watching()
    return ArcheDocumentPlatform(settings=settings, client=watching), watching


def _delegating_index() -> Any:
    """A real index holding one asset, so the local half has something to answer."""
    from cybercanon.application.ports.search_index import IndexedAsset
    from cybercanon.application.testing.search_index import InMemorySearchIndex

    index = InMemorySearchIndex()
    index.upsert(
        IndexedAsset(
            asset_id="mech_scout",
            name="Scout Mech",
            project=LIVE_PROJECT,
            aliases=("scout",),
            spec_path="characters/mech_scout/asset.yaml",
        )
    )
    return index


LIVE_PROJECT = "cyberdyne-game"

LIVE_PROSE = "derivative of a function"
"""A prose query about what the live workspace actually contains.

Probed rather than assumed, and the probe is the finding: CyberArche's
`/search/content` is a **phrase** index over block content, so it answers this
and answers `[]` to *"what do the notes say about limits and derivatives"*. The
delegation forwards the query verbatim — rewriting it would be the retrieval
tuning `design.md` rules out as a non-goal — so what a person gets back is
whatever that index holds for what they typed, and a question it cannot answer
becomes an empty approximate group plus a locally recorded miss, which is D7's
own feedback channel.
"""

LIVE_QUESTION = "what do the notes say about limits and derivatives"
"""A full-sentence question the live phrase index answers nothing for."""


def test_a_prose_question_reaches_the_live_retrieval_and_comes_back_as_passages(
    watched: tuple[ArcheDocumentPlatform, _Watching],
    credential: Credential,
    settings: ArcheSettings,
) -> None:
    from cybercanon.application.testing.outcomes import ran
    from cybercanon.application.use_cases.search_delegation import search_assets_and_docs

    platform, watching = watched
    answer = ran(
        search_assets_and_docs(
            LIVE_PROSE,
            search_index=_delegating_index(),
            platform=platform,
            credential=credential,
            project=LIVE_PROJECT,
            budget=timedelta(seconds=20),
            workspace=settings.default_workspace,
        )
    )

    assert answer.exact == (), "the question must not resolve locally, or nothing delegates"
    assert answer.was_delegated
    assert answer.semantic.is_available
    assert answer.semantic.results, "the live workspace answered nothing for a phrase it holds"
    assert all(found.source for found in answer.semantic.results)
    assert all(found.is_openable for found in answer.semantic.results)
    assert all(found.workspace == settings.default_workspace for found in answer.semantic.results)
    assert [call["method"] for call in watching.calls] == ["GET"]


def test_a_question_the_live_index_cannot_answer_degrades_to_an_empty_group(
    watched: tuple[ArcheDocumentPlatform, _Watching],
    credential: Credential,
    settings: ArcheSettings,
) -> None:
    """The honest shape of *"any passages it returns"* when it returns none.

    The delegated call succeeded, the approximate group is empty and available,
    the local half answered, and the query is recorded as a miss where somebody
    can read it. Nothing here is a failure, and nothing pretends the question
    was answered.
    """
    from cybercanon.application.testing.outcomes import ran
    from cybercanon.application.use_cases.search_delegation import search_assets_and_docs

    platform, watching = watched
    index = _delegating_index()
    answer = ran(
        search_assets_and_docs(
            LIVE_QUESTION,
            search_index=index,
            platform=platform,
            credential=credential,
            project=LIVE_PROJECT,
            budget=timedelta(seconds=20),
            workspace=settings.default_workspace,
        )
    )

    assert answer.was_delegated
    assert answer.semantic.is_available
    assert answer.semantic.results == ()
    assert answer.recorded_as_miss
    assert [miss.term for miss in index.misses(LIVE_PROJECT)] == [LIVE_QUESTION]
    assert len(watching.calls) == 1


def test_an_identifier_query_puts_nothing_on_the_wire(
    watched: tuple[ArcheDocumentPlatform, _Watching], credential: Credential
) -> None:
    from cybercanon.application.testing.outcomes import ran
    from cybercanon.application.use_cases.search_delegation import search_assets_and_docs

    platform, watching = watched
    answer = ran(
        search_assets_and_docs(
            "mech_scout",
            search_index=_delegating_index(),
            platform=platform,
            credential=credential,
            project=LIVE_PROJECT,
        )
    )

    assert answer.asset_ids == ("mech_scout",)
    assert watching.calls == []


def test_the_delegated_request_carries_the_query_and_the_scope_and_no_canon(
    watched: tuple[ArcheDocumentPlatform, _Watching],
    credential: Credential,
    settings: ArcheSettings,
) -> None:
    platform, watching = watched
    platform.search(LIVE_PROSE, credential, timedelta(seconds=20), settings.default_workspace)
    sent = watching.calls[-1]

    assert sent["params"] == {"q": LIVE_PROSE, "limit": 10}
    assert sent["json"] is None
    assert settings.default_workspace in sent["url"]
    assert SPEC_CONTENT not in watching.everything_sent


SPEC_CONTENT = "tri_budget"
"""One word that only appears in repository content. It must never go out."""


def test_a_workspace_this_account_cannot_read_is_rejected_not_unreachable(
    platform: ArcheDocumentPlatform, credential: Credential
) -> None:
    """A different sentence from *the service is down*, and the difference matters.

    Probed against the live deployment: a workspace identifier this account has
    no membership in answers `403`, which says something about *this person*
    rather than about the platform. Reporting it as an outage would send
    somebody away to wait for a retrieval service that is working perfectly
    well.
    """
    with pytest.raises(PlatformUnavailable) as raised:
        platform.search("anything", credential, timedelta(seconds=20), "0" * 32)

    assert raised.value.reason is UnavailabilityReason.REJECTED


def test_the_live_endpoint_chosen_for_delegation_is_the_one_that_returns_passages(
    settings: ArcheSettings, credential: Credential
) -> None:
    """Why `/search/content` and not `/search` — asserted, not asserted-in-a-comment.

    `/search` is a *title* index: it answers with documents and no snippet, so
    it would duplicate the local exact lookup and carry nothing a person could
    read. `/search/content` answers with the passage and the field it matched,
    which is exactly what a `Passage` is. This runs both against the live
    workspace and asserts the difference is real rather than remembered.
    """
    import httpx

    headers = {"Authorization": f"Bearer {credential.token}"}
    root = f"{settings.api_root}/api/v1/workspaces/{settings.default_workspace}"
    titles = httpx.get(
        f"{root}/search", params={"q": "limit"}, headers=headers, timeout=30.0
    ).json()
    contents = httpx.get(
        f"{root}/search/content", params={"q": "limit"}, headers=headers, timeout=30.0
    ).json()

    assert titles and contents
    assert all("snippet" not in entry for entry in titles)
    assert all(entry["field"] and entry["id"] and entry["title"] for entry in contents)
    assert any(entry["field"] == "content" and entry["snippet"] for entry in contents), (
        "the endpoint chosen for delegation must return the passage, not just the document"
    )
