"""The in-memory `MeshInspector` — facts handed to it, never read from a file.

This is where D1 pays off twice. The domain suite already runs over hand-built
`MeshFacts`; this fake extends that to the *use case*, so validate_export can be
tested end to end — discovery, merge, extraction, rules, preview — with no
binary fixture in git and no extraction library installed.

What it deliberately can model, because the use case must handle each:

* an export it can read (`add`);
* an export it cannot (`add_unreadable`) — an operation failure, never a pass;
* an export whose format has no row in the matrix (`add_unsupported`) — refused
  by name (D13);
* an export whose preview cannot be produced (`fail_preview`) — the guarded path
  of D7, whose whole point is that it changes nothing about the verdict.

It also records what it was asked, so "the preview came from the same read" is
an assertion rather than a hope.
"""

from __future__ import annotations

from cybercanon.application.ports.mesh_inspector import (
    InspectedMesh,
    MeshUnreadable,
    SourceVisuals,
    UnsupportedExport,
)
from cybercanon.application.ports.preview import PreviewMesh, PreviewUnavailable
from cybercanon.domain.mesh_facts import MeshFacts

DECIMATION_DIVISOR = 4
"""Deliberately dumb, exactly like the real emitter's fixed fraction (D7)."""


class InMemoryMeshInspector:
    """Exports registered by path, each with the facts it yields."""

    def __init__(self) -> None:
        self._facts: dict[str, MeshFacts] = {}
        self._visuals: dict[str, SourceVisuals] = {}
        self._previews: dict[str, PreviewMesh] = {}
        self._preview_failures: dict[str, Exception] = {}
        self._unreadable: dict[str, str] = {}
        self._unsupported: dict[str, str] = {}
        self.inspected: list[str] = []
        self.previewed: list[object] = []

    # -- seeding ---------------------------------------------------------

    def add(
        self,
        export: str,
        facts: MeshFacts,
        preview: PreviewMesh | None = None,
        visuals: SourceVisuals | None = None,
    ) -> None:
        """An export this inspector can read, and the preview it would emit."""
        self._facts[export] = facts
        if visuals is not None:
            self._visuals[export] = visuals
        self._previews[export] = preview if preview is not None else _preview_of(facts)

    def add_unreadable(self, export: str, reason: str) -> None:
        """A file that is not a readable mesh: :class:`MeshUnreadable` on inspect."""
        self._unreadable[export] = reason

    def add_unsupported(self, export: str, format_name: str) -> None:
        """An export in a format the matrix does not cover (D13)."""
        self._unsupported[export] = format_name

    def fail_preview(self, export: str, error: Exception | None = None) -> None:
        """Make preview emission raise for this export, verdict untouched (D7)."""
        self._preview_failures[export] = error or PreviewUnavailable(
            f"the clips in {export} cannot be carried into a preview"
        )

    # -- port ------------------------------------------------------------

    def inspect(self, export: str) -> InspectedMesh:
        self.inspected.append(export)
        unsupported = self._unsupported.get(export)
        if unsupported is not None:
            raise UnsupportedExport(export, unsupported)
        reason = self._unreadable.get(export)
        if reason is not None:
            raise MeshUnreadable(export, reason)
        facts = self._facts.get(export)
        if facts is None:
            raise MeshUnreadable(export, "no such file")
        return InspectedMesh(facts=facts, handle=export, visuals=self._visuals.get(export))

    def emit_preview(self, mesh: InspectedMesh) -> PreviewMesh:
        self.previewed.append(mesh.handle)
        export = str(mesh.handle)
        failure = self._preview_failures.get(export)
        if failure is not None:
            raise failure
        preview = self._previews.get(export)
        if preview is None:
            raise PreviewUnavailable(f"{export} was not read by this inspector")
        return preview


def _preview_of(facts: MeshFacts) -> PreviewMesh:
    """A preview derived from the facts of the read — decimated, names preserved."""
    triangles = (facts.triangles or 0) // DECIMATION_DIVISOR
    return PreviewMesh(
        content=b"preview" * max(triangles, 1),
        triangles=triangles,
        parts=tuple(facts.objects) + tuple(facts.empties),
        clips=facts.clip_names,
        bones=tuple(f"bone_{index}" for index in range(facts.bone_count or 0)),
    )


__all__ = ["DECIMATION_DIVISOR", "InMemoryMeshInspector"]
