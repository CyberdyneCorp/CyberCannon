"""Task 2.1 — tenancy as a value, and the one question it answers.

`auth-integration` requires the tenant to come from verified claims and requires
a path-supplied one to be unable to widen access. The half of that which lives
in the domain is small and is all here: a tenant is a value, a project may name
one, and an actor's tenant either admits the project or it does not.
"""

from __future__ import annotations

import pytest

from cybercanon.domain.tenancy import ProjectRef, Tenant, project_ref, tenants_agree

CYBERDYNE = Tenant("cyberdyne")
OTHER = Tenant("ironwood-studios")

GAME = ProjectRef("cyberdyne-game", tenant=CYBERDYNE)
UNTENANTED = ProjectRef("cyberdyne-game")


@pytest.mark.parametrize("value", ["", " ", "has space", " padded"])
def test_a_tenant_is_a_non_empty_unpadded_word(value: str) -> None:
    with pytest.raises(ValueError, match="tenant"):
        Tenant(value)


def test_a_tenant_renders_as_its_value() -> None:
    assert str(CYBERDYNE) == "cyberdyne"


def test_a_project_reference_renders_as_its_name() -> None:
    assert str(GAME) == "cyberdyne-game"


def test_a_padded_project_name_is_refused() -> None:
    with pytest.raises(ValueError, match="unpadded"):
        ProjectRef(" cyberdyne-game")


def test_a_bare_name_becomes_a_reference_with_no_tenant() -> None:
    """The command line has one project and no organisation (D4)."""
    assert project_ref("cyberdyne-game") == UNTENANTED


def test_a_reference_is_returned_unchanged() -> None:
    assert project_ref(GAME) is GAME


def test_a_project_naming_no_tenant_asks_no_tenancy_question() -> None:
    assert tenants_agree(None, UNTENANTED)
    assert tenants_agree(OTHER, UNTENANTED)


def test_a_project_naming_the_actors_tenant_agrees() -> None:
    assert tenants_agree(CYBERDYNE, GAME)


def test_a_project_naming_another_tenant_disagrees() -> None:
    assert not tenants_agree(OTHER, GAME)


def test_an_actor_with_no_tenant_is_refused_a_tenanted_project() -> None:
    """ "No tenant" is not "every tenant" — that reading is every cross-org leak."""
    assert not tenants_agree(None, GAME)
