"""Tasks 2.2 to 2.11 — the write path, against a real repository and a real file.

The arrangement is `tests/annotations_world.py`: an in-memory repository host
holding real `asset.yaml` bytes, the adapter's own comment-preserving reader and
writer over them, and the use cases on top. There is no index anywhere in it,
which is the point — *"no annotation is readable only from the index"* is a
property of what these use cases can reach, not of what they happen to call.
"""

from __future__ import annotations

from dataclasses import replace

import pytest

from annotations_world import (
    ANA_ACTOR,
    AUTHORED,
    BACK,
    DIRECTOR,
    FRONT,
    OUTSIDER,
    PROJECT,
    RAFA_ACTOR,
    RAFA_SUBJECT,
    SCOUT,
    SCOUT_SPEC,
    SIDE,
    Threads,
    a_part_anchor,
    a_person,
    a_spec,
    a_world,
    an_anchor,
    with_asset,
)
from cybercanon.application.results import Ok
from cybercanon.application.testing.outcomes import ran, refused
from cybercanon.application.use_cases.compile_spec import compile_spec
from cybercanon.domain.annotations import (
    Anchor2D,
    AnnotationFilter,
    AnnotationKind,
    AnnotationState,
    Stroke,
)
from cybercanon.domain.identity import AgentId, Role
from cybercanon.domain.triage import PromotionTarget

pytestmark = pytest.mark.unit

AGENT = AgentId("blender-agent")


@pytest.fixture
def threads() -> Threads:
    """A project whose `mech_scout` declares three views and holds no feedback."""
    return with_asset()


# --------------------------------------------------------------------------
# 2.2 — every operation writes through the repository and refuses per policy
# --------------------------------------------------------------------------


def test_a_created_annotation_is_in_the_specification_file(threads: Threads) -> None:
    ran(threads.create())

    assert "the pauldron reads as a backpack" in threads.spec_text()
    assert threads.annotation("an_1") is not None


def test_a_created_annotation_records_the_person_from_the_credential(
    threads: Threads,
) -> None:
    recorded = ran(threads.create()).annotation

    assert recorded.author == RAFA_SUBJECT
    assert recorded.via == ""
    assert recorded.created_at


def test_a_reply_lands_in_the_thread_and_in_the_file(threads: Threads) -> None:
    ran(threads.create())

    ran(threads.reply())

    thread = threads.annotation("an_1")
    assert thread is not None
    assert [entry.id for entry in thread.replies] == ["re_1"]
    assert "agreed, it needs a harder edge" in threads.spec_text()


def test_editing_another_persons_annotation_is_refused_and_changes_nothing(
    threads: Threads,
) -> None:
    ran(threads.create())

    outcome = threads.edit("an_1", "not what they said", actor=ANA_ACTOR)

    assert refused(outcome).kind.value == "forbidden"
    thread = threads.annotation("an_1")
    assert thread is not None
    assert thread.text == "the pauldron reads as a backpack at 15 m"


def test_deleting_a_thread_that_has_replies_is_refused(threads: Threads) -> None:
    ran(threads.create())
    ran(threads.reply())

    outcome = threads.withdraw("an_1")

    assert "resolve it or promote it" in refused(outcome).message
    assert threads.annotation("an_1") is not None


def test_deleting_an_untouched_annotation_removes_it_everywhere(threads: Threads) -> None:
    ran(threads.create())

    ran(threads.withdraw("an_1"))

    assert threads.annotation("an_1") is None
    assert "pauldron" not in threads.spec_text()


def test_creating_without_write_access_is_refused_but_reading_still_works(
    threads: Threads,
) -> None:
    """*"A read-only person is refused; reading the annotations still succeeds."*"""
    ran(threads.create())

    assert refused(threads.create("an_2", mapped=False)).kind.value == "forbidden"
    assert ran(threads.listed(mapped=False)).annotations[0].id == "an_1"


def test_a_person_with_no_mapped_git_identity_is_refused_naming_the_file(
    threads: Threads,
) -> None:
    outcome = threads.create(mapped=False)

    assert ".canon/actors.yaml" in refused(outcome).message


def test_an_engineer_may_raise_art_direction_feedback(threads: Threads) -> None:
    """*"No discipline SHALL be required in order to raise feedback of any kind."*"""
    engineer = a_person("auth|rafa", roles=(Role.ENGINEER,))

    recorded = ran(threads.create(actor=engineer, kind=AnnotationKind.ART_DIRECTION))

    assert recorded.annotation.kind is AnnotationKind.ART_DIRECTION


def test_an_anchor_naming_an_absent_view_is_refused_naming_it(threads: Threads) -> None:
    outcome = threads.create(anchor=Anchor2D(view="three_quarter", u=0.5, v=0.5))

    assert "three_quarter" in refused(outcome).message
    assert threads.annotations() == ()


def test_a_view_the_repository_holds_but_the_specification_does_not_declare_is_anchorable() -> None:
    """Ingestion writes a view as a file without touching an authored field."""
    world = a_world(
        {
            SCOUT_SPEC: a_spec(views=()),
            f"characters/{SCOUT}/concept/front.png": b"not really a png",
        }
    )

    recorded = ran(world.create(anchor=an_anchor(FRONT)))

    assert recorded.annotation.durable_key == FRONT


def test_a_text_edit_leaves_the_anchor_untouched(threads: Threads) -> None:
    ran(threads.create())

    ran(threads.edit("an_1", "the pauldron is too round"))

    thread = threads.annotation("an_1")
    assert thread is not None
    assert thread.target == an_anchor()
    assert thread.edited_at


def test_a_move_is_attributed_and_visible(threads: Threads) -> None:
    ran(threads.create())

    ran(threads.move("an_1", an_anchor(FRONT, 0.6, 0.6)))

    thread = threads.annotation("an_1")
    assert thread is not None
    assert thread.target == an_anchor(FRONT, 0.6, 0.6)
    assert thread.moved_by == RAFA_SUBJECT
    assert thread.moved_at


def test_only_the_author_may_move_their_annotation(threads: Threads) -> None:
    ran(threads.create())

    outcome = threads.move("an_1", an_anchor(SIDE, 0.5, 0.5), actor=DIRECTOR)

    assert refused(outcome).kind.value == "forbidden"


def test_an_annotation_cannot_be_moved_between_anchor_forms(threads: Threads) -> None:
    ran(threads.create())

    outcome = threads.move("an_1", a_part_anchor())

    assert "between anchor forms" in refused(outcome).message


def test_an_empty_annotation_is_refused(threads: Threads) -> None:
    assert refused(threads.create(text="   ")).kind.value == "invalid"


def test_freehand_marks_travel_with_the_annotation(threads: Threads) -> None:
    drawn = (Stroke(((0.1, 0.1), (0.2, 0.2), (0.3, 0.15))),)

    recorded = ran(threads.create(strokes=drawn))

    assert recorded.annotation.strokes
    assert "strokes" in threads.spec_text()
    ran(threads.resolve("an_1"))
    thread = threads.annotation("an_1")
    assert thread is not None
    assert thread.strokes == ()


# --------------------------------------------------------------------------
# 2.3 — attribution comes from the credential, and from nothing else
# --------------------------------------------------------------------------


def test_a_submitted_author_field_is_ignored(threads: Threads) -> None:
    """The draft has no author member at all, which is how the rule stays true.

    A request that declares a different person cannot even be expressed: the
    use case takes a :class:`~...annotations.Draft` whose fields are the kind,
    the text, the anchor and the marks, and the acting identity arrives on the
    workspace from the verified credential.
    """
    from cybercanon.application.use_cases.annotations import Draft

    assert {"author", "actor", "role", "via", "attribution"}.isdisjoint(Draft.__dataclass_fields__)
    assert ran(threads.create()).annotation.author == RAFA_SUBJECT


def test_an_agent_originated_write_records_both_the_person_and_the_agent(
    threads: Threads,
) -> None:
    recorded = ran(threads.create(via=AGENT)).annotation

    assert recorded.author == RAFA_SUBJECT
    assert recorded.via == str(AGENT)
    assert recorded.attribution == f"{RAFA_SUBJECT}, via {AGENT}"


def test_an_agent_reply_is_attributed_to_both_as_well(threads: Threads) -> None:
    ran(threads.create())

    ran(threads.reply(via=AGENT))

    thread = threads.annotation("an_1")
    assert thread is not None
    assert thread.replies[0].attribution.endswith(f", via {AGENT}")


def test_the_commit_records_the_agent_that_performed_it(threads: Threads) -> None:
    ran(threads.create(via=AGENT))

    assert any("Performed-by: blender-agent" in message for message in threads.messages())


# --------------------------------------------------------------------------
# 2.4 — the base-revision conflict path
# --------------------------------------------------------------------------


def _interfere(world: Threads, times: int = 1) -> None:
    """Land somebody else's commit between this caller's read and its write."""
    original = world.spec_store.edited
    landed: list[int] = []

    def edited(document, asset):
        content = original(document, asset)
        if len(landed) < times:
            landed.append(1)
            world.someone_else_writes()
        return content

    world.spec_store.edited = edited  # type: ignore[method-assign]


def test_two_concurrent_creates_on_one_asset_both_persist(threads: Threads) -> None:
    """*"Applying the operation rather than the file means two people both succeed."*"""
    ran(threads.create("an_1"))
    original = threads.spec_store.edited
    landed: list[int] = []

    def edited(document, asset):
        content = original(document, asset)
        if not landed:
            landed.append(1)
            ran(threads.create("an_3", actor=ANA_ACTOR, text="and the hip plate"))
        return content

    threads.spec_store.edited = edited  # type: ignore[method-assign]
    ran(threads.create("an_2", text="the knee reads as a joint"))

    assert {entry.id for entry in threads.annotations()} == {"an_1", "an_2", "an_3"}


def test_a_second_conflict_is_reported_with_the_submitted_text_preserved(
    threads: Threads,
) -> None:
    _interfere(threads, times=2)

    outcome = threads.create("an_1", text="the pauldron reads as a backpack at 15 m")

    failure = refused(outcome)
    assert failure.kind.value == "conflict"
    assert "the text was kept" in failure.message
    assert threads.annotations() == ()


# --------------------------------------------------------------------------
# 2.5 — idempotency on the client-generated identifier
# --------------------------------------------------------------------------


def test_a_retried_identical_create_produces_exactly_one_annotation(
    threads: Threads,
) -> None:
    ran(threads.create("an_1"))

    second = ran(threads.create("an_1"))

    assert len(threads.annotations()) == 1
    assert second.committed is False
    assert len(threads.commits()) == 1  # the create, and nothing for the retry


def test_a_retried_reply_produces_exactly_one_reply(threads: Threads) -> None:
    ran(threads.create())
    ran(threads.reply("an_1", "re_1"))

    ran(threads.reply("an_1", "re_1"))

    thread = threads.annotation("an_1")
    assert thread is not None
    assert len(thread.replies) == 1


# --------------------------------------------------------------------------
# 2.6 — one listing, both anchor forms, the same fields
# --------------------------------------------------------------------------


def test_a_mixed_anchor_asset_lists_both_forms_through_one_filter(
    threads: Threads,
) -> None:
    threads.parts = ("SM_MechScout_Shoulder_L",)
    ran(threads.create("an_1", kind=AnnotationKind.TECHNICAL))
    ran(threads.create("an_2", kind=AnnotationKind.TECHNICAL, anchor=a_part_anchor()))

    listing = ran(threads.listed(AnnotationFilter.of(kinds=(AnnotationKind.TECHNICAL,))))

    assert {entry.id for entry in listing.annotations} == {"an_1", "an_2"}
    assert len({type(entry.target) for entry in listing.annotations}) == 2


def test_the_listing_reports_what_the_filter_is_hiding(threads: Threads) -> None:
    ran(threads.create("an_1", kind=AnnotationKind.ART_DIRECTION))
    ran(threads.create("an_2", kind=AnnotationKind.TECHNICAL, text="the pivot is off centre"))

    listing = ran(threads.listed(AnnotationFilter.of(kinds=(AnnotationKind.TECHNICAL,))))

    assert [entry.id for entry in listing.annotations] == ["an_2"]
    assert listing.hidden == 1


def test_an_annotation_on_a_removed_view_is_listed_as_an_orphan_and_never_placed() -> None:
    world = with_asset()
    ran(world.create("an_1", anchor=an_anchor(BACK)))
    world.remove_view(BACK)

    listing = ran(world.listed(AnnotationFilter.every()))

    assert [entry.subject for entry in listing.orphaned] == [BACK]
    assert listing.placeable == ()


# --------------------------------------------------------------------------
# 2.7 — resolution and reopening
# --------------------------------------------------------------------------


def test_resolving_excludes_the_annotation_from_the_compiled_briefing(
    threads: Threads,
) -> None:
    ran(threads.create())
    before = _briefing(threads)

    ran(threads.resolve("an_1", conclusion="fixed in pass 3"))

    assert "pauldron" in before
    assert "pauldron" not in _briefing(threads)


def test_reopening_returns_it_to_the_open_set_attributed(threads: Threads) -> None:
    ran(threads.create())
    ran(threads.resolve("an_1"))

    ran(threads.reopen("an_1"))

    thread = threads.annotation("an_1")
    assert thread is not None
    assert thread.state is AnnotationState.OPEN
    assert thread.closed_by == RAFA_SUBJECT
    assert "pauldron" in _briefing(threads)


def test_reopening_a_promoted_annotation_is_refused(threads: Threads) -> None:
    ran(threads.create())
    ran(threads.promote("an_1"))

    outcome = threads.reopen("an_1", actor=DIRECTOR)

    assert "now a rule" in refused(outcome).message


def test_a_second_exit_is_refused_while_the_first_stands(threads: Threads) -> None:
    ran(threads.create())
    ran(threads.resolve("an_1"))

    outcome = threads.promote("an_1")

    assert "already resolved" in refused(outcome).message


def test_an_uninvolved_person_may_not_resolve(threads: Threads) -> None:
    ran(threads.create())

    outcome = threads.resolve("an_1", actor=OUTSIDER)

    assert refused(outcome).kind.value == "forbidden"
    thread = threads.annotation("an_1")
    assert thread is not None
    assert thread.is_open


def test_an_orphan_can_still_take_an_exit() -> None:
    world = with_asset()
    ran(world.create("an_1", anchor=an_anchor(BACK)))
    world.remove_view(BACK)

    ran(world.resolve("an_1"))

    thread = world.annotation("an_1")
    assert thread is not None
    assert thread.state is AnnotationState.RESOLVED


# --------------------------------------------------------------------------
# 2.8 — promotion is one validated atomic operation
# --------------------------------------------------------------------------


def test_a_promotion_lands_the_rule_and_retires_the_annotation_in_one_commit(
    threads: Threads,
) -> None:
    ran(threads.create())
    before = len(threads.commits())

    recorded = ran(threads.promote("an_1", "the lens glow is always emissive"))

    assert len(threads.commits()) == before + 1
    assert "the lens glow is always emissive" in threads.spec_text()
    assert recorded.annotation.state is AnnotationState.PROMOTED


def test_a_promotion_producing_an_invalid_specification_is_refused_with_the_violations() -> None:
    """*"The system SHALL NOT write a specification file that its own validator rejects."*"""
    world = with_asset(AUTHORED.encode())
    ran(world.create())
    before = world.spec_text()

    outcome = world.promote("an_1", "tri_budget: 4000", PromotionTarget.CONSTRAINTS)

    failure = refused(outcome)
    assert "lod" in failure.message.lower()
    assert world.spec_text() == before
    thread = world.annotation("an_1")
    assert thread is not None
    assert thread.is_open


def test_a_promotion_with_no_destination_is_refused_naming_both(threads: Threads) -> None:
    ran(threads.create())

    outcome = threads.promote("an_1", "a rule", target=None)

    failure = refused(outcome)
    assert "constraints" in failure.message
    assert "concept.silhouette_rules" in failure.message


def test_a_failed_write_leaves_the_annotation_open_and_no_partial_rule(
    threads: Threads,
) -> None:
    ran(threads.create())
    before = threads.spec_text()
    threads.host.make_unreachable(PROJECT, "the remote is down")

    outcome = threads.promote("an_1")

    assert refused(outcome).kind.value == "unavailable"
    threads.host.make_reachable(PROJECT)
    threads.restore()
    assert threads.spec_text() == before
    thread = threads.annotation("an_1")
    assert thread is not None
    assert thread.is_open


def test_an_artist_attempting_promotion_is_refused_naming_the_role(
    threads: Threads,
) -> None:
    ran(threads.create())

    outcome = threads.promote("an_1", actor=RAFA_ACTOR)

    assert "ART_DIRECTOR" in refused(outcome).message
    thread = threads.annotation("an_1")
    assert thread is not None
    assert thread.is_open


def test_a_refused_promoter_may_still_resolve(threads: Threads) -> None:
    ran(threads.create())
    refused(threads.promote("an_1", actor=RAFA_ACTOR))

    ran(threads.resolve("an_1"))

    thread = threads.annotation("an_1")
    assert thread is not None
    assert thread.state is AnnotationState.RESOLVED


# --------------------------------------------------------------------------
# 2.9 — the briefing never grows from settled annotations
# --------------------------------------------------------------------------


def _briefing(world: Threads, asset_id: str = SCOUT) -> str:
    """The compiled `art-spec.md`, through the same use case every surface uses."""
    compiled = compile_spec(SCOUT_SPEC, spec_store=world.spec_store)
    assert isinstance(compiled, Ok), compiled
    return compiled.value.text


def test_settling_twenty_annotations_leaves_the_briefing_byte_identical(
    threads: Threads,
) -> None:
    """The scenario that decides whether this system degrades with use."""
    before = _briefing(threads)

    for index in range(20):
        ran(threads.create(f"an_{index}", text=f"issue {index}"))
    for index in range(20):
        ran(threads.resolve(f"an_{index}"))

    assert _briefing(threads) == before


def test_a_promotion_adds_a_rule_and_not_a_thread(threads: Threads) -> None:
    ran(threads.create(text="the lens glow should always be emissive"))
    for index in range(6):
        ran(threads.reply("an_1", f"re_{index}", f"reply {index}"))

    ran(threads.promote("an_1", "the lens glow is always emissive"))

    briefing = _briefing(threads)
    assert "the lens glow is always emissive" in briefing
    assert "reply 0" not in briefing
    assert "should always be emissive" not in briefing


# --------------------------------------------------------------------------
# 2.10 — the queue, from the repository alone
# --------------------------------------------------------------------------


def _a_project() -> Threads:
    """Two assets: one with four art-direction annotations, one with a single."""
    world = a_world(
        {
            SCOUT_SPEC: a_spec(),
            "vehicles/mule/asset.yaml": (
                b"schema_version: 1\nid: mule\nname: Mule\nconcept:\n  views: [front]\n"
            ),
        }
    )
    for index in range(4):
        ran(world.create(f"an_{index}", text=f"scout issue {index}"))
    ran(
        world.create(
            "mu_1",
            asset_id="mule",
            text="the mule tailgate reads as a door",
            anchor=an_anchor(FRONT),
        )
    )
    return world


def test_the_queue_is_produced_with_no_index_anywhere_in_reach() -> None:
    """*"WHEN every derived index has been deleted THEN it SHALL be produced from
    the repository."* There is no index in this arrangement at all."""
    queue = ran(_a_project().queue())

    assert queue.size == 5


def test_recurring_feedback_rises_above_isolated_feedback() -> None:
    queue = ran(_a_project().queue())

    assert queue.entries[0].asset == SCOUT
    assert queue.entries[0].same_kind_on_asset == 4
    assert queue.entries[-1].same_kind_on_asset == 1


def test_every_entry_reports_its_counts_its_replies_and_its_age() -> None:
    queue = ran(_a_project().queue())

    entry = queue.entries[0]
    assert entry.same_kind_on_asset == 4
    assert entry.same_kind_in_project == 5
    assert entry.replies == 0
    assert entry.age_seconds >= 0.0


def test_the_queue_is_filterable_by_kind() -> None:
    world = _a_project()
    ran(world.create("tech_1", kind=AnnotationKind.TECHNICAL, text="the pivot is off centre"))

    queue = ran(world.queue(kinds=(AnnotationKind.TECHNICAL,)))

    assert [entry.id for entry in queue.entries] == ["tech_1"]


def test_the_queue_is_filterable_by_asset() -> None:
    queue = ran(_a_project().queue(asset_id="mule"))

    assert {entry.asset for entry in queue.entries} == {"mule"}


def test_a_settled_annotation_leaves_the_queue() -> None:
    world = _a_project()
    ran(world.resolve("an_0"))

    queue = ran(world.queue())

    assert "an_0" not in {entry.id for entry in queue.entries}


# --------------------------------------------------------------------------
# 2.11 — promotion is unreachable from an automated caller
# --------------------------------------------------------------------------


def test_an_art_directors_agent_is_refused_promotion(threads: Threads) -> None:
    ran(threads.create())

    outcome = threads.promote("an_1", actor=DIRECTOR, via=AGENT)

    assert refused(outcome).kind.value == "forbidden"
    assert "requires a person" in refused(outcome).message
    assert "silhouette_rules" not in threads.spec_text()


def test_the_asset_durable_rules_are_unchanged_after_a_refused_agent_promotion(
    threads: Threads,
) -> None:
    ran(threads.create())
    before = threads.spec_text()

    refused(threads.promote("an_1", actor=DIRECTOR, via=AGENT))

    assert threads.spec_text() == before


# --------------------------------------------------------------------------
# 3.5 — nothing is readable only from a derived store
# --------------------------------------------------------------------------


def test_every_thread_survives_reading_the_repository_from_scratch(
    threads: Threads,
) -> None:
    """There is no index here to delete; the assertion is that none is needed."""
    ran(threads.create(strokes=(Stroke(((0.1, 0.1), (0.4, 0.4))),)))
    ran(threads.reply())
    before = threads.annotations()

    rebuilt = a_world(threads.files()).annotations()

    assert rebuilt == before
    assert rebuilt[0].strokes == before[0].strokes
    assert rebuilt[0].replies == before[0].replies


def test_a_promotion_survives_the_same_rebuild(threads: Threads) -> None:
    ran(threads.create())
    ran(threads.promote("an_1"))

    rebuilt = a_world(threads.files())

    thread = rebuilt.annotation("an_1")
    assert thread is not None
    assert thread.state is AnnotationState.PROMOTED
    assert "the lens glow is always emissive" in rebuilt.spec_text()


def test_the_effective_specification_of_a_rebuilt_asset_is_unchanged(
    threads: Threads,
) -> None:
    ran(threads.create())
    listing = ran(threads.listed(AnnotationFilter.every()))

    rebuilt = ran(a_world(threads.files()).listed(AnnotationFilter.every()))

    assert replace(rebuilt, revision=listing.revision) == listing
