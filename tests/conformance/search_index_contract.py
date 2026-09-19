"""What every `SearchIndex` SHALL do, whoever implements it (task 2.5).

The corpus is four assets chosen so that the ranking cascade is *observable*:
`mech_scout` has the exact identifier a search for `mech_scout` wants, and
`mech_hauler` mentions "mech" only in its description, so a cascade that ranked
by anything but the fixed order would put them the wrong way round. The alias
`drone` and the tag `vehicle` each belong to exactly one asset, so a pass that
silently matched on the wrong field would be visible too.

Two properties matter more than any single assertion, and both are here:
**determinism**, because a search whose order moves between runs cannot be
reasoned about; and **disposability**, because the specification says deleting
the index loses nothing — so the contract deletes it, rebuilds it and asserts
every answer is identical.
"""

from __future__ import annotations

from cybercanon.application.ports.search_index import (
    FileFingerprint,
    IndexedAsset,
    MatchKind,
    SearchIndex,
)

PROJECT = "ironwood"
OTHER_PROJECT = "sidequest"

MECH_SCOUT = IndexedAsset(
    asset_id="mech_scout",
    name="Scout Mech",
    project=PROJECT,
    status="modeling",
    aliases=("drone", "scout"),
    tags=("character", "robot"),
    description="A light reconnaissance walker.",
    spec_path="characters/mech_scout/asset.yaml",
    directory="characters/mech_scout",
    source_file="characters/mech_scout/mech_scout.blend",
    engine_path="/Game/Characters/MechScout",
    owner_art="rafa@cyberdyne.com",
    owner_design="ana@cyberdyne.com",
    owner_code="zoe@cyberdyne.com",
    validated_export="characters/mech_scout/exports/SM_mech_scout_LOD0.glb",
    validated_at="2026-09-01",
    fingerprint=FileFingerprint(path="characters/mech_scout/asset.yaml", size=812, mtime_ns=1),
)

MULE = IndexedAsset(
    asset_id="mule",
    name="Mule Hauler",
    project=PROJECT,
    status="concept",
    tags=("vehicle",),
    description="A six-wheeled supply mech carrier.",
    spec_path="vehicles/mule/asset.yaml",
    directory="vehicles/mule",
    owner_art="rafa@cyberdyne.com",
    fingerprint=FileFingerprint(path="vehicles/mule/asset.yaml", size=210, mtime_ns=2),
)

CRATE = IndexedAsset(
    asset_id="crate",
    name="Supply Crate",
    project=PROJECT,
    status="modeling",
    tags=("prop",),
    description="A stackable container.",
    spec_path="props/crate/asset.yaml",
    directory="props/crate",
    owner_art="ana@cyberdyne.com",
    fingerprint=FileFingerprint(path="props/crate/asset.yaml", size=180, mtime_ns=3),
)

ELSEWHERE = IndexedAsset(
    asset_id="banner",
    name="Guild Banner",
    project=OTHER_PROJECT,
    status="modeling",
    tags=("prop",),
    description="Belongs to another project entirely.",
    spec_path="props/banner/asset.yaml",
    directory="props/banner",
    owner_art="rafa@cyberdyne.com",
    fingerprint=FileFingerprint(path="props/banner/asset.yaml", size=150, mtime_ns=4),
)

CORPUS = (MECH_SCOUT, MULE, CRATE, ELSEWHERE)

MISSING_TERM = "hovercraft"


def seed(index: SearchIndex) -> SearchIndex:
    """Write the corpus. Shared by every implementation's factory."""
    for entry in CORPUS:
        index.upsert(entry)
    return index


class SearchIndexContract:
    """The behaviour every search index shares."""

    # -- lookup ----------------------------------------------------------

    def test_an_asset_is_found_by_identifier(self, implementation: SearchIndex) -> None:
        found = implementation.get("mech_scout")

        assert found is not None
        assert found.name == "Scout Mech"

    def test_an_unknown_identifier_is_absent_not_invented(
        self, implementation: SearchIndex
    ) -> None:
        assert implementation.get("nobody") is None

    def test_an_upsert_replaces_the_row_for_that_identifier(
        self, implementation: SearchIndex
    ) -> None:
        """One row per asset: the index is derived, so there is nothing to merge."""
        from dataclasses import replace

        implementation.upsert(replace(MECH_SCOUT, status="review"))

        found = implementation.get("mech_scout")
        assert found is not None
        assert found.status == "review"
        assert len(implementation.list_assets(project=PROJECT)) == 3

    # -- listing and filters ---------------------------------------------

    def test_listing_is_scoped_to_one_project(self, implementation: SearchIndex) -> None:
        listed = implementation.list_assets(project=PROJECT)

        assert [entry.asset_id for entry in listed] == ["crate", "mech_scout", "mule"]

    def test_listing_is_ordered_by_identifier(self, implementation: SearchIndex) -> None:
        first = implementation.list_assets(project=PROJECT)
        second = implementation.list_assets(project=PROJECT)

        assert first == second

    def test_filters_combine_rather_than_widen(self, implementation: SearchIndex) -> None:
        listed = implementation.list_assets(
            project=PROJECT, status="modeling", owner="rafa@cyberdyne.com"
        )

        assert [entry.asset_id for entry in listed] == ["mech_scout"]

    def test_a_tag_filter_selects_only_what_carries_the_tag(
        self, implementation: SearchIndex
    ) -> None:
        listed = implementation.list_assets(project=PROJECT, tag="vehicle")

        assert [entry.asset_id for entry in listed] == ["mule"]

    def test_an_owner_matches_whichever_of_the_three_seats_they_hold(
        self, implementation: SearchIndex
    ) -> None:
        listed = implementation.list_assets(project=PROJECT, owner="zoe@cyberdyne.com")

        assert [entry.asset_id for entry in listed] == ["mech_scout"]

    # -- search (D9) -----------------------------------------------------

    def test_an_exact_identifier_outranks_a_description_substring(
        self, implementation: SearchIndex
    ) -> None:
        hits = implementation.search("mech_scout", project=PROJECT)

        assert hits[0].asset_id == "mech_scout"
        assert hits[0].kind is MatchKind.EXACT_ID

    def test_an_alias_finds_the_asset(self, implementation: SearchIndex) -> None:
        hits = implementation.search("drone", project=PROJECT)

        assert [hit.asset_id for hit in hits] == ["mech_scout"]
        assert hits[0].kind is MatchKind.ALIAS

    def test_a_description_substring_finds_what_nothing_stronger_does(
        self, implementation: SearchIndex
    ) -> None:
        hits = implementation.search("six-wheeled", project=PROJECT)

        assert [hit.asset_id for hit in hits] == ["mule"]
        assert hits[0].kind is MatchKind.DESCRIPTION

    def test_search_is_scoped_to_one_project(self, implementation: SearchIndex) -> None:
        assert implementation.search("banner", project=PROJECT) == ()
        assert [hit.asset_id for hit in implementation.search("banner")] == ["banner"]

    def test_search_is_deterministic_across_runs(self, implementation: SearchIndex) -> None:
        first = implementation.search("mech", project=PROJECT)
        second = implementation.search("mech", project=PROJECT)

        assert first == second
        assert [hit.kind.pass_number for hit in first] == sorted(
            hit.kind.pass_number for hit in first
        )

    def test_a_term_that_matches_nothing_returns_nothing(self, implementation: SearchIndex) -> None:
        assert implementation.search(MISSING_TERM, project=PROJECT) == ()

    # -- misses (D11) ----------------------------------------------------

    def test_a_recorded_miss_is_retrievable(self, implementation: SearchIndex) -> None:
        implementation.record_miss(MISSING_TERM, project=PROJECT)

        assert [miss.term for miss in implementation.misses()] == [MISSING_TERM]

    def test_a_repeated_miss_is_counted_rather_than_duplicated(
        self, implementation: SearchIndex
    ) -> None:
        implementation.record_miss(MISSING_TERM, project=PROJECT)
        implementation.record_miss(MISSING_TERM, project=PROJECT)

        (miss,) = implementation.misses()
        assert miss.count == 2

    def test_nothing_is_recorded_until_a_search_misses(self, implementation: SearchIndex) -> None:
        assert implementation.misses() == ()

    # -- staleness (D8) --------------------------------------------------

    def test_a_row_matching_the_file_is_not_stale(self, implementation: SearchIndex) -> None:
        assert not implementation.is_stale("mech_scout", MECH_SCOUT.fingerprint)

    def test_an_edited_file_makes_its_row_stale(self, implementation: SearchIndex) -> None:
        edited = FileFingerprint(path=MECH_SCOUT.spec_path, size=900, mtime_ns=99)

        assert implementation.is_stale("mech_scout", edited)

    def test_a_deleted_file_makes_its_row_stale(self, implementation: SearchIndex) -> None:
        assert implementation.is_stale("mech_scout", None)

    def test_an_unindexed_asset_is_stale(self, implementation: SearchIndex) -> None:
        """Nothing indexed can be served as current, so the answer is no."""
        assert implementation.is_stale("nobody", None)

    # -- disposability ---------------------------------------------------

    def test_forgetting_one_row_leaves_the_rest(self, implementation: SearchIndex) -> None:
        implementation.forget("crate", project=PROJECT)

        assert implementation.get("crate") is None
        assert [entry.asset_id for entry in implementation.list_assets(project=PROJECT)] == [
            "mech_scout",
            "mule",
        ]

    def test_a_deleted_index_rebuilds_to_the_same_answers(
        self, implementation: SearchIndex
    ) -> None:
        """The index is derived: deleting it loses nothing the repository holds."""
        before_list = implementation.list_assets(project=PROJECT)
        before_search = implementation.search("mech", project=PROJECT)

        implementation.clear()
        assert implementation.list_assets(project=PROJECT) == ()
        seed(implementation)

        assert implementation.list_assets(project=PROJECT) == before_list
        assert implementation.search("mech", project=PROJECT) == before_search
