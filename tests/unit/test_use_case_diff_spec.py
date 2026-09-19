"""Task 3.11 — what changed in a specification, as semantic statements (D10).

The comparison is between *parsed specifications*, so the assertions here are
about meaning — a budget that moved from 12000 to 9000 — and never about the
text of a file. Reformatting a file produces no change, which is the whole
reason this is not a textual difference.
"""

from __future__ import annotations

from dataclasses import replace

from cybercanon.application.testing.spec_store import InMemorySpecStore
from cybercanon.application.use_cases.diff_spec import UNCHANGED, compare, diff_spec
from cybercanon.domain.asset import Asset, AssetId, Links
from cybercanon.domain.concept import Concept
from cybercanon.domain.constraints import Constraints, Rig
from cybercanon.domain.design import Design, Socket
from cybercanon.domain.status import Status

SPEC_PATH = "characters/mech_scout/asset.yaml"
BEFORE_REVISION = "a1b2c3d"

SCOUT = Asset(
    id=AssetId("mech_scout"),
    name="Scout Mech",
    status=Status.MODELING,
    owner_art="rafa@cyberdyne.com",
    concept=Concept(views=("front.png",), silhouette_rules=("tall antenna",)),
    design=Design(role="scout", sockets=(Socket(name="SOCKET_muzzle_l", purpose="vfx"),)),
    constraints=Constraints(tri_budget=12000, up_axis="Z", rig=Rig(max_bones=80)),
    links=Links(source="art/mech_scout.blend"),
)


def a_store(previous: Asset | None = SCOUT, current: Asset = SCOUT) -> InMemorySpecStore:
    store = InMemorySpecStore()
    store.add(SPEC_PATH, current)
    if previous is not None:
        store.add_revision(SPEC_PATH, BEFORE_REVISION, previous)
    return store


def reduced_budget(asset: Asset = SCOUT, budget: int = 9000) -> Asset:
    constraints = asset.constraints
    assert constraints is not None
    return replace(asset, constraints=replace(constraints, tri_budget=budget))


# --------------------------------------------------------------------------
# The statements
# --------------------------------------------------------------------------


def test_a_reduced_budget_renders_as_previous_then_current() -> None:
    store = a_store(previous=SCOUT, current=reduced_budget())

    difference = diff_spec(SPEC_PATH, BEFORE_REVISION, spec_store=store)

    change = difference.change("triangle budget")
    assert change is not None
    assert change.previous == "12000"
    assert change.current == "9000"
    assert "12000" in str(change)
    assert "9000" in str(change)
    assert len(difference) == 1


def test_an_unchanged_specification_says_so() -> None:
    store = a_store()

    difference = diff_spec(SPEC_PATH, BEFORE_REVISION, spec_store=store)

    assert difference.is_unchanged
    assert difference.changes == ()
    assert UNCHANGED in difference.summary


def test_durable_content_of_every_block_is_compared() -> None:
    moved = replace(
        SCOUT,
        status=Status.VALIDATED,
        concept=Concept(views=("front.png", "back.png"), silhouette_rules=("tall antenna",)),
        design=Design(role="recon", sockets=(Socket(name="SOCKET_muzzle_r", purpose="vfx"),)),
        links=Links(source="art/mech_scout.blend", engine="/Game/Chars/MechScout"),
    )
    store = a_store(previous=SCOUT, current=moved)

    difference = diff_spec(SPEC_PATH, BEFORE_REVISION, spec_store=store)

    labels = {change.label for change in difference.changes}

    assert {"status", "concept views", "role", "required sockets", "engine path"} <= labels


def test_a_removed_field_is_distinguishable_from_one_that_never_existed() -> None:
    without_rig = replace(SCOUT, constraints=replace(SCOUT.constraints or Constraints(), rig=None))

    (change,) = compare(SCOUT, without_rig)

    assert change.label == "bone budget"
    assert change.was_removed
    assert change.previous == "80"
    assert change.current is None


def test_an_added_field_is_reported_as_added() -> None:
    (change,) = compare(SCOUT, replace(SCOUT, owner_code="joe@cyberdyne.com"))

    assert change.label == "code owner"
    assert change.was_added


def test_comparison_is_semantic_rather_than_textual() -> None:
    """The same values authored in another order are not a change."""
    reordered = replace(SCOUT, constraints=replace(SCOUT.constraints or Constraints()))

    assert compare(SCOUT, reordered) == ()


# --------------------------------------------------------------------------
# Missing history degrades instead of failing
# --------------------------------------------------------------------------


def test_a_repository_without_that_history_degrades_with_a_message() -> None:
    store = a_store(previous=None)

    difference = diff_spec(SPEC_PATH, BEFORE_REVISION, spec_store=store)

    assert not difference.available
    assert difference.changes == ()
    assert "history is unavailable" in difference.message
    assert BEFORE_REVISION in difference.message
    assert difference.summary == difference.message


def test_an_unknown_revision_degrades_rather_than_raising() -> None:
    store = a_store()

    difference = diff_spec(SPEC_PATH, "0000000", spec_store=store)

    assert not difference.available
    assert "0000000" in difference.message
    assert not difference.is_unchanged, "unavailable is not the same answer as unchanged"


def test_the_asset_is_still_identified_when_history_is_unavailable() -> None:
    store = a_store(previous=None)

    difference = diff_spec(SPEC_PATH, BEFORE_REVISION, spec_store=store)

    assert difference.asset_id == "mech_scout"
    assert difference.path == SPEC_PATH
