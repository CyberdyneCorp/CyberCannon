"""D2 — the selective-MVVM bet, checked in the change that collects it.

`openspec/project.md` claims one `AnnotationViewModel` serves both the 2D model
sheet and the 3D viewer, and that this is *"what makes 'support 2D and 3D' cost
far less than twice"*. `add-viewer-3d`'s D2 says the claim *"only pays if the
boundary is enforced rather than intended"*, and adds the consequence in as many
words: **if this change had to modify the ViewModel for 3D, the 2D/3D boundary
was in the wrong place and that is worth knowing loudly.**

So this module asserts three things about the shape of the code rather than
about its behaviour, and it lives in the Python suite for the same reason the
D1 and D7 rules next door do: `just check` runs here, and a constraint that only
bites when somebody remembers to run the frontend's own runner stops biting in
week three.

* **the ViewModel learned nothing about 3D** — no part, no bone, no clip, no
  camera, no mesh, no `three`;
* **the shared annotation module does not reach into the viewer** — the
  dependency goes one way, or the "shared" module is the viewer's;
* **the viewer reimplements no thread, filter or triage logic** — it reaches
  them through the ViewModel and through the components the sheet already
  renders.

Task 9.3 asks for any leakage to be *recorded as a finding for the design
review* rather than quietly fixed. A failure here is that finding.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterator
from pathlib import Path

import pytest

WEB = Path("apps/cybercanon/web")
VIEW_MODEL = WEB / "src" / "lib" / "annotation" / "annotation-view-model.svelte.ts"
ANNOTATION_MODULE = WEB / "src" / "lib" / "annotation"
VIEWER_MODULE = WEB / "src" / "lib" / "viewer"

VIEWER_COMPONENTS = ("Viewer3D.svelte", "AnimationTransport.svelte")

BLOCK_COMMENT = re.compile(r"/\*[\s\S]*?\*/")
LINE_COMMENT = re.compile(r"//.*$", re.M)

THREE_DIMENSIONAL = (
    "part",
    "bone",
    "clip",
    "camera",
    "mesh",
    "three",
    "vec3",
    "raycast",
    "viewer/",
)
"""The vocabulary a ViewModel with a 3D branch in it would have to use.

Deliberately including the ordinary English words: the failure this guards
against is not somebody importing `three.js` into the ViewModel — nobody would
— it is a `if (anchor.part)` appearing in a filter six months from now.
"""

SHARED_MODULES = (
    "$lib/annotation/filter",
    "$lib/annotation/sheet",
    "$lib/annotation/annotation-view-model",
    "$lib/triage",
)
"""What the viewer must reach *through* the ViewModel rather than import."""


def _code(path: Path) -> str:
    """The file with its comments removed.

    The prose in these files says what they must not do, in the words they must
    not use, which is exactly right for a reader and exactly wrong for a grep.
    """
    text = path.read_text(encoding="utf-8")
    return LINE_COMMENT.sub("", BLOCK_COMMENT.sub("", text))


def _sources(root: Path, suffix: str) -> Iterator[Path]:
    for path in sorted(root.rglob(f"*{suffix}")):
        if "node_modules" not in path.parts:
            yield path


@pytest.fixture(scope="module")
def view_model(repo_root: Path) -> str:
    path = repo_root / VIEW_MODEL
    assert path.is_file(), f"{VIEW_MODEL} is the one ViewModel (D1)"
    return _code(path)


# --------------------------------------------------------------------------
# 6.1 — the ViewModel gained no 3D-specific logic
# --------------------------------------------------------------------------


@pytest.mark.parametrize("word", THREE_DIMENSIONAL)
def test_the_view_model_learned_nothing_three_dimensional(view_model: str, word: str) -> None:
    assert word not in view_model.lower(), (
        f"the shared ViewModel's code mentions {word!r}. D2: the view produces an "
        "anchor the ViewModel never inspects, and anything genuinely 3D — the part "
        "registry, the re-projection, the transport — lives in the view and in "
        "$lib/viewer. A 3D branch here is a design failure to be discussed, not "
        "merged quietly."
    )


def test_the_guard_is_over_something_that_could_fail(view_model: str) -> None:
    """A guard over an empty file passes for the wrong reason."""
    assert "compose(anchor" in view_model
    assert "anchorPayload" in view_model


def test_the_shared_annotation_module_does_not_reach_into_the_viewer(repo_root: Path) -> None:
    """The dependency goes one way, or the shared module is the viewer's."""
    offenders = [
        path.relative_to(repo_root / WEB).as_posix()
        for path in _sources(repo_root / ANNOTATION_MODULE, ".ts")
        if "$lib/viewer" in _code(path)
    ]

    assert not offenders, (
        "the annotation module is shared by both surfaces, so it may not depend on "
        f"either one of them: {offenders}"
    )


# --------------------------------------------------------------------------
# 6.2 — the viewer reaches threads, filters and triage through the ViewModel
# --------------------------------------------------------------------------


def _viewer_files(repo_root: Path) -> list[Path]:
    directory = repo_root / WEB / "src" / "lib" / "components"
    components = [directory / name for name in VIEWER_COMPONENTS]
    return [*components, *_sources(repo_root / VIEWER_MODULE, ".ts")]


def test_the_viewer_files_are_the_ones_on_disk(repo_root: Path) -> None:
    """A viewer component added without being listed here would not be guarded."""
    missing = [path for path in _viewer_files(repo_root) if not path.is_file()]

    assert not missing, f"these viewer files are named here and are not on disk: {missing}"


@pytest.mark.parametrize("module", SHARED_MODULES)
def test_no_viewer_file_imports_a_thread_filter_or_triage_module(
    repo_root: Path, module: str
) -> None:
    offenders = [
        path.relative_to(repo_root / WEB).as_posix()
        for path in _viewer_files(repo_root)
        if module in _code(path)
    ]

    assert not offenders, (
        f"{offenders} reach {module} directly. D2 limits the viewer to two "
        "conversions — pointer input into an anchor, and an anchor into a screen "
        "position — and everything else is read from the shared ViewModel. A "
        "second copy of 'which annotations are visible' is what this rule exists "
        "to prevent."
    )


def test_the_scene_module_holds_no_annotation_logic(repo_root: Path) -> None:
    """The engine module knows about meshes; it does not know about threads."""
    code = _code(repo_root / VIEWER_MODULE / "scene.ts").lower()

    for word in ("triage", "promote", "resolveannotation", "thread", "reply"):
        assert word not in code, f"scene.ts mentions {word!r}; annotations are not its business"


def test_only_the_scene_module_imports_the_engine(repo_root: Path) -> None:
    """D7's other direction: `three` is named in exactly one module of the app."""
    importers = [
        path.relative_to(repo_root / WEB).as_posix()
        for suffix in (".ts", ".svelte")
        for path in _sources(repo_root / WEB / "src", suffix)
        if re.search(r"""from\s*['"]three""", _code(path))
    ]

    assert importers == ["src/lib/viewer/scene.ts"], (
        "the 3D engine belongs to one module behind D1's interface, so a version "
        f"bump is one module's test suite: {importers}"
    )


# --------------------------------------------------------------------------
# 4.1 — the engine is a pinned dependency of the web application, and of nothing else
# --------------------------------------------------------------------------


ENGINE = "three"


def test_the_engine_is_pinned_to_an_exact_version(repo_root: Path) -> None:
    """D1: *"a substantial frontend dependency, a pinned version"*.

    A caret range would let a `pnpm install` on somebody's laptop resolve a
    different renderer from the one CI checked — and the module this whole
    change confines behind one interface is the one where that matters most,
    because *"a version bump is one module's test suite"* only holds if a bump
    is a commit rather than a Tuesday.
    """
    manifest = json.loads((repo_root / WEB / "package.json").read_text(encoding="utf-8"))
    declared = {
        **manifest.get("dependencies", {}),
        **manifest.get("devDependencies", {}),
    }

    for name in (ENGINE, f"@types/{ENGINE}"):
        assert name in declared, f"{name} is the viewer's engine and is declared here"
        assert declared[name][0].isdigit(), (
            f"{name} is declared as {declared[name]!r}; D1 pins the engine to an "
            "exact version rather than a range"
        )


def test_the_engine_is_not_a_backend_dependency(repo_root: Path) -> None:
    """The other half of 4.1: the backend's dependency set is unchanged.

    `three` is a browser renderer, and the whole of D6 is that the *system's*
    answers need no renderer. A Python package named after one would be the
    first sign that the split had been given up on.
    """
    backend = (repo_root / "pyproject.toml").read_text(encoding="utf-8")

    assert f'"{ENGINE}' not in backend
    assert "trimesh" in backend, "the one mesh reader the backend does have, so this is not vacuous"
