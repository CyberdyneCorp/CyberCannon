"""Tasks 7.1 and 7.2 — the four commands, and the full generate → accept → search cycle.

Two properties only the inbound surface can have, and both are here:

* **the disabled path exits successfully.** `canon describe` on a machine with
  no model configured prints the reason and exits `0`. Exiting `2` would make an
  optional feature look like a broken installation in somebody's pre-commit
  hook, and `llm-integration` is explicit that everything else keeps working.
* **nothing a proposal produces is presented as somebody's.** Every suggested
  alias the command prints is labelled generated, and the `--json` document says
  the same thing in the same words.

The container is built over the world in `tests/derived_world.py`, so the
acceptance this exercises is a real commit into a real working copy read back
through the adapter's own reader.
"""

from __future__ import annotations

import json

import pytest
import typer
from typer.testing import CliRunner

from cybercanon.adapters.inbound.cli.app import build_app
from cybercanon.adapters.wiring.container import Container
from cybercanon.application.ports.llm import Unavailability
from cybercanon.application.ports.search_index import MatchKind
from cybercanon.application.testing import build_fakes
from cybercanon.application.testing.vision import InMemoryVision
from cybercanon.application.use_cases.index_assets import entry_for
from cybercanon.application.use_cases.resolve_actor import IdentitySource, Resolution
from cybercanon.domain.derived import GENERATED
from cybercanon.domain.identity import Actor, ActorId, Role
from derived_world import PROJECT, RAFA_SUBJECT, SCOUT, a_derived_world

pytestmark = pytest.mark.unit

CLEAN = 0
COULD_NOT_RUN = 2


@pytest.fixture
def world():
    return a_derived_world()


def a_container(world, vision: InMemoryVision | None = None) -> Container:
    """`canon`, wired over the derived world and whichever model it was given."""
    fakes = build_fakes()
    index = world.index
    index.upsert(
        entry_for(world.views.spec_store.load("characters/mech_scout/asset.yaml"), _project())
    )
    return Container(
        spec_store=world.views.spec_store,
        mesh_inspector=fakes["mesh_inspector"],
        search_index=index,
        repository_host=world.views.host,
        project_id=PROJECT,
        actor_resolver=_resolver(),
        vision=vision if vision is not None else world.vision,
    )


def _project():
    from cybercanon.application.ports.spec_store import ProjectConfig

    return ProjectConfig(name=PROJECT)


def _resolver():
    """A resolver answering the person the world's actors mapping binds."""
    actor = Actor(
        id=ActorId(RAFA_SUBJECT),
        display_name="Rafa",
        roles=(Role.ART_DIRECTOR,),
        projects=(PROJECT,),
    )
    resolution = Resolution(actor=actor, source=IdentitySource.LOCAL, verified=False)

    class Resolver:
        def resolve(self) -> Resolution:
            return resolution

    return Resolver()


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


def app(world, vision: InMemoryVision | None = None) -> typer.Typer:
    return build_app(a_container(world, vision))


# --------------------------------------------------------------------------
# 7.1 — the disabled path exits successfully with an explanatory message
# --------------------------------------------------------------------------


@pytest.mark.parametrize("command", ["describe", "suggest-aliases"])
def test_the_disabled_path_exits_successfully_and_says_why(
    world, runner: CliRunner, command: str
) -> None:
    world.refusing(Unavailability.DISABLED, "no model is configured for this deployment")

    result = runner.invoke(app(world), [command, SCOUT])

    assert result.exit_code == CLEAN
    assert str(Unavailability.DISABLED) in result.output
    assert "no model is configured" in result.output


@pytest.mark.parametrize("reason", list(Unavailability), ids=str)
def test_every_reason_exits_the_same_way_and_states_itself(
    world, runner: CliRunner, reason: Unavailability
) -> None:
    """*"every failure degrades identically"*, from the surface a person uses."""
    world.refusing(reason)

    result = runner.invoke(app(world), ["describe", SCOUT])

    assert result.exit_code == CLEAN
    assert str(reason) in result.output


def test_the_structured_document_says_it_is_unavailable_and_why(world, runner: CliRunner) -> None:
    world.refusing(Unavailability.UNREACHABLE)

    result = runner.invoke(app(world), ["describe", SCOUT, "--json"])

    document = json.loads(result.stdout)
    assert document["available"] is False
    assert str(Unavailability.UNREACHABLE) in document["reason"]
    assert document["records"] == []


def test_an_asset_with_no_concept_view_is_a_refusal_naming_the_reason(
    runner: CliRunner,
) -> None:
    world = a_derived_world(views={})
    world.always_answering()

    result = runner.invoke(app(world), ["describe", SCOUT])

    assert result.exit_code == COULD_NOT_RUN
    assert "no concept view to describe" in result.output
    assert "never rendered" in result.output


# --------------------------------------------------------------------------
# 7.1 — what a generation prints, and that none of it is anybody's
# --------------------------------------------------------------------------


def test_describe_prints_the_description_the_provenance_and_the_proposals(
    world, runner: CliRunner
) -> None:
    world.answering()

    result = runner.invoke(app(world), ["describe", SCOUT])

    assert result.exit_code == CLEAN
    assert GENERATED in result.output
    assert "walker" in result.output
    assert world.vision.model in result.output


def test_every_proposal_is_labelled_generated_in_the_document(world, runner: CliRunner) -> None:
    world.answering()

    result = runner.invoke(app(world), ["suggest-aliases", SCOUT, "--json"])

    (record,) = json.loads(result.stdout)["records"]
    assert record["label"] == GENERATED
    assert all(entry["label"] == GENERATED for entry in record["suggestions"])
    assert record["model"] and record["generated_at"] and record["source_hash"]


def test_a_second_run_reuses_what_is_there_and_says_so(world, runner: CliRunner) -> None:
    world.answering()
    runner.invoke(app(world), ["describe", SCOUT])

    result = runner.invoke(app(world), ["describe", SCOUT, "--json"])

    (record,) = json.loads(result.stdout)["records"]
    assert record["reused"] is True
    assert world.model_calls() == 2


# --------------------------------------------------------------------------
# 7.2 — generate, accept, search: the alias ranks as an alias
# --------------------------------------------------------------------------


def test_the_whole_cycle_ends_with_the_accepted_alias_ranking_as_an_alias(
    world, runner: CliRunner
) -> None:
    """The feature that earns this change, end to end.

    Before: searching `mech` for an asset named `Scout Mech` returns nothing and
    is logged as a miss, because `mech` is neither a prefix nor a declared
    alias. After one click of acceptance it is an ordinary alias and the search
    is exact.
    """
    world.answering()
    wired = app(world)
    index = world.index

    assert index.search("mech", PROJECT) == ()

    runner.invoke(wired, ["suggest-aliases", SCOUT])
    rescued = index.search("mech", PROJECT)
    assert rescued[0].kind is MatchKind.SUGGESTED_ALIAS

    accepted = runner.invoke(wired, ["accept-alias", SCOUT, "mech", "--image", world.source_hash()])
    assert accepted.exit_code == CLEAN
    assert world.aliases() == ("mech",)

    index.upsert(
        entry_for(world.views.spec_store.load("characters/mech_scout/asset.yaml"), _project())
    )
    (hit,) = index.search("mech", PROJECT)
    assert hit.kind is MatchKind.ALIAS
    assert not hit.is_suggestion


def test_acceptance_names_the_person_and_the_commit(world, runner: CliRunner) -> None:
    world.answering()
    wired = app(world)
    runner.invoke(wired, ["suggest-aliases", SCOUT])

    result = runner.invoke(
        wired, ["accept-alias", SCOUT, "walker", "--image", world.source_hash(), "--json"]
    )

    document = json.loads(result.stdout)
    assert document["written"] == "walker"
    assert document["accepted_by"] == RAFA_SUBJECT
    assert document["committed"] is True
    assert document["revision"]


def test_a_value_can_be_edited_before_it_is_accepted(world, runner: CliRunner) -> None:
    world.answering()
    wired = app(world)
    runner.invoke(wired, ["suggest-aliases", SCOUT])

    runner.invoke(
        wired,
        ["accept-alias", SCOUT, "walker", "--image", world.source_hash(), "--as", "Strider"],
    )

    assert world.aliases() == ("strider",)


def test_rejection_writes_nothing_and_stops_the_term_coming_back(world, runner: CliRunner) -> None:
    world.answering()
    wired = app(world)
    runner.invoke(wired, ["suggest-aliases", SCOUT])
    before = world.spec_text()

    rejected = runner.invoke(
        wired, ["reject-alias", SCOUT, "walker", "--image", world.source_hash()]
    )

    assert rejected.exit_code == CLEAN
    assert world.spec_text() == before
    listed = runner.invoke(wired, ["suggest-aliases", SCOUT, "--json"])
    (record,) = json.loads(listed.stdout)["records"]
    states = {entry["value"]: entry["state"] for entry in record["suggestions"]}
    assert states["walker"] == "rejected"


def test_accepting_something_nobody_suggested_is_refused(world, runner: CliRunner) -> None:
    world.answering()
    wired = app(world)
    runner.invoke(wired, ["suggest-aliases", SCOUT])

    result = runner.invoke(
        wired, ["accept-alias", SCOUT, "invented", "--image", world.source_hash()]
    )

    assert result.exit_code == COULD_NOT_RUN
    assert world.aliases() == ()


def test_nothing_the_commands_print_carries_a_marker_into_the_file(
    world, runner: CliRunner
) -> None:
    """The file is the canon; the label belongs to the surface, never to the file."""
    world.answering()
    wired = app(world)
    runner.invoke(wired, ["suggest-aliases", SCOUT])
    runner.invoke(wired, ["accept-alias", SCOUT, "walker", "--image", world.source_hash()])

    written = world.spec_text().lower()
    assert "walker" in written
    for marker in (GENERATED, "suggested", "vision", "llm"):
        assert marker not in written
