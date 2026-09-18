"""Asset identity, ownership, links, and the three authored blocks.

One `asset.yaml` is one :class:`Asset`. The file lives in the game repository
next to the asset it describes and git is the source of truth, so this value
object is what a specification *is*, not a row that mirrors one.

Two rules from `asset-spec` are structural here rather than checked:

* **`id` is stable and `name` is not.** `id` is what every other surface refers
  to; renaming is :meth:`Asset.renamed`, which cannot touch the id.
* **Ownership is per discipline.** Three independent owner fields, none of them
  required, because the format must not assume a single owner per asset.

Each authored block is independently optional: an asset with a concept and
nothing else is a valid specification.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

from cybercanon.domain.annotations import Annotation, open_annotations
from cybercanon.domain.concept import Concept
from cybercanon.domain.constraints import Constraints
from cybercanon.domain.design import Design
from cybercanon.domain.status import Status


@dataclass(frozen=True)
class AssetId:
    """A stable identifier, unique within its project.

    Deliberately a value object rather than a bare `str`: the id is the only
    thing every other surface agrees on, and a type keeps it from being confused
    with a name, a path or a clip.
    """

    value: str

    def __post_init__(self) -> None:
        if not self.value or self.value.strip() != self.value:
            raise ValueError(f"asset id {self.value!r} must be non-empty and unpadded")
        if any(character.isspace() for character in self.value):
            raise ValueError(f"asset id {self.value!r} must not contain whitespace")

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True)
class Links:
    """Where the asset's related artifacts live.

    Values are stored verbatim and are never fetched to read a specification: an
    unreachable URL is not a defect of the spec file.
    """

    source: str | None = None
    engine: str | None = None
    discussion: str | None = None
    design_doc: str | None = None


@dataclass(frozen=True)
class Asset:
    """One specification: identity, lifecycle, ownership and the authored blocks."""

    id: AssetId
    name: str
    status: Status = Status.CONCEPT
    aliases: tuple[str, ...] = ()
    owner_art: str | None = None
    owner_design: str | None = None
    owner_code: str | None = None
    concept: Concept | None = None
    design: Design | None = None
    constraints: Constraints | None = None
    links: Links | None = None
    annotations: tuple[Annotation, ...] = ()

    def renamed(self, name: str) -> Asset:
        """A rename changes the human-readable name and nothing else."""
        return replace(self, name=name)

    @property
    def open_annotations(self) -> tuple[Annotation, ...]:
        """The annotations the compiled briefing carries."""
        return open_annotations(self.annotations)

    @property
    def clip_naming(self) -> str | None:
        """The clip naming convention this asset declares, if it declares one.

        A project default can still supply one; that merge is the effective spec
        (D3), not this property.
        """
        return self.constraints.clip_naming if self.constraints else None

    def refers_to(self, term: str) -> bool:
        """Whether a human-written term names this asset — its id or an alias."""
        return term == self.id.value or term in self.aliases


__all__ = ["Asset", "AssetId", "Links"]
