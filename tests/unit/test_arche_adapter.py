"""Group 5 — the CyberArche adapter: whose token, what is sent, what is written.

Everything here runs against a **recording client**: the adapter's own transport
with a stand-in for `httpx`, so what is asserted is the request that actually
went out — its header, its query, its body — rather than the code that appears
to build one. The status mapping is asserted the same way, one status line at a
time, because *"401/403, 404, connection failure, timeout and malformed body"*
is a list of five different sentences to the person looking at the link.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

import pytest

from cybercanon.adapters.outbound.arche.config import (
    BASE_URL,
    DEFAULT_TIMEOUT,
    DEFAULT_WORKSPACE,
    ENABLED,
    ArcheSettings,
    settings_from,
)
from cybercanon.adapters.outbound.arche.platform import ArcheDocumentPlatform
from cybercanon.adapters.wiring.build import document_platform
from cybercanon.application.ports.document_platform import (
    NO_CREDENTIAL,
    Credential,
    DocumentCreationRefused,
    NullDocumentPlatform,
    PlatformUnavailable,
    UnavailabilityReason,
)
from cybercanon.domain.documents import DocumentRef, DocumentState

pytestmark = pytest.mark.unit

WORKSPACE = "w_production"
DOCUMENT = "d_rationale"
RAFA = Credential("token-rafa")

SPEC_TEXT = "tri_budget: 12000"
COMPILED = "# mech_scout — Scout Mech"


def a_ref(document_id: str = DOCUMENT) -> DocumentRef:
    return DocumentRef(
        workspace=WORKSPACE,
        document_id=document_id,
        url=f"https://documents.invalid/w/{WORKSPACE}/d/{document_id}",
    )


class _Answer:
    def __init__(self, status: int, payload: Any) -> None:
        self.status_code = status
        self._payload = payload

    def json(self) -> Any:
        if isinstance(self._payload, Exception):
            raise self._payload
        return self._payload


class Recorder:
    """Records every outbound call and answers with whatever a test queued."""

    def __init__(self, answers: list[tuple[int, Any]] | None = None) -> None:
        self.answers = list(answers or [])
        self.calls: list[dict[str, Any]] = []
        self.raise_with: Exception | None = None

    def request(self, method: str, url: str, **keywords: Any) -> _Answer:
        self.calls.append({"method": method, "url": url, **keywords})
        if self.raise_with is not None:
            raise self.raise_with
        status, payload = self.answers.pop(0) if self.answers else (200, {})
        return _Answer(status, payload)

    @property
    def last(self) -> dict[str, Any]:
        return self.calls[-1]

    @property
    def everything_sent(self) -> str:
        """Every byte this adapter put on the wire, as one string to search."""
        return repr(self.calls)


def a_platform(recorder: Recorder) -> ArcheDocumentPlatform:
    return ArcheDocumentPlatform(
        settings=ArcheSettings(
            enabled=True,
            base_url="https://arche.invalid",
            default_workspace=WORKSPACE,
            web_url="https://documents.invalid",
            timeout=timedelta(seconds=5),
        ),
        client=recorder,
    )


# --------------------------------------------------------------------------
# 5.1 — configuration selects the adapter, and its absence selects the null one
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "environment",
    [
        {},
        {ENABLED: "false", BASE_URL: "https://arche.invalid", DEFAULT_WORKSPACE: WORKSPACE},
        {ENABLED: "true"},
        {ENABLED: "true", BASE_URL: "https://arche.invalid"},
        {ENABLED: "true", DEFAULT_WORKSPACE: WORKSPACE},
    ],
)
def test_absent_or_incomplete_configuration_selects_the_null_adapter(
    environment: dict[str, str],
) -> None:
    """D4: half a configuration is the absence it is, not a broken deployment."""
    assert isinstance(document_platform(environment), NullDocumentPlatform)


def test_complete_configuration_selects_cyberarche() -> None:
    platform = document_platform(
        {ENABLED: "true", BASE_URL: "https://arche.invalid", DEFAULT_WORKSPACE: WORKSPACE}
    )

    assert isinstance(platform, ArcheDocumentPlatform)


def test_the_settings_name_what_a_half_configured_deployment_still_owes() -> None:
    assert settings_from({}).missing == (ENABLED,)
    assert settings_from({ENABLED: "yes"}).missing == (BASE_URL, DEFAULT_WORKSPACE)


def test_a_timeout_that_is_not_a_number_falls_back_rather_than_stopping_the_boot() -> None:
    assert settings_from({"CANON_ARCHE_TIMEOUT_S": "soon"}).timeout == DEFAULT_TIMEOUT
    assert settings_from({"CANON_ARCHE_TIMEOUT_S": "12"}).timeout == timedelta(seconds=12)


# --------------------------------------------------------------------------
# 5.2 — the caller's own token, and never a service one
# --------------------------------------------------------------------------


def test_the_token_sent_is_the_caller_s_own() -> None:
    recorder = Recorder([(200, {"id": DOCUMENT, "title": "t", "trashed": False}), (200, {})])

    a_platform(recorder).resolve((a_ref(),), RAFA)

    assert recorder.calls[0]["headers"]["Authorization"] == "Bearer token-rafa"


def test_a_second_caller_s_request_carries_a_second_token() -> None:
    recorder = Recorder(
        [
            (200, {"id": DOCUMENT, "title": "t", "trashed": False}),
            (200, {}),
            (200, {"id": DOCUMENT, "title": "t", "trashed": False}),
            (200, {}),
        ]
    )
    platform = a_platform(recorder)

    platform.resolve((a_ref(),), Credential("token-rafa"))
    platform.resolve((a_ref(),), Credential("token-bruno"))

    tokens = [call["headers"].get("Authorization") for call in recorder.calls]
    assert "Bearer token-rafa" in tokens
    assert "Bearer token-bruno" in tokens


def test_no_request_is_made_under_a_service_credential_on_a_person_s_behalf() -> None:
    """D2: with no end-user token there is no `Authorization` header to invent."""
    recorder = Recorder([(401, {"error": "NotAuthenticated"})])

    with pytest.raises(PlatformUnavailable) as refusal:
        a_platform(recorder).resolve((a_ref(),), NO_CREDENTIAL)

    assert "Authorization" not in recorder.calls[0]["headers"]
    assert refusal.value.reason is UnavailabilityReason.REJECTED


def test_the_adapter_holds_no_credential_and_cannot_be_given_one() -> None:
    platform = a_platform(Recorder())

    assert not any(
        "token" in name or "credential" in name or "secret" in name for name in vars(platform)
    )


# --------------------------------------------------------------------------
# 5.3 — the payload boundary
# --------------------------------------------------------------------------


def test_a_delegated_search_carries_the_query_and_the_scope_and_nothing_else() -> None:
    recorder = Recorder([(200, [{"id": DOCUMENT, "title": "t", "snippet": "a passage"}])])

    a_platform(recorder).search("why does the scout read as a courier", RAFA, workspace=WORKSPACE)

    call = recorder.last
    assert call["method"] == "GET"
    assert call["params"] == {"q": "why does the scout read as a courier", "limit": 10}
    assert WORKSPACE in call["url"]
    assert call["json"] is None


def test_no_specification_annotation_or_compiled_content_reaches_the_platform() -> None:
    recorder = Recorder(
        [
            (201, {"id": "made_1", "title": "mech_scout — design document"}),
            (200, [{"id": DOCUMENT, "title": "t", "snippet": "a passage"}]),
        ]
    )
    platform = a_platform(recorder)

    platform.create(WORKSPACE, "mech_scout — design document", RAFA)
    platform.search("the pauldron reads as a backpack", RAFA)

    for forbidden in (SPEC_TEXT, COMPILED, "silhouette_rules", "annotations"):
        assert forbidden not in recorder.everything_sent


def test_creating_a_document_sends_a_workspace_and_a_title_and_no_content() -> None:
    recorder = Recorder([(201, {"id": "made_1"})])

    a_platform(recorder).create(WORKSPACE, "mech_scout — design document", RAFA)

    assert recorder.last["json"] == {
        "workspace_id": WORKSPACE,
        "title": "mech_scout — design document",
    }


# --------------------------------------------------------------------------
# 5.4 — there is no ingestion path
# --------------------------------------------------------------------------


def test_the_only_write_is_creating_an_empty_pre_titled_document() -> None:
    """Task 5.4: enumerate the outbound operations and assert the inventory (D10)."""
    platform = a_platform(Recorder())
    operations = {
        name
        for name in dir(platform)
        if not name.startswith("_") and callable(getattr(platform, name))
    }

    assert operations == {"resolve", "create", "search", "revisions"}
    assert ArcheDocumentPlatform.WRITES == ("create",)


def test_every_operation_but_create_uses_a_read_method() -> None:
    recorder = Recorder(
        [
            (200, {"id": DOCUMENT, "title": "t", "trashed": False}),
            (200, {}),
            (200, []),
            (200, []),
        ]
    )
    platform = a_platform(recorder)

    platform.resolve((a_ref(),), RAFA)
    platform.revisions(a_ref(), RAFA)
    platform.search("a prose question", RAFA)

    assert {call["method"] for call in recorder.calls} == {"GET"}


def test_the_adapter_has_no_method_that_uploads_anything() -> None:
    platform = a_platform(Recorder())
    forbidden = {"upload", "publish", "mirror", "index", "ingest", "push", "sync", "update"}

    assert not {name for name in dir(platform) if name in forbidden}


# --------------------------------------------------------------------------
# 5.5 — every transport outcome maps onto exactly one reason or state
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("status", "state"),
    [
        (403, DocumentState.FORBIDDEN),
        (404, DocumentState.MISSING),
        (410, DocumentState.MISSING),
        (500, DocumentState.UNREACHABLE),
        (502, DocumentState.UNREACHABLE),
    ],
)
def test_a_status_line_maps_onto_one_document_state(status: int, state: DocumentState) -> None:
    recorder = Recorder([(status, {"detail": "nope"})])

    answer = a_platform(recorder).resolve((a_ref(),), RAFA)[0]

    assert answer.state is state
    assert answer.title == ""


def test_a_document_the_platform_reports_as_trashed_is_missing_not_readable() -> None:
    recorder = Recorder([(200, {"id": DOCUMENT, "title": "gone", "trashed": True})])

    answer = a_platform(recorder).resolve((a_ref(),), RAFA)[0]

    assert answer.state is DocumentState.MISSING
    assert answer.title == ""


def test_a_401_stops_the_whole_call_because_it_is_about_the_credential() -> None:
    recorder = Recorder([(401, {"error": "NotAuthenticated"})])

    with pytest.raises(PlatformUnavailable) as refusal:
        a_platform(recorder).resolve((a_ref(),), RAFA)

    assert refusal.value.reason is UnavailabilityReason.REJECTED


def test_a_connection_failure_is_unreachable() -> None:
    recorder = Recorder()
    recorder.raise_with = ConnectionError("no route to host")

    with pytest.raises(PlatformUnavailable) as refusal:
        a_platform(recorder).resolve((a_ref(),), RAFA)

    assert refusal.value.reason is UnavailabilityReason.UNREACHABLE


def test_a_timeout_is_timed_out_and_not_merely_unreachable() -> None:
    class ReadTimeout(Exception):
        pass

    recorder = Recorder()
    recorder.raise_with = ReadTimeout("the budget ran out")

    with pytest.raises(PlatformUnavailable) as refusal:
        a_platform(recorder).search("a prose question", RAFA)

    assert refusal.value.reason is UnavailabilityReason.TIMED_OUT


def test_a_body_that_is_not_json_is_malformed_and_not_an_outage() -> None:
    recorder = Recorder([(200, ValueError("not json"))])

    with pytest.raises(PlatformUnavailable) as refusal:
        a_platform(recorder).resolve((a_ref(),), RAFA)

    assert refusal.value.reason is UnavailabilityReason.MALFORMED


def test_a_created_document_with_no_identifier_is_malformed() -> None:
    recorder = Recorder([(201, {"title": "a document with no id"})])

    with pytest.raises(PlatformUnavailable) as refusal:
        a_platform(recorder).create(WORKSPACE, "t", RAFA)

    assert refusal.value.reason is UnavailabilityReason.MALFORMED


@pytest.mark.parametrize("status", [400, 403, 422])
def test_a_creation_the_platform_refuses_is_a_refusal_and_not_an_outage(status: int) -> None:
    recorder = Recorder([(status, {"detail": "you may not write here"})])

    with pytest.raises(DocumentCreationRefused) as refusal:
        a_platform(recorder).create(WORKSPACE, "t", RAFA)

    assert "you may not write here" in str(refusal.value)


def test_a_search_budget_tighter_than_the_configured_one_is_the_one_that_applies() -> None:
    recorder = Recorder([(200, [])])

    a_platform(recorder).search("a prose question", RAFA, timedelta(seconds=1))

    assert recorder.last["timeout"] == 1.0


# --------------------------------------------------------------------------
# What a resolved card is drawn from
# --------------------------------------------------------------------------


def test_a_readable_document_resolves_to_its_title_and_a_short_summary() -> None:
    recorder = Recorder(
        [
            (200, {"id": DOCUMENT, "title": "why it reads as a courier", "trashed": False}),
            (
                200,
                {
                    "blocks": [
                        {"type": "paragraph", "data": {"text": "The faction is logistics."}},
                        {"type": "table", "data": {"rows": []}},
                        {"type": "paragraph", "data": {"text": "We tried a heavier chassis."}},
                    ]
                },
            ),
        ]
    )

    answer = a_platform(recorder).resolve((a_ref(),), RAFA)[0]

    assert answer.title == "why it reads as a courier"
    assert answer.summary == "The faction is logistics. We tried a heavier chassis."


def test_a_document_whose_blocks_cannot_be_read_still_resolves_with_its_title() -> None:
    recorder = Recorder(
        [(200, {"id": DOCUMENT, "title": "still readable", "trashed": False}), (500, None)]
    )

    answer = a_platform(recorder).resolve((a_ref(),), RAFA)[0]

    assert answer.state is DocumentState.READABLE
    assert answer.title == "still readable"
    assert answer.summary == ""


def test_the_revisions_read_are_the_platform_s_own_snapshots_newest_first() -> None:
    recorder = Recorder(
        [
            (
                200,
                [
                    {"id": "s1", "seq": 1, "created_at": "2026-07-10T13:45:30Z"},
                    {"id": "s2", "seq": 2, "created_at": "2026-07-19T11:39:00Z", "label": "retopo"},
                ],
            )
        ]
    )

    revisions = a_platform(recorder).revisions(a_ref(), RAFA)

    assert [revision.id for revision in revisions] == ["s2", "s1"]
    assert recorder.last["url"].endswith(f"/api/v1/documents/{DOCUMENT}/snapshots")
