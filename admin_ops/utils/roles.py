from __future__ import annotations

from typing import Any

from admin_ops.models import UserRoleAssignment


ADMINISTRATOR_ROLE_NAME: str = "Administrator"
MODERATOR_ROLE_NAME: str = "Moderator"


def _extract_user_id(user_or_user_id: Any) -> int | None:
    """
    Normalize a Django user object or raw user ID into an integer user ID.
    """
    if user_or_user_id is None:
        return None

    if isinstance(user_or_user_id, int):
        return user_or_user_id

    if not getattr(user_or_user_id, "is_authenticated", False):
        return None

    raw_user_id: Any = getattr(user_or_user_id, "id", None)
    if raw_user_id is None:
        return None

    try:
        return int(raw_user_id)
    except (TypeError, ValueError):
        return None


def _user_has_role(user_or_user_id: Any, role_name: str) -> bool:
    """
    Return whether the given user currently has the specified role.
    """
    user_id: int | None = _extract_user_id(user_or_user_id)
    if user_id is None:
        return False

    return UserRoleAssignment.objects.filter(
        user_id=user_id,
        role__role_name__iexact=role_name,
    ).exists()


def is_user_administrator(user_or_user_id: Any) -> bool:
    """
    Return whether the given user currently has the Administrator role.
    """
    return _user_has_role(user_or_user_id, ADMINISTRATOR_ROLE_NAME)


def is_user_moderator(user_or_user_id: Any) -> bool:
    """
    Return whether the given user currently has the Moderator role.
    """
    return _user_has_role(user_or_user_id, MODERATOR_ROLE_NAME)
