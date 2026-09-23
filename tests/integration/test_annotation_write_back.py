"""Tasks 3.3 and 3.4 — an observation into a real working copy, and nothing else.

Two properties, both of which can only be checked against a real repository and
both of which are requirements rather than preferences:

* **the write is a proposal, not a fait accompli** (D2). The entry lands in the
  artist's working copy, `git status` reports exactly one modified file, nothing
  is staged, and `HEAD` has not moved. That is what keeps an agent's
  contribution something a human reviews in a diff — *"an auto-commit would
  write into an artist's working tree mid-edit, could land during a rebase, and
  would turn a proposal into a fait accompli"*;
* **only the annotations block moves.** Every other line of the specification
  comes back byte-identical, comments and blank lines included, which is the
  property the artists' trust in this tool rests on. It is asserted here rather
  than promised in prose, by diffing the file with its annotations block removed.

The conflicted-file case is the third: a write during an unfinished merge is
**refused with the condition named and the file untouched**. The design's own
risk entry says what has to happen — *"the writer refuses on an unmergeable or
conflicted specification file, reports the condition, and the agent is told to
retry"* — and a writer that instead wrote into a file full of conflict markers
would produce a specification that parses as nonsense inside somebody else's
rebase.

The fourth is the one the third is worth nothing without: that check **fails
closed**. A `git` that cannot answer whether a path is in conflict — absent,
timed out, or refusing the repository as dubiously owned — used to be read as
*not in conflict*, so the guarantee held exactly while nothing was wrong and
let go the moment the check went blind. The suite at the bottom makes the
question unanswerable over a clean file, where nothing but git's answer can
refuse the write, and asserts that it is refused and says which of the two
sentences it is saying.
"""

from __future__ import annotations

import os
import subprocess
from collections.abc import Callable
from pathlib import Path

import pytest
from game_repo import CRATE_SPEC, MECH_SPEC, build_game_repo

from cybercanon.adapters.outbound.git import commands
from cybercanon.adapters.outbound.git.annotation_writer import (
    CONFLICT_MARKERS,
    IN_CONFLICT,
    UNDETERMINED,
    GitAnnotationWriter,
)
from cybercanon.adapters.outbound.git.spec_store import GitSpecStore
from cybercanon.application.ports.annotation_writer import UNCOMMITTED, AnnotationWriteRefused
from cybercanon.domain.annotations import Annotation, AnnotationKind, ObservationKind
from cybercanon.domain.identity import AgentId
from cybercanon.domain.observations import observation, target_for

pytestmark = pytest.mark.integration

PROJECT = "ronin"
MECH = "mech_scout"
BLENDER = AgentId("blender-agent")
UNREACHABLE = "12000 triangles is unreachable without losing the head silhouette"

ANNOTATIONS_KEY = "annotations:"


def _environment(root: Path) -> dict[str, str]:
    """A git that answers the same on every machine, and knows who it is.

    The identity is not decoration. `git merge` resolves the committer **before
    it merges anything** on git 2.43 (ubuntu-24.04) and only when it comes to
    write the merge commit on git 2.50 (macOS), so a merge run without one dies
    at 128 having touched nothing on the first and conflicts on the second. A
    fixture that left it out produced no conflict on CI while asserting it had.
    """
    return {
        **os.environ,
        "HOME": str(root),
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_AUTHOR_NAME": "Rafa",
        "GIT_AUTHOR_EMAIL": "rafa@cyberdyne.com",
        "GIT_COMMITTER_NAME": "Rafa",
        "GIT_COMMITTER_EMAIL": "rafa@cyberdyne.com",
    }


def _git(root: Path, *arguments: str) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        ["git", "-C", str(root), *arguments],
        check=True,
        capture_output=True,
        env=_environment(root),
    )


def _git_may_fail(root: Path, *arguments: str) -> subprocess.CompletedProcess[bytes]:
    """The same git, for the one command whose non-zero exit is the point."""
    return subprocess.run(
        ["git", "-C", str(root), *arguments],
        check=False,
        capture_output=True,
        env=_environment(root),
    )


@pytest.fixture
def committed_repo(tmp_path: Path) -> Path:
    """A game repository whose every file is committed, so a diff means something."""
    root = tmp_path / "game"
    root.mkdir()
    _git(root, "init", "-q")
    build_game_repo(root)
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "the canon, as an artist committed it")
    return root


@pytest.fixture
def writer(committed_repo: Path) -> GitAnnotationWriter:
    store = GitSpecStore(committed_repo)
    return GitAnnotationWriter(store, root=store.root)


def an_observation(identifier: str = "obs_1", text: str = UNREACHABLE) -> Annotation:
    return observation(
        identifier=identifier,
        author="rafa",
        via=BLENDER,
        kind=AnnotationKind.TECHNICAL,
        observation_kind=ObservationKind.UNATTAINABLE_CONSTRAINT,
        text=text,
        target=target_for("head"),
        created_at="2026-03-01T12:00:00+00:00",
    )


def _before_annotations(text: str) -> str:
    """The file up to its annotations block — what a write may not touch."""
    return text.split(ANNOTATIONS_KEY)[0]


def _status(root: Path) -> tuple[str, ...]:
    output = _git(root, "status", "--porcelain").stdout.decode("utf-8")
    return tuple(line for line in output.splitlines() if line.strip())


# --------------------------------------------------------------------------
# 3.3 — the entry lands, uncommitted, and nothing else moves
# --------------------------------------------------------------------------


def test_the_observation_lands_in_the_specification_file(
    writer: GitAnnotationWriter, committed_repo: Path
) -> None:
    written = writer.append(PROJECT, MECH, an_observation())

    recorded = (committed_repo / MECH_SPEC).read_text(encoding="utf-8")
    assert written.path == MECH_SPEC
    assert UNREACHABLE in recorded
    assert "author_kind: agent" in recorded
    assert str(ObservationKind.UNATTAINABLE_CONSTRAINT) in recorded


def test_the_write_is_not_committed_and_says_so(
    writer: GitAnnotationWriter, committed_repo: Path
) -> None:
    """D2 — the proposal stays in the working copy, and the caller is told."""
    head = _git(committed_repo, "rev-parse", "HEAD").stdout

    written = writer.append(PROJECT, MECH, an_observation())

    assert written.committed is False
    assert written.note == UNCOMMITTED
    assert _git(committed_repo, "rev-parse", "HEAD").stdout == head
    assert _git(committed_repo, "diff", "--cached", "--name-only").stdout == b""


def test_the_only_changed_file_is_the_named_assets_specification(
    writer: GitAnnotationWriter, committed_repo: Path
) -> None:
    """*"No other file SHALL be created, modified or deleted."*"""
    writer.append(PROJECT, MECH, an_observation())

    assert _status(committed_repo) == (f" M {MECH_SPEC}",)


def test_every_line_outside_the_annotations_block_is_byte_identical(
    writer: GitAnnotationWriter, committed_repo: Path
) -> None:
    """The round trip: comments, blank lines and key order all survive."""
    spec = committed_repo / MECH_SPEC
    before = spec.read_text(encoding="utf-8")

    writer.append(PROJECT, MECH, an_observation())

    assert _before_annotations(spec.read_text(encoding="utf-8")) == _before_annotations(before)


def test_a_second_observation_adds_a_thread_rather_than_replacing_one(
    writer: GitAnnotationWriter, committed_repo: Path
) -> None:
    writer.append(PROJECT, MECH, an_observation("obs_1", "the first finding"))
    writer.append(PROJECT, MECH, an_observation("obs_2", "the second finding"))

    assert [entry.id for entry in writer.annotations(PROJECT, MECH)] == ["obs_1", "obs_2"]
    assert _status(committed_repo) == (f" M {MECH_SPEC}",)


def test_another_assets_specification_is_untouched(
    writer: GitAnnotationWriter, committed_repo: Path
) -> None:
    crate = (committed_repo / CRATE_SPEC).read_bytes()

    writer.append(PROJECT, MECH, an_observation())

    assert (committed_repo / CRATE_SPEC).read_bytes() == crate


# --------------------------------------------------------------------------
# 3.4 — a file a merge has not finished with is refused, untouched
# --------------------------------------------------------------------------


def test_a_conflicted_specification_is_refused_and_left_untouched(
    writer: GitAnnotationWriter, committed_repo: Path
) -> None:
    spec = committed_repo / MECH_SPEC
    conflicted = (
        f"{CONFLICT_MARKERS[0]}HEAD\ntri_budget: 12000\n"
        f"{CONFLICT_MARKERS[1]}tri_budget: 9000\n{CONFLICT_MARKERS[2]}theirs\n"
        + spec.read_text(encoding="utf-8")
    )
    spec.write_text(conflicted, encoding="utf-8")

    with pytest.raises(AnnotationWriteRefused) as refusal:
        writer.append(PROJECT, MECH, an_observation())

    assert spec.read_text(encoding="utf-8") == conflicted
    assert MECH_SPEC in refusal.value.message
    assert "resolve" in refusal.value.message


def _conflict_over_the_budget(root: Path) -> None:
    """Leave `MECH_SPEC` in a genuine unresolved merge, or fail saying why not.

    The assertion is `UU` rather than a non-zero exit, and that is the whole
    lesson of the defect this fixture once hid: `git merge` exits non-zero for
    *any* reason it declined, and a fixture that read that as "a conflict was
    produced" asserted a state it had never reached.
    """
    spec = root / MECH_SPEC
    _git(root, "checkout", "-q", "-b", "theirs")
    spec.write_text(
        spec.read_text(encoding="utf-8").replace("tri_budget: 12000", "tri_budget: 9000"),
        encoding="utf-8",
    )
    _git(root, "commit", "-q", "-a", "-m", "lower the budget")
    _git(root, "checkout", "-q", "-")
    spec.write_text(
        spec.read_text(encoding="utf-8").replace("tri_budget: 12000", "tri_budget: 15000"),
        encoding="utf-8",
    )
    _git(root, "commit", "-q", "-a", "-m", "raise the budget")

    merged = _git_may_fail(root, "merge", "theirs")

    assert _status(root) == (f"UU {MECH_SPEC}",), (
        "the fixture failed to produce a conflict; git said: "
        f"{merged.stdout.decode('utf-8')}{merged.stderr.decode('utf-8')}"
    )


def _one_side_kept(text: str) -> str:
    """The file as a person leaves it having picked a side and not staged it."""
    kept, taking = [], True
    for line in text.splitlines(keepends=True):
        if line.startswith(CONFLICT_MARKERS[0]):
            taking = True
        elif line.startswith(CONFLICT_MARKERS[1].strip()):
            taking = False
        elif line.startswith(CONFLICT_MARKERS[2]):
            taking = True
        elif taking:
            kept.append(line)
    return "".join(kept)


def test_an_unmerged_path_is_refused_even_with_no_markers_left(
    writer: GitAnnotationWriter, committed_repo: Path
) -> None:
    """Git's own answer, not just the text: a staged-but-unresolved path refuses."""
    _conflict_over_the_budget(committed_repo)
    spec = committed_repo / MECH_SPEC
    spec.write_text(_one_side_kept(spec.read_text(encoding="utf-8")), encoding="utf-8")
    text = spec.read_text(encoding="utf-8")
    assert not any(marker in text for marker in CONFLICT_MARKERS), "the markers are still there"
    assert _status(committed_repo) == (f"UU {MECH_SPEC}",), "git no longer calls the path unmerged"
    before = spec.read_bytes()

    with pytest.raises(AnnotationWriteRefused):
        writer.append(PROJECT, MECH, an_observation())

    assert spec.read_bytes() == before


# --------------------------------------------------------------------------
# 3.4 — the conflict check fails closed: unanswerable is not "no conflict"
# --------------------------------------------------------------------------


def _answering(reply: commands.Completed | Exception) -> Callable[..., commands.Completed]:
    """A `commands.run` that always gives this answer, whatever it is asked."""

    def run(*_arguments: object, **_keywords: object) -> commands.Completed:
        if isinstance(reply, Exception):
            raise reply
        return reply

    return run


@pytest.mark.parametrize(
    ("condition", "reply"),
    [
        ("git cannot be run at all", commands.GitUnavailable("git could not be run")),
        (
            "git refuses the repository",
            commands.Completed(
                code=128,
                out=b"",
                err="fatal: detected dubious ownership in repository at '/x'",
            ),
        ),
    ],
    ids=["unrunnable", "refused"],
)
def test_a_conflict_check_that_cannot_be_made_refuses_the_write(
    writer: GitAnnotationWriter,
    committed_repo: Path,
    monkeypatch: pytest.MonkeyPatch,
    condition: str,
    reply: commands.Completed | Exception,
) -> None:
    """Fail closed: *I could not look* is never delivered as *nothing is wrong*.

    The file here is clean and carries no markers, so the marker check cannot
    save the day — the only thing standing between an agent and a write into a
    possibly-conflicted specification is git's answer, and there is none. The
    old adapter read that silence as *not in conflict* and wrote.
    """
    spec = committed_repo / MECH_SPEC
    before = spec.read_bytes()
    monkeypatch.setattr(commands, "run", _answering(reply))

    with pytest.raises(AnnotationWriteRefused) as refusal:
        writer.append(PROJECT, MECH, an_observation())

    assert spec.read_bytes() == before, f"{condition}, and the writer wrote anyway"
    assert refusal.value.reason == UNDETERMINED
    assert MECH_SPEC in refusal.value.message


def test_the_refusal_says_the_check_failed_rather_than_that_the_file_is_conflicted(
    writer: GitAnnotationWriter, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Two different sentences, because they are two different claims.

    *"This file is in an unresolved merge"* is something the writer learned;
    *"whether it is could not be determined"* is something it failed to learn.
    Reporting the second as the first would send a person to resolve a merge
    that may not exist, and hide a repository git has stopped talking to.
    """
    monkeypatch.setattr(commands, "run", _answering(commands.GitUnavailable("no git here")))

    with pytest.raises(AnnotationWriteRefused) as refusal:
        writer.append(PROJECT, MECH, an_observation())

    assert refusal.value.reason != IN_CONFLICT
    assert "could not be determined" in refusal.value.reason


def test_a_specification_that_cannot_be_read_refuses_rather_than_reading_as_clean(
    committed_repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The marker check fails closed too: *unreadable* is not *marker-free*.

    The locator is injected here so that the file is read exactly once, by the
    check under test — a writer that scanned for the asset would meet the
    unreadable file first and answer a different question.
    """
    store = GitSpecStore(committed_repo)
    writer = GitAnnotationWriter(store, root=store.root, locate=lambda _asset: MECH_SPEC)
    spec = committed_repo / MECH_SPEC
    before = spec.read_bytes()
    readable = Path.read_text

    def refusing(self: Path, *arguments: object, **keywords: object) -> str:
        if self == spec:
            raise PermissionError(f"{spec} cannot be read")
        return readable(self, *arguments, **keywords)  # type: ignore[arg-type]

    monkeypatch.setattr(Path, "read_text", refusing)

    with pytest.raises(AnnotationWriteRefused) as refusal:
        writer.append(PROJECT, MECH, an_observation())

    assert spec.read_bytes() == before
    assert refusal.value.reason == UNDETERMINED
