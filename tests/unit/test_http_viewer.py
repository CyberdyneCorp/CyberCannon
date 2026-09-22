"""Group 3 — the viewer over HTTP, and the address rule that has to hold here.

The load-bearing test in this module is
`test_no_address_this_surface_registers_resolves_to_a_working_export`. D7 says
so in as many words: *"`project.md`'s whole preview design exists so a browser
never pulls a 200 MB export; a rule only held in the frontend is one `fetch`
away from being broken."* So the route table is enumerated and every path is
checked, rather than the frontend being trusted never to offer the link.
"""

from __future__ import annotations

import base64

import pytest
from http_world import PROJECT, SCOUT, SCOUT_SPEC, a_surface

from cybercanon.adapters.inbound.http.versioning import PREFIX
from cybercanon.application.ports.preview import PreviewMesh
from cybercanon.application.ports.repository_host import FileChange
from cybercanon.application.use_cases.validation_records import path_for, to_document
from cybercanon.domain.actors import GitAuthor
from cybercanon.domain.format_matrix import facts_for
from cybercanon.domain.mesh_facts import ClipFacts, MeshFormat
from cybercanon.domain.validation_outcome import ValidationRecord

pytestmark = pytest.mark.unit

EXPORT = "characters/mech_scout/exports/mech_scout.glb"
PARTS = ("SM_MechScout_Shoulder_L", "SM_MechScout_Torso")
WALK = "A_mech_scout_walk"
PREVIEW = b"glTF\x02\x00\x00\x00a-decimated-preview"

BASE = f"{PREFIX}/projects/{PROJECT}/assets/{SCOUT}/preview"

AUTOMATION = GitAuthor(name="canon automation", email="automation@cybercanon.invalid")


def a_viewer_surface(*, validated: bool = True, preview: bool = True):
    """The wired surface with an export, an outcome document and a stored preview."""
    wired = a_surface()
    wired.fakes["mesh_inspector"].add(
        EXPORT,
        facts_for(
            MeshFormat.GLB,
            triangles=14310,
            objects=PARTS,
            materials=("M_Body",),
            clips=(ClipFacts(name=WALK, duration_s=1.2),),
        ),
    )
    if validated:
        wired.repository_host.commit(
            PROJECT,
            [FileChange(path=path_for(SCOUT_SPEC), content=_outcome())],
            author=AUTOMATION,
            message="validation outcome",
        )
        wired.repository_host.push(PROJECT)
        wired.spec_store.snapshot(wired.repository_host.head(PROJECT).value)
    if preview:
        wired.blob_store.put_preview(
            SCOUT,
            EXPORT,
            PreviewMesh(content=PREVIEW, triangles=4200, parts=PARTS, clips=(WALK,)),
        )
    return wired


def _outcome(export: str = EXPORT, passed: bool = True) -> bytes:
    from datetime import UTC, datetime

    return to_document(
        ValidationRecord(
            asset_id=SCOUT,
            export=export,
            export_hash="sha256:" + "0" * 64,
            passed=passed,
            validated_at=datetime(2026, 9, 22, 9, 0, tzinfo=UTC),
        )
    )


# --------------------------------------------------------------------------
# 3.1 — the descriptor, including the asset that has no preview
# --------------------------------------------------------------------------


def test_the_descriptor_states_the_export_the_revision_and_the_counts() -> None:
    answer = a_viewer_surface().get(BASE)

    assert answer.status_code == 200
    body = answer.json()["data"]
    assert body["source_export"] == EXPORT
    assert body["derived_from_latest"] is True
    assert body["counts"] == {"triangles": 14310, "objects": 2, "materials": 1}
    assert body["parts"] == list(PARTS)
    assert body["clips"] == [WALK]


def test_an_asset_with_no_preview_answers_a_descriptor_with_its_reason() -> None:
    """*"SHALL state the reason it is able to determine"*, not an error status."""
    answer = a_viewer_surface(validated=False, preview=False).get(BASE)

    assert answer.status_code == 200
    body = answer.json()["data"]
    assert body["preview"] is None
    assert body["absent"] == "no_export_recorded"
    assert body["reason"]


def test_a_failed_emission_is_distinguished_from_an_unvalidated_export() -> None:
    body = a_viewer_surface(preview=False).get(BASE).json()["data"]

    assert body["absent"] == "emission_failed"
    assert body["latest_validated_export"] == EXPORT


def test_the_read_states_the_revision_it_was_served_from() -> None:
    """The descriptor carries it, because *"which revision is in view"* is on screen."""
    assert a_viewer_surface().get(BASE).json()["data"]["revision"]


def test_an_unknown_project_is_not_found_rather_than_forbidden() -> None:
    answer = a_viewer_surface().get(f"{PREFIX}/projects/nowhere/assets/{SCOUT}/preview")

    assert answer.status_code == 404


# --------------------------------------------------------------------------
# 3.4 — the bytes
# --------------------------------------------------------------------------


def test_the_preview_is_delivered_byte_identical() -> None:
    body = a_viewer_surface().get(f"{BASE}/content").json()["data"]

    assert base64.b64decode(body["content"]) == PREVIEW
    assert body["size_bytes"] == len(PREVIEW)
    assert body["content_type"] == "model/gltf-binary"


def test_a_preview_whose_object_is_gone_is_reported_as_unretrievable() -> None:
    wired = a_viewer_surface()
    key = wired.get(BASE).json()["data"]["preview"]["key"]
    wired.blob_store.lose_contents()

    answer = wired.get(f"{BASE}/content")

    assert answer.status_code == 503
    failure = answer.json()["error"]
    assert failure["id"] == "preview.unretrievable"
    assert failure["subject"] == key


# --------------------------------------------------------------------------
# 3.1 — resolutions
# --------------------------------------------------------------------------


def test_resolutions_are_answered_against_the_export_s_part_names() -> None:
    body = a_viewer_surface().get(f"{BASE}/resolutions").json()["data"]

    assert body["export"] == EXPORT
    assert body["orphaned"] == 0
    assert body["resolutions"] == []


# --------------------------------------------------------------------------
# 3.3 — D7: no address resolves to a working export
# --------------------------------------------------------------------------


EXPORT_TOKENS = ("export", "exports", "source", "working", "mesh", "fbx", "glb", "obj")
"""What a route that served a working export would have to be spelled with.

Broad on purpose: the test is looking for the route somebody adds in a hurry,
and a narrow list would miss `/assets/{asset}/mesh` while passing itself off as
enforcement.
"""

ALLOWED = (f"{PREFIX}/projects/{{project}}/validations",)
"""The one address that names an export, and does not serve one.

`/validations?export=...` runs the validator over a path *in the repository* and
answers a verdict. It reads a mesh server-side and returns a report; no byte of
the export reaches the caller, which is exactly the distinction D7 draws.
"""


def _routes() -> tuple[str, ...]:
    """Every address this surface publishes, read from its own generated description.

    The interface document rather than the route objects, because that document
    *is* what a client discovers the surface through (task 9.10 of
    `add-web-backend`): an address that is not in it is not one a browser can
    find, and an address that is in it is one somebody will eventually request.
    """
    return tuple(a_viewer_surface().client.app.openapi()["paths"])


def test_no_address_this_surface_registers_resolves_to_a_working_export() -> None:
    offenders = [
        path
        for path in _routes()
        if path not in ALLOWED and any(token in path.lower() for token in EXPORT_TOKENS)
    ]

    assert not offenders, (
        "D7: the viewer addresses previews only, and the rule is enforced at the "
        f"API rather than in the UI. These routes name an export: {offenders}"
    )


def test_the_viewer_s_own_addresses_are_the_preview_ones() -> None:
    """The other half: a boundary nothing crosses is a boundary over nothing."""
    viewer_routes = [path for path in _routes() if path.endswith(("preview", "content"))]

    assert viewer_routes, "the viewer registers no address at all"
    assert all("preview" in path for path in viewer_routes)


def test_the_descriptor_document_carries_no_address_for_the_export() -> None:
    """The export's *path* is provenance; a way to fetch it would be a link."""
    body = a_viewer_surface().get(BASE).json()["data"]

    assert body["source_export"] == EXPORT
    assert body["preview"]["key"] != EXPORT
    assert EXPORT not in body["preview"]["key"]


# --------------------------------------------------------------------------
# 3.2 — the re-anchor write, attributed from the credential and nothing else
# --------------------------------------------------------------------------


REANCHOR_BASE = f"{PREFIX}/projects/{PROJECT}/assets/{SCOUT}/annotations"


def _with_a_part_annotation(wired):
    """One 3D annotation in the repository, placed on a part the export has."""
    answer = wired.post(
        REANCHOR_BASE,
        json={
            "id": "an_1",
            "kind": "art-direction",
            "text": "the pauldron reads as a backpack at 15 m",
            "anchor": {"part": PARTS[0]},
        },
    )
    assert answer.status_code == 200, answer.json()
    _advance(wired)
    return wired


def _advance(wired) -> None:
    """Re-read the repository into the in-memory store, as the annotation suite does."""
    head = wired.repository_host.head(PROJECT)
    content = wired.repository_host.read(PROJECT, SCOUT_SPEC, head)
    if content is not None:
        wired.spec_store.add(SCOUT_SPEC, wired.spec_store.parse_document(SCOUT_SPEC, content).asset)
    wired.spec_store.snapshot(head.value)


def test_re_anchoring_is_exposed_through_the_write_conventions() -> None:
    wired = _with_a_part_annotation(a_viewer_surface())

    answer = wired.post(f"{REANCHOR_BASE}/an_1/reanchor", json={"anchor": {"part": PARTS[1]}})

    assert answer.status_code == 200, answer.json()
    recorded = answer.json()["data"]["annotation"]
    assert recorded["anchor"]["part"] == PARTS[1]
    assert recorded["anchor"]["durable_key"] == PARTS[1]


def test_an_actor_parameter_does_not_change_who_the_re_anchor_is_attributed_to() -> None:
    """Identity is the verified credential; a body or query field carries none."""
    wired = _with_a_part_annotation(a_viewer_surface())

    answer = wired.post(
        f"{REANCHOR_BASE}/an_1/reanchor?actor=auth|ana",
        json={"anchor": {"part": PARTS[1]}, "actor": "auth|ana", "author": "auth|ana"},
    )

    assert answer.status_code == 200, answer.json()
    assert answer.json()["data"]["annotation"]["author"] == "auth|rafa"


def test_a_re_anchor_records_the_playback_hint_as_a_proportion() -> None:
    """D9 — the anchor the viewer sends may carry a clip and a position, never a frame."""
    wired = _with_a_part_annotation(a_viewer_surface())

    answer = wired.post(
        f"{REANCHOR_BASE}/an_1/reanchor",
        json={"anchor": {"part": PARTS[1], "clip": WALK, "t": 0.75}},
    )

    anchor = answer.json()["data"]["annotation"]["anchor"]
    assert (anchor["clip"], anchor["t"]) == (WALK, 0.75)
    assert "frame" not in anchor


def test_a_playback_position_outside_the_range_is_refused() -> None:
    wired = _with_a_part_annotation(a_viewer_surface())

    answer = wired.post(
        f"{REANCHOR_BASE}/an_1/reanchor",
        json={"anchor": {"part": PARTS[1], "clip": WALK, "t": 24}},
    )

    assert answer.status_code == 400
    assert "proportion" in answer.json()["error"]["message"]
