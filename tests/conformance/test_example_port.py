"""Task 5.1 — one parametrised suite per port, fake and real in the same pass.

This is the template. A real port's suite is this file with the imports changed:
the contract class beside the port's fake, the implementations named here, and
nothing else.
"""

from __future__ import annotations

from contract import implementation_fixture
from example_port import FileNoteStore, InMemoryNoteStore, NoteStoreContract

implementation = implementation_fixture(fake=InMemoryNoteStore, real=FileNoteStore)


class TestNoteStore(NoteStoreContract):
    """The `NoteStore` contract, against the in-memory fake and the real adapter."""
