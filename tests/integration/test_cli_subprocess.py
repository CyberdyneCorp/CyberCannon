"""Tasks 6.3-6.8 — the `canon` binary, run as a process, against real files.

A CLI is a contract about a *process*: its exit code, its standard output and
what it needs from the environment before it will run. None of that is provable
by calling a function, so every assertion here starts a subprocess in a
repository written from code, exactly as a pre-commit hook or a CI job would.

What each group holds down:

* **6.3** the three exit codes — `0` clean, `1` error-severity violations, `2`
  could not run — including the missing file, which names the file.
* **6.4** a violation line naming the asset, the subject, the observed value and
  the expected one, so the reader acts without opening `asset.yaml`.
* **6.5** every not-evaluated rule printed by name with its reason, never a
  count: the only place a wrong matrix row is ever visible (D13).
* **6.6** `--json`, whose standard output parses whole with nothing else on it.
* **6.7** changed-file invocation validating only the assets those files belong
  to, and exiting `0` when none of them belongs to one.
* **6.8** a run on a machine with no identity, no token and no configuration —
  the requirement the validator would be worthless without.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
from game_repo import (
    BARREL_BUDGET,
    BARREL_EXPORT,
    CRATE_EXPORT,
    MECH_EXPORT,
    MECH_SPEC,
    GameRepo,
    build_game_repo,
)

pytestmark = pytest.mark.integration

CLEAN = 0
VIOLATIONS = 1
COULD_NOT_RUN = 2

MISSING_EXPORT = "characters/mech_scout/exports/SM_mech_scout_LOD9.glb"
UNGOVERNED = "docs/pipeline.glb"


def canon(repo: Path, *arguments: str, env: dict[str, str] | None = None) -> Any:
    """Run `canon` as a process inside `repo`, exactly as a hook would."""
    return subprocess.run(
        [sys.executable, "-m", "cybercanon.cli", *arguments],
        cwd=repo,
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )


@pytest.fixture(scope="module")
def repo(tmp_path_factory: pytest.TempPathFactory) -> GameRepo:
    """One repository for the module: every run below is read-only over it."""
    return build_game_repo(tmp_path_factory.mktemp("game"))


# --------------------------------------------------------------------------
# 6.3 — the exit-code seam
# --------------------------------------------------------------------------


def test_a_clean_export_exits_zero(repo: GameRepo) -> None:
    result = canon(repo.root, "validate", MECH_EXPORT)

    assert result.returncode == CLEAN, result.stderr
    assert "PASSING" in result.stdout


def test_an_error_severity_violation_exits_one(repo: GameRepo) -> None:
    result = canon(repo.root, "validate", BARREL_EXPORT)

    assert result.returncode == VIOLATIONS
    assert "FAILING" in result.stdout


def test_a_missing_export_exits_two_and_names_the_file(repo: GameRepo) -> None:
    """`2` is reserved for "could not run" — never conflated with a bad mesh."""
    result = canon(repo.root, "validate", MISSING_EXPORT)

    assert result.returncode == COULD_NOT_RUN
    assert MISSING_EXPORT in result.stderr
    assert result.stdout == ""


def test_an_export_with_no_governing_spec_exits_two(repo: GameRepo) -> None:
    (repo.root / UNGOVERNED).parent.mkdir(parents=True, exist_ok=True)
    (repo.root / UNGOVERNED).write_bytes(b"not a mesh")

    result = canon(repo.root, "validate", UNGOVERNED)

    assert result.returncode == COULD_NOT_RUN
    assert "no asset.yaml governs" in result.stderr
    assert UNGOVERNED in result.stderr


def test_check_reports_structural_violations_over_the_repository(repo: GameRepo) -> None:
    result = canon(repo.root, "check")

    assert result.returncode == CLEAN, result.stderr
    assert MECH_SPEC in result.stdout
    assert "3 specification files checked" in result.stdout


# --------------------------------------------------------------------------
# 6.4 — a violation states the fix
# --------------------------------------------------------------------------


def test_a_budget_violation_names_asset_subject_observed_and_expected(repo: GameRepo) -> None:
    result = canon(repo.root, "validate", BARREL_EXPORT)

    line = _line_with(result.stdout, "tri_budget.exceeded")
    assert "asset barrel" in line
    assert "subject triangles" in line
    assert f"observed {repo.barrel.triangles}" in line
    assert f"expected {BARREL_BUDGET}" in line


# --------------------------------------------------------------------------
# 6.5 — not-evaluated rules, by name, never a count
# --------------------------------------------------------------------------


def test_an_obj_run_lists_every_suppressed_rule_by_name(repo: GameRepo) -> None:
    """OBJ records four facts; every rule the others feed must be named, with why."""
    result = canon(repo.root, "validate", CRATE_EXPORT)
    payload = _json_run(repo, "validate", CRATE_EXPORT)

    assert result.returncode == CLEAN, result.stderr
    suppressed = [entry["rule_id"] for entry in payload["results"][0]["not_evaluated"]]
    assert suppressed
    for rule_id in suppressed:
        line = _line_with(result.stdout, rule_id)
        assert "OBJ carries no" in line


def test_the_not_evaluated_section_is_a_listing_and_not_a_count(repo: GameRepo) -> None:
    result = canon(repo.root, "validate", CRATE_EXPORT)
    payload = _json_run(repo, "validate", CRATE_EXPORT)

    listed = sum(1 for line in result.stdout.splitlines() if "carries no" in line)
    assert listed == len(payload["results"][0]["not_evaluated"])


# --------------------------------------------------------------------------
# 6.6 — machine-readable mode
# --------------------------------------------------------------------------


def test_json_mode_writes_only_the_structured_result_to_stdout(repo: GameRepo) -> None:
    result = canon(repo.root, "validate", "--json", BARREL_EXPORT)
    payload = json.loads(result.stdout)

    assert result.returncode == VIOLATIONS
    assert payload["command"] == "validate"
    assert payload["passed"] is False


def test_the_structured_result_keeps_violations_and_suppressions_apart(repo: GameRepo) -> None:
    payload = _json_run(repo, "validate", CRATE_EXPORT)
    result = payload["results"][0]

    assert result["export_format"] == "OBJ"
    assert result["violations"] == []
    assert {entry["rule_id"] for entry in result["not_evaluated"]}
    assert all(entry["reason"] for entry in result["not_evaluated"])


def test_json_mode_keeps_a_failure_out_of_stdout_prose(repo: GameRepo) -> None:
    """An operation that could not run is still data, and still not a verdict."""
    result = canon(repo.root, "validate", "--json", MISSING_EXPORT)
    payload = json.loads(result.stdout)

    assert result.returncode == COULD_NOT_RUN
    assert payload["ran"] is False
    assert MISSING_EXPORT in payload["error"]["subject"]
    assert MISSING_EXPORT in result.stderr


# --------------------------------------------------------------------------
# 6.7 — changed-file invocation
# --------------------------------------------------------------------------


def test_only_the_assets_the_changed_files_belong_to_are_validated(repo: GameRepo) -> None:
    result = canon(repo.root, "changed", "--json", MECH_EXPORT)
    payload = json.loads(result.stdout)

    assert result.returncode == CLEAN, result.stderr
    assert payload["assets"] == [MECH_SPEC]
    assert [entry["asset"] for entry in payload["results"]] == ["mech_scout"]


def test_a_changed_file_that_belongs_to_no_asset_exits_zero_without_work(
    repo: GameRepo,
) -> None:
    (repo.root / "README.md").write_text("# Ronin\n", encoding="utf-8")

    result = canon(repo.root, "changed", "README.md")

    assert result.returncode == CLEAN
    assert "no changed file belongs to an asset" in result.stdout


def test_a_changed_over_budget_export_fails_the_run(repo: GameRepo) -> None:
    result = canon(repo.root, "changed", BARREL_EXPORT)

    assert result.returncode == VIOLATIONS
    assert "tri_budget.exceeded" in result.stdout


# --------------------------------------------------------------------------
# 6.8 — no credentials, no configuration ceremony
# --------------------------------------------------------------------------


def test_validation_completes_on_a_machine_with_no_identity_configured(
    repo: GameRepo, tmp_path: Path
) -> None:
    """No token, no home, no CANON_* variable, no prompt — and still a verdict."""
    clean = {"PATH": os.environ["PATH"], "HOME": str(tmp_path / "fresh-home")}

    result = subprocess.run(
        [sys.executable, "-m", "cybercanon.cli", "validate", MECH_EXPORT],
        cwd=repo.root,
        capture_output=True,
        text=True,
        check=False,
        env=clean,
        stdin=subprocess.DEVNULL,
        timeout=120,
    )

    assert result.returncode == CLEAN, result.stderr
    assert "PASSING" in result.stdout
    assert not any(word in result.stdout.lower() for word in ("login", "token", "password"))


def test_no_canon_environment_variable_is_required(repo: GameRepo) -> None:
    assert not [name for name in os.environ if name.startswith("CANON_")]

    result = canon(repo.root, "check", env={"PATH": os.environ["PATH"]})

    assert result.returncode == CLEAN, result.stderr


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------


def _json_run(repo: GameRepo, *arguments: str) -> dict[str, Any]:
    result = canon(repo.root, arguments[0], "--json", *arguments[1:])
    return json.loads(result.stdout)


def _line_with(text: str, needle: str) -> str:
    matching = [line for line in text.splitlines() if needle in line]
    assert matching, f"no line mentions {needle!r} in:\n{text}"
    return matching[0]
