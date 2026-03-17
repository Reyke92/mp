from __future__ import annotations

from typing import Any, Optional

from django.contrib.auth import authenticate, get_user_model
from django.core.cache import cache
from django.db import transaction
from django.http import HttpRequest

from admin_ops.models import AdministrationAction, AdministrationActionType, Role, UserRoleAssignment
from admin_ops.utils.roles import (
    ADMINISTRATOR_ROLE_NAME,
    MODERATOR_ROLE_NAME,
    is_user_administrator as _db_is_user_administrator,
    is_user_moderator as _db_is_user_moderator,
)


_ROLE_CACHE_TIMEOUT_SECONDS: int = 3600
_ROLE_CACHE_KEY_PREFIX: str = "accounts:user-role-check:v1"
_ROLE_PRIORITY_BY_NAME: dict[str, int] = {
    MODERATOR_ROLE_NAME.lower(): 1,
    ADMINISTRATOR_ROLE_NAME.lower(): 2,
}
_ADD_ROLE_ACTION_TYPE_NAME: str = "AddRole"
_REMOVE_ROLE_ACTION_TYPE_NAME: str = "RemoveRole"


def authenticate_with_email(request: HttpRequest, email: str, password: str) -> Optional[Any]:
    """
    Tries to authenticate using the project's USERNAME_FIELD.
    Works if USERNAME_FIELD == "email" (custom user), or if you store email as username.
    """
    user_model = get_user_model()
    username_field: str = user_model.USERNAME_FIELD

    # Treat the input email as USERNAME_FIELD value.
    user = authenticate(request, **{username_field: email, "password": password})
    if user is not None:
        return user

    return None


def is_user_administrator(user: Any) -> bool:
    """
    Return whether the authenticated user currently has the Administrator role.
    """
    user_id: int | None = _extract_authenticated_user_id(user)
    if user_id is None:
        return False

    cache_key: str = _build_role_cache_key(user_id=user_id, role_name=ADMINISTRATOR_ROLE_NAME)
    cached_value: bool | None = cache.get(cache_key)
    if cached_value is not None:
        return cached_value

    has_role: bool = _db_is_user_administrator(user_id)
    cache.set(cache_key, has_role, _ROLE_CACHE_TIMEOUT_SECONDS)
    return has_role


def is_user_moderator(user: Any) -> bool:
    """
    Return whether the authenticated user currently has the Moderator role.
    """
    user_id: int | None = _extract_authenticated_user_id(user)
    if user_id is None:
        return False

    cache_key: str = _build_role_cache_key(user_id=user_id, role_name=MODERATOR_ROLE_NAME)
    cached_value: bool | None = cache.get(cache_key)
    if cached_value is not None:
        return cached_value

    has_role: bool = _db_is_user_moderator(user_id)
    cache.set(cache_key, has_role, _ROLE_CACHE_TIMEOUT_SECONDS)
    return has_role


def add_moderator_role(requesting_user_id: int, target_user_id: int, notes: str | None = None) -> UserRoleAssignment:
    """
    Assign the Moderator role to the target user.
    """
    return _add_user_role(
        requesting_user_id=requesting_user_id,
        target_user_id=target_user_id,
        role_name=MODERATOR_ROLE_NAME,
        notes=notes,
    )


def remove_moderator_role(requesting_user_id: int, target_user_id: int, notes: str | None = None) -> None:
    """
    Remove the Moderator role from the target user.
    """
    _remove_user_role(
        requesting_user_id=requesting_user_id,
        target_user_id=target_user_id,
        role_name=MODERATOR_ROLE_NAME,
        notes=notes,
    )


def _add_user_role(
    requesting_user_id: int,
    target_user_id: int,
    role_name: str,
    notes: str | None = None,
) -> UserRoleAssignment:
    """
    Assign the requested role to the target user and log the change.
    """
    if int(requesting_user_id) == int(target_user_id):
        raise ValueError("A user cannot assign a role to themselves.")

    with transaction.atomic():
        _lock_existing_user(requesting_user_id)
        _lock_existing_user(target_user_id)

        # Verify the acting user directly from the database so role changes take effect immediately.
        if not _db_is_user_administrator(requesting_user_id):
            raise PermissionError("Only Administrators may assign roles.")

        requested_role: Role = _get_role_by_name(role_name)
        existing_assignment: UserRoleAssignment | None = _get_single_user_role_assignment(target_user_id)

        if existing_assignment is not None:
            existing_role_name: str = str(existing_assignment.role.role_name)
            requested_role_name: str = str(requested_role.role_name)

            if existing_role_name.lower() == requested_role_name.lower():
                raise ValueError(f"The target user already has the {requested_role_name} role.")

            if _is_role_higher_priority(existing_role_name, requested_role_name):
                raise ValueError(
                    f"Cannot assign the {requested_role_name} role because the target user already has the higher-level {existing_role_name} role."
                )

            if _is_role_higher_priority(requested_role_name, existing_role_name):
                existing_assignment.delete()
            else:
                raise ValueError(
                    f"Cannot assign the {requested_role_name} role because the target user already has the different {existing_role_name} role."
                )

        created_assignment: UserRoleAssignment = UserRoleAssignment.objects.create(
            user_id=target_user_id,
            role=requested_role,
        )

        _invalidate_role_cache(target_user_id)
        _log_role_change(
            requesting_user_id=requesting_user_id,
            target_user_id=target_user_id,
            action_type_name=_ADD_ROLE_ACTION_TYPE_NAME,
            role_name=str(requested_role.role_name),
            notes=notes,
        )

    return created_assignment


def _remove_user_role(
    requesting_user_id: int,
    target_user_id: int,
    role_name: str,
    notes: str | None = None,
) -> None:
    """
    Remove the requested role from the target user and log the change.
    """
    if int(requesting_user_id) == int(target_user_id):
        raise ValueError("A user cannot remove a role from themselves.")

    with transaction.atomic():
        _lock_existing_user(requesting_user_id)
        _lock_existing_user(target_user_id)

        # Verify the acting user directly from the database so role changes take effect immediately.
        if not _db_is_user_administrator(requesting_user_id):
            raise PermissionError("Only Administrators may remove roles.")

        requested_role: Role = _get_role_by_name(role_name)
        existing_assignment: UserRoleAssignment | None = _get_single_user_role_assignment(target_user_id)
        if existing_assignment is None:
            raise ValueError(f"The target user does not have the {requested_role.role_name} role.")

        existing_role_name: str = str(existing_assignment.role.role_name)
        requested_role_name: str = str(requested_role.role_name)
        if existing_role_name.lower() != requested_role_name.lower():
            raise ValueError(f"The target user does not have the {requested_role_name} role.")

        existing_assignment.delete()
        _invalidate_role_cache(target_user_id)
        _log_role_change(
            requesting_user_id=requesting_user_id,
            target_user_id=target_user_id,
            action_type_name=_REMOVE_ROLE_ACTION_TYPE_NAME,
            role_name=requested_role_name,
            notes=notes,
        )


def _build_role_cache_key(*, user_id: int, role_name: str) -> str:
    normalized_role_name: str = role_name.strip().lower()
    return f"{_ROLE_CACHE_KEY_PREFIX}:{normalized_role_name}:{user_id}"


def _invalidate_role_cache(user_id: int) -> None:
    cache.delete_many(
        [
            _build_role_cache_key(user_id=user_id, role_name=ADMINISTRATOR_ROLE_NAME),
            _build_role_cache_key(user_id=user_id, role_name=MODERATOR_ROLE_NAME),
        ]
    )


def _extract_authenticated_user_id(user: Any) -> int | None:
    if not getattr(user, "is_authenticated", False):
        return None

    raw_user_id: Any = getattr(user, "id", None)
    if raw_user_id is None:
        return None

    try:
        return int(raw_user_id)
    except (TypeError, ValueError):
        return None


def _lock_existing_user(user_id: int) -> Any:
    user_model = get_user_model()
    return user_model.objects.select_for_update().only("id").get(id=user_id)


def _get_role_by_name(role_name: str) -> Role:
    return Role.objects.get(role_name__iexact=role_name)


def _get_single_user_role_assignment(target_user_id: int) -> UserRoleAssignment | None:
    assignments: list[UserRoleAssignment] = list(
        UserRoleAssignment.objects.select_for_update().select_related("role").filter(user_id=target_user_id)
    )
    if len(assignments) > 1:
        raise ValueError("The target user has multiple roles assigned. Resolve the data before changing roles.")
    if not assignments:
        return None
    return assignments[0]


def _is_role_higher_priority(candidate_role_name: str, comparison_role_name: str) -> bool:
    candidate_priority: int = _ROLE_PRIORITY_BY_NAME.get(candidate_role_name.strip().lower(), 0)
    comparison_priority: int = _ROLE_PRIORITY_BY_NAME.get(comparison_role_name.strip().lower(), 0)
    return candidate_priority > comparison_priority


def _log_role_change(
    *,
    requesting_user_id: int,
    target_user_id: int,
    action_type_name: str,
    role_name: str,
    notes: str | None,
) -> AdministrationAction:
    action_type: AdministrationActionType = AdministrationActionType.objects.get(
        action_type_name__iexact=action_type_name,
    )

    note_parts: list[str] = [f"Role: {role_name}."]
    trimmed_notes: str = (notes or "").strip()
    if trimmed_notes:
        note_parts.append(trimmed_notes)

    return AdministrationAction.objects.create(
        actor_user_id=requesting_user_id,
        action_type=action_type,
        target_user_id=target_user_id,
        notes=" ".join(note_parts),
    )
