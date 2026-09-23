"""What a derived-metadata test has on the table, shared by the unit suite and the steps.

Built on :mod:`views_world`, deliberately and without a second arrangement: that
module already stands a real repository host, a `SpecStore` that reads its
specifications **out of the repository** through the adapter's own reader and
writer, and an image inspector over bytes a fixture generated. Generation and
acceptance need exactly those, plus a model.

So the round trip here is real in the places it has to be: an accepted alias is
written by the comment-preserving round-trip writer, committed through the
repository host, and read back by parsing what actually landed — never by
asserting against something a test remembered.

Two seams a scenario reaches for:

* :meth:`Derived.answering` puts a description and a list of terms into the
  vision fake, so *"the model said this"* is arranged rather than mocked;
* :meth:`Derived.refusing` makes it unavailable for a named reason, which is
  how each of the six degradations is exercised by the same code path.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from cybercanon.application.ports.clock import fixed_clock
from cybercanon.application.ports.llm import Unavailability
from cybercanon.application.testing.search_index import InMemorySearchIndex
from cybercanon.application.testing.vision import InMemoryVision
from cybercanon.application.use_cases.derived_metadata import (
    Derivation,
    accept_suggestion,
    describe_view,
    list_derived,
    reject_suggestion,
    suggest_aliases,
)
from cybercanon.domain.actors import GitAuthor
from cybercanon.domain.identity import Actor, ActorId, ActorKind, Role
from cybercanon.domain.revisions import ContentHash
from views_world import PROJECT, RAFA, RAFA_SUBJECT, SCOUT, SCOUT_DIR, SCOUT_SPEC, Views, a_world

DESCRIPTION = "A light reconnaissance walker with a narrow silhouette."
TERMS = "mech, walker, quadruped, recon"

MOMENT = datetime(2026, 9, 22, 11, 30, tzinfo=UTC)
"""A fixed clock, so provenance is asserted rather than approximated."""

RAFA_ACTOR = Actor(
    id=ActorId(RAFA_SUBJECT),
    display_name="Rafa",
    roles=(Role.ART_DIRECTOR,),
    projects=(PROJECT,),
)
"""The person the scenarios accept as. An art director, because G4 lets one accept."""

AN_AGENT = Actor(
    id=ActorId("auth|blender"),
    display_name="blender-agent",
    roles=(Role.ART_DIRECTOR, Role.ARTIST, Role.DESIGNER, Role.ENGINEER),
    projects=(PROJECT,),
    kind=ActorKind.AUTOMATION,
)
"""An automated caller holding **every** role, so a refusal cannot be about roles."""

FRONT = f"{SCOUT_DIR}/concept/front.png"
SIDE = f"{SCOUT_DIR}/concept/side.png"


@dataclass
class Derived:
    """The ports one generation or acceptance runs against, and what landed."""

    views: Views
    index: InMemorySearchIndex = field(default_factory=InMemorySearchIndex)
    vision: InMemoryVision = field(default_factory=InMemoryVision)
    actor: Actor | None = RAFA_ACTOR
    author: GitAuthor | None = RAFA
    moment: datetime = MOMENT

    # -- arranging -------------------------------------------------------

    def answering(self, description: str = DESCRIPTION, terms: str = TERMS) -> None:
        """What the model says about every image it is shown, from now on."""
        self.vision.will_answer(description, terms)

    def always_answering(self, description: str = DESCRIPTION, terms: str = TERMS) -> None:
        """The same two answers however many images it is shown."""
        for _ in range(8):
            self.vision.will_answer(description, terms)

    def refusing(self, reason: Unavailability, detail: str = "") -> None:
        """Be unavailable for that reason, every time. What a disabled model is."""
        self.vision.always_refuses(reason, detail)

    # -- operations ------------------------------------------------------

    def derivation(
        self,
        asset_id: str = SCOUT,
        *,
        actor: Actor | str | None = "",
        author: GitAuthor | str | None = "",
        via: Any | None = None,
    ) -> Derivation:
        return Derivation(
            project=PROJECT,
            asset_id=asset_id,
            repository_host=self.views.host,
            spec_store=self.views.spec_store,
            search_index=self.index,
            vision=self.vision,
            actor=self.actor if actor == "" else actor,
            author=self.author if author == "" else author,
            via=via,
            clock=fixed_clock(self.moment),
        )

    def describe(self, asset_id: str = SCOUT, slot: str = "", **options: Any):
        return describe_view(self.derivation(asset_id, **options), slot)

    def suggest(self, asset_id: str = SCOUT, slot: str = "", **options: Any):
        return suggest_aliases(self.derivation(asset_id, **options), slot)

    def listed(self, asset_id: str = SCOUT, **options: Any):
        return list_derived(self.derivation(asset_id, **options))

    def accept(
        self,
        value: str,
        source_hash: str = "",
        written: str = "",
        asset_id: str = SCOUT,
        **options: Any,
    ):
        return accept_suggestion(
            self.derivation(asset_id, **options),
            source_hash or self.source_hash(),
            value,
            written,
        )

    def reject(self, value: str, source_hash: str = "", asset_id: str = SCOUT, **options: Any):
        return reject_suggestion(
            self.derivation(asset_id, **options), source_hash or self.source_hash(), value
        )

    # -- what landed -----------------------------------------------------

    def files(self) -> dict[str, bytes]:
        return self.views.files()

    def spec_text(self, path: str = SCOUT_SPEC) -> str:
        return self.files()[path].decode("utf-8")

    def aliases(self, asset_id: str = SCOUT) -> tuple[str, ...]:
        """What the specification file now declares, parsed from what landed."""
        loaded = self.views.spec_store.load(SCOUT_SPEC)
        return loaded.asset.aliases if loaded.asset.id.value == asset_id else ()

    def source_hash(self, path: str = FRONT) -> str:
        """The content hash of one concept view — what a record is keyed by."""
        return ContentHash.of(self.files()[path]).value

    def records(self):
        return self.index.derived_records(PROJECT)

    def model_calls(self) -> int:
        return self.vision.calls


def a_derived_world(
    spec: bytes | None = None, views: dict[str, bytes] | None = None, *, mapped: bool = True
) -> Derived:
    """A project whose `mech_scout` exists and holds the concept views asked for.

    The images are real bytes from `canon_fixtures`, so a content hash is the
    hash of something rather than of a string a test typed.
    """
    world = a_world(mapped=mapped)
    files: dict[str, bytes] = {SCOUT_SPEC: spec if spec is not None else _a_spec()}
    for path, content in (views if views is not None else {FRONT: b""}).items():
        files[path] = content or world.an_image(seed=len(path))
    world.host.add_project(PROJECT, files)
    world.host.clone(PROJECT)
    return Derived(views=world)


def _a_spec(aliases: str = "") -> bytes:
    """The hand-authored specification acceptance writes into, comments and all."""
    return (
        "# The scout. Keep the silhouette readable at 32 px.\n"
        "schema_version: 1\n"
        "id: mech_scout\n"
        "name: Scout Mech\n"
        "status: concept\n"
        f"{aliases}"
        "owner_art: rafa@cyberdyne.com  # art owns the concept\n"
    ).encode()


def a_spec_with(aliases: tuple[str, ...] = ()) -> bytes:
    """The same file, already declaring these aliases in flow style."""
    declared = f"aliases: [{', '.join(aliases)}]\n" if aliases else ""
    return _a_spec(declared)


__all__ = [
    "AN_AGENT",
    "DESCRIPTION",
    "FRONT",
    "MOMENT",
    "PROJECT",
    "RAFA",
    "RAFA_ACTOR",
    "RAFA_SUBJECT",
    "SCOUT",
    "SCOUT_DIR",
    "SCOUT_SPEC",
    "SIDE",
    "TERMS",
    "Derived",
    "a_derived_world",
    "a_spec_with",
]
