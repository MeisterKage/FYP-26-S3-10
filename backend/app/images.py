"""Image processing for article cover images. Pure: bytes in, bytes out.

An uploaded file is never stored or served as it arrived. It is decoded, and
only the decoded pixels are re-encoded, which does three things at once:

  * Anything that is not really a JPEG, PNG or WebP fails to decode and is
    refused, whatever its filename or declared Content-Type says. A script
    renamed to .jpg never reaches a reader.
  * Metadata does not survive, because nothing but pixels is copied. A phone
    photo's EXIF block carries the GPS position it was taken at, which for a
    writer photographing near home is their address.
  * Every image is served at two known sizes, so a 6000px original cannot make
    each front-page visit download megabytes.

Output is WebP, which every current browser displays and which is roughly a
third smaller than JPEG at the same quality.
"""
from __future__ import annotations

import io
from dataclasses import dataclass

from PIL import Image, ImageOps, UnidentifiedImageError

#: What a writer may upload. Checked against what Pillow actually decodes, not
#: against the filename.
ACCEPTED_FORMATS = {"JPEG", "PNG", "WEBP"}
MAX_UPLOAD_BYTES = 5 * 1024 * 1024
#: A decompression bomb is a small file that decodes to an enormous image. 40
#: megapixels is well above any camera a writer uses and far below one that
#: exhausts a free-tier server's memory.
MAX_PIXELS = 40_000_000
#: Anything smaller cannot fill the article header without visible blur.
MIN_WIDTH = 400

#: 1200px stays sharp in the article column on a high-density screen. Measured
#: on a worst case for compression (dense foliage): 1600px at quality 82 was
#: 658 KB; 1200px at 76 is 322 KB, and ordinary photos come in well under it.
LARGE_WIDTH = 1200
THUMB_WIDTH = 640
QUALITY = 76


class ImageRejected(ValueError):
    """The upload is not an image this platform will serve. The message is for the writer."""


@dataclass(frozen=True)
class ProcessedImage:
    large: bytes
    thumb: bytes
    width: int
    height: int


def _encode(image: Image.Image, width: int) -> bytes:
    if image.width > width:
        height = round(image.height * width / image.width)
        image = image.resize((width, height), Image.Resampling.LANCZOS)
    out = io.BytesIO()
    #No exif=, no icc_profile=: only pixels are written.
    image.save(out, format="WEBP", quality=QUALITY, method=6)
    return out.getvalue()


def process(data: bytes) -> ProcessedImage:
    """Validate and re-encode one upload. Raises ImageRejected with a reason."""
    if not data:
        raise ImageRejected("The file is empty.")
    if len(data) > MAX_UPLOAD_BYTES:
        raise ImageRejected("Images must be 5 MB or smaller.")

    try:
        with Image.open(io.BytesIO(data)) as probe:
            fmt = probe.format
            width, height = probe.size
    except (UnidentifiedImageError, OSError):
        raise ImageRejected("That file is not an image we can read. Use a JPEG, PNG or WebP.")

    if fmt not in ACCEPTED_FORMATS:
        raise ImageRejected("Use a JPEG, PNG or WebP image.")
    #Checked from the header before decoding, so a bomb is refused without
    #ever being expanded into memory.
    if width * height > MAX_PIXELS:
        raise ImageRejected("That image is too large. Keep it under 40 megapixels.")
    if width < MIN_WIDTH:
        raise ImageRejected(f"That image is too small. It needs to be at least {MIN_WIDTH} pixels wide.")

    try:
        with Image.open(io.BytesIO(data)) as source:
            source.load()
            #A phone stores "rotate 90 degrees" in EXIF rather than rotating
            #the pixels. Dropping EXIF without applying it first would put
            #every portrait photo on its side.
            image = ImageOps.exif_transpose(source)
            image = image.convert("RGBA" if "A" in image.getbands() else "RGB")
    except (OSError, ValueError, Image.DecompressionBombError):
        raise ImageRejected("That image could not be read. It may be damaged.")

    return ProcessedImage(
        large=_encode(image, LARGE_WIDTH),
        thumb=_encode(image, THUMB_WIDTH),
        width=min(image.width, LARGE_WIDTH),
        height=(
            image.height if image.width <= LARGE_WIDTH
            else round(image.height * LARGE_WIDTH / image.width)
        ),
    )
