from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable
from urllib.parse import urlencode

from django.contrib.auth import get_user_model
from django.core.paginator import Page, Paginator
from django.db.models import Case, CharField, IntegerField, OuterRef, Q, QuerySet, Subquery, Value, When
from django.db.models.functions import Coalesce, Concat, Lower
from django.urls import reverse

from accounts.models import UserProfile
from admin_ops.forms import (
    MODERATION_LOG_ACTION_TYPE_ALL_VALUE,
    MODERATION_LOG_ACTION_TYPE_BAN_USER_VALUE,
    MODERATION_LOG_ACTION_TYPE_FREEZE_LISTING_VALUE,
    MODERATION_LOG_SORT_ACTION_ASC_VALUE,
    MODERATION_LOG_SORT_ACTION_DESC_VALUE,
    MODERATION_LOG_SORT_ACTOR_ASC_VALUE,
    MODERATION_LOG_SORT_ACTOR_DESC_VALUE,
    MODERATION_LOG_SORT_MOST_RECENT_VALUE,
    MODERATION_LOG_SORT_OLDEST_VALUE,
    MODERATION_LOG_SORT_TARGET_ASC_VALUE,
    MODERATION_LOG_SORT_TARGET_DESC_VALUE,
    MODERATION_LOG_TARGET_TYPE_ALL_VALUE,
    MODERATION_LOG_TARGET_TYPE_LISTING_VALUE,
    MODERATION_LOG_TARGET_TYPE_USER_VALUE,
)
from admin_ops.utils.listing_management import (
    ListingManagementActionError,
    ListingManagementPermissionError,
    perform_listing_management_action,
)
from admin_ops.utils.roles import ADMINISTRATOR_ROLE_NAME, MODERATOR_ROLE_NAME, is_user_administrator
from admin_ops.utils.user_management import (
    USER_EMAIL_SOURCE_FIELD_NAME,
    UserManagementActionError,
    UserManagementPermissionError,
    perform_user_management_action,
)
from listings.models import ListingImage
from moderation.models import ModerationAction
from reports.models import Report
from admin_ops.models import UserRoleAssignment


PAGE_SIZE: int = 20
BAN_USER_ACTION_TYPE_NAME: str = "BanUser"
FREEZE_LISTING_ACTION_TYPE_NAME: str = "FreezeListing"
PLACEHOLDER_REPORT_URL: str = "#"
TARGET_TYPE_USER_LABEL: str = "User"
TARGET_TYPE_LISTING_LABEL: str = "Listing"
_TARGET_NAME_MAX_LENGTH: int = 48
_SELECTED_LISTING_TITLE_MAX_LENGTH: int = 72


@dataclass(frozen=True)
class ModerationLogRow:
    action_id: int
    actor_display_name: str
    actor_role_name: str | None
    actor_profile_url: str
    action_type_name: str
    action_label: str
    target_display_name: str
    target_type_label: str
    recorded_at: Any
    select_url: str
    selected_card_url: str
    is_selected: bool


@dataclass(frozen=True)
class SelectedModerationReport:
    action_id: int
    report_id: int | None
    action_label: str
    target_type_label: str
    recorded_at: Any
    reporter_email_address: str | None
    actor_first_name: str
    actor_last_name: str
    actor_email_address: str
    actor_role_name: str | None
    actor_avatar_url: str | None
    actor_profile_url: str
    notes: str | None
    target_listing_id: int | None
    target_user_id: int | None
    listing_detail_url: str | None
    target_profile_url: str | None
    target_title: str | None
    target_owner_email_address: str | None
    target_listing_primary_image_url: str | None
    target_listing_view_count: int | None
    target_user_first_name: str | None
    target_user_last_name: str | None
    target_user_email_address: str | None
    target_user_avatar_url: str | None
    target_user_role_name: str | None
    target_user_status_label: str | None
    can_freeze_listing: bool
    can_unfreeze_listing: bool
    can_ban_user: bool
    can_unban_user: bool
    report_placeholder_url: str


@dataclass(frozen=True)
class ModerationLogPageContext:
    page_obj: Page[Any]
    table_rows: list[ModerationLogRow]
    selected_report: SelectedModerationReport | None
    total_action_count: int
    filter_summary_parts: list[str]
    preserved_query_string_without_page: str
    preserved_query_string_without_selected: str
    preserved_query_items: list[tuple[str, str]]
    selected_action_id: int | None
    page_range: list[int | str]


@dataclass(frozen=True)
class SelectedModerationReportCardContext:
    selected_report: SelectedModerationReport | None
    preserved_query_items: list[tuple[str, str]]
    page_number: int


class ModerationLogActionError(Exception):
    """Raised when a moderation-log action cannot be completed."""


class ModerationLogPermissionError(Exception):
    """Raised when a moderation-log action is not permitted."""


class UnsupportedModerationLogActionError(Exception):
    """Raised when an unknown moderation-log action is submitted."""


def build_moderation_log_page_context(
    *,
    search_email: str,
    moderation_action_type: str,
    report_target_type: str,
    sort_by: str,
    page_number: int,
    selected_action_id: int | None,
    base_url: str,
    acting_user_id: int,
) -> ModerationLogPageContext:
    normalized_email: str = search_email.strip()
    queryset: QuerySet[ModerationAction] = _build_moderation_log_queryset(
        search_email=normalized_email,
        moderation_action_type=moderation_action_type,
        report_target_type=report_target_type,
    )
    queryset = _apply_sort(queryset=queryset, sort_by=sort_by)

    paginator: Paginator = Paginator(queryset, PAGE_SIZE)
    page_obj: Page[Any] = paginator.get_page(page_number)

    preserved_query_items_without_page: list[tuple[str, str]] = _build_preserved_query_items(
        search_email=normalized_email,
        moderation_action_type=moderation_action_type,
        report_target_type=report_target_type,
        sort_by=sort_by,
        selected_action_id=selected_action_id,
        exclude_keys={"page"},
    )
    preserved_query_items_without_selected: list[tuple[str, str]] = _build_preserved_query_items(
        search_email=normalized_email,
        moderation_action_type=moderation_action_type,
        report_target_type=report_target_type,
        sort_by=sort_by,
        selected_action_id=selected_action_id,
        exclude_keys={"selected"},
    )

    selected_report: SelectedModerationReport | None = _resolve_selected_report(
        queryset=queryset,
        page_obj=page_obj,
        selected_action_id=selected_action_id,
        acting_user_id=acting_user_id,
    )
    resolved_selected_action_id: int | None = selected_report.action_id if selected_report is not None else None

    table_rows: list[ModerationLogRow] = []
    for moderation_action in page_obj.object_list:
        current_action_id: int = int(moderation_action.action_id)
        target_type_label: str = _get_target_type_label(moderation_action)
        table_rows.append(
            ModerationLogRow(
                action_id=current_action_id,
                actor_display_name=_build_last_first_display_name(moderation_action.actor_user),
                actor_role_name=_normalize_role_name(getattr(moderation_action, "actor_role_name", None)),
                actor_profile_url=reverse("view_profile", kwargs={"id": int(moderation_action.actor_user_id)}),
                action_type_name=str(getattr(moderation_action.action_type, "action_type_name", "")).strip(),
                action_label=_get_action_label(moderation_action),
                target_display_name=_build_target_display_name(moderation_action),
                target_type_label=target_type_label,
                recorded_at=moderation_action.created_at,
                select_url=_build_selection_url(
                    base_url=base_url,
                    search_email=normalized_email,
                    moderation_action_type=moderation_action_type,
                    report_target_type=report_target_type,
                    sort_by=sort_by,
                    selected_action_id=current_action_id,
                    page_number=page_obj.number,
                ),
                selected_card_url=_build_selected_card_url(
                    action_id=current_action_id,
                    search_email=normalized_email,
                    moderation_action_type=moderation_action_type,
                    report_target_type=report_target_type,
                    sort_by=sort_by,
                    page_number=page_obj.number,
                ),
                is_selected=current_action_id == resolved_selected_action_id,
            )
        )

    filter_summary_parts: list[str] = _build_filter_summary_parts(
        search_email=normalized_email,
        moderation_action_type=moderation_action_type,
        report_target_type=report_target_type,
        total_action_count=paginator.count,
    )
    page_range: list[int | str] = list(paginator.get_elided_page_range(number=page_obj.number, on_each_side=1, on_ends=1))

    return ModerationLogPageContext(
        page_obj=page_obj,
        table_rows=table_rows,
        selected_report=selected_report,
        total_action_count=paginator.count,
        filter_summary_parts=filter_summary_parts,
        preserved_query_string_without_page=urlencode(preserved_query_items_without_page, doseq=True),
        preserved_query_string_without_selected=urlencode(preserved_query_items_without_selected, doseq=True),
        preserved_query_items=preserved_query_items_without_selected,
        selected_action_id=resolved_selected_action_id,
        page_range=page_range,
    )


def build_selected_moderation_report_card_context(
    *,
    action_id: int,
    search_email: str,
    moderation_action_type: str,
    report_target_type: str,
    sort_by: str,
    page_number: int,
    acting_user_id: int,
) -> SelectedModerationReportCardContext:
    normalized_email: str = search_email.strip()
    queryset: QuerySet[ModerationAction] = _build_moderation_log_queryset(
        search_email=normalized_email,
        moderation_action_type=moderation_action_type,
        report_target_type=report_target_type,
    )
    queryset = _apply_sort(queryset=queryset, sort_by=sort_by)

    selected_report: SelectedModerationReport | None = _resolve_selected_report_object(
        queryset=queryset,
        selected_action_id=action_id,
        acting_user_id=acting_user_id,
    )

    preserved_query_items: list[tuple[str, str]] = _build_preserved_query_items(
        search_email=normalized_email,
        moderation_action_type=moderation_action_type,
        report_target_type=report_target_type,
        sort_by=sort_by,
        selected_action_id=action_id,
        exclude_keys={"selected"},
    )

    return SelectedModerationReportCardContext(
        selected_report=selected_report,
        preserved_query_items=preserved_query_items,
        page_number=page_number,
    )


def perform_moderation_log_action(
    *,
    requesting_user_id: int,
    moderation_action_id: int,
    action_name: str,
) -> str:
    moderation_action: ModerationAction = (
        ModerationAction.objects.select_related("listing", "target_user")
        .get(action_id=moderation_action_id)
    )

    try:
        if action_name == "freeze_listing":
            if moderation_action.listing_id is None:
                raise ModerationLogActionError("This moderation record does not target a listing.")
            return perform_listing_management_action(
                requesting_user_id=requesting_user_id,
                target_listing_id=int(moderation_action.listing_id),
                action_name="freeze_listing",
            )

        if action_name == "unfreeze_listing":
            if moderation_action.listing_id is None:
                raise ModerationLogActionError("This moderation record does not target a listing.")
            return perform_listing_management_action(
                requesting_user_id=requesting_user_id,
                target_listing_id=int(moderation_action.listing_id),
                action_name="unfreeze_listing",
            )

        if action_name == "ban_user":
            if moderation_action.target_user_id is None:
                raise ModerationLogActionError("This moderation record does not target a user.")
            return perform_user_management_action(
                requesting_user_id=requesting_user_id,
                target_user_id=int(moderation_action.target_user_id),
                action_name="ban_user",
            )

        if action_name == "unban_user":
            if moderation_action.target_user_id is None:
                raise ModerationLogActionError("This moderation record does not target a user.")
            return perform_user_management_action(
                requesting_user_id=requesting_user_id,
                target_user_id=int(moderation_action.target_user_id),
                action_name="unban_user",
            )
    except ListingManagementPermissionError as exc:
        raise ModerationLogPermissionError(str(exc)) from exc
    except UserManagementPermissionError as exc:
        raise ModerationLogPermissionError(str(exc)) from exc
    except ListingManagementActionError as exc:
        raise ModerationLogActionError(str(exc)) from exc
    except UserManagementActionError as exc:
        raise ModerationLogActionError(str(exc)) from exc

    raise UnsupportedModerationLogActionError("Unsupported moderation-log action.")


def _build_moderation_log_queryset(
    *,
    search_email: str,
    moderation_action_type: str,
    report_target_type: str,
) -> QuerySet[ModerationAction]:
    actor_role_name_subquery: Subquery = Subquery(
        UserRoleAssignment.objects.filter(user_id=OuterRef("actor_user_id"))
        .select_related("role")
        .values("role__role_name")[:1],
        output_field=CharField(),
    )
    report_id_subquery: Subquery = Subquery(
        Report.objects.filter(action_id=OuterRef("pk")).values("report_id")[:1]
    )
    reporter_email_subquery: Subquery = Subquery(
        Report.objects.filter(action_id=OuterRef("pk")).values("reporter_user__username")[:1],
        output_field=CharField(),
    )

    queryset: QuerySet[ModerationAction] = (
        ModerationAction.objects.select_related(
            "actor_user",
            "action_type",
            "listing",
            "listing__seller_user",
            "listing__status",
            "target_user",
        )
        .annotate(actor_role_name=actor_role_name_subquery)
        .annotate(report_id_value=report_id_subquery)
        .annotate(reporter_email=reporter_email_subquery)
        .annotate(actor_name_sort=Lower(
            Concat(
                Coalesce("actor_user__last_name", Value("")),
                Value(" "),
                Coalesce("actor_user__first_name", Value("")),
            )
        ))
        .annotate(action_name_sort=Lower(Coalesce("action_type__action_type_name", Value(""))))
        .annotate(
            target_name_sort=Lower(
                Case(
                    When(
                        listing__isnull=False,
                        then=Coalesce("listing__title", Value("")),
                    ),
                    default=Concat(
                        Coalesce("target_user__last_name", Value("")),
                        Value(" "),
                        Coalesce("target_user__first_name", Value("")),
                    ),
                    output_field=CharField(),
                )
            )
        )
        .annotate(
            target_type_sort=Case(
                When(listing__isnull=False, then=Value(0)),
                default=Value(1),
                output_field=IntegerField(),
            )
        )
    )

    queryset = queryset.filter(
        action_type__action_type_name__in=[BAN_USER_ACTION_TYPE_NAME, FREEZE_LISTING_ACTION_TYPE_NAME],
    )

    if search_email != "":
        queryset = queryset.filter(
            Q(actor_user__username__icontains=search_email)
            | Q(reporter_email__icontains=search_email)
            | Q(target_user__username__icontains=search_email)
            | Q(listing__seller_user__username__icontains=search_email)
        )

    if moderation_action_type == MODERATION_LOG_ACTION_TYPE_BAN_USER_VALUE:
        queryset = queryset.filter(action_type__action_type_name__iexact=BAN_USER_ACTION_TYPE_NAME)
    elif moderation_action_type == MODERATION_LOG_ACTION_TYPE_FREEZE_LISTING_VALUE:
        queryset = queryset.filter(action_type__action_type_name__iexact=FREEZE_LISTING_ACTION_TYPE_NAME)

    if report_target_type == MODERATION_LOG_TARGET_TYPE_USER_VALUE:
        queryset = queryset.filter(target_user__isnull=False)
    elif report_target_type == MODERATION_LOG_TARGET_TYPE_LISTING_VALUE:
        queryset = queryset.filter(listing__isnull=False)

    return queryset


def _apply_sort(*, queryset: QuerySet[ModerationAction], sort_by: str) -> QuerySet[ModerationAction]:
    if sort_by == MODERATION_LOG_SORT_OLDEST_VALUE:
        return queryset.order_by("created_at", "action_id")
    if sort_by == MODERATION_LOG_SORT_ACTOR_ASC_VALUE:
        return queryset.order_by("actor_name_sort", "-created_at", "-action_id")
    if sort_by == MODERATION_LOG_SORT_ACTOR_DESC_VALUE:
        return queryset.order_by("-actor_name_sort", "-created_at", "-action_id")
    if sort_by == MODERATION_LOG_SORT_ACTION_ASC_VALUE:
        return queryset.order_by("action_name_sort", "-created_at", "-action_id")
    if sort_by == MODERATION_LOG_SORT_ACTION_DESC_VALUE:
        return queryset.order_by("-action_name_sort", "-created_at", "-action_id")
    if sort_by == MODERATION_LOG_SORT_TARGET_ASC_VALUE:
        return queryset.order_by("target_type_sort", "target_name_sort", "-created_at", "-action_id")
    if sort_by == MODERATION_LOG_SORT_TARGET_DESC_VALUE:
        return queryset.order_by("target_type_sort", "-target_name_sort", "-created_at", "-action_id")

    return queryset.order_by("-created_at", "-action_id")


def _resolve_selected_report(
    *,
    queryset: QuerySet[ModerationAction],
    page_obj: Page[Any],
    selected_action_id: int | None,
    acting_user_id: int,
) -> SelectedModerationReport | None:
    selected_action: ModerationAction | None = None

    if selected_action_id is not None:
        selected_action = queryset.filter(action_id=selected_action_id).first()

    if selected_action is None:
        selected_action = page_obj.object_list[0] if page_obj.object_list else None

    return _build_selected_report(moderation_action=selected_action, acting_user_id=acting_user_id)


def _resolve_selected_report_object(
    *,
    queryset: QuerySet[ModerationAction],
    selected_action_id: int,
    acting_user_id: int,
) -> SelectedModerationReport | None:
    moderation_action: ModerationAction | None = queryset.filter(action_id=selected_action_id).first()
    return _build_selected_report(moderation_action=moderation_action, acting_user_id=acting_user_id)


def _build_selected_report(
    *,
    moderation_action: ModerationAction | None,
    acting_user_id: int,
) -> SelectedModerationReport | None:
    if moderation_action is None:
        return None

    report: Report | None = (
        Report.objects.select_related("reporter_user")
        .filter(action_id=moderation_action.action_id)
        .first()
    )

    actor_profile: UserProfile | None = _get_profiles_for_user_ids([int(moderation_action.actor_user_id)]).get(int(moderation_action.actor_user_id))
    actor_avatar_url: str | None = _resolve_avatar_url(actor_profile)
    actor_role_name: str | None = _normalize_role_name(getattr(moderation_action, "actor_role_name", None))

    target_listing_primary_image_url: str | None = None
    target_title: str | None = None
    target_owner_email_address: str | None = None
    target_listing_view_count: int | None = None
    listing_detail_url: str | None = None
    target_profile_url: str | None = None
    target_user_first_name: str | None = None
    target_user_last_name: str | None = None
    target_user_email_address: str | None = None
    target_user_avatar_url: str | None = None
    target_user_role_name: str | None = None
    target_user_status_label: str | None = None
    can_freeze_listing: bool = False
    can_unfreeze_listing: bool = False
    can_ban_user: bool = False
    can_unban_user: bool = False

    if moderation_action.listing is not None:
        image_by_listing_id: dict[int, ListingImage] = _get_first_images_by_listing_id([int(moderation_action.listing_id)])
        listing_image: ListingImage | None = image_by_listing_id.get(int(moderation_action.listing_id))
        if listing_image is not None:
            target_listing_primary_image_url = f"/{str(listing_image.image_url).lstrip('/')}"

        target_title = _truncate_text(str(moderation_action.listing.title), _SELECTED_LISTING_TITLE_MAX_LENGTH)
        target_owner_email_address = str(getattr(moderation_action.listing.seller_user, USER_EMAIL_SOURCE_FIELD_NAME, ""))
        target_listing_view_count = int(moderation_action.listing.view_count)
        listing_detail_url = reverse("listing_detail", kwargs={"listing_id": int(moderation_action.listing_id)})

        listing_status_name: str = str(getattr(moderation_action.listing.status, "status_name", "")).strip()
        can_freeze_listing = listing_status_name.lower() != "frozen"
        can_unfreeze_listing = listing_status_name.lower() == "frozen"

    if moderation_action.target_user is not None:
        target_user: Any = moderation_action.target_user
        target_profile: UserProfile | None = _get_profiles_for_user_ids([int(moderation_action.target_user_id)]).get(int(moderation_action.target_user_id))
        target_user_avatar_url = _resolve_avatar_url(target_profile)
        target_user_first_name = _get_display_first_name(target_user)
        target_user_last_name = _get_display_last_name(target_user)
        target_user_email_address = str(getattr(target_user, USER_EMAIL_SOURCE_FIELD_NAME, ""))
        target_user_status_label = "Active" if bool(target_user.is_active) else "Banned"
        target_profile_url = reverse("view_profile", kwargs={"id": int(moderation_action.target_user_id)})

        target_user_role_name = _get_user_current_role_name(int(moderation_action.target_user_id))
        is_self_target: bool = int(moderation_action.target_user_id) == int(acting_user_id)
        is_target_administrator: bool = (target_user_role_name or "").lower() == ADMINISTRATOR_ROLE_NAME.lower()
        can_ban_user = not is_self_target and not is_target_administrator and bool(target_user.is_active)
        can_unban_user = not is_self_target and not is_target_administrator and not bool(target_user.is_active)

    return SelectedModerationReport(
        action_id=int(moderation_action.action_id),
        report_id=int(report.report_id) if report is not None else None,
        action_label=_get_action_label(moderation_action),
        target_type_label=_get_target_type_label(moderation_action),
        recorded_at=moderation_action.created_at,
        reporter_email_address=(
            str(getattr(report.reporter_user, USER_EMAIL_SOURCE_FIELD_NAME, ""))
            if report is not None else None
        ),
        actor_first_name=_get_display_first_name(moderation_action.actor_user),
        actor_last_name=_get_display_last_name(moderation_action.actor_user),
        actor_email_address=str(getattr(moderation_action.actor_user, USER_EMAIL_SOURCE_FIELD_NAME, "")),
        actor_role_name=actor_role_name,
        actor_avatar_url=actor_avatar_url,
        actor_profile_url=reverse("view_profile", kwargs={"id": int(moderation_action.actor_user_id)}),
        notes=_normalize_optional_text(moderation_action.notes),
        target_listing_id=int(moderation_action.listing_id) if moderation_action.listing_id is not None else None,
        target_user_id=int(moderation_action.target_user_id) if moderation_action.target_user_id is not None else None,
        listing_detail_url=listing_detail_url,
        target_profile_url=target_profile_url,
        target_title=target_title,
        target_owner_email_address=target_owner_email_address,
        target_listing_primary_image_url=target_listing_primary_image_url,
        target_listing_view_count=target_listing_view_count,
        target_user_first_name=target_user_first_name,
        target_user_last_name=target_user_last_name,
        target_user_email_address=target_user_email_address,
        target_user_avatar_url=target_user_avatar_url,
        target_user_role_name=target_user_role_name,
        target_user_status_label=target_user_status_label,
        can_freeze_listing=can_freeze_listing,
        can_unfreeze_listing=can_unfreeze_listing,
        can_ban_user=can_ban_user,
        can_unban_user=can_unban_user,
        report_placeholder_url=PLACEHOLDER_REPORT_URL,
    )


def _build_selection_url(
    *,
    base_url: str,
    search_email: str,
    moderation_action_type: str,
    report_target_type: str,
    sort_by: str,
    selected_action_id: int,
    page_number: int,
) -> str:
    query_items: list[tuple[str, str]] = _build_preserved_query_items(
        search_email=search_email,
        moderation_action_type=moderation_action_type,
        report_target_type=report_target_type,
        sort_by=sort_by,
        selected_action_id=selected_action_id,
        exclude_keys=set(),
    )
    query_items.append(("page", str(page_number)))
    return f"{base_url}?{urlencode(query_items, doseq=True)}"


def _build_selected_card_url(
    *,
    action_id: int,
    search_email: str,
    moderation_action_type: str,
    report_target_type: str,
    sort_by: str,
    page_number: int,
) -> str:
    query_items: list[tuple[str, str]] = _build_preserved_query_items(
        search_email=search_email,
        moderation_action_type=moderation_action_type,
        report_target_type=report_target_type,
        sort_by=sort_by,
        selected_action_id=action_id,
        exclude_keys={"selected"},
    )
    query_items.append(("page", str(page_number)))
    return f"{reverse('moderation_log_selected_card', kwargs={'action_id': action_id})}?{urlencode(query_items, doseq=True)}"


def _build_preserved_query_items(
    *,
    search_email: str,
    moderation_action_type: str,
    report_target_type: str,
    sort_by: str,
    selected_action_id: int | None,
    exclude_keys: set[str],
) -> list[tuple[str, str]]:
    query_items: list[tuple[str, str]] = []
    if "search_email" not in exclude_keys and search_email != "":
        query_items.append(("search_email", search_email))
    if "moderation_action_type" not in exclude_keys and moderation_action_type != "":
        query_items.append(("moderation_action_type", moderation_action_type))
    if "report_target_type" not in exclude_keys and report_target_type != "":
        query_items.append(("report_target_type", report_target_type))
    if "sort_by" not in exclude_keys and sort_by != "":
        query_items.append(("sort_by", sort_by))
    if "selected" not in exclude_keys and selected_action_id is not None:
        query_items.append(("selected", str(selected_action_id)))
    return query_items


def _build_filter_summary_parts(
    *,
    search_email: str,
    moderation_action_type: str,
    report_target_type: str,
    total_action_count: int,
) -> list[str]:
    summary_parts: list[str] = [f"{total_action_count} action{'s' if total_action_count != 1 else ''}"]

    if search_email != "":
        summary_parts.append(f"email contains “{search_email}”")
    if moderation_action_type == MODERATION_LOG_ACTION_TYPE_BAN_USER_VALUE:
        summary_parts.append("action: Ban User")
    elif moderation_action_type == MODERATION_LOG_ACTION_TYPE_FREEZE_LISTING_VALUE:
        summary_parts.append("action: Freeze Listing")

    if report_target_type == MODERATION_LOG_TARGET_TYPE_USER_VALUE:
        summary_parts.append("target: User")
    elif report_target_type == MODERATION_LOG_TARGET_TYPE_LISTING_VALUE:
        summary_parts.append("target: Listing")

    return summary_parts


def _get_profiles_for_user_ids(user_ids: Iterable[int]) -> dict[int, UserProfile]:
    normalized_user_ids: list[int] = [int(user_id) for user_id in user_ids]
    if not normalized_user_ids:
        return {}

    profiles: list[UserProfile] = list(
        UserProfile.objects.select_related("city", "city__state")
        .filter(user_id__in=normalized_user_ids)
    )
    return {int(profile.user_id): profile for profile in profiles}


def _get_first_images_by_listing_id(listing_ids: Iterable[int]) -> dict[int, ListingImage]:
    normalized_listing_ids: list[int] = [int(listing_id) for listing_id in listing_ids]
    if not normalized_listing_ids:
        return {}

    images: list[ListingImage] = list(
        ListingImage.objects.filter(listing_id__in=normalized_listing_ids)
        .order_by("listing_id", "display_order", "image_id")
    )
    first_images_by_listing_id: dict[int, ListingImage] = {}
    for image in images:
        listing_id: int = int(image.listing_id)
        if listing_id not in first_images_by_listing_id:
            first_images_by_listing_id[listing_id] = image
    return first_images_by_listing_id


def _resolve_avatar_url(profile: UserProfile | None) -> str | None:
    if profile is None:
        return None

    try:
        if profile.avatar:
            return str(profile.avatar.url)
    except ValueError:
        return None

    return None


def _get_user_current_role_name(user_id: int) -> str | None:
    assignment = (
        UserRoleAssignment.objects.select_related("role")
        .filter(user_id=user_id)
        .first()
    )
    if assignment is None:
        return None

    return _normalize_role_name(assignment.role.role_name)


def _get_action_label(moderation_action: ModerationAction) -> str:
    action_type_name: str = str(getattr(moderation_action.action_type, "action_type_name", "")).strip()
    if action_type_name.lower() == BAN_USER_ACTION_TYPE_NAME.lower():
        return "Ban User"
    if action_type_name.lower() == FREEZE_LISTING_ACTION_TYPE_NAME.lower():
        return "Freeze Listing"
    return action_type_name if action_type_name != "" else "—"


def _get_target_type_label(moderation_action: ModerationAction) -> str:
    return TARGET_TYPE_LISTING_LABEL if moderation_action.listing_id is not None else TARGET_TYPE_USER_LABEL


def _build_target_display_name(moderation_action: ModerationAction) -> str:
    if moderation_action.listing is not None:
        return _truncate_text(str(moderation_action.listing.title), _TARGET_NAME_MAX_LENGTH)

    if moderation_action.target_user is not None:
        return _truncate_text(_build_first_last_display_name(moderation_action.target_user), _TARGET_NAME_MAX_LENGTH)

    return "Unknown target"


def _build_first_last_display_name(user: Any) -> str:
    first_name: str = str(getattr(user, "first_name", "") or "").strip()
    last_name: str = str(getattr(user, "last_name", "") or "").strip()
    combined_name: str = " ".join(part for part in (first_name, last_name) if part != "").strip()
    return combined_name if combined_name != "" else str(getattr(user, USER_EMAIL_SOURCE_FIELD_NAME, "—"))


def _build_last_first_display_name(user: Any) -> str:
    first_name: str = str(getattr(user, "first_name", "") or "").strip()
    last_name: str = str(getattr(user, "last_name", "") or "").strip()
    if first_name != "" and last_name != "":
        return f"{last_name}, {first_name}"
    if last_name != "":
        return last_name
    if first_name != "":
        return first_name
    return str(getattr(user, USER_EMAIL_SOURCE_FIELD_NAME, "—"))


def _get_display_first_name(user: Any) -> str:
    first_name: str = str(getattr(user, "first_name", "") or "").strip()
    return first_name if first_name != "" else "—"


def _get_display_last_name(user: Any) -> str:
    last_name: str = str(getattr(user, "last_name", "") or "").strip()
    return last_name if last_name != "" else "—"


def _normalize_role_name(role_name: Any) -> str | None:
    if role_name is None:
        return None
    normalized_role_name: str = str(role_name).strip()
    return normalized_role_name if normalized_role_name != "" else None


def _normalize_optional_text(value: Any) -> str | None:
    normalized_value: str = str(value or "").strip()
    return normalized_value if normalized_value != "" else None


def _truncate_text(value: str, max_length: int) -> str:
    normalized_value: str = value.strip()
    if len(normalized_value) <= max_length:
        return normalized_value
    return f"{normalized_value[: max_length - 3].rstrip()}..."
