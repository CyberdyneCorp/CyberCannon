"""Group 1 — slots, image facts, limits, paths and the carry-forward rule.

Every test here is a constructed :class:`~cybercanon.domain.views.ImageFacts`
with no file on disk anywhere, which is D1's whole payoff restated for images:
the validator suite runs over hand-built `MeshFacts`, and this one runs over
hand-built image facts for exactly the same reason.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from cybercanon.domain.annotations import (
    Anchor2D,
    AnchorState,
    Annotation,
    AnnotationKind,
    AnnotationState,
)
from cybercanon.domain.revisions import ContentHash
from cybercanon.domain.views import (
    CANONICAL_SLOTS,
    DEFAULT_FORMATS,
    DEFAULT_MAX_BYTES,
    DEFAULT_MAX_DIMENSION,
    DIMENSION_EXCEEDED,
    FORMAT_UNSUPPORTED,
    SIZE_EXCEEDED,
    ConceptView,
    ImageFacts,
    IngestionLimits,
    InvalidSlotName,
    ViewRevision,
    ViewSlot,
    asset_dir_of,
    carry_forward,
    check_image,
    concept_dir,
    is_valid_slot,
    marked_current,
    megabytes,
    replacement,
    slot_of,
    view_path,
)

pytestmark = pytest.mark.unit

MEGABYTE = 1024 * 1024
NOON = datetime(2026, 9, 22, 12, 0, tzinfo=UTC)


def facts(
    image_format: str = "png",
    width: int = 1024,
    height: int = 768,
    byte_size: int = 2 * MEGABYTE,
    body: bytes = b"front",
    alpha: bool = False,
) -> ImageFacts:
    return ImageFacts(
        format=image_format,
        width=width,
        height=height,
        byte_size=byte_size,
        content_hash=ContentHash.of(body),
        has_alpha=alpha,
    )


# --------------------------------------------------------------------------
# 1.1 — slots
# --------------------------------------------------------------------------


@pytest.mark.parametrize("name", CANONICAL_SLOTS)
def test_the_three_canonical_slots_are_canonical(name: str) -> None:
    assert ViewSlot(name).is_canonical


@pytest.mark.parametrize("name", ["three_quarter_left", "a", "0", "left_3_4", "x" * 32, "slot_1"])
def test_a_well_formed_arbitrary_name_is_a_slot(name: str) -> None:
    """*"Any other name ... SHALL be accepted as an arbitrary named view."*"""
    slot = ViewSlot(name)

    assert str(slot) == name
    assert not slot.is_canonical


@pytest.mark.parametrize(
    "name",
    ["Front View!", "Front", "front view", "_front", "front-view", "", "x" * 33, "frônt"],
)
def test_a_name_that_is_not_a_slot_is_refused_naming_it(name: str) -> None:
    with pytest.raises(InvalidSlotName) as refusal:
        ViewSlot(name)

    assert repr(name) in str(refusal.value)
    assert not is_valid_slot(name)


def test_a_thirty_three_character_name_is_one_character_too_long() -> None:
    """At the limit is accepted; past it is not. The boundary, both sides."""
    assert is_valid_slot("x" * 32)
    assert not is_valid_slot("x" * 33)


# --------------------------------------------------------------------------
# 1.2 — image facts
# --------------------------------------------------------------------------


def test_image_facts_are_frozen_and_carry_the_six_fields() -> None:
    read = facts(alpha=True)

    assert (read.format, read.width, read.height, read.has_alpha) == ("png", 1024, 768, True)
    assert read.byte_size == 2 * MEGABYTE
    assert read.content_hash == ContentHash.of(b"front")
    with pytest.raises(AttributeError):
        read.width = 5  # type: ignore[misc]


def test_the_aspect_ratio_is_computed_in_the_domain() -> None:
    """D6 depends on it, so the domain computes it rather than being told it."""
    assert facts(width=1024, height=768).aspect == pytest.approx(4 / 3)
    assert facts(width=1000, height=1000).dimensions == "1000x1000"
    assert facts(width=12000, height=4000).largest_dimension == 12000


def test_an_image_with_no_pixels_is_not_an_image() -> None:
    with pytest.raises(ValueError, match="positive"):
        facts(width=0)


def test_the_domain_imports_no_third_party_package(repo_root) -> None:
    """The stdlib-only contract, asserted over this module's own source too.

    `lint-imports` enforces it for the package; this states it where the module
    is, so a `from PIL import Image` added in a hurry fails a test that names
    the file rather than only a contract that names the package.
    """
    import ast

    source = (repo_root / "libs" / "cybercanon" / "domain" / "views.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    roots = {
        (node.module or "").split(".")[0]
        if isinstance(node, ast.ImportFrom)
        else alias.name.split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.Import | ast.ImportFrom)
        for alias in node.names
    }

    assert roots <= {"__future__", "re", "dataclasses", "datetime", "cybercanon"}, roots


# --------------------------------------------------------------------------
# 1.3 — limits
# --------------------------------------------------------------------------


def test_limits_declared_by_nobody_are_the_defaults() -> None:
    limits = IngestionLimits.declared()

    assert limits.accepted_formats == DEFAULT_FORMATS
    assert limits.max_bytes == DEFAULT_MAX_BYTES
    assert limits.max_dimension == DEFAULT_MAX_DIMENSION


def test_each_limit_is_overridable_on_its_own() -> None:
    """A project raising the pixel ceiling should not have to restate the formats."""
    limits = IngestionLimits.declared(max_dimension=16384)

    assert limits.max_dimension == 16384
    assert limits.accepted_formats == DEFAULT_FORMATS
    assert limits.max_bytes == DEFAULT_MAX_BYTES


def test_a_declared_empty_format_set_is_a_declaration_not_an_absence() -> None:
    """``None`` means *declared nothing*; an empty tuple means *accepts nothing*."""
    assert IngestionLimits.declared(accepted_formats=()).accepted_formats == ()
    assert IngestionLimits.declared(accepted_formats=None).accepted_formats == DEFAULT_FORMATS


# --------------------------------------------------------------------------
# 1.4 — the acceptance rules
# --------------------------------------------------------------------------


def test_an_accepted_image_produces_no_violation() -> None:
    assert check_image(facts(), IngestionLimits()) == ()


def test_an_unsupported_format_names_it_and_the_accepted_set() -> None:
    (violation,) = check_image(facts(image_format="tiff"), IngestionLimits(), "front.png")

    assert violation.rule_id == FORMAT_UNSUPPORTED
    assert "TIFF" in violation.message
    assert "png, jpeg, webp" in violation.message


def test_an_oversized_file_states_the_observed_and_the_allowed() -> None:
    limits = IngestionLimits(max_bytes=25 * MEGABYTE)

    (violation,) = check_image(facts(byte_size=41 * MEGABYTE), limits, "front.png")

    assert violation.rule_id == SIZE_EXCEEDED
    assert violation.observed == "41 MB"
    assert violation.expected == "25 MB"


def test_oversized_dimensions_state_the_observed_width_and_the_maximum() -> None:
    limits = IngestionLimits(max_dimension=8192)

    (violation,) = check_image(facts(width=12000, height=4000), limits, "front.png")

    assert violation.rule_id == DIMENSION_EXCEEDED
    assert violation.observed == "12000x4000"
    assert violation.expected == "8192"


def test_exactly_at_each_limit_is_accepted() -> None:
    """*"An image at exactly the configured limit SHALL be accepted."*"""
    limits = IngestionLimits(max_bytes=25 * MEGABYTE, max_dimension=8192)
    at_the_limit = facts(width=8192, height=8192, byte_size=25 * MEGABYTE)

    assert check_image(at_the_limit, limits) == ()


def test_one_under_each_limit_is_accepted_and_one_over_is_not() -> None:
    limits = IngestionLimits(max_bytes=100, max_dimension=10)

    assert check_image(facts(width=9, height=9, byte_size=99), limits) == ()
    assert len(check_image(facts(width=11, height=11, byte_size=101), limits)) == 2


def test_every_reason_is_reported_rather_than_the_first() -> None:
    limits = IngestionLimits(max_bytes=MEGABYTE, max_dimension=100)
    bad = facts(image_format="tiff", width=200, height=200, byte_size=9 * MEGABYTE)

    found = check_image(bad, limits)

    assert {violation.rule_id for violation in found} == {
        FORMAT_UNSUPPORTED,
        SIZE_EXCEEDED,
        DIMENSION_EXCEEDED,
    }


def test_megabytes_render_as_a_person_reads_them() -> None:
    assert megabytes(41 * MEGABYTE) == "41 MB"
    assert megabytes(25 * MEGABYTE) == "25 MB"
    assert megabytes(MEGABYTE // 2) == "0.5 MB"


# --------------------------------------------------------------------------
# 1.5 — a view and its revisions
# --------------------------------------------------------------------------


def a_revision(identifier: str, removed: bool = False) -> ViewRevision:
    return ViewRevision(
        revision=identifier,
        author="Rafa <rafa@cyberdyne.com>",
        at=NOON,
        content_hash=None if removed else ContentHash.of(identifier.encode()),
        width=1024,
        height=768,
        byte_size=2048,
        removed=removed,
    )


def test_exactly_one_of_three_revisions_is_current() -> None:
    listed = marked_current((a_revision("r3"), a_revision("r2"), a_revision("r1")))

    assert [entry.is_current for entry in listed] == [True, False, False]
    view = ConceptView(asset_id="mech_scout", slot=ViewSlot("front"), path="", revisions=listed)
    assert view.current is not None and view.current.revision == "r3"


def test_a_removed_view_has_no_current_revision() -> None:
    listed = marked_current((a_revision("r3", removed=True), a_revision("r2"), a_revision("r1")))

    view = ConceptView(asset_id="mech_scout", slot=ViewSlot("front"), path="", revisions=listed)

    assert view.current is None
    assert view.is_removed
    assert [entry.is_current for entry in listed] == [False, False, False]


def test_an_empty_history_marks_nothing() -> None:
    assert marked_current(()) == ()


def test_a_view_finds_a_revision_by_identifier_and_answers_nothing_for_another() -> None:
    view = ConceptView(
        asset_id="mech_scout",
        slot=ViewSlot("front"),
        path="",
        revisions=marked_current((a_revision("r2"), a_revision("r1"))),
    )

    assert view.revision("r1") is not None
    assert view.revision("r9") is None


def test_a_truncated_history_says_so() -> None:
    view = ConceptView(
        asset_id="mech_scout", slot=ViewSlot("front"), path="", truncated_before="r1"
    )

    assert not view.is_complete


# --------------------------------------------------------------------------
# 1.6 — the deterministic path
# --------------------------------------------------------------------------


def test_the_same_slot_always_yields_the_same_path() -> None:
    first = view_path("characters/mech_scout", ViewSlot("front"), "png")
    second = view_path("characters/mech_scout", ViewSlot("front"), "png")

    assert first == second == "characters/mech_scout/concept/front.png"


def test_jpeg_is_written_as_jpg_and_the_format_stays_jpeg() -> None:
    assert view_path("props/crate", ViewSlot("side"), "jpeg") == "props/crate/concept/side.jpg"


def test_a_format_change_is_a_rename_rather_than_an_unrelated_path() -> None:
    """D4: history follows the slot, so the old path is removed in the same commit."""
    current = view_path("characters/mech_scout", ViewSlot("front"), "png")
    replaced = view_path("characters/mech_scout", ViewSlot("front"), "webp")

    removed, written = replacement(current, replaced)

    assert removed == current
    assert written == replaced


def test_a_replacement_in_the_same_format_removes_nothing() -> None:
    path = view_path("characters/mech_scout", ViewSlot("front"), "png")

    assert replacement(path, path) == (None, path)
    assert replacement(None, path) == (None, path)


def test_a_view_path_reads_back_to_its_slot_and_its_asset_directory() -> None:
    """What makes a project's views reconstructible by walking the repository (D3)."""
    path = view_path("characters/mech_scout", ViewSlot("three_quarter_left"), "png")

    found = slot_of(path)

    assert found is not None and str(found) == "three_quarter_left"
    assert asset_dir_of(path) == "characters/mech_scout"
    assert concept_dir("characters/mech_scout") == "characters/mech_scout/concept"


@pytest.mark.parametrize(
    "path",
    [
        "characters/mech_scout/asset.yaml",
        "characters/mech_scout/exports/front.png",
        "concept",
        "characters/mech_scout/concept/Front.png",
        "characters/mech_scout/concept/front",
    ],
)
def test_a_path_that_is_not_a_view_reads_back_as_none(path: str) -> None:
    assert slot_of(path) is None


def test_a_view_at_the_repository_root_still_reads_back() -> None:
    assert slot_of("concept/front.png") is not None


# --------------------------------------------------------------------------
# 1.7 — carry-forward (D6)
# --------------------------------------------------------------------------


def test_an_equal_aspect_ratio_carries() -> None:
    before = facts(width=1024, height=768)
    after = facts(width=2048, height=1536, body=b"bigger")

    assert carry_forward(before, after) is AnchorState.CARRIED


def test_a_ratio_within_the_tolerance_carries() -> None:
    """A rounding difference between exporters is not a crop."""
    before = facts(width=1000, height=750)
    after = facts(width=1001, height=750, body=b"rounded")

    assert carry_forward(before, after) is AnchorState.CARRIED


def test_a_crop_orphans() -> None:
    before = facts(width=1024, height=768)
    after = facts(width=768, height=768, body=b"cropped")

    assert carry_forward(before, after) is AnchorState.ORPHANED


def test_the_tolerance_is_a_parameter_rather_than_a_constant_in_the_rule() -> None:
    before = facts(width=100, height=100)
    after = facts(width=105, height=100, body=b"slightly wider")

    assert carry_forward(before, after) is AnchorState.ORPHANED
    assert carry_forward(before, after, tolerance=0.1) is AnchorState.CARRIED


# --------------------------------------------------------------------------
# 1.8 — the anchor state is not an exit (D7)
# --------------------------------------------------------------------------


def an_annotation(state: AnnotationState = AnnotationState.OPEN) -> Annotation:
    return Annotation(
        id="ann-1",
        author="rafa",
        kind=AnnotationKind.ART_DIRECTION,
        text="the pauldron reads as a backpack",
        target=Anchor2D(view="front", u=0.4, v=0.6),
        state=state,
        authored_against="r1",
    )


def test_an_anchor_state_renders_as_the_word_a_surface_shows() -> None:
    assert str(AnchorState.CARRIED) == "carried"
    assert str(AnchorState.ORPHANED) == "orphaned"


def test_an_annotation_starts_carried_against_the_revision_it_was_authored_on() -> None:
    annotation = an_annotation()

    assert annotation.anchor_state is AnchorState.CARRIED
    assert annotation.authored_against == "r1"
    assert not annotation.is_orphaned


def test_orphaning_leaves_the_exit_state_and_the_authoring_revision_alone() -> None:
    """D7: the anchor state is independent of the exit state, and of nothing else."""
    orphaned = an_annotation().orphaned_by()

    assert orphaned.anchor_state is AnchorState.ORPHANED
    assert orphaned.state is AnnotationState.OPEN
    assert orphaned.is_open
    assert orphaned.authored_against == "r1"


def test_carrying_moves_the_authoring_revision_and_nothing_else() -> None:
    carried = an_annotation().carried_to("r2")

    assert carried.anchor_state is AnchorState.CARRIED
    assert carried.authored_against == "r2"
    assert carried.text == an_annotation().text
    assert carried.state is AnnotationState.OPEN


def test_neither_anchor_move_can_write_an_exit_state() -> None:
    """Asserted over the signatures: neither method takes a state to write."""
    import inspect

    for method in (Annotation.carried_to, Annotation.orphaned_by):
        parameters = set(inspect.signature(method).parameters) - {"self"}
        assert "state" not in parameters


def test_re_anchoring_records_who_and_when_and_changes_neither_text_nor_exit() -> None:
    orphaned = an_annotation().orphaned_by()

    reanchored = orphaned.reanchored(
        Anchor2D(view="front", u=0.2, v=0.3), revision="r3", by="ana", at="2026-09-22T12:00:00Z"
    )

    assert reanchored.anchor_state is AnchorState.CARRIED
    assert reanchored.authored_against == "r3"
    assert reanchored.reanchored_by == "ana"
    assert reanchored.reanchored_at == "2026-09-22T12:00:00Z"
    assert reanchored.text == orphaned.text
    assert reanchored.state is AnnotationState.OPEN


def test_an_orphan_that_was_promoted_stays_promoted() -> None:
    """The two axes are independent in both directions, not only in one."""
    promoted = an_annotation(AnnotationState.PROMOTED).orphaned_by()

    assert promoted.state is AnnotationState.PROMOTED
    assert promoted.is_orphaned
