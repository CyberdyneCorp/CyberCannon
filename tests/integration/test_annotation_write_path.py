"""Tasks 3.1 to 3.3 and 3.5 — annotations against a real git repository.

Everything here runs over a real bare remote and a real working copy, because
the three claims being made are claims about **git**: that a created annotation
appears in the history attributed to the person who made it, that adding one
leaves every unrelated line of a hand-authored `asset.yaml` byte-identical, and
that the commits are filterable in a log. None of those is checkable against a
dictionary.

The last suite is the index-rebuild one, and its shape is the argument: the
annotations are read back by dropping *everything* and re-reading the
repository, because that is the recovery `project.md` requires to always be
valid.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from staged_project import BRANCH, PROJECT, Staged, git, ready

from cybercanon.adapters.outbound.git.spec_store import GitSpecStore
from cybercanon.application.testing.outcomes import ran, refused
from cybercanon.application.use_cases.annotations import (
    COMMIT_PREFIX,
    Draft,
    Workspace,
    create_annotation,
    delete_annotation,
    list_annotations,
    promote_annotation,
    reply_to_annotation,
    resolve_annotation,
)
from cybercanon.domain.actors import GitAuthor
from cybercanon.domain.annotations import Anchor2D, AnnotationFilter, AnnotationKind, Stroke
from cybercanon.domain.identity import Actor, ActorId, Role
from cybercanon.domain.triage import PromotionTarget

pytestmark = pytest.mark.integration

SCOUT = "mech_scout"
SCOUT_SPEC = "characters/mech_scout/asset.yaml"

RAFA_SUBJECT = "auth|rafa"
DANA_SUBJECT = "auth|dana"

RAFA = GitAuthor(name="Rafa Santos", email="rafa@cyberdyne.com")
DANA = GitAuthor(name="Dana Reyes", email="dana@cyberdyne.com")

ACTORS = b"""\
schema_version: 1
actors:
  - subject: auth|rafa
    name: Rafa Santos
    emails: [rafa@cyberdyne.com]
  - subject: auth|dana
    name: Dana Reyes
    emails: [dana@cyberdyne.com]
    default_role: ART_DIRECTOR
"""

AUTHORED = b"""\
schema_version: 1
id: mech_scout
name: Scout Mech        # the id is what everything refers to, not this
status: modeling

# engineering fixed these at the kick-off, and nothing may rewrite them
constraints:
  tri_budget: 12000
  lods: [8000, 4000]
  naming: "SM_{asset}_LOD{n}"

design:
  sockets:
    - name: SOCKET_muzzle_l   # the VFX attaches here
      purpose: muzzle flash

concept:
  views: [front, side, back]

links:
  source: art/source/mech_scout.blend
"""
"""A hand-authored specification: comments, quoting, inline lists, blank lines."""

CORPUS = {
    ".canon/project.yaml": b"schema_version: 1\nname: ronin\n",
    ".canon/actors.yaml": ACTORS,
    SCOUT_SPEC: AUTHORED,
}

PIN = Anchor2D(view="front", u=0.25, v=0.4)
TEXT = "the pauldron reads as a backpack at 15 m"


def a_person(subject: str = RAFA_SUBJECT, *roles: Role) -> Actor:
    return Actor(id=ActorId(subject), display_name=subject, roles=roles, projects=(PROJECT,))


@pytest.fixture
def staged(tmp_path: Path) -> Staged:
    return ready(tmp_path, dict(CORPUS))


def workspace(staged: Staged, actor: Actor, author: GitAuthor = RAFA) -> Workspace:
    return Workspace(
        project=PROJECT,
        asset_id=SCOUT,
        repository_host=staged.host,
        spec_store=GitSpecStore(staged.working_copy),
        actor=actor,
        author=author,
    )


def a_draft(identifier: str = "an_1", text: str = TEXT, **fields: object) -> Draft:
    return Draft(
        id=identifier,
        kind=AnnotationKind.ART_DIRECTION,
        text=text,
        anchor=PIN,
        **fields,  # type: ignore[arg-type]
    )


def log(staged: Staged, *arguments: str) -> str:
    return git(staged.working_copy, ["log", *arguments], staged.home)


def spec_text(staged: Staged) -> str:
    return (staged.working_copy / SCOUT_SPEC).read_text(encoding="utf-8")


# --------------------------------------------------------------------------
# 3.1 — the commit is in the history, attributed to the person
# --------------------------------------------------------------------------


def test_a_created_annotation_appears_in_the_history_attributed_to_the_person(
    staged: Staged,
) -> None:
    ran(create_annotation(workspace(staged, a_person()), a_draft()))

    assert "an_1" in spec_text(staged)
    assert RAFA.email in log(staged, "-1", "--format=%ae")
    assert RAFA.name in log(staged, "-1", "--format=%an")


def test_the_commit_is_on_the_branch_and_not_only_in_the_working_copy(
    staged: Staged,
) -> None:
    """*"A commit that cannot be pushed did not happen."*"""
    ran(create_annotation(workspace(staged, a_person()), a_draft()))

    remote = git(staged.bare, ["log", "-1", "--format=%s"], staged.home)

    assert COMMIT_PREFIX in remote


def test_a_person_with_no_mapped_git_identity_writes_nothing(staged: Staged) -> None:
    before = spec_text(staged)

    outcome = create_annotation(workspace(staged, a_person("auth|nobody"), author=None), a_draft())

    assert ".canon/actors.yaml" in refused(outcome).message
    assert spec_text(staged) == before


# --------------------------------------------------------------------------
# 3.2 — the comment-preserving round trip
# --------------------------------------------------------------------------


def _unrelated(text: str) -> list[str]:
    """Every line of the file that is not part of the annotation block."""
    lines = text.splitlines()
    if "annotations:" not in lines:
        return lines
    return lines[: lines.index("annotations:")]


def test_adding_replying_and_resolving_leaves_every_unrelated_line_byte_identical(
    staged: Staged,
) -> None:
    """The risk most likely to lose a team's trust in one afternoon (D4)."""
    before = _unrelated(AUTHORED.decode("utf-8"))
    person = a_person()

    ran(create_annotation(workspace(staged, person), a_draft()))
    ran(reply_to_annotation(workspace(staged, person), "an_1", "re_1", "agreed"))
    ran(resolve_annotation(workspace(staged, person), "an_1", "fixed in pass 3"))

    assert _unrelated(spec_text(staged)) == before


def test_the_comments_and_the_quoting_survive(staged: Staged) -> None:
    ran(create_annotation(workspace(staged, a_person()), a_draft()))

    written = spec_text(staged)

    assert "# the id is what everything refers to, not this" in written
    assert "# engineering fixed these at the kick-off" in written
    assert '"SM_{asset}_LOD{n}"' in written
    assert "lods: [8000, 4000]" in written


def test_withdrawing_the_only_annotation_leaves_the_file_as_it_was(
    staged: Staged,
) -> None:
    person = a_person()
    ran(create_annotation(workspace(staged, person), a_draft()))

    ran(delete_annotation(workspace(staged, person), "an_1"))

    assert spec_text(staged) == AUTHORED.decode("utf-8")


def test_a_freehand_mark_round_trips_through_the_file(staged: Staged) -> None:
    drawn = (Stroke(((0.1, 0.1), (0.2, 0.25), (0.34, 0.31))),)

    ran(create_annotation(workspace(staged, a_person()), a_draft(strokes=drawn)))

    listing = ran(list_annotations(workspace(staged, a_person()), AnnotationFilter.every()))
    assert listing.annotations[0].strokes == drawn


# --------------------------------------------------------------------------
# 3.3 — the commits are legible, and a promotion is one diff
# --------------------------------------------------------------------------


def test_every_annotation_commit_names_the_asset_and_the_annotation(
    staged: Staged,
) -> None:
    person = a_person()
    ran(create_annotation(workspace(staged, person), a_draft()))
    ran(reply_to_annotation(workspace(staged, person), "an_1", "re_1", "agreed"))

    subjects = log(staged, "-2", "--format=%s").splitlines()

    assert all(line.startswith(f"{COMMIT_PREFIX}({SCOUT}):") for line in subjects), subjects
    assert all("an_1" in line for line in subjects)


def test_annotation_commits_are_filterable_in_a_log(staged: Staged) -> None:
    """One commit per reply is only bearable if `git log --grep` separates them."""
    person = a_person()
    ran(create_annotation(workspace(staged, person), a_draft()))
    ran(reply_to_annotation(workspace(staged, person), "an_1", "re_1", "agreed"))

    found = log(staged, f"--grep=^{COMMIT_PREFIX}(", "--format=%s").splitlines()

    assert len(found) == 2


def test_a_promotion_shows_the_added_rule_and_the_retired_annotation_in_one_diff(
    staged: Staged,
) -> None:
    ran(create_annotation(workspace(staged, a_person()), a_draft()))

    ran(
        promote_annotation(
            workspace(staged, a_person(DANA_SUBJECT, Role.ART_DIRECTOR), author=DANA),
            "an_1",
            "the pauldron never breaks the shoulder silhouette",
            PromotionTarget.SILHOUETTE_RULES,
        )
    )

    diff = git(staged.working_copy, ["show", "--format=%s", "HEAD"], staged.home)
    assert "+    - the pauldron never breaks the shoulder silhouette" in diff
    assert "+    state: promoted" in diff
    assert "-    state: open" in diff
    assert DANA.email in git(staged.working_copy, ["log", "-1", "--format=%ae"], staged.home)


def test_a_promotion_is_one_commit_and_not_two(staged: Staged) -> None:
    """D6: there is no intermediate state in which the rule exists and the thread is open."""
    ran(create_annotation(workspace(staged, a_person()), a_draft()))
    before = len(log(staged, "--format=%H").splitlines())

    ran(
        promote_annotation(
            workspace(staged, a_person(DANA_SUBJECT, Role.ART_DIRECTOR), author=DANA),
            "an_1",
            "the pauldron never breaks the shoulder silhouette",
            PromotionTarget.SILHOUETTE_RULES,
        )
    )

    assert len(log(staged, "--format=%H").splitlines()) == before + 1


# --------------------------------------------------------------------------
# 3.5 — nothing is readable only from a derived store
# --------------------------------------------------------------------------


def test_every_thread_is_recovered_by_re_reading_the_repository_from_scratch(
    tmp_path: Path, staged: Staged
) -> None:
    """*"Deleting every derived store and re-reading the repository SHALL restore
    every annotation and every thread unchanged."*"""
    person = a_person()
    ran(
        create_annotation(
            workspace(staged, person), a_draft(strokes=(Stroke(((0.1, 0.1), (0.4, 0.4))),))
        )
    )
    ran(reply_to_annotation(workspace(staged, person), "an_1", "re_1", "agreed"))
    before = ran(list_annotations(workspace(staged, person), AnnotationFilter.every()))

    fresh = tmp_path / "fresh"
    git(None, ["clone", "--quiet", str(staged.bare), str(fresh)], staged.home)
    rebuilt = GitSpecStore(fresh).load(SCOUT_SPEC).asset

    assert rebuilt.annotations == before.annotations
    assert rebuilt.annotations[0].replies == before.annotations[0].replies
    assert rebuilt.annotations[0].strokes == before.annotations[0].strokes


def test_a_promoted_rule_survives_the_same_recovery(tmp_path: Path, staged: Staged) -> None:
    ran(create_annotation(workspace(staged, a_person()), a_draft()))
    ran(
        promote_annotation(
            workspace(staged, a_person(DANA_SUBJECT, Role.ART_DIRECTOR), author=DANA),
            "an_1",
            "the pauldron never breaks the shoulder silhouette",
            PromotionTarget.SILHOUETTE_RULES,
        )
    )

    fresh = tmp_path / "fresh"
    git(None, ["clone", "--quiet", str(staged.bare), str(fresh)], staged.home)
    rebuilt = GitSpecStore(fresh).load(SCOUT_SPEC).asset

    assert rebuilt.concept is not None
    assert "the pauldron never breaks the shoulder silhouette" in rebuilt.concept.silhouette_rules
    assert rebuilt.annotations[0].has_exited
    assert BRANCH  # the branch the push landed on, named by the staging helper
