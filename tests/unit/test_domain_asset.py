"""Task 2.1 — identity, ownership and links as frozen value objects."""

from __future__ import annotations

import dataclasses

import pytest

from cybercanon.domain.annotations import Anchor2D, Annotation, AnnotationKind
from cybercanon.domain.asset import Asset, AssetId, Links
from cybercanon.domain.concept import Concept
from cybercanon.domain.constraints import AnimationDefaults, Constraints
from cybercanon.domain.status import Status


def an_asset(**overrides: object) -> Asset:
    fields: dict[str, object] = {"id": AssetId("mech_scout"), "name": "Scout Mech"}
    fields.update(overrides)
    return Asset(**fields)  # type: ignore[arg-type]


def test_an_asset_id_is_a_value_object_rendering_as_its_text() -> None:
    assert str(AssetId("mech_scout")) == "mech_scout"
    assert AssetId("mech_scout") == AssetId("mech_scout")


@pytest.mark.parametrize("value", ["", " ", "mech scout", "mech\tscout", " mech_scout"])
def test_an_unusable_asset_id_is_refused(value: str) -> None:
    with pytest.raises(ValueError, match="asset id"):
        AssetId(value)


def test_renaming_does_not_touch_the_id() -> None:
    asset = an_asset(aliases=("scout", "walker"))

    renamed = asset.renamed("Recon Walker")

    assert renamed.name == "Recon Walker"
    assert renamed.id == asset.id == AssetId("mech_scout")
    assert asset.name == "Scout Mech", "the original value object is untouched"


def test_an_asset_is_reachable_by_its_id_and_by_any_alias() -> None:
    asset = an_asset(aliases=("scout", "recon walker"))

    assert asset.refers_to("mech_scout")
    assert asset.refers_to("recon walker")
    assert not asset.refers_to("Scout Mech"), "the name is not an identifier"


def test_ownership_is_per_discipline_and_none_of_it_is_required() -> None:
    asset = an_asset(owner_art="ana", owner_code="rafa")

    assert (asset.owner_art, asset.owner_code) == ("ana", "rafa")
    assert asset.owner_design is None


def test_the_three_authored_blocks_are_independently_optional() -> None:
    concept_only = an_asset(concept=Concept(views=("front",)))

    assert concept_only.concept is not None
    assert concept_only.design is None
    assert concept_only.constraints is None


def test_an_asset_defaults_to_the_first_lifecycle_status() -> None:
    assert an_asset().status is Status.CONCEPT


def test_links_are_stored_verbatim() -> None:
    links = Links(discussion="https://unreachable.invalid/thread/7")

    assert links.discussion == "https://unreachable.invalid/thread/7"
    assert (links.source, links.engine, links.design_doc) == (None, None, None)


def test_the_clip_naming_convention_an_asset_declares_is_readable() -> None:
    asset = an_asset(
        constraints=Constraints(animation=AnimationDefaults(clip_naming="A_{asset}_{state}"))
    )

    assert asset.clip_naming == "A_{asset}_{state}"
    assert an_asset().clip_naming is None
    assert an_asset(constraints=Constraints()).clip_naming is None


def test_open_annotations_exclude_the_two_exits() -> None:
    target = Anchor2D(view="front", u=0.5, v=0.5)
    fields = {"author": "ana", "kind": AnnotationKind.ART_DIRECTION, "target": target}
    annotations = (
        Annotation(id="a1", text="lens glow is emissive", **fields),  # type: ignore[arg-type]
        Annotation(id="a2", text="arm clips", **fields).resolved(),  # type: ignore[arg-type]
        Annotation(id="a3", text="always emissive", **fields).promoted(),  # type: ignore[arg-type]
    )

    asset = an_asset(annotations=annotations)

    assert [annotation.id for annotation in asset.open_annotations] == ["a1"]


def test_an_asset_is_frozen() -> None:
    asset = an_asset()

    with pytest.raises(dataclasses.FrozenInstanceError):
        asset.name = "Recon Walker"  # type: ignore[misc]
