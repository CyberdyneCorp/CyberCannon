"""What every `SpecStore` SHALL do, whoever implements it (task 4.1).

The contract is a plain class of test methods plus the corpus every
implementation is seeded with. `test_spec_store.py` runs it against the
in-memory fake today; `GitSpecStore` joins by adding one factory that writes
this same corpus into a working copy (task 5.1), and any divergence between the
two — discovery that stops in a different place, a missing file that reads as
empty — fails the build instead of the product.

Paths in the corpus are repository-relative POSIX strings, which is the port's
contract: a store hands back paths that read the same on every machine.
"""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from cybercanon.application.ports.spec_store import ProjectConfig, SpecNotFound, SpecStore
from cybercanon.domain.asset import Asset, AssetId
from cybercanon.domain.constraints import AnimationDefaults, Constraints
from cybercanon.domain.design import Design, Socket
from cybercanon.domain.status import Status
from cybercanon.domain.violations import Severity, SpecViolation


@dataclass(frozen=True)
class SpecFixture:
    """One specification the corpus expects to find at `path`."""

    path: str
    asset: Asset
    warnings: tuple[SpecViolation, ...] = ()


MECH_SCOUT = SpecFixture(
    path="characters/mech_scout/asset.yaml",
    asset=Asset(
        id=AssetId("mech_scout"),
        name="Scout Mech",
        status=Status.MODELING,
        design=Design(sockets=(Socket(name="SOCKET_muzzle_l", purpose="muzzle flash"),)),
        constraints=Constraints(tri_budget=12000, naming="SM_{asset}_LOD{n}"),
    ),
)

MULE = SpecFixture(
    path="vehicles/mule/asset.yaml",
    asset=Asset(id=AssetId("mule"), name="Mule Hauler", status=Status.CONCEPT),
)

WITH_UNKNOWN_FIELD = SpecFixture(
    path="props/crate/asset.yaml",
    asset=Asset(id=AssetId("crate"), name="Supply Crate"),
    warnings=(
        SpecViolation(
            rule_id="spec.unknown_field",
            severity=Severity.WARNING,
            subject="constraints.shinyness",
            message="unrecognised field 'shinyness' at constraints.shinyness",
        ),
    ),
)

CORPUS = (MECH_SCOUT, MULE, WITH_UNKNOWN_FIELD)

PROJECT = ProjectConfig(
    name="Ironwood",
    defaults=Constraints(
        up_axis="Z",
        unit_scale=1.0,
        animation=AnimationDefaults(frame_rate=30.0, clip_naming="A_{asset}_{state}"),
    ),
    golden_rules=("The silhouette reads at 25 m.",),
)

EXPORT = "characters/mech_scout/exports/SM_mech_scout_LOD0.glb"
"""A path inside an asset, several levels below its specification."""

ORPHAN = "docs/pipeline.md"
"""A path belonging to no asset — the pre-commit hook's ordinary case."""

UNKNOWN_SPEC = "characters/nobody/asset.yaml"


class SpecStoreContract:
    """The behaviour every specification store shares."""

    # -- discovery (D9) --------------------------------------------------

    def test_an_export_path_discovers_its_governing_spec(self, implementation: SpecStore) -> None:
        assert implementation.discover(EXPORT) == MECH_SCOUT.path

    def test_discovery_from_the_asset_directory_finds_the_same_spec(
        self, implementation: SpecStore
    ) -> None:
        assert implementation.discover("characters/mech_scout") == MECH_SCOUT.path

    def test_discovery_from_the_spec_itself_finds_the_spec(self, implementation: SpecStore) -> None:
        assert implementation.discover(MECH_SCOUT.path) == MECH_SCOUT.path

    def test_a_path_belonging_to_no_asset_discovers_nothing(
        self, implementation: SpecStore
    ) -> None:
        """An answer, not an error: most touched files belong to no asset."""
        assert implementation.discover(ORPHAN) is None

    def test_discovery_stops_at_the_nearest_spec(self, implementation: SpecStore) -> None:
        assert implementation.discover("vehicles/mule/exports/mule.glb") == MULE.path

    # -- loading ---------------------------------------------------------

    def test_a_spec_loads_as_its_declared_asset(self, implementation: SpecStore) -> None:
        loaded = implementation.load(MECH_SCOUT.path)

        assert loaded.path == MECH_SCOUT.path
        assert loaded.asset.id.value == "mech_scout"
        assert loaded.asset.name == "Scout Mech"

    def test_authored_constraints_survive_the_load(self, implementation: SpecStore) -> None:
        constraints = implementation.load(MECH_SCOUT.path).asset.constraints

        assert constraints is not None
        assert constraints.tri_budget == 12000

    def test_an_unknown_spec_path_is_reported_not_invented(self, implementation: SpecStore) -> None:
        with pytest.raises(SpecNotFound):
            implementation.load(UNKNOWN_SPEC)

    def test_an_unrecognised_field_is_a_warning_and_the_asset_still_loads(
        self, implementation: SpecStore
    ) -> None:
        """D5 — version skew must never be fatal, and never silent either."""
        loaded = implementation.load(WITH_UNKNOWN_FIELD.path)

        assert loaded.asset.id.value == "crate"
        assert loaded.warnings
        assert all(warning.severity is Severity.WARNING for warning in loaded.warnings)

    # -- project configuration (D3) --------------------------------------

    def test_the_project_defaults_are_readable(self, implementation: SpecStore) -> None:
        defaults = implementation.load_project(MECH_SCOUT.path).defaults

        assert defaults is not None
        assert defaults.up_axis == "Z"
        assert defaults.unit_scale == 1.0

    def test_the_project_is_the_same_from_anywhere_inside_it(
        self, implementation: SpecStore
    ) -> None:
        assert implementation.load_project(EXPORT) == implementation.load_project(MULE.path)

    # -- enumeration -----------------------------------------------------

    def test_every_spec_is_enumerable_in_a_deterministic_order(
        self, implementation: SpecStore
    ) -> None:
        found = implementation.specs_under("")

        assert found == tuple(sorted(fixture.path for fixture in CORPUS))

    def test_enumeration_is_bounded_by_the_path_it_starts_at(
        self, implementation: SpecStore
    ) -> None:
        assert implementation.specs_under("characters") == (MECH_SCOUT.path,)
