"""Tasks 1.1 to 1.7 — the observation, the write policy, and the three limits.

The product's sharpest rule is a domain property or it is nothing: *agents read
constraints, agents never write constraints*. So every assertion below is about
a pure function, runs with no repository, no clock and no credential, and asks
the question the specification asks rather than the question the implementation
makes convenient.

Four of them are worth reading as claims rather than as tests:

* an observation kind outside the closed set **cannot be constructed** — the
  refusal is raised by the only function that produces one, so there is no path
  to a free-form value;
* the prohibition is walked **for every role in turn**, from
  :func:`~cybercanon.domain.observations.prohibited_for_every_role`, so a role
  added tomorrow is asserted the day it is added;
* the rate limit is exercised at the boundary, one over it, and after it resets,
  with a clock a test chose — which is only possible because the policy takes
  the moment as an argument;
* the duplicate predicate is asserted in all three directions: an identical
  repeat suppresses, one after a resolution does not, and another agent's
  identical text never swallows a finding.
"""

from __future__ import annotations

import ast
import inspect
from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from cybercanon.domain import observations as observations_module
from cybercanon.domain.annotations import (
    Anchor3D,
    Annotation,
    AnnotationKind,
    AnnotationState,
    AuthorKind,
    ObservationKind,
)
from cybercanon.domain.identity import (
    WRITE_NEEDS_BOTH,
    Actor,
    ActorId,
    AgentId,
    Role,
    automation_actor,
    write_attribution,
)
from cybercanon.domain.observations import (
    OBSERVATION_ONLY,
    ONLY_OBSERVES,
    ObservationRefused,
    WriteLimits,
    annotation_kind_of,
    duplicate_of,
    materially_same,
    may_only_observe,
    normalized,
    observation,
    observation_kind_of,
    prohibited_for_every_role,
    target_for,
    write_allowance,
)
from cybercanon.domain.policy import MUTATING, Operation

pytestmark = pytest.mark.unit

RAFA = ActorId("rafa")
ANA = ActorId("ana")
BLENDER = AgentId("blender-agent")
OTHER_AGENT = AgentId("houdini-agent")
ASSET = "mech_scout"
NOW = datetime(2026, 3, 1, 12, 0, tzinfo=UTC)


def a_person(*roles: Role, actor_id: ActorId = RAFA) -> Actor:
    return Actor(id=actor_id, display_name="Rafa", roles=roles, projects=("ronin",))


def an_observation(
    text: str = "12k triangles is unreachable without losing the head silhouette",
    *,
    author: ActorId = RAFA,
    via: AgentId = BLENDER,
    target: str = "head",
    kind: AnnotationKind = AnnotationKind.TECHNICAL,
    observed: ObservationKind = ObservationKind.UNATTAINABLE_CONSTRAINT,
    at: datetime | None = None,
    identifier: str = "obs_1",
) -> Annotation:
    return observation(
        identifier=identifier,
        author=author.value,
        via=via,
        kind=kind,
        observation_kind=observed,
        text=text,
        target=target_for(target, ("head", "torso")),
        created_at=(at or NOW).isoformat(),
    )


# --------------------------------------------------------------------------
# 1.1 — the author kind, the closed observation kind, and the domain's imports
# --------------------------------------------------------------------------


def test_an_annotation_says_whether_a_person_or_an_agent_wrote_it() -> None:
    """The marking is a field, not an inference from an optional `via` (D8)."""
    human = Annotation(
        id="an_1",
        author="rafa",
        kind=AnnotationKind.DESIGN,
        text="hi",
        target=Anchor3D(part="head"),
    )

    assert human.author_kind is AuthorKind.HUMAN
    assert not human.is_agent_authored
    assert an_observation().is_agent_authored


def test_an_observation_carries_both_kinds_and_does_not_extend_the_first() -> None:
    """`kind` stays `asset-spec`'s set; the agent's vocabulary is its own field."""
    recorded = an_observation()

    assert recorded.kind in set(AnnotationKind)
    assert recorded.observation_kind is ObservationKind.UNATTAINABLE_CONSTRAINT
    assert recorded.is_observation


def test_the_observation_kind_set_is_the_three_the_requirement_names() -> None:
    assert ObservationKind.values() == ("unattainable_constraint", "ambiguity", "defect")


@pytest.mark.parametrize("declared", ["", "  ", "blocked", "unattainable-constraint", "TECHNICAL"])
def test_an_unknown_observation_kind_cannot_be_constructed(declared: str) -> None:
    """There is no path to a free-form value: the only constructor refuses."""
    with pytest.raises(ObservationRefused) as raised:
        observation_kind_of(declared)

    assert all(value in raised.value.reason for value in ObservationKind.values())


def test_an_observation_specific_value_in_the_kind_field_is_refused() -> None:
    """*"The write SHALL be refused naming the values `asset-spec` permits."*"""
    with pytest.raises(ObservationRefused) as raised:
        annotation_kind_of("unattainable_constraint")

    assert all(member.value in raised.value.reason for member in AnnotationKind)
    assert "observation_kind" in raised.value.reason


def test_an_unknown_annotation_kind_lists_the_permitted_ones() -> None:
    with pytest.raises(ObservationRefused) as raised:
        annotation_kind_of("engineering")

    assert "art-direction" in raised.value.reason
    assert raised.value.subject == "kind"


def test_the_observation_domain_imports_only_the_standard_library() -> None:
    """The `stdlib_only` contract, asserted at the module that would break it.

    `lint-imports` enforces it over the whole package; this is the same claim at
    the new module, so a third-party import added here fails the unit suite
    before anybody runs the layering contract.
    """
    tree = ast.parse(inspect.getsource(observations_module))
    roots = {
        (node.module or "").split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
    } | {
        alias.name.split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    }

    assert roots <= {
        "__future__",
        "unicodedata",
        "collections",
        "dataclasses",
        "datetime",
        "cybercanon",
    }


# --------------------------------------------------------------------------
# 1.2 — a write attribution has both slots or it is not produced (D4)
# --------------------------------------------------------------------------


def test_a_write_attribution_names_the_person_and_the_agent() -> None:
    attribution = write_attribution(a_person(), BLENDER)

    assert attribution.actor == RAFA
    assert attribution.via == BLENDER
    assert str(attribution) == "rafa, via blender-agent"


@pytest.mark.parametrize(
    ("actor", "via"),
    [(RAFA, None), (None, BLENDER), (None, None), (RAFA, "blender-agent"), (RAFA, "")],
)
def test_no_constructor_path_produces_a_write_attribution_missing_a_slot(actor, via) -> None:
    """*"An unattributable write is refused, never recorded anonymously."*"""
    with pytest.raises(ValueError, match="refused"):
        write_attribution(actor, via)


def test_the_write_attribution_refusal_says_what_was_missing() -> None:
    with pytest.raises(ValueError) as raised:
        write_attribution(a_person(), None)

    assert str(raised.value) == WRITE_NEEDS_BOTH


def test_the_observation_constructor_has_no_slot_for_a_missing_agent() -> None:
    """The domain exposes no constructor for an anonymous observation (D4)."""
    with pytest.raises(ObservationRefused):
        observation(
            identifier="obs_1",
            author="rafa",
            via=None,  # type: ignore[arg-type]
            kind=AnnotationKind.TECHNICAL,
            observation_kind=ObservationKind.DEFECT,
            text="the pivot is not at the origin",
            target=target_for("head"),
        )


# --------------------------------------------------------------------------
# 1.3 — an automated caller only observes, for every role in turn
# --------------------------------------------------------------------------


def test_the_prohibition_is_every_mutating_operation_but_recording_one() -> None:
    assert MUTATING - {Operation.CREATE_ANNOTATION} == OBSERVATION_ONLY
    assert Operation.PROMOTE_TO_RULE in OBSERVATION_ONLY
    assert Operation.RESOLVE_ISSUE in OBSERVATION_ONLY
    assert Operation.REOPEN_ISSUE in OBSERVATION_ONLY
    assert Operation.TRANSITION_ASSET_STATUS in OBSERVATION_ONLY


@pytest.mark.parametrize("role", prohibited_for_every_role(), ids=lambda role: role.value)
@pytest.mark.parametrize(
    "operation",
    sorted(OBSERVATION_ONLY, key=str),
    ids=lambda operation: operation.value,
)
def test_an_agent_is_refused_every_prohibited_operation_for_every_role(
    role: Role, operation: Operation
) -> None:
    """*"Regardless of the roles held by the actor the caller acts as."*"""
    decision = may_only_observe(a_person(role), operation, via=BLENDER)

    assert decision.refused
    assert ONLY_OBSERVES in decision.reason
    assert str(BLENDER) in decision.reason


@pytest.mark.parametrize("role", prohibited_for_every_role(), ids=lambda role: role.value)
def test_an_agent_holding_any_role_may_still_record_an_observation(role: Role) -> None:
    """The prohibition narrows; it never closes the one tool that exists."""
    assert may_only_observe(a_person(role), Operation.CREATE_ANNOTATION, via=BLENDER).allowed


def test_background_automation_with_no_agent_named_is_refused_too() -> None:
    """A service credential holding every role is still an automated caller."""
    decision = may_only_observe(automation_actor(roles=tuple(Role)), Operation.PROMOTE_TO_RULE)

    assert decision.refused


def test_a_person_acting_directly_is_not_this_policy_s_business() -> None:
    """The ordinary matrix decides for a person; this one answers only about machines."""
    assert may_only_observe(a_person(Role.ART_DIRECTOR), Operation.PROMOTE_TO_RULE).allowed


# --------------------------------------------------------------------------
# 1.5 — the rate limit, with a clock a test chose (D9)
# --------------------------------------------------------------------------


LIMITS = WriteLimits(observations=3, window_seconds=600.0)


def _recorded(count: int, *, at: datetime = NOW, author: ActorId = RAFA) -> tuple[Annotation, ...]:
    return tuple(
        an_observation(text=f"finding {index}", author=author, at=at, identifier=f"obs_{index}")
        for index in range(count)
    )


def test_a_caller_under_the_limit_may_write() -> None:
    allowance = write_allowance(
        actor=a_person(), asset_id=ASSET, recorded=_recorded(2), now=NOW, limits=LIMITS
    )

    assert allowance.allowed
    assert allowance.remaining == 1


def test_the_boundary_is_the_last_permitted_write() -> None:
    """At the limit exactly, the next one is refused — not the one that reached it."""
    at_limit = write_allowance(
        actor=a_person(), asset_id=ASSET, recorded=_recorded(2), now=NOW, limits=LIMITS
    )
    one_over = write_allowance(
        actor=a_person(), asset_id=ASSET, recorded=_recorded(3), now=NOW, limits=LIMITS
    )

    assert at_limit.allowed
    assert one_over.refused


def test_a_throttled_write_names_the_limit_and_when_it_resets() -> None:
    allowance = write_allowance(
        actor=a_person(), asset_id=ASSET, recorded=_recorded(3), now=NOW, limits=LIMITS
    )

    assert allowance.refused
    assert str(LIMITS.observations) in allowance.reason
    assert ASSET in allowance.reason
    assert allowance.resets_at == NOW + LIMITS.window
    assert allowance.resets_at is not None and allowance.resets_at.isoformat() in allowance.reason


def test_the_allowance_returns_after_the_window_passes() -> None:
    later = NOW + timedelta(seconds=LIMITS.window_seconds + 1)

    allowance = write_allowance(
        actor=a_person(), asset_id=ASSET, recorded=_recorded(3), now=later, limits=LIMITS
    )

    assert allowance.allowed
    assert allowance.recorded == 0


def test_another_actor_s_observations_do_not_consume_this_one_s_allowance() -> None:
    """Per `(actor, asset)`: an agent's loop must not throttle a second person."""
    allowance = write_allowance(
        actor=a_person(actor_id=ANA),
        asset_id=ASSET,
        recorded=_recorded(5),
        now=NOW,
        limits=LIMITS,
    )

    assert allowance.allowed


def test_a_human_thread_never_consumes_an_agent_s_allowance() -> None:
    """The limit is on automated writes; a person's annotations are not counted."""
    human = tuple(
        Annotation(
            id=f"an_{index}",
            author=RAFA.value,
            kind=AnnotationKind.ART_DIRECTION,
            text="the silhouette reads as a crate",
            target=Anchor3D(part="head"),
            created_at=NOW.isoformat(),
        )
        for index in range(5)
    )

    assert write_allowance(
        actor=a_person(), asset_id=ASSET, recorded=human, now=NOW, limits=LIMITS
    ).allowed


def test_an_observation_with_no_recorded_time_counts_against_the_limit() -> None:
    """The conservative direction: an unstamped write must not evade the limit."""
    unstamped = tuple(replace(entry, created_at="") for entry in _recorded(3))

    assert write_allowance(
        actor=a_person(), asset_id=ASSET, recorded=unstamped, now=NOW, limits=LIMITS
    ).refused


@pytest.mark.parametrize(("observations", "window"), [(0, 60.0), (1, 0.0), (1, -1.0)])
def test_a_limit_that_permits_nothing_is_not_a_limit(observations: int, window: float) -> None:
    with pytest.raises(ValueError):
        WriteLimits(observations=observations, window_seconds=window)


# --------------------------------------------------------------------------
# 1.6 — near-duplicate suppression, against open observations only (D10)
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("left", "right"),
    [
        ("Cannot reach 12k triangles.", "cannot reach 12k triangles"),
        ("cannot   reach\n12k  triangles", "Cannot reach 12k triangles!"),
        ("Cannot reach 12k triangles", "  CANNOT REACH 12K TRIANGLES  "),
    ],
)
def test_normalisation_folds_case_whitespace_and_punctuation(left: str, right: str) -> None:
    assert normalized(left) == normalized(right)


def test_two_different_findings_do_not_normalise_together() -> None:
    assert normalized("the pivot is off") != normalized("the up axis is off")


def test_an_identical_repeat_is_suppressed() -> None:
    existing = an_observation()

    assert duplicate_of((existing,), an_observation(identifier="obs_2")) is existing


def test_a_repeat_after_a_resolution_is_not_suppressed() -> None:
    """*"If a person resolved an observation and the agent still hits it, that is
    new information and must be recordable."*"""
    resolved = an_observation().resolved(by="rafa", at=NOW.isoformat())

    assert resolved.state is AnnotationState.RESOLVED
    assert duplicate_of((resolved,), an_observation(identifier="obs_2")) is None


def test_another_agent_s_identical_text_does_not_suppress() -> None:
    """One agent silently swallowing another's finding is the failure being avoided."""
    theirs = an_observation(via=OTHER_AGENT)

    assert duplicate_of((theirs,), an_observation(identifier="obs_2")) is None


def test_a_human_s_identical_text_does_not_suppress_an_observation() -> None:
    human = replace(an_observation(), author_kind=AuthorKind.HUMAN, via="")

    assert duplicate_of((human,), an_observation(identifier="obs_2")) is None


def test_the_same_text_on_a_different_target_is_a_different_observation() -> None:
    assert (
        duplicate_of((an_observation(),), an_observation(target="torso", identifier="obs_2"))
        is None
    )


def test_the_same_text_with_a_different_observation_kind_is_not_the_same_thing() -> None:
    other = an_observation(observed=ObservationKind.AMBIGUITY, identifier="obs_2")

    assert not materially_same(an_observation(), other)


def test_the_same_text_with_a_different_discipline_is_not_the_same_thing() -> None:
    other = an_observation(kind=AnnotationKind.DESIGN, identifier="obs_2")

    assert not materially_same(an_observation(), other)


# --------------------------------------------------------------------------
# 1.7 — the target: anchored, or preserved as given and reported unanchored
# --------------------------------------------------------------------------


def test_a_named_target_that_exists_anchors_to_it() -> None:
    target = target_for("head", ("head", "torso"))

    assert target.anchored
    assert target.anchor == Anchor3D(part="head")
    assert an_observation().durable_key == "head"


def test_an_unresolvable_target_is_preserved_and_marked_unanchored() -> None:
    """*"It SHALL NOT be silently attached to a different target."*"""
    target = target_for("helmet_crest", ("head", "torso"))

    assert not target.anchored
    assert target.given == "helmet_crest"
    assert target.anchor.part == "helmet_crest"


def test_an_unanchored_observation_is_recorded_rather_than_discarded() -> None:
    """*"The write SHALL NOT be discarded for the target alone."*"""
    recorded = observation(
        identifier="obs_1",
        author="rafa",
        via=BLENDER,
        kind=AnnotationKind.TECHNICAL,
        observation_kind=ObservationKind.AMBIGUITY,
        text="which part is the crest?",
        target=target_for("helmet_crest", ("head", "torso")),
    )

    assert recorded.is_orphaned
    assert recorded.durable_key == "helmet_crest"
    assert recorded.is_open


def test_no_observation_is_ever_attached_to_a_neighbouring_target() -> None:
    """A near-miss name is preserved verbatim, never resolved to what is close."""
    target = target_for("heads", ("head", "torso"))

    assert target.anchor.part == "heads"


def test_an_unknown_subject_set_does_not_declare_every_target_dead() -> None:
    """``None`` means *this caller does not know*, which is not an empty set."""
    assert target_for("head").anchored
    assert not target_for("head", ()).anchored


@pytest.mark.parametrize("given", ["", "   ", "\n"])
def test_an_observation_that_names_no_target_is_refused(given: str) -> None:
    with pytest.raises(ObservationRefused) as raised:
        target_for(given)

    assert raised.value.subject == "target"


def test_an_empty_observation_is_refused_rather_than_recorded() -> None:
    with pytest.raises(ObservationRefused) as raised:
        observation(
            identifier="obs_1",
            author="rafa",
            via=BLENDER,
            kind=AnnotationKind.TECHNICAL,
            observation_kind=ObservationKind.DEFECT,
            text="   ",
            target=target_for("head"),
        )

    assert raised.value.subject == "text"


def test_an_observation_is_created_open_with_no_way_to_ask_for_anything_else() -> None:
    """Neither exit is a parameter here, which is what makes the two-exit rule hold."""
    parameters = set(inspect.signature(observation).parameters)

    assert an_observation().state is AnnotationState.OPEN
    assert not parameters & {"state", "closed_by", "closing_text", "author_kind"}


def test_a_timezone_less_recorded_time_is_a_decision_rather_than_a_crash() -> None:
    """A hand-authored `asset.yaml` may carry a naive time; a write must not die on it."""
    naive = tuple(replace(entry, created_at="2026-03-01T12:00:00") for entry in _recorded(3))

    allowance = write_allowance(
        actor=a_person(), asset_id=ASSET, recorded=naive, now=NOW, limits=LIMITS
    )

    assert allowance.refused
    assert allowance.resets_at == NOW + LIMITS.window
