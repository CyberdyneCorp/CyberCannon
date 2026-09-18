"""Tasks 2.1-2.5 — the spec-to-feature generator.

The spec deltas are the source of the test suite, so the generator has exactly
three obligations: lose nothing, produce the same bytes every time, and refuse
loudly rather than skip a file it cannot read. A skipped spec is an untested
requirement that looks tested.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

import pytest
from pytest_bdd.parser import FeatureParser
from spec_repo import ONE_REQUIREMENT, SpecRepo

from canon_bdd import generator, gherkin
from canon_bdd.specs import CapabilitySpec, SpecParseError, load, load_all

SCENARIO_HEADING = re.compile(r"^#### Scenario:", re.MULTILINE)
GENERATOR = Path("scripts/gen_features.py")

MALFORMED = {
    "a bullet that is not a step": """\
### Requirement: A requirement

#### Scenario: A scenario
- **GIVEN** a thing
- a bare bullet nobody can execute
- **THEN** it SHALL be done
""",
    "an unknown step keyword": """\
### Requirement: A requirement

#### Scenario: A scenario
- **SUPPOSE** a thing
- **THEN** it SHALL be done
""",
    "prose where steps belong": """\
### Requirement: A requirement

#### Scenario: A scenario
This scenario forgot to be a scenario.
""",
    "a scenario with no steps at all": """\
### Requirement: A requirement

#### Scenario: A scenario

### Requirement: Another requirement

#### Scenario: Another scenario
- **WHEN** it runs
- **THEN** it SHALL be done
""",
    "a duplicate scenario name": """\
### Requirement: A requirement

#### Scenario: A scenario
- **WHEN** it runs
- **THEN** it SHALL be done

### Requirement: Another requirement

#### Scenario: A scenario
- **WHEN** it runs
- **THEN** it SHALL be done
""",
}


# --------------------------------------------------------------------------
# 2.1 — the real corpus generates without loss
# --------------------------------------------------------------------------


@pytest.fixture(scope="module")
def specs(repo_root: Path) -> tuple[CapabilitySpec, ...]:
    return generator.load_specs(repo_root)


def test_every_spec_delta_is_read(repo_root: Path, specs: tuple[CapabilitySpec, ...]) -> None:
    found = sorted((repo_root / "openspec").glob("changes/*/specs/*/spec.md"))
    assert [spec.path for spec in specs] == [path.relative_to(repo_root) for path in found]


def test_no_scenario_is_lost(repo_root: Path, specs: tuple[CapabilitySpec, ...]) -> None:
    """Every `#### Scenario:` in the corpus reaches a generated feature."""
    written = sum(len(spec.scenarios) for spec in specs)
    declared = sum(
        len(SCENARIO_HEADING.findall((repo_root / spec.path).read_text(encoding="utf-8")))
        for spec in specs
    )
    assert written == declared


def test_generated_gherkin_preserves_names_and_steps_verbatim(
    repo_root: Path, specs: tuple[CapabilitySpec, ...]
) -> None:
    """Parsed back with pytest-bdd, a feature says exactly what its spec says."""
    for spec in specs:
        feature = FeatureParser(str(repo_root), spec.feature_path.as_posix()).parse()
        assert _from_feature(feature) == _from_spec(spec), spec.path


def test_every_feature_carries_its_change_capability_and_spec_path(
    repo_root: Path, specs: tuple[CapabilitySpec, ...]
) -> None:
    """D5 — a failing scenario says which capability and which spec file it came from."""
    for spec in specs:
        feature = FeatureParser(str(repo_root), spec.feature_path.as_posix()).parse()
        assert feature.tags == set(gherkin.tags(spec))
        assert f"spec:{spec.path.as_posix()}" in feature.tags


def _from_spec(spec: CapabilitySpec) -> set[tuple[str, str, tuple[tuple[str, str], ...]]]:
    return {
        (
            requirement.name,
            scenario.name,
            tuple((step.keyword, step.text) for step in scenario.steps),
        )
        for requirement, scenario in spec.scenarios
    }


def _from_feature(feature: object) -> set[tuple[str, str, tuple[tuple[str, str], ...]]]:
    return {
        (
            scenario.rule.name if scenario.rule else "",
            name,
            tuple((step.keyword.upper(), step.name) for step in scenario.steps),
        )
        for name, scenario in feature.scenarios.items()  # type: ignore[attr-defined]
    }


# --------------------------------------------------------------------------
# 2.3 — deterministic and idempotent
# --------------------------------------------------------------------------


def test_generation_is_idempotent(spec_repo: SpecRepo) -> None:
    spec_repo.add("add-thing", "thing-capability")
    generator.write(spec_repo.root)
    once = spec_repo.feature("add-thing", "thing-capability").read_bytes()
    generator.write(spec_repo.root)
    assert spec_repo.feature("add-thing", "thing-capability").read_bytes() == once


def test_generation_is_deterministic_for_the_whole_corpus(repo_root: Path) -> None:
    assert generator.generate(repo_root) == generator.generate(repo_root)


def test_generation_removes_a_feature_whose_spec_is_gone(spec_repo: SpecRepo) -> None:
    spec = spec_repo.add("add-thing", "thing-capability")
    generator.write(spec_repo.root)
    spec.unlink()
    spec_repo.add("add-thing", "other-capability")
    generator.write(spec_repo.root)
    assert not spec_repo.feature("add-thing", "thing-capability").exists()
    assert spec_repo.feature("add-thing", "other-capability").exists()


# --------------------------------------------------------------------------
# 2.4 — a spec that cannot be parsed fails loudly, naming the file
# --------------------------------------------------------------------------


@pytest.mark.parametrize("description", sorted(MALFORMED))
def test_a_malformed_spec_names_its_file_and_line(spec_repo: SpecRepo, description: str) -> None:
    path = spec_repo.add("add-thing", "thing-capability", MALFORMED[description])
    with pytest.raises(SpecParseError) as raised:
        load(path, spec_repo.root)
    assert str(path) in str(raised.value)
    assert raised.value.line > 0


def test_a_malformed_spec_stops_the_whole_run(spec_repo: SpecRepo) -> None:
    """One bad file fails the run; the good ones are not quietly generated instead."""
    spec_repo.add("add-thing", "good-capability")
    spec_repo.add("add-thing", "bad-capability", MALFORMED["prose where steps belong"])
    with pytest.raises(SpecParseError):
        load_all(spec_repo.root / "openspec", spec_repo.root)
    assert not spec_repo.feature("add-thing", "good-capability").exists()


def test_a_spec_with_no_requirements_is_an_error(spec_repo: SpecRepo) -> None:
    path = spec_repo.add("add-thing", "thing-capability", "Nothing but prose.\n")
    with pytest.raises(SpecParseError, match="no '### Requirement:' heading"):
        load(path, spec_repo.root)


def test_the_cli_exits_two_and_names_the_file(spec_repo: SpecRepo, repo_root: Path) -> None:
    path = spec_repo.add("add-thing", "thing-capability", MALFORMED["an unknown step keyword"])
    result = _run_generator(repo_root, spec_repo, [])
    assert result.returncode == 2, result.stdout
    assert str(path) in result.stderr


# --------------------------------------------------------------------------
# 2.5 — the committed features are regenerated and compared (D1)
# --------------------------------------------------------------------------


def test_the_committed_features_match_the_spec_deltas(repo_root: Path) -> None:
    differences = generator.check(repo_root)
    assert not differences, "run `just gen-features`:\n" + "\n".join(
        f"  {difference}" for difference in differences
    )


def test_a_hand_edited_feature_fails_the_check(spec_repo: SpecRepo, repo_root: Path) -> None:
    spec_repo.add("add-thing", "thing-capability")
    generator.write(spec_repo.root)
    feature = spec_repo.feature("add-thing", "thing-capability")
    feature.write_text(feature.read_text(encoding="utf-8").replace("a thing", "a rewritten thing"))

    differences = generator.check(spec_repo.root)
    assert [difference.path for difference in differences] == [feature.relative_to(spec_repo.root)]
    assert "gen-features" in differences[0].reason

    result = _run_generator(repo_root, spec_repo, ["--check"])
    assert result.returncode == 1
    assert "thing-capability.feature" in result.stderr


def test_a_missing_feature_fails_the_check(spec_repo: SpecRepo) -> None:
    spec_repo.add("add-thing", "thing-capability")
    differences = generator.check(spec_repo.root)
    assert [difference.reason for difference in differences] == ["missing; run `just gen-features`"]


def test_a_feature_no_spec_generates_fails_the_check(spec_repo: SpecRepo) -> None:
    spec_repo.add("add-thing", "thing-capability")
    generator.write(spec_repo.root)
    orphan = spec_repo.feature("add-thing", "orphan-capability")
    orphan.write_text("Feature: orphan\n", encoding="utf-8")
    assert [difference.path for difference in generator.check(spec_repo.root)] == [
        orphan.relative_to(spec_repo.root)
    ]


def test_the_cli_reports_a_clean_tree(repo_root: Path) -> None:
    result = subprocess.run(
        [sys.executable, str(repo_root / GENERATOR), "--check"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "matches the spec deltas" in result.stdout


# --------------------------------------------------------------------------
# The pending-list bootstrap is a one-time operation, never a `just` recipe
# --------------------------------------------------------------------------


def test_bootstrapping_the_pending_list_lists_every_unimplemented_scenario(
    spec_repo: SpecRepo, repo_root: Path
) -> None:
    spec_repo.add("add-thing", "thing-capability", ONE_REQUIREMENT)
    result = _run_generator(repo_root, spec_repo, ["--bootstrap-pending"])
    assert result.returncode == 0, result.stderr
    listed = (spec_repo.root / "tests" / "bdd" / "pending.txt").read_text(encoding="utf-8")
    assert "thing-capability :: It does the thing" in listed


def _run_generator(
    repo_root: Path, spec_repo: SpecRepo, arguments: list[str]
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            str(repo_root / GENERATOR),
            "--repo-root",
            str(spec_repo.root),
            *arguments,
        ],
        capture_output=True,
        text=True,
        check=False,
    )
