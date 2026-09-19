"""Task 4.5 — linting the specification files themselves.

The findings a person acts on need two things the domain check cannot supply on
its own: the **file** the violation is in, and — for the one check that spans
files — every file involved. That is what this use case adds, and it is all it
adds: the rules stay pure domain functions.
"""

from __future__ import annotations

from cybercanon.application.ports.spec_store import ProjectConfig
from cybercanon.application.testing.outcomes import ran
from cybercanon.application.testing.spec_store import InMemorySpecStore
from cybercanon.application.use_cases.lint_spec import lint_project, lint_specs
from cybercanon.domain import spec_checks
from cybercanon.domain.asset import Asset, AssetId
from cybercanon.domain.constraints import AnimationDefaults, Constraints
from cybercanon.domain.design import Design, State
from cybercanon.domain.violations import Severity, SpecViolation

SCOUT = "characters/mech_scout/asset.yaml"
MULE = "vehicles/mule/asset.yaml"
CONVENTION = "A_{asset}_{state}"


def an_asset(asset_id: str = "mech_scout", **blocks: object) -> Asset:
    return Asset(id=AssetId(asset_id), name="Scout Mech", **blocks)  # type: ignore[arg-type]


def a_store(*specs: tuple[str, Asset], project: ProjectConfig | None = None) -> InMemorySpecStore:
    store = InMemorySpecStore()
    for path, asset in specs:
        store.add(path, asset)
    if project is not None:
        store.set_project(project)
    return store


def test_a_clean_specification_passes_with_no_findings() -> None:
    store = a_store(
        (SCOUT, an_asset(constraints=Constraints(tri_budget=12000, lods=(12000, 4000))))
    )

    report = ran(lint_specs([SCOUT], spec_store=store))

    assert report.findings == ()
    assert report.checked == (SCOUT,)
    assert report.passed


def test_a_state_that_constrains_nothing_names_the_file_and_the_state() -> None:
    """D12 — `states: [walk]` looked like a specification and enforced nothing."""
    store = a_store((SCOUT, an_asset(design=Design(states=(State(name="walk"),)))))

    (finding,) = ran(lint_specs([SCOUT], spec_store=store)).findings

    assert finding.path == SCOUT
    assert finding.rule_id == spec_checks.RULE_STATE_CONSTRAINS_NOTHING
    assert finding.subject == "design.states[walk]"
    assert "animated: false" in finding.violation.expected


def test_a_project_clip_naming_convention_makes_the_same_state_checkable() -> None:
    store = a_store(
        (SCOUT, an_asset(design=Design(states=(State(name="walk"),)))),
        project=ProjectConfig(
            defaults=Constraints(animation=AnimationDefaults(clip_naming=CONVENTION))
        ),
    )

    assert ran(lint_specs([SCOUT], spec_store=store)).findings == ()


def test_an_unanimated_state_is_checkable_on_its_own() -> None:
    store = a_store(
        (SCOUT, an_asset(design=Design(states=(State(name="destroyed", animated=False),))))
    )

    assert ran(lint_specs([SCOUT], spec_store=store)).passed


def test_ascending_lods_are_reported_against_the_field_that_declares_them() -> None:
    store = a_store((SCOUT, an_asset(constraints=Constraints(lods=(4000, 12000)))))

    (finding,) = ran(lint_specs([SCOUT], spec_store=store)).findings_of(
        spec_checks.RULE_LODS_NOT_DESCENDING
    )

    assert finding.path == SCOUT
    assert finding.subject == "constraints.lods"
    assert finding.is_error


def test_a_first_lod_above_the_triangle_budget_is_reported() -> None:
    store = a_store(
        (SCOUT, an_asset(constraints=Constraints(tri_budget=12000, lods=(14000, 4000))))
    )

    (finding,) = ran(lint_specs([SCOUT], spec_store=store)).findings_of(
        spec_checks.RULE_LOD0_OVER_TRI_BUDGET
    )

    assert finding.subject == "constraints.lods[0]"


def test_a_duplicate_id_is_reported_against_every_file_that_declares_it() -> None:
    """The one check no single file can answer — so it is reported in both."""
    store = a_store(
        (SCOUT, an_asset("mech_scout")),
        (
            MULE,
            an_asset(
                "mech_scout",
            ),
        ),
    )

    findings = ran(lint_specs([SCOUT, MULE], spec_store=store)).findings_of(
        spec_checks.RULE_DUPLICATE_ID
    )

    assert tuple(finding.path for finding in findings) == (SCOUT, MULE)
    assert all(SCOUT in finding.violation.message for finding in findings)
    assert all(MULE in finding.violation.message for finding in findings)


def test_distinct_ids_produce_no_duplicate_finding() -> None:
    store = a_store((SCOUT, an_asset("mech_scout")), (MULE, an_asset("mule")))

    assert ran(lint_specs([SCOUT, MULE], spec_store=store)).findings == ()


def test_a_loading_warning_is_a_finding_with_its_field_location() -> None:
    """D5 — an unrecognised field is reported here, and never blocks a commit."""
    store = InMemorySpecStore()
    store.add(
        SCOUT,
        an_asset(),
        warnings=(
            SpecViolation(
                rule_id="spec.unknown_field",
                severity=Severity.WARNING,
                subject="constraints.shinyness",
                message="unrecognised field 'shinyness' at constraints.shinyness",
            ),
        ),
    )

    report = ran(lint_specs([SCOUT], spec_store=store))

    (finding,) = report.warnings
    assert finding.path == SCOUT
    assert finding.subject == "constraints.shinyness"
    assert report.passed


def test_linting_a_project_covers_every_specification_under_it() -> None:
    store = a_store(
        (SCOUT, an_asset("mech_scout", design=Design(states=(State(name="walk"),)))),
        (MULE, an_asset("mule")),
    )

    report = ran(lint_project("", spec_store=store))

    assert report.checked == (SCOUT, MULE)
    assert len(report.findings) == 1
    assert report.findings_in(MULE) == ()
