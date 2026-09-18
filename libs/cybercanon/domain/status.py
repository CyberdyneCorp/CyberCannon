"""The asset lifecycle: an ordered set, not a free-text label.

`asset-spec` fixes the set and its order — `concept`, `approved`, `modeling`,
`validated`, `in-engine` — and requires a value outside it to be reported as a
violation of the specification file rather than silently accepted. The order is
the declaration order below; nothing else may encode it.
"""

from __future__ import annotations

from enum import Enum
from typing import Any


class Status(Enum):
    """Where an asset sits in its lifecycle. Declaration order is the order."""

    CONCEPT = "concept"
    APPROVED = "approved"
    MODELING = "modeling"
    VALIDATED = "validated"
    IN_ENGINE = "in-engine"

    @property
    def rank(self) -> int:
        """Position in the lifecycle, counting from `concept` at 0."""
        return list(type(self)).index(self)

    @classmethod
    def values(cls) -> tuple[str, ...]:
        """Every accepted value, in lifecycle order — what a message must name."""
        return tuple(member.value for member in cls)

    @classmethod
    def from_value(cls, value: str) -> Status | None:
        """The status this text declares, or ``None`` when it declares none.

        Returning ``None`` rather than raising is deliberate: an unknown status
        is a reportable violation of the file (`spec.unknown_status`), and a
        parse error would deny the artist every other finding in the same run.
        """
        return _BY_VALUE.get(value)

    def __lt__(self, other: Any) -> Any:
        if not isinstance(other, Status):
            return NotImplemented
        return self.rank < other.rank

    def __le__(self, other: Any) -> Any:
        if not isinstance(other, Status):
            return NotImplemented
        return self.rank <= other.rank

    def __gt__(self, other: Any) -> Any:
        if not isinstance(other, Status):
            return NotImplemented
        return self.rank > other.rank

    def __ge__(self, other: Any) -> Any:
        if not isinstance(other, Status):
            return NotImplemented
        return self.rank >= other.rank

    def __str__(self) -> str:
        return self.value


_BY_VALUE = {member.value: member for member in Status}

__all__ = ["Status"]
