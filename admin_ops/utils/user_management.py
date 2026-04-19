from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable
from urllib.parse import urlencode

from django.contrib.auth import get_user_model
from django.core.paginator import Page, Paginator
from django.db import transaction
from django.db.models import Case, CharField, IntegerField, OuterRef, QuerySet, Subquery, Value, When
from django.db.models.functions import Coalesce, Lower
from django.urls import reverse

from accounts.models import UserProfile
from accounts.utils.auth import add_moderator_role, remove_moderator_role
from admin_ops.forms import (
    USER_ROLE_ADMINISTRATOR_VALUE,
    USER_ROLE_MODERATOR_VALUE,
    USER_ROLE_NONE_VALUE,
    USER_SORT_EMAIL_ASC_VALUE,
    USER_SORT_EMAIL_DESC_VALUE,
    USER_SORT_NAME_ASC_VALUE,
    USER_SORT_NAME_DESC_VALUE,
    USER_SORT_NEWEST_VALUE,
    USER_SORT_OLDEST_VALUE,
    USER_SORT_ROLE_ASC_VALUE,
    USER_SORT_ROLE_DESC_VALUE,
    USER_SORT_STATUS_ASC_VALUE,
    USER_SORT_STATUS_DESC_VALUE,
    USER_STATUS_ACTIVE_VALUE,
    USER_STATUS_BANNED_VALUE,
)
from admin_ops.models import AdministrationAction, AdministrationActionType, UserRoleAssignment
from admin_ops.utils.roles import ADMINISTRATOR_ROLE_NAME, MODERATOR_ROLE_NAME, is_user_administrator


PAGE_SIZE: int = 20
BAN_USER_ACTION_TYPE_NAME: str = "BanUser"
UNBAN_USER_ACTION_TYPE_NAME: str = "UnbanUser"
USER_EMAIL_SOURCE_FIELD_NAME: str = "username"


@dataclass(frozen=True)
class ManagedUserRow:
    user_id: int
    first_name: str
    last_name: str
    email_address: str
    role_name: str | None
    account_status_label: str
    account_status_variant: str
    profile_url: str
    select_url: str
    selected_card_url: str
    is_selected: bool


@dataclass(frozen=True)
class SelectedManagedUser:
    user_id: int
    first_name: str
    last_name: str
    email_address: str
    role_name: str | None
    account_status_label: str
    account_status_variant: str
    avatar_url: str | None
    profile_url: str
    can_assign_moderator: bool
    can_unassign_moderator: bool
    can_ban: bool
    can_unban: bool
    view_messages_url: str




@dataclass(frozen=True)
class SelectedUserCardContext:
    selected_user: SelectedManagedUser | None
    preserved_query_items: list[tuple[str, str]]
    page_number: int


@dataclass(frozen=True)
class UserManagementPageContext:
    page_obj: Page[Any]
    table_rows: list[ManagedUserRow]
    selected_user: SelectedManagedUser | None
    total_user_count: int
    filter_summary_parts: list[str]
    preserved_query_string_without_page: str
    preserved_query_string_without_selected: str
    preserved_query_items: list[tuple[str, str]]
    selected_user_id: int | None
    page_range: list[int | str]


class UserManagementActionError(Exception):
    """Raised when a user-management action cannot be completed."""


class UserManagementPermissionError(Exception):
    """Raised when a user-management action is not permitted."""


class UnsupportedUserManagementActionError(Exception):
    """Raised when an unknown action name is submitted."""



def build_user_management_page_context(
    *,
    search_email: str,
    account_status: str,
    user_role: str,
    sort_by: str,
    page_number: int,
    selected_user_id: int | None,
    base_url: str,
    acting_user_id: int,
) -> UserManagementPageContext:
    normalized_email: str = search_email.strip()
    queryset: QuerySet[Any] = _build_user_management_queryset(
        search_email=normalized_email,
        account_status=account_status,
        user_role=user_role,
    )
    queryset = _apply_sort(queryset=queryset, sort_by=sort_by)

    paginator: Paginator = Paginator(queryset, PAGE_SIZE)
    page_obj: Page[Any] = paginator.get_page(page_number)
    preserved_query_items_without_page: list[tuple[str, str]] = _build_preserved_query_items(
        search_email=normalized_email,
        account_status=account_status,
        user_role=user_role,
        sort_by=sort_by,
        selected_user_id=selected_user_id,
        exclude_keys={"page"},
    )
    preserved_query_items_without_selected: list[tuple[str, str]] = _build_preserved_query_items(
        search_email=normalized_email,
        account_status=account_status,
        user_role=user_role,
        sort_by=sort_by,
        selected_user_id=selected_user_id,
        exclude_keys={"selected"},
    )

    selected_user: SelectedManagedUser | None = _resolve_selected_user(
        queryset=queryset,
        page_obj=page_obj,
        selected_user_id=selected_user_id,
        acting_user_id=acting_user_id,
    )
    resolved_selected_user_id: int | None = selected_user.user_id if selected_user is not None else None

    table_rows: list[ManagedUserRow] = []
    for user in page_obj.object_list:
        current_user_id: int = int(user.id)
        table_rows.append(
            ManagedUserRow(
                user_id=current_user_id,
                first_name=_get_display_first_name(user),
                last_name=_get_display_last_name(user),
                email_address=str(getattr(user, USER_EMAIL_SOURCE_FIELD_NAME, "")),
                role_name=_normalize_role_name(getattr(user, "role_name", None)),
                account_status_label=_get_account_status_label(bool(user.is_active)),
                account_status_variant=_get_account_status_variant(bool(user.is_active)),
                profile_url=reverse("view_profile", kwargs={"id": current_user_id}),
                select_url=_build_selection_url(
                    base_url=base_url,
                    search_email=normalized_email,
                    account_status=account_status,
                    user_role=user_role,
                    sort_by=sort_by,
                    selected_user_id=current_user_id,
                    page_number=page_obj.number,
                ),
                selected_card_url=_build_selected_card_url(
                    user_id=current_user_id,
                    search_email=normalized_email,
                    account_status=account_status,
                    user_role=user_role,
                    sort_by=sort_by,
                    page_number=page_obj.number,
                ),
                is_selected=current_user_id == resolved_selected_user_id,
            )
        )
    if selected_user is not None:
        selected_profile_by_user_id: dict[int, UserProfile] = _get_profiles_for_user_ids([selected_user.user_id])
        selected_profile: UserProfile | None = selected_profile_by_user_id.get(selected_user.user_id)
        selected_user = _hydrate_selected_user(selected_user=selected_user, profile=selected_profile)

    filter_summary_parts: list[str] = _build_filter_summary_parts(
        search_email=normalized_email,
        account_status=account_status,
        user_role=user_role,
        total_user_count=paginator.count,
    )

    page_range: list[int | str] = list(paginator.get_elided_page_range(number=page_obj.number, on_each_side=1, on_ends=1))

    return UserManagementPageContext(
        page_obj=page_obj,
        table_rows=table_rows,
        selected_user=selected_user,
        total_user_count=paginator.count,
        filter_summary_parts=filter_summary_parts,
        preserved_query_string_without_page=urlencode(preserved_query_items_without_page, doseq=True),
        preserved_query_string_without_selected=urlencode(preserved_query_items_without_selected, doseq=True),
        preserved_query_items=preserved_query_items_without_selected,
        selected_user_id=resolved_selected_user_id,
        page_range=page_range,
    )



def build_selected_user_card_context(
    *,
    user_id: int,
    search_email: str,
    account_status: str,
    user_role: str,
    sort_by: str,
    page_number: int,
    acting_user_id: int,
) -> SelectedUserCardContext:
    normalized_email: str = search_email.strip()
    queryset: QuerySet[Any] = _build_user_management_queryset(
        search_email=normalized_email,
        account_status=account_status,
        user_role=user_role,
    )
    queryset = _apply_sort(queryset=queryset, sort_by=sort_by)

    selected_user: SelectedManagedUser | None = _resolve_selected_user_object(
        queryset=queryset,
        selected_user_id=user_id,
        acting_user_id=acting_user_id,
    )
    if selected_user is not None:
        selected_profile_by_user_id: dict[int, UserProfile] = _get_profiles_for_user_ids([selected_user.user_id])
        selected_profile: UserProfile | None = selected_profile_by_user_id.get(selected_user.user_id)
        selected_user = _hydrate_selected_user(selected_user=selected_user, profile=selected_profile)

    preserved_query_items: list[tuple[str, str]] = _build_preserved_query_items(
        search_email=normalized_email,
        account_status=account_status,
        user_role=user_role,
        sort_by=sort_by,
        selected_user_id=user_id,
        exclude_keys={"selected"},
    )

    return SelectedUserCardContext(
        selected_user=selected_user,
        preserved_query_items=preserved_query_items,
        page_number=page_number,
    )



def _build_user_management_queryset(
    *,
    search_email: str,
    account_status: str,
    user_role: str,
) -> QuerySet[Any]:
    user_model: type[Any] = get_user_model()
    role_name_subquery: Subquery = Subquery(
        UserRoleAssignment.objects.filter(user_id=OuterRef("pk"))
        .select_related("role")
        .values("role__role_name")[:1],
        output_field=CharField(),
    )

    queryset: QuerySet[Any] = (
        user_model.objects.all()
        .annotate(role_name=role_name_subquery)
        .annotate(first_name_sort=Lower(Coalesce("first_name", Value(""))))
        .annotate(last_name_sort=Lower(Coalesce("last_name", Value(""))))
        .annotate(email_sort=Lower(Coalesce(USER_EMAIL_SOURCE_FIELD_NAME, Value(""))))
        .annotate(role_name_sort=Lower(Coalesce("role_name", Value("zzzzzz"))))
        .annotate(
            status_sort=Case(
                When(is_active=True, then=Value(0)),
                default=Value(1),
                output_field=IntegerField(),
            )
        )
    )

    # Email addresses are stored in the Django user model's username field in this project.
    if search_email != "":
        queryset = queryset.filter(**{f"{USER_EMAIL_SOURCE_FIELD_NAME}__icontains": search_email})

    if account_status == USER_STATUS_ACTIVE_VALUE:
        queryset = queryset.filter(is_active=True)
    elif account_status == USER_STATUS_BANNED_VALUE:
        queryset = queryset.filter(is_active=False)

    if user_role == USER_ROLE_NONE_VALUE:
        queryset = queryset.filter(role_name__isnull=True)
    elif user_role == USER_ROLE_MODERATOR_VALUE:
        queryset = queryset.filter(role_name__iexact=MODERATOR_ROLE_NAME)
    elif user_role == USER_ROLE_ADMINISTRATOR_VALUE:
        queryset = queryset.filter(role_name__iexact=ADMINISTRATOR_ROLE_NAME)

    return queryset



def perform_user_management_action(
    *,
    requesting_user_id: int,
    target_user_id: int,
    action_name: str,
) -> str:
    if action_name == "assign_moderator":
        add_moderator_role(requesting_user_id=requesting_user_id, target_user_id=target_user_id)
        return "Moderator role assigned successfully."

    if action_name == "unassign_moderator":
        remove_moderator_role(requesting_user_id=requesting_user_id, target_user_id=target_user_id)
        return "Moderator role removed successfully."

    if action_name == "ban_user":
        _set_user_active_state(
            requesting_user_id=requesting_user_id,
            target_user_id=target_user_id,
            is_active=False,
        )
        return "User account was banned successfully."

    if action_name == "unban_user":
        _set_user_active_state(
            requesting_user_id=requesting_user_id,
            target_user_id=target_user_id,
            is_active=True,
        )
        return "User account was unbanned successfully."

    raise UnsupportedUserManagementActionError("Unsupported user-management action.")



def _apply_sort(*, queryset: QuerySet[Any], sort_by: str) -> QuerySet[Any]:
    if sort_by == USER_SORT_OLDEST_VALUE:
        return queryset.order_by("date_joined", "id")
    if sort_by == USER_SORT_NAME_ASC_VALUE:
        return queryset.order_by("last_name_sort", "first_name_sort", "email_sort", "id")
    if sort_by == USER_SORT_NAME_DESC_VALUE:
        return queryset.order_by("-last_name_sort", "-first_name_sort", "-email_sort", "-id")
    if sort_by == USER_SORT_EMAIL_ASC_VALUE:
        return queryset.order_by("email_sort", "id")
    if sort_by == USER_SORT_EMAIL_DESC_VALUE:
        return queryset.order_by("-email_sort", "-id")
    if sort_by == USER_SORT_ROLE_ASC_VALUE:
        return queryset.order_by("role_name_sort", "email_sort", "id")
    if sort_by == USER_SORT_ROLE_DESC_VALUE:
        return queryset.order_by("-role_name_sort", "email_sort", "-id")
    if sort_by == USER_SORT_STATUS_ASC_VALUE:
        return queryset.order_by("status_sort", "email_sort", "id")
    if sort_by == USER_SORT_STATUS_DESC_VALUE:
        return queryset.order_by("-status_sort", "email_sort", "id")

    return queryset.order_by("-date_joined", "-id")



def _get_profiles_for_user_ids(user_ids: Iterable[int]) -> dict[int, UserProfile]:
    normalized_user_ids: list[int] = [int(user_id) for user_id in user_ids]
    if not normalized_user_ids:
        return {}

    profiles: list[UserProfile] = list(
        UserProfile.objects.select_related("city", "city__state")
        .filter(user_id__in=normalized_user_ids)
    )
    return {int(profile.user_id): profile for profile in profiles}



def _resolve_selected_user(
    *,
    queryset: QuerySet[Any],
    page_obj: Page[Any],
    selected_user_id: int | None,
    acting_user_id: int,
) -> SelectedManagedUser | None:
    selected_user_object: Any | None = None

    if selected_user_id is not None:
        selected_user_object = queryset.filter(id=selected_user_id).first()

    if selected_user_object is None:
        selected_user_object = page_obj.object_list[0] if page_obj.object_list else None

    return _build_selected_managed_user(
        selected_user_object=selected_user_object,
        acting_user_id=acting_user_id,
    )



def _resolve_selected_user_object(
    *,
    queryset: QuerySet[Any],
    selected_user_id: int,
    acting_user_id: int,
) -> SelectedManagedUser | None:
    selected_user_object: Any | None = queryset.filter(id=selected_user_id).first()
    return _build_selected_managed_user(
        selected_user_object=selected_user_object,
        acting_user_id=acting_user_id,
    )



def _build_selected_managed_user(
    *,
    selected_user_object: Any | None,
    acting_user_id: int,
) -> SelectedManagedUser | None:
    if selected_user_object is None:
        return None

    role_name: str | None = _normalize_role_name(getattr(selected_user_object, "role_name", None))
    user_id: int = int(selected_user_object.id)

    is_self_selection: bool = user_id == int(acting_user_id)
    is_administrator_target: bool = (role_name or "").lower() == ADMINISTRATOR_ROLE_NAME.lower()

    can_assign_moderator: bool = (
        not is_self_selection
        and not is_administrator_target
        and (role_name is None or role_name.lower() != MODERATOR_ROLE_NAME.lower())
    )
    can_unassign_moderator: bool = (
        not is_self_selection
        and role_name is not None
        and role_name.lower() == MODERATOR_ROLE_NAME.lower()
    )

    return SelectedManagedUser(
        user_id=user_id,
        first_name=_get_display_first_name(selected_user_object),
        last_name=_get_display_last_name(selected_user_object),
        email_address=str(getattr(selected_user_object, USER_EMAIL_SOURCE_FIELD_NAME, "")),
        role_name=role_name,
        account_status_label=_get_account_status_label(bool(selected_user_object.is_active)),
        account_status_variant=_get_account_status_variant(bool(selected_user_object.is_active)),
        avatar_url=None,
        profile_url=reverse("view_profile", kwargs={"id": user_id}),
        can_assign_moderator=can_assign_moderator,
        can_unassign_moderator=can_unassign_moderator,
        can_ban=not is_self_selection and not is_administrator_target and bool(selected_user_object.is_active),
        can_unban=not is_self_selection and not is_administrator_target and not bool(selected_user_object.is_active),
        view_messages_url=reverse("user_conversations", kwargs={"user_id": user_id}),
    )



def _hydrate_selected_user(*, selected_user: SelectedManagedUser, profile: UserProfile | None) -> SelectedManagedUser:
    avatar_url: str | None = None
    if profile is not None:
        try:
            if profile.avatar:
                avatar_url = str(profile.avatar.url)
        except ValueError:
            avatar_url = None

    return SelectedManagedUser(
        user_id=selected_user.user_id,
        first_name=selected_user.first_name,
        last_name=selected_user.last_name,
        email_address=selected_user.email_address,
        role_name=selected_user.role_name,
        account_status_label=selected_user.account_status_label,
        account_status_variant=selected_user.account_status_variant,
        avatar_url=avatar_url,
        profile_url=selected_user.profile_url,
        can_assign_moderator=selected_user.can_assign_moderator,
        can_unassign_moderator=selected_user.can_unassign_moderator,
        can_ban=selected_user.can_ban,
        can_unban=selected_user.can_unban,
        view_messages_url=selected_user.view_messages_url,
    )



def _build_selection_url(
    *,
    base_url: str,
    search_email: str,
    account_status: str,
    user_role: str,
    sort_by: str,
    selected_user_id: int,
    page_number: int,
) -> str:
    query_items: list[tuple[str, str]] = _build_preserved_query_items(
        search_email=search_email,
        account_status=account_status,
        user_role=user_role,
        sort_by=sort_by,
        selected_user_id=selected_user_id,
        exclude_keys=set(),
    )
    query_items.append(("page", str(page_number)))
    return f"{base_url}?{urlencode(query_items, doseq=True)}"



def _build_selected_card_url(
    *,
    user_id: int,
    search_email: str,
    account_status: str,
    user_role: str,
    sort_by: str,
    page_number: int,
) -> str:
    query_items: list[tuple[str, str]] = _build_preserved_query_items(
        search_email=search_email,
        account_status=account_status,
        user_role=user_role,
        sort_by=sort_by,
        selected_user_id=user_id,
        exclude_keys={"selected"},
    )
    query_items.append(("page", str(page_number)))
    return f"{reverse('user_management_selected_card', kwargs={'user_id': user_id})}?{urlencode(query_items, doseq=True)}"



def _build_preserved_query_items(
    *,
    search_email: str,
    account_status: str,
    user_role: str,
    sort_by: str,
    selected_user_id: int | None,
    exclude_keys: set[str],
) -> list[tuple[str, str]]:
    query_items: list[tuple[str, str]] = []
    if "search_email" not in exclude_keys and search_email != "":
        query_items.append(("search_email", search_email))
    if "account_status" not in exclude_keys and account_status != "":
        query_items.append(("account_status", account_status))
    if "user_role" not in exclude_keys and user_role != "":
        query_items.append(("user_role", user_role))
    if "sort_by" not in exclude_keys and sort_by != "":
        query_items.append(("sort_by", sort_by))
    if "selected" not in exclude_keys and selected_user_id is not None:
        query_items.append(("selected", str(selected_user_id)))
    return query_items



def _build_filter_summary_parts(
    *,
    search_email: str,
    account_status: str,
    user_role: str,
    total_user_count: int,
) -> list[str]:
    summary_parts: list[str] = [f"{total_user_count} user{'s' if total_user_count != 1 else ''}"]

    if search_email != "":
        summary_parts.append(f"email contains “{search_email}”")
    if account_status == USER_STATUS_ACTIVE_VALUE:
        summary_parts.append("status: Active")
    elif account_status == USER_STATUS_BANNED_VALUE:
        summary_parts.append("status: Banned")

    if user_role == USER_ROLE_NONE_VALUE:
        summary_parts.append("role: No role")
    elif user_role == USER_ROLE_MODERATOR_VALUE:
        summary_parts.append("role: Moderator")
    elif user_role == USER_ROLE_ADMINISTRATOR_VALUE:
        summary_parts.append("role: Administrator")

    return summary_parts



def _get_display_first_name(user: Any) -> str:
    first_name: str = str(getattr(user, "first_name", "") or "").strip()
    if first_name != "":
        return first_name
    return "—"



def _get_display_last_name(user: Any) -> str:
    last_name: str = str(getattr(user, "last_name", "") or "").strip()
    if last_name != "":
        return last_name
    return "—"



def _normalize_role_name(role_name: Any) -> str | None:
    if role_name is None:
        return None
    normalized_role_name: str = str(role_name).strip()
    return normalized_role_name if normalized_role_name != "" else None



def _get_account_status_label(is_active: bool) -> str:
    return "Active" if is_active else "Banned"



def _get_account_status_variant(is_active: bool) -> str:
    return "active" if is_active else "banned"



def _set_user_active_state(
    *,
    requesting_user_id: int,
    target_user_id: int,
    is_active: bool,
) -> None:
    user_model: type[Any] = get_user_model()

    with transaction.atomic():
        user_model.objects.select_for_update().only("id").get(id=requesting_user_id)
        target_user: Any = user_model.objects.select_for_update().get(id=target_user_id)

        if requesting_user_id == target_user_id:
            raise UserManagementPermissionError("Administrators cannot ban or unban their own accounts from this page.")

        if not is_user_administrator(requesting_user_id):
            raise UserManagementPermissionError("Only Administrators may perform account enforcement actions.")

        existing_assignment: UserRoleAssignment | None = (
            UserRoleAssignment.objects.select_for_update()
            .select_related("role")
            .filter(user_id=target_user_id)
            .first()
        )
        target_role_name: str | None = None
        if existing_assignment is not None:
            target_role_name = str(existing_assignment.role.role_name).strip()

        if (target_role_name or "").lower() == ADMINISTRATOR_ROLE_NAME.lower():
            raise UserManagementPermissionError("Administrator accounts cannot be banned or unbanned from User Management.")

        current_is_active: bool = bool(target_user.is_active)
        if current_is_active == is_active:
            if is_active:
                raise UserManagementActionError("That account is already active.")
            raise UserManagementActionError("That account is already banned.")

        target_user.is_active = is_active
        target_user.save(update_fields=["is_active"])

        _log_account_status_change(
            requesting_user_id=requesting_user_id,
            target_user_id=target_user_id,
            is_active=is_active,
        )



def _log_account_status_change(
    *,
    requesting_user_id: int,
    target_user_id: int,
    is_active: bool,
) -> AdministrationAction:
    action_type_name: str = UNBAN_USER_ACTION_TYPE_NAME if is_active else BAN_USER_ACTION_TYPE_NAME
    action_type: AdministrationActionType = AdministrationActionType.objects.get(
        action_type_name__iexact=action_type_name,
    )
    state_label: str = "Account status changed to Active." if is_active else "Account status changed to Banned."
    return AdministrationAction.objects.create(
        actor_user_id=requesting_user_id,
        action_type=action_type,
        target_user_id=target_user_id,
        notes=state_label,
    )
