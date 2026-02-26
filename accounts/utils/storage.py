from __future__ import annotations

import secrets
import shutil
from pathlib import Path

from django.conf import settings

def copy_default_avatar_for_user() -> str:
    """
    Copies MEDIA_ROOT/DefaultAvatar.png to MEDIA_ROOT/avatars/<random>.png
    and returns the *relative* path to store in avatar_url, e.g. "avatars/abc.png"
    """
    media_root = Path(settings.MEDIA_ROOT)
    src = media_root / "DefaultAvatar.png"

    avatars_dir = media_root / "avatars"
    avatars_dir.mkdir(parents=True, exist_ok=True)

    token = secrets.token_urlsafe(60).rstrip("=")
    filename = f"{token}.png"

    dst = avatars_dir / filename

    if not src.exists():
        raise FileNotFoundError(f"Default avatar not found: {src}")

    shutil.copy2(src, dst)
    return f"avatars/{filename}"
