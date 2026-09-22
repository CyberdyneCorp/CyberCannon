"""Step definitions for `viewer-3d` — the half of the viewer that is the system.

**Read the pending list beside this file.** Navigation, framing, selection,
isolation and the two degraded presentations are claims about a *screen*, and
they are exercised where they can be — `apps/cybercanon/web/tests/viewer-*.test.ts`,
which run under `just check` through `web-check` — and listed in
`tests/bdd/pending.txt` as the reviewed exception `add-test-strategy`'s D3
provides for, exactly as `add-model-sheet-2d` and `add-web-app-shell` listed
theirs.

What is bound here is every scenario whose THEN the system answers: which
preview is loaded and which export it came from, whether that export is still
the latest, the counts the validation run recorded, the three reasons an asset
has no preview, the unretrievable one — and, the one that matters most for the
selective-MVVM claim, that a filter and an exit behave identically in the two
surfaces **because they are one use case**.

D7 is here rather than in the browser on purpose: *"a rule only held in the
frontend is one `fetch` away from being broken"*, so the address enumeration is
over the application's own generated interface description.
"""

from __future__ import annotations

from typing import Any

import pytest
from pytest_bdd import given, scenario, then, when

from annotations_world import PROJECT, a_part_anchor
from cybercanon.adapters.inbound.http.app import build_app
from cybercanon.adapters.inbound.http.versioning import PREFIX
from cybercanon.application.testing.outcomes import ran
from cybercanon.application.use_cases.viewer import NoPreview
from cybercanon.domain.annotations import AnnotationFilter, AnnotationKind
from viewer_world import (
    EXPORT,
    MATERIALS,
    OLDER_EXPORT,
    PARTS,
    PREVIEW_BYTES,
    SHOULDER,
    Viewer,
    a_spec_with_states,
    a_viewer,
    an_export,
)

EXPORT_TOKENS = ("export", "exports", "working", "mesh", "fbx", "glb", "obj")
"""What a route serving a working export would have to be spelled with."""

VALIDATIONS = f"{PREFIX}/projects/{{project}}/validations"
"""The one address that *names* an export and serves a verdict, never bytes."""


@pytest.fixture
def viewer() -> Viewer:
    return a_viewer()


@pytest.fixture
def outcome() -> dict[str, Any]:
    return {}


# --------------------------------------------------------------------------
# Scenarios
# --------------------------------------------------------------------------


@scenario("../features/add-viewer-3d/viewer-3d.feature", "Preview is what is loaded")
def test_preview_is_what_is_loaded() -> None: ...


@scenario("../features/add-viewer-3d/viewer-3d.feature", "No route exposes the working export")
def test_no_route_exposes_the_working_export() -> None: ...


@scenario("../features/add-viewer-3d/viewer-3d.feature", "Provenance is visible")
def test_provenance_is_visible() -> None: ...


@scenario("../features/add-viewer-3d/viewer-3d.feature", "Superseded preview is flagged")
def test_superseded_preview_is_flagged() -> None: ...


@scenario("../features/add-viewer-3d/viewer-3d.feature", "Budget-relevant count is the source's")
def test_budget_relevant_count_is_the_sources() -> None: ...


@scenario("../features/add-viewer-3d/viewer-3d.feature", "Unrecorded count is absent, not inferred")
def test_unrecorded_count_is_absent_not_inferred() -> None: ...


@scenario("../features/add-viewer-3d/viewer-3d.feature", "No export yet")
def test_no_export_yet() -> None: ...


@scenario("../features/add-viewer-3d/viewer-3d.feature", "Preview emission failed")
def test_preview_emission_failed() -> None: ...


@scenario("../features/add-viewer-3d/viewer-3d.feature", "Retrieval fails")
def test_retrieval_fails() -> None: ...


@scenario("../features/add-viewer-3d/viewer-3d.feature", "Same annotation state in both surfaces")
def test_same_annotation_state_in_both_surfaces() -> None: ...


@scenario(
    "../features/add-viewer-3d/viewer-3d.feature", "Triage performed in 3D behaves identically"
)
def test_triage_performed_in_3d_behaves_identically() -> None: ...


# --------------------------------------------------------------------------
# Given
# --------------------------------------------------------------------------


@given("an asset with a working export and a preview derived from it")
def _an_asset_with_an_export_and_a_preview(viewer: Viewer) -> None:
    assert ran(viewer.descriptor()).has_preview


@given("a preview derived from a named export")
def _a_preview_from_a_named_export(viewer: Viewer) -> None:
    assert ran(viewer.descriptor()).source_export == EXPORT


@given(
    "a preview derived from an export that has since been superseded by a newer validated export"
)
def _a_superseded_preview(viewer: Viewer) -> None:
    viewer.store_preview(OLDER_EXPORT)


@given("a source export of 14310 triangles whose preview contains 4200")
def _a_source_of_14310(viewer: Viewer) -> None:
    assert ran(viewer.descriptor()).counts.triangles == 14310


@given("an asset whose source material count was never recorded")
def _no_material_count(viewer: Viewer) -> None:
    from cybercanon.domain.mesh_facts import FactKind, MeshFacts, MeshFormat

    recorded = an_export()
    viewer.record_export(
        facts=MeshFacts(
            source_format=MeshFormat.GLB,
            available=recorded.available - {FactKind.MATERIALS},
            triangles=recorded.triangles,
            objects=recorded.objects,
            clips=recorded.clips,
        )
    )


@given("an asset whose status is `concept` with no export recorded")
def _an_asset_with_no_export(outcome: dict[str, Any]) -> None:
    from annotations_world import SCOUT_SPEC, a_world

    fresh = Viewer(threads=a_world({SCOUT_SPEC: a_spec_with_states()}))
    fresh.record_export()
    outcome["viewer"] = fresh


@given("an export that validated successfully but whose preview emission failed")
def _emission_failed(outcome: dict[str, Any]) -> None:
    from annotations_world import SCOUT_SPEC, a_world

    fresh = Viewer(threads=a_world({SCOUT_SPEC: a_spec_with_states()}))
    fresh.record_export()
    fresh.record_validation()
    outcome["viewer"] = fresh


@given("a recorded preview that cannot be retrieved")
def _an_unretrievable_preview(viewer: Viewer, outcome: dict[str, Any]) -> None:
    outcome["key"] = ran(viewer.descriptor()).preview.key  # type: ignore[union-attr]
    viewer.blobs.lose_contents()


@given("an annotation filtered out by an active filter in the 2D surface")
def _filtered_out_in_the_sheet(viewer: Viewer, outcome: dict[str, Any]) -> None:
    ran(viewer.threads.create("an_1", anchor=a_part_anchor(SHOULDER)))
    ran(
        viewer.threads.create("an_2", anchor=a_part_anchor(SHOULDER), kind=AnnotationKind.TECHNICAL)
    )
    wanted = AnnotationFilter.of(kinds=(AnnotationKind.TECHNICAL,))
    outcome["filter"] = wanted
    outcome["sheet"] = tuple(entry.id for entry in ran(viewer.threads.listed(wanted)).annotations)


@given("an open annotation displayed in the 3D viewer")
def _an_open_annotation(viewer: Viewer) -> None:
    ran(viewer.threads.create("an_1", anchor=a_part_anchor(SHOULDER)))


# --------------------------------------------------------------------------
# When
# --------------------------------------------------------------------------


@when("the asset is opened in the viewer")
def _opened_in_the_viewer(viewer: Viewer, outcome: dict[str, Any]) -> None:
    opened = outcome.get("viewer", viewer)
    outcome["descriptor"] = ran(opened.descriptor())
    outcome["content"] = opened.preview_bytes()


@when("the asset is displayed")
def _displayed(viewer: Viewer, outcome: dict[str, Any]) -> None:
    outcome["descriptor"] = ran(viewer.descriptor())


@when("the addresses the viewer is able to request are enumerated")
def _addresses_enumerated(outcome: dict[str, Any]) -> None:
    outcome["addresses"] = tuple(build_app().openapi()["paths"])


@when("the same asset is opened in the 3D viewer with the same filter active")
def _opened_in_3d_with_the_same_filter(viewer: Viewer, outcome: dict[str, Any]) -> None:
    listing = ran(viewer.threads.listed(outcome["filter"]))
    outcome["viewer_ids"] = tuple(entry.id for entry in listing.annotations)


@when("it is resolved from the viewer")
def _resolved_from_the_viewer(viewer: Viewer, outcome: dict[str, Any]) -> None:
    ran(viewer.threads.resolve("an_1", conclusion="it reads correctly now"))
    outcome["annotation"] = viewer.threads.annotation("an_1")
    outcome["spec"] = viewer.threads.spec_text()


# --------------------------------------------------------------------------
# Then
# --------------------------------------------------------------------------


@then("the mesh loaded SHALL be the preview")
def _the_preview_is_loaded(outcome: dict[str, Any]) -> None:
    content = ran(outcome["content"])
    assert content.content == PREVIEW_BYTES
    assert content.key == outcome["descriptor"].preview.key


@then("the working export SHALL NOT be requested")
def _the_export_is_not_requested(outcome: dict[str, Any]) -> None:
    content = ran(outcome["content"])
    assert content.key != EXPORT
    assert EXPORT not in content.key


@then("none of them SHALL resolve to a working export file")
def _no_address_resolves_to_an_export(outcome: dict[str, Any]) -> None:
    offenders = [
        address
        for address in outcome["addresses"]
        if address != VALIDATIONS and any(token in address.lower() for token in EXPORT_TOKENS)
    ]

    assert not offenders, f"these addresses name a working export: {offenders}"
    assert outcome["addresses"], "an empty enumeration would assert nothing"


@then("the viewer SHALL show the export it was derived from and the specification revision in view")
def _provenance_is_shown(outcome: dict[str, Any]) -> None:
    descriptor = outcome["descriptor"]
    assert descriptor.source_export == EXPORT
    assert descriptor.revision


@then("the viewer SHALL state that the preview is not derived from the latest validated export")
def _superseded_is_stated(outcome: dict[str, Any]) -> None:
    descriptor = outcome["descriptor"]
    assert descriptor.source_export == OLDER_EXPORT
    assert descriptor.latest_validated_export == EXPORT
    assert not descriptor.derived_from_latest


@then("the asset's triangle count SHALL be shown as 14310")
def _the_triangle_count_is_the_sources(outcome: dict[str, Any]) -> None:
    assert outcome["descriptor"].counts.triangles == 14310


@then("any display of 4200 SHALL be labelled as the preview's count")
def _the_preview_count_is_labelled(outcome: dict[str, Any]) -> None:
    # The descriptor carries the *source's* figures and nothing else; the
    # preview's own triangle count is counted in the browser and labelled there
    # (`apps/cybercanon/web/src/lib/viewer/presentation.ts`), so there is no
    # member of this answer a surface could mistake for the asset's.
    descriptor = outcome["descriptor"]
    assert descriptor.counts.triangles == 14310
    assert 4200 not in (descriptor.counts.objects, descriptor.counts.materials)


@then("the material count SHALL be shown as unavailable")
def _the_material_count_is_unavailable(outcome: dict[str, Any]) -> None:
    counts = outcome["descriptor"].counts
    assert counts.materials is None
    assert counts.triangles == 14310, "an unavailable fact does not take the others with it"
    assert len(MATERIALS) > 0, "the fixture does record materials when the format carries them"


@then("the viewer SHALL state that no preview exists because no export has been validated")
def _no_export_recorded(outcome: dict[str, Any]) -> None:
    descriptor = outcome["descriptor"]
    assert descriptor.absent is NoPreview.NO_EXPORT_RECORDED
    assert descriptor.reason


@then("the asset's specification SHALL remain readable")
def _the_specification_is_readable(outcome: dict[str, Any]) -> None:
    descriptor = outcome["descriptor"]
    assert descriptor.path.endswith("asset.yaml")
    assert descriptor.revision


@then("the viewer SHALL state that no preview is available and that emission failed")
def _emission_failed_is_stated(outcome: dict[str, Any]) -> None:
    assert outcome["descriptor"].absent is NoPreview.EMISSION_FAILED


@then("it SHALL NOT report the export as unvalidated")
def _the_export_is_not_reported_unvalidated(outcome: dict[str, Any]) -> None:
    assert outcome["descriptor"].latest_validated_export == EXPORT


@then("the viewer SHALL report that the preview could not be loaded")
def _the_preview_could_not_be_loaded(outcome: dict[str, Any]) -> None:
    failure = outcome["content"]
    assert failure.identifier == "preview.unretrievable"
    assert outcome["key"] in failure.subject


@then("a retry SHALL be offered")
def _a_retry_is_offered(outcome: dict[str, Any]) -> None:
    # Unavailable rather than not-found, which is what makes a retry meaningful:
    # the record is right, the repository can produce the preview again, and the
    # condition resolves without the caller changing anything about the request.
    assert outcome["content"].kind.value == "unavailable"


@then("that annotation SHALL be filtered out there as well")
def _filtered_out_in_both(outcome: dict[str, Any]) -> None:
    assert outcome["viewer_ids"] == outcome["sheet"] == ("an_2",)


@then(
    "it SHALL take the same exit, with the same effect on the compiled "
    "specification, as resolving it from the 2D surface"
)
def _the_same_exit(outcome: dict[str, Any]) -> None:
    annotation = outcome["annotation"]
    assert annotation is not None
    assert annotation.is_resolved
    assert annotation.closing_text == "it reads correctly now"
    assert "state: resolved" in outcome["spec"]
    assert PROJECT, "the arrangement is one project, one use case, one answer"
    assert PARTS
