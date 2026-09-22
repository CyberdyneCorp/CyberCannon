"""What every `ViewIndex` SHALL do, whoever implements it (task 3.4, D3).

D3 splits the mirror in two: the bytes live in blob storage under their content
hash, and *what that hash is* — which asset, which slot, which revision — is a
row here. The contract is therefore about the mapping and about nothing else:

* an unknown digest answers **nothing**, never a guess, because every read that
  cannot find a mapping falls back to the repository and a fabricated row would
  send it somewhere else;
* recording the same row twice is **the same fact**, which is what makes
  *"re-running the mirror is a no-op"* true one layer up;
* rows are **scoped to a project**, so two deployments sharing a database never
  answer each other's questions;
* forgetting a project **drops its rows and nobody else's** — the rebuild's
  first step.
"""

from __future__ import annotations

from cybercanon.application.ports.view_index import ViewIndex, ViewRow
from cybercanon.domain.revisions import ContentHash

PROJECT = "cyberdyne-game"
OTHER_PROJECT = "cyberdyne-art"

SCOUT = "mech_scout"
MULE = "mule"

DIGEST = ContentHash.of(b"the front view")
OTHER_DIGEST = ContentHash.of(b"the side view")


def a_row(
    digest: ContentHash = DIGEST,
    slot: str = "front",
    asset_id: str = SCOUT,
    project: str = PROJECT,
    revision: str = "rev-0001",
) -> ViewRow:
    return ViewRow(
        project=project,
        asset_id=asset_id,
        slot=slot,
        revision=revision,
        path=f"characters/{asset_id}/concept/{slot}.png",
        digest=digest,
        byte_size=1234,
    )


class ViewIndexContract:
    """The behaviour every view index shares."""

    def test_an_unknown_digest_is_answered_with_nothing(self, implementation: ViewIndex) -> None:
        assert implementation.row_for(PROJECT, DIGEST) is None

    def test_a_recorded_digest_names_its_asset_slot_and_revision(
        self, implementation: ViewIndex
    ) -> None:
        implementation.record(a_row())

        found = implementation.row_for(PROJECT, DIGEST)

        assert found is not None
        assert (found.asset_id, found.slot, found.revision) == (SCOUT, "front", "rev-0001")
        assert found.path.endswith("concept/front.png")

    def test_recording_the_same_row_twice_is_the_same_fact(self, implementation: ViewIndex) -> None:
        """*"Re-running it is a no-op"* is only true if the write is idempotent."""
        implementation.record(a_row())
        implementation.record(a_row())

        assert len(implementation.rows_for(PROJECT, SCOUT)) == 1

    def test_a_later_revision_of_the_same_digest_replaces_what_it_was(
        self, implementation: ViewIndex
    ) -> None:
        implementation.record(a_row(revision="rev-0001"))
        implementation.record(a_row(revision="rev-0002"))

        found = implementation.row_for(PROJECT, DIGEST)

        assert found is not None
        assert found.revision == "rev-0002"

    def test_rows_are_listed_for_one_asset_in_a_deterministic_order(
        self, implementation: ViewIndex
    ) -> None:
        implementation.record(a_row(OTHER_DIGEST, slot="side"))
        implementation.record(a_row(DIGEST, slot="front"))
        implementation.record(a_row(ContentHash.of(b"the mule"), asset_id=MULE))

        listed = implementation.rows_for(PROJECT, SCOUT)

        assert [row.slot for row in listed] == ["front", "side"]

    def test_a_projects_rows_are_invisible_to_another_project(
        self, implementation: ViewIndex
    ) -> None:
        implementation.record(a_row(project=OTHER_PROJECT))

        assert implementation.row_for(PROJECT, DIGEST) is None
        assert implementation.rows_for(PROJECT, SCOUT) == ()

    def test_forgetting_a_project_drops_its_rows_and_nobody_elses(
        self, implementation: ViewIndex
    ) -> None:
        implementation.record(a_row())
        implementation.record(a_row(project=OTHER_PROJECT))

        implementation.forget_project(PROJECT)

        assert implementation.rows_for(PROJECT, SCOUT) == ()
        assert implementation.row_for(OTHER_PROJECT, DIGEST) is not None
