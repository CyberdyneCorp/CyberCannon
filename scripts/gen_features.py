#!/usr/bin/env python3
"""Generate the BDD feature files from the OpenSpec spec deltas.

    just gen-features                 # write tests/bdd/features/ from the specs
    just features                     # fail if the committed features drifted (D1)
    python scripts/gen_features.py --bootstrap-pending   # one-time, see below

The spec deltas are the source of truth: nobody hand-writes a `.feature`, and a
hand edit is overwritten by the next run and rejected by `just features` before
that. Parsing is strict — a spec that cannot be parsed names its file and line
and stops the run, because a skipped spec is an untested requirement that looks
tested.

`--bootstrap-pending` rewrites `tests/bdd/pending.txt` with every scenario that
has no step definition. It exists to bootstrap the list once, and it is
deliberately not a `just` recipe: routinely regenerating the pending list would
turn the one reviewed exception into a silent skip.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "tools"))

from canon_bdd import generator, implemented, pending, specs, traceability  # noqa: E402

EXIT_OK = 0
EXIT_DRIFTED = 1
EXIT_UNPARSEABLE = 2


def main(argv: list[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    repo_root = arguments.repo_root.resolve()
    try:
        return _run(arguments, repo_root)
    except (specs.SpecParseError, pending.PendingListError) as error:
        print(f"error: {error}", file=sys.stderr)
        print("The spec deltas are the source of the test suite; fix the spec.", file=sys.stderr)
        return EXIT_UNPARSEABLE


def _run(arguments: argparse.Namespace, repo_root: Path) -> int:
    if arguments.check:
        return _check(repo_root)
    if arguments.bootstrap_pending:
        return _bootstrap_pending(repo_root)
    return _write(repo_root)


def _write(repo_root: Path) -> int:
    written = generator.write(repo_root)
    scenarios = sum(len(spec.scenarios) for spec in generator.load_specs(repo_root))
    print(f"{len(written)} feature files, {scenarios} scenarios, written to tests/bdd/features/")
    return EXIT_OK


def _check(repo_root: Path) -> int:
    differences = generator.check(repo_root)
    if not differences:
        print("tests/bdd/features/ matches the spec deltas")
        return EXIT_OK
    print("The committed features do not match the spec deltas:", file=sys.stderr)
    for difference in differences:
        print(f"  {difference}", file=sys.stderr)
    print("Run `just gen-features`; never edit a generated .feature by hand.", file=sys.stderr)
    return EXIT_DRIFTED


def _bootstrap_pending(repo_root: Path) -> int:
    parsed = generator.load_specs(repo_root)
    bound = implemented.discover(repo_root / implemented.STEPS_DIR)
    statuses = traceability.classify(parsed, bound, ())
    keys = [status.key for status in statuses if status.state != traceability.EXECUTING]
    path = repo_root / pending.PENDING_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(pending.render(keys), encoding="utf-8")
    print(f"{len(keys)} scenarios written to {pending.PENDING_PATH.as_posix()}")
    return EXIT_OK


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--check",
        action="store_true",
        help="do not write; fail when the committed features differ from the specs (D1)",
    )
    parser.add_argument(
        "--bootstrap-pending",
        action="store_true",
        help="rewrite tests/bdd/pending.txt with every scenario that has no step definition",
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=REPO_ROOT,
        help="repository root to read specs from and write features to",
    )
    return parser


if __name__ == "__main__":
    raise SystemExit(main())
