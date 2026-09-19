"""Task 6.3 — the actor mapping is validated in the lint path, not beside it.

The risk the requirement names is that nobody ever writes `.canon/actors.yaml`
and every author stays unmapped forever. The mitigation is that its defects
surface in the check somebody already runs, so an empty or contradictory mapping
is a visible failure rather than an invisible one.

Two properties, and they pull against each other on purpose:

* the mapping's findings **count** — a duplicated email fails `lint_project`
  exactly as a descending-LOD error does;
* the mapping is **not a specification file** — it never enters `checked`, so the
  count of specification files a project has does not move when somebody adds an
  identity file.

Pure, with no file on disk and no identity service: validation must need neither.
"""

from __future__ import annotations

import pytest

from cybercanon.application.testing.spec_store import InMemorySpecStore
from cybercanon.application.use_cases.lint_spec import (
    lint_actor_mapping,
    lint_project,
    lint_specs,
)
from cybercanon.domain.actor_checks import (
    RULE_DUPLICATE_EMAIL,
    RULE_DUPLICATE_SUBJECT,
    RULE_UNKNOWN_ROLE,
    RULE_UNPARSEABLE,
)
from cybercanon.domain.actors import ACTORS_PATH, ActorBinding, ActorMapping
from cybercanon.domain.asset import Asset, AssetId
from cybercanon.domain.constraints import Constraints

pytestmark = pytest.mark.unit

SPEC_PATH = "characters/mech_scout/asset.yaml"
RAFA = "rafa@cyberdyne.com"


def a_store() -> InMemorySpecStore:
    store = InMemorySpecStore()
    store.add(
        SPEC_PATH,
        Asset(id=AssetId("mech_scout"), name="Scout Mech", constraints=Constraints(tri_budget=1)),
    )
    return store


def mapping(*bindings: ActorBinding) -> ActorMapping:
    return ActorMapping(bindings=bindings)


def a_binding(subject: str, *emails: str, role: str | None = None) -> ActorBinding:
    return ActorBinding(subject=subject, display_name=subject, emails=emails, default_role=role)


def test_a_project_with_no_mapping_produces_no_findings() -> None:
    """The mapping is optional and additive: its absence is not a defect."""
    assert lint_actor_mapping(spec_store=a_store()) == ()


def test_a_well_formed_mapping_produces_no_findings() -> None:
    store = a_store()
    store.set_actor_mapping(mapping(a_binding("auth|rafa", RAFA, role="artist")))

    assert lint_actor_mapping(spec_store=store) == ()


@pytest.mark.parametrize(
    ("built", "rule_id"),
    [
        (
            mapping(a_binding("auth|rafa", RAFA), a_binding("auth|other", RAFA)),
            RULE_DUPLICATE_EMAIL,
        ),
        (
            mapping(a_binding("auth|rafa", RAFA), a_binding("auth|rafa", "second@x.com")),
            RULE_DUPLICATE_SUBJECT,
        ),
        (mapping(a_binding("auth|rafa", RAFA, role="wizard")), RULE_UNKNOWN_ROLE),
    ],
    ids=["duplicate email", "duplicate subject", "unknown role"],
)
def test_each_structural_defect_is_reported_against_the_mapping_file(
    built: ActorMapping, rule_id: str
) -> None:
    store = a_store()
    store.set_actor_mapping(built)

    findings = lint_actor_mapping(spec_store=store)

    assert [finding.rule_id for finding in findings] == [rule_id]
    assert findings[0].path == ACTORS_PATH


def test_an_unparseable_mapping_is_a_finding_rather_than_an_exception() -> None:
    store = a_store()
    store.set_actor_mapping_unparseable("expected a list of actors")

    findings = lint_actor_mapping(spec_store=store)

    assert [finding.rule_id for finding in findings] == [RULE_UNPARSEABLE]
    assert ACTORS_PATH in findings[0].violation.message


def test_the_project_lint_fails_over_a_broken_mapping() -> None:
    """The point of wiring it here: `canon check` exits non-zero over it."""
    store = a_store()
    store.set_actor_mapping(mapping(a_binding("auth|rafa", RAFA), a_binding("auth|other", RAFA)))

    report = lint_project("", spec_store=store)

    assert not report.passed
    assert report.errors
    assert report.findings_of(RULE_DUPLICATE_EMAIL)


def test_the_mapping_is_never_counted_as_a_specification_file() -> None:
    """Adding an identity file must not change how many assets a project has."""
    store = a_store()
    without = lint_project("", spec_store=store)
    store.set_actor_mapping(mapping(a_binding("auth|rafa", RAFA)))
    with_mapping = lint_project("", spec_store=store)

    assert without.checked == with_mapping.checked == (SPEC_PATH,)
    assert with_mapping.mapping == ()


def test_linting_named_files_says_nothing_about_the_mapping() -> None:
    """`canon changed` validates the assets a commit touched, and nothing else.

    The pre-commit path must not block a mesh commit over an identity file the
    author never looked at; the project check is where that belongs.
    """
    store = a_store()
    store.set_actor_mapping(mapping(a_binding("auth|rafa", RAFA), a_binding("auth|other", RAFA)))

    named = lint_specs([SPEC_PATH], spec_store=store)

    assert named.mapping == ()
    assert named.passed
    assert not lint_project("", spec_store=store).passed
