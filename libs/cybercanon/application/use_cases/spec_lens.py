"""Discipline lenses — one compilation, four projections (D2, D3).

A lens shapes *which parts* of a specification a reader receives, so a modelling
agent needing four constraints is not handed the whole contract. It is
presentation and nothing else, and two decisions keep it that way:

* **D2 — there is one compiler.** A lensed read compiles the specification
  exactly once, through the same :func:`~cybercanon.application.use_cases.compile_spec.compile_spec`
  the CLI calls, and then *removes* content from that document. Every line of a
  lensed response is a line of the full compilation, byte for byte, which is why
  a field presented by two lenses cannot differ between them: there is no second
  renderer that could disagree. Four templates would read better per lens and
  would guarantee that the `design` and `modeling` lenses eventually disagree
  about what the sockets are — and sockets are the closed loop's payload.
* **D3 — authorization happens before the lens.** The order in
  :func:`compile_spec_for_lens` is fixed: authorize the read, then interpret the
  lens, then compile, then project. The lens never reaches the authorization
  decision, so there is no code path on which a lens could widen access — which
  is what makes it safe to let a caller send any lens it likes.

Closed annotations need no rule here: the compiled briefing carries open
annotations only, so a projection over it cannot reveal a resolved or promoted
thread however the lens is written.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import Enum

from cybercanon.application.errors import OperationFailed
from cybercanon.application.ports.search_index import SearchIndex
from cybercanon.application.ports.spec_store import SpecStore
from cybercanon.application.use_cases.briefing import NOTHING_DECLARED
from cybercanon.application.use_cases.compile_spec import CompiledSpec, compile_spec
from cybercanon.application.use_cases.index_assets import Fingerprinter, no_fingerprints
from cybercanon.application.use_cases.lookup_assets import spec_path_for
from cybercanon.application.use_cases.resolve_actor import Resolution, may_read

HEADING_PREFIX = "## "
SECTION_SEPARATOR = " — "
BOLD = "**"
BULLET = "- "

CONCEPT = "Concept"
DESIGN = "Design"
CONSTRAINTS = "Engineering constraints"
OPEN_ISSUES = "Open issues"
LINKS = "Links"

OWNER = "Owner"
SOCKETS = "Required attachment points"
STATES = "States"

EVERYTHING: tuple[str, ...] | None = None
"""What a lens keeping a whole section declares, rather than listing its fields."""


class Lens(Enum):
    """The four discipline lenses. A lens outside the set is refused by name."""

    DESIGN = "design"
    ART = "art"
    MODELING = "modeling"
    CODE = "code"

    @classmethod
    def values(cls) -> tuple[str, ...]:
        """Every accepted lens, in declaration order — what a refusal must name."""
        return tuple(member.value for member in cls)

    @classmethod
    def from_value(cls, value: str) -> Lens | None:
        """The lens this text names, or ``None`` when it names none."""
        return _BY_VALUE.get(value.strip().lower())

    def __str__(self) -> str:
        return self.value


_BY_VALUE = {member.value: member for member in Lens}


PROJECTIONS: Mapping[Lens, Mapping[str, tuple[str, ...] | None]] = {
    Lens.DESIGN: {
        DESIGN: (
            OWNER,
            "Role",
            "Read distance",
            "Silhouette priority",
            "Scale reference",
            SOCKETS,
            STATES,
        ),
        OPEN_ISSUES: ("[design]",),
    },
    Lens.ART: {
        CONCEPT: EVERYTHING,
        OPEN_ISSUES: ("[art-direction]",),
    },
    Lens.MODELING: {
        DESIGN: (SOCKETS,),
        CONSTRAINTS: EVERYTHING,
        OPEN_ISSUES: ("[technical]",),
    },
    Lens.CODE: {
        DESIGN: (SOCKETS,),
        LINKS: EVERYTHING,
    },
}
"""Which sections, and which of their fields, each lens keeps.

Read straight off `spec-lenses`: `design` gets role, states, read distance,
silhouette priority, sockets and scale reference; `art` the concept block;
`modeling` the effective constraints including the required sockets; `code` the
engine path, the recorded links and the sockets it may bind to. The status line
is in the heading, which every lens keeps, because a projection that hid what
the asset *is* would be unreadable.

Annotations are selected by kind — the label of a compiled annotation line is
its kind — so each discipline sees the open issues addressed to it.
"""


OPEN_ISSUES_ONLY: Mapping[str, tuple[str, ...] | None] = {OPEN_ISSUES: EVERYTHING}
"""The projection behind an open-threads read: that one section, whole.

Not a fifth lens — the lens set is closed at four — but the same mechanism over
the same single compilation (D2), which is what makes a resolved or promoted
thread unreachable through it: the compiled briefing carries open annotations
only, so no projection over it can produce a closed one.
"""


class UnknownLens(OperationFailed):
    """A lens outside the defined set. Refused, and the valid ones are named."""

    def __init__(self, lens: str) -> None:
        super().__init__(
            f"{lens!r} is not a lens; the available lenses are "
            f"{', '.join(Lens.values())}, and omitting the lens returns the "
            "full specification",
            lens,
        )


class ReadRefused(OperationFailed):
    """The caller may not read this project. Decided before the lens is looked at."""

    def __init__(self, reason: str, subject: str | None = None) -> None:
        super().__init__(reason, subject)


@dataclass(frozen=True)
class LensedSpec:
    """One compiled specification, projected for a discipline.

    `full` travels with the response because the reader has to know that a
    projection is what they are holding: an agent that took a lensed read for
    the whole truth would model against a subset.
    """

    asset_id: str
    source: str
    body: str
    full: str
    lens: Lens | None = None
    notice: str = ""

    @property
    def is_lensed(self) -> bool:
        return self.lens is not None

    @property
    def text(self) -> str:
        """What a surface shows: the notice, when there is one, then the projection."""
        return f"{self.notice}\n\n{self.body}" if self.notice else self.body

    @property
    def lines(self) -> tuple[str, ...]:
        """The projection's lines — every one of them a line of `full`."""
        return tuple(self.body.splitlines())


def compile_spec_for_lens(
    spec_path: str,
    lens: str | Lens | None = None,
    *,
    spec_store: SpecStore,
    resolution: Resolution,
    project: str,
) -> LensedSpec:
    """Read one specification as a discipline sees it.

    The order is the specification's guarantee and it is fixed here rather than
    left to callers: **authorize, then interpret the lens, then compile, then
    project.** An unentitled caller is refused identically whatever lens it
    sent, because the refusal happens before the lens has been looked at.
    """
    decision = may_read(resolution, project)
    if decision.refused:
        raise ReadRefused(decision.reason, subject=spec_path)
    chosen = _as_lens(lens)
    compiled = compile_spec(spec_path, spec_store=spec_store)
    return project_lens(compiled, chosen)


def project_lens(compiled: CompiledSpec, lens: Lens | None = None) -> LensedSpec:
    """The projection itself: a pure function over one compiled specification.

    Separate from the read so the D2 property is testable on its own — hand it a
    compilation and every lens, and assert that each response is a subset of the
    lines it was given.
    """
    if lens is None:
        return LensedSpec(
            asset_id=compiled.asset_id,
            source=compiled.source,
            body=compiled.text,
            full=compiled.text,
        )
    return LensedSpec(
        asset_id=compiled.asset_id,
        source=compiled.source,
        body=_project(compiled.text, PROJECTIONS[lens]),
        full=compiled.text,
        lens=lens,
        notice=notice_for(lens, compiled.asset_id),
    )


OPEN_THREADS_NOTICE = (
    "> Open threads for `{asset_id}` — this is a projection of the "
    "specification, not the whole of it. The full specification exists and is "
    "returned when no lens is given."
)
"""What an open-threads read says about itself, for the same reason a lens does."""


def notice_for(lens: Lens, asset_id: str) -> str:
    """What every lensed response says about itself.

    Cheap, and it prevents the worst misreading: an agent treating a subset as
    the whole contract and modelling against it.
    """
    return (
        f"> Lens `{lens}` — this is a projection of the specification for "
        f"`{asset_id}`. The full specification exists and is returned when no "
        "lens is given."
    )


def read_asset_spec(
    asset_id: str,
    lens: str | Lens | None = None,
    *,
    spec_store: SpecStore,
    search_index: SearchIndex,
    resolution: Resolution,
    project: str,
    fingerprints: Fingerprinter = no_fingerprints,
) -> LensedSpec:
    """One asset's specification by identifier, as a discipline sees it.

    The same fixed order as :func:`compile_spec_for_lens`, with one step in
    front of it: turning an identifier into the file it names. Authorization
    runs *before* that lookup too, so an unentitled caller is refused
    identically whether the asset it named exists or not — the refusal cannot
    be read as evidence that something is there.
    """
    path = _authorized_path(
        asset_id,
        spec_store=spec_store,
        search_index=search_index,
        resolution=resolution,
        project=project,
        fingerprints=fingerprints,
    )
    return compile_spec_for_lens(
        path, lens, spec_store=spec_store, resolution=resolution, project=project
    )


def read_open_annotations(
    asset_id: str,
    *,
    spec_store: SpecStore,
    search_index: SearchIndex,
    resolution: Resolution,
    project: str,
    fingerprints: Fingerprinter = no_fingerprints,
) -> LensedSpec:
    """The threads still open on one asset, and nothing else.

    Authorized first, like every other read, and projected from the same single
    compilation — so a resolved or promoted thread is not excluded by a filter
    here, it is unreachable from the document this reads.
    """
    path = _authorized_path(
        asset_id,
        spec_store=spec_store,
        search_index=search_index,
        resolution=resolution,
        project=project,
        fingerprints=fingerprints,
    )
    return project_open_issues(compile_spec(path, spec_store=spec_store))


def project_open_issues(compiled: CompiledSpec) -> LensedSpec:
    """One compiled specification reduced to its open issues.

    Returned as a :class:`LensedSpec` carrying the whole compilation, because a
    reader holding a subset has to be able to tell that it is one.
    """
    return LensedSpec(
        asset_id=compiled.asset_id,
        source=compiled.source,
        body=_project(compiled.text, OPEN_ISSUES_ONLY),
        full=compiled.text,
        notice=OPEN_THREADS_NOTICE.format(asset_id=compiled.asset_id),
    )


def _authorized_path(
    asset_id: str,
    *,
    spec_store: SpecStore,
    search_index: SearchIndex,
    resolution: Resolution,
    project: str,
    fingerprints: Fingerprinter,
) -> str:
    """Authorize, then ask the index where the specification is. Never the reverse."""
    decision = may_read(resolution, project)
    if decision.refused:
        raise ReadRefused(decision.reason, subject=asset_id)
    return spec_path_for(
        asset_id,
        spec_store=spec_store,
        search_index=search_index,
        fingerprints=fingerprints,
        project=project or None,
    )


def _as_lens(lens: str | Lens | None) -> Lens | None:
    if lens is None or isinstance(lens, Lens):
        return lens
    chosen = Lens.from_value(lens)
    if chosen is None:
        raise UnknownLens(lens)
    return chosen


# --------------------------------------------------------------------------
# The compiled document, as something a lens can select from
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Item:
    """One field or one sub-block of a section, kept verbatim.

    `lines` are never rewritten — a projection removes items, it does not render
    them again — which is what makes a field's content identical under every
    lens that keeps it.
    """

    label: str
    lines: tuple[str, ...]

    @property
    def is_block(self) -> bool:
        """Whether this is a titled sub-block rather than a single field line."""
        return bool(self.lines) and self.lines[0].startswith(BOLD)


@dataclass
class Section:
    """One `##` section of the compiled briefing."""

    heading: str
    prelude: list[str] = field(default_factory=list)
    items: list[Item] = field(default_factory=list)
    open_lines: list[str] = field(default_factory=list)

    @property
    def key(self) -> str:
        """The section's name without the discipline that authored it."""
        return self.heading.split(SECTION_SEPARATOR)[0].strip()

    def add(self, line: str) -> None:
        """One more line of this section, starting an item where one starts."""
        if not line.strip():
            self.close()
        elif _starts_an_item(line):
            self.close()
            self.open_lines.append(line)
        elif self.open_lines:
            self.open_lines.append(line)
        elif line.strip() != NOTHING_DECLARED:
            self.prelude.append(line)

    def close(self) -> None:
        """End the item being read, if one is open."""
        if self.open_lines:
            self.items.append(Item(label=_label(self.open_lines[0]), lines=tuple(self.open_lines)))
            self.open_lines = []


def _starts_an_item(line: str) -> bool:
    return line.startswith(f"{BULLET}{BOLD}") or line.startswith(BOLD)


def _label(line: str) -> str:
    """The bold label a field or sub-block opens with, without its punctuation."""
    body = line.removeprefix(BULLET)
    if not body.startswith(BOLD):
        return ""
    _, _, rest = body.partition(BOLD)
    label, _, _ = rest.partition(BOLD)
    return label.strip().removesuffix(":")


def _parse(text: str) -> tuple[list[str], list[Section]]:
    """The compiled briefing as a heading block and its sections."""
    heading: list[str] = []
    sections: list[Section] = []
    for line in text.splitlines():
        if line.startswith(HEADING_PREFIX):
            sections.append(Section(heading=line.removeprefix(HEADING_PREFIX).strip()))
        elif sections:
            sections[-1].add(line)
        else:
            heading.append(line)
    for section in sections:
        section.close()
    return heading, sections


def _project(text: str, projection: Mapping[str, tuple[str, ...] | None]) -> str:
    """Keep the heading, then each selected section with its selected items."""
    heading, sections = _parse(text)
    blocks = ["\n".join(heading).strip()]
    for section in sections:
        if section.key not in projection:
            continue
        blocks.append(_render(section, _selected(section, projection[section.key])))
    return "\n\n".join(block for block in blocks if block) + "\n"


def _selected(section: Section, labels: tuple[str, ...] | None) -> list[Item]:
    if labels is None:
        return list(section.items)
    return [item for item in section.items if item.label in labels]


def _render(section: Section, items: list[Item]) -> str:
    """One section, with the kept items in their original order and wording."""
    lines = [f"{HEADING_PREFIX}{section.heading}", ""]
    if section.prelude:
        lines.extend((*section.prelude, ""))
    if not items:
        return "\n".join((*lines, NOTHING_DECLARED))
    for item in items:
        if item.is_block and lines[-1] != "":
            lines.append("")
        lines.extend(item.lines)
    return "\n".join(lines)


__all__ = [
    "CONCEPT",
    "CONSTRAINTS",
    "DESIGN",
    "LINKS",
    "OPEN_ISSUES",
    "OPEN_ISSUES_ONLY",
    "OPEN_THREADS_NOTICE",
    "PROJECTIONS",
    "SOCKETS",
    "STATES",
    "Lens",
    "LensedSpec",
    "ReadRefused",
    "UnknownLens",
    "compile_spec_for_lens",
    "notice_for",
    "project_lens",
    "project_open_issues",
    "read_asset_spec",
    "read_open_annotations",
]
