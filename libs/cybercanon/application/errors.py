"""The one distinction every inbound adapter maps to an exit code.

A use case has exactly two ways to end: it produces a verdict, or **it could not
run at all**. The second is this exception, and it exists so that "the export is
missing", "the format is not in the matrix" and "no `asset.yaml` governs this
file" can never be rendered as a passing report — the failure mode D13 calls a
validator that lies about its coverage, one level up.

`services/cybercanon/cli` maps it to exit code `2` in one seam (D11); every
other surface renders `message` and `subject` and reports the run as not having
happened.
"""

from __future__ import annotations


class OperationFailed(Exception):
    """The operation could not run. Never a verdict, never a passing report."""

    def __init__(self, message: str, subject: str | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.subject = subject


__all__ = ["OperationFailed"]
