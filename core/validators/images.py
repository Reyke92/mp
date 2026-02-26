from __future__ import annotations

import os
import warnings
from typing import Final

from django.core.exceptions import ValidationError
from django.core.validators import FileExtensionValidator

from PIL import Image, UnidentifiedImageError


# Keep this tight. Avoid SVG for avatars (it’s XML, not a raster image).
ALLOWED_IMAGE_EXTENSIONS: Final[list[str]] = ["jpg", "jpeg", "png", "webp"]
ALLOWED_IMAGE_FORMATS: Final[set[str]] = {"JPEG", "PNG", "WEBP"}

MAX_UPLOAD_BYTES: Final[int] = 5 * 1024 * 1024        # 5 MB
MAX_IMAGE_PIXELS: Final[int] = 25_000_000            # e.g., 25 MP


_extension_validator = FileExtensionValidator(ALLOWED_IMAGE_EXTENSIONS)  # case-insensitive per Django docs :contentReference[oaicite:3]{index=3}


def validate_uploaded_image(uploaded_file) -> None:
    """
    Validates:
      - file extension allowlist
      - file size
      - actual image parse/verify (Pillow)
      - image format allowlist (based on parsed content, not extension)
      - decompression bomb protection
    """
    # 1) Extension allowlist (fast fail)
    _extension_validator(uploaded_file)

    # 2) File size allowlist (fast fail)
    size = getattr(uploaded_file, "size", None)
    if size is not None and size > MAX_UPLOAD_BYTES:
        raise ValidationError(f"Image too large. Max size is {MAX_UPLOAD_BYTES} bytes.")

    # 3) Pillow safety: treat decompression bomb warnings as errors
    # Pillow docs: warnings can be turned into errors; very large images raise DecompressionBombError. :contentReference[oaicite:4]{index=4}
    previous_max = Image.MAX_IMAGE_PIXELS
    Image.MAX_IMAGE_PIXELS = MAX_IMAGE_PIXELS

    # Save/restore file pointer so we don't break later code
    try:
        original_pos = uploaded_file.tell()
    except Exception:
        original_pos = None

    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)

            # Pillow expects file pointer at start
            try:
                uploaded_file.seek(0)
            except Exception:
                pass

            # Verify header/structure
            try:
                img = Image.open(uploaded_file)
                img.verify()  # verifies integrity without fully decoding pixel data
            except (UnidentifiedImageError, OSError, Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
                raise ValidationError("Invalid or unsafe image file.") from exc

            # Re-open to inspect format/size reliably (verify() leaves file in unusable state for some operations)
            try:
                uploaded_file.seek(0)
                img2 = Image.open(uploaded_file)

                # Check dimensions (cheap)
                width, height = img2.size
                if (width * height) > MAX_IMAGE_PIXELS:
                    raise ValidationError("Image dimensions are too large.")

                # Check the true parsed format (don’t trust extension)
                if img2.format not in ALLOWED_IMAGE_FORMATS:
                    raise ValidationError("Unsupported image format.")
            except (UnidentifiedImageError, OSError, Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
                raise ValidationError("Invalid or unsafe image file.") from exc

    finally:
        Image.MAX_IMAGE_PIXELS = previous_max
        if original_pos is not None:
            try:
                uploaded_file.seek(original_pos)
            except Exception:
                pass
        else:
            try:
                uploaded_file.seek(0)
            except Exception:
                pass
