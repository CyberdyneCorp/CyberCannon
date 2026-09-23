"""Task 6.2 — a failed write leaves the specification exactly as it was (D7).

`metadata-acceptance`: *"If writing an accepted value cannot complete, the
specification file SHALL be left exactly as it was, and the suggestion SHALL
remain unaccepted so the action can be retried."*

This is a property of the file system, so it is asserted against real files: a
real working copy, a real interruption in the middle of the write, and the
original compared byte for byte afterwards. A unit test over a fake would be
asserting the fake.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from cybercanon.adapters.outbound.git import atomic

pytestmark = pytest.mark.integration

ORIGINAL = b"# hand written\nschema_version: 1\nid: mech_scout\nname: Scout Mech\n"
REPLACEMENT = (
    b"# hand written\nschema_version: 1\nid: mech_scout\nname: Scout Mech\naliases:\n  - recon\n"
)


@pytest.fixture
def specification(tmp_path: Path) -> Path:
    target = tmp_path / "characters" / "mech_scout" / "asset.yaml"
    target.parent.mkdir(parents=True)
    target.write_bytes(ORIGINAL)
    return target


def test_a_completed_write_replaces_the_file(specification: Path) -> None:
    atomic.write_atomically(specification, REPLACEMENT)

    assert specification.read_bytes() == REPLACEMENT


def test_an_interrupted_write_leaves_the_original_byte_identical(
    specification: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The rename is where the change becomes visible; before it, nothing has."""

    def refuse(source: object, destination: object) -> None:
        raise OSError("the volume went away between the write and the rename")

    monkeypatch.setattr(os, "replace", refuse)

    with pytest.raises(OSError, match="volume went away"):
        atomic.write_atomically(specification, REPLACEMENT)

    assert specification.read_bytes() == ORIGINAL


def test_an_interrupted_write_leaves_no_debris_beside_the_file(
    specification: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A half-written file beside the original is the next `git status`'s problem."""

    def refuse(source: object, destination: object) -> None:
        raise OSError("interrupted")

    monkeypatch.setattr(os, "replace", refuse)

    with pytest.raises(OSError):
        atomic.write_atomically(specification, REPLACEMENT)

    assert [path.name for path in specification.parent.iterdir()] == ["asset.yaml"]


def test_an_interruption_that_is_not_an_exception_is_still_cleaned_up(
    specification: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`KeyboardInterrupt` is not an `Exception`, and a person does press control-C."""

    def interrupt(source: object, destination: object) -> None:
        raise KeyboardInterrupt

    monkeypatch.setattr(os, "replace", interrupt)

    with pytest.raises(KeyboardInterrupt):
        atomic.write_atomically(specification, REPLACEMENT)

    assert specification.read_bytes() == ORIGINAL
    assert [path.name for path in specification.parent.iterdir()] == ["asset.yaml"]


def test_the_temporary_file_is_created_beside_its_destination(
    specification: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A rename is atomic only within one filesystem, and /tmp is often another."""
    seen: list[Path] = []
    original = atomic.tempfile.mkstemp

    def watched(**options: object):
        seen.append(Path(str(options["dir"])))
        return original(**options)

    monkeypatch.setattr(atomic.tempfile, "mkstemp", watched)

    atomic.write_atomically(specification, REPLACEMENT)

    assert seen == [specification.parent]


def test_a_file_that_did_not_exist_is_created_with_its_directory(tmp_path: Path) -> None:
    target = tmp_path / "props" / "crate" / "asset.yaml"

    atomic.write_atomically(target, REPLACEMENT)

    assert target.read_bytes() == REPLACEMENT
