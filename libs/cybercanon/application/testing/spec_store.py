"""The in-memory `SpecStore` — assets in a dict, discovery over their paths.

It answers the same questions `GitSpecStore` answers, over specifications
handed to it rather than parsed from a working copy, so a unit test and a BDD
scenario can state "this asset exists here" in one line and never touch a disk.
The port conformance suite runs this fake and the real adapter through the same
contract, so a divergence between them fails the build rather than the product.

`fail_with` is here because the offline guarantee has to be *testable*: a store
configured to raise stands in for a working copy on an unreachable network
share, and the use-case suite asserts that compilation and validation still
behave (task 4.9).

Two later capabilities are modelled the same way, with no file and no git:

* **history** (D10) — `add_revision` builds a revision series for a path, so
  `diff_spec` can be tested against parsed specifications rather than text, and
  a path with no series reproduces the shallow-clone case the design has to
  degrade through;
* **the actor mapping** (D12) — `set_actor_mapping` serves one,
  `set_actor_mapping_unparseable` reproduces a broken file as a *violation*
  rather than an exception, and a store nobody seeded serves the empty mapping,
  which is what a project without `.canon/actors.yaml` has.
"""

from __future__ import annotations

from pathlib import PurePosixPath

from cybercanon.application.ports.spec_store import (
    HistoryUnavailable,
    LoadedMapping,
    LoadedSpec,
    ProjectConfig,
    SpecNotFound,
    SpecUnreadable,
)
from cybercanon.domain.actor_checks import mapping_unparseable
from cybercanon.domain.actors import ACTORS_PATH, EMPTY_MAPPING, ActorMapping
from cybercanon.domain.asset import Asset
from cybercanon.domain.violations import SpecViolation

SPEC_FILENAME = "asset.yaml"


class InMemorySpecStore:
    """Specifications keyed by their repository-relative path."""

    def __init__(self) -> None:
        self._specs: dict[str, LoadedSpec] = {}
        self._unreadable: dict[str, str] = {}
        self._project = ProjectConfig()
        self._failure: Exception | None = None
        self._history: dict[str, dict[str, LoadedSpec]] = {}
        self._mapping = LoadedMapping()

    # -- seeding ---------------------------------------------------------

    def add(self, path: str, asset: Asset, warnings: tuple[SpecViolation, ...] = ()) -> LoadedSpec:
        """Register one specification at a path, as the store would have parsed it."""
        loaded = LoadedSpec(asset=asset, path=_normalised(path), warnings=warnings)
        self._specs[loaded.path] = loaded
        return loaded

    def add_unreadable(self, path: str, reason: str) -> None:
        """A file that exists and cannot be parsed — :class:`SpecUnreadable` on load."""
        self._unreadable[_normalised(path)] = reason

    def set_project(self, project: ProjectConfig) -> None:
        """The project configuration every discovery under this store resolves to."""
        self._project = project

    def fail_with(self, error: Exception | None) -> None:
        """Make every call raise, to prove a caller's failure handling (task 4.9)."""
        self._failure = error

    def add_revision(
        self,
        path: str,
        revision: str,
        asset: Asset,
        warnings: tuple[SpecViolation, ...] = (),
    ) -> LoadedSpec:
        """Register what this file looked like at an earlier revision (D10).

        Revisions are remembered in the order they are added and handed back
        newest first, which is the order a person reads a log in and the order
        `GitSpecStore` will answer with.
        """
        loaded = LoadedSpec(asset=asset, path=_normalised(path), warnings=warnings)
        self._history.setdefault(loaded.path, {})[revision] = loaded
        return loaded

    def set_actor_mapping(self, mapping: ActorMapping) -> None:
        """The mapping this project authored (D12)."""
        self._mapping = LoadedMapping(mapping=mapping)

    def set_actor_mapping_unparseable(self, detail: str) -> None:
        """A `.canon/actors.yaml` that cannot be read — a violation, never a raise.

        The project keeps the empty mapping and stays fully readable; every
        author simply resolves as unmapped until somebody fixes the file.
        """
        self._mapping = LoadedMapping(
            mapping=EMPTY_MAPPING,
            violations=mapping_unparseable(detail, ACTORS_PATH),
        )

    # -- port ------------------------------------------------------------

    def discover(self, start: str) -> str | None:
        """Walk upward from `start` looking for a registered specification (D9)."""
        self._raise_if_configured()
        for directory in _upward(_normalised(start)):
            candidate = _join(directory, SPEC_FILENAME)
            if candidate in self._specs or candidate in self._unreadable:
                return candidate
        return None

    def load(self, spec_path: str) -> LoadedSpec:
        self._raise_if_configured()
        path = _normalised(spec_path)
        reason = self._unreadable.get(path)
        if reason is not None:
            raise SpecUnreadable(path, reason)
        loaded = self._specs.get(path)
        if loaded is None:
            raise SpecNotFound(path)
        return loaded

    def load_project(self, start: str) -> ProjectConfig:
        self._raise_if_configured()
        return self._project

    def specs_under(self, start: str) -> tuple[str, ...]:
        """Every registered specification under `start`, unreadable ones included.

        A file that cannot be parsed is still a specification file on disk, and
        `GitSpecStore` finds it by walking the tree, so a fake that hid it would
        make "the scan names the files it could not read" untestable — the exact
        shape of lie the conformance suites exist to catch.
        """
        self._raise_if_configured()
        prefix = _normalised(start)
        return tuple(
            path
            for path in sorted((*self._specs, *self._unreadable))
            if prefix in ("", ".") or path == prefix or path.startswith(f"{prefix}/")
        )

    def load_at(self, spec_path: str, revision: str) -> LoadedSpec:
        self._raise_if_configured()
        path = _normalised(spec_path)
        series = self._history.get(path)
        if not series:
            raise HistoryUnavailable(path, revision, "no history was recorded for this file")
        loaded = series.get(revision)
        if loaded is None:
            raise HistoryUnavailable(path, revision, "that revision is not in this history")
        return loaded

    def revisions_for(self, spec_path: str, limit: int | None = None) -> tuple[str, ...]:
        self._raise_if_configured()
        series = tuple(reversed(tuple(self._history.get(_normalised(spec_path), {}))))
        return series[:limit] if limit is not None else series

    def load_actor_mapping(self, start: str = "") -> LoadedMapping:
        """An absent mapping is empty; an unreadable one is empty plus a violation.

        Neither is an exception — a broken identity file must never break a read
        of the repository (D12).
        """
        self._raise_if_configured()
        return self._mapping

    def _raise_if_configured(self) -> None:
        if self._failure is not None:
            raise self._failure


def _normalised(path: str) -> str:
    """Repository-relative POSIX, so a seeded path and a queried one compare equal."""
    return PurePosixPath(path.replace("\\", "/")).as_posix().removeprefix("./")


def _join(directory: str, name: str) -> str:
    return name if directory in ("", ".") else f"{directory}/{name}"


def _upward(start: str) -> tuple[str, ...]:
    """`start` itself when it is a directory, then every parent up to the root.

    The walk is bounded by the store's root exactly as `GitSpecStore`'s is
    bounded by the git root (D9): the last candidate is the repository root
    itself, and there is nothing above it to climb into.
    """
    path = PurePosixPath(start)
    return (path.as_posix(), *[parent.as_posix() for parent in path.parents])


__all__ = ["SPEC_FILENAME", "InMemorySpecStore"]
