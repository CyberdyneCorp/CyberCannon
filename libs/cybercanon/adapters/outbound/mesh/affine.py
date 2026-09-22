"""4x4 affine arithmetic, in the one convention glTF stores matrices in.

`fbx_gltf` has to invert a bind matrix and compose two of them, and an FBX
records rotations as Euler angles in degrees while glTF records them as
quaternions. That is all this module does, and it does it literally: no library
is pulled in for four functions, and nothing here knows what a mesh is.

**The convention, stated once so no call site has to guess.** A matrix is four
*rows*, applied to a column vector (``v' = M @ v``) — the convention glTF uses.
:func:`from_flat` and :func:`to_flat` convert to and from the flat sixteen
glTF stores, which is column-major.

**Why an FBX matrix can be handed to :func:`from_flat` unchanged.** FBX composes
with row vectors (``v' = v @ M``) and stores row-major; glTF composes with column
vectors and stores column-major. The two differences are transposes of each
other and cancel exactly, which is why a cluster's sixteen doubles are read here
with no transpose and why translation sits at indices 12-14 in both.
"""

from __future__ import annotations

import math
from collections.abc import Sequence

Matrix = tuple[tuple[float, float, float, float], ...]
"""Four rows, applied to a column vector."""

Quaternion = tuple[float, float, float, float]
"""``(x, y, z, w)`` — glTF's order, not ``(w, x, y, z)``."""

IDENTITY: Matrix = (
    (1.0, 0.0, 0.0, 0.0),
    (0.0, 1.0, 0.0, 0.0),
    (0.0, 0.0, 1.0, 0.0),
    (0.0, 0.0, 0.0, 1.0),
)

IDENTITY_ROTATION: Quaternion = (0.0, 0.0, 0.0, 1.0)


class Singular(ValueError):
    """A matrix with no inverse — a bind pose that collapses an axis."""


def from_flat(values: Sequence[float]) -> Matrix:
    """The sixteen numbers glTF (and FBX) store, read as four rows."""
    if len(values) != 16:
        raise ValueError(f"a 4x4 matrix is sixteen numbers, not {len(values)}")
    return tuple(tuple(float(values[column * 4 + row]) for column in range(4)) for row in range(4))


def to_flat(matrix: Matrix) -> tuple[float, ...]:
    """Back to the flat sixteen, column-major, as glTF writes them."""
    return tuple(matrix[row][column] for column in range(4) for row in range(4))


def multiply(left: Matrix, right: Matrix) -> Matrix:
    """``left @ right`` — the transform `right` applies first."""
    return tuple(
        tuple(
            sum(left[row][term] * right[term][column] for term in range(4)) for column in range(4)
        )
        for row in range(4)
    )


def inverse(matrix: Matrix) -> Matrix:
    """A general 4x4 inverse by Gauss-Jordan elimination with partial pivoting.

    General rather than the affine shortcut because a bind matrix from a DCC is
    not guaranteed to be a rigid transform — non-uniform scale and shear both
    reach this, and a shortcut that assumed otherwise would silently deform the
    preview instead of refusing.
    """
    working = [list(row) + list(unit) for row, unit in zip(matrix, IDENTITY, strict=True)]
    for column in range(4):
        pivot = max(range(column, 4), key=lambda row: abs(working[row][column]))
        if abs(working[pivot][column]) < 1e-12:
            raise Singular("this matrix cannot be inverted")
        working[column], working[pivot] = working[pivot], working[column]
        _normalise(working[column], column)
        for row in range(4):
            if row != column:
                _eliminate(working[row], working[column], column)
    return tuple(tuple(row[4:]) for row in working)  # type: ignore[return-value]


def _normalise(row: list[float], column: int) -> None:
    divisor = row[column]
    for index in range(8):
        row[index] /= divisor


def _eliminate(row: list[float], pivot: list[float], column: int) -> None:
    factor = row[column]
    for index in range(8):
        row[index] -= factor * pivot[index]


def euler_to_quaternion(degrees: Sequence[float]) -> Quaternion:
    """FBX's default ``EulerXYZ`` rotation, as the quaternion glTF wants.

    ``EulerXYZ`` names the order the axes are applied in — X first — which
    composes as ``Rz @ Ry @ Rx`` for the column vectors this module uses, and so
    as ``qz * qy * qx``. Any other rotation order is a different rotation, which
    is why `fbx_gltf` refuses a file that declares one rather than converting it
    as if it were this one.
    """
    half = [math.radians(angle) / 2.0 for angle in degrees]
    sines = [math.sin(angle) for angle in half]
    cosines = [math.cos(angle) for angle in half]
    rotation: Quaternion = IDENTITY_ROTATION
    for axis in range(3):
        components = [0.0, 0.0, 0.0]
        components[axis] = sines[axis]
        rotation = _product((*components, cosines[axis]), rotation)
    return rotation


def placement(
    translation: Sequence[float], rotation: Sequence[float], scale: Sequence[float]
) -> Matrix:
    """``T @ R @ S`` — one node's local transform, from the three FBX records."""
    rotated = rotation_matrix(rotation)
    return tuple(
        tuple(
            rotated[row][column] * scale[column] if column < 3 else translation[row]
            for column in range(4)
        )
        if row < 3
        else (0.0, 0.0, 0.0, 1.0)
        for row in range(4)
    )


def rotation_matrix(degrees: Sequence[float]) -> Matrix:
    """The same ``EulerXYZ`` rotation as :func:`euler_to_quaternion`, as a matrix."""
    x, y, z, w = euler_to_quaternion(degrees)
    return (
        (1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w), 0.0),
        (2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w), 0.0),
        (2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y), 0.0),
        (0.0, 0.0, 0.0, 1.0),
    )


def _product(left: Quaternion, right: Quaternion) -> Quaternion:
    """Hamilton product, in ``(x, y, z, w)`` order."""
    lx, ly, lz, lw = left
    rx, ry, rz, rw = right
    return (
        lw * rx + lx * rw + ly * rz - lz * ry,
        lw * ry - lx * rz + ly * rw + lz * rx,
        lw * rz + lx * ry - ly * rx + lz * rw,
        lw * rw - lx * rx - ly * ry - lz * rz,
    )


def shortest_way_round(rotation: Quaternion, previous: Quaternion) -> Quaternion:
    """The same rotation, signed so a slerp from `previous` takes the short arc.

    ``q`` and ``-q`` are one rotation, and a viewer interpolating between two
    keys takes the shorter arc between the *stored* values — so a sign flip
    between consecutive keys sends a bone the long way round. Euler angles
    produce those flips routinely, which is why every converted key passes
    through here.
    """
    if sum(a * b for a, b in zip(rotation, previous, strict=True)) < 0.0:
        return tuple(-value for value in rotation)  # type: ignore[return-value]
    return rotation


__all__ = [
    "IDENTITY",
    "IDENTITY_ROTATION",
    "Matrix",
    "Quaternion",
    "Singular",
    "euler_to_quaternion",
    "from_flat",
    "inverse",
    "multiply",
    "placement",
    "rotation_matrix",
    "shortest_way_round",
    "to_flat",
]
