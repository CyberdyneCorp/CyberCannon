"""What a delegated-search test has on the table, shared by the unit suite and the steps.

Its own module at the root of `tests/` for the reason `tests/views_world.py`
gives: the directories below have conftests of their own, so a shared name would
resolve to whichever pytest inserted into `sys.path` first.

Both halves are the real thing with in-memory edges. The local half is the
in-memory `SearchIndex` ranked by the port's own cascade — not a list somebody
sorted — and the remote half is the in-memory `DocumentPlatform`, with
per-actor permissions, a failure switch and a delay measured against the
caller's budget. The use case on top is the product's.

Two properties of the arrangement are what make the assertions worth anything:

* **the same asset is findable exactly and mentioned in prose.** `mech_scout` is
  indexed *and* written about in two documents, so *"a semantic hit is not an
  asset record"* can be asserted about a response that genuinely contains both;
* **two people see different documents.** Rafa may read the rationale and the
  research; Bruno may read the faction bible and neither of the others. The
  workspace is the same one, so *"each SHALL receive only passages from
  workspaces they may read"* is decided by the platform's own permissions
  rather than by the query being different.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta

from cybercanon.application.ports.document_platform import (
    DEFAULT_BUDGET,
    NO_CREDENTIAL,
    Credential,
    DocumentPlatform,
    NullDocumentPlatform,
    UnavailabilityReason,
)
from cybercanon.application.ports.search_index import IndexedAsset
from cybercanon.application.results import Result
from cybercanon.application.testing.document_platform import InMemoryDocumentPlatform, Request
from cybercanon.application.testing.search_index import InMemorySearchIndex
from cybercanon.application.use_cases.search_delegation import (
    DelegatedSearch,
    search_assets_and_docs,
)
from documents_world import (
    BRUNO_SUBJECT,
    BRUNO_TOKEN,
    PRIVATE,
    RAFA_SUBJECT,
    RAFA_TOKEN,
    RATIONALE,
    RESEARCH,
    WORKSPACE,
)
from views_world import PROJECT

SCOUT = "mech_scout"
HEAVY = "mech_heavy"
DRONE = "drone_spotter"

PROSE_QUERY = "why does the scout mech look scavenged"
"""The specification's own example of a natural-language question."""

IDENTIFIER_QUERY = SCOUT
"""The specification's own example of a query that is not delegated."""

UNKNOWN_QUERY = "why is the armour plate hand welded on every panel"
"""Prose nothing local matches and nothing at the platform answers either."""

BOTH_QUERY = "reconnaissance mech for the logistics"
"""Prose that matches an asset's *description* and also retrieves a passage.

The specification renders *"a query producing both exact and semantic
results"*, so the gate has to be able to produce one: a description substring
is not the query resolving to an identifier, a name, an alias or a tag, which
is the list the requirement names.
"""

RATIONALE_PROSE = (
    "The scout mech looks scavenged because the faction cannot manufacture armour "
    "plate: every panel it wears was taken off something else. We chose that over a "
    "clean silhouette in February, when the team read the heavier chassis as a tank."
)

RESEARCH_PROSE = (
    "Silhouette studies for the scout. The scavenged reading comes from asymmetry "
    "more than from damage, which is why the left pauldron is a cargo bracket."
)

BIBLE_PROSE = (
    "The faction bible: the scavenged look is a political statement about supply "
    "lines, and it is unreleased until the reveal."
)


def an_asset(
    asset_id: str,
    name: str,
    *,
    aliases: tuple[str, ...] = (),
    tags: tuple[str, ...] = (),
    description: str = "",
) -> IndexedAsset:
    return IndexedAsset(
        asset_id=asset_id,
        name=name,
        project=PROJECT,
        status="modeling",
        aliases=aliases,
        tags=tags,
        description=description,
        spec_path=f"characters/{asset_id}/asset.yaml",
        directory=f"characters/{asset_id}",
    )


@dataclass
class Searches:
    """The two halves of one search, and the seams a scenario needs."""

    index: InMemorySearchIndex
    platform: DocumentPlatform = field(default_factory=InMemoryDocumentPlatform)
    budget: timedelta = DEFAULT_BUDGET
    workspace: str = WORKSPACE
    notes: dict[str, object] = field(default_factory=dict)

    # -- running ---------------------------------------------------------

    def run(
        self,
        term: str,
        *,
        token: str = RAFA_TOKEN,
        credentialed: bool = True,
    ) -> Result[DelegatedSearch]:
        """One query, asked with this person's own credential (D2)."""
        return search_assets_and_docs(
            term,
            search_index=self.index,
            platform=self.platform,
            credential=Credential(token) if credentialed else NO_CREDENTIAL,
            project=PROJECT,
            budget=self.budget,
            workspace=self.workspace,
        )

    # -- seams -----------------------------------------------------------

    def unavailable(self, reason: UnavailabilityReason) -> None:
        """Make the platform fail this way for every call from now on."""
        self.platform.fail_with(reason)  # type: ignore[union-attr]

    def unconfigured(self) -> None:
        """The deployment that never set `CANON_ARCHE_ENABLED` (D4)."""
        self.platform = NullDocumentPlatform()

    def slow(self, seconds: float) -> None:
        """A platform that takes longer than the budget it is given."""
        self.platform.set_delay(timedelta(seconds=seconds))  # type: ignore[union-attr]

    # -- what went out ---------------------------------------------------

    @property
    def requests(self) -> tuple[Request, ...]:
        """Every call that reached the platform, with the token and payload it carried."""
        recorded = getattr(self.platform, "requests", [])
        return tuple(recorded)

    @property
    def searches(self) -> tuple[Request, ...]:
        return tuple(sent for sent in self.requests if sent.operation == "search")

    @property
    def misses(self) -> tuple[str, ...]:
        """Every term the local index recorded as matching nothing."""
        return tuple(miss.term for miss in self.index.misses(PROJECT))


def a_world() -> Searches:
    """Three indexed assets, three documents, and two people who see different ones."""
    index = InMemorySearchIndex()
    index.upsert(
        an_asset(
            SCOUT,
            "Scout Mech",
            aliases=("scout", "recon mech"),
            tags=("mech", "faction-logistics"),
            description="Light reconnaissance mech for the logistics faction.",
        )
    )
    index.upsert(an_asset(HEAVY, "Heavy Mech", tags=("mech",)))
    index.upsert(an_asset(DRONE, "Spotter Drone", tags=("drone",)))

    platform = InMemoryDocumentPlatform()
    platform.add_actor(RAFA_TOKEN, RAFA_SUBJECT)
    platform.add_actor(BRUNO_TOKEN, BRUNO_SUBJECT)
    platform.add_document(
        WORKSPACE,
        RATIONALE,
        "mech_scout — design rationale",
        summary=RATIONALE_PROSE,
        body=RATIONALE_PROSE,
        readers=(RAFA_SUBJECT,),
    )
    platform.add_document(
        WORKSPACE,
        RESEARCH,
        "scout silhouette research",
        summary=RESEARCH_PROSE,
        body=RESEARCH_PROSE,
        readers=(RAFA_SUBJECT,),
    )
    platform.add_document(
        WORKSPACE,
        PRIVATE,
        "unreleased faction bible",
        summary=BIBLE_PROSE,
        body=BIBLE_PROSE,
        readers=(BRUNO_SUBJECT,),
    )
    return Searches(index=index, platform=platform)


def without_platform() -> Searches:
    """The same world with no document platform configured at all (D4)."""
    world = a_world()
    world.unconfigured()
    return world
