"""Tasks 6.2 and 6.3 — index maintenance and the mapping, as processes.

Three commands arrive with the read surface, and each of them is a promise about
a run rather than about a return value:

* **6.2 — `canon index rebuild`** reports how many assets it indexed and
  **names** every specification it could not read, without one broken file
  aborting the scan. A rebuild that stopped at the first defect is a rebuild
  nobody runs, and a count with no names is not actionable.
* **6.2 — `canon index misses`** reads back the zero-result search terms the
  read surface recorded locally (D11). The miss is produced the way a real one
  is — an agent searching for something that is not there — and the assertion
  that nothing left the machine is that the whole cycle ran with the network
  denied.
* **6.3 — the mapping is validated in the lint path that already exists.** A
  `.canon/actors.yaml` binding one email to two people makes `canon check` exit
  non-zero naming both entries, and `canon actors unmapped` lists the addresses
  nobody has bound yet. Both run with no credential and no network, because
  identity validation that needed an identity service would be unusable on the
  day it mattered.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
from game_repo import MECH_SPEC, build_game_repo

pytestmark = pytest.mark.integration

CLEAN = 0
VIOLATIONS = 1

MECH = "mech_scout"
MISSING_TERM = "hovercraft"
BROKEN_SPEC = "props/ghost/asset.yaml"

RAFA = "rafa@cyberdyne.com"
DANI = "dani@cyberdyne.com"

DUPLICATE_EMAIL_MAPPING = f"""\
schema_version: 1
actors:
  - subject: auth|rafa
    display_name: Rafa
    emails: [{RAFA}]
  - subject: auth|impostor
    display_name: Someone Else
    emails: [{RAFA}]
"""

ONE_PERSON_MAPPING = f"""\
schema_version: 1
actors:
  - subject: auth|rafa
    display_name: Rafa
    emails: [{RAFA}]
"""

DENY_NETWORK = """\
import socket


def _denied(*_arguments, **_keywords):
    raise OSError("network access is denied")


socket.socket.connect = _denied
socket.socket.connect_ex = _denied
socket.create_connection = _denied
socket.getaddrinfo = _denied
"""


def bare_environment(**extra: str) -> dict[str, str]:
    """No credential, no identity service, nothing configured — on purpose."""
    stripped = {
        name: value
        for name, value in os.environ.items()
        if not name.startswith(("CANON_", "CYBERDYNE_", "GIT_"))
        and name not in {"HOME", "USER", "LOGNAME", "GITHUB_TOKEN"}
    }
    return {**stripped, **extra}


def canon(repo: Path, *arguments: str, env: dict[str, str] | None = None) -> Any:
    """Run `canon` as a process inside `repo`, exactly as a person would."""
    return subprocess.run(
        [sys.executable, "-m", "cybercanon.cli", *arguments],
        cwd=repo,
        capture_output=True,
        text=True,
        check=False,
        env=env if env is not None else bare_environment(),
    )


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """A fresh game repository per test: these runs write an index into it."""
    return build_game_repo(tmp_path / "game").root


@pytest.fixture
def offline(tmp_path: Path) -> dict[str, str]:
    """An environment with no credential and with the network denied."""
    directory = tmp_path / "offline"
    directory.mkdir()
    (directory / "sitecustomize.py").write_text(DENY_NETWORK, encoding="utf-8")
    return bare_environment(PYTHONPATH=str(directory))


def write_mapping(repo: Path, text: str) -> None:
    (repo / ".canon").mkdir(parents=True, exist_ok=True)
    (repo / ".canon" / "actors.yaml").write_text(text, encoding="utf-8")


# --------------------------------------------------------------------------
# 6.2 — `canon index rebuild`
# --------------------------------------------------------------------------


def test_rebuild_reports_the_count_it_indexed(repo: Path, offline: dict[str, str]) -> None:
    result = canon(repo, "index", "rebuild", env=offline)

    assert result.returncode == CLEAN, result.stderr
    assert "indexed 3 assets" in result.stdout
    assert "PASSING" in result.stdout


def test_rebuild_names_the_malformed_file_and_indexes_the_rest(repo: Path) -> None:
    """One broken specification is a finding, never the end of the scan."""
    broken = repo / BROKEN_SPEC
    broken.parent.mkdir(parents=True, exist_ok=True)
    broken.write_text("schema_version: 1\nid: [this is not an identifier\n", encoding="utf-8")

    result = canon(repo, "index", "rebuild")

    assert result.returncode == VIOLATIONS
    assert "indexed 3 assets" in result.stdout
    assert BROKEN_SPEC in result.stdout
    assert "FAILING" in result.stdout


def test_rebuild_reports_the_same_thing_as_json(repo: Path) -> None:
    result = canon(repo, "index", "rebuild", "--json")

    document = json.loads(result.stdout)
    assert document["passed"] is True
    assert sorted(document["indexed"]) == ["barrel", "crate", MECH]
    assert document["unreadable"] == []


# --------------------------------------------------------------------------
# 6.2 — `canon index misses`
# --------------------------------------------------------------------------


def test_misses_are_empty_until_something_misses(repo: Path) -> None:
    canon(repo, "index", "rebuild")

    result = canon(repo, "index", "misses")

    assert result.returncode == CLEAN, result.stderr
    assert "no search term has come up empty" in result.stdout


def test_a_zero_result_search_is_recorded_and_read_back(
    repo: Path, offline: dict[str, str]
) -> None:
    """The whole D11 cycle, with the network denied: it is recorded here or nowhere."""
    canon(repo, "index", "rebuild", env=offline)
    _search(repo, MISSING_TERM, offline)
    _search(repo, MECH, offline)

    result = canon(repo, "index", "misses", env=offline)

    assert MISSING_TERM in result.stdout
    assert MECH not in result.stdout, "a search that matched is not a miss"


def _search(repo: Path, term: str, env: dict[str, str]) -> None:
    """Search the way the read surface does — there is no `canon search`."""
    probe = (
        "from pathlib import Path;"
        "from cybercanon.adapters.wiring.build import build_container;"
        f"build_container(Path('.')).search_assets({term!r})"
    )
    completed = subprocess.run(
        [sys.executable, "-c", probe],
        cwd=repo,
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )
    assert completed.returncode == 0, completed.stderr


# --------------------------------------------------------------------------
# 6.3 — the mapping, validated where the specifications are
# --------------------------------------------------------------------------


def test_a_duplicate_email_fails_the_existing_lint_path_naming_both_entries(
    repo: Path, offline: dict[str, str]
) -> None:
    """`canon check` is the lint path, and the mapping is checked in it."""
    write_mapping(repo, DUPLICATE_EMAIL_MAPPING)

    result = canon(repo, "check", env=offline)

    assert result.returncode == VIOLATIONS
    assert ".canon/actors.yaml" in result.stdout
    assert RAFA in result.stdout
    assert "auth|rafa" in result.stdout
    assert "auth|impostor" in result.stdout


def test_a_project_with_no_mapping_still_checks_clean(repo: Path) -> None:
    """The mapping is optional and additive: its absence is not a defect."""
    result = canon(repo, "check")

    assert result.returncode == CLEAN, result.stderr
    assert "PASSING" in result.stdout


def test_the_specification_findings_are_unaffected_by_the_mapping(repo: Path) -> None:
    """A broken mapping fails the run without being counted as a specification."""
    write_mapping(repo, DUPLICATE_EMAIL_MAPPING)

    result = canon(repo, "check", "--json")

    document = json.loads(result.stdout)
    assert document["passed"] is False
    assert len(document["checked"]) == 3
    assert MECH_SPEC in document["checked"]
    assert [finding["subject"] for finding in document["mapping"]]
    assert document["findings"] == []


# --------------------------------------------------------------------------
# 6.3 — `canon actors unmapped`
# --------------------------------------------------------------------------


def test_unmapped_lists_the_owners_no_entry_binds(repo: Path, offline: dict[str, str]) -> None:
    canon(repo, "index", "rebuild", env=offline)
    write_mapping(repo, ONE_PERSON_MAPPING)

    result = canon(repo, "actors", "unmapped", env=offline)

    assert result.returncode == CLEAN, result.stderr
    assert "rafa" in result.stdout
    assert "dani" in result.stdout
    assert "leo" in result.stdout


def test_unmapped_omits_the_people_the_mapping_binds(repo: Path) -> None:
    """The list is what is left to do, so a bound address must not appear on it."""
    canon(repo, "index", "rebuild")
    mapping = ONE_PERSON_MAPPING.replace(f"emails: [{RAFA}]", f"emails: [{RAFA}, rafa, dani, leo]")
    write_mapping(repo, mapping)

    result = canon(repo, "actors", "unmapped", "--json")

    assert json.loads(result.stdout)["authors"] == []
