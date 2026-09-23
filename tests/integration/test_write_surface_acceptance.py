"""Task 6.6 — the M5 acceptance run: the line an agent cannot cross, against a real repository.

One session, one repository on disk, one spawned agent server, and the sentence
the whole milestone exists to make true:

    **Agents read constraints. Agents never write constraints.**

The run is the story the proposal tells. A modelling agent cannot fit the scout
mech in its triangle budget without destroying the head silhouette. It is acting
as a person who holds the **art director** role — the one role that may promote
an annotation into a durable rule on a human surface — so every refusal below is
a refusal of the *caller*, never of the person's permissions. It then:

1. asks what the server offers, and finds **no promotion tool**;
2. attempts to promote anyway, and is refused by the protocol itself;
3. records the observation that the budget is unattainable, with its reason;
4. has the budget read back — **still 12000**, in the tool's answer and in the
   bytes of `asset.yaml`;
5. cannot resolve or close what it recorded;
6. reports the export's outcome, which is retained because nothing is listening,
   and the verdict stands regardless;
7. is seen by a person: the observation is marked agent-authored in the
   compiled `art-spec.md` a human reads, and in the open threads;
8. is given one of the two exits **by that person** — promoted into a rule
   attributed to them, and retired from the open threads.

The last step runs through the same use case the web surface calls, over the
same working copy, so the exit an agent may not take is demonstrably available
to a human on the same file.

`SESSION_VOLUME` is the other half of the task: the observation count this
session produced, recorded as the input to the rate-limit configuration D9
leaves open.
"""

from __future__ import annotations

import asyncio
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
from fastmcp import Client
from fastmcp.client.transports import StdioTransport
from game_repo import BARREL_BUDGET, BARREL_SPEC, MECH_EXPORT, MECH_SPEC, build_game_repo
from machine import (
    AGENT,
    ART_DIRECTION_ROLE,
    GIT_EMAIL,
    PERSON,
    SUBJECT,
    bare_environment,
    signing_issuer,
    stub_keychain,
)

from cybercanon.adapters.outbound.fs.outbox import OUTBOX_PATH
from cybercanon.adapters.outbound.git.local_host import LocalRepositoryHost
from cybercanon.adapters.outbound.git.spec_store import GitSpecStore
from cybercanon.application.testing.outcomes import ran
from cybercanon.application.use_cases.annotations import (
    Workspace,
    promote_annotation,
    resolve_annotation,
)
from cybercanon.domain.actors import GitAuthor
from cybercanon.domain.identity import Actor, ActorId, Role
from cybercanon.domain.triage import PromotionTarget

pytestmark = pytest.mark.integration

MECH = "mech_scout"
PROJECT = "Ronin"
BUDGET = "12000"
UNATTAINABLE = "12000 triangles is unreachable without losing the head silhouette"

BARREL = "barrel"
BARREL_UNATTAINABLE = "100 triangles cannot hold the barrel's rim without faceting it"

PROMOTED_RULE = "the barrel's rim reads as a circle at 5 m"
RESOLUTION = "the budget stands; model the head in 11k and drop the antenna detail"

PROHIBITED_TOOLS = (
    "promote_annotation",
    "promote",
    "resolve_annotation",
    "set_status",
    "update_spec",
    "set_constraint",
    "create_asset",
)
"""Tools an agent would need to author the canon. None of them may exist."""

ACTORS = """\
schema_version: 1
actors:
  - subject: auth|rafa
    name: Rafa
    emails: [rafa@cyberdyne.com]
    default_role: ART_DIRECTOR
"""

SESSION_VOLUME: dict[str, int] = {}
"""What this session recorded, read back by the rate-limit note at the end."""


def git(root: Path, *arguments: str) -> None:
    subprocess.run(
        ["git", "-C", str(root), *arguments],
        check=True,
        capture_output=True,
        env={
            **os.environ,
            "HOME": str(root),
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_AUTHOR_NAME": PERSON,
            "GIT_AUTHOR_EMAIL": GIT_EMAIL,
            "GIT_COMMITTER_NAME": PERSON,
            "GIT_COMMITTER_EMAIL": GIT_EMAIL,
        },
    )


@pytest.fixture(scope="module")
def game(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """A committed working copy: real specifications, real exports, real history."""
    root = build_game_repo(tmp_path_factory.mktemp("acceptance")).root
    (root / ".canon" / "actors.yaml").write_text(ACTORS, encoding="utf-8")
    (root / ".gitignore").write_text(".canon/index.sqlite\n.canon/reports.ndjson\n", "utf-8")
    shutil.rmtree(root / ".git")
    git(root, "init", "-q")
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", "the canon")
    return root


@pytest.fixture(scope="module")
def session(game: Path, tmp_path_factory: pytest.TempPathFactory) -> dict[str, str]:
    """The whole agent session, against a signed-in machine and a spawned server."""
    keychain = stub_keychain(tmp_path_factory.mktemp("keychain"))
    with signing_issuer(roles=(ART_DIRECTION_ROLE,)) as running:
        environment = bare_environment(keychain, **running.environment, CANON_AGENT=AGENT)
        signed_in = subprocess.run(
            [sys.executable, "-m", "cybercanon.cli", "login"],
            cwd=game,
            capture_output=True,
            text=True,
            check=False,
            env=environment,
        )
        assert signed_in.returncode == 0, signed_in.stderr
        answers = asyncio.run(_session(game, environment))
    SESSION_VOLUME["observations"] = sum(
        (game / spec).read_text(encoding="utf-8").count("- id: obs_")
        for spec in (MECH_SPEC, BARREL_SPEC)
    )
    SESSION_VOLUME["writes_attempted"] = sum(1 for name in answers if name.startswith("record"))
    return answers


async def _session(game: Path, environment: dict[str, str]) -> dict[str, str]:
    """One connection, the calls in the order the story makes them."""
    transport = StdioTransport(
        command=sys.executable,
        args=["-m", "cybercanon.cli", "mcp", "serve", str(game)],
        env=environment,
        cwd=str(game),
    )
    async with Client(transport) as client:
        answers: dict[str, str] = {
            "advertised": "\n".join(tool.name for tool in await client.list_tools())
        }
        for tool in PROHIBITED_TOOLS:
            answers[f"promote:{tool}"] = await _refused(client, tool)
        answers["record"] = await _text(
            client,
            "add_annotation",
            {"asset": MECH, "target": "head", "text": UNATTAINABLE},
        )
        answers["record-again"] = await _text(
            client,
            "add_annotation",
            {"asset": MECH, "target": "head", "text": UNATTAINABLE},
        )
        answers["record-barrel"] = await _text(
            client,
            "add_annotation",
            {"asset": BARREL, "target": "rim", "text": BARREL_UNATTAINABLE},
        )
        answers["constraints"] = await _text(client, "get_constraints", {"asset_id": MECH})
        answers["constraints-barrel"] = await _text(client, "get_constraints", {"asset_id": BARREL})
        answers["open"] = await _text(client, "get_open_annotations", {"asset_id": MECH})
        answers["report"] = await _text(
            client, "report_export", {"asset": MECH, "path": MECH_EXPORT}
        )
        return answers


async def _text(client: Client, tool: str, arguments: dict[str, Any]) -> str:
    result = await client.call_tool(tool, arguments)
    return "\n".join(block.text for block in result.content)


async def _refused(client: Client, tool: str) -> str:
    """What the server says when asked for a tool it does not have."""
    try:
        await client.call_tool(tool, {"asset": MECH, "annotation": "obs_1"})
    except Exception as refusal:
        return f"{type(refusal).__name__}: {refusal}"
    return ""


# --------------------------------------------------------------------------
# 1 and 2 — the promotion that does not exist, for the role that would have it
# --------------------------------------------------------------------------


def test_the_agent_acts_as_an_art_director(game: Path, session: dict[str, str]) -> None:
    """The refusals below are refusals of the caller, not of the person's roles.

    The credential carries the group this machine maps to `ART_DIRECTOR`, and
    the mapping is configuration — so the actor really does hold the one role
    that may promote on a human surface.
    """
    assert session["record"], "the session produced nothing"
    assert "ART_DIRECTOR" in (game / ".canon" / "actors.yaml").read_text(encoding="utf-8")


@pytest.mark.parametrize("tool", PROHIBITED_TOOLS)
def test_no_tool_exists_for_authoring_the_canon(session: dict[str, str], tool: str) -> None:
    """*"No such tool SHALL exist, and the attempt SHALL be refused."*"""
    assert tool not in session["advertised"].split("\n")
    assert "Unknown tool" in session[f"promote:{tool}"], session[f"promote:{tool}"]


def test_the_advertised_surface_is_the_eight_reads_and_the_two_writes(
    session: dict[str, str],
) -> None:
    from cybercanon.adapters.inbound.mcp.tools import TOOL_NAMES, WRITE_TOOL_NAMES

    advertised = tuple(sorted(session["advertised"].split("\n")))

    assert advertised == tuple(sorted(TOOL_NAMES))
    assert len(WRITE_TOOL_NAMES) == 2


# --------------------------------------------------------------------------
# 3 and 4 — the observation is recorded, and the budget does not move
# --------------------------------------------------------------------------


def test_the_observation_is_recorded_with_its_reason(session: dict[str, str]) -> None:
    assert "Observation" in session["record"]
    assert "unattainable_constraint" in session["record"]
    assert MECH_SPEC in session["record"]


def test_the_write_names_the_person_and_the_agent(session: dict[str, str]) -> None:
    """*"Every recorded write SHALL carry both the person and the agent."*"""
    assert SUBJECT in session["record"]
    assert AGENT in session["record"]


def test_the_response_says_the_change_is_uncommitted(session: dict[str, str]) -> None:
    """D2: a proposal a person reviews as a diff, never a fait accompli."""
    assert "not committed" in session["record"]


def test_the_recorded_budget_is_unchanged_in_the_tool_answer(session: dict[str, str]) -> None:
    assert BUDGET in session["constraints"]


def test_the_recorded_budget_is_unchanged_in_the_file(game: Path, session: dict[str, str]) -> None:
    """The bytes, not a rendering of them: *"the budget SHALL still be 12000"*."""
    assert session["record"], "the observation was recorded first"
    specification = (game / MECH_SPEC).read_text(encoding="utf-8")

    assert f"tri_budget: {BUDGET}" in specification
    assert UNATTAINABLE in specification


def test_the_only_changed_file_is_the_named_assets_specification(
    game: Path, session: dict[str, str]
) -> None:
    """*"No other file SHALL be created, modified or deleted."*"""
    assert session["record"], "the observation was recorded first"
    status = subprocess.run(
        ["git", "-C", str(game), "status", "--porcelain"],
        check=True,
        capture_output=True,
        text=True,
    )

    assert sorted(line.split()[-1] for line in status.stdout.splitlines()) == sorted(
        (BARREL_SPEC, MECH_SPEC)
    )


# --------------------------------------------------------------------------
# 5 and 6 — it cannot close it, and the report cannot block it
# --------------------------------------------------------------------------


def test_the_agent_cannot_close_its_own_observation(session: dict[str, str]) -> None:
    assert "Unknown tool" in session["promote:resolve_annotation"]


def test_a_repeat_of_the_same_observation_adds_no_second_thread(
    session: dict[str, str],
) -> None:
    """D10: one thread per issue, so a looping agent cannot bury a human one."""
    assert "already says this" in session["record-again"]


def test_the_report_returns_the_verdict_and_says_delivery_is_pending(
    session: dict[str, str],
) -> None:
    assert "PASSING" in session["report"]
    assert "the verdict stands locally" in session["report"]


def test_the_undelivered_report_is_waiting_outside_the_canon(
    game: Path, session: dict[str, str]
) -> None:
    assert session["report"], "the outcome was reported first"
    assert (game / OUTBOX_PATH).is_file()


# --------------------------------------------------------------------------
# 7 — and a person sees that a machine wrote it
# --------------------------------------------------------------------------


def test_the_open_threads_mark_the_observation_as_agent_authored(
    session: dict[str, str],
) -> None:
    assert "agent-authored" in session["open"]
    assert UNATTAINABLE in session["open"]


def test_the_compiled_briefing_a_human_reads_marks_it_too(
    game: Path, session: dict[str, str]
) -> None:
    """`canon compile` as a process: the file a contractor or a model reads."""
    assert session["record"], "the observation was recorded first"
    compiled = subprocess.run(
        [sys.executable, "-m", "cybercanon.cli", "compile", MECH_SPEC, "--stdout"],
        cwd=game,
        capture_output=True,
        text=True,
        check=False,
        env=bare_environment(),
    )

    assert compiled.returncode == 0, compiled.stderr
    assert UNATTAINABLE in compiled.stdout
    assert "agent-authored" in compiled.stdout
    assert AGENT in compiled.stdout


# --------------------------------------------------------------------------
# 8 — the exit the agent may not take, taken by a person on the same file
# --------------------------------------------------------------------------


@pytest.fixture(scope="module")
def reviewed(game: Path, session: dict[str, str]) -> str:
    """The person reads the diff and commits it — what the tool told them to do.

    D2 stops at the working copy on purpose: *"the human review of a diff is the
    thing that keeps an agent's contribution accountable"*, and the tool's own
    response says the change is uncommitted and names the file. The triage
    surface reads committed content at a pinned revision, so a person acts on an
    observation **after** they have accepted it into the history — which is the
    review step, not a formality to skip.
    """
    assert session["record"], "the observation was recorded first"
    diff = subprocess.run(
        ["git", "-C", str(game), "diff", "--stat"],
        check=True,
        capture_output=True,
        text=True,
    )
    assert MECH_SPEC in diff.stdout, "there is a diff to review"
    git(game, "add", MECH_SPEC, BARREL_SPEC)
    git(game, "commit", "-q", "-m", "record the agent's observations")
    return observation_id(game, MECH_SPEC)


def observation_id(game: Path, spec: str) -> str:
    """The identifier the agent's write left in that specification."""
    for line in (game / spec).read_text(encoding="utf-8").splitlines():
        if line.strip().startswith("- id: obs_"):
            return line.split(": ", 1)[1].strip()
    raise AssertionError("no observation was recorded")


def test_the_person_reviews_an_ordinary_diff(game: Path, session: dict[str, str]) -> None:
    """What the agent left behind is one reviewable addition, in one file."""
    assert session["record"], "the observation was recorded first"
    diff = subprocess.run(
        ["git", "-C", str(game), "diff", "--", MECH_SPEC],
        check=True,
        capture_output=True,
        text=True,
    )
    added = [line for line in diff.stdout.splitlines() if line.startswith("+") and line[1:2] != "+"]
    removed = [
        line for line in diff.stdout.splitlines() if line.startswith("-") and line[1:2] != "-"
    ]

    assert any(UNATTAINABLE in line for line in added)
    assert any("author_kind: agent" in line for line in added)
    assert removed == [], "an observation removes nothing from the specification"


def a_workspace(game: Path, asset_id: str) -> Workspace:
    """The art director, over this working copy, through the use case the web calls."""
    return Workspace(
        project=PROJECT,
        asset_id=asset_id,
        repository_host=LocalRepositoryHost(game, PROJECT),
        spec_store=GitSpecStore(game),
        actor=Actor(
            id=ActorId(SUBJECT),
            display_name=PERSON,
            roles=(Role.ART_DIRECTOR,),
            projects=(PROJECT,),
        ),
        author=GitAuthor(name=PERSON, email=GIT_EMAIL),
    )


def compiled(game: Path, spec: str) -> str:
    """`canon compile` as a process — the file a human, or a model, reads."""
    run = subprocess.run(
        [sys.executable, "-m", "cybercanon.cli", "compile", spec, "--stdout"],
        cwd=game,
        capture_output=True,
        text=True,
        check=False,
        env=bare_environment(),
    )
    assert run.returncode == 0, run.stderr
    return run.stdout


def test_a_person_resolves_the_agents_observation(
    game: Path, reviewed: str, session: dict[str, str]
) -> None:
    """Exit two, on the observation the agent could not close itself.

    *"Subsequent compilations SHALL NOT contain it."* The budget the agent said
    was unattainable is still 12000 afterwards, which is the whole point: the
    person decided what to do about the conflict, and the specification records
    their decision rather than the agent's convenience.
    """
    assert UNATTAINABLE in compiled(game, MECH_SPEC), "it is in the briefing first"

    ran(resolve_annotation(a_workspace(game, MECH), reviewed, RESOLUTION))
    after = compiled(game, MECH_SPEC)
    specification = (game / MECH_SPEC).read_text(encoding="utf-8")

    assert UNATTAINABLE not in after, "the resolved thread left the briefing"
    assert f"tri_budget: {BUDGET}" in specification, "and the budget still did not move"


def test_a_person_promotes_the_other_observation_into_a_rule(game: Path, reviewed: str) -> None:
    """Exit one, taken by the person on the asset whose budget really is too small.

    *"The resulting rule SHALL be attributed to the person who promoted it and
    SHALL NOT be attributed to the agent."* The agent said the rim cannot hold
    its shape in a hundred triangles; a person turned that into a durable rule
    about the rim, and left the hundred alone.
    """
    identifier = observation_id(game, BARREL_SPEC)

    promoted = ran(
        promote_annotation(
            a_workspace(game, BARREL),
            identifier,
            PROMOTED_RULE,
            PromotionTarget.SILHOUETTE_RULES,
        )
    )
    specification = (game / BARREL_SPEC).read_text(encoding="utf-8")

    assert promoted.annotation.is_promoted
    assert PROMOTED_RULE in specification, "the rule is in the specification now"
    assert f"tri_budget: {BARREL_BUDGET}" in specification, "and the budget did not move"


def test_the_promoted_rule_is_the_persons_and_not_the_agents(game: Path, reviewed: str) -> None:
    """Read the briefing back: the rule carries no agent anywhere near it."""
    briefing = compiled(game, BARREL_SPEC)

    assert PROMOTED_RULE in briefing
    rule_line = next(line for line in briefing.splitlines() if PROMOTED_RULE in line)
    assert AGENT not in rule_line
    assert "agent-authored" not in rule_line


def test_the_promoted_observation_left_the_open_threads(game: Path, reviewed: str) -> None:
    """*"Subsequent compilations SHALL NOT contain it."* — the two-exit discipline."""
    assert BARREL_UNATTAINABLE not in compiled(game, BARREL_SPEC)


def test_the_promotion_is_a_commit_in_the_persons_name(game: Path, reviewed: str) -> None:
    """Attribution survives the exit: the durable rule is the person's commit."""
    log = subprocess.run(
        ["git", "-C", str(game), "log", "-1", "--format=%an <%ae> %s", "--", BARREL_SPEC],
        check=True,
        capture_output=True,
        text=True,
    )

    assert GIT_EMAIL in log.stdout
    assert AGENT not in log.stdout


def test_the_session_volume_is_recorded_for_the_rate_limit(session: dict[str, str]) -> None:
    """D9's open question: the numbers are configuration, and this is the input.

    One real session of a modelling agent that could not meet a budget produced
    **one** observation on the asset — the repeat was suppressed rather than
    recorded — which is the volume the default limit of ten per hour per actor
    and asset is set against. A session that ever approaches that limit is a
    looping agent, which is exactly what the limit is for.
    """
    from cybercanon.domain.observations import DEFAULT_OBSERVATION_LIMIT, DEFAULT_WINDOW_SECONDS

    assert SESSION_VOLUME["writes_attempted"] == 3, "three writes were attempted"
    assert SESSION_VOLUME["observations"] == 2, "two threads exist, one per asset"
    assert SESSION_VOLUME["observations"] < DEFAULT_OBSERVATION_LIMIT
    assert DEFAULT_WINDOW_SECONDS == 3600.0
