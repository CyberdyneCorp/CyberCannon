"""The blob mirror: what belongs in it, how it is rebuilt, and who may read it.

The store itself (`FsBlobStore`, `S3BlobStore`) knows how to hold bytes under a
content key and how to bound access to one object. It deliberately does **not**
know what belongs in it, because `blob-storage` puts that decision somewhere
else: *"The service SHALL NOT ... treat the blob store as the record of what an
asset's views or exports are, and SHALL determine that set from the
repository."*

So this module is the half that reads the repository:

* :func:`mirror_project` walks the specifications at one revision and mirrors
  what they point at. Idempotent by construction — the key is the digest — so
  running it after a total loss lands every object on the key it had, which is
  what lets recovery be stated as *"readable again under the same keys"*.
* :func:`views_of` answers *what are this asset's views* from the specification
  and the repository, never from the store. A view removed from the repository
  stops being listed the moment the commit lands, even though its object is
  still sitting in the bucket costing nothing and harming nobody.
* :func:`accept_blob` refuses content that corresponds to no repository file.
  There is no upload endpoint behind it and there is not meant to be: the mirror
  is downstream of the repository, and an object with no source is an object
  nothing can ever rebuild.
* :func:`link_to_blob` issues a bounded link **after** the authorization
  decision that governs the owning asset, and never streams bytes (D14).

One distinction runs through all of it and it is the one `blob-storage` insists
on: a view the repository does not describe is **not found**, and a view it
describes whose object is missing is **temporarily unavailable**. They are
different sentences because they mean opposite things to the person reading
them, and collapsing them would tell an artist their concept art was never
uploaded when the truth is that a bucket is being restored.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from types import MappingProxyType

from cybercanon.application.errors import FailureKind, OperationFailed
from cybercanon.application.ports.blob_store import BlobStore, SignedLink
from cybercanon.application.ports.preview import PreviewMesh, StoredPreview
from cybercanon.application.ports.repository_host import RepositoryHost
from cybercanon.application.ports.spec_store import LoadedSpec, SpecStore
from cybercanon.application.results import as_result
from cybercanon.application.use_cases.spec_lens import ReadRefused
from cybercanon.domain.authorization import may_read_project
from cybercanon.domain.identity import Actor
from cybercanon.domain.revisions import ContentHash, Revision, blob_key

NO_EXPORTS: Mapping[str, Sequence[str]] = MappingProxyType({})
"""The default export set: none. Exports are named by whoever validated them."""


class SourceKind(Enum):
    """Why a repository file is mirrored. Three, and the specification names all three."""

    VIEW = "view"
    EXPORT = "export"
    PREVIEW = "preview"

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True)
class MirrorSource:
    """One repository file the mirror holds a copy of, and which asset it serves."""

    path: str
    asset_id: str
    kind: SourceKind = SourceKind.VIEW


@dataclass(frozen=True)
class MirroredBlob:
    """One mirrored file: where it came from, and the key its bytes derive."""

    source: MirrorSource
    key: str
    digest: ContentHash
    size_bytes: int

    @property
    def path(self) -> str:
        return self.source.path


@dataclass(frozen=True)
class MirroredView:
    """One view an asset declares, as the repository and the store see it.

    `stored` is false for a view the repository describes and the mirror has not
    got — which is *temporarily unavailable*, and is why this is a field rather
    than a reason to leave the view out of the answer.
    """

    path: str
    asset_id: str
    key: str
    stored: bool


@dataclass(frozen=True)
class DerivedPreview:
    """A preview mesh a validation run produced, and the export it came from.

    Derived rather than stored in the repository, and re-mirrorable because it
    is *reproducible from* one — which is the wording `blob-storage` uses and
    the reason a preview is allowed in a store that refuses sourceless content.
    """

    asset_id: str
    source_export: str
    mesh: PreviewMesh


@dataclass(frozen=True)
class MirrorReport:
    """What one mirroring pass stored, and what it could not find."""

    project: str
    revision: Revision
    mirrored: tuple[MirroredBlob, ...] = ()
    missing: tuple[MirrorSource, ...] = ()
    previews: tuple[StoredPreview, ...] = ()

    @property
    def keys(self) -> Mapping[str, str]:
        """Repository path to stored key — what a recovery compares before and after."""
        return {blob.path: blob.key for blob in self.mirrored}

    @property
    def is_complete(self) -> bool:
        """Whether every file the specifications point at was there to mirror."""
        return not self.missing


class NoRepositorySource(OperationFailed):
    """Content that corresponds to no repository file, or a path that is not one.

    *"The service SHALL NOT accept a blob with no repository-side source."*
    Invalid rather than not-found, because the caller submitted something the
    mirror can never be asked to rebuild — the fix is a commit, not a retry.
    """

    kind = FailureKind.INVALID
    identifier = "blob.no_repository_source"

    def __init__(self, subject: str) -> None:
        super().__init__(
            f"{subject} corresponds to no file in the repository; the mirror holds "
            "copies of repository content and nothing else",
            subject,
        )


class BlobNotMirrored(OperationFailed):
    """The repository describes it; the store has not got it yet.

    *"the response SHALL report it as temporarily unavailable AND SHALL NOT
    report the asset as having no such view."* Unavailable, and the distinction
    from :class:`NoRepositorySource` is the whole point of having two failures.
    """

    kind = FailureKind.UNAVAILABLE
    identifier = "blob.not_mirrored"

    def __init__(self, path: str, key: str = "") -> None:
        super().__init__(
            f"{path} is described by the repository but is not in the mirror yet; "
            "it is temporarily unavailable — re-mirroring restores it",
            path,
        )
        self.key = key


# --------------------------------------------------------------------------
# What the repository says the mirror should hold
# --------------------------------------------------------------------------


def sources_of(loaded: LoadedSpec, exports: Sequence[str] = ()) -> tuple[MirrorSource, ...]:
    """Every repository file this specification points at, in a stable order.

    The concept views are authored in `asset.yaml`; the exports are named by
    whoever validated them, because an export that was never validated is a file
    in a directory and not something the specification points at.
    """
    asset = loaded.asset
    views = asset.concept.views if asset.concept else ()
    asset_id = asset.id.value
    return (
        *(MirrorSource(path=path, asset_id=asset_id, kind=SourceKind.VIEW) for path in views),
        *(MirrorSource(path=path, asset_id=asset_id, kind=SourceKind.EXPORT) for path in exports),
    )


@as_result
def mirror_project(
    project: str,
    *,
    repository_host: RepositoryHost,
    spec_store: SpecStore,
    blob_store: BlobStore,
    root: str = "",
    exports: Mapping[str, Sequence[str]] = NO_EXPORTS,
    previews: Sequence[DerivedPreview] = (),
) -> MirrorReport:
    """Mirror everything this project's specifications point at, at one revision.

    Read at a pinned revision like every other read (D3), so a fetch landing
    mid-mirror cannot produce a store that is half one commit and half another.

    Idempotent, and that is not an optimisation: *"Mirroring content that is
    already stored SHALL succeed without re-uploading it and without changing
    its key."* Because the key is the digest, a second pass writes the same
    bytes to the same key, which is also what repairs a corrupted object.

    A file a specification names and the repository does not have is **reported,
    not invented**: it lands in `missing`, and the pass keeps going. A mirror
    that stopped at the first missing view would be a recovery nobody can run.
    """
    revision = repository_host.head(project)
    pinned = spec_store.pinned(revision.value)
    mirrored: list[MirroredBlob] = []
    missing: list[MirrorSource] = []
    for spec_path in pinned.specs_under(root):
        loaded = pinned.load(spec_path)
        for source in sources_of(loaded, exports.get(loaded.asset.id.value, ())):
            _mirror_one(project, source, revision, repository_host, blob_store, mirrored, missing)
    return MirrorReport(
        project=project,
        revision=revision,
        mirrored=tuple(mirrored),
        missing=tuple(missing),
        previews=tuple(
            blob_store.put_preview(preview.asset_id, preview.source_export, preview.mesh)
            for preview in previews
        ),
    )


def _mirror_one(
    project: str,
    source: MirrorSource,
    revision: Revision,
    repository_host: RepositoryHost,
    blob_store: BlobStore,
    mirrored: list[MirroredBlob],
    missing: list[MirrorSource],
) -> None:
    """One file: mirror it, or record that the repository does not have it."""
    content = repository_host.read(project, source.path, revision)
    if content is None:
        missing.append(source)
        return
    stored = blob_store.put(content)
    mirrored.append(
        MirroredBlob(
            source=source,
            key=stored.key,
            digest=stored.digest,
            size_bytes=stored.size_bytes,
        )
    )


@as_result
def views_of(
    project: str,
    spec_path: str,
    *,
    repository_host: RepositoryHost,
    spec_store: SpecStore,
    blob_store: BlobStore,
) -> tuple[MirroredView, ...]:
    """This asset's views, as the repository describes them (task 7.6).

    The store is asked only whether it *has* each one. A view whose file was
    removed from the repository is not listed at all — its object may well still
    be in the bucket, and that is fine: the bucket is a mirror, and a mirror
    does not get a vote on what an asset's views are.
    """
    revision = repository_host.head(project)
    loaded = spec_store.pinned(revision.value).load(spec_path)
    listed: list[MirroredView] = []
    for source in sources_of(loaded):
        content = repository_host.read(project, source.path, revision)
        if content is None:
            continue
        key = blob_key(ContentHash.of(content))
        listed.append(
            MirroredView(
                path=source.path,
                asset_id=source.asset_id,
                key=key,
                stored=blob_store.exists(key),
            )
        )
    return tuple(listed)


@as_result
def accept_blob(
    project: str,
    content: bytes,
    *,
    repository_host: RepositoryHost,
    path: str = "",
) -> MirroredBlob:
    """Accept content for storage only when the repository is its source (task 7.6).

    The check is the strong one: not *is there a file with this name*, but *does
    the repository hold exactly these bytes at this path, right now*. Anything
    else is content the mirror could never rebuild, and a mirror holding
    something it cannot rebuild is a database pretending to be a cache.
    """
    revision = repository_host.head(project)
    source = repository_host.read(project, path, revision) if path else None
    if source is None or source != content:
        raise NoRepositorySource(path or "the submitted content")
    digest = ContentHash.of(content)
    return MirroredBlob(
        source=MirrorSource(path=path, asset_id="", kind=SourceKind.VIEW),
        key=blob_key(digest),
        digest=digest,
        size_bytes=len(content),
    )


@as_result
def link_to_blob(
    actor: Actor,
    project: str,
    path: str,
    *,
    repository_host: RepositoryHost,
    blob_store: BlobStore,
    expires_at: datetime,
) -> SignedLink:
    """A bounded link to one blob, issued after the authorization decision (D14).

    The order is the requirement, not a style: *"The link SHALL be issued only
    after the authorization decision governing the owning asset has permitted
    the actor to read it"*, so the policy call comes first and an actor who may
    not read the project never reaches the store at all — no link is issued, and
    none could have been.

    The key is derived from the repository's current bytes rather than looked up
    in the index, because the repository is what decides which object an asset's
    view *is*. That costs a read of a file the mirror already holds a copy of,
    and it is the cost of never serving a stale object as current.
    """
    decision = may_read_project(actor, project)
    if decision.refused:
        raise ReadRefused(decision.reason, project)
    revision = repository_host.head(project)
    content = repository_host.read(project, path, revision)
    if content is None:
        raise NoRepositorySource(path)
    key = blob_key(ContentHash.of(content))
    if not blob_store.exists(key):
        raise BlobNotMirrored(path, key)
    return blob_store.link_for(key, expires_at=expires_at)


__all__ = [
    "NO_EXPORTS",
    "BlobNotMirrored",
    "DerivedPreview",
    "MirrorReport",
    "MirrorSource",
    "MirroredBlob",
    "MirroredView",
    "NoRepositorySource",
    "SourceKind",
    "accept_blob",
    "link_to_blob",
    "mirror_project",
    "sources_of",
    "views_of",
]
