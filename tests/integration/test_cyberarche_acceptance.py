"""Tasks 7.4 and 7.5 — the whole integration, over a real repository and the real surface.

Two claims, and neither is checkable one layer at a time.

**7.4 — the integration degrades to absent.** *"When the document platform is
not configured, every capability of the system unrelated to linked documents
SHALL behave identically to a deployment where it is configured."* The only
honest way to assert *identically* is to run both deployments and compare the
answers, so that is what this does: the same repository, the same requests, one
container with a platform and one with none, and a byte comparison of every
answer that is not about a linked document. Anything that differed — a field, a
number, a revision — fails here rather than being argued about.

**7.5 — the acceptance test.** A designer creates a rationale document for
`mech_scout` from the asset page and it is linked in one action; a second person
with no access to that workspace sees the link marked inaccessible carrying no
title and no summary; and a natural-language question comes back with the
passage labelled approximate while the exact group is empty. Three people, three
requests, one repository.

The platform is the in-memory one, because what is under test here is *this*
product's behaviour at its own surface. The adapter against the live CyberArche
deployment is `tests/integration/test_arche_live.py`, and it is opt-in.
"""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from staged_project import PROJECT, SCOUT_EXPORT, SCOUT_SPEC, Staged, ready

from canon_fixtures.mesh import write_skinned_glb
from cybercanon.adapters.inbound.http.app import build_app
from cybercanon.adapters.inbound.http.surface import HostedProject, Surface
from cybercanon.adapters.inbound.http.versioning import VERSION
from cybercanon.adapters.wiring.build import build_container
from cybercanon.adapters.wiring.container import Container
from cybercanon.application.ports.identity_provider import Credential
from cybercanon.application.testing.document_platform import InMemoryDocumentPlatform
from cybercanon.application.testing.identity_provider import InMemoryIdentityProvider
from cybercanon.application.testing.outcomes import ran
from cybercanon.application.testing.search_index import InMemorySearchIndex
from cybercanon.application.use_cases.index_assets import rebuild_index
from cybercanon.domain.documents import DocumentState
from cybercanon.domain.identity import Actor, ActorId, Role

pytestmark = pytest.mark.integration

SCOUT = "mech_scout"
WORKSPACE = "w_production"

RAFA = "auth|rafa"
BRUNO = "auth|bruno"

RAFA_TOKEN = "token-rafa"
BRUNO_TOKEN = "token-bruno"

RAFA_EMAIL = "rafa@cyberdyne.com"
BRUNO_EMAIL = "bruno@cyberdyne.com"

ACTORS = b"""\
schema_version: 1
actors:
  - subject: auth|rafa
    display_name: Rafa Santos
    emails: [rafa@cyberdyne.com]
  - subject: auth|bruno
    display_name: Bruno Lima
    emails: [bruno@cyberdyne.com]
"""

PRIVATE = "d_unreleased"
"""A document in a workspace Bruno was never granted."""

PROSE = (
    "The scout reads as a courier rather than as a brawler because the faction "
    "is logistics: every panel it wears was taken off something else, and the "
    "silhouette has to say that before anybody reads a label."
)

QUESTION = "why does the scout read as a courier rather than a brawler"

BASE = f"/{VERSION}/projects/{PROJECT}"


# --------------------------------------------------------------------------
# Two deployments over one repository
# --------------------------------------------------------------------------


@pytest.fixture
def staged(tmp_path: Path) -> Staged:
    """The staged project, plus a git-identity mapping and a real export.

    The corpus's export is a placeholder, and 7.4 asks for *validation* to be
    exercised rather than for a refusal to be exercised twice — so a real
    skinned GLB is committed over it and the verdict compared is a verdict.
    """
    project = ready(tmp_path)
    export = tmp_path / "SM_mech_scout_LOD0.glb"
    write_skinned_glb(export)
    project.commit_outside(".canon/actors.yaml", ACTORS, "map the team to git identities")
    project.commit_outside(SCOUT_EXPORT, export.read_bytes(), "a real export")
    project.host.fetch(PROJECT)
    return project


@pytest.fixture
def platform() -> InMemoryDocumentPlatform:
    """A platform holding one readable document and one Bruno may not see."""
    built = InMemoryDocumentPlatform()
    built.add_actor(RAFA_TOKEN, RAFA)
    built.add_actor(BRUNO_TOKEN, BRUNO)
    built.add_document(
        WORKSPACE,
        PRIVATE,
        "mech_scout — unreleased faction brief",
        summary=PROSE,
        body=PROSE,
        readers=(RAFA,),
    )
    built.permit_creation(RAFA, WORKSPACE)
    return built


def _container(staged: Staged, platform: InMemoryDocumentPlatform | None) -> Container:
    """The container the composition root builds, pointed at this working copy.

    Built through :func:`build_container` rather than assembled here, so the two
    deployments differ in exactly one thing — whether a document platform is
    wired — and in nothing a fixture happened to pass differently.
    """
    built = replace(
        build_container(staged.working_copy),
        search_index=InMemorySearchIndex(),
        project_id=PROJECT,
    )
    ran(
        rebuild_index(
            "",
            spec_store=built.spec_store,
            search_index=built.search_index,
            project=PROJECT,
        )
    )
    if platform is None:
        return built
    return replace(built, document_platform=platform, document_workspace=WORKSPACE)


def _client(container: Container, staged: Staged) -> TestClient:
    provider = InMemoryIdentityProvider()
    provider.add(
        Credential(RAFA_TOKEN),
        Actor(
            id=ActorId(RAFA),
            display_name="Rafa",
            roles=(Role.ART_DIRECTOR,),
            projects=(PROJECT,),
        ),
        git_emails=(RAFA_EMAIL,),
    )
    provider.add(
        Credential(BRUNO_TOKEN),
        Actor(id=ActorId(BRUNO), display_name="Bruno", projects=(PROJECT,)),
        git_emails=(BRUNO_EMAIL,),
    )
    surface = Surface(
        projects={
            PROJECT: HostedProject(name=PROJECT, container=container, repository_host=staged.host)
        },
        identity_provider=provider,
    )
    return TestClient(build_app(surface=surface))


@pytest.fixture
def configured(staged: Staged, platform: InMemoryDocumentPlatform) -> TestClient:
    return _client(_container(staged, platform), staged)


@pytest.fixture
def unconfigured(staged: Staged) -> TestClient:
    """The same repository, with no document platform configuration at all."""
    return _client(_container(staged, None), staged)


def _get(client: TestClient, path: str, token: str = RAFA_TOKEN) -> dict[str, Any]:
    response = client.get(path, headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200, response.text
    return response.json()


def _answer(client: TestClient, path: str, token: str = RAFA_TOKEN) -> tuple[int, str]:
    """One answer, reduced to what two deployments must agree about.

    The status *and* the body, because *"behave exactly as"* is a claim about
    both — and with the correlation identifier and the confirmation timestamp
    dropped, since those are about this request rather than about the answer.
    """
    response = client.get(path, headers={"Authorization": f"Bearer {token}"})
    return response.status_code, _comparable(response.json())


def _documents(client: TestClient, token: str = RAFA_TOKEN) -> dict[str, Any]:
    return _get(client, f"{BASE}/assets/{SCOUT}/documents", token)["data"]


def _spec_text(staged: Staged) -> str:
    return (staged.working_copy / SCOUT_SPEC).read_text(encoding="utf-8")


# --------------------------------------------------------------------------
# 7.4 — every unrelated capability answers identically
# --------------------------------------------------------------------------

UNRELATED = (
    f"{BASE}/assets",
    f"{BASE}/assets/{SCOUT}",
    f"{BASE}/assets/{SCOUT}/briefing",
    f"{BASE}/assets/{SCOUT}/locations",
    f"{BASE}/briefing",
    f"{BASE}/validations?export=characters/mech_scout/exports/SM_mech_scout_LOD0.glb",
)
"""Asset browsing, compilation and validation — every capability 7.4 names but search."""

VOLATILE = ("correlation_id", "confirmed_at")
"""Fields that are about *this request* rather than about the answer."""


def _comparable(body: dict[str, Any]) -> str:
    return json.dumps(
        {name: value for name, value in body.items() if name not in VOLATILE},
        sort_keys=True,
    )


@pytest.mark.parametrize("path", UNRELATED, ids=lambda path: path.split("/projects/")[-1])
def test_an_unrelated_capability_answers_byte_identically(
    configured: TestClient, unconfigured: TestClient, path: str
) -> None:
    """Task 7.4 — *"all SHALL behave exactly as with the platform configured"*."""
    assert _answer(configured, path) == _answer(unconfigured, path)


def test_the_export_really_was_validated(configured: TestClient) -> None:
    """So that the comparison above is a comparison of verdicts, not of refusals."""
    outcome = _get(configured, UNRELATED[-1])["data"]

    assert outcome["export_format"].lower() == "glb"
    assert outcome["outcome"] in {"passing", "failing"}


def test_an_identifier_query_is_the_same_answer_in_both_deployments(
    configured: TestClient, unconfigured: TestClient
) -> None:
    """The gate never delegates it, so there is nothing for the platform to change."""
    assert _answer(configured, f"{BASE}/search?q={SCOUT}") == _answer(
        unconfigured, f"{BASE}/search?q={SCOUT}"
    )


def test_a_prose_query_keeps_its_local_results_and_says_why_there_is_no_other_half(
    configured: TestClient, unconfigured: TestClient
) -> None:
    """Local search is untouched; only the group beside it distinguishes the two."""
    query = QUESTION.replace(" ", "+")
    with_platform = _get(configured, f"{BASE}/search?q={query}")
    without = _get(unconfigured, f"{BASE}/search?q={query}")

    assert with_platform["data"] == without["data"]
    assert without["semantic"]["available"] is False
    assert without["semantic"]["reason"] == "unconfigured"


def test_the_links_are_still_listed_and_openable_with_no_configuration(
    staged: Staged, configured: TestClient, unconfigured: TestClient
) -> None:
    """*"Existing stored references SHALL still be listed and openable."*"""
    address = f"https://documents.invalid/w/{WORKSPACE}/d/{PRIVATE}"
    written = configured.put(
        f"{BASE}/assets/{SCOUT}/documents/{PRIVATE}",
        headers={"Authorization": f"Bearer {RAFA_TOKEN}"},
        json={"workspace": WORKSPACE, "url": address},
    )
    assert written.status_code == 200, written.text

    listing = _documents(unconfigured)
    assert listing["available"] is False
    assert listing["reason"] == "unconfigured"
    entry = listing["links"][0]
    assert entry["document"] == PRIVATE
    assert entry["url"] == address
    assert entry["title"] == ""
    assert "open" in entry["actions"]


def test_creating_a_document_with_no_configuration_reports_unavailability(
    staged: Staged, unconfigured: TestClient
) -> None:
    """*"The feature SHALL report itself unavailable and name the reason."*"""
    before = _spec_text(staged)

    response = unconfigured.post(
        f"{BASE}/assets/{SCOUT}/documents",
        headers={"Authorization": f"Bearer {RAFA_TOKEN}"},
        json={},
    )

    assert response.status_code == 503, response.text
    assert "unconfigured" in response.text
    assert _spec_text(staged) == before


# --------------------------------------------------------------------------
# 7.5 — the acceptance test
# --------------------------------------------------------------------------


def test_a_designer_creates_a_rationale_document_from_the_asset_page(
    staged: Staged, configured: TestClient, platform: InMemoryDocumentPlatform
) -> None:
    """One action: the document exists at the platform and the link is committed."""
    response = configured.post(
        f"{BASE}/assets/{SCOUT}/documents",
        headers={"Authorization": f"Bearer {RAFA_TOKEN}"},
        json={"title": f"{SCOUT} — design rationale"},
    )

    assert response.status_code == 200, response.text
    recorded = response.json()["data"]
    created = recorded["created"]
    assert created is not None
    assert SCOUT in created["title"]
    assert platform.exists(WORKSPACE, created["document"])
    assert created["document"] in _spec_text(staged)
    assert recorded["reference"]["linked_by"] == RAFA
    assert PROSE not in _spec_text(staged)


def test_a_second_person_sees_the_link_marked_inaccessible_with_no_title(
    configured: TestClient,
) -> None:
    """The permission boundary, at the surface: Bruno gets a state and nothing else."""
    address = f"https://documents.invalid/w/{WORKSPACE}/d/{PRIVATE}"
    written = configured.put(
        f"{BASE}/assets/{SCOUT}/documents/{PRIVATE}",
        headers={"Authorization": f"Bearer {RAFA_TOKEN}"},
        json={"workspace": WORKSPACE, "url": address},
    )
    assert written.status_code == 200, written.text

    mine = _documents(configured)["links"][0]
    assert mine["state"] == str(DocumentState.READABLE)
    assert mine["title"] == "mech_scout — unreleased faction brief"

    theirs = _documents(configured, BRUNO_TOKEN)["links"][0]
    assert theirs["state"] == str(DocumentState.FORBIDDEN)
    assert theirs["title"] == ""
    assert theirs["summary"] == ""
    assert "courier" not in json.dumps(theirs)
    assert theirs["url"] == address


def test_a_natural_language_question_returns_the_passage_above_no_exact_match(
    configured: TestClient,
) -> None:
    """The third half of acceptance: a question, an approximate answer, no exact one."""
    answered = _get(configured, f"{BASE}/search?q={QUESTION.replace(' ', '+')}")

    assert answered["data"]["items"] == []
    semantic = answered["semantic"]
    assert semantic["delegated"] is True
    assert semantic["available"] is True
    assert semantic["approximate"] is True
    assert [found["document"] for found in semantic["results"]] == [PRIVATE]
    assert semantic["results"][0]["provenance"] == "semantic"
    assert "asset" not in semantic["results"][0]


def test_the_question_asked_as_bruno_returns_nothing_of_that_document(
    configured: TestClient,
) -> None:
    """Delegation runs under the asker's own authority, so it answers per person."""
    answered = _get(configured, f"{BASE}/search?q={QUESTION.replace(' ', '+')}", BRUNO_TOKEN)

    assert [found["document"] for found in answered["semantic"]["results"]] == []
    assert "courier" not in json.dumps(answered)
