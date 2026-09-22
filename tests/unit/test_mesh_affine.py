"""The conventions `fbx_gltf` composes bind matrices in, asserted on their own.

Everything in this module is a convention rather than a calculation — which
storage order, which rotation order, which side a matrix multiplies on — and a
convention that is wrong produces a preview that renders *somewhere*, just not
where the export put it. That failure is invisible in a part list and obvious
only to someone looking at the viewer, so the conventions are pinned here with
numbers small enough to check by hand.

The Euler cases were taken from Blender's own `mathutils.Euler(..., "XYZ")`,
which is the implementation FBX's `EulerXYZ` has to agree with; the cross-check
that keeps them honest against a real export lives in
`tests/integration/test_fbx_against_blender.py`.
"""

from __future__ import annotations

import math

import pytest

from cybercanon.adapters.outbound.mesh import affine

pytestmark = pytest.mark.unit

TRANSLATION_INDICES = (12, 13, 14)
"""Where a translation sits in the flat sixteen — the same slots in FBX and glTF."""


def _apply(matrix: affine.Matrix, point: tuple[float, float, float]) -> tuple[float, ...]:
    column = (*point, 1.0)
    return tuple(
        round(sum(matrix[row][term] * column[term] for term in range(4)), 6) for row in range(3)
    )


# --------------------------------------------------------------------------
# Storage
# --------------------------------------------------------------------------


def test_a_flat_matrix_round_trips() -> None:
    flat = tuple(float(value) for value in range(16))

    assert affine.to_flat(affine.from_flat(flat)) == flat


def test_a_translation_is_read_out_of_the_last_three_of_the_flat_sixteen() -> None:
    """The one property that lets an FBX matrix be read as a glTF one unchanged.

    FBX composes with row vectors and stores row-major, glTF with column vectors
    and column-major. The two differences are transposes and cancel, so a
    cluster's sixteen doubles need no transpose — and this is what says so.
    """
    flat = [0.0] * 16
    for index, value in zip(TRANSLATION_INDICES, (2.0, 3.0, 4.0), strict=True):
        flat[index] = value
    flat[0] = flat[5] = flat[10] = flat[15] = 1.0

    assert _apply(affine.from_flat(flat), (0.0, 0.0, 0.0)) == (2.0, 3.0, 4.0)


# --------------------------------------------------------------------------
# Arithmetic
# --------------------------------------------------------------------------


def test_multiplying_applies_the_right_hand_transform_first() -> None:
    """`multiply(a, b)` is `a @ b`, which is the order every bind matrix uses."""
    move = affine.placement((10.0, 0.0, 0.0), (0.0, 0.0, 0.0), (1.0, 1.0, 1.0))
    grow = affine.placement((0.0, 0.0, 0.0), (0.0, 0.0, 0.0), (2.0, 2.0, 2.0))

    assert _apply(affine.multiply(move, grow), (1.0, 0.0, 0.0)) == (12.0, 0.0, 0.0)
    assert _apply(affine.multiply(grow, move), (1.0, 0.0, 0.0)) == (22.0, 0.0, 0.0)


def test_a_matrix_times_its_inverse_is_the_identity() -> None:
    matrix = affine.placement((1.0, -2.0, 3.0), (10.0, 20.0, 30.0), (2.0, 0.5, 4.0))

    product = affine.multiply(matrix, affine.inverse(matrix))

    assert all(
        abs(product[row][column] - affine.IDENTITY[row][column]) < 1e-9
        for row in range(4)
        for column in range(4)
    )


def test_a_collapsed_bind_pose_is_refused_rather_than_inverted() -> None:
    """A zero scale has no inverse, and a preview built from one is nonsense."""
    with pytest.raises(affine.Singular):
        affine.inverse(affine.placement((0.0, 0.0, 0.0), (0.0, 0.0, 0.0), (1.0, 0.0, 1.0)))


# --------------------------------------------------------------------------
# Rotation
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("degrees", "expected"),
    [
        ((30.0, 0.0, 0.0), (0.258819, 0.0, 0.0, 0.965926)),
        ((0.0, 45.0, 0.0), (0.0, 0.382683, 0.0, 0.92388)),
        ((0.0, 0.0, 60.0), (0.0, 0.0, 0.5, 0.866025)),
        ((-90.0, 0.0, 0.0), (-0.707107, 0.0, 0.0, 0.707107)),
        ((12.0, 34.0, 56.0), (-0.048248, 0.303664, 0.419515, 0.854089)),
    ],
)
def test_euler_xyz_matches_the_rotation_a_dcc_means_by_it(
    degrees: tuple[float, float, float], expected: tuple[float, float, float, float]
) -> None:
    """Values from Blender's `mathutils.Euler(..., "XYZ").to_quaternion()`."""
    assert affine.euler_to_quaternion(degrees) == pytest.approx(expected, abs=1e-6)


def test_the_axes_are_applied_x_first() -> None:
    """The order is the whole content of `EulerXYZ`, so it is asserted as a motion.

    Applied X first, a point on +Y is tipped onto +Z and then swung onto -X.
    Applied Z first it would end up somewhere else entirely, which is what a
    converter that assumed the wrong order would render.
    """
    rotation = affine.rotation_matrix((90.0, 0.0, 90.0))

    assert _apply(rotation, (0.0, 1.0, 0.0)) == (0.0, 0.0, 1.0)


def test_a_rotation_matrix_is_the_quaternion_it_reports() -> None:
    degrees = (12.0, 34.0, 56.0)
    point = (0.3, -0.7, 1.1)

    x, y, z, w = affine.euler_to_quaternion(degrees)
    rotated = _apply(affine.rotation_matrix(degrees), point)

    # q * (p, 0) * conjugate(q), written out rather than looped.
    px, py, pz = point
    tx, ty, tz = 2 * (y * pz - z * py), 2 * (z * px - x * pz), 2 * (x * py - y * px)
    by_quaternion = (
        px + w * tx + y * tz - z * ty,
        py + w * ty + z * tx - x * tz,
        pz + w * tz + x * ty - y * tx,
    )
    assert rotated == pytest.approx(by_quaternion, abs=1e-6)


def test_a_key_is_signed_to_take_the_short_way_round() -> None:
    """Euler keys flip sign routinely; a viewer slerps the stored values.

    Without this, two keys a few degrees apart can be stored as opposite
    quaternions and the bone spins most of the way round the long side.
    """
    turning = affine.euler_to_quaternion((0.0, 0.0, 170.0))
    past = affine.euler_to_quaternion((0.0, 0.0, -170.0))

    signed = affine.shortest_way_round(past, turning)

    assert sum(a * b for a, b in zip(past, turning, strict=True)) < 0.0, "the case is a flip"
    assert sum(a * b for a, b in zip(signed, turning, strict=True)) > 0.0
    assert signed == pytest.approx(tuple(-value for value in past), abs=1e-9)


def test_placement_composes_translation_rotation_and_scale_in_that_order() -> None:
    """`T @ R @ S`: scaled first, then rotated, then moved — a node's own matrix."""
    matrix = affine.placement((0.0, 0.0, 5.0), (0.0, 0.0, 90.0), (2.0, 2.0, 2.0))

    assert _apply(matrix, (1.0, 0.0, 0.0)) == (0.0, 2.0, 5.0)
    assert math.isclose(affine.to_flat(matrix)[14], 5.0)
