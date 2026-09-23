"""Tasks 3.5 and 3.6 — the outbox as a file in a real repository (D6, D7).

The conformance suite already holds the outbox to the `OutcomeReporter`
contract. What can only be checked here is what the file *is*:

* **it is invisible to git.** The repository carries this project's own
  `.gitignore`, copied rather than written for the test, so removing the line
  that ships fails this. A retained report appearing in `git status` would be a
  second copy of a fact whose durable home G2 already settled — the committed
  `asset.validation.json` — and it would put telemetry in an artist's diff;
* **it survives its own corruption** (3.6). A truncated line is skipped and
  reported, and everything else is still delivered. An outbox that refused the
  whole file over one bad line would have converted a cosmetic failure into the
  silent outage D6's mitigation exists to prevent;
* **it is bounded.** A machine that has never reached a destination keeps the
  most recent reports and drops the oldest, because outcomes are telemetry and
  the verdict is authoritative locally.
"""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass, field, replace
from pathlib import Path

import pytest

from cybercanon.adapters.outbound.fs.outbox import OUTBOX_PATH, FileOutbox
from cybercanon.application.ports.outcome_reporter import ReportedOutcome

pytestmark = pytest.mark.integration

OUTCOME = ReportedOutcome(
    asset_id="mech_scout",
    export="characters/mech_scout/exports/SM_mech_scout_LOD0.glb",
    export_hash="sha256:aaaa",
    verdict_hash="sha256:vvvv",
    passed=False,
    errors=2,
    reported_at="2026-03-01T12:00:00+00:00",
    attributed_to="rafa",
    via="blender-agent",
)


@dataclass
class Destination:
    """Somewhere to report to, which can stop answering."""

    reachable: bool = True
    delivered: list[ReportedOutcome] = field(default_factory=list)

    def __call__(self, outcome: ReportedOutcome) -> None:
        if not self.reachable:
            raise ConnectionError("unreachable")
        self.delivered.append(outcome)


def _git(root: Path, *arguments: str) -> subprocess.CompletedProcess[bytes]:
    environment = {
        **os.environ,
        "HOME": str(root),
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_AUTHOR_NAME": "Rafa",
        "GIT_AUTHOR_EMAIL": "rafa@cyberdyne.com",
        "GIT_COMMITTER_NAME": "Rafa",
        "GIT_COMMITTER_EMAIL": "rafa@cyberdyne.com",
    }
    return subprocess.run(
        ["git", "-C", str(root), *arguments], check=True, capture_output=True, env=environment
    )


@pytest.fixture
def repository(tmp_path: Path, repo_root: Path) -> Path:
    """A committed repository carrying this project's own ignore rules."""
    root = tmp_path / "game"
    root.mkdir()
    _git(root, "init", "-q")
    (root / ".gitignore").write_text(
        (repo_root / ".gitignore").read_text(encoding="utf-8"), encoding="utf-8"
    )
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "the ignore rules that ship")
    return root


# --------------------------------------------------------------------------
# 3.5 — retained, retried, and absent from `git status`
# --------------------------------------------------------------------------


def test_a_report_that_cannot_be_delivered_is_retained(repository: Path) -> None:
    destination = Destination(reachable=False)
    outbox = FileOutbox(repository, deliver=destination)

    delivery = outbox.report(OUTCOME)

    assert delivery.delivered == 0
    assert delivery.pending == 1
    assert outbox.pending() == (OUTCOME,)
    assert destination.delivered == []


def test_a_later_flush_delivers_what_was_retained(repository: Path) -> None:
    destination = Destination(reachable=False)
    outbox = FileOutbox(repository, deliver=destination)
    outbox.report(OUTCOME)

    destination.reachable = True
    delivery = outbox.flush()

    assert delivery.delivered == 1
    assert delivery.complete
    assert destination.delivered == [OUTCOME]
    assert outbox.pending() == ()


def test_the_outbox_is_a_file_under_canon(repository: Path) -> None:
    FileOutbox(repository, deliver=Destination(reachable=False)).report(OUTCOME)

    assert (repository / OUTBOX_PATH).is_file()


def test_the_outbox_never_appears_in_git_status(repository: Path) -> None:
    """The line in the `.gitignore` that ships is what makes this pass."""
    FileOutbox(repository, deliver=Destination(reachable=False)).report(OUTCOME)

    assert _git(repository, "status", "--porcelain").stdout == b""


def test_a_machine_with_no_destination_keeps_reporting_successfully(repository: Path) -> None:
    """The ordinary local case: nowhere to send it, and nothing goes wrong."""
    outbox = FileOutbox(repository)

    delivery = outbox.report(OUTCOME)

    assert delivery.pending == 1
    assert delivery.reason
    assert outbox.pending() == (OUTCOME,)


def test_re_reporting_one_run_keeps_one_record(repository: Path) -> None:
    """D7 — the triple is the identity, so a restarted agent does not accumulate."""
    outbox = FileOutbox(repository, deliver=Destination(reachable=False))

    outbox.report(OUTCOME)
    outbox.report(OUTCOME)

    assert outbox.pending() == (OUTCOME,)
    assert len((repository / OUTBOX_PATH).read_text(encoding="utf-8").strip().splitlines()) == 1


def test_a_re_export_is_a_second_record(repository: Path) -> None:
    outbox = FileOutbox(repository, deliver=Destination(reachable=False))

    outbox.report(OUTCOME)
    outbox.report(replace(OUTCOME, export_hash="sha256:bbbb"))

    assert {outcome.export_hash for outcome in outbox.pending()} == {"sha256:aaaa", "sha256:bbbb"}


# --------------------------------------------------------------------------
# 3.6 — bounded, and self-healing
# --------------------------------------------------------------------------


def test_a_corrupt_line_is_skipped_and_reported_rather_than_fatal(repository: Path) -> None:
    outbox = FileOutbox(repository, deliver=Destination(reachable=False))
    outbox.report(OUTCOME)
    file = repository / OUTBOX_PATH
    file.write_text(
        '{"asset": "mech_scout", "truncated"\n' + file.read_text(encoding="utf-8"),
        encoding="utf-8",
    )

    pending = outbox.pending()

    assert pending == (OUTCOME,)
    assert outbox.skipped


def test_a_corrupt_line_does_not_block_delivery_of_the_rest(repository: Path) -> None:
    destination = Destination()
    outbox = FileOutbox(repository, deliver=destination)
    file = repository / OUTBOX_PATH
    file.parent.mkdir(parents=True, exist_ok=True)
    file.write_text("}} not json at all\n", encoding="utf-8")

    delivery = outbox.report(OUTCOME)

    assert destination.delivered == [OUTCOME]
    assert delivery.delivered == 1
    assert delivery.complete
    assert "skipped" in delivery.reason
    assert outbox.flush().complete, "the bad line healed itself on the way through"


def test_the_outbox_is_bounded(repository: Path) -> None:
    outbox = FileOutbox(repository, deliver=Destination(reachable=False), capacity=3)

    for index in range(6):
        outbox.report(replace(OUTCOME, export_hash=f"sha256:{index}"))

    assert [outcome.export_hash for outcome in outbox.pending()] == [
        "sha256:3",
        "sha256:4",
        "sha256:5",
    ]
