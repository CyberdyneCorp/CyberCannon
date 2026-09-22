"""What an annotation test has on the table, shared by the unit suite and the steps.

Its own module at the root of `tests/` for the reason `tests/views_world.py`
gives: two directories below have conftests of their own, so a shared name would
resolve to whichever pytest inserted into `sys.path` first.

The arrangement is deliberately the **real** write path with in-memory edges: an
in-memory repository host holding real `asset.yaml` bytes, the adapter's own
comment-preserving reader and writer over them, and the real use cases on top.
Nothing here re-implements an annotation rule, so a scenario that passes here
passes because the product does the thing, not because the test does.

Everything a scenario needs a *seam* for is a method on :class:`Threads`: a
second writer arriving between the read and the commit, a repository that
refuses the push, an agent acting for a person, a person nobody has mapped.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from cybercanon.application.results import Ok, Result
from cybercanon.application.testing.repository_host import InMemoryRepositoryHost
from cybercanon.application.use_cases.annotations import (
    Draft,
    Workspace,
    available_exits,
    create_annotation,
    delete_annotation,
    edit_annotation,
    list_annotations,
    list_triage_queue,
    move_annotation,
    promote_annotation,
    reanchor_annotation,
    reopen_annotation,
    reply_to_annotation,
    resolve_annotation,
)
from cybercanon.domain.actors import ActorBinding, ActorMapping, GitAuthor
from cybercanon.domain.annotations import (
    Anchor,
    Anchor2D,
    Anchor3D,
    Annotation,
    AnnotationFilter,
    AnnotationKind,
)
from cybercanon.domain.identity import Actor, ActorId, ActorKind, AgentId, Role
from cybercanon.domain.triage import PromotionTarget
from views_world import MAPPING, PROJECT, RAFA, RAFA_SUBJECT, SCOUT, SCOUT_DIR, RepositorySpecStore

SCOUT_SPEC = f"{SCOUT_DIR}/asset.yaml"
FRONT = "front"
SIDE = "side"
BACK = "back"

ANA_SUBJECT = "auth|ana"
DANA_SUBJECT = "auth|dana"
NOBODY_SUBJECT = "auth|nobody"

ANA = GitAuthor(name="Ana", email="ana@cyberdyne.com")
DANA = GitAuthor(name="Dana", email="dana@cyberdyne.com")
NOBODY = GitAuthor(name="Sam", email="sam@cyberdyne.com")

PEOPLE = ActorMapping(
    bindings=(
        *MAPPING.bindings,
        ActorBinding(subject=ANA_SUBJECT, display_name="Ana", emails=(ANA.email,)),
        ActorBinding(
            subject=DANA_SUBJECT,
            display_name="Dana",
            emails=(DANA.email,),
            default_role="ART_DIRECTOR",
        ),
        ActorBinding(subject=NOBODY_SUBJECT, display_name="Sam", emails=(NOBODY.email,)),
    )
)
"""Four people: an artist, a second artist, an art director and an outsider."""

AUTHORED = """\
schema_version: 1
id: mech_scout
name: Scout Mech      # renaming this is safe; the id is what everything refers to
status: modeling

# engineering fixed these at the kick-off
constraints:
  tri_budget: 12000
  lods: [8000, 4000]

concept:
  views: [front, side, back]
"""
"""A hand-authored specification, comments and all — what a round trip must survive."""


def a_spec(views: Sequence[str] = (FRONT, SIDE, BACK), **extra: str) -> bytes:
    """A specification declaring these views, and whatever else a test needs."""
    declared = ", ".join(views)
    lines = [
        "schema_version: 1",
        f"id: {SCOUT}",
        "name: Scout Mech",
        "status: modeling",
        *(f"{key}: {value}" for key, value in extra.items()),
        "concept:",
        f"  views: [{declared}]",
    ]
    return ("\n".join(lines) + "\n").encode()


def a_person(
    subject: str = RAFA_SUBJECT,
    *,
    roles: tuple[Role, ...] = (),
    project: str = PROJECT,
    name: str = "",
) -> Actor:
    """One resolved person entitled to this project, holding whatever roles."""
    return Actor(
        id=ActorId(subject),
        display_name=name or subject,
        roles=roles,
        projects=(project,),
    )


RAFA_ACTOR = a_person(RAFA_SUBJECT, name="Rafa")
ANA_ACTOR = a_person(ANA_SUBJECT, name="Ana")
DIRECTOR = a_person(DANA_SUBJECT, roles=(Role.ART_DIRECTOR,), name="Dana")
OUTSIDER = a_person(NOBODY_SUBJECT, name="Sam")

WORKER_SUBJECT = "service|worker"
WORKER = GitAuthor(name="canon automation", email="automation@cybercanon.invalid")
AUTOMATION_ACTOR = Actor(
    id=ActorId(WORKER_SUBJECT),
    display_name="worker",
    kind=ActorKind.AUTOMATION,
    projects=(PROJECT,),
)
"""A credential with no person behind it, and a git identity of its own.

The validation worker has exactly this shape (G2), so it is the honest way to
ask whether an operation that requires a person refuses one: an automation with
*no* mapping would be refused for the mapping and the question would never be
reached.
"""

AUTHORS = {
    RAFA_SUBJECT: RAFA,
    ANA_SUBJECT: ANA,
    DANA_SUBJECT: DANA,
    NOBODY_SUBJECT: NOBODY,
    WORKER_SUBJECT: WORKER,
}


def an_anchor(view: str = FRONT, u: float = 0.25, v: float = 0.4) -> Anchor2D:
    return Anchor2D(view=view, u=u, v=v)


def a_part_anchor(part: str = "SM_MechScout_Shoulder_L") -> Anchor3D:
    return Anchor3D(part=part)


@dataclass
class Threads:
    """Every port one annotation operation touches, and the seams a scenario needs."""

    host: InMemoryRepositoryHost
    spec_store: RepositorySpecStore
    mapping: ActorMapping = PEOPLE
    moment: datetime = field(default_factory=lambda: datetime(2026, 9, 22, 10, 0, tzinfo=UTC))
    parts: tuple[str, ...] | None = None
    notes: dict[str, Any] = field(default_factory=dict)

    # -- the clock -------------------------------------------------------

    def clock(self) -> datetime:
        """A clock that advances a second per reading, so ages are deterministic."""
        self.moment += timedelta(seconds=1)
        return self.moment

    def age(self, seconds: int) -> None:
        """Move the clock forward, so one annotation is older than another."""
        self.moment += timedelta(seconds=seconds)

    # -- the workspace ---------------------------------------------------

    def workspace(
        self,
        actor: Actor = RAFA_ACTOR,
        *,
        asset_id: str = SCOUT,
        via: AgentId | None = None,
        mapped: bool = True,
    ) -> Workspace:
        return Workspace(
            project=PROJECT,
            asset_id=asset_id,
            repository_host=self.host,
            spec_store=self.spec_store,
            actor=actor,
            author=AUTHORS.get(actor.subject) if mapped else None,
            via=via,
            agent=str(via) if via else "",
            clock=self.clock,
            parts=self.parts,
        )

    # -- operations ------------------------------------------------------

    def create(
        self,
        annotation_id: str = "an_1",
        *,
        actor: Actor = RAFA_ACTOR,
        asset_id: str = SCOUT,
        kind: AnnotationKind = AnnotationKind.ART_DIRECTION,
        text: str = "the pauldron reads as a backpack at 15 m",
        anchor: Anchor | None = None,
        strokes: tuple = (),
        via: AgentId | None = None,
        mapped: bool = True,
    ) -> Result:
        return create_annotation(
            self.workspace(actor, asset_id=asset_id, via=via, mapped=mapped),
            Draft(
                id=annotation_id,
                kind=kind,
                text=text,
                anchor=an_anchor() if anchor is None else anchor,
                strokes=strokes,
            ),
        )

    def reply(
        self,
        annotation_id: str = "an_1",
        reply_id: str = "re_1",
        text: str = "agreed, it needs a harder edge",
        *,
        actor: Actor = ANA_ACTOR,
        via: AgentId | None = None,
    ) -> Result:
        return reply_to_annotation(self.workspace(actor, via=via), annotation_id, reply_id, text)

    def edit(self, annotation_id: str = "an_1", text: str = "reworded", *, actor=RAFA_ACTOR):
        return edit_annotation(self.workspace(actor), annotation_id, text)

    def withdraw(self, annotation_id: str = "an_1", *, actor: Actor = RAFA_ACTOR):
        return delete_annotation(self.workspace(actor), annotation_id)

    def move(self, annotation_id: str = "an_1", anchor: Anchor | None = None, *, actor=RAFA_ACTOR):
        return move_annotation(
            self.workspace(actor), annotation_id, anchor or an_anchor(u=0.6, v=0.6)
        )

    def reanchor(
        self,
        annotation_id: str = "an_1",
        anchor: Anchor | None = None,
        *,
        actor: Actor = RAFA_ACTOR,
        via: AgentId | None = None,
        mapped: bool = True,
    ):
        """A person rescues an orphan by naming the subject it belongs on now."""
        return reanchor_annotation(
            self.workspace(actor, via=via, mapped=mapped),
            annotation_id,
            anchor or a_part_anchor(),
        )

    def resolve(self, annotation_id: str = "an_1", *, actor: Actor = RAFA_ACTOR, conclusion=""):
        return resolve_annotation(self.workspace(actor), annotation_id, conclusion)

    def reopen(self, annotation_id: str = "an_1", *, actor: Actor = RAFA_ACTOR):
        return reopen_annotation(self.workspace(actor), annotation_id)

    def promote(
        self,
        annotation_id: str = "an_1",
        rule: str = "the lens glow is always emissive",
        target: PromotionTarget | None = PromotionTarget.SILHOUETTE_RULES,
        *,
        actor: Actor = DIRECTOR,
        via: AgentId | None = None,
    ):
        return promote_annotation(self.workspace(actor, via=via), annotation_id, rule, target)

    def listed(
        self,
        annotation_filter: AnnotationFilter | None = None,
        *,
        actor: Actor = RAFA_ACTOR,
        asset_id: str = SCOUT,
        mapped: bool = True,
    ):
        return list_annotations(
            self.workspace(actor, asset_id=asset_id, mapped=mapped), annotation_filter
        )

    def exits(self, annotation_id: str = "an_1", *, actor: Actor = RAFA_ACTOR):
        return available_exits(self.workspace(actor), annotation_id)

    def queue(self, **filters: Any):
        return list_triage_queue(
            PROJECT,
            spec_store=self.spec_store,
            repository_host=self.host,
            clock=self.clock,
            **filters,
        )

    # -- what landed -----------------------------------------------------

    def annotations(self, asset_id: str = SCOUT) -> tuple[Annotation, ...]:
        """What the repository holds for this asset — never what a cache remembers."""
        listing = self.listed(AnnotationFilter.every(), asset_id=asset_id)
        assert isinstance(listing, Ok), listing
        return listing.value.annotations

    def annotation(self, annotation_id: str = "an_1", asset_id: str = SCOUT) -> Annotation | None:
        return next(
            (entry for entry in self.annotations(asset_id) if entry.id == annotation_id), None
        )

    def spec_text(self, path: str = SCOUT_SPEC) -> str:
        """The specification file as the branch holds it, verbatim."""
        return self.files()[path].decode("utf-8")

    def files(self) -> dict[str, bytes]:
        return self.host.remote_files(PROJECT)

    def commits(self):
        return self.host.commits(PROJECT)

    def messages(self) -> tuple[str, ...]:
        return tuple(commit.message for commit in self.commits())

    # -- seams -----------------------------------------------------------

    def replace_spec(self, content: bytes, path: str = SCOUT_SPEC) -> None:
        """Somebody edited the specification outside this service, and we fetched.

        Two steps rather than one, because they are two facts: the branch moved,
        and this working copy has since confirmed it. A test that pushed without
        fetching would be asserting against a revision nobody is serving.
        """
        self.host.push_to_remote(PROJECT, path, content)
        self.host.fetch(PROJECT, confirmed_at=self.clock())

    def remove_view(self, slot: str = BACK, path: str = SCOUT_SPEC) -> None:
        """Take a view out of the specification, leaving everything else as it is.

        The annotations anchored to it stay in the file, which is the whole of
        the orphan case: *"WHEN that view is removed from the asset THEN those
        annotations SHALL be reported as orphaned."*
        """
        current = self.files()[path].decode("utf-8")
        self.replace_spec(
            current.replace(f", {slot}]", "]").replace(f"{slot}, ", "").encode("utf-8"), path
        )

    def restore(self) -> None:
        """Re-obtain a working copy after a seam made the remote unreachable."""
        self.host.clone(PROJECT)

    def someone_else_writes(self, path: str = SCOUT_SPEC, content: bytes | None = None) -> None:
        """A second writer lands a commit between this caller's read and its write."""
        self.host.commit(
            PROJECT,
            [_change(path, content or (self.files()[path] + b"# and another hand\n"))],
            author=ANA,
            message="a second writer",
        )
        self.host.push(PROJECT)


def _change(path: str, content: bytes):
    from cybercanon.application.ports.repository_host import FileChange

    return FileChange(path=path, content=content)


def a_world(files: dict[str, bytes] | None = None, *, mapping: ActorMapping = PEOPLE) -> Threads:
    """A cloned project holding whatever a test asked for, and nothing else."""
    host = InMemoryRepositoryHost()
    host.add_project(PROJECT, dict(files or {}))
    host.clone(PROJECT)
    return Threads(host=host, spec_store=RepositorySpecStore(host=host, mapping=mapping))


def with_asset(spec: bytes | None = None, **files: bytes) -> Threads:
    """A project whose `mech_scout` declares three views, plus any extra files."""
    return a_world({SCOUT_SPEC: spec if spec is not None else a_spec(), **files})


__all__ = [
    "ANA",
    "ANA_ACTOR",
    "ANA_SUBJECT",
    "AUTHORED",
    "AUTOMATION_ACTOR",
    "BACK",
    "DANA_SUBJECT",
    "DIRECTOR",
    "FRONT",
    "NOBODY_SUBJECT",
    "OUTSIDER",
    "PEOPLE",
    "PROJECT",
    "RAFA",
    "RAFA_ACTOR",
    "RAFA_SUBJECT",
    "SCOUT",
    "SCOUT_SPEC",
    "SIDE",
    "Threads",
    "a_part_anchor",
    "a_person",
    "a_spec",
    "a_world",
    "an_anchor",
    "with_asset",
]
