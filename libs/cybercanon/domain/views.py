"""Concept views: slots, image facts, ingestion limits and the carry-forward rule.

The boundary `add-asset-spec-and-validator` drew for meshes is drawn again here,
deliberately and without re-arguing it (D1): **image reading is a port, image
rules are the domain.** An `ImageInspector` turns bytes into a frozen
:class:`ImageFacts`; everything that *decides* — is this format accepted, is it
too big, does replacing this view keep its pins — is a pure function in this
module over that value object. The payoff is the one `MeshFacts` already paid:
every format, size, slot and carry-forward test is a constructed `ImageFacts`
with no file on disk anywhere.

Four ideas live here and each is a sentence of `concept-ingestion` or
`view-versioning`:

* **A slot is an address, not a label** (D4). `front`, `side` and `back` are
  canonical; any other lowercase name is an arbitrary named view. The slot is
  what :class:`~cybercanon.domain.annotations.Anchor2D` keys on, so it has to be
  stable, which is why :func:`view_path` derives the file path from it and from
  nothing else.
* **A view is one file per slot, replaced in place** (D4). That is what makes
  git produce a *revision* rather than an unrelated file, and it is why a format
  change is a rename of the old path followed by a write rather than a delete
  and an add.
* **Acceptance is arithmetic over facts.** Format, byte size and pixel
  dimensions, each rejected with the observed value and the allowed one, and
  *at* the limit is accepted — a limit that rejected its own value would be a
  limit nobody could state.
* **Carry-forward is decided by aspect ratio** (D6). A normalised `u,v` anchor
  stays meaningful under a pure rescale and stops being meaningful under a crop,
  and aspect ratio is the cheapest honest proxy for that distinction. Nothing
  here infers a new position for a pin: the two answers are *carried* and
  *orphaned*, and there is no third.

`hashlib` reaches this module only through
:class:`~cybercanon.domain.revisions.ContentHash`, so the domain's stdlib-only
import contract holds.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, replace
from datetime import datetime

from cybercanon.domain.annotations import AnchorState
from cybercanon.domain.revisions import ContentHash
from cybercanon.domain.violations import Severity, SpecViolation

CANONICAL_SLOTS: tuple[str, ...] = ("front", "side", "back")
"""The three slots every surface may assume exist by name.

Canonical rather than exclusive: `concept-ingestion` accepts any well-formed
name as an arbitrary named view, because a studio that needs
`three_quarter_left` should not have to ask for a schema change.
"""

MAX_SLOT_LENGTH = 32
"""How long a slot name may be. It becomes a file name; file names have limits."""

SLOT_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_]*$")
"""Lowercase letters, digits and underscores, beginning with a letter or digit.

Deliberately narrow: the slot is a path segment on every platform the working
copy is ever checked out on, and a name that is only legal on one of them is a
repository that cannot be cloned.
"""

CONCEPT_DIR = "concept"
"""The directory a view lives in, beside the asset's `asset.yaml` (D4)."""


class InvalidSlotName(ValueError):
    """The supplied slot name is not one. Raised naming the offending value.

    A `ValueError` because it is the domain refusing to construct something that
    is not a slot — the same discipline
    :class:`~cybercanon.domain.requests.AssetRequest` uses for a request with
    nothing in it. The application turns it into the outcome vocabulary.
    """

    def __init__(self, value: str) -> None:
        super().__init__(
            f"{value!r} is not a valid slot name: a slot is lowercase letters, digits "
            f"and underscores, begins with a letter or digit and is at most "
            f"{MAX_SLOT_LENGTH} characters"
        )
        self.value = value


@dataclass(frozen=True)
class ViewSlot:
    """Which view of an asset an image is. One slot, one file, one address.

    A value object rather than a bare `str` for the reason
    :class:`~cybercanon.domain.asset.AssetId` is one: the slot is what an anchor
    keys on and what a path is derived from, and a validated type is what stops
    `Front View!` from ever reaching either.
    """

    name: str

    def __post_init__(self) -> None:
        if not is_valid_slot(self.name):
            raise InvalidSlotName(self.name)

    @property
    def is_canonical(self) -> bool:
        """Whether this is one of the three slots every surface knows by name."""
        return self.name in CANONICAL_SLOTS

    def __str__(self) -> str:
        return self.name


def is_valid_slot(name: str) -> bool:
    """Whether this text names a slot. Empty is not a slot, and neither is `Front View!`."""
    return bool(name) and len(name) <= MAX_SLOT_LENGTH and SLOT_PATTERN.match(name) is not None


# --------------------------------------------------------------------------
# What an image is, as far as the domain is concerned (D1)
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class ImageFacts:
    """Six facts about an image, and nothing about how they were read (D1).

    The mesh boundary, again: a port produces this from bytes, the domain
    decides over it. `format` is the lowercase name the inspector detected **from
    the content** — never from a file name, because `concept-ingestion` requires
    a TIFF called `.png` to be rejected as a TIFF.
    """

    format: str
    width: int
    height: int
    byte_size: int
    content_hash: ContentHash
    has_alpha: bool = False

    def __post_init__(self) -> None:
        if self.width <= 0 or self.height <= 0:
            raise ValueError(
                f"an image is {self.width}x{self.height}; both dimensions must be positive"
            )

    @property
    def aspect(self) -> float:
        """Width over height — the one number the carry-forward rule reads (D6)."""
        return self.width / self.height

    @property
    def dimensions(self) -> str:
        """`1024x768`, for a message that has to state what was observed."""
        return f"{self.width}x{self.height}"

    @property
    def largest_dimension(self) -> int:
        """The side a dimension limit is compared against."""
        return max(self.width, self.height)


# --------------------------------------------------------------------------
# The limits a project declares, and the three rules over them
# --------------------------------------------------------------------------

DEFAULT_FORMATS: tuple[str, ...] = ("png", "jpeg", "webp")
"""The accepted set a project that declares none is measured against."""

DEFAULT_MAX_BYTES = 25 * 1024 * 1024
"""25 MB. Large enough for ordinary concept art, small enough not to need LFS."""

DEFAULT_MAX_DIMENSION = 8192
"""8192 pixels on the longest side — a 4K board at double resolution."""

FORMAT_UNSUPPORTED = "format.unsupported"
SIZE_EXCEEDED = "size.exceeded"
DIMENSION_EXCEEDED = "dimension.exceeded"
"""The three rule identifiers. Stable, because a refusal is acted on by its id."""


@dataclass(frozen=True)
class IngestionLimits:
    """What this project accepts: formats, bytes and pixels.

    Three independent values, each overridable on its own, because a project
    that wants to raise the pixel ceiling should not have to restate the format
    set to do it. :meth:`declared` is the merge, and it is the only one — a
    second place that filled in a default would be a second set of defaults.
    """

    accepted_formats: tuple[str, ...] = DEFAULT_FORMATS
    max_bytes: int = DEFAULT_MAX_BYTES
    max_dimension: int = DEFAULT_MAX_DIMENSION

    @classmethod
    def declared(
        cls,
        accepted_formats: tuple[str, ...] | None = None,
        max_bytes: int | None = None,
        max_dimension: int | None = None,
    ) -> IngestionLimits:
        """These limits over the defaults, field by field.

        ``None`` means *this project declared nothing here*, which is different
        from an empty tuple or a zero: those are declarations, and a project
        that declared an empty format set has declared that it accepts nothing.
        """
        return cls(
            accepted_formats=(
                DEFAULT_FORMATS if accepted_formats is None else tuple(accepted_formats)
            ),
            max_bytes=DEFAULT_MAX_BYTES if max_bytes is None else max_bytes,
            max_dimension=DEFAULT_MAX_DIMENSION if max_dimension is None else max_dimension,
        )

    @property
    def formats_listed(self) -> str:
        """The accepted set as a message states it, in the order it was declared."""
        return ", ".join(self.accepted_formats)

    def accepts(self, image_format: str) -> bool:
        return image_format.lower() in self.accepted_formats


def check_format(facts: ImageFacts, limits: IngestionLimits, subject: str) -> SpecViolation | None:
    """Whether this format is in the project's accepted set, naming both if not."""
    if limits.accepts(facts.format):
        return None
    return SpecViolation(
        rule_id=FORMAT_UNSUPPORTED,
        severity=Severity.ERROR,
        subject=subject,
        message=(
            f"{subject} is {facts.format.upper()}, which this project does not accept; "
            f"the accepted formats are {limits.formats_listed}"
        ),
        observed=facts.format,
        expected=limits.formats_listed,
    )


def check_size(facts: ImageFacts, limits: IngestionLimits, subject: str) -> SpecViolation | None:
    """Whether the file is within the byte limit. At the limit is within it."""
    if facts.byte_size <= limits.max_bytes:
        return None
    return SpecViolation(
        rule_id=SIZE_EXCEEDED,
        severity=Severity.ERROR,
        subject=subject,
        message=(
            f"{subject} is {megabytes(facts.byte_size)}, and this project allows "
            f"{megabytes(limits.max_bytes)} per image"
        ),
        observed=megabytes(facts.byte_size),
        expected=megabytes(limits.max_bytes),
    )


def check_dimensions(
    facts: ImageFacts, limits: IngestionLimits, subject: str
) -> SpecViolation | None:
    """Whether either side exceeds the pixel ceiling. At the ceiling is accepted."""
    if facts.largest_dimension <= limits.max_dimension:
        return None
    return SpecViolation(
        rule_id=DIMENSION_EXCEEDED,
        severity=Severity.ERROR,
        subject=subject,
        message=(
            f"{subject} is {facts.dimensions} pixels, and this project allows at most "
            f"{limits.max_dimension} pixels on a side"
        ),
        observed=facts.dimensions,
        expected=str(limits.max_dimension),
    )


CHECKS = (check_format, check_size, check_dimensions)
"""Every acceptance rule, so :func:`check_image` cannot forget one."""


def check_image(
    facts: ImageFacts, limits: IngestionLimits, subject: str = "the image"
) -> tuple[SpecViolation, ...]:
    """Every reason this image is not acceptable, or an empty tuple.

    All of them rather than the first: a request carrying three defects should
    be rejected once with three reasons, not three times with one.
    """
    found = (check(facts, limits, subject) for check in CHECKS)
    return tuple(violation for violation in found if violation is not None)


def megabytes(byte_size: int) -> str:
    """`41 MB` — what a refusal states, because a byte count is not a number people read."""
    value = byte_size / (1024 * 1024)
    rendered = f"{value:.1f}".removesuffix(".0")
    return f"{rendered} MB"


# --------------------------------------------------------------------------
# Where a view lives (D4)
# --------------------------------------------------------------------------

EXTENSIONS: dict[str, str] = {"png": "png", "jpeg": "jpg", "webp": "webp", "tiff": "tiff"}
"""The file extension each detected format is written under.

`jpeg` writes `.jpg` because that is what every tool in an artist's hands emits;
the *format* stays `jpeg`, because that is what the content says it is.
"""


def extension_for(image_format: str) -> str:
    """The extension this format is written under — its own name when unlisted."""
    return EXTENSIONS.get(image_format.lower(), image_format.lower())


def concept_dir(asset_dir: str) -> str:
    """Where this asset's views live, relative to the repository root."""
    return f"{asset_dir}/{CONCEPT_DIR}" if asset_dir else CONCEPT_DIR


def view_path(asset_dir: str, slot: ViewSlot, image_format: str) -> str:
    """`<asset dir>/concept/<slot>.<ext>` — derived from the slot and nothing else.

    Deterministic by requirement (D4): the slot is the anchor's durable key, so
    the same slot must always yield the same path, and the path is what makes a
    replacement a revision of the same file rather than an unrelated add.
    """
    return f"{concept_dir(asset_dir)}/{slot}.{extension_for(image_format)}"


def slot_of(path: str) -> ViewSlot | None:
    """The slot a repository path names, or ``None`` when it names no view.

    The inverse of :func:`view_path`, and what makes a project's views
    *reconstructible by walking the repository* (D3) rather than known only from
    an index row.
    """
    head, separator, name = path.rpartition("/")
    in_concept_dir = bool(separator) and (head == CONCEPT_DIR or head.endswith(f"/{CONCEPT_DIR}"))
    stem, dot, _ = name.partition(".")
    if not in_concept_dir or not dot or not is_valid_slot(stem):
        return None
    return ViewSlot(stem)


def asset_dir_of(path: str) -> str:
    """The asset directory a view path belongs to — the inverse of :func:`concept_dir`."""
    head, _, _ = path.rpartition("/")
    return head.removesuffix(CONCEPT_DIR).removesuffix("/")


def replacement(current_path: str | None, new_path: str) -> tuple[str | None, str]:
    """The pair of paths a replacement touches: what to remove, and what to write.

    A slot whose format changed also changes its extension, so the path moves.
    D4 handles that as a **rename** — remove the old path in the same commit as
    the write — so the history follows the slot instead of showing a delete and
    an unrelated add. A replacement at the same path removes nothing.
    """
    if current_path is None or current_path == new_path:
        return (None, new_path)
    return (current_path, new_path)


# --------------------------------------------------------------------------
# A view and its revisions
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class ViewRevision:
    """One recorded state of one view's file, as the repository identifies it.

    `content_hash` is ``None`` exactly when the revision *removed* the view,
    which `view-versioning` requires to be a revision like any other — *"Removing
    a view SHALL likewise be recorded as a revision"* — rather than the view
    ceasing to have existed.
    """

    revision: str
    author: str
    at: datetime
    content_hash: ContentHash | None = None
    width: int = 0
    height: int = 0
    byte_size: int = 0
    is_current: bool = False
    removed: bool = False

    @property
    def dimensions(self) -> str:
        return f"{self.width}x{self.height}"


@dataclass(frozen=True)
class ConceptView:
    """One slot of one asset, and the revisions its file has been through.

    `revisions` are newest first, which is the order `view-versioning` requires
    a listing to be in, so nothing downstream sorts them again.
    """

    asset_id: str
    slot: ViewSlot
    path: str
    revisions: tuple[ViewRevision, ...] = ()
    truncated_before: str = ""

    @property
    def current(self) -> ViewRevision | None:
        """The revision this view is at now, or ``None`` when it was removed."""
        return next((revision for revision in self.revisions if revision.is_current), None)

    @property
    def is_removed(self) -> bool:
        """Whether the newest revision removed the file. No current revision then."""
        return bool(self.revisions) and self.revisions[0].removed

    @property
    def is_complete(self) -> bool:
        """Whether this is the whole history, or only as much as the copy holds."""
        return not self.truncated_before

    def revision(self, identifier: str) -> ViewRevision | None:
        """The revision with that identifier, or ``None`` — never the current one."""
        return next((entry for entry in self.revisions if entry.revision == identifier), None)


def marked_current(revisions: tuple[ViewRevision, ...]) -> tuple[ViewRevision, ...]:
    """The same revisions with exactly one marked current, unless the view is removed.

    Newest first is the input order, so the current one is the first — and a
    view whose newest revision removed it has none, which is the sentence
    `view-versioning` states: *"Exactly one entry SHALL be marked as the current
    revision, unless the view has been removed, in which case none SHALL be."*
    """
    if not revisions:
        return ()
    newest, rest = revisions[0], revisions[1:]
    return (
        replace(newest, is_current=not newest.removed),
        *(replace(entry, is_current=False) for entry in rest),
    )


# --------------------------------------------------------------------------
# Carry-forward (D6, D7)
# --------------------------------------------------------------------------

DEFAULT_ASPECT_TOLERANCE = 0.01
"""How far two aspect ratios may differ and still be called the same shape.

A configuration value whose *behaviour* is specified and whose number is not
(design, Open Questions). One per cent absorbs a rounding difference between
exporters and rejects any real crop.
"""


def same_shape(
    before: ImageFacts, after: ImageFacts, tolerance: float = DEFAULT_ASPECT_TOLERANCE
) -> bool:
    """Whether the replacement has the superseded revision's aspect ratio (D6)."""
    return abs(after.aspect - before.aspect) <= tolerance


def carry_forward(
    before: ImageFacts, after: ImageFacts, tolerance: float = DEFAULT_ASPECT_TOLERANCE
) -> AnchorState:
    """What becomes of an annotation anchored to `before` when `after` replaces it.

    Exactly two answers, and no third (D7): **carried**, meaning the normalised
    anchor still means what it meant, or **orphaned**, meaning it does not.
    Nothing here moves a pin by inference — that is the "silently mis-placed
    annotation" `project.md` forbids by name, dressed up as a feature.
    """
    return AnchorState.CARRIED if same_shape(before, after, tolerance) else AnchorState.ORPHANED


__all__ = [
    "CANONICAL_SLOTS",
    "CHECKS",
    "CONCEPT_DIR",
    "DEFAULT_ASPECT_TOLERANCE",
    "DEFAULT_FORMATS",
    "DEFAULT_MAX_BYTES",
    "DEFAULT_MAX_DIMENSION",
    "DIMENSION_EXCEEDED",
    "EXTENSIONS",
    "FORMAT_UNSUPPORTED",
    "MAX_SLOT_LENGTH",
    "SIZE_EXCEEDED",
    "SLOT_PATTERN",
    "ConceptView",
    "ImageFacts",
    "IngestionLimits",
    "InvalidSlotName",
    "ViewRevision",
    "ViewSlot",
    "asset_dir_of",
    "carry_forward",
    "check_dimensions",
    "check_format",
    "check_image",
    "check_size",
    "concept_dir",
    "extension_for",
    "is_valid_slot",
    "marked_current",
    "megabytes",
    "replacement",
    "same_shape",
    "slot_of",
    "view_path",
]
