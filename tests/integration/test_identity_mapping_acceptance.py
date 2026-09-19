"""Task 6.7 — the identity-mapping acceptance test, over a repository with real history.

Attribution is half the value of the tool, and it breaks *silently*: the Rafa who
is recorded as an asset's art owner and the `rafa@cyberdyne.com` who committed
that file are two different people in the history until something binds them.
Nothing in a unit test notices that, because a unit test hands the mapping the
emails it expects to see.

So this builds a real git repository — the worked example, committed by two
people, one of whom the mapping knows — and asserts the three things the
acceptance criterion names:

* **every mapped git author is reported as the person wherever a name appears** —
  the location answer, the listing, and the commit author all render `Rafa`;
* **every unmapped author is reported as unmapped and listed for completion** —
  the contractor who committed once and the owner nobody bound both carry their
  raw address, marked, and both appear in `canon actors unmapped`;
* **no name resolves to the wrong person** — a near-miss address is an unknown
  actor, never the similar mapped one, because matching is exact and never fuzzy.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from cybercanon.adapters.wiring.build import build_container
from cybercanon.application.testing.outcomes import ran
from cybercanon.application.use_cases.lookup_assets import ART, CODE, DESIGN
from cybercanon.domain.actors import resolve_git_author
from cybercanon.domain.identity import UNMAPPED_MARK

pytestmark = pytest.mark.integration

MECH = "mech_scout"
SPEC = "characters/mech_scout/asset.yaml"

RAFA = "rafa@cyberdyne.com"
RAFA_NAME = "Rafa"
DANI = "dani@cyberdyne.com"
NEAR_MISS = "r.santos@cyberdyne.com"
CONTRACTOR = "contractor@example.com"

MAPPING = f"""\
schema_version: 1
actors:
  - subject: auth|rafa
    display_name: {RAFA_NAME}
    emails: [{RAFA}]
    default_role: artist
"""
"""One person bound, on purpose: the interesting half is everybody else."""


def git(root: Path, *arguments: str, author: str = RAFA, name: str = RAFA_NAME) -> str:
    environment = {
        **os.environ,
        "HOME": str(root),
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_AUTHOR_NAME": name,
        "GIT_AUTHOR_EMAIL": author,
        "GIT_COMMITTER_NAME": name,
        "GIT_COMMITTER_EMAIL": author,
    }
    completed = subprocess.run(
        ["git", "-C", str(root), *arguments],
        check=True,
        capture_output=True,
        text=True,
        env=environment,
    )
    return completed.stdout


def canon(repo: Path, *arguments: str) -> subprocess.CompletedProcess[str]:
    """`canon`, with nothing in the environment that could identify anybody."""
    stripped = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith(("CANON_", "CYBERDYNE_", "GIT_")) and key != "HOME"
    }
    return subprocess.run(
        [sys.executable, "-m", "cybercanon.cli", *arguments],
        cwd=repo,
        capture_output=True,
        text=True,
        check=False,
        env=stripped,
    )


@pytest.fixture(scope="module")
def history(tmp_path_factory: pytest.TempPathFactory, repo_root: Path) -> Path:
    """The worked example, committed twice, by one known person and one stranger."""
    root = tmp_path_factory.mktemp("ronin")
    shutil.copytree(repo_root / "examples" / "ronin", root, dirs_exist_ok=True)
    spec = root / SPEC
    spec.write_text(
        spec.read_text(encoding="utf-8")
        .replace("owner_art: rafa", f"owner_art: {RAFA}")
        .replace("owner_design: dani", f"owner_design: {DANI}")
        .replace("owner_code: leo", f"owner_code: {NEAR_MISS}"),
        encoding="utf-8",
    )
    (root / ".canon" / "actors.yaml").write_text(MAPPING, encoding="utf-8")
    (root / ".gitignore").write_text(
        (repo_root / ".gitignore").read_text(encoding="utf-8"), encoding="utf-8"
    )
    git(root, "init", "-q")
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", "the canon, as its art director committed it")
    (root / "characters" / "mech_scout" / "notes.md").write_text("a pass\n", encoding="utf-8")
    git(root, "add", "-A")
    git(
        root,
        "commit",
        "-q",
        "-m",
        "a contractor's pass",
        author=CONTRACTOR,
        name="A Contractor",
    )
    return root


@pytest.fixture(scope="module")
def container(history: Path):  # type: ignore[no-untyped-def]
    built = build_container(history)
    ran(built.rebuild_index())
    return built


# --------------------------------------------------------------------------
# A mapped person is that person, everywhere a name appears
# --------------------------------------------------------------------------


def test_a_mapped_owner_is_named_as_the_person_in_the_location_answer(container) -> None:  # type: ignore[no-untyped-def]
    owner = ran(container.where_is(MECH)).owner(ART)

    assert owner.recorded == RAFA
    assert owner.display == RAFA_NAME
    assert not owner.is_unmapped


def test_the_same_person_renders_identically_in_a_listing(container) -> None:  # type: ignore[no-untyped-def]
    (row,) = [row for row in ran(container.list_assets()).rows if row.asset_id == MECH]

    assert row.owner(ART).display == ran(container.where_is(MECH)).owner(ART).display


def test_the_same_person_renders_identically_as_a_commit_author(container, history: Path) -> None:  # type: ignore[no-untyped-def]
    """One person, one presentation, whether the name came from a file or a commit."""
    mapping = container.spec_store.load_actor_mapping("").mapping
    authors = git(history, "log", "--format=%ae").split()

    assert RAFA in authors
    assert resolve_git_author(mapping, RAFA).display == RAFA_NAME
    assert (
        resolve_git_author(mapping, RAFA).display
        == ran(container.where_is(MECH)).owner(ART).display
    )


# --------------------------------------------------------------------------
# An unmapped author keeps its address, marked, and is listed for completion
# --------------------------------------------------------------------------


def test_an_unmapped_owner_shows_the_raw_address_marked_unmapped(container) -> None:  # type: ignore[no-untyped-def]
    owner = ran(container.where_is(MECH)).owner(DESIGN)

    assert owner.is_unmapped
    assert DANI in owner.display
    assert UNMAPPED_MARK in owner.display


def test_an_unmapped_commit_author_and_owner_are_both_listed_for_completion(
    container,  # type: ignore[no-untyped-def]
) -> None:
    """History and specification content are both sources of somebody to bind."""
    listed = ran(container.unmapped_authors()).emails

    assert CONTRACTOR in listed, "a commit author nobody bound must be listed"
    assert DANI in listed, "a recorded owner nobody bound must be listed"
    assert RAFA not in listed, "a bound address is not work that is left"


def test_the_command_lists_them_with_no_credential_and_no_identity_service(
    history: Path,
) -> None:
    result = canon(history, "actors", "unmapped")

    assert result.returncode == 0, result.stderr
    assert CONTRACTOR in result.stdout
    assert DANI in result.stdout
    assert RAFA not in result.stdout


# --------------------------------------------------------------------------
# No name resolves to the wrong person
# --------------------------------------------------------------------------


def test_a_near_miss_address_is_never_resolved_to_the_similar_mapped_person(
    container,  # type: ignore[no-untyped-def]
) -> None:
    owner = ran(container.where_is(MECH)).owner(CODE)

    assert owner.recorded == NEAR_MISS
    assert owner.is_unmapped
    assert RAFA_NAME not in owner.display


def test_the_mapping_itself_passes_the_lint_path(history: Path) -> None:
    """The mapping is authored content, so it is checked where the specifications are."""
    result = canon(history, "check")

    assert result.returncode == 0, result.stdout + result.stderr
    assert "PASSING" in result.stdout
