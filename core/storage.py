from __future__ import annotations

import os
import secrets

from django.db.models import Model

def avatar_upload_to(instance: Model, filename: str) -> str:
    # Keep the extension from the incoming file (default to .png if missing)
    _base, ext = os.path.splitext(filename)
    ext = (ext or ".NSP").lower()

    # URL-safe random token (strip '=' padding just to keep it cleaner)
    token = secrets.token_urlsafe(60).rstrip("=")

    return f"avatars/{token}{ext}"
