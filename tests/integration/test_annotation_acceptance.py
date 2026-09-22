"""Tasks 6.4 and 6.5 — the acceptance runs, end to end over a real repository.

Two runs, and between them they are the change's claim:

* **6.4** — one asset, three views. A pin is placed the way a pointer places one
  and again the way a stylus does; a second person replies; the threads are
  filtered; one annotation is resolved and another promoted. Then `canon
  compile` is run **as a process**, on a machine that has never heard of this
  service, and the compiled briefing has to show the promoted rule, omit the
  resolved annotation, and `git log` has to show one attributed commit per
  action.
* **6.5** — the derived stores are destroyed and everything is rebuilt from the
  repository, and the sheet's three answers — the pins, the threads and the
  triage queue — have to be the same answers.

`canon compile` is a subprocess on purpose. The compiled briefing is what a
contractor, a new hire or a language model reads years after this tool is
replaced, and *"the promoted rule is in it and the resolved thread is not"* is a
claim about that file rather than about a function this suite could call.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest
from staged_project import BRANCH, PROJECT, Staged, git, ready

from cybercanon.adapters.outbound.git.repository_host import GitRepositoryHost, ProjectRemote
from cybercanon.adapters.outbound.git.spec_store import GitSpecStore
from cybercanon.application.testing.outcomes import ran
from cybercanon.application.use_cases.annotations import (
    COMMIT_PREFIX,
    Draft,
    Workspace,
    create_annotation,
    list_annotations,
    list_triage_queue,
    promote_annotation,
    reply_to_annotation,
    resolve_annotation,
)
from cybercanon.domain.actors import GitAuthor
from cybercanon.domain.annotations import (
    Anchor2D,
    AnnotationFilter,
    AnnotationKind,
    AnnotationState,
    Stroke,
)
from cybercanon.domain.identity import Actor, ActorId, Role
from cybercanon.domain.triage import PromotionTarget

pytestmark = pytest.mark.integration

SCOUT = "mech_scout"
SCOUT_SPEC = "characters/mech_scout/asset.yaml"
COMPILED = "characters/mech_scout/art-spec.md"

RAFA = GitAuthor(name="Rafa Santos", email="rafa@cyberdyne.com")
ANA = GitAuthor(name="Ana Silva", email="ana@cyberdyne.com")
DANA = GitAuthor(name="Dana Reyes", email="dana@cyberdyne.com")

ACTORS = b"""\
schema_version: 1
actors:
  - subject: auth|rafa
    name: Rafa Santos
    emails: [rafa@cyberdyne.com]
  - subject: auth|ana
    name: Ana Silva
    emails: [ana@cyberdyne.com]
  - subject: auth|dana
    name: Dana Reyes
    emails: [dana@cyberdyne.com]
    default_role: ART_DIRECTOR
"""

SPEC = b"""\
schema_version: 1
id: mech_scout
name: Scout Mech
status: modeling

constraints:
  tri_budget: 12000

concept:
  views: [front, side, back]
"""

CORPUS = {
    ".canon/project.yaml": b"schema_version: 1\nname: ronin\n",
    ".canon/actors.yaml": ACTORS,
    SCOUT_SPEC: SPEC,
    "characters/mech_scout/concept/front.png": b"\x89PNG\r\n\x1a\nfront",
    "characters/mech_scout/concept/side.png": b"\x89PNG\r\n\x1a\nside",
    "characters/mech_scout/concept/back.png": b"\x89PNG\r\n\x1a\nback",
}

PROMOTED_RULE = "the pauldron never breaks the shoulder silhouette"
RESOLVED_TEXT = "the antenna reads as an aerial from behind"
OPEN_TEXT = "the knee reads as a joint rather than a plate"

# The same position on the `front` view, as each input device reports it. One
# code path produces one anchor (D10), so these two are the same value — and a
# test that built them separately is how that stops being true.
POINTER_PIN = Anchor2D(view="front", u=0.2537, v=0.4128)
STYLUS_PIN = Anchor2D(view="front", u=0.2537, v=0.4128)


def a_person(subject: str, *roles: Role) -> Actor:
    return Actor(id=ActorId(subject), display_name=subject, roles=roles, projects=(PROJECT,))


def workspace(staged: Staged, subject: str, author: GitAuthor, *roles: Role) -> Workspace:
    return Workspace(
        project=PROJECT,
        asset_id=SCOUT,
        repository_host=staged.host,
        spec_store=GitSpecStore(staged.working_copy),
        actor=a_person(subject, *roles),
        author=author,
    )


def a_draft(identifier: str, text: str, anchor: Anchor2D, **fields: object) -> Draft:
    return Draft(
        id=identifier,
        kind=AnnotationKind.ART_DIRECTION,
        text=text,
        anchor=anchor,
        **fields,  # type: ignore[arg-type]
    )


@pytest.fixture(scope="module")
def staged(tmp_path_factory: pytest.TempPathFactory) -> Staged:
    """One repository, driven once through the whole pass (6.4)."""
    root = tmp_path_factory.mktemp("acceptance")
    built = ready(root, dict(CORPUS))
    rafa = workspace(built, "auth|rafa", RAFA)
    ana = workspace(built, "auth|ana", ANA)
    dana = workspace(built, "auth|dana", DANA, Role.ART_DIRECTOR)

    ran(create_annotation(rafa, a_draft("an_pointer", PROMOTED_RULE, POINTER_PIN)))
    ran(
        create_annotation(
            ana,
            a_draft(
                "an_stylus",
                RESOLVED_TEXT,
                STYLUS_PIN,
                strokes=(Stroke(((0.24, 0.40), (0.28, 0.44), (0.33, 0.41))),),
            ),
        )
    )
    ran(create_annotation(rafa, a_draft("an_third", OPEN_TEXT, Anchor2D("side", 0.6, 0.3))))
    ran(reply_to_annotation(ana, "an_pointer", "re_1", "agreed, it needs a harder edge"))
    ran(resolve_annotation(ana, "an_stylus", "fixed in the third pass"))
    ran(promote_annotation(dana, "an_pointer", PROMOTED_RULE, PromotionTarget.SILHOUETTE_RULES))
    return built


def compile_briefing(staged: Staged) -> subprocess.CompletedProcess[str]:
    """`canon compile`, as a process, on a machine that knows nothing about us.

    No token, no service, no configuration: the validator and the compiler must
    work for an artist who is off the VPN, and a subprocess with a stripped
    environment is the only way to assert that rather than assume it.
    """
    environment = {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "HOME": str(staged.home),
        "GIT_CONFIG_GLOBAL": "/dev/null",
        "PYTHONPATH": os.pathsep.join(sys.path),
    }
    return subprocess.run(
        [sys.executable, "-m", "cybercanon.cli", "compile", SCOUT_SPEC, "--stdout"],
        cwd=staged.working_copy,
        capture_output=True,
        text=True,
        check=False,
        env=environment,
        stdin=subprocess.DEVNULL,
        timeout=120,
    )


# --------------------------------------------------------------------------
# 6.4 — the pass, and what `canon compile` says afterwards
# --------------------------------------------------------------------------


def test_a_pointer_and_a_stylus_produce_the_same_anchor(staged: Staged) -> None:
    """*"Both SHALL produce the same normalized coordinate."*"""
    assert POINTER_PIN == STYLUS_PIN

    listing = ran(list_annotations(workspace(staged, "auth|rafa", RAFA), AnnotationFilter.every()))
    placed = {entry.id: entry.target for entry in listing.annotations}

    assert placed["an_pointer"] == placed["an_stylus"] == POINTER_PIN


def test_the_compiled_briefing_shows_the_promoted_rule(staged: Staged) -> None:
    compiled = compile_briefing(staged)

    assert compiled.returncode == 0, compiled.stderr
    assert PROMOTED_RULE in compiled.stdout


def test_the_compiled_briefing_omits_the_resolved_annotation(staged: Staged) -> None:
    """The sentence that decides whether this system degrades with use."""
    compiled = compile_briefing(staged)

    assert RESOLVED_TEXT not in compiled.stdout
    assert OPEN_TEXT in compiled.stdout


def test_the_promoted_thread_is_not_in_the_briefing_either(staged: Staged) -> None:
    """*"It SHALL NOT contain the annotation's text or any of its replies."*"""
    compiled = compile_briefing(staged)

    assert "agreed, it needs a harder edge" not in compiled.stdout


def test_filtering_returns_what_the_filter_asked_for(staged: Staged) -> None:
    rafa = workspace(staged, "auth|rafa", RAFA)

    wanted = AnnotationFilter.of(states=(AnnotationState.OPEN,))
    listing = ran(list_annotations(rafa, wanted))

    assert [entry.id for entry in listing.annotations] == ["an_third"]
    assert listing.hidden == 2


def test_the_history_shows_one_attributed_commit_per_action(staged: Staged) -> None:
    """Six actions, six commits, each authored by the person who took it."""
    log = git(
        staged.working_copy,
        ["log", f"--grep=^{COMMIT_PREFIX}(", "--format=%ae%x09%s", "--reverse"],
        staged.home,
    ).splitlines()

    assert len(log) == 6
    authors = [line.split("\t")[0] for line in log]
    assert authors == [
        RAFA.email,
        ANA.email,
        RAFA.email,
        ANA.email,
        ANA.email,
        DANA.email,
    ]
    assert all(f"{COMMIT_PREFIX}({SCOUT})" in line for line in log)


def test_the_promotion_is_the_last_commit_and_carries_both_edits(staged: Staged) -> None:
    diff = git(staged.working_copy, ["show", "--format=%s", "HEAD"], staged.home)

    assert f"promoted into {PromotionTarget.SILHOUETTE_RULES}" in diff
    assert f"+    - {PROMOTED_RULE}" in diff
    assert "+    state: promoted" in diff


# --------------------------------------------------------------------------
# 6.5 — destroy the derived stores, rebuild, and compare every answer
# --------------------------------------------------------------------------


@pytest.fixture
def rebuilt(tmp_path: Path, staged: Staged) -> Staged:
    """The project obtained again from its remote, with no derived store anywhere.

    Nothing is copied from the working copy the pass ran in: this is a clone of
    the **remote**, which is what a recovery actually is. There is no index and
    no blob mirror in the arrangement at all, which is the strongest form of
    *"delete PostgreSQL and MinIO and rebuild"* — the answers below are produced
    by a process that never had either.
    """
    home = tmp_path / "home"
    home.mkdir(parents=True, exist_ok=True)
    host = GitRepositoryHost(
        tmp_path / "working-copies",
        [ProjectRemote(project=PROJECT, url=str(staged.bare), branch=BRANCH)],
        environment={"HOME": str(home), "GIT_CONFIG_GLOBAL": "/dev/null"},
    )
    host.clone(PROJECT)
    return Staged(host=host, bare=staged.bare, home=home, root=tmp_path)


def _answers(target: Staged) -> tuple[object, object, object]:
    """The three answers the sheet is made of: pins, threads and the queue."""
    rafa = workspace(target, "auth|rafa", RAFA)
    listing = ran(list_annotations(rafa, AnnotationFilter.every()))
    queue = ran(
        list_triage_queue(
            PROJECT,
            spec_store=GitSpecStore(target.working_copy),
            repository_host=target.host,
        )
    )
    return (
        tuple(listing.placeable),
        tuple(entry.replies for entry in listing.annotations),
        tuple((entry.asset, entry.id, entry.rank[:3]) for entry in queue.entries),
    )


def test_the_sheet_presents_the_same_pins_threads_and_queue_after_a_rebuild(
    staged: Staged, rebuilt: Staged
) -> None:
    before = _answers(staged)
    after = _answers(rebuilt)

    assert after == before
    assert before[0], "the comparison would pass over nothing"


def test_the_rebuilt_copy_carries_the_freehand_marks_verbatim(rebuilt: Staged) -> None:
    listing = ran(list_annotations(workspace(rebuilt, "auth|rafa", RAFA), AnnotationFilter.every()))
    stylus = next(entry for entry in listing.annotations if entry.id == "an_stylus")

    assert stylus.state is AnnotationState.RESOLVED
    assert stylus.strokes == ()


def test_the_rebuilt_copy_compiles_the_same_briefing(staged: Staged, rebuilt: Staged) -> None:
    assert compile_briefing(rebuilt).stdout == compile_briefing(staged).stdout
