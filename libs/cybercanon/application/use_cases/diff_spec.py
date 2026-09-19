"""`diff_spec` — what changed in a specification, as sentences (D10).

A consumer that built against a contract needs to discover that the contract has
moved. A raw file difference answers that badly: it is unreadable in a context
window, it reports reformatting as change, and it says nothing about *meaning*.
So the previous revision is parsed into the same domain objects as the current
one and the two are compared field by field, producing statements a reader can
act on — "triangle budget 12000 → 9000".

Three properties the specification fixes:

* **Durable content only.** Concept, design, constraints, ownership, status and
  the recorded links — the things somebody built against. Nothing here looks at
  annotations: an open thread is not a contract.
* **Unchanged is an answer.** A specification that did not move says so, rather
  than returning an empty list a caller has to interpret.
* **Missing history degrades, it does not fail.** A shallow clone, a file that
  did not exist at that revision, a store with no version control at all — all
  of them produce a difference that reports history as unavailable and keeps the
  session alive. A degraded answer beats a broken tool.

The comparison is *reporting*, not a rule: it produces no verdict and no
severity, and nothing downstream branches on it. That is why it lives here
rather than in the domain, beside the checks that decide whether an export
passes.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from cybercanon.application.ports.search_index import ABSENT
from cybercanon.application.ports.spec_store import (
    HistoryUnavailable,
    SpecNotFound,
    SpecStore,
)
from cybercanon.domain.asset import Asset, Links
from cybercanon.domain.concept import Concept
from cybercanon.domain.constraints import Constraints
from cybercanon.domain.design import Design

UNCHANGED = "the specification is unchanged"
ARROW = "→"

Fields = tuple[tuple[str, str | None], ...]
"""A specification flattened into labelled values, in presentation order."""


@dataclass(frozen=True)
class FieldChange:
    """One field that moved, with both of its values.

    Both sides are carried because "the triangle budget changed" is not
    actionable and "12000 → 9000" is. An absent side reads as *not recorded*,
    which distinguishes a field that was removed from one that was never there.
    """

    label: str
    previous: str | None = None
    current: str | None = None

    @property
    def was_added(self) -> bool:
        return self.previous is None and self.current is not None

    @property
    def was_removed(self) -> bool:
        return self.current is None and self.previous is not None

    def __str__(self) -> str:
        return f"{self.label} {self.previous or ABSENT} {ARROW} {self.current or ABSENT}"


@dataclass(frozen=True)
class SpecDifference:
    """How one specification changed since a revision, or why that is unknown."""

    asset_id: str
    path: str
    revision: str
    changes: tuple[FieldChange, ...] = ()
    available: bool = True
    message: str = ""

    @property
    def is_unchanged(self) -> bool:
        """Whether the comparison ran and found nothing."""
        return self.available and not self.changes

    @property
    def statements(self) -> tuple[str, ...]:
        """The changes as sentences — what a reader is shown."""
        return tuple(str(change) for change in self.changes)

    @property
    def summary(self) -> str:
        """One line: the statement of unavailability, of no change, or the count."""
        if not self.available:
            return self.message
        if not self.changes:
            return f"{UNCHANGED} since {self.revision}"
        return f"{len(self.changes)} change(s) since {self.revision}"

    def change(self, label: str) -> FieldChange | None:
        return next((change for change in self.changes if change.label == label), None)

    def __len__(self) -> int:
        return len(self.changes)


def diff_spec(spec_path: str, revision: str, *, spec_store: SpecStore) -> SpecDifference:
    """Compare a specification with itself at an earlier revision.

    Never raises for want of history: a store that cannot reach the revision
    produces a difference that says so, because a tool that ends the session
    over a shallow clone is worse than one that answers "I cannot see that far
    back".
    """
    current = spec_store.load(spec_path)
    try:
        previous = spec_store.load_at(spec_path, revision)
    except (HistoryUnavailable, SpecNotFound) as failure:
        return SpecDifference(
            asset_id=current.asset.id.value,
            path=spec_path,
            revision=revision,
            available=False,
            message=(
                f"history is unavailable for {spec_path} at revision {revision!r}: "
                f"{failure.message}"
            ),
        )
    return SpecDifference(
        asset_id=current.asset.id.value,
        path=spec_path,
        revision=revision,
        changes=compare(previous.asset, current.asset),
    )


def compare(previous: Asset, current: Asset) -> tuple[FieldChange, ...]:
    """Every durable field whose value differs, in presentation order."""
    before = dict(fields_of(previous))
    after = dict(fields_of(current))
    return tuple(
        FieldChange(label=label, previous=before.get(label), current=after.get(label))
        for label, _ in fields_of(current)
        if before.get(label) != after.get(label)
    )


def fields_of(asset: Asset) -> Fields:
    """One specification flattened into the values a consumer builds against."""
    return (
        *_identity(asset),
        *_concept(asset.concept),
        *_design(asset.design),
        *_constraints(asset.constraints),
        *_links(asset.links),
    )


def _identity(asset: Asset) -> Fields:
    return (
        ("name", asset.name),
        ("status", str(asset.status)),
        ("aliases", _joined(asset.aliases)),
        ("art owner", asset.owner_art),
        ("design owner", asset.owner_design),
        ("code owner", asset.owner_code),
    )


def _concept(concept: Concept | None) -> Fields:
    if concept is None:
        return ()
    return (
        ("concept views", _joined(concept.views)),
        ("silhouette rules", _joined(concept.silhouette_rules)),
    )


def _design(design: Design | None) -> Fields:
    if design is None:
        return ()
    return (
        ("role", design.role),
        ("read distance", _text(design.read_distance_m)),
        ("silhouette priority", design.silhouette_priority),
        ("scale reference", design.scale_ref),
        ("team colour regions", _joined(design.team_color_regions)),
        ("required sockets", _joined(design.socket_names)),
        ("states", _joined(tuple(state.name for state in design.states))),
    )


def _constraints(constraints: Constraints | None) -> Fields:
    if constraints is None:
        return ()
    rig = constraints.rig
    texture = constraints.texture
    animation = constraints.animation
    return (
        ("triangle budget", _text(constraints.tri_budget)),
        ("LOD triangle budgets", _joined(tuple(str(count) for count in constraints.lods))),
        ("up axis", constraints.up_axis),
        ("unit scale", _text(constraints.unit_scale)),
        ("object naming", constraints.naming),
        ("pivot", constraints.pivot),
        ("collider", constraints.collider),
        ("texture size", _text(texture.size if texture else None)),
        ("texture sets", _text(texture.sets if texture else None)),
        ("texture channels", _joined(texture.channels if texture else ())),
        ("skeleton", rig.skeleton if rig else None),
        ("bone budget", _text(rig.max_bones if rig else None)),
        ("clip naming", animation.clip_naming if animation else None),
        ("clip frame rate", _text(animation.frame_rate if animation else None)),
    )


def _links(links: Links | None) -> Fields:
    if links is None:
        return ()
    return (
        ("source file", links.source),
        ("engine path", links.engine),
        ("design document", links.design_doc),
        ("discussion", links.discussion),
    )


def _joined(values: Sequence[str]) -> str | None:
    return ", ".join(values) if values else None


def _text(value: object) -> str | None:
    return None if value is None else str(value)


__all__ = [
    "ARROW",
    "UNCHANGED",
    "FieldChange",
    "Fields",
    "SpecDifference",
    "compare",
    "diff_spec",
    "fields_of",
]
