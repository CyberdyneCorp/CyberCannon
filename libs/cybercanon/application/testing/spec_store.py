"""The in-memory `SpecStore` — assets in a dict, discovery over their paths.

It answers the same three questions `GitSpecStore` answers, over specifications
handed to it rather than parsed from a working copy, so a unit test and a BDD
scenario can state "this asset exists here" in one line and never touch a disk.
The port conformance suite runs this fake and the real adapter through the same
contract, so a divergence between them fails the build rather than the product.

`fail_with` is here because the offline guarantee has to be *testable*: a store
configured to raise stands in for a working copy on an unreachable network
share, and the use-case suite asserts that compilation and validation still
behave (task 4.9).
"""

from __future__ import annotations

from pathlib import PurePosixPath

from cybercanon.application.ports.spec_store import (
    LoadedSpec,
    ProjectConfig,
    SpecNotFound,
    SpecUnreadable,
)
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
        self._raise_if_configured()
        prefix = _normalised(start)
        return tuple(
            path
            for path in sorted(self._specs)
            if prefix in ("", ".") or path == prefix or path.startswith(f"{prefix}/")
        )

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
