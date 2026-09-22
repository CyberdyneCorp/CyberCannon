"""`PillowThumbnailRenderer` — fixed sizes, fixed settings, identical bytes twice.

`concept-ingestion` asks for one property and it is the only interesting thing
about this adapter: *"Derivation SHALL be deterministic: deriving twice from the
same source image SHALL produce thumbnails with the same content hash."* Without
it a wiped thumbnail cache could not be rebuilt onto the keys it had, and the
recovery `blob-storage` documents would restore *something* rather than *the
same thing*.

Determinism is bought by removing every input that is not the source bytes and
the requested size:

* one encoder (WebP), at one quality, with one method — never "whatever the
  library defaults to this year", because a Pillow upgrade would then silently
  re-key every thumbnail in the store;
* one resampling filter, named;
* the metadata dropped, because EXIF carries a timestamp and a thumbnail that
  embeds when it was made is a thumbnail whose digest changes every run;
* the image flattened onto nothing — alpha is kept, not composited against a
  colour somebody would have had to choose.

And, from D9, the property that is a *signature* rather than a setting: there is
no path in :meth:`derive`, so nothing here can write into a working copy.
"""

from __future__ import annotations

from io import BytesIO

from PIL import Image, UnidentifiedImageError

from cybercanon.application.ports.thumbnail_renderer import (
    DEFAULT_SIZES,
    THUMBNAIL_TYPE,
    Thumbnail,
    ThumbnailFailed,
)

ENCODER = "WEBP"
QUALITY = 82
METHOD = 4
"""The three encoder settings. Pinned, because a default that moves re-keys the store."""

RESAMPLE = Image.Resampling.LANCZOS
"""The one resampling filter. Named for the same reason the quality is."""


class PillowThumbnailRenderer:
    """Derives thumbnails with Pillow, into bytes and never into a working copy."""

    def derive(
        self, content: bytes, sizes: tuple[int, ...] = DEFAULT_SIZES
    ) -> tuple[Thumbnail, ...]:
        """One thumbnail per requested size, in the order they were requested."""
        source = _opened(content)
        return tuple(_thumbnail(source, size) for size in sizes)


def _opened(content: bytes) -> Image.Image:
    """The source image, or the failure that makes derivation a *pending step*."""
    try:
        image = Image.open(BytesIO(content))
        image.load()
    except (UnidentifiedImageError, OSError, ValueError) as error:
        raise ThumbnailFailed("the source image", str(error)) from error
    return image


def _thumbnail(source: Image.Image, size: int) -> Thumbnail:
    """One size, scaled to fit inside it, encoded with the pinned settings."""
    scaled = source.copy()
    scaled.thumbnail((size, size), RESAMPLE)
    buffer = BytesIO()
    scaled.save(buffer, format=ENCODER, quality=QUALITY, method=METHOD, exif=b"", icc_profile=None)
    width, height = scaled.size
    return Thumbnail(
        size=size,
        width=width,
        height=height,
        content=buffer.getvalue(),
        content_type=THUMBNAIL_TYPE,
    )


__all__ = ["ENCODER", "METHOD", "QUALITY", "RESAMPLE", "PillowThumbnailRenderer"]
