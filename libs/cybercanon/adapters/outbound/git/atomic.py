"""Putting a file into a working copy without ever leaving half of one (D7).

`metadata-acceptance` states the requirement in one sentence — *"If writing an
accepted value cannot complete, the specification file SHALL be left exactly as
it was"* — and `add-derived-metadata`'s D7 names the mechanism: a temporary file
**in the same directory**, then a rename over the original.

Three details are the whole of it, and each of them is why this is not a
`write_bytes` call:

* **Same directory.** A rename is atomic only within one filesystem, so the
  temporary file is created beside its destination rather than in the system
  temporary directory, which on a container is routinely a different mount.
* **Flushed and synced before the rename.** Otherwise the rename can publish a
  name whose contents are still in a buffer, and a crash leaves a file that is
  present, zero-length and byte-identical to nothing anybody wrote.
* **The temporary file is removed on any failure**, including a
  :class:`KeyboardInterrupt` or a `SystemExit`, so an interrupted write leaves
  the original untouched *and* leaves no debris beside it for the next `git
  status` to report as an untracked file.

It is used by **both** repository hosts — the artist's local checkout and the
hosted volume — because the requirement is about a specification file and there
is no reading of it under which one of those two is allowed to be less careful.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

TEMPORARY_PREFIX = ".canon-write-"
"""How a half-written file names itself, so debris is recognisable if it survives."""


def write_atomically(target: Path, content: bytes) -> None:
    """Replace `target` with these bytes, or leave it exactly as it was.

    There is no third outcome. A caller that is interrupted between the write
    and the rename has changed nothing a reader can observe, which is what makes
    *"the suggestion SHALL still be pending"* true without any compensating
    logic above this line.
    """
    target.parent.mkdir(parents=True, exist_ok=True)
    descriptor, name = tempfile.mkstemp(dir=target.parent, prefix=TEMPORARY_PREFIX)
    staged = Path(name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(staged, target)
    except BaseException:
        staged.unlink(missing_ok=True)
        raise


__all__ = ["TEMPORARY_PREFIX", "write_atomically"]
