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
  which is the cost D12 accepted rather than inventing a second identity port.

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

from cybercanon.application.errors import OperationFailed
from cybercanon.domain.actors import ACTORS_PATH, EMPTY_MAPPING, ActorMapping
from cybercanon.domain.asset import Asset
from cybercanon.domain.constraints import Constraints
from cybercanon.domain.violations import Severity, SpecViolation

EMPTY_SEVERITIES: Mapping[str, Severity] = MappingProxyType({})
"""The default per-rule severity table: empty, so every rule keeps its own."""


@dataclass(frozen=True)
class LoadedSpec:
    """One specification file: the asset it declares, and what reading it said."""

    asset: Asset
    path: str
    warnings: tuple[SpecViolation, ...] = ()


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

    def __init__(self, subject: str) -> None:
        super().__init__(
            f"no asset.yaml governs {subject}; add one beside the asset or "
            "validate a path inside an asset directory",
            subject=subject,
        )


class SpecUnreadable(OperationFailed):
    """The file is there and cannot be turned into an asset."""

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


__all__ = [
    "EMPTY_SEVERITIES",
    "HistoryUnavailable",
    "LoadedMapping",
    "LoadedSpec",
    "PreviewDefaults",
    "ProjectConfig",
    "SpecNotFound",
    "SpecStore",
    "SpecUnreadable",
]
