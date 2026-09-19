"""Tasks 1.6, 1.7, 1.5 and 2.2 — the structural constraints of the web application.

Three of `add-web-app-shell`'s decisions are conventions that no requirement can
express, because none of them changes observable product behaviour. The change
says so and says what to do about it: *"neither earns a requirement; both are
enforced here by structure and by tests"*. This module is that enforcement, and
it lives in the Python suite on purpose — `just check` is the contract, it runs
here, and a constraint that only bites when somebody remembers to run the
frontend's own runner is a constraint that stops biting in week three.

* **D1** — the only ViewModel in the application is the shared
  `AnnotationViewModel` owned by `add-model-sheet-2d`. MVVM earns its place in
  exactly one spot; spreading it everywhere destroys the argument for it.
* **D4** — a local component that reimplements a design-system primitive fails
  the build, and the only way past is a waiver naming the upstream request. The
  failure mode is the slow fork: a local Button *"just for this one case"*, then
  five more, then a design system nobody uses.
* **D7** — the viewer's scene module is reached by dynamic import only, so the
  3D engine is never in another screen's bundle. The build itself is checked by
  `apps/cybercanon/web/tests/code-splitting.test.ts`; what is checked here is
  the import that would silently undo it.
* **D2** — server state lives in the query cache. A view that built a client of
  its own would be the second copy of the truth.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterator
from pathlib import Path

import pytest

WEB = Path("apps/cybercanon/web")
SOURCE = WEB / "src"
ANNOTATION_MODULE = SOURCE / "lib" / "annotation"
INVENTORY = WEB / "design-system.json"

SCENE_IMPORT = re.compile(r"""import\s[^;]*?from\s*['"][^'"]*viewer/scene['"]""", re.S)
DYNAMIC_SCENE = re.compile(r"""import\(\s*['"][^'"]*viewer/scene['"]\s*\)""")
COMPONENT_NAME = re.compile(r"^[A-Z][A-Za-z0-9]*$")
CLIENT_CONSTRUCTION = re.compile(r"\bnew\s+(CanonClient|CanonApi)\b")

# What a waiver must carry to be one. D4: "the test has to be explicitly waived
# with a reference to the upstream request, which is the friction that keeps the
# waiver honest."
WAIVER_FIELDS = ("primitive", "component", "upstream", "reason")


@pytest.fixture(scope="module")
def web_root(repo_root: Path) -> Path:
    root = repo_root / WEB
    assert root.is_dir(), f"{WEB} is the SvelteKit application (task 1.1)"
    return root


@pytest.fixture(scope="module")
def inventory(repo_root: Path) -> dict:
    return json.loads((repo_root / INVENTORY).read_text(encoding="utf-8"))


def _sources(root: Path, suffix: str) -> Iterator[Path]:
    """Every file the application owns. `node_modules` and build output are not ours."""
    for path in sorted((root / "src").rglob(f"*{suffix}")):
        if "node_modules" not in path.parts and ".svelte-kit" not in path.parts:
            yield path


# --------------------------------------------------------------------------
# 1.6 — D1: no ViewModel outside the annotation module
# --------------------------------------------------------------------------


def test_no_view_model_exists_outside_the_annotation_module(web_root: Path) -> None:
    """`*.svelte.ts` is the ViewModel spelling (openspec/project.md)."""
    stray = [
        path.relative_to(web_root).as_posix()
        for path in _sources(web_root, ".svelte.ts")
        if ANNOTATION_MODULE not in path.parents
    ]

    assert not stray, (
        "D1 reserves MVVM for the one ViewModel that serves both the 2D sheet and "
        "the 3D viewer; routes, the browser and the asset page are plain Svelte "
        f"components with runes. ViewModels found outside {ANNOTATION_MODULE}: {stray}"
    )


def test_the_annotation_module_is_where_a_view_model_would_go(web_root: Path) -> None:
    """The rule names a place, so the place has to be the one add-model-sheet-2d uses."""
    assert ANNOTATION_MODULE.as_posix().endswith("src/lib/annotation"), ANNOTATION_MODULE


# --------------------------------------------------------------------------
# 1.7 — D4: a local reimplementation of a library primitive fails the build
# --------------------------------------------------------------------------


def _local_components(web_root: Path) -> dict[str, str]:
    """Every component this application defines, by its component name."""
    found: dict[str, str] = {}
    for path in _sources(web_root, ".svelte"):
        name = path.stem
        if COMPONENT_NAME.match(name):
            found[name] = path.relative_to(web_root).as_posix()
    return found


def _waivers(inventory: dict) -> dict[str, dict]:
    return {waiver["primitive"]: waiver for waiver in inventory["waivers"]}


def test_no_local_component_reimplements_a_design_system_primitive(
    web_root: Path, inventory: dict
) -> None:
    primitives = set(inventory["primitives"])
    waived = _waivers(inventory)
    reimplemented = {
        name: path
        for name, path in _local_components(web_root).items()
        if name in primitives and name not in waived
    }

    assert not reimplemented, (
        f"these components reimplement primitives {inventory['package']} already "
        f"provides: {reimplemented}. Import them from src/lib/design-system.ts. If "
        "the library genuinely lacks one, raise it upstream and add a waiver to "
        f"{INVENTORY} naming the request — D4 makes that the visible, reviewable "
        "exception rather than the quiet fork."
    )


def test_a_waiver_must_name_the_upstream_request(inventory: dict) -> None:
    """The friction that keeps the waiver honest, asserted rather than trusted."""
    for waiver in inventory["waivers"]:
        missing = [field for field in WAIVER_FIELDS if not waiver.get(field)]
        assert not missing, f"waiver {waiver} is missing {missing}"
        assert waiver["upstream"].startswith("http"), (
            f"waiver for {waiver['primitive']} must reference the upstream request, "
            f"not describe it: {waiver['upstream']}"
        )


def test_a_waiver_names_a_primitive_that_exists(inventory: dict) -> None:
    """A waiver against nothing is a waiver nobody will ever remove."""
    primitives = set(inventory["primitives"])
    unknown = [
        waiver["primitive"]
        for waiver in inventory["waivers"]
        if waiver["primitive"] not in primitives
    ]

    assert not unknown, f"{INVENTORY} waives primitives the library does not have: {unknown}"


def test_the_inventory_names_the_design_system_this_project_consumes(inventory: dict) -> None:
    assert inventory["package"] == "@cyberdynecorp/svelte-ui-core"
    assert inventory["foundation"] == "@cyberdynecorp/svelte-ui-foundation"
    assert inventory["primitives"], "an empty inventory would waive D4 entirely"


def test_the_inventory_matches_the_library_once_it_is_installed(
    web_root: Path, inventory: dict
) -> None:
    """While the packages are not installable here the inventory stands alone.

    The moment one *is* installed, it is the authority: the list cannot quietly
    drift from what the library actually exports. Task 1.2 is what installs it.
    """
    installed = web_root / "node_modules" / inventory["package"] / "package.json"
    if not installed.is_file():
        assert inventory["verified_against"] is None, (
            f"{INVENTORY} claims to have been read from an installed "
            f"{inventory['package']}, which is not in this checkout"
        )
        return
    version = json.loads(installed.read_text(encoding="utf-8"))["version"]
    assert inventory["verified_against"] == version, (
        f"{INVENTORY} was read from {inventory['verified_against']} and "
        f"{inventory['package']} {version} is installed; re-read the inventory"
    )


# --------------------------------------------------------------------------
# 1.5 — D7: the scene module is reached by dynamic import only
# --------------------------------------------------------------------------


def test_nothing_imports_the_viewer_scene_statically(web_root: Path) -> None:
    offenders = [
        path.relative_to(web_root).as_posix()
        for suffix in (".ts", ".svelte")
        for path in _sources(web_root, suffix)
        if SCENE_IMPORT.search(path.read_text(encoding="utf-8"))
    ]

    assert not offenders, (
        "D7 keeps the 3D engine out of every other screen's bundle, and a static "
        f"import silently undoes it: {offenders}. Use `await import(...)`."
    )


def test_the_viewer_surface_reaches_it_dynamically(web_root: Path) -> None:
    """The other half: a boundary nothing crosses at all is a boundary of nothing."""
    dynamic = [
        path.relative_to(web_root).as_posix()
        for path in _sources(web_root, ".svelte")
        if DYNAMIC_SCENE.search(path.read_text(encoding="utf-8"))
    ]

    assert dynamic, "no screen loads the viewer scene; the split has nothing to split"


# --------------------------------------------------------------------------
# 2.2 — D2: no component holds server state, and none builds its own client
# --------------------------------------------------------------------------


def test_no_view_constructs_its_own_client_or_cache(web_root: Path) -> None:
    offenders = [
        path.relative_to(web_root).as_posix()
        for path in _sources(web_root, ".svelte")
        if CLIENT_CONSTRUCTION.search(path.read_text(encoding="utf-8"))
    ]

    assert not offenders, (
        "openspec/project.md: views never call the API directly. Server state is "
        f"loaded by the route and read from the one query cache (D2): {offenders}"
    )


def test_every_data_bearing_route_renders_through_the_closed_state_set(web_root: Path) -> None:
    """1.4 — a route with a load cannot resolve outside the closed set (D6)."""
    missing = []
    for load in _sources(web_root, "+page.ts"):
        screen = load.with_name("+page.svelte")
        if not screen.is_file():
            continue
        if "RouteScreen" not in screen.read_text(encoding="utf-8"):
            missing.append(screen.relative_to(web_root).as_posix())

    assert not missing, (
        "D6 makes empty, error and degraded route-level states rather than "
        f"conditionals; these screens render their data without them: {missing}"
    )
