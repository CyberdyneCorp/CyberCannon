"""The build pipeline's record, and the two checks read from it (task 3.3).

:mod:`canon_release.digests` answers three questions about a deployable
artifact; this module is how a pipeline and an operator ask them, so that the
ledger is something a build **writes** rather than a library nobody calls.

Three commands, each a `just` recipe:

* ``record`` — run after an image is built, with the revision it was built from
  and the digest the engine reported. Recording a second, *different* digest for
  one revision exits non-zero, which is what *"built once per revision and
  promoted between environments without rebuilding"* comes to in practice: a
  build that rebuilt an already-built revision fails its own pipeline step;
* ``promotion`` — the gate before an environment is pointed at an artifact. It
  compares what that environment is running against the record and, when they
  differ, names both digests. Several environments are checked in one call, so
  *"the artifact running in a later environment is identical to the one verified
  in an earlier environment"* is one question with one answer;
* ``rollback`` — the withdrawal. It prints the digest to deploy for the revision
  being returned to and exits zero; a revision the ledger does not hold is the
  one case a rollback would need a build, and it is **reported** rather than
  performed, because an artifact nobody verified is not a rollback target.

**The digest is supplied, not computed here.** The engine that built the image
is the thing that knows it — `docker image inspect --format '{{.Id}}'` in the
pipeline — and a command that shelled out to an engine could not be run by the
operator checking what production is running from a laptop. That also keeps
every question in this module answerable from a checkout, including on the day
the platform is what is broken.

The exit code is the whole interface for a pipeline step: zero is conforming,
non-zero stops the release.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import TextIO

from canon_release.digests import (
    IMAGES,
    LEDGER_PATH,
    AlreadyBuilt,
    Build,
    Ledger,
    promotions,
    rollback,
)

RECORD = "record"
PROMOTION = "promotion"
ROLLBACK = "rollback"

REFUSED = 1
"""What a pipeline step exits with when the artifact rule was broken."""

PAIR_SEPARATOR = "="
"""`--running <environment>=<digest>`, so one call checks every environment."""


def artifact() -> argparse.ArgumentParser:
    """What every command names: an image, a revision, and which ledger.

    Shared as a parent rather than declared at the top level, so that the
    arguments may follow the command. A flag whose position depends on where the
    subcommand is would be a pipeline step that fails on the day somebody
    reorders it.
    """
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--ledger", type=Path, default=LEDGER_PATH)
    common.add_argument("--image", required=True, choices=IMAGES)
    common.add_argument("--revision", required=True)
    return common


def parser() -> argparse.ArgumentParser:
    """The three commands, and the arguments a pipeline has to hand."""
    described = argparse.ArgumentParser(prog="canon_release", description=__doc__)
    commands = described.add_subparsers(dest="command", required=True)
    common = [artifact()]

    recording = commands.add_parser(RECORD, parents=common, help="record a built digest")
    recording.add_argument("--digest", required=True)
    recording.add_argument("--built-at", default="")

    checking = commands.add_parser(PROMOTION, parents=common, help="check what is running")
    checking.add_argument("--running", required=True, nargs="+", metavar="ENVIRONMENT=DIGEST")

    commands.add_parser(ROLLBACK, parents=common, help="the digest a withdrawal deploys")
    return described


def running(pairs: Sequence[str]) -> dict[str, str]:
    """`<environment>=<digest>` pairs as a mapping, refusing anything else."""
    read: dict[str, str] = {}
    for pair in pairs:
        environment, separator, digest = pair.partition(PAIR_SEPARATOR)
        if not separator or not environment.strip() or not digest.strip():
            raise ValueError(f"expected <environment>=<digest>, not {pair!r}")
        read[environment.strip()] = digest.strip()
    return read


def record(
    arguments: argparse.Namespace, out: TextIO = sys.stdout, err: TextIO = sys.stderr
) -> int:
    """Write the digest this revision was built as, or refuse a second one."""
    ledger = Ledger.read(arguments.ledger)
    built = Build(
        image=arguments.image,
        revision=arguments.revision,
        digest=arguments.digest,
        built_at=arguments.built_at or datetime.now(UTC).isoformat(timespec="seconds"),
    )
    try:
        recorded = ledger.record(built)
    except AlreadyBuilt as refusal:
        print(refusal, file=err)
        return REFUSED
    recorded.write(arguments.ledger)
    print(f"{built.image}@{built.revision} is {built.digest}", file=out)
    return 0


def check(arguments: argparse.Namespace, out: TextIO = sys.stdout, err: TextIO = sys.stderr) -> int:
    """Compare each environment against the record. Non-zero if one rebuilt."""
    ledger = Ledger.read(arguments.ledger)
    verdicts = promotions(
        ledger,
        image=arguments.image,
        revision=arguments.revision,
        running=running(arguments.running),
    )
    for verdict in verdicts:
        if verdict.conforms:
            print(f"{verdict.environment} is running the recorded {verdict.recorded}", file=out)
        else:
            print(verdict.reason, file=err)
    return 0 if all(verdict.conforms for verdict in verdicts) else REFUSED


def withdraw(
    arguments: argparse.Namespace, out: TextIO = sys.stdout, err: TextIO = sys.stderr
) -> int:
    """Print the digest to redeploy, or say that the ledger does not hold one."""
    ledger = Ledger.read(arguments.ledger)
    plan = rollback(ledger, image=arguments.image, revision=arguments.revision)
    if plan.requires_build:
        print(
            f"{plan.image}@{plan.revision} has no recorded digest, so rolling back to "
            "it would mean building an artifact nobody verified",
            file=err,
        )
        return REFUSED
    print(plan.digest, file=out)
    return 0


COMMANDS = {RECORD: record, PROMOTION: check, ROLLBACK: withdraw}


def main(
    arguments: Sequence[str] | None = None, out: TextIO = sys.stdout, err: TextIO = sys.stderr
) -> int:
    """Run one command and answer with the code that gates the release."""
    given = parser().parse_args(sys.argv[1:] if arguments is None else list(arguments))
    try:
        return COMMANDS[given.command](given, out, err)
    except ValueError as malformed:
        print(str(malformed), file=err)
        return REFUSED


if __name__ == "__main__":  # pragma: no cover — exercised as a subprocess
    raise SystemExit(main())
