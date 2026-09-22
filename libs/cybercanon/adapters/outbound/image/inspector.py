"""`PillowImageInspector` — six facts from bytes, and the format from the content.

The whole adapter is one call into Pillow and a translation into
:class:`~cybercanon.domain.views.ImageFacts`. Two properties are worth stating
because they are requirements rather than implementation details:

* **The format comes from the content.** Pillow sniffs the header, so a TIFF
  whose file name ends in `.png` is reported as TIFF and refused as one. The
  adapter never sees a file name at all except to put it in a message, which is
  the strongest available form of *"format SHALL be determined from the file's
  own content, not from its filename extension"*.
* **Nothing is decoded that does not have to be.** `Image.open` reads the header
  and stops; the pixels are never loaded, so inspecting a rejected 41 MB image
  costs a header read rather than a decompression. That is also what keeps the
  *"validate before writing anything"* order cheap enough to be unconditional.

A decompression-bomb guard is left at Pillow's default deliberately: the
project's pixel ceiling is the domain's
(:class:`~cybercanon.domain.views.IngestionLimits`), and a second, invisible
limit inside an adapter would reject images the project said it accepts.
"""

from __future__ import annotations

from io import BytesIO

from PIL import Image, UnidentifiedImageError

from cybercanon.application.ports.image_inspector import ImageUnreadable
from cybercanon.domain.revisions import ContentHash
from cybercanon.domain.views import ImageFacts

ALPHA_MODES = frozenset({"RGBA", "LA", "PA", "RGBa", "La"})
"""The Pillow modes that carry a per-pixel alpha channel.

`P` is deliberately absent: a palette image *may* carry transparency, and it
does so through a `transparency` key rather than a mode, which is checked
separately below. Guessing from the mode alone would report every GIF-style
palette as opaque.
"""

TRANSPARENCY = "transparency"


class PillowImageInspector:
    """Reads an image's facts with Pillow. Decides nothing."""

    def inspect(self, content: bytes, *, name: str = "") -> ImageFacts:
        """The six facts these bytes carry, or a named refusal."""
        with _opened(content, name) as image:
            width, height = image.size
            return ImageFacts(
                format=_format_of(image, name),
                width=width,
                height=height,
                byte_size=len(content),
                content_hash=ContentHash.of(content),
                has_alpha=_has_alpha(image),
            )


def _opened(content: bytes, name: str) -> Image.Image:
    """The image, or :class:`ImageUnreadable` naming what could not be read."""
    if not content:
        raise ImageUnreadable(name or "the upload", "it is empty")
    try:
        return Image.open(BytesIO(content))
    except UnidentifiedImageError as error:
        raise ImageUnreadable(name or "the upload", "it is not a recognised image") from error
    except OSError as error:
        raise ImageUnreadable(name or "the upload", str(error)) from error


def _format_of(image: Image.Image, name: str) -> str:
    """The lowercase format name Pillow detected from the header."""
    detected = image.format
    if not detected:
        raise ImageUnreadable(name or "the upload", "its format could not be determined")
    return detected.lower()


def _has_alpha(image: Image.Image) -> bool:
    """Whether the image carries transparency, by mode or by palette key."""
    return image.mode in ALPHA_MODES or TRANSPARENCY in image.info


__all__ = ["ALPHA_MODES", "PillowImageInspector"]
