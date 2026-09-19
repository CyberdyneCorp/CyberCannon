"""The vocabulary of failure: one exception, and the kind of answer it is.

A use case has exactly two ways to end: it produces a verdict, or **it could not
run at all**. The second is :class:`OperationFailed`, and it exists so that "the
export is missing", "the format is not in the matrix" and "no `asset.yaml`
governs this file" can never be rendered as a passing report — the failure mode
D13 calls a validator that lies about its coverage, one level up.

`services/cybercanon/cli` maps it to exit code `2` in one seam (D11); every
other surface renders `message` and `subject` and reports the run as not having
happened.

**Two class attributes were added by `add-web-backend` (D10) and they carry the
whole of the outcome vocabulary.** A networked surface has to answer *which kind
of refusal this is* — not found, refused, invalid, conflicting, unavailable —
and it may not decide that for itself, because two endpoints deciding
separately is how the same outcome starts mapping to two status codes. So every
named failure declares its :class:`FailureKind` and its stable `identifier`
**where it is defined**, beside the sentence it raises with, and
:mod:`cybercanon.application.results` turns the declaration into a value. A new
failure that declares neither inherits the conservative pair below: *unavailable*,
identified generically — visible, safe, and obviously in want of a declaration.

Nothing here knows what a status code is. The translation from
:class:`FailureKind` to one is the HTTP adapter's single mapping function, and
it is the only place in the product that has an opinion about numbers.
"""

from __future__ import annotations

from enum import Enum
from typing import ClassVar


class FailureKind(Enum):
    """What kind of answer a failure is, in terms every surface can translate.

    Six members, exactly the six `http-api` enumerates: *"not found, refused for
    lack of permission, refused because the caller is unidentified, rejected as
    invalid input, refused because the resource changed since it was read, and
    refused because a precondition of the domain is unmet"*. There is no
    seventh, and a use case that wanted one would be inventing a refusal no
    surface knows how to render.
    """

    NOT_FOUND = "not_found"
    FORBIDDEN = "forbidden"
    UNAUTHENTICATED = "unauthenticated"
    INVALID = "invalid"
    CONFLICT = "conflict"
    UNAVAILABLE = "unavailable"

    @classmethod
    def values(cls) -> tuple[str, ...]:
        """Every kind, in declaration order."""
        return tuple(member.value for member in cls)

    def __str__(self) -> str:
        return self.value


GENERIC_FAILURE = "operation.failed"
"""The identifier a failure that declared none answers with."""


class OperationFailed(Exception):
    """The operation could not run. Never a verdict, never a passing report.

    Subclasses declare `kind` and `identifier`; the defaults are the
    conservative pair for anything raised generically.
    """

    kind: ClassVar[FailureKind] = FailureKind.UNAVAILABLE
    identifier: ClassVar[str] = GENERIC_FAILURE

    def __init__(self, message: str, subject: str | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.subject = subject


__all__ = ["GENERIC_FAILURE", "FailureKind", "OperationFailed"]
