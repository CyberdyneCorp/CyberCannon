"""Tasks 6.1 and 6.2 — `canon login`, `canon whoami`, `canon logout`, `canon report flush`.

These are the commands D5 and D6 name, and every one of them is a claim about a
*process*: what it exits with, what it puts on standard output, and what it
leaves behind on the machine. So the sign-in half runs as a subprocess against a
stubbed authorization server on a real socket, with a keychain the child
imports instead of the developer's own (`machine.py` explains both), and nothing
below is a mock of the flow.

* **6.1** — a sign-in completes without a secret being typed or printed;
  `whoami` names the person, whether this machine may write at all, and how many
  reported outcomes are still undelivered (D6's mitigation for a silent
  reporting outage); `logout` removes the credential and leaves every read
  working, which is the specified degradation rather than an accident.
* **6.2** — `report flush` delivers what was retained, says how many went and
  how many stayed, and exits zero when nothing could be delivered at all.

The delivery half runs in-process, because the local composition root wires the
outbox with **no destination** — a laptop has nowhere to report to, which is the
ordinary case D6 designs for — and the only way to exercise a delivery is to
hand the outbox somewhere to deliver to, exactly as the hosted surface will.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest
from game_repo import MECH_EXPORT, build_game_repo
from machine import (
    AGENT,
    GIT_EMAIL,
    PERSON,
    SUBJECT,
    Issuing,
    bare_environment,
    signing_issuer,
)
from typer.testing import CliRunner

from cybercanon.adapters.inbound.cli.app import build_app
from cybercanon.adapters.outbound.fs.outbox import OUTBOX_PATH, FileOutbox
from cybercanon.adapters.wiring.container import Container
from cybercanon.application.ports.outcome_reporter import ReportedOutcome
from cybercanon.application.testing import build_fakes

pytestmark = pytest.mark.integration

CLEAN = 0

RETAINED = ReportedOutcome(
    asset_id="mech_scout",
    export=MECH_EXPORT,
    export_hash="a1b2c3",
    verdict_hash="d4e5f6",
    passed=True,
    reported_at="2026-03-01T12:00:00+00:00",
    attributed_to=PERSON,
    via=AGENT,
)
"""One outcome a machine reported earlier and could not deliver."""


def canon(repo: Path, *arguments: str, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    """Run `canon` as a process inside a working copy, exactly as a person does."""
    return subprocess.run(
        [sys.executable, "-m", "cybercanon.cli", *arguments],
        cwd=repo,
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )


@pytest.fixture(scope="module")
def game(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return build_game_repo(tmp_path_factory.mktemp("signed-in")).root


@pytest.fixture
def issuing() -> Issuing:
    with signing_issuer() as running:
        yield running


@pytest.fixture
def machine(tmp_path: Path, issuing: Issuing) -> dict[str, str]:
    """A machine with an issuer it can reach and a keychain it can write to."""
    from machine import stub_keychain

    return bare_environment(
        stub_keychain(tmp_path / "keychain"),
        **issuing.environment,
        CANON_AGENT=AGENT,
    )


# --------------------------------------------------------------------------
# 6.1 — signing in, asking who this machine is, and signing out again
# --------------------------------------------------------------------------


def test_signing_in_completes_against_the_authorization_server(
    game: Path, machine: dict[str, str]
) -> None:
    """The whole device flow, over a socket, ending in a stored credential."""
    result = canon(game, "login", env=machine)

    assert result.returncode == CLEAN, result.stderr
    assert "credential store" in result.stdout
    assert "WDJB-MJHT" in result.stderr, "the person is shown the code to confirm"
    assert "/activate" in result.stderr, "and the address to open"


def test_the_sign_in_prints_no_credential_anywhere(game: Path, machine: dict[str, str]) -> None:
    """A token in a scrollback is a token somebody else has."""
    result = canon(game, "login", env=machine)
    written = result.stdout + result.stderr

    assert "eyJ" not in written, "a JWT begins `eyJ`; none may be printed"


def test_whoami_names_the_person_and_the_pending_report_count(
    game: Path, machine: dict[str, str]
) -> None:
    """It names them by **subject**, because that is what the credential carries.

    A CyberdyneAuth access token has no `name` and no `email`: the display name
    this used to print came from a claim the fixture minted and the identity
    service has never sent. The stable subject is what authorization,
    attribution and `.canon/actors.yaml` all agree on, so it is what a person
    sees here — and the readable name, where a surface wants one, is the mapping
    file's to supply (D13).
    """
    canon(game, "login", env=machine)

    result = canon(game, "whoami", env=machine)

    assert result.returncode == CLEAN, result.stderr
    assert SUBJECT in result.stdout
    assert "0 report(s) pending" in result.stdout


def test_whoami_says_this_machine_may_write(game: Path, machine: dict[str, str]) -> None:
    """Identity *and* agent: `may_write` is the question a person is really asking."""
    canon(game, "login", env=machine)

    document = json.loads(canon(game, "whoami", "--json", env=machine).stdout)

    assert document["signed_in"] is True
    assert document["verified"] is True
    assert document["may_write"] is True
    assert document["agent"] == AGENT
    assert "eyJ" not in json.dumps(document), "never the credential itself"


def test_whoami_without_an_agent_identifier_says_writes_are_refused(
    game: Path, machine: dict[str, str]
) -> None:
    without_agent = {name: value for name, value in machine.items() if name != "CANON_AGENT"}
    canon(game, "login", env=without_agent)

    result = canon(game, "whoami", "--json", env=without_agent)

    assert json.loads(result.stdout)["may_write"] is False
    assert json.loads(result.stdout)["signed_in"] is True


def test_whoami_counts_what_the_outbox_is_holding(
    game: Path, machine: dict[str, str], tmp_path: Path
) -> None:
    """A growing outbox is visible where a person already looks (D6)."""
    repo = build_game_repo(tmp_path / "holding").root
    FileOutbox(repo).report(RETAINED)

    result = canon(repo, "whoami", env=machine)

    assert "1 report(s) pending" in result.stdout


def test_signing_out_removes_the_credential_and_leaves_reads_working(
    game: Path, machine: dict[str, str]
) -> None:
    """*"Subsequent writes SHALL be refused while reads continue to succeed."*"""
    canon(game, "login", env=machine)

    signed_out = canon(game, "logout", env=machine)
    after = canon(game, "whoami", "--json", env=machine)
    read = canon(game, "validate", MECH_EXPORT, env=machine)

    assert signed_out.returncode == CLEAN, signed_out.stderr
    assert json.loads(after.stdout)["signed_in"] is False
    assert json.loads(after.stdout)["may_write"] is False
    assert read.returncode == CLEAN, read.stderr
    assert "PASSING" in read.stdout


def test_signing_out_twice_is_not_an_error(game: Path, machine: dict[str, str]) -> None:
    canon(game, "login", env=machine)

    assert canon(game, "logout", env=machine).returncode == CLEAN
    assert canon(game, "logout", env=machine).returncode == CLEAN


def test_a_machine_that_never_signed_in_still_answers_whoami(game: Path) -> None:
    """The local-first case: no issuer, no credential, and a straight answer."""
    result = canon(game, "whoami", env=bare_environment())

    assert result.returncode == CLEAN, result.stderr
    assert "not signed in" in result.stdout


# --------------------------------------------------------------------------
# 6.2 — flushing what the machine is still holding
# --------------------------------------------------------------------------


def a_container(root: Path, reporter: FileOutbox) -> Container:
    """The command line over one outbox. Nothing else is needed to flush."""
    fakes = build_fakes()
    return Container(
        spec_store=fakes["spec_store"],
        mesh_inspector=fakes["mesh_inspector"],
        outcome_reporter=reporter,
    )


def test_flush_delivers_what_was_retained(tmp_path: Path) -> None:
    delivered: list[ReportedOutcome] = []
    outbox = FileOutbox(tmp_path, deliver=delivered.append)
    FileOutbox(tmp_path).report(RETAINED)

    result = CliRunner().invoke(build_app(a_container(tmp_path, outbox)), ["report", "flush"])

    assert result.exit_code == CLEAN
    assert "1 delivered" in result.stdout
    assert [outcome.key for outcome in delivered] == [RETAINED.key]
    assert outbox.pending() == ()


def test_flush_reports_the_delivered_and_still_pending_counts(tmp_path: Path) -> None:
    """Two retained outcomes, a destination that takes one and then stops."""
    taken: list[ReportedOutcome] = []

    def unreliable(outcome: ReportedOutcome) -> None:
        if taken:
            raise ConnectionError("the destination stopped answering")
        taken.append(outcome)

    keeping = FileOutbox(tmp_path)
    keeping.report(RETAINED)
    keeping.report(ReportedOutcome(**{**RETAINED.__dict__, "verdict_hash": "999"}))

    result = CliRunner().invoke(
        build_app(a_container(tmp_path, FileOutbox(tmp_path, deliver=unreliable))),
        ["report", "flush", "--json"],
    )
    document = json.loads(result.stdout)

    assert result.exit_code == CLEAN
    assert document["delivered"] == 1
    assert document["pending"] == 1
    assert "unreachable" in document["reason"]


def test_flush_exits_zero_when_the_destination_is_unreachable(
    game: Path, machine: dict[str, str], tmp_path: Path
) -> None:
    """A report that could fail a command is a report that blocks a commit (D6)."""
    repo = build_game_repo(tmp_path / "unreachable").root
    FileOutbox(repo).report(RETAINED)

    result = canon(repo, "report", "flush", env=machine)

    assert result.returncode == CLEAN, result.stderr
    assert "1 pending" in result.stdout
    assert "verdict stands" in result.stdout
    assert (repo / OUTBOX_PATH).is_file(), "what could not be delivered is still here"


def test_the_retained_report_names_both_parties(tmp_path: Path) -> None:
    """Whatever happens to delivery, the record keeps the person and the agent."""
    outbox = FileOutbox(tmp_path)
    outbox.report(RETAINED)

    (kept,) = outbox.pending()

    assert kept.attributed_to == PERSON
    assert kept.via == AGENT
    assert GIT_EMAIL not in json.dumps(kept.__dict__), "attribution is the actor, not an address"


def test_flush_on_a_machine_with_nothing_to_send_is_not_a_failure(
    game: Path, machine: dict[str, str]
) -> None:
    result = canon(game, "report", "flush", env=machine)

    assert result.returncode == CLEAN
    assert "0 delivered" in result.stdout
