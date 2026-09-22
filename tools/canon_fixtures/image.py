"""Concept-view fixtures, written from code rather than committed as binaries.

The same rule `canon_fixtures.mesh` follows, for the same reason: the domain
suite runs over hand-built
:class:`~cybercanon.domain.views.ImageFacts` with zero files on disk (D1), and
the *adapter* suite has to be handed real images or it is checking nothing. So
these are produced here, in one place, deterministically.

Deterministic matters more than usual. `concept-ingestion` requires thumbnail
derivation to produce identical content hashes twice, and the port conformance
suite seeds the in-memory inspector with the facts of the very bytes it writes
for Pillow — which is only honest if the bytes are the same bytes every run. So
every writer paints from a fixed formula, saves with fixed settings, and emits
no timestamp.
"""

from __future__ import annotations

from io import BytesIO
from pathlib import Path

from PIL import Image

PNG = "PNG"
JPEG = "JPEG"
WEBP = "WEBP"
TIFF = "TIFF"

DEFAULT_WIDTH = 1024
DEFAULT_HEIGHT = 768
"""A 4:3 board — the shape most concept art arrives in."""


def image_bytes(
    image_format: str = PNG,
    width: int = DEFAULT_WIDTH,
    height: int = DEFAULT_HEIGHT,
    *,
    seed: int = 0,
    alpha: bool = False,
) -> bytes:
    """One image, painted from `seed` and encoded with fixed settings.

    `seed` changes the pixels and therefore the content hash, which is how a
    test stages *"the same slot, a different image"* without also changing the
    dimensions — the two things `concept-ingestion` and `view-versioning` care
    about separately.
    """
    image = _painted(width, height, seed=seed, alpha=alpha)
    buffer = BytesIO()
    image.save(buffer, format=image_format, **_settings(image_format))
    return buffer.getvalue()


def write_image(
    destination: Path,
    image_format: str = PNG,
    width: int = DEFAULT_WIDTH,
    height: int = DEFAULT_HEIGHT,
    *,
    seed: int = 0,
    alpha: bool = False,
) -> Path:
    """The same image, on disk, with its directory created."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(image_bytes(image_format, width, height, seed=seed, alpha=alpha))
    return destination


def not_an_image() -> bytes:
    """Bytes no decoder will accept — what an inspector has to refuse by name."""
    return b"this is not an image, it is a sentence about one"


def _painted(width: int, height: int, *, seed: int, alpha: bool) -> Image.Image:
    """A small deterministic gradient. Never noise: noise defeats every encoder."""
    mode = "RGBA" if alpha else "RGB"
    image = Image.new(mode, (width, height))
    pixels = image.load()
    assert pixels is not None
    for y in range(height):
        for x in range(0, width, _STEP):
            value = ((x + y + seed * 37) // _STEP) % 256
            colour = (value, (value * 2) % 256, (value * 3) % 256)
            for offset in range(min(_STEP, width - x)):
                pixels[x + offset, y] = (*colour, 255) if alpha else colour
    return image


_STEP = 16
"""How wide a painted band is. Bands keep the fixtures small and compressible."""


def _settings(image_format: str) -> dict[str, object]:
    """Fixed encoder settings per format, so two runs produce identical bytes."""
    if image_format == JPEG:
        return {"quality": 85, "optimize": False}
    if image_format == WEBP:
        return {"quality": 80, "method": 4}
    if image_format == PNG:
        return {"optimize": False, "compress_level": 6}
    return {}


__all__ = [
    "DEFAULT_HEIGHT",
    "DEFAULT_WIDTH",
    "JPEG",
    "PNG",
    "TIFF",
    "WEBP",
    "image_bytes",
    "not_an_image",
    "write_image",
]
