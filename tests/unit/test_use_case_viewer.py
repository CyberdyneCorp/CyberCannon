"""Group 2 — what the viewer needs to load an asset, answered with no renderer.

Every test here runs over an in-memory repository, a hand-built `MeshFacts` and
a preview that is twenty-five bytes of nothing. That is not a shortcut: D6's
whole claim is that the honest answers — which export, which revision, how many
triangles, which states have clips, which annotations are orphaned — are
answerable before a GPU is involved, and a suite that needed one would be
evidence the split had not happened.
"""

from __future__ import annotations

import pytest

from annotations_world import (
    AUTOMATION_ACTOR,
    DIRECTOR,
    RAFA_ACTOR,
    SCOUT,
    a_part_anchor,
    an_anchor,
)
from cybercanon.application.testing.outcomes import ran, refused
from cybercanon.application.use_cases.viewer import (
    NoPreview,
    PreviewUnretrievable,
    StateCoverage,
    coverage_of,
)
from cybercanon.domain.anchor_resolution import Resolution
from cybercanon.domain.design import State
from cybercanon.domain.mesh_facts import FactKind, MeshFacts, MeshFormat
from viewer_world import (
    ARM,
    EXPORT,
    OLDER_EXPORT,
    PARTS,
    PAULDRON,
    PREVIEW_BYTES,
    SHOULDER,
    WALK,
    a_spec_with_states,
    a_viewer,
    an_export,
)

pytestmark = pytest.mark.unit


# --------------------------------------------------------------------------
# 2.1 — the descriptor
# --------------------------------------------------------------------------


def test_the_descriptor_names_the_preview_the_export_and_the_revision() -> None:
    descriptor = ran(a_viewer().descriptor())

    assert descriptor.preview is not None
    assert descriptor.source_export == EXPORT
    assert descriptor.revision, "a read states the revision it was served from"


def test_the_descriptor_reports_the_source_export_counts() -> None:
    """*"the triangle count, the object count and the material count ... for the source."*"""
    descriptor = ran(a_viewer().descriptor())

    assert descriptor.counts.triangles == 14310
    assert descriptor.counts.objects == 3
    assert descriptor.counts.materials == 2


def test_an_unrecorded_count_is_unavailable_rather_than_zero() -> None:
    viewer = a_viewer()
    viewer.record_export(EXPORT, _without(FactKind.MATERIALS))

    counts = ran(viewer.descriptor()).counts

    assert counts.materials is None, "an unavailable fact has no substitute value"
    assert counts.triangles == 14310


def test_an_unreadable_export_leaves_the_counts_unavailable_and_the_asset_open() -> None:
    """A deleted export must not make the asset unopenable in the viewer."""
    viewer = a_viewer()
    viewer.mesh.add_unreadable(EXPORT, "the file is not there any more")

    descriptor = ran(viewer.descriptor())

    assert descriptor.counts.triangles is None
    assert descriptor.has_preview, "the preview is still stored and still loadable"


def test_the_descriptor_carries_the_part_and_clip_names() -> None:
    descriptor = ran(a_viewer().descriptor())

    assert descriptor.parts == PARTS
    assert descriptor.clips == (WALK,)


def test_a_preview_from_a_superseded_export_is_not_derived_from_the_latest() -> None:
    """*"the viewer SHALL state that the preview is not derived from the latest."*"""
    viewer = a_viewer()
    viewer.store_preview(OLDER_EXPORT)

    descriptor = ran(viewer.descriptor())

    assert descriptor.source_export == OLDER_EXPORT
    assert descriptor.latest_validated_export == EXPORT
    assert not descriptor.derived_from_latest


def test_a_current_preview_is_derived_from_the_latest() -> None:
    assert ran(a_viewer().descriptor()).derived_from_latest


def test_an_unknown_asset_is_not_found() -> None:
    assert refused(a_viewer().descriptor("no_such_asset")).kind.value == "not_found"


# --------------------------------------------------------------------------
# 2.6 — the three no-preview reasons, distinguishable
# --------------------------------------------------------------------------


def test_no_validated_export_reports_that_none_was_recorded() -> None:
    descriptor = ran(_viewer_without_validation().descriptor())

    assert descriptor.absent is NoPreview.NO_EXPORT_RECORDED
    assert not descriptor.has_preview


def test_a_failed_validation_is_not_reported_as_an_absent_export() -> None:
    viewer = a_viewer()
    viewer.record_validation(EXPORT, passed=False)

    descriptor = ran(viewer.descriptor())

    assert descriptor.absent is NoPreview.NO_SUCCESSFUL_VALIDATION


def test_a_failed_emission_is_not_reported_as_an_unvalidated_export() -> None:
    """*"it SHALL NOT report the export as unvalidated."*"""
    viewer = _viewer_without_validation()
    viewer.record_validation()

    descriptor = ran(viewer.descriptor())

    assert descriptor.absent is NoPreview.EMISSION_FAILED
    assert descriptor.latest_validated_export == EXPORT


def test_the_three_reasons_are_distinguishable_from_each_other() -> None:
    assert len({str(reason) for reason in NoPreview}) == 3


def test_the_descriptor_states_its_reason_in_words() -> None:
    assert ran(_viewer_without_validation().descriptor()).reason


# --------------------------------------------------------------------------
# 2.2 — state-to-clip coverage, consumed verbatim (D8)
# --------------------------------------------------------------------------


def test_a_two_state_asset_with_one_clip_reports_one_satisfied_and_one_gap() -> None:
    viewer = a_viewer(a_spec_with_states("walk", "fire"))

    coverage = ran(viewer.descriptor()).coverage

    assert [entry.state for entry in coverage.satisfied] == ["walk"]
    assert [entry.state for entry in coverage.missing] == ["fire"]
    assert coverage.unclaimed == ()


def test_a_missing_clip_is_listed_rather_than_omitted() -> None:
    viewer = a_viewer(a_spec_with_states("walk", "fire"))

    states = [entry.state for entry in ran(viewer.descriptor()).coverage.states]

    assert states == ["walk", "fire"]


def test_a_state_declared_unanimated_is_not_a_gap() -> None:
    viewer = a_viewer(a_spec_with_states("walk", unanimated=("destroyed",)))

    coverage = ran(viewer.descriptor()).coverage

    assert [entry.state for entry in coverage.unanimated] == ["destroyed"]
    assert coverage.missing == ()


def test_a_clip_no_state_requires_is_unclaimed_rather_than_an_error() -> None:
    viewer = a_viewer(a_spec_with_states("walk"))
    viewer.record_export(EXPORT, an_export(clips=(WALK, "A_mech_scout_test")))

    coverage = ran(viewer.descriptor()).coverage

    assert coverage.unclaimed == ("A_mech_scout_test",)
    assert [entry.state for entry in coverage.satisfied] == ["walk"]


def test_the_mapping_is_exact_and_never_by_similarity() -> None:
    """D8: a clip named one character off is a gap plus an unclaimed clip."""
    coverage = coverage_of(
        (State(name="fire"),), {"fire": "A_mech_scout_fire"}, ("A_mech_scout_Fire",)
    )

    assert coverage.states[0].coverage is StateCoverage.NO_CLIP
    assert coverage.unclaimed == ("A_mech_scout_Fire",)


def test_the_state_a_clip_satisfies_is_answerable_by_name() -> None:
    coverage = coverage_of((State(name="fire"),), {"fire": "A_x_fire"}, ("A_x_fire",))

    assert coverage.state_for("A_x_fire") == "fire"
    assert coverage.state_for("A_x_walk") == ""


# --------------------------------------------------------------------------
# 2.3 — resolutions, with no mesh loaded
# --------------------------------------------------------------------------


def test_resolutions_answer_for_every_mesh_anchored_annotation() -> None:
    viewer = a_viewer()
    ran(viewer.threads.create("an_1", anchor=a_part_anchor(SHOULDER)))
    ran(viewer.threads.create("an_2", anchor=a_part_anchor(ARM)))

    listing = ran(viewer.resolutions())

    assert [entry.id for entry in listing.entries] == ["an_1", "an_2"]
    assert all(entry.resolution.outcome is Resolution.RESOLVED for entry in listing.entries)


def test_a_two_dimensional_annotation_is_not_in_the_resolution_listing() -> None:
    viewer = a_viewer()
    ran(viewer.threads.create("an_1", anchor=an_anchor()))

    assert ran(viewer.resolutions()).entries == ()


def test_the_orphan_count_matches_the_domain_function() -> None:
    viewer = a_viewer()
    ran(viewer.threads.create("an_1", anchor=a_part_anchor(SHOULDER)))
    ran(viewer.threads.create("an_2", anchor=a_part_anchor(ARM)))

    listing = ran(viewer.resolutions(parts=(ARM,)))

    assert listing.orphan_count == 1
    assert [entry.id for entry in listing.orphaned] == ["an_1"]
    assert listing.orphaned[0].resolution.part == SHOULDER


def test_resolutions_run_with_no_mesh_and_no_blob_store() -> None:
    """The listing is a question about names, so it needs neither port."""
    viewer = a_viewer()
    ran(viewer.threads.create("an_1", anchor=a_part_anchor(SHOULDER)))
    viewer.mesh.add_unreadable(EXPORT, "no file")

    assert ran(viewer.resolutions()).orphan_count == 0


def test_a_missing_bone_is_reported_partial_when_the_bone_set_is_known() -> None:
    viewer = a_viewer()
    ran(viewer.threads.create("an_1", anchor=a_part_anchor(ARM).with_hints(None, None)))
    ran(viewer.threads.create("an_2", anchor=_bone_anchor()))

    listing = ran(viewer.resolutions(bones=("bone_upper_l",)))

    assert [entry.id for entry in listing.partial] == ["an_2"]


# --------------------------------------------------------------------------
# 2.4 and 2.5 — re-anchoring
# --------------------------------------------------------------------------


def test_re_anchoring_clears_the_orphan_state_and_keeps_the_thread() -> None:
    viewer = a_viewer()
    ran(viewer.threads.create("an_1", anchor=a_part_anchor(SHOULDER)))
    ran(viewer.threads.reply("an_1"))
    viewer.threads.parts = (PAULDRON,)

    ran(viewer.threads.reanchor("an_1", a_part_anchor(PAULDRON)))

    annotation = viewer.threads.annotation("an_1")
    assert annotation is not None
    assert annotation.durable_key == PAULDRON
    assert annotation.reply_count == 1
    assert annotation.is_open
    assert not ran(viewer.resolutions(parts=(PAULDRON,))).orphaned


def test_re_anchoring_leaves_the_identifier_the_text_and_the_state_alone() -> None:
    viewer = a_viewer()
    ran(
        viewer.threads.create(
            "an_1", anchor=a_part_anchor(SHOULDER), text="the pauldron reads flat"
        )
    )
    before = viewer.threads.annotation("an_1")
    viewer.threads.parts = (PAULDRON,)

    ran(viewer.threads.reanchor("an_1", a_part_anchor(PAULDRON)))

    after = viewer.threads.annotation("an_1")
    assert before is not None and after is not None
    assert (after.id, after.text, after.state) == (before.id, before.text, before.state)


def test_re_anchoring_names_the_person_and_the_instrument() -> None:
    """*"the recorded change SHALL name both that person and the caller."*"""
    viewer = a_viewer()
    ran(viewer.threads.create("an_1", anchor=a_part_anchor(SHOULDER)))
    viewer.threads.parts = (PAULDRON,)

    ran(viewer.threads.reanchor("an_1", a_part_anchor(PAULDRON), via=_agent()))

    annotation = viewer.threads.annotation("an_1")
    assert annotation is not None
    assert annotation.reanchored_by == RAFA_ACTOR.subject
    assert annotation.reanchored_at
    assert "blender-agent" in viewer.threads.messages()[-1]


def test_an_automated_caller_acting_on_its_own_is_refused() -> None:
    viewer = a_viewer()
    ran(viewer.threads.create("an_1", anchor=a_part_anchor(SHOULDER)))
    viewer.threads.parts = (PAULDRON,)

    outcome = viewer.threads.reanchor("an_1", a_part_anchor(PAULDRON), actor=AUTOMATION_ACTOR)

    assert refused(outcome).kind.value == "forbidden"
    assert "on its own" in refused(outcome).message


def test_nothing_re_anchors_on_its_own() -> None:
    """A plausible replacement part changes nothing until a person acts."""
    viewer = a_viewer()
    ran(viewer.threads.create("an_1", anchor=a_part_anchor(SHOULDER)))

    listing = ran(viewer.resolutions(parts=(PAULDRON,)))

    assert listing.orphan_count == 1
    assert viewer.threads.annotation("an_1").durable_key == SHOULDER  # type: ignore[union-attr]


def test_re_anchoring_cannot_promote() -> None:
    """2.5 — no promotion path through it; the exit state is not a parameter."""
    viewer = a_viewer()
    ran(viewer.threads.create("an_1", anchor=a_part_anchor(SHOULDER)))
    viewer.threads.parts = (PAULDRON,)

    ran(viewer.threads.reanchor("an_1", a_part_anchor(PAULDRON), actor=DIRECTOR))

    annotation = viewer.threads.annotation("an_1")
    assert annotation is not None and annotation.is_open
    assert "promot" not in viewer.threads.messages()[-1]


def test_re_anchoring_refuses_a_part_the_export_does_not_have() -> None:
    viewer = a_viewer()
    ran(viewer.threads.create("an_1", anchor=a_part_anchor(SHOULDER)))
    viewer.threads.parts = (PAULDRON,)

    assert (
        refused(viewer.threads.reanchor("an_1", a_part_anchor("SM_Invented"))).kind.value
        == "not_found"
    )


def test_re_anchoring_does_not_cross_anchor_forms() -> None:
    viewer = a_viewer()
    ran(viewer.threads.create("an_1", anchor=a_part_anchor(SHOULDER)))

    assert refused(viewer.threads.reanchor("an_1", an_anchor())).kind.value == "invalid"


# --------------------------------------------------------------------------
# 3.4 — the preview's bytes
# --------------------------------------------------------------------------


def test_the_preview_is_delivered_byte_identical() -> None:
    content = ran(a_viewer().preview_bytes())

    assert content.content == PREVIEW_BYTES
    assert content.size_bytes == len(PREVIEW_BYTES)
    assert content.content_type == "model/gltf-binary"


def test_a_missing_preview_blob_is_unretrievable_and_names_the_preview() -> None:
    viewer = a_viewer()
    key = ran(viewer.descriptor()).preview.key  # type: ignore[union-attr]
    viewer.blobs.lose_contents()

    refusal = refused(viewer.preview_bytes())

    assert refusal.identifier == PreviewUnretrievable.identifier
    assert key in refusal.subject, "the report names the preview it attempted"


def test_an_asset_with_no_preview_says_so_rather_than_returning_bytes() -> None:
    refusal = refused(_viewer_without_validation().preview_bytes())

    assert refusal.kind.value == "unavailable"
    assert refusal.identifier == PreviewUnretrievable.identifier
    assert str(NoPreview.NO_EXPORT_RECORDED) in refusal.message


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------


def _viewer_without_validation():
    """The ordinary world minus the outcome file — nothing has been validated."""
    from annotations_world import SCOUT_SPEC, a_world
    from viewer_world import Viewer

    viewer = Viewer(threads=a_world({SCOUT_SPEC: a_spec_with_states()}))
    viewer.record_export()
    return viewer


def _without(kind: FactKind) -> MeshFacts:
    """The same export with one fact its format could carry simply not recorded."""
    facts = an_export()
    return MeshFacts(
        source_format=MeshFormat.GLB,
        available=facts.available - {kind},
        triangles=facts.triangles,
        objects=facts.objects,
        clips=facts.clips,
    )


def _bone_anchor():
    from cybercanon.domain.annotations import Anchor3D

    return Anchor3D(part=ARM, bone="bone_forearm_l")


def _agent():
    from cybercanon.domain.identity import AgentId

    return AgentId("blender-agent")


def _unused() -> None:
    """Keeps the `SCOUT` import honest for readers grepping for the asset id."""
    assert SCOUT
