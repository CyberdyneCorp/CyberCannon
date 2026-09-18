"""Task 3.7 — the naming template expander (D8).

Templates, not regular expressions: `SM_{asset}_LOD{n}` is what an artist can be
asked to author. The expander turns it into a matcher, and reads the LOD index
back out so a per-level triangle budget knows which level it is looking at.
"""

from __future__ import annotations

import pytest

from cybercanon.domain.naming import expand, lod_index, matches, placeholders

OBJECT_TEMPLATE = "SM_{asset}_LOD{n}"
CLIP_TEMPLATE = "A_{asset}_{state}"
ASSET = {"asset": "mech_scout"}


def test_a_template_declares_its_placeholders_in_order() -> None:
    assert placeholders(OBJECT_TEMPLATE) == ("asset", "n")


def test_expanding_substitutes_every_bound_placeholder() -> None:
    assert expand(CLIP_TEMPLATE, {"asset": "mech_scout", "state": "walk"}) == "A_mech_scout_walk"


def test_expanding_leaves_an_unbound_placeholder_standing() -> None:
    """Half a template is still a template; inventing an index would be worse."""
    assert expand(OBJECT_TEMPLATE, ASSET) == "SM_mech_scout_LOD{n}"


def test_expanding_with_nothing_bound_is_the_template_itself() -> None:
    assert expand(OBJECT_TEMPLATE) == OBJECT_TEMPLATE


@pytest.mark.parametrize("name", ["SM_mech_scout_LOD0", "SM_mech_scout_LOD12"])
def test_a_matching_object_name_passes(name: str) -> None:
    assert matches(OBJECT_TEMPLATE, name, ASSET)


def test_matching_ignores_case_because_conventions_capitalise_differently() -> None:
    assert matches(OBJECT_TEMPLATE, "SM_Mech_Scout_LOD0", ASSET)


@pytest.mark.parametrize(
    "name",
    [
        "mesh_final_v2",
        "SM_mech_scout",
        "SM_other_LOD0",
        "SM_mech_scout_LODx",
        "xSM_mech_scout_LOD0",
    ],
)
def test_a_non_matching_object_name_fails(name: str) -> None:
    assert not matches(OBJECT_TEMPLATE, name, ASSET)


def test_the_lod_index_is_read_back_out_of_the_name() -> None:
    assert lod_index(OBJECT_TEMPLATE, "SM_mech_scout_LOD2", ASSET) == 2


def test_a_name_that_does_not_match_has_no_lod_index() -> None:
    assert lod_index(OBJECT_TEMPLATE, "mesh_final_v2", ASSET) is None


def test_a_template_with_no_index_placeholder_yields_no_index() -> None:
    assert lod_index("SM_{asset}", "SM_mech_scout", ASSET) is None


def test_an_unbound_name_placeholder_matches_any_run_of_non_space() -> None:
    assert matches(CLIP_TEMPLATE, "A_mech_scout_walk", ASSET)
    assert not matches(CLIP_TEMPLATE, "A_mech_scout_", ASSET)


def test_literal_text_is_escaped_rather_than_interpreted() -> None:
    """A dot in a template is a dot, not 'any character'."""
    assert matches("{asset}.mesh", "mech_scout.mesh", ASSET)
    assert not matches("{asset}.mesh", "mech_scoutXmesh", ASSET)


def test_a_template_that_is_only_a_placeholder_still_matches() -> None:
    assert matches("{asset}", "mech_scout", ASSET)
