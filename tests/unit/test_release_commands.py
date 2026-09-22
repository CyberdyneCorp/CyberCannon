"""Task 3.3 — the pipeline step that records a digest, and the checks over it.

`tests/unit/test_release_digests.py` drives the ledger as values; this suite
drives the **commands**, because task 3.3 is not "there is a record" but "the
build records one and a promotion is checked against it". So every assertion
here goes through `canon_release.__main__.main` — the entry point
`just release-record` and `just release-promotion` run — over a ledger file in a
temporary directory, and asserts the exit code a pipeline step gates on.

What is deliberately *not* here is an engine. The digest is an argument, because
the thing that knows it is the engine that built the image
(`docker image inspect --format '{{.Id}}'`), and a command that shelled out to
one could not be run by an operator checking production from a laptop. The
build-and-compare assertion lives in `tests/tooling/test_container_artifacts.py`
and skips where there is no engine, which is the honest division: this suite
asserts the record and the gate, that one asserts the build.
"""

from __future__ import annotations

import io
import json
from pathlib import Path

import pytest

from canon_release.__main__ import REFUSED, main
from canon_release.digests import API, WEB, Ledger

pytestmark = pytest.mark.unit

REVISION = "a" * 40
PREVIOUS = "b" * 40

FIRST = "sha256:" + "1" * 64
SECOND = "sha256:" + "2" * 64

STAGING = "pre-production"
PRODUCTION = "production"


class Run:
    """One command run, with what it wrote and the code it exited with."""

    def __init__(self, code: int, out: str, err: str) -> None:
        self.code = code
        self.out = out
        self.err = err


def run(*arguments: str, ledger: Path) -> Run:
    """Drive the real entry point against a ledger of our own."""
    out, err = io.StringIO(), io.StringIO()
    code = main([*arguments, "--ledger", str(ledger)], out=out, err=err)
    return Run(code, out.getvalue(), err.getvalue())


def record(ledger: Path, *, image: str = API, revision: str = REVISION, digest: str = FIRST) -> Run:
    return run(
        "record",
        "--image",
        image,
        "--revision",
        revision,
        "--digest",
        digest,
        "--built-at",
        "2026-09-22T10:00:00Z",
        ledger=ledger,
    )


@pytest.fixture
def ledger(tmp_path: Path) -> Path:
    return tmp_path / "digests.json"


# --------------------------------------------------------------------------
# The pipeline step: a build records what it produced
# --------------------------------------------------------------------------


def test_a_build_records_its_digest_against_the_revision(ledger: Path) -> None:
    outcome = record(ledger)

    assert outcome.code == 0
    assert Ledger.read(ledger).digest_for(API, REVISION) == FIRST


def test_the_record_is_a_file_a_later_run_reads(ledger: Path) -> None:
    """The ledger is committed, so the check runs from a checkout."""
    record(ledger)
    record(ledger, image=WEB, digest=SECOND)

    recorded = json.loads(ledger.read_text(encoding="utf-8"))

    assert [(entry["image"], entry["digest"]) for entry in recorded] == [
        (API, FIRST),
        (WEB, SECOND),
    ]


def test_recording_the_same_build_again_is_not_a_failure(ledger: Path) -> None:
    """A retried pipeline step is a retry, not a second build."""
    record(ledger)

    again = record(ledger)

    assert again.code == 0
    assert len(Ledger.read(ledger).builds) == 1


def test_a_second_digest_for_one_revision_stops_the_pipeline_step(ledger: Path) -> None:
    """*"Built once per revision and promoted"* — the rebuild has nowhere to go."""
    record(ledger)

    rebuilt = record(ledger, digest=SECOND)

    assert rebuilt.code == REFUSED
    assert FIRST in rebuilt.err
    assert SECOND in rebuilt.err
    assert Ledger.read(ledger).digest_for(API, REVISION) == FIRST


def test_a_build_records_nothing_for_the_other_image(ledger: Path) -> None:
    record(ledger)

    assert Ledger.read(ledger).digest_for(WEB, REVISION) == ""


# --------------------------------------------------------------------------
# The promotion check: what an environment is running against what was built
# --------------------------------------------------------------------------


def test_promotion_conforms_when_every_environment_runs_the_recorded_digest(
    ledger: Path,
) -> None:
    record(ledger)

    checked = run(
        "promotion",
        "--image",
        API,
        "--revision",
        REVISION,
        "--running",
        f"{STAGING}={FIRST}",
        f"{PRODUCTION}={FIRST}",
        ledger=ledger,
    )

    assert checked.code == 0
    assert STAGING in checked.out
    assert PRODUCTION in checked.out


def test_a_rebuilt_artifact_fails_the_check_naming_both_digests(ledger: Path) -> None:
    record(ledger)

    checked = run(
        "promotion",
        "--image",
        API,
        "--revision",
        REVISION,
        "--running",
        f"{PRODUCTION}={SECOND}",
        ledger=ledger,
    )

    assert checked.code == REFUSED
    assert FIRST in checked.err
    assert SECOND in checked.err
    assert PRODUCTION in checked.err


def test_an_unrecorded_revision_is_reported_as_never_verified(ledger: Path) -> None:
    checked = run(
        "promotion",
        "--image",
        API,
        "--revision",
        REVISION,
        "--running",
        f"{PRODUCTION}={FIRST}",
        ledger=ledger,
    )

    assert checked.code == REFUSED
    assert "never verified" in checked.err


def test_a_malformed_environment_pair_is_refused_rather_than_ignored(ledger: Path) -> None:
    """A dropped pair would report conformance for an environment nobody checked."""
    record(ledger)

    checked = run(
        "promotion", "--image", API, "--revision", REVISION, "--running", FIRST, ledger=ledger
    )

    assert checked.code == REFUSED
    assert "<environment>=<digest>" in checked.err


# --------------------------------------------------------------------------
# Rollback: the digest a withdrawal deploys, and no build
# --------------------------------------------------------------------------


def test_rolling_back_answers_the_previous_revisions_recorded_digest(ledger: Path) -> None:
    """Deploy N, then N-1: what is deployed is what was already built."""
    record(ledger, revision=PREVIOUS, digest=FIRST)
    record(ledger, revision=REVISION, digest=SECOND)

    withdrawn = run("rollback", "--image", API, "--revision", PREVIOUS, ledger=ledger)

    assert withdrawn.code == 0
    assert withdrawn.out.strip() == FIRST
    assert Ledger.read(ledger).digest_for(API, PREVIOUS) == FIRST


def test_rolling_back_records_no_new_build(ledger: Path) -> None:
    """*"No rebuild SHALL be required"* — and none is performed."""
    record(ledger, revision=PREVIOUS, digest=FIRST)
    record(ledger, revision=REVISION, digest=SECOND)
    before = ledger.read_text(encoding="utf-8")

    run("rollback", "--image", API, "--revision", PREVIOUS, ledger=ledger)

    assert ledger.read_text(encoding="utf-8") == before


def test_rolling_back_to_a_revision_nobody_built_is_refused(ledger: Path) -> None:
    record(ledger, revision=REVISION, digest=SECOND)

    withdrawn = run("rollback", "--image", API, "--revision", PREVIOUS, ledger=ledger)

    assert withdrawn.code == REFUSED
    assert "nobody verified" in withdrawn.err


def test_an_absent_ledger_reads_as_empty_rather_than_failing(ledger: Path) -> None:
    withdrawn = run("rollback", "--image", API, "--revision", REVISION, ledger=ledger)

    assert withdrawn.code == REFUSED
    assert not ledger.exists()
