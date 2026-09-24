"""Source glTF texture-channel summaries without sending image bytes to the web."""

from __future__ import annotations

from base64 import b64decode
from binascii import Error as Base64Error
from io import BytesIO
from typing import Any

from PIL import Image

from cybercanon.adapters.outbound.mesh.gltf_document import GltfDocument
from cybercanon.application.ports.mesh_inspector import SourceTexture, SourceVisuals


def read_visuals(document: GltfDocument) -> SourceVisuals:
    """Read material channels and embedded image headers; leave external sizes unknown."""
    textures: list[SourceTexture] = []
    for index, material in enumerate(document.gltf.materials or []):
        name = material.name or f"material_{index}"
        for channel, reference in _channels(material):
            width, height = _dimensions(document, reference.index)
            textures.append(SourceTexture(name, channel, width, height))
    return SourceVisuals(tuple(textures))


def _channels(material: Any) -> tuple[tuple[str, Any], ...]:
    pbr = material.pbrMetallicRoughness
    candidates = (
        ("base color", getattr(pbr, "baseColorTexture", None)),
        ("metallic roughness", getattr(pbr, "metallicRoughnessTexture", None)),
        ("normal", material.normalTexture),
        ("occlusion", material.occlusionTexture),
        ("emissive", material.emissiveTexture),
    )
    return tuple((channel, reference) for channel, reference in candidates if reference is not None)


def _dimensions(document: GltfDocument, texture_index: int) -> tuple[int | None, int | None]:
    try:
        texture = document.gltf.textures[texture_index]
        image = document.gltf.images[texture.source]
        content = _embedded(document, image)
        if content is None:
            return None, None
        with Image.open(BytesIO(content)) as pixels:
            return pixels.size
    except (AttributeError, Base64Error, IndexError, KeyError, OSError, TypeError, ValueError):
        return None, None


def _embedded(document: GltfDocument, image: Any) -> bytes | None:
    if image.bufferView is not None:
        view = document.gltf.bufferViews[image.bufferView]
        start = view.byteOffset or 0
        return document.blob[start : start + view.byteLength]
    if isinstance(image.uri, str) and image.uri.startswith("data:"):
        return b64decode(image.uri.partition(",")[2], validate=True)
    return None
