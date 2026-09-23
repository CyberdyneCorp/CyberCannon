"""Tasks 5.1 to 5.3 — a machine's contribution is visible, and takes no exit.

D8 makes an observation *"an ordinary annotation with an author kind, not a
parallel record type"*, and accepts the consequence in as many words: *"every
annotation reader must now render the author kind, which is why the spec
requires the marking on every human surface rather than leaving it to each
view."* This module is that requirement, asserted on the two surfaces the tasks
name and on the payload the web application reads.

Three things, and the second is the one that keeps the briefing from rotting:

* **marked** (5.1) — one human-authored and one agent-authored open annotation,
  and exactly one of them is marked, in a reading of open annotations and in the
  compiled briefing alike;
* **two exits and no third** (5.2) — a person resolves an agent's observation
  and subsequent compilations do not contain it; a person promotes one and the
  resulting rule is attributed to the person, never to the agent. An agent that
  could take either exit would be an agent editing the canon by another route;
* **unanchored, never guessed** (5.3) — an observation naming a target the asset
  does not have is reported as unanchored wherever it is read, with the target
  the caller gave preserved verbatim.

The specifications below are written as YAML and parsed by the adapter's own
reader, so what is asserted is what an `asset.yaml` in a game repository would
actually produce — including the two fields `add-mcp-writes` added to the file
format.
"""

from __future__ import annotations

from dataclasses import replace

import pytest

from annotations_world import DIRECTOR, RAFA_ACTOR, SCOUT, SCOUT_SPEC, Threads, with_asset
from cybercanon.adapters.inbound.http import payloads
from cybercanon.application.testing.outcomes import ran
from cybercanon.application.use_cases.compile_spec import compile_spec
from cybercanon.application.use_cases.spec_lens import project_open_issues
from cybercanon.domain.annotations import (
    AGENT_AUTHORED,
    UNANCHORED,
    AnchorState,
    AuthorKind,
    ObservationKind,
    marked,
    marks,
)
from cybercanon.domain.triage import PromotionTarget

pytestmark = pytest.mark.unit

HUMAN_TEXT = "the pauldron reads as a backpack at 15 m"
AGENT_TEXT = "12000 triangles is unreachable without losing the head silhouette"
ABSENT_PART = "SM_MechScout_Antenna"
BLENDER = "blender-agent"


def a_spec_with_threads(*, target: str = "SM_MechScout_Shoulder_L", state: str = "open") -> bytes:
    """One asset, one person's annotation and one agent's observation beside it."""
    return f"""\
schema_version: 1
id: {SCOUT}
name: Scout Mech
status: modeling

constraints:
  tri_budget: 12000

concept:
  views: [front, side, back]

annotations:
  - id: an_1
    author: auth|rafa
    kind: art-direction
    text: {HUMAN_TEXT}
    state: open
    created_at: "2026-03-01T09:00:00+00:00"
    target:
      part: SM_MechScout_Shoulder_L
  - id: obs_1
    author: auth|rafa
    via: {BLENDER}
    kind: technical
    text: {AGENT_TEXT}
    state: {state}
    author_kind: agent
    observation_kind: {ObservationKind.UNATTAINABLE_CONSTRAINT.value}
    created_at: "2026-03-01T12:00:00+00:00"
    target:
      part: {target}
""".encode()


def briefing(world: Threads) -> str:
    """The compiled `art-spec.md` for the asset as the repository holds it now."""
    return compile_spec.raising(SCOUT_SPEC, spec_store=world.spec_store).text


def open_issues(world: Threads) -> str:
    """The same compilation projected down to its open threads — what a read returns."""
    return project_open_issues(compile_spec.raising(SCOUT_SPEC, spec_store=world.spec_store)).text


def an_observation(world: Threads):
    return world.annotation("obs_1")


# --------------------------------------------------------------------------
# 5.1 — exactly one of the two is marked
# --------------------------------------------------------------------------


def test_a_reading_of_open_annotations_marks_the_agents_and_not_the_persons() -> None:
    world = with_asset(a_spec_with_threads())

    rendered = open_issues(world).splitlines()
    lines = [line for line in rendered if HUMAN_TEXT in line or AGENT_TEXT in line]

    marked = [line for line in lines if AGENT_AUTHORED in line]
    assert len(lines) == 2
    assert len(marked) == 1
    assert AGENT_TEXT in marked[0]


def test_the_compiled_briefing_marks_the_agent_authored_observation() -> None:
    world = with_asset(a_spec_with_threads())

    compiled = briefing(world)

    assert AGENT_AUTHORED in compiled
    assert AGENT_TEXT in compiled
    assert compiled.count(AGENT_AUTHORED) == 1


def test_the_briefing_names_the_person_and_the_agent() -> None:
    """Attribution is *"rafa, via blender-agent"* wherever a human reads it."""
    compiled = briefing(with_asset(a_spec_with_threads()))

    assert f"via {BLENDER}" in compiled


def test_the_payload_a_human_surface_reads_carries_the_author_kind() -> None:
    """The triage view is a human surface too, and it must not infer this from `via`."""
    world = with_asset(a_spec_with_threads())

    rendered = payloads.annotation(an_observation(world))

    assert rendered["author_kind"] == str(AuthorKind.AGENT)
    assert rendered["observation_kind"] == ObservationKind.UNATTAINABLE_CONSTRAINT.value
    assert payloads.annotation(world.annotation("an_1"))["author_kind"] == str(AuthorKind.HUMAN)


# --------------------------------------------------------------------------
# 5.2 — the same two exits, and neither of them is the agent's
# --------------------------------------------------------------------------


def test_a_resolved_observation_leaves_subsequent_compilations() -> None:
    world = with_asset(a_spec_with_threads())
    assert AGENT_TEXT in briefing(world)

    ran(world.resolve("obs_1", actor=RAFA_ACTOR, conclusion="the budget was re-cut"))

    assert AGENT_TEXT not in briefing(world)
    assert HUMAN_TEXT in briefing(world)


def test_a_promoted_observation_becomes_a_rule_attributed_to_the_person() -> None:
    """*"It SHALL be attributed to the person who promoted it ... and not to the agent."*"""
    world = with_asset(a_spec_with_threads())
    rule = "the head silhouette outranks the triangle budget"

    ran(world.promote("obs_1", rule, PromotionTarget.SILHOUETTE_RULES, actor=DIRECTOR))

    compiled = briefing(world)
    assert rule in compiled
    assert BLENDER not in compiled.split("Open issues")[0]
    assert AGENT_TEXT not in compiled


def test_the_promotion_commit_is_the_persons_own() -> None:
    world = with_asset(a_spec_with_threads())

    ran(world.promote("obs_1", "the head silhouette outranks the budget", actor=DIRECTOR))

    assert world.commits()[-1].author.email == "dana@cyberdyne.com"


def test_a_promoted_observation_is_retired_from_the_open_threads() -> None:
    world = with_asset(a_spec_with_threads())

    ran(world.promote("obs_1", "the head silhouette outranks the budget", actor=DIRECTOR))

    assert an_observation(world).has_exited
    assert AGENT_AUTHORED not in open_issues(world)


# --------------------------------------------------------------------------
# 5.3 — an unanchored observation says so, and keeps the name it was given
# --------------------------------------------------------------------------


def test_an_unanchored_observation_is_reported_as_unanchored_with_its_target() -> None:
    world = with_asset(a_spec_with_threads(target=ABSENT_PART))
    world.parts = ("SM_MechScout_Shoulder_L", "SM_MechScout_Torso")

    listed = ran(world.listed())

    orphaned = [entry for entry in listed.orphaned if entry.annotation.id == "obs_1"]
    assert orphaned, "an observation naming a part the mesh does not have is an orphan"
    assert orphaned[0].subject == ABSENT_PART
    assert ABSENT_PART in payloads.orphan(orphaned[0])["subject"]


def test_the_target_as_given_is_preserved_in_the_record() -> None:
    world = with_asset(a_spec_with_threads(target=ABSENT_PART))

    assert an_observation(world).target.part == ABSENT_PART
    assert ABSENT_PART in world.spec_text()


def test_an_orphan_carries_both_markings_for_whoever_renders_it() -> None:
    """One function answers *what does a reader need to be told about this*.

    Authorship and anchoring are separate questions and both have to survive to
    the surface: an agent-authored thread that no longer lands anywhere is the
    case a reader is most likely to act on wrongly.
    """
    world = with_asset(a_spec_with_threads(target=ABSENT_PART))
    world.parts = ("SM_MechScout_Shoulder_L",)

    orphaned = ran(world.listed()).orphaned[0].annotation

    assert orphaned.id == "obs_1"
    assert marks(replace(orphaned, anchor_state=AnchorState.ORPHANED)) == (
        AGENT_AUTHORED,
        UNANCHORED,
    )
    assert UNANCHORED in marked(replace(orphaned, anchor_state=AnchorState.ORPHANED))
