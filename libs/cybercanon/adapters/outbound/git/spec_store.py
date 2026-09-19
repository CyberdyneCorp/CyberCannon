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
  identity file must never break a read of the repository.

Every path it hands back is repository-relative POSIX, so a report produced on
one machine reads identically on another.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from cybercanon.adapters.outbound.git import discovery, revisions, schema, yaml_io
from cybercanon.application.ports.spec_store import (
    HistoryUnavailable,
    LoadedMapping,
    LoadedSpec,
    ProjectConfig,
    SpecNotFound,
    SpecUnreadable,
)
from cybercanon.domain.actor_checks import mapping_unparseable
from cybercanon.domain.actors import ACTORS_PATH
from cybercanon.domain.violations import SpecViolation

Parser = Callable[[Mapping[str, Any]], tuple[Any, tuple[SpecViolation, ...]]]
"""Shapes a mapping read off disk, reporting rather than raising where it can."""


class GitSpecStore:
    """Reads `asset.yaml` and `.canon/project.yaml` from a git working copy."""

    def __init__(self, root: str | Path) -> None:
        """Open a store over `root`, or over the repository `root` lives in.

        A directory that is not inside a repository is still usable — a tarball,
        a container image, a temporary directory in a test — and then `root`
        itself bounds the upward walk, which is the same guarantee by a weaker
        means.
        """
        given = Path(root)
        self._root = discovery.find_repository_root(given) or given

    @property
    def root(self) -> Path:
        """The directory every path this store speaks is relative to."""
        return self._root

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
            if self._absolute(candidate).is_file():
                return candidate
        return None

    # -- loading (D4, D5, D6) --------------------------------------------

    def load(self, spec_path: str) -> LoadedSpec:
        """One specification file as a domain asset, with what reading it said."""
        relative = discovery.relative_to(self._root, spec_path)
        if relative is None or not self._absolute(relative).is_file():
            raise SpecNotFound(str(spec_path))
        return self._as_spec(self._text(relative), relative)

    def load_project(self, start: str) -> ProjectConfig:
        """`.canon/project.yaml`, or empty defaults when the repository has none.

        The file carries two kinds of thing and they are kept apart: `defaults`
        is an ordinary constraints block that merges with an asset's own (D3),
        while the engine content root, the per-rule severity table and the
        preview settings are project knobs no asset overrides.
        """
        path = self._root / discovery.PROJECT_CONFIG
        if not path.is_file():
            return ProjectConfig(root=self._posix_root())
        parsed, warnings = self._read(discovery.PROJECT_CONFIG, schema.parse_project_file)
        severities, severity_warnings = schema.to_severities(parsed.severity)
        return ProjectConfig(
            root=self._posix_root(),
            name=parsed.name,
            defaults=schema.to_constraints(parsed.defaults),
            golden_rules=tuple(parsed.golden_rules),
            engine_content_root=parsed.engine_content_root,
            severities=severities,
            preview=schema.to_preview(parsed.preview),
            warnings=(*warnings, *severity_warnings),
        )

    def specs_under(self, start: str) -> tuple[str, ...]:
        """Every specification at or below `start`, in a deterministic order."""
        relative = discovery.relative_to(self._root, start)
        if relative is None:
            return ()
        base = self._absolute(relative)
        if base.is_file():
            return (relative,) if base.name == discovery.SPEC_FILENAME else ()
        found = (discovery.relative_to(self._root, path) for path in self._walk(base))
        return tuple(sorted(path for path in found if path is not None))

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
        path = self._root / ACTORS_PATH
        if not path.is_file():
            return LoadedMapping()
        try:
            parsed = schema.parse_actors_file(self._text(ACTORS_PATH))
        except SpecUnreadable as error:
            return LoadedMapping(violations=mapping_unparseable(error.reason, ACTORS_PATH))
        except ValueError as error:
            return LoadedMapping(violations=mapping_unparseable(_first_line(error), ACTORS_PATH))
        return LoadedMapping(mapping=schema.to_actor_mapping(parsed))

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
        """The file on disk as a mapping, with the read named rather than the library."""
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


def _first_line(error: Exception) -> str:
    """A pydantic failure is a paragraph; a report line needs the first sentence."""
    return str(error).strip().splitlines()[0]


__all__ = ["GitSpecStore"]
