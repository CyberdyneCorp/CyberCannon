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
  tolerance and yielding an empty :class:`ProjectConfig` when absent (D3).

Every path it hands back is repository-relative POSIX, so a report produced on
one machine reads identically on another.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from cybercanon.adapters.outbound.git import discovery, schema, yaml_io
from cybercanon.application.ports.spec_store import (
    LoadedSpec,
    ProjectConfig,
    SpecNotFound,
    SpecUnreadable,
)
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
        parsed, warnings = self._read(relative, schema.parse_asset_file)
        try:
            asset, mapping_warnings = schema.to_asset(parsed)
        except ValueError as error:
            raise SpecUnreadable(relative, str(error)) from error
        return LoadedSpec(asset=asset, path=relative, warnings=(*warnings, *mapping_warnings))

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

    # -- internals -------------------------------------------------------

    def _read(self, relative: str, parse: Parser) -> tuple[Any, tuple[SpecViolation, ...]]:
        """Read, then shape. Both failure modes name the file rather than the library."""
        path = self._absolute(relative)
        try:
            data = yaml_io.load_mapping(path.read_text(encoding="utf-8"), subject=relative)
        except (OSError, yaml_io.YamlUnreadable) as error:
            raise SpecUnreadable(relative, str(error)) from error
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
