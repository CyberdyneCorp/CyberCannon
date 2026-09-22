"""Mirroring concept views, and rebuilding that mirror from the repository alone.

Two operations and one guarantee. The guarantee is `concept-ingestion`'s, and it
is the reason both operations exist rather than being folded into ingestion:

    *"The mirror SHALL be reconstructible in full from the repository alone:
    deleting every mirrored object and every thumbnail and rebuilding SHALL
    restore every view."*

A recovery you cannot run is a hope, so the rebuild is an ordinary operation
that takes the same path ingestion's mirroring step takes — one function, called
twice — and produces byte-identical keys, because the key is the digest (D3) and
a digest does not remember when it was taken.

**What a project's views are is read from the repository, never from the
mirror and never from `asset.yaml`.** A view lives at
`<asset dir>/concept/<slot>.<ext>` (D4), so the set of views is a tree listing
filtered by that shape. That is what makes ingestion able to leave an existing
specification untouched, and what makes the index's hash → view mapping
reconstructible by walking the repository exactly as D3 says it is.
"""

from __future__ import annotations

from dataclasses import dataclass

from cybercanon.application.ports.blob_store import BlobStore
from cybercanon.application.ports.repository_host import RepositoryHost
from cybercanon.application.ports.spec_store import SpecStore
from cybercanon.application.ports.thumbnail_renderer import (
    DEFAULT_SIZES,
    ThumbnailRenderer,
)
from cybercanon.application.ports.view_index import ViewIndex, ViewRow
from cybercanon.application.results import as_result
from cybercanon.domain.revisions import ContentHash, Revision, blob_key
from cybercanon.domain.views import ViewSlot, asset_dir_of, slot_of


@dataclass(frozen=True)
class LocatedView:
    """One view file the repository holds, and the asset it belongs to."""

    asset_id: str
    slot: ViewSlot
    path: str


@dataclass(frozen=True)
class MirroredView:
    """One view as the mirror now holds it."""

    view: LocatedView
    digest: ContentHash
    byte_size: int
    stored: bool

    @property
    def key(self) -> str:
        return blob_key(self.digest)


@dataclass(frozen=True)
class ViewMirrorReport:
    """What one pass did: what it mirrored, and what it derived from that."""

    project: str
    revision: Revision
    mirrored: tuple[MirroredView, ...] = ()
    already_stored: tuple[str, ...] = ()
    thumbnails: int = 0

    @property
    def keys(self) -> dict[str, str]:
        """Repository path to stored key — what a recovery compares before and after."""
        return {entry.view.path: entry.key for entry in self.mirrored}

    @property
    def wrote_nothing(self) -> bool:
        """True when every object was already there — *"re-running it is a no-op"*."""
        return len(self.already_stored) == len(self.mirrored)


def views_at(
    project: str,
    revision: Revision,
    *,
    repository_host: RepositoryHost,
    spec_store: SpecStore,
) -> tuple[LocatedView, ...]:
    """Every concept view the repository holds at that revision, in path order.

    Derived from the deterministic path (D4) and from the specification files
    that say which asset each directory describes — not from an index row and
    not from a list inside `asset.yaml`, so a project whose index was dropped
    and whose specification nobody edited still knows exactly what its views
    are.
    """
    pinned = spec_store.pinned(revision.value)
    assets = {
        _directory_of(path): pinned.load(path).asset.id.value for path in pinned.specs_under("")
    }
    located: list[LocatedView] = []
    for path in repository_host.paths_at(project, revision):
        slot = slot_of(path)
        asset_id = assets.get(asset_dir_of(path)) if slot is not None else None
        if slot is not None and asset_id is not None:
            located.append(LocatedView(asset_id=asset_id, slot=slot, path=path))
    return tuple(sorted(located, key=lambda view: view.path))


@as_result
def mirror_views(
    project: str,
    *,
    repository_host: RepositoryHost,
    spec_store: SpecStore,
    blob_store: BlobStore,
    view_index: ViewIndex | None = None,
    thumbnail_renderer: ThumbnailRenderer | None = None,
) -> ViewMirrorReport:
    """Mirror every view this project holds, and derive its thumbnails (D3, D9).

    Idempotent by construction and not by an optimisation: the key is the
    digest, so a second pass writes the same bytes to the same key and the
    report says so. That is also what repairs a corrupted object and what makes
    a rebuild after total loss land on the keys it had.
    """
    revision = repository_host.head(project)
    located = views_at(project, revision, repository_host=repository_host, spec_store=spec_store)
    mirrored: list[MirroredView] = []
    already: list[str] = []
    derived = 0
    for view in located:
        content = repository_host.read(project, view.path, revision)
        if content is None:  # pragma: no cover — the listing came from this revision
            continue
        entry = _mirror_one(project, view, content, blob_store, view_index, revision)
        mirrored.append(entry)
        if entry.stored:
            already.append(view.path)
        derived += _derive(content, blob_store, thumbnail_renderer)
    return ViewMirrorReport(
        project=project,
        revision=revision,
        mirrored=tuple(mirrored),
        already_stored=tuple(already),
        thumbnails=derived,
    )


def _mirror_one(
    project: str,
    view: LocatedView,
    content: bytes,
    blob_store: BlobStore,
    view_index: ViewIndex | None,
    revision: Revision,
) -> MirroredView:
    """One view's bytes into the store, and its row into the index (D3)."""
    digest = ContentHash.of(content)
    stored_already = blob_store.exists(blob_key(digest))
    stored = blob_store.put(content)
    if view_index is not None:
        view_index.record(
            ViewRow(
                project=project,
                asset_id=view.asset_id,
                slot=str(view.slot),
                revision=revision.value,
                path=view.path,
                digest=stored.digest,
                byte_size=stored.size_bytes,
            )
        )
    return MirroredView(
        view=view, digest=stored.digest, byte_size=stored.size_bytes, stored=stored_already
    )


def _derive(
    content: bytes, blob_store: BlobStore, thumbnail_renderer: ThumbnailRenderer | None
) -> int:
    """Thumbnails into the store and nowhere else (D9). None wired means none derived."""
    if thumbnail_renderer is None:
        return 0
    derived = thumbnail_renderer.derive(content, DEFAULT_SIZES)
    for thumbnail in derived:
        blob_store.put(thumbnail.content, content_type=thumbnail.content_type)
    return len(derived)


def _directory_of(spec_path: str) -> str:
    head, _, _ = spec_path.rpartition("/")
    return head


__all__ = [
    "LocatedView",
    "MirroredView",
    "ViewMirrorReport",
    "mirror_views",
    "views_at",
]
