"""The worked example, with its art attached, actually satisfies its own contract.

`examples/ronin` is source only — `asset.yaml`, `art-spec.md`, a project file —
because nothing binary lives in this repository's history. That is the right
trade for review and it leaves the example unable to demonstrate the thing the
product is for: the first hosted deployment served it and correctly reported an
asset with no export, no triangles, no clips and no mirrored concept views.

`scripts/seed_game_repo.py` writes the example's sources and generates the
binaries beside them, into a game repository. This asserts the claim that makes
that worth doing: the generated content is not decorative, it **satisfies the
specification the example states**. A fixture that merely produced a file would
let the contract and the content drift apart, which is the failure the whole
product exists to prevent -- here, in its own example.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from canon_fixtures.seed import EXPORT, VIEWS, seed
from cybercanon.adapters.wiring.build import build_container
from cybercanon.application.testing.outcomes import ran

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def seeded(tmp_path_factory: pytest.TempPathFactory) -> Path:
    root = tmp_path_factory.mktemp("game-repo")
    seed(root)
    return root


def test_the_seeded_export_satisfies_the_example_s_specification(seeded: Path) -> None:
    """Fifteen rules, no violations — the contract and the content agree.

    Not "a file was written". The socket the design block declares is in the
    export, both states resolve to clips that are present, and the triangle
    count is inside the budget engineering wrote down.
    """
    report = ran(build_container(str(seeded)).validate_export(EXPORT)).report

    assert report.passed, [violation.rule_id for violation in report.violations]
    assert report.not_evaluated == ()
    assert len(report.passed_rules) == 15


def test_every_concept_view_the_specification_names_is_present(seeded: Path) -> None:
    """A view the spec names and the repository lacks is a blank box in the sheet.

    That is what the deployment showed: "no image is mirrored for this view
    yet", twice, because the files the `concept.views` list names were not
    there to mirror.
    """
    for path, _ in VIEWS:
        assert (seeded / path).is_file(), path
        assert (seeded / path).stat().st_size > 0


def test_the_seeder_refuses_to_write_binaries_into_this_repository() -> None:
    """The rule the script exists to respect, asserted rather than trusted."""
    from canon_fixtures.seed import main

    assert main(["seed", str(Path(__file__).resolve().parent)]) == 2
