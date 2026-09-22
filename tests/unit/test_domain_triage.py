"""Tasks 1.5 to 1.7 — the two exits, the promotion transformation and the queue.

This is the heart of the product as a pure function: who may take each exit, what
a promotion writes, and the ordering that lifts feedback repeating across a
project above a one-off. None of it touches a file, and the promotion case that
matters most — *"no path produces the rule without retiring the annotation"* — is
asserted by there being one function with one return value to assert about.
"""

from __future__ import annotations

from dataclasses import replace

import pytest

from cybercanon.domain.annotations import (
    Anchor2D,
    Anchor3D,
    Annotation,
    AnnotationKind,
    AnnotationState,
)
from cybercanon.domain.asset import Asset, AssetId
from cybercanon.domain.concept import Concept
from cybercanon.domain.constraints import Constraints
from cybercanon.domain.identity import Actor, ActorId, AgentId, Role, automation_actor
from cybercanon.domain.policy import HUMAN_ONLY, Operation, Subject, decide
from cybercanon.domain.spec_checks import RULE_LOD0_OVER_TRI_BUDGET, check_asset
from cybercanon.domain.triage import (
    EXITS,
    FIELDS,
    Declaration,
    Exit,
    PromotionRefused,
    PromotionTarget,
    TriageEntry,
    exits_for,
    parse_rule,
    promote,
    same_kind_counts,
    triage_order,
)

pytestmark = pytest.mark.unit

PROJECT = "cyberdyne-game"
RAFA = ActorId("auth|rafa")
ANA = ActorId("auth|ana")
DANA = ActorId("auth|dana")

RULE = "the lens glow is always emissive"


def a_person(*roles: Role, actor_id: ActorId = RAFA) -> Actor:
    return Actor(id=actor_id, display_name=str(actor_id), roles=roles, projects=(PROJECT,))


def an_annotation(
    identifier: str = "an_1",
    kind: AnnotationKind = AnnotationKind.ART_DIRECTION,
    *,
    state: AnnotationState = AnnotationState.OPEN,
    part: str = "",
    **fields: object,
) -> Annotation:
    target = Anchor3D(part=part) if part else Anchor2D(view="front", u=0.25, v=0.4)
    return Annotation(
        id=identifier,
        author=str(RAFA),
        kind=kind,
        text=RULE,
        target=target,
        state=state,
        **fields,  # type: ignore[arg-type]
    )


def an_asset(*annotations: Annotation, **fields: object) -> Asset:
    return Asset(
        id=AssetId("mech_scout"),
        name="Scout Mech",
        annotations=annotations,
        **fields,  # type: ignore[arg-type]
    )


# --------------------------------------------------------------------------
# Exactly two exits, and no third
# --------------------------------------------------------------------------


def test_exactly_two_exits_are_offered_for_an_open_annotation() -> None:
    assert exits_for(an_annotation()) == EXITS
    assert len(EXITS) == 2
    assert {str(exit_) for exit_ in EXITS} == {"promote", "resolve"}


@pytest.mark.parametrize("state", [AnnotationState.RESOLVED, AnnotationState.PROMOTED], ids=str)
def test_an_annotation_that_took_an_exit_is_offered_none(state: AnnotationState) -> None:
    assert exits_for(an_annotation(state=state)) == ()


def test_the_exit_set_is_closed() -> None:
    """A third terminal state would have to be written down here first."""
    assert {member.value for member in Exit} == {"promote", "resolve"}


# --------------------------------------------------------------------------
# 1.5 — who may take which exit, every role against every exit
# --------------------------------------------------------------------------

ROLES = (None, Role.ARTIST, Role.DESIGNER, Role.ENGINEER, Role.ART_DIRECTOR)


def _subject(author: ActorId = RAFA, owner: ActorId | None = None) -> Subject:
    return Subject(project=PROJECT, author=author, discipline_owner=owner)


@pytest.mark.parametrize("role", ROLES, ids=lambda role: str(role or "no role"))
def test_only_an_art_director_may_promote(role: Role | None) -> None:
    actor = a_person(*(role,) if role else (), actor_id=ANA)

    decision = decide(actor, Operation.PROMOTE_TO_RULE, _subject())

    assert decision.allowed is (role is Role.ART_DIRECTOR)


@pytest.mark.parametrize("role", ROLES, ids=lambda role: str(role or "no role"))
def test_a_refused_promoter_may_still_resolve_their_own(role: Role | None) -> None:
    """*"Refusal does not remove other exits."*"""
    actor = a_person(*(role,) if role else (), actor_id=RAFA)

    assert decide(actor, Operation.RESOLVE_ISSUE, _subject(author=RAFA)).allowed


def test_the_author_the_discipline_owner_and_the_director_may_resolve() -> None:
    for actor in (
        a_person(actor_id=RAFA),
        a_person(actor_id=ANA),
        a_person(Role.ART_DIRECTOR, actor_id=DANA),
    ):
        assert decide(actor, Operation.RESOLVE_ISSUE, _subject(author=RAFA, owner=ANA)).allowed


def test_an_uninvolved_person_may_not_resolve() -> None:
    outsider = a_person(Role.ENGINEER, actor_id=ActorId("auth|nobody"))

    decision = decide(outsider, Operation.RESOLVE_ISSUE, _subject(author=RAFA, owner=ANA))

    assert decision.refused
    assert str(Role.ART_DIRECTOR) in decision.reason


def test_a_person_may_only_edit_and_withdraw_their_own() -> None:
    for operation in (
        Operation.EDIT_CONTRIBUTION,
        Operation.WITHDRAW_CONTRIBUTION,
        Operation.MOVE_ANNOTATION,
    ):
        assert decide(a_person(actor_id=RAFA), operation, _subject(author=RAFA)).allowed
        refused = decide(
            a_person(Role.ART_DIRECTOR, actor_id=DANA), operation, _subject(author=RAFA)
        )
        assert refused.refused, operation


def test_promotion_is_never_available_to_an_automated_caller() -> None:
    """*"Including when the person it acts for holds the art director role."*"""
    director = a_person(Role.ART_DIRECTOR, actor_id=DANA)

    decision = decide(director, Operation.PROMOTE_TO_RULE, _subject(), via=AgentId("blender-agent"))

    assert decision.refused
    assert "requires a person" in decision.reason


def test_a_service_credential_holding_every_role_is_still_refused_promotion() -> None:
    robot = automation_actor(projects=(PROJECT,), roles=tuple(Role))

    assert decide(robot, Operation.PROMOTE_TO_RULE, _subject()).refused


def test_promotion_is_registered_as_requiring_a_person() -> None:
    assert Operation.PROMOTE_TO_RULE in HUMAN_ONLY


# --------------------------------------------------------------------------
# 1.6 — the promotion transformation, both halves or neither
# --------------------------------------------------------------------------


def test_a_promotion_writes_the_rule_and_retires_the_annotation_together() -> None:
    asset = an_asset(an_annotation())

    promotion = promote(asset, "an_1", RULE, PromotionTarget.SILHOUETTE_RULES, by=str(DANA))

    assert promotion.asset.concept is not None
    assert RULE in promotion.asset.concept.silhouette_rules
    assert promotion.asset.annotations[0].state is AnnotationState.PROMOTED
    assert promotion.annotation.closed_by == str(DANA)


def test_there_is_no_way_to_ask_for_only_one_half() -> None:
    """One function, one value: a caller cannot apply the rule and skip the retirement."""
    asset = an_asset(an_annotation())

    promotion = promote(asset, "an_1", RULE, PromotionTarget.SILHOUETTE_RULES)

    assert promotion.asset.annotations[0].has_exited
    assert promotion.asset is not asset


def test_promoting_into_the_constraints_sets_a_checkable_field() -> None:
    asset = an_asset(an_annotation(), constraints=Constraints(lods=(4000, 2000)))

    promotion = promote(asset, "an_1", "tri_budget: 8000", PromotionTarget.CONSTRAINTS)

    assert promotion.asset.constraints is not None
    assert promotion.asset.constraints.tri_budget == 8000


def test_promoting_into_a_nested_constraint_block_creates_it() -> None:
    promotion = promote(
        an_asset(an_annotation()), "an_1", "rig.max_bones: 75", PromotionTarget.CONSTRAINTS
    )

    assert promotion.asset.constraints is not None
    assert promotion.asset.constraints.rig is not None
    assert promotion.asset.constraints.rig.max_bones == 75


def test_a_rule_that_declares_no_engineering_field_is_refused_naming_the_set() -> None:
    with pytest.raises(PromotionRefused, match="tri_budget"):
        promote(
            an_asset(an_annotation()),
            "an_1",
            "make it lighter",
            PromotionTarget.CONSTRAINTS,
        )


def test_an_empty_rule_is_refused_rather_than_retiring_the_annotation() -> None:
    with pytest.raises(PromotionRefused, match="empty rule"):
        promote(an_asset(an_annotation()), "an_1", "   ", PromotionTarget.SILHOUETTE_RULES)


def test_promoting_an_annotation_that_already_exited_is_refused() -> None:
    asset = an_asset(an_annotation(state=AnnotationState.RESOLVED))

    with pytest.raises(PromotionRefused, match="already resolved"):
        promote(asset, "an_1", RULE, PromotionTarget.SILHOUETTE_RULES)


def test_promoting_an_annotation_that_is_not_there_is_refused() -> None:
    with pytest.raises(PromotionRefused, match="no annotation"):
        promote(an_asset(), "an_1", RULE, PromotionTarget.SILHOUETTE_RULES)


def test_a_promotion_producing_an_invalid_specification_is_detectable_before_it_lands() -> None:
    """The specification check runs over the *resulting* document, not the current one."""
    asset = an_asset(an_annotation(), constraints=Constraints(lods=(12000, 4000)))

    promotion = promote(asset, "an_1", "tri_budget: 8000", PromotionTarget.CONSTRAINTS)

    assert [finding.rule_id for finding in check_asset(promotion.asset)] == [
        RULE_LOD0_OVER_TRI_BUDGET
    ]


def test_the_two_destinations_are_the_only_ones() -> None:
    assert PromotionTarget.values() == ("constraints", "concept.silhouette_rules")
    assert PromotionTarget.from_value("wherever") is None


def test_a_silhouette_rule_is_prose_and_a_constraint_is_a_declaration() -> None:
    assert parse_rule(RULE, PromotionTarget.SILHOUETTE_RULES) == RULE
    assert parse_rule("tri_budget: 8000", PromotionTarget.CONSTRAINTS) == Declaration(
        path="tri_budget", value=8000
    )


def test_promoting_the_same_rule_twice_does_not_duplicate_it() -> None:
    asset = an_asset(an_annotation("a1"), an_annotation("a2"), concept=Concept(views=("front",)))

    once = promote(asset, "a1", RULE, PromotionTarget.SILHOUETTE_RULES)
    twice = promote(once.asset, "a2", RULE, PromotionTarget.SILHOUETTE_RULES)

    assert twice.asset.concept is not None
    assert twice.asset.concept.silhouette_rules == (RULE,)


def test_promotion_behaves_identically_for_both_anchor_forms() -> None:
    """*"Neither outcome SHALL depend on the anchor form."*"""
    flat = promote(an_asset(an_annotation("a1")), "a1", RULE, PromotionTarget.SILHOUETTE_RULES)
    solid = promote(
        an_asset(an_annotation("a1", part="SM_Shoulder")),
        "a1",
        RULE,
        PromotionTarget.SILHOUETTE_RULES,
    )

    assert flat.asset.concept == solid.asset.concept
    assert flat.annotation.state is solid.annotation.state
    assert replace(flat.annotation, target=solid.annotation.target) == solid.annotation


# --------------------------------------------------------------------------
# 1.7 — the queue ordering is total and deterministic
# --------------------------------------------------------------------------


def an_entry(
    asset: str = "mech_scout",
    identifier: str = "an_1",
    *,
    on_asset: int = 1,
    in_project: int = 1,
    replies: int = 0,
    age: float = 0.0,
) -> TriageEntry:
    annotation = an_annotation(identifier)
    for index in range(replies):
        from cybercanon.domain.annotations import Reply

        annotation = annotation.with_reply(Reply(id=f"re_{index}", author=str(ANA), text="x"))
    return TriageEntry(
        asset=asset,
        annotation=annotation,
        same_kind_on_asset=on_asset,
        same_kind_in_project=in_project,
        age_seconds=age,
    )


def test_recurring_feedback_orders_above_isolated_feedback() -> None:
    """*"Annotations from the asset with four SHALL be ordered above the single one."*"""
    crowded = an_entry("mech_scout", "a1", on_asset=4)
    lonely = an_entry("mule", "b1", on_asset=1)

    assert [entry.id for entry in triage_order((lonely, crowded))] == ["a1", "b1"]


def test_the_project_wide_count_breaks_a_tie_on_the_asset() -> None:
    wide = an_entry("mule", "b1", on_asset=2, in_project=9)
    narrow = an_entry("mech_scout", "a1", on_asset=2, in_project=2)

    assert [entry.id for entry in triage_order((narrow, wide))] == ["b1", "a1"]


def test_the_reply_count_breaks_a_tie_on_both_counts() -> None:
    argued = an_entry("mech_scout", "a1", replies=6)
    quiet = an_entry("mech_scout", "a2", replies=0)

    assert [entry.id for entry in triage_order((quiet, argued))] == ["a1", "a2"]


def test_age_breaks_a_tie_on_every_count_with_the_oldest_first() -> None:
    old = an_entry("mech_scout", "a1", age=900.0)
    fresh = an_entry("mech_scout", "a2", age=10.0)

    assert [entry.id for entry in triage_order((fresh, old))] == ["a1", "a2"]


def test_the_order_is_total_for_entries_with_identical_signals() -> None:
    """Paging over a partial order returns some entries twice and some never."""
    same = (an_entry("mule", "b1"), an_entry("mech_scout", "a2"), an_entry("mech_scout", "a1"))

    assert [entry.id for entry in triage_order(same)] == ["a1", "a2", "b1"]
    assert triage_order(same) == triage_order(tuple(reversed(same)))


def test_the_same_kind_count_counts_only_open_annotations() -> None:
    listed = (
        an_annotation("a1", AnnotationKind.TECHNICAL),
        an_annotation("a2", AnnotationKind.TECHNICAL, state=AnnotationState.RESOLVED),
        an_annotation("a3", AnnotationKind.DESIGN),
    )

    assert same_kind_counts(listed, AnnotationKind.TECHNICAL) == 1


# --------------------------------------------------------------------------
# The constraint table — every field a promotion may set, and how it reads
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "declaration,expected",
    [
        ("tri_budget: 8000", ("tri_budget", 8000)),
        ("lods: 8000, 4000, 2000", ("lods", (8000, 4000, 2000))),
        ("lods: [8000, 4000]", ("lods", (8000, 4000))),
        ("collider: convex", ("collider", "convex")),
        ("pivot:  base centre ", ("pivot", "base centre")),
        ("up_axis: Z", ("up_axis", "Z")),
        ("unit_scale: 1.0", ("unit_scale", 1.0)),
        ("naming: SM_{asset}_LOD{n}", ("naming", "SM_{asset}_LOD{n}")),
        ("texture.size: 2048", ("texture.size", 2048)),
        ("texture.sets: 2", ("texture.sets", 2)),
        ("texture.channels: base, orm", ("texture.channels", ("base", "orm"))),
        ("rig.skeleton: SK_Humanoid", ("rig.skeleton", "SK_Humanoid")),
        ("rig.max_bones: 75", ("rig.max_bones", 75)),
        ("rig.skinned: true", ("rig.skinned", True)),
        ("rig.skinned: no", ("rig.skinned", False)),
        ("animation.frame_rate: 30", ("animation.frame_rate", 30.0)),
        (
            "animation.clip_naming: A_{asset}_{state}",
            ("animation.clip_naming", "A_{asset}_{state}"),
        ),
    ],
    ids=lambda value: value if isinstance(value, str) else "",
)
def test_every_promotable_constraint_reads_its_value(
    declaration: str, expected: tuple[str, object]
) -> None:
    """The closed table, exercised entry by entry rather than in the aggregate."""
    parsed = parse_rule(declaration, PromotionTarget.CONSTRAINTS)

    assert isinstance(parsed, Declaration)
    assert (parsed.path, parsed.value) == expected


def test_the_table_covers_every_field_the_tests_name() -> None:
    """A field added without a case here is a field nobody checked the reading of."""
    assert set(FIELDS) == {
        "tri_budget",
        "lods",
        "collider",
        "pivot",
        "up_axis",
        "unit_scale",
        "naming",
        "texture.size",
        "texture.sets",
        "texture.channels",
        "rig.skeleton",
        "rig.max_bones",
        "rig.skinned",
        "animation.frame_rate",
        "animation.clip_naming",
    }


@pytest.mark.parametrize(
    "declaration",
    ["tri_budget: heavy", "rig.skinned: maybe", "lods: 8000, four thousand"],
)
def test_a_value_the_field_cannot_hold_is_refused_naming_the_field(declaration: str) -> None:
    field = declaration.split(":")[0]

    with pytest.raises(PromotionRefused) as refusal:
        parse_rule(declaration, PromotionTarget.CONSTRAINTS)

    assert refusal.value.subject == field


def test_a_declaration_renders_as_the_file_writes_it() -> None:
    """A list renders as a list, which is what the refusal and the diff both show."""
    assert str(Declaration(path="tri_budget", value=8000)) == "tri_budget: 8000"
    assert str(Declaration(path="lods", value=(8000, 4000))) == "lods: 8000, 4000"


def test_a_promotion_carries_the_rule_as_it_now_reads() -> None:
    promotion = promote(
        an_asset(an_annotation()), "an_1", "tri_budget: 8000", PromotionTarget.CONSTRAINTS
    )

    assert promotion.rule_text == "tri_budget: 8000"
    assert promotion.target is PromotionTarget.CONSTRAINTS


def test_a_destination_renders_as_the_specification_spells_it() -> None:
    """A refusal and a commit message both name it, so both name the same thing."""
    assert str(PromotionTarget.CONSTRAINTS) == "constraints"
    assert str(PromotionTarget.SILHOUETTE_RULES) == "concept.silhouette_rules"
    assert PromotionTarget.listed() == "`constraints` and `concept.silhouette_rules`"


def test_a_queue_entry_reports_the_annotation_it_is_about() -> None:
    entry = an_entry("mech_scout", "an_1")

    assert entry.id == "an_1"
    assert entry.kind is AnnotationKind.ART_DIRECTION
    assert entry.replies == 0
