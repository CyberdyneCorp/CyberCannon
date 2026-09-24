"""The real browser displays repository images and the emitted Draco preview."""

from __future__ import annotations

import json
import re
from base64 import b64encode
from pathlib import Path
from typing import Any

import pytest

from canon_fixtures import mesh
from cybercanon.adapters.outbound.mesh.trimesh_inspector import TrimeshInspector

pytestmark = pytest.mark.e2e

ASSET = "/p/ronin/a/mech_scout"
API = "/v1/projects/ronin/assets/mech_scout"
PNG = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jRZkAAAAASUVORK5CYII="


def _signed_in(page: Any) -> None:
    page.goto("/sign-in?next=/")
    page.locator("button.start").click()
    page.wait_for_url(lambda url: "/sign-in" not in url and "/signed-in" not in url)
    page.locator('[data-signed-in="yes"]').wait_for()


def _answer(route: Any, data: dict[str, Any]) -> None:
    route.fulfill(
        status=200,
        content_type="application/json",
        body=json.dumps({"version": "v1", "data": data}),
    )


def _descriptor(size: int, parts: list[str], triangles: int) -> dict[str, Any]:
    return {
        "project": "ronin",
        "asset": "mech_scout",
        "path": "characters/mech_scout/asset.yaml",
        "revision": "r1",
        "preview": {
            "key": "previews/test.glb",
            "source_export": "rigged.glb",
            "size_bytes": size,
            "content_type": "model/gltf-binary",
        },
        "source_export": "rigged.glb",
        "latest_validated_export": "rigged.glb",
        "derived_from_latest": True,
        "counts": {"triangles": triangles, "objects": 2, "materials": 1},
        "source_visuals": {
            "textures": [{"material": "Armor", "channel": "normal", "width": 1024, "height": 1024}]
        },
        "parts": parts,
        "clips": [],
        "coverage": {"states": [], "unclaimed": []},
        "absent": None,
        "reason": None,
    }


def test_sheet_displays_one_current_reference_image(page: Any) -> None:
    _signed_in(page)

    def reference(route: Any) -> None:
        url = route.request.url
        if url.endswith("/revisions"):
            _answer(
                route,
                {
                    "asset": "mech_scout",
                    "slot": "mech_scout_front",
                    "path": "characters/mech_scout/concept/mech_scout_front.png",
                    "removed": False,
                    "revisions": [{"revision": "r1", "current": True, "removed": False}],
                },
            )
        else:
            _answer(
                route,
                {
                    "asset": "mech_scout",
                    "slot": "mech_scout_front",
                    "revision": "r1",
                    "content": PNG,
                },
            )

    page.route(re.compile(rf"{API}/views/mech_scout_front/revisions(?:/r1)?$"), reference)
    page.goto(f"{ASSET}?surface=sheet")

    image = page.locator('figure[data-view="mech_scout_front"] img')
    image.wait_for()
    assert image.count() == 1
    assert image.evaluate("image => image.complete && image.naturalWidth === 1")
    frame = page.locator('figure[data-view="mech_scout_front"] .frame')
    ratio = frame.evaluate("frame => frame.clientWidth / frame.clientHeight")
    assert 0.98 <= ratio <= 1.02


def test_sheet_annotation_stroke_saves_and_reopens(page: Any) -> None:
    _signed_in(page)
    page.goto(f"{ASSET}?surface=sheet")

    image = page.locator('figure[data-view="mech_scout_front"] .image')
    image.wait_for()
    box = image.bounding_box()
    assert box is not None
    y_by_width = {1920: 0.30, 1280: 0.45, 390: 0.60, 834: 0.75}
    image.click(
        position={"x": box["width"] * 0.80, "y": box["height"] * y_by_width[page.viewport_size["width"]]}
    )
    page.get_by_role("heading", name="New annotation").wait_for()
    composer = page.locator(".composer")
    assert f"Image view · mech_scout_front" in composer.inner_text()
    assert page.get_by_role("button", name="Save", exact=True).is_disabled()
    x, y = box["x"] + box["width"] / 2, box["y"] + box["height"] / 2
    page.mouse.move(x, y)
    page.mouse.down()
    page.mouse.move(x + 30, y + 20, steps=4)
    page.mouse.up()
    assert "1 stroke(s) drawn" in page.locator(".composer").inner_text()

    text = f"Browser check: 2D annotation with stroke at {page.viewport_size['width']}px"
    page.get_by_role("textbox", name="what this annotation says").fill(text)
    assert page.get_by_role("button", name="Save", exact=True).is_enabled()
    page.get_by_role("button", name="Save", exact=True).click()
    page.get_by_role("heading", name="New annotation").wait_for(state="detached")
    pin = page.locator(f'figure[data-view="mech_scout_front"] .pin[title="{text}"]')
    pin.wait_for()
    assert pin.get_attribute("aria-label") == f"art-direction annotation, open: {text}"
    page.reload()
    pin.wait_for()
    pin.click()
    assert page.get_by_role("heading", name="New annotation").count() == 0
    assert text in page.locator(".thread .text").first.inner_text()
    assert page.locator('figure[data-view="mech_scout_front"] svg.marks polyline').count() >= 1


def test_viewer_decodes_a_real_draco_preview(page: Any, tmp_path: Path) -> None:
    _signed_in(page)
    mesh.write_rigged_glb(tmp_path / "rigged.glb")
    inspector = TrimeshInspector(root=tmp_path)
    preview = inspector.emit_preview(inspector.inspect("rigged.glb"))
    encoded = b64encode(preview.content).decode("ascii")

    def descriptor(route: Any) -> None:
        _answer(route, _descriptor(len(preview.content), list(preview.parts), preview.triangles))

    def content(route: Any) -> None:
        _answer(
            route,
            {
                "asset": "mech_scout",
                "preview": "previews/test.glb",
                "source_export": "rigged.glb",
                "content_type": "model/gltf-binary",
                "size_bytes": len(preview.content),
                "content": encoded,
            },
        )

    page.route(re.compile(rf"{API}/preview$"), descriptor)
    page.route(re.compile(rf"{API}/preview/content$"), content)
    page.goto(f"{ASSET}?surface=viewer")

    page.get_by_text("Triangles (preview)").wait_for(timeout=30_000)
    assert page.locator('[aria-label="3D viewer"] canvas').count() == 1
    assert page.get_by_text("SM_MechScout_Shoulder_L").count() >= 1
    assert "Armor · normal: 1024 \u00d7 1024 px" in page.locator("main").inner_text()
    assert "Preview vertex normals" in page.locator("main").inner_text()

    canvas = page.locator('[aria-label="3D viewer"] canvas')
    parts = page.locator('[aria-label="3D viewer"] [aria-label="parts"]')
    canvas_box = canvas.bounding_box()
    parts_box = parts.bounding_box()
    assert canvas_box is not None and parts_box is not None
    width = page.viewport_size["width"]
    if width > 960:
        assert canvas_box["width"] > width / 2
        assert parts_box["x"] > canvas_box["x"] + canvas_box["width"]
        assert canvas_box["height"] <= min(512, page.viewport_size["height"] * 0.46) + 2
    else:
        assert parts_box["y"] >= canvas_box["y"] + canvas_box["height"]
    thread_index = page.locator('[aria-label="annotations"] .thread-index').bounding_box()
    discussion = page.locator('[aria-label="annotations"] aside').bounding_box()
    assert thread_index is not None and discussion is not None
    if width > 960:
        assert discussion["x"] > thread_index["x"] + thread_index["width"]
    else:
        assert discussion["y"] >= thread_index["y"] + thread_index["height"]
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth + 2")

    page.set_viewport_size({"width": width - 80, "height": page.viewport_size["height"]})
    page.wait_for_function(
        """() => {
            const canvas = document.querySelector('[aria-label="3D viewer"] canvas');
            return canvas && Math.abs(canvas.width - canvas.clientWidth) <= 1
                && Math.abs(canvas.height - canvas.clientHeight) <= 1;
        }"""
    )

    before = canvas.screenshot()
    box = canvas.bounding_box()
    assert box is not None
    x, y = box["x"] + box["width"] / 2, box["y"] + box["height"] / 2
    page.mouse.move(x, y)
    page.mouse.down()
    page.mouse.move(x + 110, y + 45, steps=8)
    page.mouse.up()
    assert canvas.screenshot() != before
    assert page.get_by_role("heading", name="New annotation").count() == 0

    before_zoom = canvas.screenshot()
    page.get_by_role("button", name="Zoom in").click()
    assert canvas.screenshot() != before_zoom
    page.get_by_role("button", name="Frame asset").click()

    current_box = canvas.bounding_box()
    assert current_box is not None
    for u, v in ((0.48, 0.44), (0.52, 0.48), (0.46, 0.54), (0.54, 0.56)):
        canvas.click(position={"x": current_box["width"] * u, "y": current_box["height"] * v})
        if page.get_by_role("heading", name="New annotation").count():
            break
    page.get_by_role("heading", name="New annotation").wait_for()
    composer = page.locator(".composer")
    assert "Model part ·" in composer.inner_text()
    placed_part = composer.locator(".placement").inner_text().split(" · ", 1)[1]
    assert composer.get_by_role("button", name="Undo stroke").count() == 0
    assert composer.get_by_role("button", name="Save", exact=True).is_disabled()
    text = f"Browser check: 3D annotation at {page.viewport_size['width']}px"
    page.get_by_role("textbox", name="what this annotation says").fill(text)
    page.get_by_role("button", name="Save", exact=True).click()
    page.get_by_role("heading", name="New annotation").wait_for(state="detached")
    assert text in page.locator('[aria-label="annotations"]').inner_text()
    model_note = page.locator('[aria-label="model annotations"] button', has_text=text)
    model_note.wait_for()
    assert placed_part in model_note.inner_text()
    model_note.click()
    assert text in page.locator(".thread .text").first.inner_text()
    page.reload()
    assert text in page.locator('[aria-label="annotations"]').inner_text()
    assert page.locator('[aria-label="model annotations"] button', has_text=text).count() == 1

    page.goto(ASSET)
    sections = page.locator(".asset-page [data-section]")
    sections.first.wait_for()
    assert sections.count() > 1
    first, second = sections.nth(0).bounding_box(), sections.nth(1).bounding_box()
    assert first is not None and second is not None
    if width > 960:
        positions = [section.bounding_box() for section in sections.all()]
        assert any(box is not None and box["x"] > first["x"] for box in positions[1:])
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth + 2")


def test_viewer_explains_decode_failure_and_keeps_threads(page: Any) -> None:
    _signed_in(page)
    page.route(
        re.compile(rf"{API}/preview$"),
        lambda route: _answer(route, _descriptor(4, ["SM_MechScout_Shoulder_L"], 1)),
    )
    page.route(
        re.compile(rf"{API}/preview/content$"),
        lambda route: _answer(
            route,
            {
                "asset": "mech_scout",
                "preview": "previews/test.glb",
                "source_export": "rigged.glb",
                "content_type": "model/gltf-binary",
                "size_bytes": 4,
                "content": b64encode(b"bad!").decode("ascii"),
            },
        ),
    )
    page.goto(f"{ASSET}?surface=viewer")

    page.get_by_text("The preview could not be decoded.", exact=False).wait_for(timeout=30_000)
    assert page.get_by_role("button", name="Retry").count() == 1
    assert "The pauldron still reads as a backpack" in page.locator("main").inner_text()
