"""Building the derived index, and keeping it honest on the read path (D7, D8).

Git is the source of truth, so this module never *originates* anything: it
scans the repository's specification files and writes one
:class:`~cybercanon.application.ports.search_index.IndexedAsset` row per asset.
Deleting the index and running :func:`rebuild_index` again is a complete
recovery, which is what `asset-lookup` means by *derived and rebuildable*.

Two jobs, and they fail in opposite directions:

* **rebuild** — a command. It reads every specification under a root, reports
  how many assets it indexed and **names the files it could not read**, without
  letting one malformed file abort the scan. A rebuild that stopped at the first
  broken file would be a rebuild nobody runs.
* **the read path** — never a command. Every lookup compares the indexed file's
  size and modification time against the file on disk and, on a mismatch,
  re-reads that one file and updates its row (D8). The common case — one file
  edited — costs one stat call, and a stale answer is never served as current.

**Where the fingerprint comes from is the caller's business.** The core does no
file system access, so :data:`Fingerprinter` is injected: the composition root
passes one backed by `os.stat`, and a unit test passes rows that fingerprint to
:data:`None`, which is the honest value for "this store has no files". Two
``None`` fingerprints compare equal, so a repository-free test is simply a
repository where nothing has changed.

**A validated export is repository content, and a rebuild reads it** (G2). The
validation worker writes the outcome of a run as a file beside the asset and
commits it, so `validations` — a lookup over those files, injected exactly as
`fingerprints` is — is what makes *"dropping the index loses no answer"* true
for the one field `asset.yaml` does not carry. A caller with no repository to
read them from (a laptop, a unit test) passes none, and the rebuild then carries
the two fields forward from the row it replaces rather than blanking them: what
a scan cannot restore, it does not destroy.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import PurePosixPath

from cybercanon.application.errors import OperationFailed
from cybercanon.application.ports.search_index import (
    FileFingerprint,
    IndexedAsset,
    SearchIndex,
)
from cybercanon.application.ports.spec_store import LoadedSpec, ProjectConfig, SpecStore
from cybercanon.application.results import as_result
from cybercanon.application.use_cases.validation_records import (
    ValidationLookup,
    no_validations,
)
from cybercanon.domain.asset import Links
from cybercanon.domain.validation_outcome import ValidationRecord

Fingerprinter = Callable[[str], FileFingerprint | None]
"""How a caller answers *what does this file look like right now* (D8).

``None`` means the question cannot be answered here — an in-memory store, a
path that has disappeared — and it is a value rather than a failure: a row
fingerprinted ``None`` and a file that answers ``None`` agree, so a test with no
disk behaves as a repository in which nothing has changed.
"""

ROOT_DIRECTORY = "."
"""What the directory of a specification at the repository root reads as."""


def no_fingerprints(path: str) -> FileFingerprint | None:
    """The default fingerprinter: nothing is knowable, so nothing is stale."""
    return None


@dataclass(frozen=True)
class RebuildProgress:
    """How far a rebuild has got, reported one specification at a time.

    A rebuild is the recovery for a lost index (`deployment-operations`, D5), so
    its duration is an operational number rather than a detail: *"an index
    rebuild is in progress"* has to be sayable while it runs, and *"reads that
    cannot be served from the partial index"* only means something if there is a
    partial index somebody is watching fill. Hence a value with both halves —
    how many are done and how many there are — rather than a log line.
    """

    project: str
    path: str
    done: int
    total: int
    resumed: bool = False

    @property
    def complete(self) -> bool:
        return self.done >= self.total

    @property
    def remaining(self) -> int:
        return max(self.total - self.done, 0)


type Progress = Callable[[RebuildProgress], None]
"""How a caller watches a rebuild. The composition root prints; a test records."""


def no_progress(progress: RebuildProgress) -> None:
    """The default: nobody is watching, and the rebuild does not care."""


@dataclass(frozen=True)
class UnreadableSpec:
    """A specification file the scan found and could not parse.

    Named rather than counted: "one file could not be read" is not actionable,
    and the whole point of reporting it is that somebody opens that file.
    """

    path: str
    reason: str

    def __str__(self) -> str:
        return f"{self.path}: {self.reason}"


@dataclass(frozen=True)
class RebuildReport:
    """What a rebuild indexed, and what it could not read."""

    project: str = ""
    indexed: tuple[str, ...] = ()
    unreadable: tuple[UnreadableSpec, ...] = ()
    forgotten: tuple[str, ...] = ()

    @property
    def indexed_count(self) -> int:
        """How many assets were indexed — the count the command reports."""
        return len(self.indexed)

    @property
    def unreadable_paths(self) -> tuple[str, ...]:
        """The files that could not be read, named."""
        return tuple(spec.path for spec in self.unreadable)

    @property
    def is_complete(self) -> bool:
        """Whether every specification under the root became a row."""
        return not self.unreadable


@dataclass(frozen=True)
class FreshEntry:
    """One indexed row and whether it can be served as current (D8).

    `stale` is true only when the row disagrees with the file on disk *and* the
    file could not be re-read — the one case where an answer exists but must not
    be presented as current.
    """

    entry: IndexedAsset | None
    refreshed: bool = False
    stale: bool = False
    detail: str = ""

    @property
    def is_known(self) -> bool:
        return self.entry is not None


def entry_for(
    loaded: LoadedSpec,
    project: ProjectConfig | None = None,
    fingerprint: FileFingerprint | None = None,
    previous: IndexedAsset | None = None,
    validation: ValidationRecord | None = None,
) -> IndexedAsset:
    """One parsed specification as the index holds it.

    Deliberately mechanical: every value is copied from the specification file
    or from the path it was read at. Nothing is summarised, guessed or
    generated, because a row that carried an opinion would be a place where
    information originates — which is exactly what the index may not be.

    Tags and descriptions stay empty here. They are *derived* metadata keyed by
    a blob's content (openspec/project.md), and the block D7 lists for this
    index — ids, names, aliases, tags, status, owners, link targets — is fed by
    `add-derived-metadata`, not by `asset.yaml`, which has no such fields.
    """
    asset = loaded.asset
    links = asset.links or Links()
    return IndexedAsset(
        asset_id=asset.id.value,
        name=asset.name,
        project=_project_name(project),
        status=str(asset.status),
        aliases=asset.aliases,
        spec_path=loaded.path,
        directory=directory_of(loaded.path),
        source_file=links.source,
        engine_path=links.engine,
        discussion=links.discussion,
        design_doc=links.design_doc,
        owner_art=asset.owner_art,
        owner_design=asset.owner_design,
        owner_code=asset.owner_code,
        validated_export=_validated_export(validation, previous),
        validated_at=_validated_at(validation, previous),
        fingerprint=fingerprint,
    )


def _validated_export(
    validation: ValidationRecord | None, previous: IndexedAsset | None
) -> str | None:
    """Which export was validated: the repository's answer, then the old row's."""
    if validation is not None:
        return validation.export
    return previous.validated_export if previous else None


def _validated_at(validation: ValidationRecord | None, previous: IndexedAsset | None) -> str | None:
    """When it was validated, in the shape every surface renders it from."""
    if validation is not None:
        return validation.validated_at.isoformat()
    return previous.validated_at if previous else None


def directory_of(spec_path: str) -> str:
    """The asset's directory in the repository — where `where_is` starts."""
    parent = PurePosixPath(spec_path).parent.as_posix()
    return ROOT_DIRECTORY if parent in ("", ".") else parent


@as_result
def rebuild_index(
    root: str = "",
    *,
    spec_store: SpecStore,
    search_index: SearchIndex,
    fingerprints: Fingerprinter = no_fingerprints,
    progress: Progress = no_progress,
    resume: bool = False,
    validations: ValidationLookup = no_validations,
) -> RebuildReport:
    """Scan every specification under `root` and rewrite the project's rows.

    One unreadable file is a finding, never the end of the scan: a project with
    a broken `asset.yaml` still gets an index of everything else, and the
    command names the file so somebody can fix it.

    **Resumable, because the rebuild is a recovery** (`deployment-operations`,
    task 5.7). Rows are written one specification at a time, so an interrupted
    rebuild leaves a partial index rather than nothing; `resume` then carries
    over every row whose file has not changed since it was written and re-reads
    only the rest. Two consequences worth stating: a resumed run reports the
    carried-over rows as indexed, so the sweep at the end does not forget an
    asset it merely did not re-read; and with no fingerprinter a resumed run
    carries everything over, which is the honest answer for a store that cannot
    see files — *nothing has changed* is exactly what it knows.
    """
    project = spec_store.load_project(root)
    name = _project_name(project)
    known = {entry.asset_id: entry for entry in search_index.list_assets(project=name)}
    carried = {entry.spec_path: entry for entry in known.values()} if resume else {}
    paths = tuple(spec_store.specs_under(root))
    indexed: list[str] = []
    unreadable: list[UnreadableSpec] = []
    for position, path in enumerate(paths, start=1):
        already = _carried_over(path, carried, fingerprints)
        row = already or _row_for(
            path, project, spec_store, fingerprints, known, unreadable, validations
        )
        if row is not None and already is None:
            search_index.upsert(row)
        if row is not None:
            indexed.append(row.asset_id)
        progress(
            RebuildProgress(
                project=name,
                path=path,
                done=position,
                total=len(paths),
                resumed=already is not None,
            )
        )
    forgotten = _forget_missing(search_index, name, known, frozenset(indexed))
    return RebuildReport(
        project=name,
        indexed=tuple(indexed),
        unreadable=tuple(unreadable),
        forgotten=forgotten,
    )


def _carried_over(
    path: str,
    carried: dict[str, IndexedAsset],
    fingerprints: Fingerprinter,
) -> IndexedAsset | None:
    """The row a resumed rebuild keeps rather than re-reading, if there is one.

    The comparison is the one D8's read path already makes — the fingerprint the
    row was written with against the file as it is now — so "already done" means
    the same thing here as "not stale" there, rather than a second notion of
    freshness that could disagree with it.
    """
    entry = carried.get(path)
    if entry is None:
        return None
    return entry if entry.fingerprint == fingerprints(path) else None


def current_entry(
    asset_id: str,
    *,
    spec_store: SpecStore,
    search_index: SearchIndex,
    fingerprints: Fingerprinter = no_fingerprints,
    project: str | None = None,
) -> FreshEntry:
    """The row for that asset, re-read first if the file has moved on (D8).

    The self-healing half of the staleness rule: a lookup never returns an
    answer it knows to be out of date, and it never triggers a full rebuild to
    avoid one. When the file cannot be re-read, the old row is still returned —
    marked stale, so the caller states it rather than presenting it as current.
    """
    entry = search_index.get(asset_id, project)
    if entry is None:
        return FreshEntry(entry=None)
    fingerprint = fingerprints(entry.spec_path) if entry.spec_path else None
    if not search_index.is_stale(asset_id, fingerprint):
        return FreshEntry(entry=entry)
    return _reread(
        entry,
        fingerprint,
        spec_store=spec_store,
        search_index=search_index,
    )


def _reread(
    entry: IndexedAsset,
    fingerprint: FileFingerprint | None,
    *,
    spec_store: SpecStore,
    search_index: SearchIndex,
) -> FreshEntry:
    """Re-read one specification file and update its row, or say it is stale."""
    try:
        loaded = spec_store.load(entry.spec_path)
    except OperationFailed as failure:
        return FreshEntry(entry=entry, stale=True, detail=failure.message)
    refreshed = entry_for(
        loaded,
        ProjectConfig(name=entry.project or None),
        fingerprint,
        previous=entry,
    )
    search_index.upsert(refreshed)
    return FreshEntry(entry=refreshed, refreshed=True)


def _row_for(
    path: str,
    project: ProjectConfig,
    spec_store: SpecStore,
    fingerprints: Fingerprinter,
    known: dict[str, IndexedAsset],
    unreadable: list[UnreadableSpec],
    validations: ValidationLookup = no_validations,
) -> IndexedAsset | None:
    """One scanned file as a row, or ``None`` with the failure recorded."""
    try:
        loaded = spec_store.load(path)
    except OperationFailed as failure:
        unreadable.append(UnreadableSpec(path=path, reason=failure.message))
        return None
    return entry_for(
        loaded,
        project,
        fingerprints(path),
        previous=known.get(loaded.asset.id.value),
        validation=validations(path),
    )


def _forget_missing(
    search_index: SearchIndex,
    project: str,
    known: dict[str, IndexedAsset],
    indexed: frozenset[str],
) -> tuple[str, ...]:
    """Drop rows for specifications that are no longer in the repository."""
    gone = tuple(sorted(asset_id for asset_id in known if asset_id not in indexed))
    for asset_id in gone:
        search_index.forget(asset_id, project)
    return gone


def _project_name(project: ProjectConfig | None) -> str:
    return (project.name or "") if project else ""


__all__ = [
    "ROOT_DIRECTORY",
    "Fingerprinter",
    "FreshEntry",
    "Progress",
    "RebuildProgress",
    "RebuildReport",
    "UnreadableSpec",
    "current_entry",
    "directory_of",
    "entry_for",
    "no_fingerprints",
    "no_progress",
    "rebuild_index",
]
