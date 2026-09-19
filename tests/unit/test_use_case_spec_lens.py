"""Tasks 3.8-3.10 — one compilation, four projections, authorization first.

Two properties carry this capability, and both are asserted structurally rather
than by reading prose:

* **D2** — every line of a lensed response is a line of the full compilation.
  That is what "a field common to two lenses is byte-identical in both" means
  mechanically, and it is only provable because the projection removes content
  from one document instead of rendering four.
* **D3** — authorization is evaluated before the lens. The ordering test makes
  the specification store *explode* if it is touched, so a refusal that still
  arrives proves nothing was compiled first.
"""

from __future__ import annotations

import pytest

from cybercanon.application.ports.spec_store import ProjectConfig
from cybercanon.application.testing.outcomes import ran
from cybercanon.application.testing.spec_store import InMemorySpecStore
from cybercanon.application.use_cases.compile_spec import compile_spec
from cybercanon.application.use_cases.resolve_actor import (
    ActorResolver,
    IdentitySource,
    Resolution,
)
from cybercanon.application.use_cases.spec_lens import (
    Lens,
    ReadRefused,
    UnknownLens,
    compile_spec_for_lens,
    project_lens,
)
from cybercanon.domain.annotations import Anchor3D, Annotation, AnnotationKind
from cybercanon.domain.asset import Asset, AssetId, Links
from cybercanon.domain.concept import Concept
from cybercanon.domain.constraints import AnimationDefaults, Constraints, Rig, Texture
from cybercanon.domain.design import Design, Socket, State
from cybercanon.domain.identity import Actor, ActorId, Role
from cybercanon.domain.status import Status

PROJECT = "cyberdyne-game"
OTHER_PROJECT = "another-game"
SPEC_PATH = "characters/mech_scout/asset.yaml"
SOCKET = "SOCKET_muzzle_l"
PALETTE_RULE = "the palette stays to three desaturated greens"
ANTENNA = Anchor3D(part="antenna")


def an_annotation(identifier: str, kind: AnnotationKind, text: str) -> Annotation:
    return Annotation(
        id=identifier,
        author="rafa@cyberdyne.com",
        kind=kind,
        text=text,
        target=ANTENNA,
    )


OPEN_ANNOTATIONS = (
    an_annotation("a1", AnnotationKind.ART_DIRECTION, "the antenna reads as a weapon"),
    an_annotation("a2", AnnotationKind.TECHNICAL, "the antenna costs 900 triangles"),
    an_annotation("a3", AnnotationKind.DESIGN, "the antenna hides the muzzle socket"),
)
RESOLVED_ANNOTATIONS = tuple(
    an_annotation(f"r{index}", kind, f"the hatch seam was fixed in pass {index}").resolved()
    for index, kind in enumerate(AnnotationKind)
)
PROMOTED = an_annotation(
    "p1", AnnotationKind.ART_DIRECTION, "the antenna rule became a silhouette rule"
).promoted()

SCOUT = Asset(
    id=AssetId("mech_scout"),
    name="Scout Mech",
    status=Status.MODELING,
    aliases=("drone",),
    owner_art="rafa@cyberdyne.com",
    owner_design="ana@cyberdyne.com",
    owner_code="joe@cyberdyne.com",
    concept=Concept(views=("front.png", "side.png"), silhouette_rules=(PALETTE_RULE,)),
    design=Design(
        role="scout",
        read_distance_m=8.0,
        silhouette_priority="high",
        scale_ref="human",
        team_color_regions=("shoulders",),
        states=(State(name="idle", clip="A_idle"),),
        sockets=(Socket(name=SOCKET, purpose="muzzle flash"),),
    ),
    constraints=Constraints(
        tri_budget=12000,
        lods=(12000, 6000),
        up_axis="Z",
        unit_scale=1.0,
        naming="SM_{asset}",
        pivot="origin",
        collider="box",
        texture=Texture(size=2048, sets=2, channels=("BC", "N")),
        rig=Rig(skeleton="humanoid", max_bones=80),
        animation=AnimationDefaults(clip_naming="A_{asset}_{state}", frame_rate=30),
    ),
    links=Links(
        source="art/mech_scout.blend",
        engine="/Game/Chars/MechScout",
        discussion="https://chat.example/threads/17",
        design_doc="https://arche.example/docs/mech-scout",
    ),
    annotations=(*OPEN_ANNOTATIONS, *RESOLVED_ANNOTATIONS, PROMOTED),
)


@pytest.fixture
def store() -> InMemorySpecStore:
    store = InMemorySpecStore()
    store.set_project(ProjectConfig(name=PROJECT))
    store.add(SPEC_PATH, SCOUT)
    return store


@pytest.fixture
def entitled() -> Resolution:
    return ActorResolver(project=PROJECT).resolve()


@pytest.fixture
def unentitled() -> Resolution:
    return Resolution(
        actor=Actor(
            id=ActorId("auth|ana"),
            display_name="Ana",
            roles=(Role.ENGINEER,),
            projects=(OTHER_PROJECT,),
        ),
        source=IdentitySource.PROVIDER,
        verified=True,
    )


def read(store: InMemorySpecStore, resolution: Resolution, lens: str | None = None):
    return compile_spec_for_lens(
        SPEC_PATH,
        lens,
        spec_store=store,
        resolution=resolution,
        project=PROJECT,
    )


# --------------------------------------------------------------------------
# 3.8 — one compilation, projected (D2)
# --------------------------------------------------------------------------


@pytest.mark.parametrize("lens", list(Lens))
def test_every_line_of_a_lens_is_a_line_of_the_one_compilation(store, entitled, lens) -> None:
    lensed = read(store, entitled, lens.value)

    full = set(lensed.full.splitlines())
    assert set(lensed.lines) <= full, "a lens removes content; it never renders it again"


def test_a_field_presented_by_two_lenses_is_byte_identical_in_both(store, entitled) -> None:
    design = read(store, entitled, "design")
    modeling = read(store, entitled, "modeling")

    socket_lines = [line for line in design.lines if SOCKET in line]
    assert socket_lines, "the design lens presents the required sockets"
    assert socket_lines == [line for line in modeling.lines if SOCKET in line]


def test_the_projection_is_a_pure_function_of_one_compiled_specification(store) -> None:
    compiled = ran(compile_spec(SPEC_PATH, spec_store=store))

    projections = {lens: project_lens(compiled, lens) for lens in Lens}

    assert all(projection.full == compiled.text for projection in projections.values())
    assert project_lens(compiled).body == compiled.text


# --------------------------------------------------------------------------
# 3.9 — what each lens returns
# --------------------------------------------------------------------------


def test_the_modeling_lens_returns_the_constraints_and_the_required_sockets(
    store, entitled
) -> None:
    body = read(store, entitled, "modeling").body

    assert "12000" in body, "the effective triangle budget"
    assert "humanoid" in body, "the effective rig"
    assert SOCKET in body


def test_the_modeling_lens_omits_the_concept_block(store, entitled) -> None:
    """The palette is authored in the concept block; no part of it reaches modeling."""
    body = read(store, entitled, "modeling").body

    assert PALETTE_RULE not in body
    assert "front.png" not in body
    assert "Concept" not in body


def test_an_absent_lens_returns_the_whole_specification(store, entitled) -> None:
    full = read(store, entitled).body
    compiled = ran(compile_spec(SPEC_PATH, spec_store=store))

    assert full == compiled.text
    for block in ("Concept", "Design", "Engineering constraints", "Open issues", "Links"):
        assert block in full


def test_an_unknown_lens_is_refused_naming_the_available_ones(store, entitled) -> None:
    with pytest.raises(UnknownLens) as failure:
        read(store, entitled, "engineering")

    for name in Lens.values():
        assert name in failure.value.message


@pytest.mark.parametrize("lens", list(Lens))
def test_no_lens_exposes_a_resolved_or_promoted_annotation(store, entitled, lens) -> None:
    body = read(store, entitled, lens.value).body

    assert "the hatch seam was fixed" not in body
    assert "became a silhouette rule" not in body


@pytest.mark.parametrize(
    ("lens", "expected"),
    [
        ("design", "the antenna hides the muzzle socket"),
        ("art", "the antenna reads as a weapon"),
        ("modeling", "the antenna costs 900 triangles"),
    ],
)
def test_a_lens_carries_the_open_annotations_of_its_discipline(
    store, entitled, lens, expected
) -> None:
    body = read(store, entitled, lens).body

    assert expected in body
    assert sum(note.text in body for note in OPEN_ANNOTATIONS) == 1, (
        "a lens carries its own discipline's open issues and no other's"
    )


def test_the_code_lens_carries_the_engine_path_and_the_links(store, entitled) -> None:
    body = read(store, entitled, "code").body

    assert "/Game/Chars/MechScout" in body
    assert "https://arche.example/docs/mech-scout" in body
    assert SOCKET in body, "the sockets code may bind to"


def test_the_art_lens_carries_the_concept_and_not_the_budget(store, entitled) -> None:
    body = read(store, entitled, "art").body

    assert PALETTE_RULE in body
    assert "front.png" in body
    assert "12000" not in body


def test_a_lensed_response_names_its_lens_and_says_a_full_specification_exists(
    store, entitled
) -> None:
    lensed = read(store, entitled, "modeling")

    assert lensed.is_lensed
    assert "modeling" in lensed.notice
    assert "full specification" in lensed.notice
    assert lensed.notice in lensed.text


def test_an_unlensed_response_carries_no_notice(store, entitled) -> None:
    assert read(store, entitled).notice == ""


# --------------------------------------------------------------------------
# 3.10 — authorization is evaluated before the lens (D3)
# --------------------------------------------------------------------------


def test_authorization_is_evaluated_before_anything_is_compiled(store, unentitled) -> None:
    """If the read were compiled first, the store's booby trap would fire."""
    store.fail_with(AssertionError("the specification was compiled before authorizing"))

    with pytest.raises(ReadRefused):
        read(store, unentitled, "modeling")


def test_an_unentitled_read_is_refused_identically_under_every_lens(store, unentitled) -> None:
    refusals = set()
    for lens in (None, *Lens.values()):
        with pytest.raises(ReadRefused) as failure:
            read(store, unentitled, lens)
        refusals.add(failure.value.message)

    assert len(refusals) == 1, "the lens does not change the refusal, because it is not consulted"


def test_an_unknown_lens_does_not_reveal_whether_the_asset_exists(store, unentitled) -> None:
    """Authorization first means a hostile lens string gets the same refusal."""
    with pytest.raises(ReadRefused) as refused:
        read(store, unentitled, "engineering")

    with pytest.raises(ReadRefused) as plainly_refused:
        read(store, unentitled, "modeling")

    assert refused.value.message == plainly_refused.value.message


@pytest.mark.parametrize("lens", list(Lens))
def test_a_caller_may_choose_any_lens_whatever_role_it_holds(store, lens) -> None:
    engineer = Resolution(
        actor=Actor(
            id=ActorId("auth|joe"),
            display_name="Joe",
            roles=(Role.ENGINEER,),
            projects=(PROJECT,),
        ),
        source=IdentitySource.PROVIDER,
        verified=True,
    )

    assert read(store, engineer, lens.value).is_lensed


def test_a_read_with_no_identity_configured_still_works(store) -> None:
    """The local unauthenticated actor reads the project it is standing in (D4)."""
    local = ActorResolver(project=PROJECT).resolve()

    assert read(store, local, "modeling").body
