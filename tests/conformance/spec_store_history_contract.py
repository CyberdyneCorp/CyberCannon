"""What a `SpecStore` SHALL do with history and with the actor mapping (2.6, 2.7).

Kept apart from `spec_store_contract.py` on purpose. Those are the three
questions every store has answered since change 1; these are the two this change
adds (D10, D12), and `GitSpecStore` joins each contract as it grows the
capability — history in task 4.2, the mapping in task 4.4 — rather than the
whole file failing until both land.

**History is compared as parsed specifications, never as file text** (D10). So
the corpus is one asset at two revisions differing in a single constraint: a
store that returned the right bytes but the wrong parse would pass a textual
assertion and fail this one.

**A revision identifier is whatever the store calls it.** The fake names its
revisions; `GitSpecStore` answers with commit hashes it computed. So the
contract asks each store for its own series and asserts what a series *means* —
newest first, bounded on request, and the older revision carrying the older
budget — rather than asserting identifiers only one implementation could
produce.

**The mapping has three outcomes and none of them raises** (D12): a file, no
file, and a file nobody can parse. The third is the one worth writing down — a
broken identity file must degrade to "every author is unmapped", never to a
repository nobody can read.
"""

from __future__ import annotations

import pytest

from cybercanon.application.ports.spec_store import HistoryUnavailable, SpecStore
from cybercanon.domain.actor_checks import RULE_UNPARSEABLE
from cybercanon.domain.actors import ACTORS_PATH, ActorBinding, ActorMapping
from cybercanon.domain.asset import Asset, AssetId
from cybercanon.domain.constraints import Constraints
from cybercanon.domain.identity import Role
from cybercanon.domain.status import Status

SPEC_PATH = "characters/mech_scout/asset.yaml"
UNTRACKED_SPEC = "vehicles/mule/asset.yaml"

OLDER = "rev-older"
NEWER = "rev-newer"
REVISIONS = (OLDER, NEWER)
"""What the fake is seeded with, oldest first. Only a factory names these."""

UNKNOWN_REVISION = "rev-nobody-wrote"

BUDGET_THEN = 12000
BUDGET_NOW = 9000


def _mech_scout(budget: int) -> Asset:
    return Asset(
        id=AssetId("mech_scout"),
        name="Scout Mech",
        status=Status.MODELING,
        constraints=Constraints(tri_budget=budget),
    )


HISTORY = {OLDER: _mech_scout(BUDGET_THEN), NEWER: _mech_scout(BUDGET_NOW)}

RAFA = ActorBinding(
    subject="auth|rafa",
    display_name="Rafa",
    emails=("rafa@cyberdyne.com", "rafa@personal.dev"),
    chat_handle="@rafa",
    default_role="ARTIST",
)
MAPPING = ActorMapping((RAFA,))

UNPARSEABLE_DETAIL = "line 4: found unexpected ':'"


def budget_at(store: SpecStore, revision: str) -> int | None:
    """The triangle budget the specification declared at that revision."""
    constraints = store.load_at(SPEC_PATH, revision).asset.constraints
    return constraints.tri_budget if constraints else None


class SpecStoreHistoryContract:
    """Reading a specification as it stood at an earlier revision (D10)."""

    def test_an_earlier_revision_parses_into_the_same_domain_objects(
        self, implementation: SpecStore
    ) -> None:
        oldest = implementation.revisions_for(SPEC_PATH)[-1]
        earlier = implementation.load_at(SPEC_PATH, oldest)

        assert earlier.asset.id.value == "mech_scout"
        assert earlier.asset.constraints is not None
        assert earlier.asset.constraints.tri_budget == BUDGET_THEN

    def test_the_series_shows_the_change_the_diff_will_describe(
        self, implementation: SpecStore
    ) -> None:
        newest, *_, oldest = implementation.revisions_for(SPEC_PATH)
        earlier = implementation.load_at(SPEC_PATH, oldest)
        later = implementation.load_at(SPEC_PATH, newest)

        assert earlier.asset.constraints != later.asset.constraints

    def test_revisions_are_listed_newest_first(self, implementation: SpecStore) -> None:
        """Asserted by what the revisions *contain*: a hash proves nothing by itself."""
        series = implementation.revisions_for(SPEC_PATH)

        assert len(series) == len(REVISIONS)
        assert budget_at(implementation, series[0]) == BUDGET_NOW
        assert budget_at(implementation, series[-1]) == BUDGET_THEN

    def test_the_revision_list_can_be_bounded(self, implementation: SpecStore) -> None:
        bounded = implementation.revisions_for(SPEC_PATH, limit=1)

        assert bounded == implementation.revisions_for(SPEC_PATH)[:1]
        assert budget_at(implementation, bounded[0]) == BUDGET_NOW

    def test_a_file_with_no_history_lists_nothing(self, implementation: SpecStore) -> None:
        """Empty is an answer — a new file, or a store with no version control."""
        assert implementation.revisions_for(UNTRACKED_SPEC) == ()

    def test_an_unreachable_revision_is_a_named_failure(self, implementation: SpecStore) -> None:
        """A degraded answer beats a broken session, so the caller can catch this."""
        with pytest.raises(HistoryUnavailable):
            implementation.load_at(SPEC_PATH, UNKNOWN_REVISION)

    def test_a_file_with_no_history_reports_unavailability(self, implementation: SpecStore) -> None:
        """Reachable revision, uncommitted file: unavailable, not a broken read."""
        reachable = implementation.revisions_for(SPEC_PATH)[0]

        with pytest.raises(HistoryUnavailable):
            implementation.load_at(UNTRACKED_SPEC, reachable)


class SpecStoreMappingContract:
    """Reading `.canon/actors.yaml` as project-scoped repository content (D12)."""

    def test_a_declared_mapping_is_served(self, implementation: SpecStore) -> None:
        loaded = implementation.load_actor_mapping("")

        assert loaded.is_declared
        assert loaded.is_readable
        (binding,) = loaded.mapping.bindings
        assert binding.subject == "auth|rafa"
        assert binding.emails == ("rafa@cyberdyne.com", "rafa@personal.dev")
        assert binding.role is Role.ARTIST

    def test_the_mapping_is_the_same_from_anywhere_inside_the_project(
        self, implementation: SpecStore
    ) -> None:
        assert implementation.load_actor_mapping("") == implementation.load_actor_mapping(SPEC_PATH)

    def test_an_absent_mapping_is_empty_and_not_a_failure(self, without_mapping: SpecStore) -> None:
        loaded = without_mapping.load_actor_mapping("")

        assert loaded.mapping.is_empty
        assert not loaded.is_declared
        assert loaded.is_readable

    def test_an_unparseable_mapping_is_a_violation_naming_the_file(
        self, unparseable_mapping: SpecStore
    ) -> None:
        loaded = unparseable_mapping.load_actor_mapping("")

        assert loaded.mapping.is_empty
        assert not loaded.is_readable
        (violation,) = loaded.violations
        assert violation.rule_id == RULE_UNPARSEABLE
        assert ACTORS_PATH in violation.message

    def test_a_broken_mapping_does_not_stop_the_specifications_being_read(
        self, unparseable_mapping: SpecStore
    ) -> None:
        """The whole point of reporting rather than raising."""
        assert unparseable_mapping.load(SPEC_PATH).asset.id.value == "mech_scout"
