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

from dataclasses import dataclass, replace

import pytest

from cybercanon.application.ports.spec_store import (
    HistoryUnavailable,
    ProjectConfig,
    SpecNotFound,
    SpecStore,
)
from cybercanon.domain.annotations import (
    Anchor2D,
    Annotation,
    AnnotationKind,
    AnnotationState,
)
from cybercanon.domain.asset import Asset, AssetId
from cybercanon.domain.constraints import AnimationDefaults, Constraints
from cybercanon.domain.design import Design, Socket
from cybercanon.domain.revisions import ContentHash
from cybercanon.domain.status import Status
from cybercanon.domain.triage import PromotionTarget, promote
from cybercanon.domain.violations import Severity, SpecViolation

A_PIN = Annotation(
    id="an_contract_1",
    author="rafa",
    kind=AnnotationKind.ART_DIRECTION,
    text="the pauldron reads as a backpack at 15 m",
    target=Anchor2D(view="front", u=0.25, v=0.4),
)
"""One annotation the editing contract writes, reads back and promotes."""


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

    # -- revision pinning (D3) -------------------------------------------

    def test_a_store_says_what_revision_it_reads_at(self, implementation: SpecStore) -> None:
        """A string or nothing — never a guess, and never a failure."""
        revision = implementation.current_revision()

        assert revision is None or isinstance(revision, str)

    def test_pinning_to_an_unreachable_revision_is_refused(self, implementation: SpecStore) -> None:
        """One failure at the point somebody chose the revision, not six later."""
        with pytest.raises(HistoryUnavailable):
            implementation.pinned("no-such-revision")

    # -- editing (add-model-sheet-2d, task 2.1) --------------------------

    def test_a_document_carries_the_bytes_and_the_meaning(self, implementation: SpecStore) -> None:
        """Both halves of a write path: what the file says, and what it *is*."""
        document = implementation.read_document(MECH_SCOUT.path)

        assert document.path == MECH_SCOUT.path
        assert document.asset.id.value == "mech_scout"
        assert document.content

    def test_a_documents_precondition_is_the_digest_of_its_own_bytes(
        self, implementation: SpecStore
    ) -> None:
        """D5: the precondition is per file and by content, never the branch tip."""
        document = implementation.read_document(MECH_SCOUT.path)

        assert document.based_on == ContentHash.of(document.content)

    def test_reading_a_document_twice_yields_the_same_bytes(
        self, implementation: SpecStore
    ) -> None:
        """A precondition that changed between two reads would refuse every edit."""
        first = implementation.read_document(MECH_SCOUT.path)
        second = implementation.read_document(MECH_SCOUT.path)

        assert first.content == second.content

    def test_a_missing_document_is_reported_not_invented(self, implementation: SpecStore) -> None:
        with pytest.raises(SpecNotFound):
            implementation.read_document(UNKNOWN_SPEC)

    def test_an_edit_reads_back_as_what_was_written(self, implementation: SpecStore) -> None:
        """The round trip the whole annotation write path rests on."""
        document = implementation.read_document(MECH_SCOUT.path)
        edited = replace(document.asset, annotations=(A_PIN,))

        written = implementation.parse_document(
            MECH_SCOUT.path, implementation.edited(document, edited)
        )

        assert written.asset.annotations == (A_PIN,)

    def test_an_edit_leaves_the_rest_of_the_specification_alone(
        self, implementation: SpecStore
    ) -> None:
        """Adding an annotation is not licence to rewrite what engineering declared."""
        document = implementation.read_document(MECH_SCOUT.path)
        edited = replace(document.asset, annotations=(A_PIN,))

        written = implementation.parse_document(
            MECH_SCOUT.path, implementation.edited(document, edited)
        )

        assert written.asset.name == document.asset.name
        assert written.asset.status is document.asset.status
        assert written.asset.constraints == document.asset.constraints

    def test_rendering_an_edit_does_not_change_the_stored_specification(
        self, implementation: SpecStore
    ) -> None:
        """A composed write that never lands leaves nothing half-done."""
        document = implementation.read_document(MECH_SCOUT.path)

        implementation.edited(document, replace(document.asset, annotations=(A_PIN,)))

        assert implementation.read_document(MECH_SCOUT.path).content == document.content
        assert implementation.load(MECH_SCOUT.path).asset.annotations == ()

    def test_a_promoted_rule_reads_back_from_the_document(self, implementation: SpecStore) -> None:
        """The other destination: a durable rule, written where a reader finds it."""
        document = implementation.read_document(MECH_SCOUT.path)
        promoted = promote(
            replace(document.asset, annotations=(A_PIN,)),
            A_PIN.id,
            "the lens glow is always emissive",
            PromotionTarget.SILHOUETTE_RULES,
        )

        written = implementation.parse_document(
            MECH_SCOUT.path, implementation.edited(document, promoted.asset)
        )

        assert written.asset.concept is not None
        assert "the lens glow is always emissive" in written.asset.concept.silhouette_rules
        assert written.asset.annotations[0].state is AnnotationState.PROMOTED
