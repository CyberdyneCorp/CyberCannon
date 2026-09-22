"""What the 3D viewer needs before it loads anything, and none of it is geometry.

`add-viewer-3d` splits the viewer in two along D6's line. Everything in this
module is the half that is answerable **without a renderer**: which preview to
load, which export it came from, whether that export is still the latest one
that validated, what the validation run measured, which parts and clips the
source carries, which declared design state each clip satisfies, and which
annotations are orphaned. The other half — the nearest point on a part's
surface, the camera, the bounding volume — is the browser's, and nothing here
can reach it.

Three properties are load-bearing:

* **The working export is never addressed.** This module produces a *preview*
  reference and has no field that could hold an export's content address. The
  export's path is reported as provenance, which is a sentence on a screen, not
  a link (D7, and `tests/unit/test_http_viewer.py` enumerates
  the surface to prove it).
* **A missing preview has a reason.** *"No preview"* on its own reads as a page
  that failed to load one, so :class:`NoPreview` distinguishes the three cases
  the specification names and the descriptor always carries one of them or a
  preview.
* **The state-to-clip mapping is consumed, never re-derived** (D8). The required
  clip name for a declared state comes from
  :func:`~cybercanon.domain.effective_spec.merge`'s `required_clips`, which is
  the same derivation `animation.clip_missing` validates against. Matching is
  exact: a clip named one character off shows as *a state with no clip* beside
  *an unclaimed clip*, which is the report a modeller can act on and the report
  a fuzzy match would hide.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from enum import Enum

from cybercanon.application.errors import FailureKind, OperationFailed
from cybercanon.application.ports.blob_store import BlobStore
from cybercanon.application.ports.mesh_inspector import MeshInspector
from cybercanon.application.ports.preview import StoredPreview
from cybercanon.application.ports.repository_host import RepositoryHost
from cybercanon.application.ports.spec_store import SpecStore
from cybercanon.application.results import as_result
from cybercanon.application.use_cases.annotations import AssetNotFound, Workspace, list_annotations
from cybercanon.application.use_cases.ingest_views import locate_asset
from cybercanon.application.use_cases.validation_records import recorded_validation
from cybercanon.domain.anchor_resolution import AnchorResolution, Resolution, resolution_of
from cybercanon.domain.annotations import Annotation, AnnotationFilter
from cybercanon.domain.design import State
from cybercanon.domain.effective_spec import merge
from cybercanon.domain.mesh_facts import FactKind, MeshFacts
from cybercanon.domain.validation_outcome import ValidationRecord


class NoPreview(Enum):
    """Why this asset has no preview to display. Three reasons and no fourth.

    `viewer-3d` names them: *"no export recorded, no successful validation run,
    or preview emission failed"*. They are distinguished at this level rather
    than in the browser because the difference is a fact about the repository,
    and a viewer that inferred it would eventually report an unvalidated export
    as a failed emission — which sends a modeller to fix the wrong thing.
    """

    NO_EXPORT_RECORDED = "no export has been validated for this asset yet"
    NO_SUCCESSFUL_VALIDATION = "the most recent validation of this asset's export failed"
    EMISSION_FAILED = "the export validated, but no preview was emitted from it"

    def __str__(self) -> str:
        return self.value


class StateCoverage(Enum):
    """What became of one declared design state against the clips on hand."""

    SATISFIED = "satisfied"
    NO_CLIP = "no clip"
    UNANIMATED = "declared unanimated"

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True)
class CoveredState:
    """One declared state, the clip it requires, and whether that clip is there.

    A state declared unanimated carries no clip name and is *not* a gap:
    `animation-playback` requires it to be *"shown as declared unanimated"* and
    explicitly not as missing.
    """

    state: str
    clip: str
    coverage: StateCoverage

    @property
    def is_satisfied(self) -> bool:
        return self.coverage is StateCoverage.SATISFIED

    @property
    def is_missing(self) -> bool:
        """Whether this state is a gap — an unanimated one never is."""
        return self.coverage is StateCoverage.NO_CLIP


@dataclass(frozen=True)
class ClipCoverage:
    """Every declared state, and every clip no declared state claims (D8)."""

    states: tuple[CoveredState, ...] = ()
    unclaimed: tuple[str, ...] = ()

    @property
    def satisfied(self) -> tuple[CoveredState, ...]:
        return tuple(entry for entry in self.states if entry.is_satisfied)

    @property
    def missing(self) -> tuple[CoveredState, ...]:
        return tuple(entry for entry in self.states if entry.is_missing)

    @property
    def unanimated(self) -> tuple[CoveredState, ...]:
        return tuple(entry for entry in self.states if entry.coverage is StateCoverage.UNANIMATED)

    def state_for(self, clip: str) -> str:
        """Which declared state this clip satisfies, or an empty string for none."""
        return next(
            (entry.state for entry in self.states if entry.is_satisfied and entry.clip == clip),
            "",
        )


@dataclass(frozen=True)
class SourceCounts:
    """What the validation run measured about the source export.

    Every field is ``None`` when the fact was not available, never ``0`` — the
    `MeshFacts` convention, and `viewer-3d` requires it in so many words: *"A
    count that was never recorded SHALL be shown as unavailable rather than
    substituted by the preview's."*
    """

    triangles: int | None = None
    objects: int | None = None
    materials: int | None = None

    @property
    def any_recorded(self) -> bool:
        return any(value is not None for value in (self.triangles, self.objects, self.materials))

    @property
    def reported(self) -> tuple[tuple[str, int | None], ...]:
        """The three figures, named once, in the order every surface names them.

        Named *here* rather than in the renderer, and that is a layering rule
        rather than a convenience: `triangles` is the figure a triangle budget
        is compared against, and
        `tests/tooling/test_rule_logic_stays_in_the_domain.py` fails the build
        when a surface module names one — because *"comparing a budget requires
        naming it"*, and the surface that names it is one `if` away from
        comparing it. The adapter renders this mapping and never spells a field.
        """
        return (
            ("triangles", self.triangles),
            ("objects", self.objects),
            ("materials", self.materials),
        )


@dataclass(frozen=True)
class PreviewDescriptor:
    """Everything the viewer needs to load an asset, and nothing it must not have.

    There is no member here that addresses the working export. `source_export`
    is its **path**, carried as the provenance sentence the specification
    requires — *"the viewer SHALL identify the export the preview was derived
    from"* — and a path is not a way to fetch one.
    """

    project: str
    asset_id: str
    path: str
    revision: str
    preview: StoredPreview | None = None
    source_export: str = ""
    latest_validated_export: str = ""
    counts: SourceCounts = SourceCounts()
    parts: tuple[str, ...] = ()
    clips: tuple[str, ...] = ()
    coverage: ClipCoverage = ClipCoverage()
    absent: NoPreview | None = None

    @property
    def has_preview(self) -> bool:
        return self.preview is not None

    @property
    def derived_from_latest(self) -> bool:
        """Whether what is on screen came from the export that most recently passed.

        A superseded preview has to say so: *"a reviewer annotating a stale
        preview is a reviewer wasting a modeller's day."*
        """
        if self.preview is None:
            return False
        return bool(self.source_export) and self.source_export == self.latest_validated_export

    @property
    def reason(self) -> str:
        """Why there is nothing to display, or an empty string when there is."""
        return str(self.absent) if self.absent is not None else ""


@dataclass(frozen=True)
class ResolvedAnnotation:
    """One annotation and its standing against a given export's part names."""

    annotation: Annotation
    resolution: AnchorResolution

    @property
    def id(self) -> str:
        return self.annotation.id


@dataclass(frozen=True)
class ResolutionListing:
    """Every mesh-anchored annotation of one asset, resolved against one export.

    Annotations anchored to a concept view are simply not here: resolving one is
    `view-versioning`'s question, asked against a view's history rather than
    against a mesh's part names.
    """

    project: str
    asset_id: str
    export: str
    revision: str
    entries: tuple[ResolvedAnnotation, ...] = ()

    @property
    def orphaned(self) -> tuple[ResolvedAnnotation, ...]:
        return tuple(entry for entry in self.entries if entry.resolution.is_orphaned)

    @property
    def partial(self) -> tuple[ResolvedAnnotation, ...]:
        return tuple(entry for entry in self.entries if entry.resolution.is_partial)

    @property
    def orphan_count(self) -> int:
        """*"Orphaned annotations SHALL be listed and countable."*"""
        return len(self.orphaned)


# --------------------------------------------------------------------------
# The descriptor
# --------------------------------------------------------------------------


@as_result
def get_preview_descriptor(
    project: str,
    asset_id: str,
    *,
    repository_host: RepositoryHost,
    spec_store: SpecStore,
    mesh_inspector: MeshInspector | None = None,
    blob_store: BlobStore | None = None,
) -> PreviewDescriptor:
    """What to load for this asset, where it came from, and what it is made of.

    Never raises over a preview: an asset with none is a *descriptor carrying a
    reason*, because `viewer-3d` requires the specification, the annotations and
    every other surface to stay usable when there is nothing to render.
    """
    revision = repository_host.head(project)
    pinned = spec_store.pinned(revision.value)
    path = locate_asset(asset_id, spec_store=spec_store, revision=revision)
    if path is None:
        raise AssetNotFound(project, asset_id)
    record = recorded_validation(project, path, repository_host=repository_host, revision=revision)
    facts = _facts_of(record, mesh_inspector)
    preview = _preview_of(record, asset_id, blob_store)
    return PreviewDescriptor(
        project=project,
        asset_id=asset_id,
        path=path,
        revision=revision.value,
        preview=preview,
        source_export=preview.source_export if preview else "",
        latest_validated_export=record.export if record and record.passed else "",
        counts=counts_of(facts),
        parts=_names(facts, FactKind.OBJECTS),
        clips=facts.clip_names if facts and facts.has(FactKind.CLIPS) else (),
        coverage=coverage_of(_states(pinned, path), _required(pinned, path), _clips(facts)),
        absent=_absence(record, preview),
    )


def _absence(record: ValidationRecord | None, preview: StoredPreview | None) -> NoPreview | None:
    """Which of the three reasons applies, or ``None`` when there is a preview."""
    if record is None:
        return NoPreview.NO_EXPORT_RECORDED
    if not record.passed:
        return NoPreview.NO_SUCCESSFUL_VALIDATION
    if preview is None:
        return NoPreview.EMISSION_FAILED
    return None


def _preview_of(
    record: ValidationRecord | None, asset_id: str, blob_store: BlobStore | None
) -> StoredPreview | None:
    """The stored preview for this asset, when an export validated and one exists."""
    if record is None or not record.passed or blob_store is None:
        return None
    return blob_store.preview_for(asset_id)


def _facts_of(
    record: ValidationRecord | None, mesh_inspector: MeshInspector | None
) -> MeshFacts | None:
    """What the source export is made of, read through the one inspector boundary.

    Guarded, and deliberately: an export that has been deleted since it was
    validated must leave the viewer reporting unavailable counts, not refusing
    to open the asset. The verdict is the recorded one either way — nothing here
    re-decides it, and nothing here can.
    """
    if record is None or mesh_inspector is None:
        return None
    try:
        return mesh_inspector.inspect(record.export).facts
    except OperationFailed:
        return None


def counts_of(facts: MeshFacts | None) -> SourceCounts:
    """The three figures the viewer reports as *the asset's*, or their absence."""
    if facts is None:
        return SourceCounts()
    return SourceCounts(
        triangles=facts.triangles if facts.has(FactKind.TRIANGLES) else None,
        objects=len(facts.objects) if facts.has(FactKind.OBJECTS) else None,
        materials=len(facts.materials) if facts.has(FactKind.MATERIALS) else None,
    )


def _names(facts: MeshFacts | None, kind: FactKind) -> tuple[str, ...]:
    if facts is None or not facts.has(kind):
        return ()
    return tuple(facts.value(kind) or ())  # type: ignore[arg-type]


def _clips(facts: MeshFacts | None) -> tuple[str, ...]:
    return facts.clip_names if facts is not None and facts.has(FactKind.CLIPS) else ()


def _states(spec_store: SpecStore, path: str) -> tuple[State, ...]:
    loaded = spec_store.load(path)
    return loaded.asset.design.states if loaded.asset.design else ()


def _required(spec_store: SpecStore, path: str) -> dict[str, str]:
    """The clip each declared state requires, as the specification already derives it."""
    loaded = spec_store.load(path)
    spec = merge(loaded.asset, spec_store.load_project(path).defaults)
    return {required.state: required.clip_name for required in spec.required_clips}


# --------------------------------------------------------------------------
# State-to-clip coverage (D8)
# --------------------------------------------------------------------------


def coverage_of(
    states: Iterable[State],
    required: dict[str, str],
    clips: Iterable[str],
) -> ClipCoverage:
    """Which declared states these clips satisfy, and which clips claim no state.

    Exact name matching, with no case folding and no similarity — D8: *"two
    places deriving the same mapping is the design/modeling lens divergence in a
    new costume"*, and a heuristic here would hide the naming drift the
    validator exists to catch.
    """
    present = tuple(clips)
    covered = tuple(_covered(state, required.get(state.name, ""), present) for state in states)
    claimed = {entry.clip for entry in covered if entry.is_satisfied}
    return ClipCoverage(
        states=covered,
        unclaimed=tuple(clip for clip in present if clip not in claimed),
    )


def _covered(state: State, required: str, clips: tuple[str, ...]) -> CoveredState:
    """One state's standing. A state that declares no animation is never a gap."""
    if state.is_unanimated:
        return CoveredState(state=state.name, clip="", coverage=StateCoverage.UNANIMATED)
    if required and required in clips:
        return CoveredState(state=state.name, clip=required, coverage=StateCoverage.SATISFIED)
    return CoveredState(state=state.name, clip=required, coverage=StateCoverage.NO_CLIP)


# --------------------------------------------------------------------------
# Resolutions, with no mesh loaded (D6)
# --------------------------------------------------------------------------


@as_result
def annotation_resolutions(
    workspace: Workspace,
    *,
    export: str = "",
    parts: Iterable[str] = (),
    bones: Iterable[str] | None = None,
) -> ResolutionListing:
    """Every mesh-anchored annotation of this asset against those part names.

    `parts` is a set of *names* — from `MeshFacts`, from the preview descriptor,
    or from a mesh the browser has already loaded. Nothing here opens a file or
    touches geometry, which is the whole of D6: the asset page and the agent
    read surface can both state an orphan count with no renderer anywhere.

    `bones` is ``None`` when the caller does not know the bone set, which is
    *not* the same as an export with no bones: an anchor naming a bone would
    otherwise be reported partial by every caller that simply had not looked.
    """
    known = tuple(parts)
    listing = list_annotations.raising(workspace, AnnotationFilter.every())
    entries = tuple(
        ResolvedAnnotation(annotation=annotation, resolution=resolution)
        for annotation in listing.annotations
        if (resolution := resolution_of(annotation.target, known, _bones(bones))) is not None
    )
    return ResolutionListing(
        project=workspace.project,
        asset_id=workspace.asset_id,
        export=export,
        revision=listing.revision,
        entries=entries,
    )


def _bones(declared: Iterable[str] | None) -> Iterable[str] | None:
    return None if declared is None else tuple(declared)


class PreviewUnretrievable(OperationFailed):
    """The preview is recorded but its bytes could not be read, named (`viewer-3d`).

    *"The viewer SHALL report that condition, naming the preview it attempted,
    and SHALL offer a retry. It SHALL NOT ... report the asset as having no
    preview."* Unavailable rather than not-found for the same reason a corrupt
    blob is: the record is right, the repository can produce it again, and
    re-mirroring is the repair.
    """

    kind = FailureKind.UNAVAILABLE
    identifier = "preview.unretrievable"

    def __init__(self, key: str, reason: str = "") -> None:
        stated = f": {reason}" if reason else ""
        super().__init__(f"the preview stored at {key!r} could not be retrieved{stated}", key)
        self.key = key
        self.reason = reason


@dataclass(frozen=True)
class PreviewContent:
    """The preview's bytes exactly as they are stored, and what they are."""

    asset_id: str
    key: str
    content: bytes
    content_type: str
    source_export: str = ""

    @property
    def size_bytes(self) -> int:
        return len(self.content)


@as_result
def read_preview(
    project: str,
    asset_id: str,
    *,
    repository_host: RepositoryHost,
    spec_store: SpecStore,
    blob_store: BlobStore | None = None,
) -> PreviewContent:
    """The stored preview's bytes, verbatim, or the failure that names it.

    Byte-identical by construction: the bytes come from
    :meth:`~cybercanon.application.ports.blob_store.BlobStore.verified`, which is
    the same accessor every other read of stored content goes through, and
    nothing between here and the caller transforms them.
    """
    descriptor = get_preview_descriptor.raising(
        project,
        asset_id,
        repository_host=repository_host,
        spec_store=spec_store,
        blob_store=blob_store,
    )
    preview = descriptor.preview
    if preview is None or blob_store is None:
        raise PreviewUnretrievable(f"{asset_id} preview", descriptor.reason)
    return PreviewContent(
        asset_id=asset_id,
        key=preview.key,
        content=_bytes_of(preview.key, blob_store),
        content_type=preview.content_type,
        source_export=preview.source_export,
    )


def _bytes_of(key: str, blob_store: BlobStore) -> bytes:
    """The stored object, or the one failure that names the preview it attempted.

    The store's own vocabulary — absent, corrupt — is translated into
    :class:`PreviewUnretrievable` so the viewer has one condition to present and
    one retry to offer, rather than two that mean the same thing to a reviewer.
    """
    try:
        return blob_store.verified(key)
    except OperationFailed as failure:
        raise PreviewUnretrievable(key, failure.message) from failure


__all__ = [
    "ClipCoverage",
    "CoveredState",
    "NoPreview",
    "PreviewContent",
    "PreviewDescriptor",
    "PreviewUnretrievable",
    "Resolution",
    "ResolutionListing",
    "ResolvedAnnotation",
    "SourceCounts",
    "StateCoverage",
    "annotation_resolutions",
    "counts_of",
    "coverage_of",
    "get_preview_descriptor",
    "read_preview",
]
