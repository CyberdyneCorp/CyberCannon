"""Step definitions for `canon-cli` — the surface a person and a hook type at.

Group 6 of `add-asset-spec-and-validator` builds the inbound CLI: a composition
root, four thin commands, one exit-code seam and two renderings. Every scenario
here drives the **real Typer application**, built over the in-memory fakes, so
what is exercised is the command the artist runs — argument parsing, discovery,
the exit code and the text — with no repository on disk.

The one thing a runner cannot prove is what a *process* does on a machine with
no identity configured, so the subprocess proofs (all three exit codes from a
real shell, `--json` standard output parsed whole, and a run with an empty
environment) live in `tests/integration/test_cli_subprocess.py`, which is where
tasks 6.3 and 6.8 put them. What is asserted below is the behaviour the spec
states: the same codes, the same discovery, the same message content.
"""

from __future__ import annotations

import json
from typing import Any

import pytest
from pytest_bdd import given, scenario, then, when
from typer.testing import CliRunner

from cybercanon.adapters.inbound.cli.app import build_app
from cybercanon.adapters.inbound.cli.exit_codes import CLEAN, COULD_NOT_RUN, VIOLATIONS
from cybercanon.adapters.wiring.container import Container
from cybercanon.application.testing import build_fakes
from cybercanon.domain.asset import Asset, AssetId
from cybercanon.domain.constraints import Constraints
from cybercanon.domain.format_matrix import facts_for
from cybercanon.domain.mesh_facts import MeshFormat
from cybercanon.domain.rules import budgets
from cybercanon.domain.status import Status

ASSET_ID = "mech_scout"
SPEC_PATH = "characters/mech_scout/asset.yaml"
EXPORT = "characters/mech_scout/exports/SM_mech_scout_LOD0.glb"
OBJECT = "SM_mech_scout_LOD0"

OTHER_ID = "supply_crate"
OTHER_SPEC = "props/supply_crate/asset.yaml"
OTHER_EXPORT = "props/supply_crate/exports/SM_supply_crate_LOD0.glb"

UNGOVERNED = "docs/pipeline/turntable.glb"
MISSING = "characters/mech_scout/exports/SM_mech_scout_LOD9.glb"
UNRELATED = "docs/pipeline.md"

TRI_BUDGET = 12000
OVER_BUDGET = 14310

NO_CREDENTIALS: dict[str, str] = {}
"""A fresh machine: no token, no stored configuration, nothing in the environment."""


def an_asset(asset_id: str, **constraints: Any) -> Asset:
    return Asset(
        id=AssetId(asset_id),
        name=asset_id,
        status=Status.MODELING,
        constraints=Constraints(naming="SM_{asset}_LOD{n}", **constraints),
    )


def a_glb(triangles: int, objects: tuple[str, ...]) -> Any:
    """A glTF export's facts, hand-built: no file, no library, no fixture (D1)."""
    return facts_for(
        MeshFormat.GLB,
        triangles=triangles,
        objects=objects,
        transforms_applied=True,
        unit_scale=1.0,
        up_axis="Y",
        uv_sets=1,
        materials=("M_mech_scout",),
        empties=(),
        clips=(),
        frame_rate=None,
        is_skinned=False,
        bone_count=0,
    )


@pytest.fixture
def cli() -> dict[str, Any]:
    """The application under test, its fakes, and whatever running it produced."""
    fakes = build_fakes()
    container = Container(
        spec_store=fakes["spec_store"],
        mesh_inspector=fakes["mesh_inspector"],
        blob_store=fakes["blob_store"],
    )
    return {"fakes": fakes, "container": container, "app": build_app(container)}


def _seed(cli: dict[str, Any], triangles: int = 9000) -> None:
    cli["fakes"]["spec_store"].add(SPEC_PATH, an_asset(ASSET_ID, tri_budget=TRI_BUDGET))
    cli["fakes"]["mesh_inspector"].add(EXPORT, a_glb(triangles, (OBJECT,)))


def _seed_second_asset(cli: dict[str, Any]) -> None:
    cli["fakes"]["spec_store"].add(OTHER_SPEC, an_asset(OTHER_ID, tri_budget=2000))
    cli["fakes"]["mesh_inspector"].add(OTHER_EXPORT, a_glb(9000, ("SM_supply_crate_LOD0",)))


def _run(cli: dict[str, Any], *arguments: str, env: dict[str, str] | None = None) -> Any:
    result = CliRunner().invoke(cli["app"], list(arguments), env=env, input="")
    cli["result"] = result
    return result


def _output(cli: dict[str, Any]) -> str:
    return cli["result"].stdout


# --------------------------------------------------------------------------
# Command surface
# --------------------------------------------------------------------------


@scenario("../features/add-asset-spec-and-validator/canon-cli.feature", "Validate an export")
def test_validate_an_export() -> None: ...


@when("the user runs the validate command against an export file")
def _run_validate(cli: dict[str, Any]) -> None:
    _seed(cli, triangles=OVER_BUDGET)
    _run(cli, "validate", EXPORT)


@then("the tool SHALL report the violations for that export")
def _the_violations_are_reported(cli: dict[str, Any]) -> None:
    output = _output(cli)
    assert budgets.TRI_BUDGET in output
    assert EXPORT in output
    assert str(OVER_BUDGET) in output


@scenario("../features/add-asset-spec-and-validator/canon-cli.feature", "Check specification files")
def test_check_specification_files() -> None: ...


@when("the user runs the check command over a repository")
def _run_check(cli: dict[str, Any]) -> None:
    store = cli["fakes"]["spec_store"]
    store.add(SPEC_PATH, an_asset(ASSET_ID, tri_budget=TRI_BUDGET, lods=(4000, 9000)))
    store.add(OTHER_SPEC, an_asset(OTHER_ID, tri_budget=2000, lods=(1000, 8000)))
    _run(cli, "check")


@then("the tool SHALL report structural violations of every specification file found")
def _every_file_is_reported(cli: dict[str, Any]) -> None:
    output = _output(cli)
    assert SPEC_PATH in output
    assert OTHER_SPEC in output
    assert output.count("spec.lods_not_descending") == 2


# --------------------------------------------------------------------------
# Exit codes
# --------------------------------------------------------------------------


@scenario("../features/add-asset-spec-and-validator/canon-cli.feature", "Clean run")
def test_clean_run() -> None: ...


@when("validation produces no error-severity violations")
def _a_clean_validation(cli: dict[str, Any]) -> None:
    _seed(cli, triangles=9000)
    _run(cli, "validate", EXPORT)


@then("the tool SHALL exit with code 0")
def _exits_zero(cli: dict[str, Any]) -> None:
    assert cli["result"].exit_code == CLEAN, _output(cli)


@scenario("../features/add-asset-spec-and-validator/canon-cli.feature", "Violations found")
def test_violations_found() -> None: ...


@when("validation produces at least one error-severity violation")
def _a_failing_validation(cli: dict[str, Any]) -> None:
    _seed(cli, triangles=OVER_BUDGET)
    _run(cli, "validate", EXPORT)


@then("the tool SHALL exit with code 1")
def _exits_one(cli: dict[str, Any]) -> None:
    assert cli["result"].exit_code == VIOLATIONS, _output(cli)


@scenario("../features/add-asset-spec-and-validator/canon-cli.feature", "Operation could not run")
def test_operation_could_not_run() -> None: ...


@when("the requested export file does not exist")
def _a_missing_export(cli: dict[str, Any]) -> None:
    _seed(cli)
    cli["fakes"]["mesh_inspector"].add_unreadable(MISSING, "no such file")
    _run(cli, "validate", MISSING)


@then("the tool SHALL exit with a non-zero code distinct from 1")
def _exits_with_the_could_not_run_code(cli: dict[str, Any]) -> None:
    assert cli["result"].exit_code == COULD_NOT_RUN
    assert cli["result"].exit_code != VIOLATIONS


@then("the message SHALL name the missing file")
def _the_message_names_the_file(cli: dict[str, Any]) -> None:
    assert MISSING in cli["result"].stderr
    assert _output(cli) == ""


# --------------------------------------------------------------------------
# Human and machine output modes
# --------------------------------------------------------------------------


@scenario(
    "../features/add-asset-spec-and-validator/canon-cli.feature",
    "Machine mode output is parseable",
)
def test_machine_mode_output_is_parseable() -> None: ...


@when("the tool is run in machine-readable mode")
def _run_in_machine_mode(cli: dict[str, Any]) -> None:
    _seed(cli, triangles=OVER_BUDGET)
    _run(cli, "validate", "--json", EXPORT)


@then("standard output SHALL contain only the structured result")
def _stdout_is_only_the_document(cli: dict[str, Any]) -> None:
    payload = json.loads(_output(cli))
    (result,) = payload["results"]
    assert [violation["rule_id"] for violation in result["violations"]] == [budgets.TRI_BUDGET]
    assert result["export_format"] == "GLB"
    assert "not_evaluated" in result


@then("any progress or diagnostic text SHALL be written elsewhere")
def _no_prose_on_stdout(cli: dict[str, Any]) -> None:
    assert "FAILING" not in _output(cli)
    assert "violation" not in _output(cli).replace('"violations"', "")


# --------------------------------------------------------------------------
# Asset discovery from a path
# --------------------------------------------------------------------------


@scenario(
    "../features/add-asset-spec-and-validator/canon-cli.feature", "Spec found from an export path"
)
def test_spec_found_from_an_export_path() -> None: ...


@given("`characters/mech_scout/asset.yaml` exists")
def _the_spec_exists(cli: dict[str, Any]) -> None:
    _seed(cli)


@when("the tool validates `characters/mech_scout/exports/SM_MechScout_LOD0.glb`")
def _validate_without_naming_the_spec(cli: dict[str, Any]) -> None:
    _run(cli, "validate", EXPORT)


@then("it SHALL use that specification without the user naming it")
def _the_spec_was_discovered(cli: dict[str, Any]) -> None:
    assert cli["result"].exit_code == CLEAN, _output(cli)
    assert SPEC_PATH in _output(cli)


@scenario("../features/add-asset-spec-and-validator/canon-cli.feature", "No governing spec found")
def test_no_governing_spec_found() -> None: ...


@when("the tool is run against an export with no `asset.yaml` above it")
def _validate_an_ungoverned_export(cli: dict[str, Any]) -> None:
    _seed(cli)
    cli["fakes"]["mesh_inspector"].add(UNGOVERNED, a_glb(100, ("SM_turntable",)))
    _run(cli, "validate", UNGOVERNED)


@then("it SHALL report that no specification was found for the path")
def _no_specification_was_found(cli: dict[str, Any]) -> None:
    assert "no asset.yaml governs" in cli["result"].stderr
    assert UNGOVERNED in cli["result"].stderr


@then("SHALL exit with the code reserved for an operation that could not run")
def _exits_with_the_reserved_code(cli: dict[str, Any]) -> None:
    assert cli["result"].exit_code == COULD_NOT_RUN


# --------------------------------------------------------------------------
# No credentials, no configuration ceremony
# --------------------------------------------------------------------------


@scenario(
    "../features/add-asset-spec-and-validator/canon-cli.feature", "First run on a fresh machine"
)
def test_first_run_on_a_fresh_machine() -> None: ...


@given("a machine where the tool has never been run and no identity is configured")
def _a_fresh_machine(cli: dict[str, Any]) -> None:
    """Nothing is configured because nothing is configurable: there is no such step."""
    _seed(cli)


@when("the user validates an export")
def _validate_on_a_fresh_machine(cli: dict[str, Any]) -> None:
    _run(cli, "validate", EXPORT, env=NO_CREDENTIALS)


@then("the tool SHALL complete the validation")
def _the_validation_completed(cli: dict[str, Any]) -> None:
    assert cli["result"].exit_code == CLEAN, _output(cli)
    assert "rules passed" in _output(cli)


@then("SHALL NOT prompt for or require credentials")
def _nothing_was_asked_for(cli: dict[str, Any]) -> None:
    """Standard input was empty: a prompt would have failed the run, not blocked it."""
    output = _output(cli).lower()
    assert not any(word in output for word in ("login", "token", "password", "credential"))
    assert cli["result"].exception is None


# --------------------------------------------------------------------------
# Usable as a pre-commit hook
# --------------------------------------------------------------------------


@scenario(
    "../features/add-asset-spec-and-validator/canon-cli.feature",
    "Only touched assets are validated",
)
def test_only_touched_assets_are_validated() -> None: ...


@given("a repository containing many assets")
def _many_assets(cli: dict[str, Any]) -> None:
    _seed(cli)
    _seed_second_asset(cli)


@when("the tool is invoked with files belonging to one asset")
def _invoked_with_one_assets_files(cli: dict[str, Any]) -> None:
    _run(cli, "changed", "--json", EXPORT)


@then("it SHALL validate only that asset")
def _only_that_asset_was_validated(cli: dict[str, Any]) -> None:
    payload = json.loads(_output(cli))
    assert payload["assets"] == [SPEC_PATH]
    assert [result["asset"] for result in payload["results"]] == [ASSET_ID]


@scenario("../features/add-asset-spec-and-validator/canon-cli.feature", "Nothing relevant changed")
def test_nothing_relevant_changed() -> None: ...


@when("the tool is invoked with files that belong to no asset")
def _invoked_with_unrelated_files(cli: dict[str, Any]) -> None:
    _seed(cli)
    _run(cli, "changed", UNRELATED)


@then("it SHALL exit with code 0 without reporting violations")
def _exits_zero_with_nothing_to_say(cli: dict[str, Any]) -> None:
    assert cli["result"].exit_code == CLEAN
    assert "violation" not in _output(cli)


# --------------------------------------------------------------------------
# Violation messages state the fix
# --------------------------------------------------------------------------


@scenario("../features/add-asset-spec-and-validator/canon-cli.feature", "Actionable message")
def test_actionable_message() -> None: ...


@when("a triangle budget violation is printed")
def _a_printed_budget_violation(cli: dict[str, Any]) -> None:
    _seed(cli, triangles=OVER_BUDGET)
    _run(cli, "validate", EXPORT)


@then(
    "the message SHALL name the asset, the observed triangle count and the allowed triangle count"
)
def _the_message_states_the_fix(cli: dict[str, Any]) -> None:
    (line,) = [line for line in _output(cli).splitlines() if budgets.TRI_BUDGET in line]
    assert f"asset {ASSET_ID}" in line
    assert f"observed {OVER_BUDGET}" in line
    assert f"expected {TRI_BUDGET}" in line
