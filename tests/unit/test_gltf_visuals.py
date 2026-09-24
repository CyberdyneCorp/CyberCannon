"""Texture-channel inspection reads source image headers, not preview pixels."""

from __future__ import annotations

from io import BytesIO

import pytest
from PIL import Image as PillowImage
from pygltflib import GLTF2, BufferView, Image, Material, NormalMaterialTexture, Texture

from cybercanon.adapters.outbound.mesh.gltf_document import GltfDocument
from cybercanon.adapters.outbound.mesh.gltf_visuals import read_visuals
from cybercanon.application.ports.mesh_inspector import SourceTexture

pytestmark = pytest.mark.unit


def _png(width: int, height: int) -> bytes:
    content = BytesIO()
    PillowImage.new("RGB", (width, height)).save(content, format="PNG")
    return content.getvalue()


def _document(image: Image, blob: bytes = b"") -> GltfDocument:
    gltf = GLTF2(
        materials=[Material(name="Armor", normalTexture=NormalMaterialTexture(index=0))],
        textures=[Texture(source=0)],
        images=[image],
        bufferViews=[BufferView(buffer=0, byteOffset=0, byteLength=len(blob))],
    )
    return GltfDocument(gltf=gltf, blob=blob, source="model.glb")


def test_embedded_normal_map_reports_its_pixel_size() -> None:
    content = _png(1024, 512)
    visuals = read_visuals(_document(Image(bufferView=0, mimeType="image/png"), content))

    assert visuals.textures == (SourceTexture("Armor", "normal", 1024, 512),)


def test_external_image_keeps_channel_but_not_guessed_dimensions() -> None:
    visuals = read_visuals(_document(Image(uri="textures/normal.png")))

    assert visuals.textures == (SourceTexture("Armor", "normal"),)


def test_corrupt_embedded_image_does_not_break_source_inspection() -> None:
    visuals = read_visuals(_document(Image(bufferView=0, mimeType="image/png"), b"not png"))

    assert visuals.textures == (SourceTexture("Armor", "normal"),)


def test_an_untextured_material_has_no_reported_texture_channels() -> None:
    visuals = read_visuals(GltfDocument(GLTF2(materials=[Material(name="Bare")]), b"", "x.glb"))

    assert visuals.textures == ()
