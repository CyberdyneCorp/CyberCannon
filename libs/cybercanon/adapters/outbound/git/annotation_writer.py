"""`GitAnnotationWriter` — an observation into the working copy, uncommitted (D2).

This is the local half of D1's one port, two destinations, and everything about
it follows from one sentence of D2: *"`GitAnnotationWriter` appends the entry to
the `annotations` block of the asset's specification file in the working copy,
preserving comments and formatting, and stops there. It does not stage, commit,
branch or push."*

That refusal is the whole value of the local path. Git is the source of truth
and a human reading a diff is what keeps an agent's contribution accountable, so
an agent's write has to arrive as a **proposal in the artist's working copy**
rather than as a commit in her history: *"an auto-commit would write into an
artist's working tree mid-edit, could land during a rebase, and would turn a
proposal into a fait accompli."* The hosted writer is the one place a direct
commit is correct, because there no human working tree exists to disturb.

Three properties are structural rather than remembered:

* **there is no commit in this module.** It imports
  :mod:`cybercanon.adapters.outbound.git.commands` for exactly two read-only
  questions — is this file in conflict, and is this repository usable — and
  writes with :meth:`pathlib.Path.write_bytes`. Nothing here can stage
  anything, so nothing here can be persuaded to;
* **only the annotations block moves.** The rendering is
  :meth:`~cybercanon.application.ports.spec_store.SpecStore.edited`, the same
  round-trip writer the web surface's annotations go through, so comments, key
  order and every unrelated line come back byte-identical — asserted, in
  `tests/integration/test_annotation_write_back.py`, by comparing the file
  before and after;
* **an unknown asset is never created.** :meth:`GitAnnotationWriter.locate`
  answers ``None`` and :meth:`GitAnnotationWriter.append` refuses, because
  `mcp-write-surface` forbids an automated caller from causing a specification
  file *"to come into existence as a side effect of a write."*

A **conflicted file is refused and left untouched** (task 3.4). A write that
landed in the middle of somebody's rebase would either be lost with the conflict
resolution or, worse, silently resolve it; the agent is told to retry, which is
the condition clearing itself when the person finishes.

That check **fails closed**. Asking git whether a path is in conflict has three
answers, not two — *yes*, *no*, and *git did not answer* — and the third is
refused with :data:`UNDETERMINED` rather than read as *no*. It used to be read
as *no*, and that inverted the guarantee this module advertises: the one
condition the writer exists to refuse was permitted precisely when the check
had gone blind, which on a CI runner is as ordinary as `git` declining a
repository for *"detected dubious ownership"*. A check whose failure mode is
*proceed* protects nothing.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from pathlib import Path

from cybercanon.adapters.outbound.git import commands, discovery
from cybercanon.application.errors import OperationFailed
from cybercanon.application.ports.annotation_writer import (
    AnnotationWriteRefused,
    AnnotationWriteUnavailable,
    WrittenAnnotation,
)
from cybercanon.application.ports.spec_store import SpecDocument, SpecStore
from cybercanon.domain.annotations import Annotation

CONFLICT_MARKERS: tuple[str, ...] = ("<<<<<<< ", "=======\n", ">>>>>>> ")
"""What an unresolved merge leaves in a file.

Checked in the *content* as well as in git's index state, because a file can
carry markers a person pasted or a merge tool left after `git add` — and writing
an annotation into a file that still contains them would produce a specification
that parses as nonsense and a diff nobody can review.
"""

UNMERGED_STATES: tuple[str, ...] = ("DD", "AU", "UD", "UA", "DU", "AA", "UU")
"""The `git status --porcelain` codes that mean *this path is in conflict*."""

IN_CONFLICT = "it is in an unresolved merge or rebase; resolve it and record this again"
"""What the refusal says, and what the agent does about it."""

UNDETERMINED = (
    "whether it is in an unresolved merge could not be determined — git did not answer; "
    "the write was refused rather than risked, so check the repository and record this again"
)
"""What the refusal says when the conflict check itself could not be made.

A different sentence from :data:`IN_CONFLICT` on purpose, and the distinction is
the one `canon` already draws between exit 1 and exit 2: *"this file is in
conflict"* and *"I could not find out whether this file is in conflict"* are
different claims, and the second must never be spoken as the first. What they
share is the outcome — **nothing is written** — because a check that has gone
blind is the moment a guarantee is worth the most, not the moment to drop it.
"""


type SpecPathFor = Callable[[str], str | None]
"""How this writer answers *which file is this asset written in*.

Injected the way
:data:`~cybercanon.application.use_cases.index_assets.Fingerprinter` is: a
surface with an index answers from it, and a surface without one — a laptop
that has never run a rebuild — falls back to walking the specifications under
the root. Neither answer is this adapter's to decide, and both must give the
same path or two surfaces would write to two files.
"""


class GitAnnotationWriter:
    """Appends one observation to one asset's `asset.yaml`, and commits nothing."""

    def __init__(
        self,
        spec_store: SpecStore,
        *,
        root: str | Path,
        locate: SpecPathFor | None = None,
    ) -> None:
        """Write through `spec_store`'s round-trip renderer, into `root`.

        `root` is the working copy the relative paths the store speaks are
        resolved against — the same root the store itself resolved, handed in
        rather than read off the store, because the port knows nothing about a
        directory and this adapter must not learn to ask a port for one.
        """
        self._spec_store = spec_store
        self._root = Path(root)
        self._locate = locate

    @property
    def root(self) -> Path:
        """The working copy this writer modifies, and never leaves."""
        return self._root

    # -- port ------------------------------------------------------------

    def locate(self, project: str, asset_id: str) -> str | None:
        """The specification file this asset is written in, or ``None``.

        ``None`` is an answer rather than a failure: the refusal that names the
        unknown identifier and offers the closest ones is a use case's sentence,
        and an adapter that raised here would make *"the read after a refused
        write still succeeds"* depend on somebody catching it.
        """
        if self._locate is not None:
            return self._locate(asset_id)
        return self._scanned(asset_id)

    def annotations(self, project: str, asset_id: str) -> tuple[Annotation, ...]:
        """Every annotation this asset's file lists, in the order it lists them."""
        return self._document(self._required(asset_id)).asset.annotations

    def append(self, project: str, asset_id: str, annotation: Annotation) -> WrittenAnnotation:
        """Add this annotation to that file's `annotations` block. Nothing else moves.

        The file is written whole, from the round-trip renderer, and the write is
        not staged: the response says so, and D2's sentence about the working
        copy travels with it so the caller cannot phrase the risk its own way.
        """
        path = self._required(asset_id)
        self._mergeable(path)
        document = self._document(path)
        edited = self._spec_store.edited(
            document, replace(document.asset, annotations=(*document.asset.annotations, annotation))
        )
        self._write(path, edited)
        return WrittenAnnotation(path=path, annotation=annotation, committed=False)

    # -- the file --------------------------------------------------------

    def _required(self, asset_id: str) -> str:
        """Where this asset is written, or the refusal that it is written nowhere."""
        path = self.locate("", asset_id)
        if path is None:
            raise AnnotationWriteUnavailable(asset_id, "no specification declares this asset here")
        return path

    def _document(self, path: str) -> SpecDocument:
        """The file as it stands: its bytes and its meaning, read once per write.

        Read **after** the conflict check, never before: a file mid-merge does
        not parse, and reporting that as *unreadable* would hide the condition
        the agent can actually do something about.
        """
        try:
            return self._spec_store.read_document(path)
        except OperationFailed as failure:
            raise AnnotationWriteRefused(path, failure.message) from failure

    def _mergeable(self, path: str) -> None:
        """Refuse a file a merge has not finished with, having written nothing (3.4).

        Both checks answer three things, not two — *yes*, *no*, and **I could
        not tell** — and the third refuses. A safety check that reports *safe*
        when it could not reach an answer is not a safety check: it is one that
        holds exactly while nothing is wrong and lets go the moment something
        is, which is the inversion this method exists to make impossible.
        """
        unmerged = self._unmerged(path)
        marked = self._marked(path)
        if unmerged is None or marked is None:
            raise AnnotationWriteRefused(path, UNDETERMINED)
        if unmerged or marked:
            raise AnnotationWriteRefused(path, IN_CONFLICT)

    def _unmerged(self, path: str) -> bool | None:
        """Whether git reports this path as unresolved, or ``None`` if it cannot say.

        A question, never a fix: this adapter does not resolve conflicts, stage
        anything, or decide what a merge should have produced. It does not
        answer the question *for* git either — `git` not installed, `git`
        timed out, and a `git` that refuses the repository outright (a CI
        runner's *"detected dubious ownership"* is the everyday way to meet
        one) are all ``None``, because none of them is the sentence *this path
        is not in conflict*.
        """
        try:
            completed = commands.run(self._root, ["status", "--porcelain", "--", path])
        except commands.GitUnavailable:
            return None
        if not completed.ok:
            return None
        return any(line[:2] in UNMERGED_STATES for line in completed.text.splitlines() if line)

    def _marked(self, path: str) -> bool | None:
        """Whether the file still carries the markers a merge left in it.

        ``None`` for a file that is there and cannot be read, for the same
        reason: *unreadable* is not *clean*. A path with no file at all is a
        different condition and not this one's to report — :meth:`_document`
        refuses it next, naming it — so it answers ``False`` and moves on.
        """
        absolute = self._root / path
        if not absolute.is_file():
            return False
        try:
            text = absolute.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return None
        return any(marker in text for marker in CONFLICT_MARKERS)

    def _write(self, path: str, content: bytes) -> None:
        """The whole file, as the renderer produced it. No staging, no commit."""
        absolute = self._root / path
        try:
            absolute.write_bytes(content)
        except OSError as failure:
            raise AnnotationWriteUnavailable(path, str(failure)) from failure

    # -- discovery -------------------------------------------------------

    def _scanned(self, asset_id: str) -> str | None:
        """The specification declaring this identifier, found by reading them.

        The fallback for a surface with no index. Linear in the number of
        specifications and deliberately not cached: a write is rare, a stale
        answer would write into the wrong file, and the index-backed locator is
        what a surface that cares about the cost supplies instead.
        """
        for path in self._spec_store.specs_under(str(self._root)):
            if self._declares(path, asset_id):
                return _relative(self._root, path)
        return None

    def _declares(self, path: str, asset_id: str) -> bool:
        """Whether that file is this asset's specification, parseable or not.

        A file in the middle of a merge does not parse, and answering *no such
        asset* for one would be the wrong refusal entirely: the caller would be
        offered the closest identifiers for an asset that exists and is simply
        mid-rebase. So a file the parser refuses is matched on its declared
        identifier line instead, which is enough to locate it and hand it to
        :meth:`_mergeable`, where it is refused *as conflicted* and told to
        retry.
        """
        try:
            return self._spec_store.load(path).asset.id.value == asset_id
        except OperationFailed:
            return _declares_id(self._root / _relative(self._root, path), asset_id)


def _relative(root: Path, path: str) -> str:
    """The path as the working copy speaks it, whatever form the store answered in."""
    return discovery.relative_to(root, path) or path


def _declares_id(path: Path, asset_id: str) -> bool:
    """Whether the file's text carries a top-level `id:` naming this asset.

    Text rather than a parse, because this is only reached for a file the parser
    has already refused. It answers *which asset is this file about*, never
    *what does it say*: nothing is written on the strength of this — the write
    that follows is refused as conflicted.
    """
    if not path.is_file():
        return False
    declared = f"id: {asset_id}"
    quoted = (f'id: "{asset_id}"', f"id: '{asset_id}'")
    return any(
        line.strip() == declared or line.strip() in quoted
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines()
    )


__all__ = [
    "CONFLICT_MARKERS",
    "IN_CONFLICT",
    "UNDETERMINED",
    "UNMERGED_STATES",
    "GitAnnotationWriter",
    "SpecPathFor",
]
