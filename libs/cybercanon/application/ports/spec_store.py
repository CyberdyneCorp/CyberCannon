"""The `SpecStore` port — where specifications are read from (D9).

Git is the source of truth (openspec/project.md), so the store is a reader over
a working copy: `GitSpecStore` today, a `PostgresSpecStore` later, with the
domain untouched. Five responsibilities, and the first is the one that keeps
path arithmetic out of every adapter:

* **discovery** — given any path inside the repository, the governing
  `asset.yaml` is found by walking upward, bounded by the repository root (D9).
  `canon validate exports/SM_MechScout_LOD0.glb` has to just work, and the MCP
  server's `where_is` needs the same walk, so it lives here once.
* **loading** — one specification file becomes a domain :class:`Asset`, plus the
  warnings the parse produced. An unknown field is a warning, never a parse
  failure (D5), which is why warnings travel with the asset rather than instead
  of it.
* **project configuration** — the defaults half of the effective-spec merge (D3);
* **history** — the same specification file as it stood at an earlier revision
  (D10), so `diff_spec` compares *parsed specifications* rather than file text.
  It is the one capability in this product that genuinely needs version control
  rather than a file system, and a store that cannot reach the revision says so
  with :class:`HistoryUnavailable` instead of failing the caller's session;
* **the actor mapping** — `.canon/actors.yaml` is repository content like
  `asset.yaml`, so it is fetched here, at the same revision as the specifications
  it explains (D12). It is a project-scoped read beside the asset-scoped ones,
  which is the cost D12 accepted rather than inventing a second identity port;
* **revision pinning** (D3) — :meth:`SpecStore.pinned` hands back a store whose
  *every* read resolves at one revision. The hosted surface resolves the
  revision once per logical operation and reads through the pinned store, so a
  briefing assembled from six files is assembled from one revision by
  construction and a fetch landing mid-read cannot be observed. No lock, and no
  window in which a reader sees a half-updated tree.

D3's accepted cost is that the store grows a second read path, and that the
local "just read the file" path and the server's "read this revision" path must
be covered by the same conformance suite or they will drift — which is why
`tests/conformance/test_spec_store.py` runs the contract over a pinned store as
well as a path-reading one.

**Paths are repository-relative POSIX strings.** An implementation MAY also
accept an absolute path that lies inside its repository, but the paths it hands
back are always relative, so a report, a compiled briefing and a conformance
suite read the same whatever machine produced them.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Protocol

from cybercanon.application.errors import FailureKind, OperationFailed
from cybercanon.domain.actors import ACTORS_PATH, EMPTY_MAPPING, ActorMapping
from cybercanon.domain.asset import Asset
from cybercanon.domain.constraints import Constraints
from cybercanon.domain.documents import DocumentRef
from cybercanon.domain.revisions import ContentHash
from cybercanon.domain.violations import Severity, SpecViolation

PROJECT_CONFIG_PATH = ".canon/project.yaml"
"""Where a project's configuration lives, as a repository-relative POSIX path.

Named here rather than only in the git adapter for the same reason
:data:`~cybercanon.domain.actors.ACTORS_PATH` is named in the domain: a use case
that writes a project-scoped document link has to say *which file it is
writing*, and a use case that had to import an adapter to learn the name would
break the layering to learn a string.
"""

EMPTY_SEVERITIES: Mapping[str, Severity] = MappingProxyType({})
"""The default per-rule severity table: empty, so every rule keeps its own."""


@dataclass(frozen=True)
class LoadedSpec:
    """One specification file: the asset it declares, and what reading it said."""

    asset: Asset
    path: str
    warnings: tuple[SpecViolation, ...] = ()


@dataclass(frozen=True)
class SpecDocument:
    """One specification file as an *editable* thing: its bytes and its meaning.

    :class:`LoadedSpec` answers *what does this file say*, which is all a reader
    ever needed. A writer needs two more facts, and they are the whole of D5:
    the bytes it was composed against — so the precondition a commit states is
    the content hash of what was read, per file and never the branch tip — and
    the revision that content was read at, so a conflict can say what it raced.

    `content` is the file verbatim. Nothing rewrites it on the way in: a
    round trip that normalised the author's formatting would make *"every
    unrelated line is byte-identical"* a property nobody could assert.
    """

    path: str
    content: bytes
    asset: Asset
    warnings: tuple[SpecViolation, ...] = ()
    revision: str = ""

    @property
    def based_on(self) -> ContentHash:
        """The precondition an edit to this document states (D5)."""
        return ContentHash.of(self.content)

    @property
    def loaded(self) -> LoadedSpec:
        """The same document as a reader sees it."""
        return LoadedSpec(asset=self.asset, path=self.path, warnings=self.warnings)


@dataclass(frozen=True)
class PreviewDefaults:
    """What preview emission aims for, as the project configured it (D7).

    Neutral numbers rather than an emitter's own settings type: the port must
    not know which emitter will read them, and preview quality is a
    configuration value, not a rule.
    """

    ratio: float | None = None
    ceiling: int | None = None


@dataclass(frozen=True)
class IngestionDefaults:
    """`ingestion:` — what this project accepts, and how fresh a view must look.

    Neutral optional values rather than a domain type, exactly as
    :class:`PreviewDefaults` is: the port must not know which rule will read
    them, and ``None`` means *this project declared nothing here*, which is
    different from an empty tuple or a zero. The merge with the defaults is
    :meth:`~cybercanon.domain.views.IngestionLimits.declared`, in the domain,
    where the two cannot disagree about it.
    """

    accepted_formats: tuple[str, ...] | None = None
    max_bytes: int | None = None
    max_dimension: int | None = None
    freshness_seconds: float | None = None
    aspect_tolerance: float | None = None


@dataclass(frozen=True)
class ProjectConfig:
    """`.canon/project.yaml` — the defaults half of the merge, and the golden rules.

    `defaults` are ordinary :class:`~cybercanon.domain.constraints.Constraints`
    so the merge (D3) has one shape to reason about; `golden_rules` are the
    project's standing prose, the only thing the project-level briefing carries
    that no asset does.
    """

    root: str = ""
    name: str | None = None
    defaults: Constraints | None = None
    golden_rules: tuple[str, ...] = ()
    engine_content_root: str | None = None
    severities: Mapping[str, Severity] = EMPTY_SEVERITIES
    preview: PreviewDefaults | None = None
    ingestion: IngestionDefaults | None = None
    documents: tuple[DocumentRef, ...] = ()
    """Long-form documents linked at project scope — references, never mirrors.

    `document-platform` puts an asset-scoped link in that asset's specification
    and a project-scoped one here, "so that both are versioned by the repository
    alongside everything else authored there". They are listed beside an asset's
    own links and distinguished from them; nothing about them is resolved at
    this layer.
    """

    warnings: tuple[SpecViolation, ...] = ()

    def severity_for(self, rule_id: str, default: Severity) -> Severity:
        """The severity this project gives a rule, or the rule's own default.

        A project lowers a noisy rule to a warning without editing the rule —
        the mechanism the design calls for: default a rule to `warning`, promote
        it to `error` once the team has seen the noise.
        """
        return self.severities.get(rule_id, default)


class SpecNotFound(OperationFailed):
    """No specification governs that path. Named, never assumed to be clean."""

    kind = FailureKind.NOT_FOUND
    identifier = "spec.not_found"

    def __init__(self, subject: str) -> None:
        super().__init__(
            f"no asset.yaml governs {subject}; add one beside the asset or "
            "validate a path inside an asset directory",
            subject=subject,
        )


class SpecUnreadable(OperationFailed):
    """The file is there and cannot be turned into an asset."""

    kind = FailureKind.INVALID
    identifier = "spec.unreadable"

    def __init__(self, subject: str, reason: str) -> None:
        super().__init__(f"{subject} could not be read as a specification: {reason}", subject)
        self.reason = reason


class HistoryUnavailable(OperationFailed):
    """That revision of that file cannot be reached — a shallow clone, a new file.

    A named failure rather than a silent empty answer, because the caller's
    obligation differs: `diff_spec` reports that history is unavailable for the
    requested range and keeps the session alive, which is the degraded answer
    the design prefers to a broken tool.
    """

    kind = FailureKind.UNAVAILABLE
    identifier = "history.unavailable"

    def __init__(self, subject: str, revision: str, reason: str = "") -> None:
        detail = f": {reason}" if reason else ""
        super().__init__(f"{subject} has no history at revision {revision!r}{detail}", subject)
        self.revision = revision
        self.reason = reason


@dataclass(frozen=True)
class LoadedMapping:
    """`.canon/actors.yaml` as the store found it (D12).

    Three outcomes, and none of them is an exception: a mapping, an absent file
    (the empty mapping — a project without one stays fully readable), and a file
    that cannot be parsed, which yields the empty mapping *plus* the violation
    saying so. Raising would make a broken identity file break every read of the
    repository, which is precisely the failure D14 refuses in miniature.
    """

    mapping: ActorMapping = EMPTY_MAPPING
    violations: tuple[SpecViolation, ...] = ()
    path: str = ACTORS_PATH

    @property
    def is_declared(self) -> bool:
        """Whether this project actually authored a mapping."""
        return not self.mapping.is_empty

    @property
    def is_readable(self) -> bool:
        """Whether the file could be parsed at all."""
        return not self.violations


class SpecStore(Protocol):
    """Reads specifications and project configuration out of a repository."""

    def current_revision(self) -> str | None:
        """The revision this store is reading at, or ``None`` when it reads a tree.

        A store over a working copy answers the revision its checkout is on; a
        directory that is not a repository answers ``None``, which is an answer
        rather than a failure — the CLI has never needed one.
        """
        ...

    def pinned(self, revision: str) -> SpecStore:
        """This same store, with every read resolved at that revision (D3).

        The returned store answers the same questions from the repository's
        object database rather than from the checked-out tree, so nothing it
        hands back can change while a fetch is in progress. Raises
        :class:`HistoryUnavailable` when the revision cannot be reached at all.
        """
        ...

    def discover(self, start: str) -> str | None:
        """The governing specification for `start`, found by walking upward (D9).

        ``None`` when the walk reaches the repository root without finding one —
        an answer, not an error: a file belonging to no asset is the pre-commit
        hook's ordinary case.
        """
        ...

    def load(self, spec_path: str) -> LoadedSpec:
        """One specification file as a domain asset, with its parse warnings (D5).

        Raises :class:`SpecNotFound` when there is no such file and
        :class:`SpecUnreadable` when there is one and it cannot be parsed.
        """
        ...

    def load_project(self, start: str) -> ProjectConfig:
        """The project configuration governing `start`.

        A repository with no `.canon/project.yaml` yields an empty
        :class:`ProjectConfig`, so every asset-level declaration still applies.
        """
        ...

    def specs_under(self, start: str) -> tuple[str, ...]:
        """Every specification at or below `start`, in a deterministic order."""
        ...

    def load_at(self, spec_path: str, revision: str) -> LoadedSpec:
        """The specification as it stood at an earlier revision (D10).

        The same parse as :meth:`load`, so the comparison is between domain
        objects and never between two renderings of a file. Raises
        :class:`HistoryUnavailable` when the store cannot reach that revision
        and :class:`SpecNotFound` when the file did not exist there.
        """
        ...

    def revisions_for(self, spec_path: str, limit: int | None = None) -> tuple[str, ...]:
        """The revisions that touched this file, newest first.

        Empty when the store has no history to offer — a directory that is not a
        repository, or a shallow clone. Empty is an answer; a caller that needed
        a specific revision gets :class:`HistoryUnavailable` from
        :meth:`load_at`.
        """
        ...

    def load_actor_mapping(self, start: str = "") -> LoadedMapping:
        """The project's `.canon/actors.yaml`, read at the same revision as the specs.

        Never raises: an absent file is the empty mapping and an unparseable one
        is the empty mapping with a violation naming the file (D12).
        """
        ...

    # -- editing (add-model-sheet-2d, D4 and D5) --------------------------

    def read_document(self, spec_path: str, revision: str | None = None) -> SpecDocument:
        """The file, its bytes and its parsed meaning, at a revision or as it stands.

        The read half of the write path. `revision` of ``None`` reads what the
        store is already reading at — its pin, or the checkout — so a caller
        that has not chosen a revision does not have to invent one.

        Raises :class:`SpecNotFound` when there is no such file,
        :class:`SpecUnreadable` when there is one and it cannot be parsed, and
        :class:`HistoryUnavailable` for a revision the store cannot reach.
        """
        ...

    def parse_document(self, spec_path: str, content: bytes) -> SpecDocument:
        """These bytes as a specification, without going back to the repository.

        What a retry needs: the same parse applied to content the caller already
        holds, so re-applying a domain operation after a conflict re-reads the
        file rather than the caller's memory of it.
        """
        ...

    def edited_project(self, content: bytes, documents: tuple[DocumentRef, ...]) -> bytes:
        """`.canon/project.yaml` carrying these project-scoped document links.

        The one edit the project configuration accepts, and the narrowest
        signature that could express it: no asset, no constraints, no golden
        rules — a caller cannot rewrite the project's defaults through the door
        that exists to add a link. Comments and key order survive it exactly as
        they survive :meth:`edited`, because it is the same round trip.

        `content` of ``b""`` composes a new file, which is what a project that
        has never had a `.canon/project.yaml` needs.
        """
        ...

    def edited(self, document: SpecDocument, asset: Asset) -> bytes:
        """The same file carrying this asset's edits — comments and order kept (D4).

        Only what the edit changed is written: the annotation list, the concept
        block's durable rules and the engineering constraints. Every other line
        of the document comes back byte-identical, which is the property the
        artists' trust in this tool rests on, and it is asserted rather than
        promised — `tests/integration/test_spec_round_trip.py` adds, replies to
        and resolves an annotation in a hand-authored file and compares the rest
        line by line.
        """
        ...


__all__ = [
    "EMPTY_SEVERITIES",
    "PROJECT_CONFIG_PATH",
    "HistoryUnavailable",
    "IngestionDefaults",
    "LoadedMapping",
    "LoadedSpec",
    "PreviewDefaults",
    "ProjectConfig",
    "SpecDocument",
    "SpecNotFound",
    "SpecStore",
    "SpecUnreadable",
]
