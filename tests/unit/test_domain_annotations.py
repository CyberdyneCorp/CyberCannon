"""Task 2.3 — anchors are durable by construction, and annotations have two exits.

The load-bearing test here is `test_no_anchor_type_can_carry_a_triangle_index`.
`asset-spec` forbids storing a triangle index or barycentric coordinate as an
anchor, because those are precise and worthless the moment the mesh is
re-exported — exactly when the feedback has to survive. That is not a comment to
respect, so this asserts it over the fields of every type reachable from an
anchor, and over `ANCHOR_TYPES` rather than a hand-written list, so a new anchor
type is covered the day it is added.
"""

from __future__ import annotations

import dataclasses
import typing

import pytest

from cybercanon.domain.annotations import (
    ANCHOR_TYPES,
    Anchor2D,
    Anchor3D,
    Annotation,
    AnnotationKind,
    AnnotationState,
    Camera,
    open_annotations,
)

FORBIDDEN_IN_A_FIELD_NAME = (
    "triangle",
    "tri_index",
    "triindex",
    "face_index",
    "faceindex",
    "barycentric",
    "bary",
    "uvw",
    "vertex_index",
)

ANCHOR_2D_FIELDS = {"view", "u", "v"}
ANCHOR_3D_FIELDS = {"part", "bone", "point", "normal", "camera"}

PART = "SM_MechScout_Shoulder_L"


def types_reachable_from(root: type) -> set[type]:
    """Every dataclass an anchor can hold, directly or through another one."""
    seen: set[type] = set()
    pending = [root]
    while pending:
        current = pending.pop()
        if current in seen or not dataclasses.is_dataclass(current):
            continue
        seen.add(current)
        pending.extend(_referenced_types(current))
    return seen


def _referenced_types(owner: type) -> list[type]:
    hints = typing.get_type_hints(owner)
    return [
        argument
        for hint in hints.values()
        for argument in (hint, *typing.get_args(hint))
        if isinstance(argument, type)
    ]


def field_names_of(owner: type) -> set[str]:
    return {field.name for field in dataclasses.fields(owner)}


# --------------------------------------------------------------------------
# The durable-anchoring rule, asserted rather than documented
# --------------------------------------------------------------------------


@pytest.mark.parametrize("anchor_type", ANCHOR_TYPES, ids=lambda item: item.__name__)
def test_no_anchor_type_can_carry_a_triangle_index(anchor_type: type) -> None:
    offenders = {
        f"{owner.__name__}.{name}"
        for owner in types_reachable_from(anchor_type)
        for name in field_names_of(owner)
        if any(token in name.lower() for token in FORBIDDEN_IN_A_FIELD_NAME)
    }

    assert not offenders, (
        f"{sorted(offenders)} store mesh topology as an anchor. A triangle index "
        "or barycentric coordinate does not survive a re-export, which is "
        "precisely when the annotation has to (asset-spec)."
    )


def test_the_anchor_field_sets_are_exactly_the_specified_ones() -> None:
    """Closes the loophole of a topology field under an innocent name."""
    assert field_names_of(Anchor2D) == ANCHOR_2D_FIELDS
    assert field_names_of(Anchor3D) == ANCHOR_3D_FIELDS


def test_both_anchor_forms_are_anchor_types() -> None:
    assert set(ANCHOR_TYPES) == {Anchor2D, Anchor3D}


# --------------------------------------------------------------------------
# What the durable key is, and what the hints are not
# --------------------------------------------------------------------------


def test_the_named_part_is_the_identity_of_a_3d_anchor() -> None:
    anchor = Anchor3D(part=PART, point=(0.1, 2.0, 0.3), normal=(0.0, 1.0, 0.0))

    assert anchor.durable_key == PART


def test_moving_the_hints_does_not_change_what_the_anchor_identifies() -> None:
    """A retopology moves every vertex; the part name is what has to survive."""
    anchor = Anchor3D(part=PART, point=(0.1, 2.0, 0.3), normal=(0.0, 1.0, 0.0))

    remeshed = anchor.with_hints(point=(0.4, 2.1, 0.2), normal=(0.1, 0.9, 0.0))

    assert remeshed.durable_key == anchor.durable_key
    assert remeshed.part == PART
    assert remeshed.point != anchor.point


def test_a_3d_anchor_needs_nothing_but_the_part() -> None:
    anchor = Anchor3D(part=PART)

    assert (anchor.bone, anchor.point, anchor.normal, anchor.camera) == (None, None, None, None)


def test_a_3d_anchor_can_record_the_bone_and_the_viewing_angle() -> None:
    camera = Camera(position=(0.0, 1.5, 4.0), target=(0.0, 1.5, 0.0), fov_deg=45.0)

    anchor = Anchor3D(part=PART, bone="upperarm_l", camera=camera)

    assert anchor.bone == "upperarm_l"
    assert anchor.camera == camera


def test_the_named_view_is_the_identity_of_a_2d_anchor() -> None:
    assert Anchor2D(view="front", u=0.25, v=0.75).durable_key == "front"


@pytest.mark.parametrize(("u", "v"), [(-0.1, 0.5), (1.1, 0.5), (0.5, -0.01), (0.5, 1.5)])
def test_a_2d_anchor_outside_the_normalized_range_is_refused(u: float, v: float) -> None:
    with pytest.raises(ValueError, match="normalized range"):
        Anchor2D(view="front", u=u, v=v)


# --------------------------------------------------------------------------
# Two exits, and only two
# --------------------------------------------------------------------------


def an_annotation(**overrides: object) -> Annotation:
    fields: dict[str, object] = {
        "id": "a1",
        "author": "ana",
        "kind": AnnotationKind.ART_DIRECTION,
        "text": "the lens glow is always emissive",
        "target": Anchor3D(part=PART),
    }
    fields.update(overrides)
    return Annotation(**fields)  # type: ignore[arg-type]


def test_an_annotation_starts_open() -> None:
    annotation = an_annotation()

    assert annotation.is_open
    assert not annotation.has_exited
    assert annotation.state is AnnotationState.OPEN


def test_promotion_retires_the_annotation() -> None:
    promoted = an_annotation().promoted()

    assert promoted.state is AnnotationState.PROMOTED
    assert not promoted.is_open
    assert promoted.has_exited


def test_resolution_takes_the_other_exit() -> None:
    resolved = an_annotation().resolved()

    assert resolved.state is AnnotationState.RESOLVED
    assert not resolved.is_open


def test_there_are_exactly_two_exits_and_one_non_exit() -> None:
    assert {state.value for state in AnnotationState} == {"open", "promoted", "resolved"}


def test_the_three_annotation_kinds_are_the_three_disciplines() -> None:
    assert {kind.value for kind in AnnotationKind} == {"art-direction", "technical", "design"}
    assert str(AnnotationKind.ART_DIRECTION) == "art-direction"
    assert str(AnnotationState.PROMOTED) == "promoted"


def test_an_annotation_reports_what_it_is_attached_to() -> None:
    assert an_annotation().durable_key == PART
    assert an_annotation(target=Anchor2D(view="front", u=0.1, v=0.2)).durable_key == "front"


def test_only_open_annotations_reach_the_compiled_briefing() -> None:
    annotations = (
        an_annotation(id="open"),
        an_annotation(id="promoted").promoted(),
        an_annotation(id="resolved").resolved(),
    )

    assert [item.id for item in open_annotations(annotations)] == ["open"]


def test_an_annotation_is_frozen() -> None:
    with pytest.raises(dataclasses.FrozenInstanceError):
        an_annotation().state = AnnotationState.RESOLVED  # type: ignore[misc]
