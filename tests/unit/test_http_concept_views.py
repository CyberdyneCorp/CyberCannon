"""Task 7.4 — the concept-view endpoints, delegating and deciding nothing.

The surface is asserted the way the rest of this package is: the *verdict* comes
from the use case, the *status* comes from the one mapping, and the handler has
no opinion of its own. What is checked here is that the translation is faithful
— the base64 envelope, the refusal that travels as itself, and the authorship
rule a view shares with a specification write (G4, D8).
"""

from __future__ import annotations

from base64 import b64encode
from dataclasses import replace

import pytest
from fastapi.testclient import TestClient
from http_world import AUTOMATION_TOKEN, PROJECT, SCOUT, Wired, a_surface

from cybercanon.adapters.inbound.http.app import build_app
from cybercanon.adapters.inbound.http.versioning import VERSION
from cybercanon.adapters.inbound.http.views import NO_IMAGES, UNREADABLE
from cybercanon.adapters.inbound.http.writes import AUTHORSHIP_REFUSED
from cybercanon.domain.revisions import ContentHash
from cybercanon.domain.views import ImageFacts
from views_world import RepositorySpecStore

pytestmark = pytest.mark.unit

BASE = f"/{VERSION}/projects/{PROJECT}/assets/{SCOUT}/views"

CREATED = 200
INVALID = 400
NOT_FOUND = 404
FORBIDDEN = 403


@pytest.fixture
def wired() -> Wired:
    """A deployment whose specifications are read out of its own working copy.

    `a_surface` wires the in-memory store, which is seeded once and pinned to
    one revision — right for a read surface, wrong here: ingestion *commits* an
    `asset.yaml` and then reads it back, and a store that answered what a test
    remembered to put in it would never see what the commit wrote. So this
    swaps in the repository-backed store, which is what a hosted deployment
    actually runs.
    """
    return _over_the_repository(a_surface())


def _over_the_repository(wired: Wired) -> Wired:
    built = wired.surface.projects[PROJECT]
    store = RepositorySpecStore(
        host=wired.repository_host,
        project=PROJECT,
        mapping=wired.spec_store.load_actor_mapping().mapping,
    )
    hosted = replace(built, container=replace(built.container, spec_store=store))
    surface = replace(wired.surface, projects={PROJECT: hosted})
    return Wired(client=TestClient(build_app(surface=surface)), surface=surface, fakes=wired.fakes)


def an_image(wired: Wired, *, width: int = 1024, height: int = 768, seed: int = 0) -> bytes:
    """Bytes the surface's inspector knows the facts of."""
    from canon_fixtures import image as fixtures

    content = fixtures.image_bytes(fixtures.PNG, width, height, seed=seed)
    wired.image_inspector.add(
        content,
        ImageFacts(
            format="png",
            width=width,
            height=height,
            byte_size=len(content),
            content_hash=ContentHash.of(content),
        ),
    )
    return content


def an_envelope(*images: tuple[str, bytes], name: str = "") -> dict:
    return {
        "images": [
            {"slot": slot, "content": b64encode(content).decode("ascii"), "filename": f"{slot}.png"}
            for slot, content in images
        ],
        "name": name,
    }


def _error(response) -> str:
    return str((response.json().get("error") or {}).get("id", ""))


# --------------------------------------------------------------------------
# Ingesting
# --------------------------------------------------------------------------


def test_an_upload_is_committed_and_the_response_names_the_view(wired: Wired) -> None:
    response = wired.post(BASE, json=an_envelope(("front", an_image(wired))))

    assert response.status_code == CREATED, response.text
    data = response.json()["data"]
    assert data["committed"] is True
    assert data["views"][0]["slot"] == "front"
    assert data["views"][0]["content_hash"].startswith("sha256:")
    assert data["views"][0]["path"].endswith("concept/front.png")


def test_three_slots_travel_in_one_request(wired: Wired) -> None:
    response = wired.post(
        BASE,
        json=an_envelope(
            ("front", an_image(wired, seed=1)),
            ("side", an_image(wired, seed=2)),
            ("back", an_image(wired, seed=3)),
        ),
    )

    assert response.status_code == CREATED, response.text
    assert len(response.json()["data"]["views"]) == 3


def test_an_envelope_with_no_images_is_invalid(wired: Wired) -> None:
    response = wired.post(BASE, json={"images": []})

    assert response.status_code == INVALID
    assert _error(response) == NO_IMAGES


def test_content_that_is_not_base64_is_invalid_rather_than_an_unreadable_image(
    wired: Wired,
) -> None:
    """Nothing has reached an inspector yet, and the caller is told which it is."""
    response = wired.post(BASE, json={"images": [{"slot": "front", "content": "not base64!"}]})

    assert response.status_code == INVALID
    assert _error(response) == UNREADABLE


def test_a_body_that_is_not_an_object_is_invalid(wired: Wired) -> None:
    response = wired.post(BASE, content=b"[]")

    assert response.status_code == INVALID
    assert _error(response) == UNREADABLE


def test_an_invalid_slot_name_travels_as_the_domains_refusal(wired: Wired) -> None:
    response = wired.post(BASE, json=an_envelope(("Front View!", an_image(wired))))

    assert response.status_code == INVALID
    assert "Front View!" in response.text


def test_an_automated_caller_may_not_author_a_view(wired: Wired) -> None:
    """G4's last row: a view is durable repository content in a person's name."""
    response = wired.post(
        BASE, token=AUTOMATION_TOKEN, json=an_envelope(("front", an_image(wired)))
    )

    assert response.status_code == FORBIDDEN
    assert _error(response) == AUTHORSHIP_REFUSED


def test_an_unmapped_person_is_refused_naming_the_missing_entry() -> None:
    wired = _over_the_repository(a_surface(mapped=False))

    response = wired.post(BASE, json=an_envelope(("front", an_image(wired))))

    assert response.status_code == FORBIDDEN
    assert ".canon/actors.yaml" in response.text


# --------------------------------------------------------------------------
# Reading the history
# --------------------------------------------------------------------------


def test_the_revision_listing_is_newest_first_with_one_current(wired: Wired) -> None:
    for seed in (1, 2, 3):
        wired.post(BASE, json=an_envelope(("front", an_image(wired, seed=seed))))

    response = wired.get(f"{BASE}/front/revisions")

    assert response.status_code == CREATED, response.text
    data = response.json()["data"]
    assert len(data["revisions"]) == 3
    assert [entry["current"] for entry in data["revisions"]] == [True, False, False]
    assert data["complete"] is True


def test_a_superseded_revision_is_served_labelled_historical(wired: Wired) -> None:
    wired.post(BASE, json=an_envelope(("front", an_image(wired, seed=1))))
    wired.post(BASE, json=an_envelope(("front", an_image(wired, seed=2))))
    older = wired.get(f"{BASE}/front/revisions").json()["data"]["revisions"][1]["revision"]

    response = wired.get(f"{BASE}/front/revisions/{older}")

    data = response.json()["data"]
    assert data["historical"] is True
    assert data["content"]


def test_an_unknown_revision_is_a_not_found_naming_it(wired: Wired) -> None:
    wired.post(BASE, json=an_envelope(("front", an_image(wired))))

    response = wired.get(f"{BASE}/front/revisions/no-such-revision")

    assert response.status_code == NOT_FOUND
    assert "no-such-revision" in response.text


def test_a_comparison_presents_the_older_revision_first(wired: Wired) -> None:
    wired.post(BASE, json=an_envelope(("front", an_image(wired, seed=1))))
    wired.post(BASE, json=an_envelope(("front", an_image(wired, seed=2))))
    listed = wired.get(f"{BASE}/front/revisions").json()["data"]["revisions"]
    newer, older = listed[0]["revision"], listed[1]["revision"]

    response = wired.get(f"{BASE}/front/comparison?first={newer}&second={older}")

    data = response.json()["data"]
    assert data["older"]["revision"] == older
    assert data["newer"]["revision"] == newer


def test_the_token_carries_the_content_hash_of_the_current_revision(wired: Wired) -> None:
    content = an_image(wired)
    wired.post(BASE, json=an_envelope(("front", content)))

    response = wired.get(f"{BASE}/front/token")

    assert response.json()["data"]["content_hash"] == ContentHash.of(content).labelled


def test_removing_a_view_is_a_revision_and_the_earlier_ones_survive(wired: Wired) -> None:
    wired.post(BASE, json=an_envelope(("front", an_image(wired, seed=1))))
    wired.post(BASE, json=an_envelope(("front", an_image(wired, seed=2))))

    removed = wired.delete(f"{BASE}/front")

    assert removed.status_code == CREATED, removed.text
    listed = wired.get(f"{BASE}/front/revisions").json()["data"]
    assert listed["removed"] is True
    assert not any(entry["current"] for entry in listed["revisions"])


def test_an_unknown_view_is_a_not_found_rather_than_an_empty_listing(wired: Wired) -> None:
    response = wired.get(f"{BASE}/side/revisions")

    assert response.status_code == NOT_FOUND
