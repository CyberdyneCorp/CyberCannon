"""`GitSpecStore` — specifications read straight out of a working copy.

Git is the source of truth (openspec/project.md), so this is the real
`SpecStore`: a reader over a checkout, with no database, no service and no
network anywhere in the path. Deleting every derived index and re-scanning the
repository is always a valid recovery, because the repository is the only thing
that was ever authoritative.

What it owes the port, and where each piece lives:

* **discovery** walks upward bounded by the git root —
  :mod:`cybercanon.adapters.outbound.git.discovery` (D9);
* **loading** is `ruamel.yaml` for the file and pydantic for the shape —
  :mod:`~cybercanon.adapters.outbound.git.yaml_io` and
  :mod:`~cybercanon.adapters.outbound.git.schema` (D4, D5, D6);
* **project configuration** is `.canon/project.yaml`, read with the same
  tolerance and yielding an empty :class:`ProjectConfig` when absent (D3);
* **history** is the working copy's own history —
  :mod:`~cybercanon.adapters.outbound.git.revisions` (D10). It is the only
  capability here that needs version control rather than a file system, and a
  repository that cannot reach the requested revision — a shallow clone, a file
  nobody has committed — says so rather than failing the caller's session;
* **the actor mapping** is `.canon/actors.yaml`, read from the same working copy
  as the specifications it explains (D12). Absent is the empty mapping and
  unreadable is the empty mapping plus a violation naming the file: a broken
  identity file must never break a read of the repository;
* **revision pinning** is :meth:`GitSpecStore.pinned` (D3). A pinned store is the
  same object over the same repository with one field set, and every read it
  makes goes to the object database at that revision instead of to the checkout:
  the tracked paths come from a tree listing rather than a directory walk, and
  the bytes come from `git show`. That is what makes read isolation structural —
  a fetch moves a ref, and a reader holding a revision never notices.

**One parse, two sources.** The pinned path and the tree path differ in where
the bytes come from and in nothing else, so a specification means the same thing
whichever way it was read; the port conformance suite runs the whole contract
over both for exactly that reason.

Every path it hands back is repository-relative POSIX, so a report produced on
one machine reads identically on another.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from cybercanon.adapters.outbound.git import discovery, revisions, schema, writer, yaml_io
from cybercanon.application.ports.spec_store import (
    HistoryUnavailable,
    LoadedMapping,
    LoadedSpec,
    ProjectConfig,
    SpecDocument,
    SpecNotFound,
    SpecUnreadable,
)
from cybercanon.domain.actor_checks import mapping_unparseable
from cybercanon.domain.actors import ACTORS_PATH
from cybercanon.domain.asset import Asset
from cybercanon.domain.documents import DocumentRef
from cybercanon.domain.violations import SpecViolation

Parser = Callable[[Mapping[str, Any]], tuple[Any, tuple[SpecViolation, ...]]]
"""Shapes a mapping read off disk, reporting rather than raising where it can."""


class GitSpecStore:
    """Reads `asset.yaml` and `.canon/project.yaml` from a git working copy."""

    def __init__(self, root: str | Path, *, revision: str | None = None) -> None:
        """Open a store over `root`, or over the repository `root` lives in.

        A directory that is not inside a repository is still usable — a tarball,
        a container image, a temporary directory in a test — and then `root`
        itself bounds the upward walk, which is the same guarantee by a weaker
        means.

        `revision` pins every read to one revision (D3) and is set through
        :meth:`pinned` rather than by callers, so a pinned store is always one
        that resolved its revision first.
        """
        given = Path(root)
        self._root = discovery.find_repository_root(given) or given
        self._revision = revision
        self._tracked: frozenset[str] | None = None

    @property
    def root(self) -> Path:
        """The directory every path this store speaks is relative to."""
        return self._root

    # -- revision pinning (D3) -------------------------------------------

    @property
    def revision(self) -> str | None:
        """The revision this store reads at, or ``None`` when it reads the tree."""
        return self._revision

    def current_revision(self) -> str | None:
        """What this store is reading at: its pin, or the checkout's own head."""
        if self._revision is not None:
            return self._revision
        try:
            return revisions.resolve(self._root, "HEAD")
        except revisions.RevisionUnreachable:
            return None

    def pinned(self, revision: str) -> GitSpecStore:
        """This store with every read resolved at that revision.

        The revision is resolved to a commit here rather than lazily, so a
        revision the repository cannot reach fails once, at the point somebody
        chose it, instead of failing differently on each of six file reads.
        """
        try:
            resolved = revisions.resolve(self._root, revision)
        except revisions.RevisionUnreachable as error:
            raise HistoryUnavailable(self._posix_root(), revision, str(error)) from error
        return GitSpecStore(self._root, revision=resolved)

    def _exists(self, relative: str) -> bool:
        """Whether that path is present — in the pinned tree, or on disk."""
        if self._revision is None:
            return self._absolute(relative).is_file()
        return relative in self._paths()

    def _paths(self) -> frozenset[str]:
        """Every tracked path at the pinned revision, read once and remembered.

        Cached because a pinned store is immutable by construction: the tree at
        a revision cannot change, so asking git again would only cost a process.
        """
        if self._tracked is None:
            self._tracked = frozenset(revisions.paths_at(self._root, self._revision or "HEAD"))
        return self._tracked

    # -- discovery (D9) --------------------------------------------------

    def discover(self, start: str) -> str | None:
        """The governing specification for `start`, or ``None`` — never an error.

        A file belonging to no asset is the pre-commit hook's ordinary case, so
        it is an answer rather than a failure.
        """
        relative = discovery.relative_to(self._root, start)
        if relative is None:
            return None
        for directory in discovery.upward(relative):
            candidate = discovery.join(directory, discovery.SPEC_FILENAME)
            if self._exists(candidate):
                return candidate
        return None

    # -- loading (D4, D5, D6) --------------------------------------------

    def load(self, spec_path: str) -> LoadedSpec:
        """One specification file as a domain asset, with what reading it said."""
        relative = discovery.relative_to(self._root, spec_path)
        if relative is None or not self._exists(relative):
            raise SpecNotFound(str(spec_path))
        return self._as_spec(self._text(relative), relative)

    def load_project(self, start: str) -> ProjectConfig:
        """`.canon/project.yaml`, or empty defaults when the repository has none.

        The file carries two kinds of thing and they are kept apart: `defaults`
        is an ordinary constraints block that merges with an asset's own (D3),
        while the engine content root, the per-rule severity table and the
        preview settings are project knobs no asset overrides.
        """
        if not self._exists(discovery.PROJECT_CONFIG):
            return ProjectConfig(root=self._posix_root())
        parsed, warnings = self._read(discovery.PROJECT_CONFIG, schema.parse_project_file)
        severities, severity_warnings = schema.to_severities(parsed.severity)
        documents, document_warnings = schema.to_documents(parsed.documents, "documents")
        return ProjectConfig(
            root=self._posix_root(),
            name=parsed.name,
            defaults=schema.to_constraints(parsed.defaults),
            golden_rules=tuple(parsed.golden_rules),
            engine_content_root=parsed.engine_content_root,
            severities=severities,
            preview=schema.to_preview(parsed.preview),
            ingestion=schema.to_ingestion(parsed.ingestion),
            documents=documents,
            warnings=(*warnings, *severity_warnings, *document_warnings),
        )

    def specs_under(self, start: str) -> tuple[str, ...]:
        """Every specification at or below `start`, in a deterministic order."""
        relative = discovery.relative_to(self._root, start)
        if relative is None:
            return ()
        if self._revision is not None:
            return self._specs_at(relative)
        base = self._absolute(relative)
        if base.is_file():
            return (relative,) if base.name == discovery.SPEC_FILENAME else ()
        found = (discovery.relative_to(self._root, path) for path in self._walk(base))
        return tuple(sorted(path for path in found if path is not None))

    def _specs_at(self, relative: str) -> tuple[str, ...]:
        """Every specification at or below `relative` in the pinned tree."""
        prefix = "" if relative in ("", ".") else f"{relative}/"
        return tuple(
            sorted(
                path
                for path in self._paths()
                if path.endswith(discovery.SPEC_FILENAME)
                and (path == relative or path.startswith(prefix))
            )
        )

    # -- history (D10) ---------------------------------------------------

    def load_at(self, spec_path: str, revision: str) -> LoadedSpec:
        """The specification as it stood at an earlier revision.

        Parsed by the same path :meth:`load` uses, so `diff_spec` compares
        domain objects and never two renderings of a file.
        """
        relative = discovery.relative_to(self._root, spec_path)
        if relative is None:
            raise SpecNotFound(str(spec_path))
        return self._as_spec(self._text_at(relative, revision), relative)

    def revisions_for(self, spec_path: str, limit: int | None = None) -> tuple[str, ...]:
        """The commits that touched this file, newest first — empty when there are none.

        A path outside the repository, a file nobody committed and a directory
        that is not a repository all answer empty, because all three mean there
        is nothing to compare against. A caller that needed one specific
        revision learns that from :meth:`load_at` instead.
        """
        relative = discovery.relative_to(self._root, spec_path)
        if relative is None:
            return ()
        return revisions.revisions(self._root, relative, limit)

    # -- the actor mapping (D12) -----------------------------------------

    def load_actor_mapping(self, start: str = "") -> LoadedMapping:
        """`.canon/actors.yaml` from this working copy. Never raises.

        Three outcomes and none of them is an exception: the mapping the project
        authored, the empty mapping for a project that authored none, and the
        empty mapping plus a violation naming the file for one nobody can parse.
        A repository whose identity file is broken still reads every
        specification it holds; its authors simply resolve as unmapped until
        somebody fixes the file.
        """
        if not self._exists(ACTORS_PATH):
            return LoadedMapping()
        try:
            parsed = schema.parse_actors_file(self._text(ACTORS_PATH))
        except SpecUnreadable as error:
            return LoadedMapping(violations=mapping_unparseable(error.reason, ACTORS_PATH))
        except ValueError as error:
            return LoadedMapping(violations=mapping_unparseable(_first_line(error), ACTORS_PATH))
        return LoadedMapping(mapping=schema.to_actor_mapping(parsed))

    # -- editing (add-model-sheet-2d, D4 and D5) --------------------------

    def read_document(self, spec_path: str, revision: str | None = None) -> SpecDocument:
        """The file verbatim, its meaning, and the revision it was read at.

        The bytes come back untouched — no reformatting on the way in — because
        the precondition an edit states is the digest of *these* bytes, and a
        normalising read would make it the digest of something nobody has.
        """
        relative = discovery.relative_to(self._root, spec_path)
        if relative is None:
            raise SpecNotFound(str(spec_path))
        at = revision if revision is not None else self._revision
        text = self._verbatim(relative, at)
        return self._document(relative, text, at or self.current_revision() or "")

    def parse_document(self, spec_path: str, content: bytes) -> SpecDocument:
        """These bytes as a specification, without going back to the repository."""
        relative = discovery.relative_to(self._root, spec_path) or spec_path
        return self._document(relative, _decoded(content, relative), "")

    def edited(self, document: SpecDocument, asset: Asset) -> bytes:
        """The document with this asset's edits applied, comments intact (D4)."""
        text = _decoded(document.content, document.path)
        return writer.render(text, asset, document.asset).encode("utf-8")

    def edited_project(self, content: bytes, documents: tuple[DocumentRef, ...]) -> bytes:
        """The project configuration carrying these links, every other line intact."""
        text = _decoded(content, discovery.PROJECT_CONFIG) if content else ""
        return writer.render_project(text, documents).encode("utf-8")

    def _document(self, relative: str, text: str, revision: str) -> SpecDocument:
        """One already-read file as an editable document."""
        loaded = self._as_spec(self._mapping_of(text, relative), relative)
        return SpecDocument(
            path=relative,
            content=text.encode("utf-8"),
            asset=loaded.asset,
            warnings=loaded.warnings,
            revision=revision,
        )

    def _verbatim(self, relative: str, revision: str | None) -> str:
        """The file's text, from a revision when one is named and from disk when not."""
        if revision is not None:
            return self._text_at_revision(relative, revision)
        if not self._exists(relative):
            raise SpecNotFound(relative)
        try:
            return self._absolute(relative).read_text(encoding="utf-8")
        except OSError as error:
            raise SpecUnreadable(relative, str(error)) from error

    def _text_at_revision(self, relative: str, revision: str) -> str:
        """That file at that revision, keeping the two ways it can be missing apart."""
        try:
            return revisions.file_at(self._root, revision, relative)
        except revisions.RevisionUnreachable as error:
            raise HistoryUnavailable(relative, revision, str(error)) from error
        except revisions.PathAbsent as error:
            raise SpecNotFound(relative) from error

    # -- internals -------------------------------------------------------

    def _as_spec(self, data: dict[str, Any], relative: str) -> LoadedSpec:
        """One already-read file as a domain asset — the shared half of every load."""
        parsed, warnings = self._shape(data, relative, schema.parse_asset_file)
        try:
            asset, mapping_warnings = schema.to_asset(parsed)
        except ValueError as error:
            raise SpecUnreadable(relative, str(error)) from error
        return LoadedSpec(asset=asset, path=relative, warnings=(*warnings, *mapping_warnings))

    def _text_at(self, relative: str, revision: str) -> dict[str, Any]:
        """That file at that revision, with the two ways it can be missing kept apart.

        A revision this repository cannot reach is
        :class:`HistoryUnavailable` — the degraded answer a shallow clone gets,
        and the one `diff_spec` reports rather than failing over. A file that is
        simply not in an otherwise reachable revision is
        :class:`SpecNotFound`, unless it has no history at all, which is the
        same *unavailable* answer by another route.
        """
        try:
            text = revisions.file_at(self._root, revision, relative)
        except revisions.RevisionUnreachable as error:
            raise HistoryUnavailable(relative, revision, str(error)) from error
        except revisions.PathAbsent as error:
            if not self.revisions_for(relative):
                raise HistoryUnavailable(
                    relative, revision, "this file has no history in this repository"
                ) from error
            raise SpecNotFound(relative) from error
        return self._mapping_of(text, relative)

    def _text(self, relative: str) -> dict[str, Any]:
        """That file as a mapping — from the pinned revision, or from disk.

        The one place the two read paths differ. Everything above it is the same
        parse over the same bytes, which is what keeps a pinned read and a tree
        read from ever meaning different things.
        """
        if self._revision is not None:
            return self._text_at(relative, self._revision)
        try:
            return self._mapping_of(self._absolute(relative).read_text(encoding="utf-8"), relative)
        except OSError as error:
            raise SpecUnreadable(relative, str(error)) from error

    def _mapping_of(self, text: str, relative: str) -> dict[str, Any]:
        try:
            return yaml_io.load_mapping(text, subject=relative)
        except yaml_io.YamlUnreadable as error:
            raise SpecUnreadable(relative, _first_line(error)) from error

    def _read(self, relative: str, parse: Parser) -> tuple[Any, tuple[SpecViolation, ...]]:
        """Read, then shape. Both failure modes name the file rather than the library."""
        return self._shape(self._text(relative), relative, parse)

    def _shape(
        self, data: dict[str, Any], relative: str, parse: Parser
    ) -> tuple[Any, tuple[SpecViolation, ...]]:
        """Turn a read mapping into its parsed shape, naming the file on failure."""
        try:
            return parse(data)
        except schema.SchemaTooNew as error:
            raise SpecUnreadable(relative, str(error)) from error
        except ValueError as error:
            raise SpecUnreadable(relative, _first_line(error)) from error

    def _walk(self, base: Path) -> tuple[Path, ...]:
        return tuple(base.rglob(discovery.SPEC_FILENAME))

    def _absolute(self, relative: str) -> Path:
        return self._root / relative if relative not in ("", ".") else self._root

    def _posix_root(self) -> str:
        return self._root.as_posix()


def _decoded(content: bytes, subject: str) -> str:
    """The bytes as text, refusing anything that is not a readable file."""
    try:
        return content.decode("utf-8")
    except UnicodeDecodeError as error:
        raise SpecUnreadable(subject, "the file is not UTF-8 text") from error


def _first_line(error: Exception) -> str:
    """A pydantic failure is a paragraph; a report line needs the first sentence."""
    return str(error).strip().splitlines()[0]


__all__ = ["GitSpecStore"]
