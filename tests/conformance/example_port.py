"""The worked example the conformance pattern is demonstrated on (task 5.1).

Real ports — `SpecStore`, `MeshInspector`, `BlobStore` — arrive with the changes
that introduce them, and each brings its own contract class next to its fake.
Until then the pattern needs something to be a pattern *of*: a port with an
in-memory fake and a real, file-backed adapter, so `test_example_port.py` is
the template a real port's suite copies.

`DivergentNoteStore` is the deliberately lying fake of task 5.2. It is never
collected by the suite here — `tests/tooling/test_conformance_pattern.py` runs
the contract against it in a throwaway project and asserts the contract catches
it, which is the only way to observe a failing suite from a passing one.
"""

from __future__ import annotations

from pathlib import Path
from typing import Protocol


class NoteStore(Protocol):
    """Stores a note under a key. Keys come back sorted; an unknown key is None."""

    def put(self, key: str, note: str) -> None: ...

    def get(self, key: str) -> str | None: ...

    def keys(self) -> tuple[str, ...]: ...


class InMemoryNoteStore:
    """The in-memory fake: what the unit suite and the BDD steps would run against."""

    def __init__(self, directory: Path | None = None) -> None:
        self._notes: dict[str, str] = {}

    def put(self, key: str, note: str) -> None:
        self._notes[key] = note

    def get(self, key: str) -> str | None:
        return self._notes.get(key)

    def keys(self) -> tuple[str, ...]:
        return tuple(sorted(self._notes))


class FileNoteStore:
    """The real adapter: one file per key, so the suite runs against actual I/O."""

    def __init__(self, directory: Path) -> None:
        self._directory = directory / "notes"
        self._directory.mkdir(parents=True, exist_ok=True)

    def put(self, key: str, note: str) -> None:
        self._path(key).write_text(note, encoding="utf-8")

    def get(self, key: str) -> str | None:
        path = self._path(key)
        return path.read_text(encoding="utf-8") if path.is_file() else None

    def keys(self) -> tuple[str, ...]:
        return tuple(sorted(path.stem for path in self._directory.glob("*.txt")))

    def _path(self, key: str) -> Path:
        return self._directory / f"{key}.txt"


class DivergentNoteStore(InMemoryNoteStore):
    """A fake that lies in one way: an unknown key reads as empty, not missing.

    Exactly the class of divergence that makes a unit suite green and the
    product broken — the fake answers, the adapter does not.
    """

    def get(self, key: str) -> str | None:
        return self._notes.get(key, "")


class NoteStoreContract:
    """What every `NoteStore` SHALL do, whoever implements it.

    Subclassed once per port suite; the `implementation` fixture supplies each
    implementation in turn.
    """

    def test_a_stored_note_reads_back(self, implementation: NoteStore) -> None:
        implementation.put("mech_scout", "hello")

        assert implementation.get("mech_scout") == "hello"

    def test_an_unknown_key_reads_as_missing(self, implementation: NoteStore) -> None:
        assert implementation.get("no_such_asset") is None

    def test_a_second_put_replaces_the_first(self, implementation: NoteStore) -> None:
        implementation.put("mech_scout", "first")
        implementation.put("mech_scout", "second")

        assert implementation.get("mech_scout") == "second"

    def test_keys_come_back_sorted(self, implementation: NoteStore) -> None:
        for key in ("scout", "atlas", "mule"):
            implementation.put(key, key)

        assert implementation.keys() == ("atlas", "mule", "scout")
