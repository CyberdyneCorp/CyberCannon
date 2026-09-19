"""Task 6.3 — the subprocess harness for end-to-end runs of `canon`.

The command line is a deployable of its own, and the thing that can only be
checked by running it is the contract between the process and whatever runs it:
its **exit code**, its **standard output**, and its **standard error**, as three
separate channels.

They are separate here on purpose, and the assertion helpers refuse to let them
be conflated:

* a pre-commit hook and a CI step branch on the **exit code**, so an exit code
  that is right for the wrong reason is a gate that will pass the day it should
  not. `canon validate` returning `1` for a violation and `2` for a run that
  could not happen is the distinction `application/errors.py` exists to keep,
  and it is worth nothing if a test only greps the output;
* a caller piping ``canon ... --json`` into `jq` needs **stdout** to carry the
  document and nothing else. A progress line printed to stdout instead of
  stderr is a break for that caller and is invisible to a test that captures
  them together — which is exactly why ``capture_output`` keeps them apart and
  :meth:`Run.stdout_json` parses stdout alone.
"""

from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

CANON = (sys.executable, "-m", "cybercanon.cli")
TIMEOUT_S = 120


@dataclass(frozen=True)
class Run:
    """One completed run of the binary: three channels, none folded into another."""

    arguments: tuple[str, ...]
    exit_code: int
    stdout: str
    stderr: str

    def stdout_json(self) -> Any:
        """Standard output as the document it claims to be, or a failure saying so."""
        try:
            return json.loads(self.stdout)
        except json.JSONDecodeError as error:
            raise AssertionError(
                f"`canon {' '.join(self.arguments)}` did not write a JSON document to "
                f"standard output ({error}); stdout was {self.stdout!r} and stderr "
                f"was {self.stderr!r}"
            ) from error

    def expect_exit(self, code: int) -> Run:
        assert self.exit_code == code, (
            f"`canon {' '.join(self.arguments)}` exited {self.exit_code}, expected "
            f"{code}; stderr was {self.stderr!r}"
        )
        return self

    def expect_stdout_contains(self, fragment: str) -> Run:
        assert fragment in self.stdout, (
            f"standard output of `canon {' '.join(self.arguments)}` does not contain "
            f"{fragment!r}; it was {self.stdout!r}"
        )
        return self

    def expect_stdout_empty(self) -> Run:
        """What a caller piping into `jq` needs of a command that produced nothing."""
        assert self.stdout == "", (
            f"`canon {' '.join(self.arguments)}` wrote to standard output when it "
            f"should have written only to standard error: {self.stdout!r}"
        )
        return self


def run_canon(*arguments: str, cwd: Path | None = None, env: dict[str, str] | None = None) -> Run:
    """Run the binary as a caller runs it: a real process, with real streams."""
    completed = subprocess.run(
        [*CANON, *arguments],
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        check=False,
        timeout=TIMEOUT_S,
    )
    return Run(
        arguments=arguments,
        exit_code=completed.returncode,
        stdout=completed.stdout,
        stderr=completed.stderr,
    )
