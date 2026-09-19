"""Tasks 4.2 and 4.4 — history and the actor mapping against real repositories.

The port conformance suite already runs `GitSpecStore` and the in-memory fake
through one contract, so what is left here is what only a real repository can
show, and each case is a way history can be *missing* rather than present:

* a **shallow clone**, which is the case D10 names — the commit exists in the
  world and not in this checkout, and `diff_spec` must report that the range is
  unavailable rather than end the session;
* a directory that is **not a repository at all** — a tarball, a container
  image, an artist's unzipped folder — where every file is current and nothing
  has a previous revision;
* a `.canon/actors.yaml` **on disk**, in the three shapes a project can have it:
  authored, absent, and unreadable.

The mapping's tolerance is asserted here rather than in the contract because it
is a property of the *file*: an entry naming a role that does not exist must
still parse, so that the structural checks can report it by name. A parser that
refused it would turn one typo into "this project has no mapping", and every
author in the repository would silently become unmapped.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

from cybercanon.adapters.outbound.git.spec_store import GitSpecStore
from cybercanon.application.ports.spec_store import HistoryUnavailable
from cybercanon.domain.actor_checks import RULE_UNPARSEABLE, check_mapping
from cybercanon.domain.actors import ACTORS_PATH
from cybercanon.domain.identity import Role

pytestmark = pytest.mark.integration

SPEC_PATH = "characters/mech_scout/asset.yaml"

SPEC_TEMPLATE = """\
schema_version: 1
id: mech_scout
name: Scout Mech
status: modeling
constraints:
  tri_budget: {budget}
"""

BUDGET_THEN = 12000
BUDGET_NOW = 9000

ACTORS_YAML = """\
schema_version: 1
actors:
  - subject: auth|rafa
    display_name: Rafa
    emails:
      - rafa@cyberdyne.com
    default_role: ARTIST
"""

ACTORS_WITH_UNKNOWN_ROLE = """\
schema_version: 1
actors:
  - subject: auth|rafa
    display_name: Rafa
    emails:
      - rafa@cyberdyne.com
    default_role: WIZARD
"""

BROKEN_ACTORS_YAML = 'actors: [ {subject: "auth|rafa"\n'


def _git(root: Path, *arguments: str) -> subprocess.CompletedProcess[bytes]:
    """One git command, isolated from whatever this machine's git is configured to do."""
    environment = {
        **os.environ,
        "HOME": str(root),
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_AUTHOR_NAME": "Rafa",
        "GIT_AUTHOR_EMAIL": "rafa@cyberdyne.com",
        "GIT_COMMITTER_NAME": "Rafa",
        "GIT_COMMITTER_EMAIL": "rafa@cyberdyne.com",
    }
    return subprocess.run(
        ["git", "-C", str(root), *arguments], check=True, capture_output=True, env=environment
    )


def _write(root: Path, relative: str, content: str) -> None:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _repository(root: Path, *, budgets: tuple[int, ...] = (BUDGET_THEN, BUDGET_NOW)) -> Path:
    """A working copy whose specification was committed once per budget given."""
    root.mkdir(parents=True, exist_ok=True)
    _git(root, "init", "-q")
    for budget in budgets:
        _write(root, SPEC_PATH, SPEC_TEMPLATE.format(budget=budget))
        _git(root, "add", SPEC_PATH)
        _git(root, "commit", "-q", "-m", f"triangle budget {budget}")
    return root


# --------------------------------------------------------------------------
# 4.2 — an earlier revision, and the repositories that cannot offer one
# --------------------------------------------------------------------------


def test_an_earlier_revision_is_read_out_of_the_repositorys_history(tmp_path: Path) -> None:
    store = GitSpecStore(_repository(tmp_path / "game"))

    newest, oldest = store.revisions_for(SPEC_PATH)
    earlier = store.load_at(SPEC_PATH, oldest)

    assert earlier.asset.constraints is not None
    assert earlier.asset.constraints.tri_budget == BUDGET_THEN
    assert store.load_at(SPEC_PATH, newest).asset.constraints.tri_budget == BUDGET_NOW


def test_a_revision_can_be_named_the_way_a_person_would(tmp_path: Path) -> None:
    """`HEAD~1` and a tag are revisions too: git resolves them, this does not parse them."""
    store = GitSpecStore(_repository(tmp_path / "game"))

    assert store.load_at(SPEC_PATH, "HEAD~1").asset.constraints.tri_budget == BUDGET_THEN


def test_a_shallow_clone_reports_unavailability_for_history_it_does_not_have(
    tmp_path: Path,
) -> None:
    """The case D10 names: the commit exists in the world, not in this checkout."""
    origin = _repository(tmp_path / "origin")
    truncated = GitSpecStore(origin).revisions_for(SPEC_PATH)[-1]
    clone = tmp_path / "shallow"
    clone.mkdir()
    _git(clone, "clone", "-q", "--depth", "1", origin.as_uri(), ".")
    store = GitSpecStore(clone)

    assert store.revisions_for(SPEC_PATH) == (GitSpecStore(origin).revisions_for(SPEC_PATH)[0],)
    with pytest.raises(HistoryUnavailable) as raised:
        store.load_at(SPEC_PATH, truncated)

    assert truncated in raised.value.message


def test_a_directory_that_is_not_a_repository_has_no_history(tmp_path: Path) -> None:
    """A tarball or an unzipped folder: every file is current and nothing came before."""
    _write(tmp_path, SPEC_PATH, SPEC_TEMPLATE.format(budget=BUDGET_NOW))
    store = GitSpecStore(tmp_path)

    assert store.revisions_for(SPEC_PATH) == ()
    with pytest.raises(HistoryUnavailable):
        store.load_at(SPEC_PATH, "HEAD")


def test_a_file_with_no_prior_revision_reports_unavailability(tmp_path: Path) -> None:
    root = _repository(tmp_path / "game")
    _write(root, "props/crate/asset.yaml", SPEC_TEMPLATE.format(budget=BUDGET_NOW))
    store = GitSpecStore(root)

    with pytest.raises(HistoryUnavailable) as raised:
        store.load_at("props/crate/asset.yaml", store.revisions_for(SPEC_PATH)[0])

    assert "props/crate/asset.yaml" in raised.value.message


def test_an_unknown_revision_names_the_revision_it_could_not_reach(tmp_path: Path) -> None:
    store = GitSpecStore(_repository(tmp_path / "game"))

    with pytest.raises(HistoryUnavailable) as raised:
        store.load_at(SPEC_PATH, "v9.9.9")

    assert "v9.9.9" in raised.value.message


def test_reading_history_leaves_the_working_copy_untouched(tmp_path: Path) -> None:
    """A read is a read: nothing is checked out, stashed or moved to serve one."""
    root = _repository(tmp_path / "game")
    store = GitSpecStore(root)
    before = (root / SPEC_PATH).read_text(encoding="utf-8")

    store.load_at(SPEC_PATH, store.revisions_for(SPEC_PATH)[-1])

    assert (root / SPEC_PATH).read_text(encoding="utf-8") == before
    assert _git(root, "status", "--porcelain").stdout == b""


# --------------------------------------------------------------------------
# 4.4 — `.canon/actors.yaml`, read from the same working copy as the specs
# --------------------------------------------------------------------------


def test_an_authored_mapping_is_read_from_the_repository(tmp_path: Path) -> None:
    root = _repository(tmp_path / "game")
    _write(root, ACTORS_PATH, ACTORS_YAML)

    loaded = GitSpecStore(root).load_actor_mapping("")

    (binding,) = loaded.mapping.bindings
    assert binding.subject == "auth|rafa"
    assert binding.emails == ("rafa@cyberdyne.com",)
    assert binding.role is Role.ARTIST
    assert loaded.is_readable


def test_an_absent_mapping_is_empty_and_not_a_failure(tmp_path: Path) -> None:
    """A project that never wrote one stays fully readable; every author is unmapped."""
    loaded = GitSpecStore(_repository(tmp_path / "game")).load_actor_mapping("")

    assert loaded.mapping.is_empty
    assert not loaded.is_declared
    assert loaded.is_readable


def test_a_malformed_mapping_is_a_violation_naming_the_file(tmp_path: Path) -> None:
    root = _repository(tmp_path / "game")
    _write(root, ACTORS_PATH, BROKEN_ACTORS_YAML)
    store = GitSpecStore(root)

    loaded = store.load_actor_mapping("")

    (violation,) = loaded.violations
    assert violation.rule_id == RULE_UNPARSEABLE
    assert ACTORS_PATH in violation.message
    assert store.load(SPEC_PATH).asset.id.value == "mech_scout"


def test_an_entry_naming_an_unknown_role_still_parses_so_it_can_be_reported(
    tmp_path: Path,
) -> None:
    """A defect in the file is a violation to report, never a file nobody can read."""
    root = _repository(tmp_path / "game")
    _write(root, ACTORS_PATH, ACTORS_WITH_UNKNOWN_ROLE)

    loaded = GitSpecStore(root).load_actor_mapping("")

    assert loaded.is_readable
    (violation,) = check_mapping(loaded.mapping)
    assert "WIZARD" in violation.message


def test_the_mapping_is_read_at_the_working_copys_revision(tmp_path: Path) -> None:
    """Committed or not, the mapping a read sees is the one beside the specs it explains."""
    root = _repository(tmp_path / "game")
    _write(root, ACTORS_PATH, ACTORS_YAML)
    _git(root, "add", ACTORS_PATH)
    _git(root, "commit", "-q", "-m", "map rafa")
    _write(root, ACTORS_PATH, ACTORS_YAML.replace("Rafa", "Rafael"))

    loaded = GitSpecStore(root).load_actor_mapping("")

    assert loaded.mapping.bindings[0].display_name == "Rafael"
