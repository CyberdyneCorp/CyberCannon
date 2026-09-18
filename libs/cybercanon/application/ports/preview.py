"""The preview value objects both preview ports speak in (D7).

A preview is produced by the mesh side and stored by the blob side, so the two
ports would otherwise import each other. :class:`PreviewMesh` is what the
emitter produced, :class:`StoredPreview` is the record that says which export it
came from, and :class:`PreviewUnavailable` is the one failure that is *not* an
:class:`~cybercanon.application.errors.OperationFailed`: a preview that cannot
be produced never changes a verdict, so it can never fail the operation.
"""

from __future__ import annotations

from dataclasses import dataclass

GLB_CONTENT_TYPE = "model/gltf-binary"


@dataclass(frozen=True)
class PreviewMesh:
    """A decimated, compressed mesh, and what it kept from the source.

    `parts`, `clips` and `bones` are what the emitter verified it carried over —
    `asset-preview` makes a preview that dropped them a *failure* rather than a
    silently degraded preview, and these are what a later surface checks that
    against.
    """

    content: bytes
    triangles: int
    parts: tuple[str, ...] = ()
    clips: tuple[str, ...] = ()
    bones: tuple[str, ...] = ()
    content_type: str = GLB_CONTENT_TYPE

    @property
    def size_bytes(self) -> int:
        return len(self.content)


@dataclass(frozen=True)
class StoredPreview:
    """A stored preview and the export it represents.

    The association is the requirement: a consumer has to be able to tell which
    export a preview came from and whether it is current.
    """

    key: str
    asset_id: str
    source_export: str
    size_bytes: int
    content_type: str = GLB_CONTENT_TYPE


class PreviewUnavailable(Exception):
    """No preview could be produced — deliberately not an `OperationFailed`.

    Raised when the emitter would have to drop clips, bones or named parts to
    reach its triangle target, and when the compressor is simply not installed.
    Either way the validation verdict stands untouched (D7).
    """


__all__ = [
    "GLB_CONTENT_TYPE",
    "PreviewMesh",
    "PreviewUnavailable",
    "StoredPreview",
]
