"""The exit-code seam (D11) — three codes, defined once, stable across releases.

A script, a pre-commit hook and a CI job all read the same three numbers, and
`canon-cli` requires them to stay stable, so they live in one module with
nothing else in it:

* **0** — the operation ran and produced no `error`-severity violation. Warnings
  and not-evaluated rules never move it: they are listed, never fatal.
* **1** — the operation ran and produced at least one `error`-severity
  violation. The verdict, and the only failing verdict there is.
* **2** — the operation *could not run*: a missing export, a format outside the
  matrix, no `asset.yaml` above the path. Distinct from 1 on purpose — "your
  mesh is wrong" and "I could not look at your mesh" are different sentences,
  and a hook that conflated them would tell an artist to fix an export that was
  never read.

The mapping from a use case to a code is :func:`exit_code` and the one `except
OperationFailed` in :mod:`cybercanon.adapters.inbound.cli.app`. There is no
second place a process exit is decided.
"""

from __future__ import annotations

CLEAN = 0
"""Ran, nothing at `error` severity."""

VIOLATIONS = 1
"""Ran, at least one `error`-severity violation."""

COULD_NOT_RUN = 2
"""Did not run at all: the distinct non-zero code `canon-cli` requires."""


def exit_code(passed: bool) -> int:
    """The code for a verdict. An operation that produced none never reaches here."""
    return CLEAN if passed else VIOLATIONS


__all__ = ["CLEAN", "COULD_NOT_RUN", "VIOLATIONS", "exit_code"]
