"""Tasks 3.4-3.7 and 3.12 — locating, listing, searching, and naming people.

The four questions a developer actually asks, answered from the derived index
with no identity and no network. The assertions are on *content* — that the
engine path is reported as not recorded, that the exact identifier ranks first —
never on wording, so the prose renderers in the MCP adapter can be improved
without rewriting any of this.
"""

from __future__ import annotations

import socket

import pytest

from cybercanon.application.ports.search_index import ABSENT, IndexedAsset, MatchKind
from cybercanon.application.ports.spec_store import ProjectConfig
from cybercanon.application.results import NotFound
from cybercanon.application.testing.outcomes import ran, refused
from cybercanon.application.testing.search_index import InMemorySearchIndex
from cybercanon.application.testing.spec_store import InMemorySpecStore
from cybercanon.application.use_cases.index_assets import rebuild_index
from cybercanon.application.use_cases.lookup_assets import (
    ART,
    CODE,
    DESIGN,
    DESIGN_DOCUMENT,
    DIRECTORY,
    DISCUSSION,
    ENGINE_PATH,
    LOCATION_LABELS,
    SOURCE_FILE,
    VALIDATED_AT,
    VALIDATED_EXPORT,
    UnknownAsset,
    list_assets,
    recorded_misses,
    search_assets,
    where_is,
)
from cybercanon.domain.actors import ActorBinding, ActorMapping
from cybercanon.domain.asset import Asset, AssetId, Links
from cybercanon.domain.identity import UNMAPPED_MARK
from cybercanon.domain.status import Status

PROJECT = "cyberdyne-game"
SCOUT_PATH = "characters/mech_scout/asset.yaml"
CRATE_PATH = "props/crate/asset.yaml"

RAFA_EMAIL = "rafa@cyberdyne.com"
ANA_EMAIL = "ana@cyberdyne.com"
STRANGER = "contractor@elsewhere.io"

RAFA = ActorBinding(
    subject="auth|rafa",
    display_name="Rafa",
    emails=(RAFA_EMAIL,),
    default_role="ARTIST",
)
MAPPING = ActorMapping((RAFA,))

SCOUT = Asset(
    id=AssetId("mech_scout"),
    name="Scout Mech",
    status=Status.MODELING,
    aliases=("drone",),
    owner_art=RAFA_EMAIL,
    owner_design=ANA_EMAIL,
    owner_code=None,
    links=Links(
        source="art/mech_scout.blend",
        engine="/Game/Chars/MechScout",
        discussion="https://chat.example/threads/17",
    ),
)
CRATE = Asset(
    id=AssetId("crate"),
    name="Supply Crate",
    status=Status.VALIDATED,
    owner_art=ANA_EMAIL,
    links=Links(source="art/crate.blend"),
)


def a_store(mapping: ActorMapping | None = MAPPING) -> InMemorySpecStore:
    store = InMemorySpecStore()
    store.set_project(ProjectConfig(name=PROJECT))
    store.add(SCOUT_PATH, SCOUT)
    store.add(CRATE_PATH, CRATE)
    if mapping is not None:
        store.set_actor_mapping(mapping)
    return store


def an_index(store: InMemorySpecStore) -> InMemorySearchIndex:
    index = InMemorySearchIndex()
    ran(rebuild_index(spec_store=store, search_index=index))
    return index


@pytest.fixture
def store() -> InMemorySpecStore:
    return a_store()


@pytest.fixture
def index(store: InMemorySpecStore) -> InMemorySearchIndex:
    return an_index(store)


# --------------------------------------------------------------------------
# 3.4 — where_is
# --------------------------------------------------------------------------


def test_a_location_answer_carries_every_recorded_location(store, index) -> None:
    answer = ran(where_is("mech_scout", spec_store=store, search_index=index))

    assert answer.location(DIRECTORY).value == "characters/mech_scout"
    assert answer.location(SOURCE_FILE).value == "art/mech_scout.blend"
    assert answer.location(ENGINE_PATH).value == "/Game/Chars/MechScout"
    assert answer.location(DISCUSSION).value == "https://chat.example/threads/17"
    assert answer.status == "modeling"


def test_a_location_answer_carries_the_three_owners(store, index) -> None:
    answer = ran(where_is("mech_scout", spec_store=store, search_index=index))

    assert [owner.discipline for owner in answer.owners] == [ART, DESIGN, CODE]
    assert answer.owner(ART).display == "Rafa"
    assert answer.owner(CODE).display == ABSENT


def test_an_unrecorded_location_is_stated_rather_than_omitted(store, index) -> None:
    answer = ran(where_is("crate", spec_store=store, search_index=index))

    assert [entry.label for entry in answer.locations] == list(LOCATION_LABELS)
    engine = answer.location(ENGINE_PATH)
    assert not engine.is_recorded
    assert engine.text == ABSENT
    assert ENGINE_PATH in {entry.label for entry in answer.unrecorded}
    assert DESIGN_DOCUMENT in {entry.label for entry in answer.unrecorded}


def test_a_validated_export_is_identified_with_its_date(store, index) -> None:
    from dataclasses import replace

    indexed = index.get("mech_scout")
    assert indexed is not None
    index.upsert(
        replace(
            indexed,
            validated_export="exports/SM_MechScout_LOD0.glb",
            validated_at="2026-09-17",
        )
    )

    answer = ran(where_is("mech_scout", spec_store=store, search_index=index))

    assert answer.location(VALIDATED_EXPORT).value == "exports/SM_MechScout_LOD0.glb"
    assert answer.location(VALIDATED_AT).value == "2026-09-17"


def test_an_unindexed_asset_is_refused_by_name(store, index) -> None:
    failure = refused(where_is("no_such_asset", spec_store=store, search_index=index))

    assert isinstance(failure, NotFound)
    assert failure.identifier == UnknownAsset.identifier
    assert "no_such_asset" in failure.message


def test_a_location_answer_needs_no_network(store, index, monkeypatch) -> None:
    def refuse(*args: object, **kwargs: object) -> None:
        raise AssertionError("a lookup opened a network connection")

    monkeypatch.setattr(socket, "socket", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)

    assert (
        ran(where_is("mech_scout", spec_store=store, search_index=index)).asset_id == "mech_scout"
    )


# --------------------------------------------------------------------------
# 3.5 — list_assets
# --------------------------------------------------------------------------


def test_a_listing_returns_the_projects_assets_by_identifier(store, index) -> None:
    listing = ran(list_assets(spec_store=store, search_index=index, project=PROJECT))

    assert listing.asset_ids == ("crate", "mech_scout")


def test_filters_combine_rather_than_widen(store, index) -> None:
    both = ran(
        list_assets(
            spec_store=store,
            search_index=index,
            project=PROJECT,
            status="modeling",
            owner=RAFA_EMAIL,
        )
    )
    mismatched = ran(
        list_assets(
            spec_store=store,
            search_index=index,
            project=PROJECT,
            status="validated",
            owner=RAFA_EMAIL,
        )
    )

    assert both.asset_ids == ("mech_scout",)
    assert mismatched.asset_ids == ()


def test_a_listing_resolves_the_owners_it_names(store, index) -> None:
    listing = ran(list_assets(spec_store=store, search_index=index, project=PROJECT))
    row = next(row for row in listing.rows if row.asset_id == "mech_scout")

    assert row.owner(ART).display == "Rafa"
    assert row.status == "modeling"


def test_a_tag_filter_is_scoped_to_the_project(store, index) -> None:
    index.upsert(IndexedAsset(asset_id="turret", name="Turret", project=PROJECT, tags=("weapon",)))
    index.upsert(
        IndexedAsset(asset_id="other", name="Other", project="another-game", tags=("weapon",))
    )

    listing = ran(list_assets(spec_store=store, search_index=index, project=PROJECT, tag="weapon"))

    assert listing.asset_ids == ("turret",)


# --------------------------------------------------------------------------
# 3.6 — search_assets, the fixed cascade (D9)
# --------------------------------------------------------------------------


def test_an_alias_finds_the_asset(store, index) -> None:
    answer = ran(search_assets("drone", search_index=index))

    assert answer.asset_ids == ("mech_scout",)
    assert answer.hits[0].kind is MatchKind.ALIAS


def test_an_exact_identifier_outranks_a_description_substring(store, index) -> None:
    index.upsert(
        IndexedAsset(
            asset_id="hangar",
            name="Hangar",
            project=PROJECT,
            description="the bay where a mech_scout is repaired",
        )
    )

    answer = ran(search_assets("mech_scout", search_index=index, project=PROJECT))

    assert answer.asset_ids == ("mech_scout", "hangar")
    assert answer.hits[0].kind is MatchKind.EXACT_ID
    assert answer.hits[1].kind is MatchKind.DESCRIPTION


def test_search_is_deterministic_across_runs(store, index) -> None:
    runs = {ran(search_assets("mech", search_index=index)).asset_ids for _ in range(5)}

    assert len(runs) == 1


def test_search_needs_no_embeddings_or_vector_store(store, index) -> None:
    """The only collaborator is the index; nothing here can reach a model."""
    answer = ran(search_assets("Scout", search_index=index))

    assert answer.asset_ids == ("mech_scout",)
    assert answer.hits[0].kind is MatchKind.NAME_PREFIX


# --------------------------------------------------------------------------
# 3.7 — zero-result queries are recorded, locally (D11)
# --------------------------------------------------------------------------


def test_a_miss_is_recorded_and_retrievable(store, index) -> None:
    answer = ran(search_assets("hovercraft", search_index=index, project=PROJECT))

    assert answer.is_empty
    assert answer.recorded_as_miss
    assert [miss.term for miss in ran(recorded_misses(search_index=index))] == ["hovercraft"]


def test_a_successful_search_records_no_miss(store, index) -> None:
    answer = ran(search_assets("drone", search_index=index, project=PROJECT))

    assert not answer.recorded_as_miss
    assert ran(recorded_misses(search_index=index)) == ()


def test_a_repeated_miss_is_counted_once_with_its_frequency(store, index) -> None:
    for _ in range(3):
        ran(search_assets("hovercraft", search_index=index, project=PROJECT))

    (miss,) = ran(recorded_misses(search_index=index))
    assert miss.count == 3


def test_recording_a_miss_transmits_nothing(store, index, monkeypatch) -> None:
    def refuse(*args: object, **kwargs: object) -> None:
        raise AssertionError("a recorded miss left the machine")

    monkeypatch.setattr(socket, "socket", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)

    ran(search_assets("hovercraft", search_index=index, project=PROJECT))

    assert [miss.term for miss in ran(recorded_misses(search_index=index))] == ["hovercraft"]


# --------------------------------------------------------------------------
# 3.12 — every name goes through the mapping (D12, D14)
# --------------------------------------------------------------------------


def test_a_mapped_owner_renders_as_the_display_name(store, index) -> None:
    answer = ran(where_is("mech_scout", spec_store=store, search_index=index))

    owner = answer.owner(ART)
    assert owner.display == "Rafa"
    assert not owner.is_unmapped
    assert owner.recorded == RAFA_EMAIL


def test_an_unmapped_owner_renders_as_the_raw_email_marked_unmapped(store, index) -> None:
    answer = ran(where_is("mech_scout", spec_store=store, search_index=index))

    owner = answer.owner(DESIGN)
    assert owner.is_unmapped
    assert ANA_EMAIL in owner.display
    assert UNMAPPED_MARK in owner.display


def test_an_owner_is_resolved_identically_in_a_location_answer_and_a_listing(store, index) -> None:
    answer = ran(where_is("mech_scout", spec_store=store, search_index=index))
    listing = ran(list_assets(spec_store=store, search_index=index, project=PROJECT))
    row = next(row for row in listing.rows if row.asset_id == "mech_scout")

    assert answer.owner(ART).display == row.owner(ART).display
    assert answer.owner(DESIGN).display == row.owner(DESIGN).display


def test_a_project_with_no_mapping_reports_every_owner_as_unmapped() -> None:
    store = a_store(mapping=None)
    index = an_index(store)

    answer = ran(where_is("mech_scout", spec_store=store, search_index=index))

    assert answer.owner(ART).is_unmapped
    assert RAFA_EMAIL in answer.owner(ART).display


def test_an_unrecorded_owner_is_neither_mapped_nor_guessed(store, index) -> None:
    owner = ran(where_is("crate", spec_store=store, search_index=index)).owner(CODE)

    assert not owner.is_recorded
    assert owner.actor is None
    assert owner.display == ABSENT
    assert STRANGER not in owner.display
