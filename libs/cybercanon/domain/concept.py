"""The `concept` block — authored by art.

Kept deliberately thin. The golden rule (openspec/project.md) applies to every
authored block: a field either constrains art, constrains code, or is checkable.
`views` names the concept images an :class:`~cybercanon.domain.annotations.Anchor2D`
can be anchored into; `silhouette_rules` are the durable rules an annotation is
promoted into. Free prose about the asset belongs in a design document, linked
through `links`, not here.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Concept:
    """What art has fixed about the asset's look."""

    views: tuple[str, ...] = ()
    silhouette_rules: tuple[str, ...] = ()

    def has_view(self, name: str) -> bool:
        """Whether a 2D anchor naming this view can resolve."""
        return name in self.views


__all__ = ["Concept"]
