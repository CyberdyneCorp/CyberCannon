"""Tasks 4.7 and 4.8 — the compiled briefing, and the project-level one.

`art-spec.md` is read by people and by agents that never heard of this tool, so
what is asserted here is mostly about what the output does **not** contain: no
resolved thread, no promoted thread, no per-asset content in the project
briefing, and nothing that changes between two runs of the same input.
"""

from __future__ import annotations

from cybercanon.application.ports.spec_store import ProjectConfig
from cybercanon.application.testing.spec_store import InMemorySpecStore
from cybercanon.application.use_cases.compile_spec import compile_project_briefing, compile_spec
from cybercanon.domain.annotations import Anchor3D, Annotation, AnnotationKind
from cybercanon.domain.asset import Asset, AssetId, Links
from cybercanon.domain.concept import Concept
from cybercanon.domain.constraints import AnimationDefaults, Constraints, Rig
from cybercanon.domain.design import Design, Socket, State
from cybercanon.domain.status import Status

SPEC_PATH = "characters/mech_scout/asset.yaml"
SHOULDER = "SM_MechScout_Shoulder_L"
OPEN_TEXT = "the shoulder pauldron reads as a backpack at 25 m"
RESOLVED_TEXT = "the left foot clips the ground in the idle pose"
PROMOTED_TEXT = "the silhouette must read as a scout, not a brawler"


def an_annotation(identifier: str, text: str, kind: AnnotationKind = AnnotationKind.ART_DIRECTION):
    return Annotation(
        id=identifier,
        author="rafa",
        kind=kind,
        text=text,
        target=Anchor3D(part=SHOULDER),
    )


def an_asset(**blocks: object) -> Asset:
    return Asset(  # type: ignore[arg-type]
        id=AssetId("mech_scout"),
        name="Scout Mech",
        status=Status.MODELING,
        owner_art="rafa",
        owner_design="dani",
        **blocks,
    )


def compiled(asset: Asset, project: ProjectConfig | None = None) -> str:
    store = InMemorySpecStore()
    store.add(SPEC_PATH, asset)
    if project is not None:
        store.set_project(project)
    return compile_spec(SPEC_PATH, spec_store=store).text


# --------------------------------------------------------------------------
# Rules and open issues only
# --------------------------------------------------------------------------


def test_the_open_annotation_is_carried_and_the_resolved_ones_are_not() -> None:
    asset = an_asset(
        annotations=(
            an_annotation("a1", OPEN_TEXT),
            an_annotation("a2", RESOLVED_TEXT).resolved(),
            an_annotation("a3", "the antenna is too short").resolved(),
        )
    )

    text = compiled(asset)

    assert OPEN_TEXT in text
    assert RESOLVED_TEXT not in text
    assert "antenna" not in text


def test_promoted_content_appears_as_a_rule_and_not_as_an_open_item() -> None:
    """Promotion moved the content into the rules; the thread stays in git history."""
    asset = an_asset(
        concept=Concept(silhouette_rules=(PROMOTED_TEXT,)),
        annotations=(an_annotation("a1", PROMOTED_TEXT).promoted(),),
    )

    text = compiled(asset)
    rules, issues = text.split("## Open issues")

    assert PROMOTED_TEXT in rules
    assert PROMOTED_TEXT not in issues


def test_the_output_does_not_grow_as_annotations_are_resolved() -> None:
    open_only = an_asset(annotations=(an_annotation("a1", OPEN_TEXT),))
    after_many = an_asset(
        annotations=(
            an_annotation("a1", OPEN_TEXT),
            *(an_annotation(f"r{index}", f"issue {index}").resolved() for index in range(20)),
        )
    )

    assert compiled(after_many) == compiled(open_only)


# --------------------------------------------------------------------------
# Self-explanatory, effective, deterministic
# --------------------------------------------------------------------------


def test_the_output_names_the_asset_its_status_and_the_authoring_disciplines() -> None:
    text = compiled(an_asset(concept=Concept(silhouette_rules=("reads at 25 m",))))

    assert "mech_scout" in text
    assert "Scout Mech" in text
    assert "**Status:** modeling" in text
    assert "## Concept — authored by art" in text
    assert "## Design — authored by design" in text
    assert "## Engineering constraints — authored by engineering" in text


def test_effective_values_are_resolved_so_nobody_consults_the_project_file() -> None:
    """D3 — the reader and the validator see the same merged object."""
    text = compiled(
        an_asset(constraints=Constraints(tri_budget=12000)),
        project=ProjectConfig(defaults=Constraints(up_axis="Z")),
    )

    assert "- **Up axis**: Z" in text
    assert "- **Triangle budget**: 12000" in text


def test_the_asset_declaration_wins_over_the_project_default_in_the_output() -> None:
    text = compiled(
        an_asset(constraints=Constraints(up_axis="Y")),
        project=ProjectConfig(defaults=Constraints(up_axis="Z")),
    )

    assert "- **Up axis**: Y" in text


def test_required_clips_are_stated_with_the_names_the_export_must_carry() -> None:
    asset = an_asset(
        design=Design(
            states=(
                State(name="walk", frame_rate=30.0, min_duration_s=1.0),
                State(name="destroyed", animated=False),
            ),
            sockets=(Socket(name="SOCKET_muzzle_l", purpose="muzzle flash"),),
        ),
        constraints=Constraints(animation=AnimationDefaults(clip_naming="A_{asset}_{state}")),
    )

    text = compiled(asset)

    assert "clip `A_mech_scout_walk`" in text
    assert "30.0 fps" in text
    assert "at least 1.0 s" in text
    assert "`destroyed` — declared unanimated" in text
    assert "`SOCKET_muzzle_l`" in text


def test_a_state_that_resolves_to_no_clip_says_so_instead_of_going_quiet() -> None:
    text = compiled(an_asset(design=Design(states=(State(name="walk"),))))

    assert "resolves to no clip" in text


def test_compiling_the_same_specification_twice_is_byte_identical() -> None:
    asset = an_asset(
        concept=Concept(views=("front", "side"), silhouette_rules=("reads at 25 m",)),
        design=Design(role="scout", sockets=(Socket(name="SOCKET_muzzle_l", purpose="vfx"),)),
        constraints=Constraints(tri_budget=12000, rig=Rig(skeleton="SK_MechScout", max_bones=96)),
        links=Links(source="art/mech_scout.blend", engine="/Game/Characters/MechScout"),
        annotations=(an_annotation("a1", OPEN_TEXT),),
    )

    assert compiled(asset) == compiled(asset)


def test_the_compiled_text_ends_in_exactly_one_newline() -> None:
    """Byte-identical is only reviewable if the file is well-formed every time."""
    text = compiled(an_asset())

    assert text.endswith("\n")
    assert not text.endswith("\n\n")


def test_the_compilation_records_what_it_was_derived_from() -> None:
    store = InMemorySpecStore()
    store.add(SPEC_PATH, an_asset())

    result = compile_spec(SPEC_PATH, spec_store=store)

    assert result.asset_id == "mech_scout"
    assert result.source == SPEC_PATH
    assert result.filename == "art-spec.md"
    assert SPEC_PATH in result.text


# --------------------------------------------------------------------------
# 4.8 — the project-level briefing
# --------------------------------------------------------------------------


def a_project_store() -> InMemorySpecStore:
    store = InMemorySpecStore()
    store.add(SPEC_PATH, an_asset(annotations=(an_annotation("a1", OPEN_TEXT),)))
    store.set_project(
        ProjectConfig(
            name="Ironwood",
            defaults=Constraints(up_axis="Z", unit_scale=1.0, naming="SM_{asset}_LOD{n}"),
            golden_rules=("Every design field constrains art, constrains code, or is checkable.",),
        )
    )
    return store


def test_the_project_briefing_carries_the_shared_constraints_and_the_golden_rules() -> None:
    briefing = compile_project_briefing("", spec_store=a_project_store())

    assert briefing.project == "Ironwood"
    assert "Every design field constrains art" in briefing.text
    assert "- **Up axis**: Z" in briefing.text
    assert "- **Object naming**: `SM_{asset}_LOD{n}`" in briefing.text


def test_the_project_briefing_contains_no_asset_annotation() -> None:
    briefing = compile_project_briefing("", spec_store=a_project_store())

    assert OPEN_TEXT not in briefing.text
    assert "mech_scout" not in briefing.text


def test_the_project_briefing_is_deterministic_too() -> None:
    store = a_project_store()

    assert compile_project_briefing("", spec_store=store) == compile_project_briefing(
        "", spec_store=store
    )
