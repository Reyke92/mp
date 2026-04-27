from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.shortcuts import get_object_or_404
from django.urls import reverse
from django.utils import timezone

from admin_ops.utils.roles import ADMINISTRATOR_ROLE_NAME, MODERATOR_ROLE_NAME, is_user_administrator
from listings.models import ListingStatus
from moderation.models import ModerationAction, ModerationActionType
from reports.models import Report, ReportStatus


UserModel = get_user_model()
RELATED_REPORT_WINDOW_DAYS: int = 30
RECEIVED_STATUS_NAME: str = "Received"
ACTION_TAKEN_STATUS_NAME: str = "ActionTaken"
DISMISSED_STATUS_NAME: str = "Dismissed"
FREEZE_LISTING_ACTION_NAME: str = "FreezeListing"
BAN_USER_ACTION_NAME: str = "BanUser"
FROZEN_LISTING_STATUS_NAME: str = "Frozen"


@dataclass(frozen=True)
class RelatedRecentReportRow:
    report_id: int
    reporter_email_address: str
    status_label: str
    status_variant: str
    created_at: Any
    details_preview: str
    is_current_report: bool
    detail_url: str


@dataclass(frozen=True)
class ReportDetailPageContent:
    report: Report
    report_type_label: str
    reporter_email: str
    reported_user_display_name: str
    reported_user_email: str
    reported_user_profile_url: str | None
    status_label: str
    status_variant: str
    target_display_name: str
    target_subtext: str
    view_target_url: str | None
    view_target_label: str
    view_target_disabled_reason: str | None
    view_reporter_url: str
    back_to_queue_url: str
    allowed_action_names: list[str]
    related_recent_reports: list[RelatedRecentReportRow]
    action_notes: str | None
    action_label: str | None
    readonly_mode: bool
    affected_open_related_report_count: int


def build_report_detail_page_content(report_id: int, *, readonly_mode: bool = False) -> ReportDetailPageContent:
    report = get_object_or_404(
        Report.objects.select_related(
            "reporter_user",
            "status",
            "action",
            "action__action_type",
            "listing",
            "listing__seller_user",
            "conversation",
            "conversation__user_a",
            "conversation__user_b",
        ),
        report_id=report_id,
    )

    is_listing_report = report.listing_id is not None
    reported_user = resolve_reported_user(report=report)
    related_recent_reports = _build_related_recent_reports(report)
    affected_count = len([item for item in related_recent_reports if item.status_label == RECEIVED_STATUS_NAME])

    target_display_name, target_subtext = _build_target_display(report=report, reported_user=reported_user)
    view_target_url, view_target_label, view_target_disabled_reason = _resolve_view_target(
        report=report,
        reported_user=reported_user,
    )

    return ReportDetailPageContent(
        report=report,
        report_type_label="Listing" if is_listing_report else "Conversation",
        reporter_email=str(report.reporter_user.username),
        reported_user_display_name=_build_person_display_name(reported_user),
        reported_user_email=str(reported_user.username),
        reported_user_profile_url=reverse("view_profile", kwargs={"id": int(reported_user.id)}),
        status_label=str(report.status.status_name),
        status_variant=_status_variant_for(str(report.status.status_name)),
        target_display_name=target_display_name,
        target_subtext=target_subtext,
        view_target_url=view_target_url,
        view_target_label=view_target_label,
        view_target_disabled_reason=view_target_disabled_reason,
        view_reporter_url=reverse("view_profile", kwargs={"id": int(report.reporter_user_id)}),
        back_to_queue_url=reverse("moderation_queue"),
        allowed_action_names=[FREEZE_LISTING_ACTION_NAME] if is_listing_report else [BAN_USER_ACTION_NAME],
        related_recent_reports=related_recent_reports,
        action_notes=None if report.action is None or not report.action.notes else str(report.action.notes).strip(),
        action_label=None if report.action is None else str(report.action.action_type.action_type_name),
        readonly_mode=readonly_mode,
        affected_open_related_report_count=affected_count,
    )


def resolve_reported_user(*, report: Report) -> Any:
    if report.listing_id is not None and report.listing is not None:
        return report.listing.seller_user

    conversation = report.conversation
    if int(conversation.user_a_id) == int(report.reporter_user_id):
        return conversation.user_b
    return conversation.user_a


def _build_target_display(*, report: Report, reported_user: Any) -> tuple[str, str]:
    if report.listing_id is not None and report.listing is not None:
        return (
            str(report.listing.title),
            f"Listing owned by {reported_user.username}.",
        )

    conversation = report.conversation
    return (
        f"Conversation #{int(conversation.conversation_id)}",
        f"Reported user: {reported_user.username}",
    )


def _resolve_view_target(*, report: Report, reported_user: Any) -> tuple[str | None, str, str | None]:
    if report.listing_id is not None:
        return (
            reverse("listing_detail", kwargs={"listing_id": int(report.listing_id)}),
            "View Listing",
            None,
        )

    if report.conversation_id is None:
        return None, "View Target", "No target is associated with this report."

    return (
        reverse(
            "limited_user_conversation",
            kwargs={
                "user_id": int(reported_user.id),
                "conversation_id": int(report.conversation_id),
            },
        ),
        "View Conversation",
        None,
    )


def _build_related_recent_reports(report: Report) -> list[RelatedRecentReportRow]:
    related_reports = find_related_reports_for_report(report=report, include_selected_always=True)
    rows: list[RelatedRecentReportRow] = []
    for related_report in related_reports:
        detail_url = reverse("report_details", kwargs={"report_id": int(related_report.report_id)})
        rows.append(
            RelatedRecentReportRow(
                report_id=int(related_report.report_id),
                reporter_email_address=str(related_report.reporter_user.username),
                status_label=str(related_report.status.status_name),
                status_variant=_status_variant_for(str(related_report.status.status_name)),
                created_at=related_report.created_at,
                details_preview=_truncate_text(str(related_report.details or "").strip() or "(no reason provided)", 120),
                is_current_report=int(related_report.report_id) == int(report.report_id),
                detail_url=detail_url,
            )
        )
    rows.sort(key=lambda item: (item.created_at, item.report_id))
    return rows


def find_related_reports_for_report(
    *,
    report: Report,
    include_selected_always: bool,
    received_only: bool = False,
) -> list[Report]:
    base_queryset = Report.objects.select_related(
        "reporter_user",
        "status",
        "listing",
        "listing__seller_user",
        "conversation",
        "conversation__user_a",
        "conversation__user_b",
    )
    window_start = timezone.now() - timedelta(days=RELATED_REPORT_WINDOW_DAYS)

    selected_report_id = int(report.report_id)
    related_reports: list[Report] = []

    if report.listing_id is not None:
        queryset = base_queryset.filter(listing_id=int(report.listing_id))
        if received_only:
            queryset = queryset.filter(status__status_name=RECEIVED_STATUS_NAME)
        queryset = queryset.filter(created_at__gte=window_start) | base_queryset.filter(report_id=selected_report_id)
        dedup: dict[int, Report] = {}
        for item in queryset.order_by("created_at", "report_id"):
            dedup[int(item.report_id)] = item
        related_reports = list(dedup.values())
    else:
        reported_user = resolve_reported_user(report=report)
        candidate_queryset = base_queryset.filter(
            conversation__isnull=False,
            created_at__gte=window_start,
        ) | base_queryset.filter(report_id=selected_report_id)
        if received_only:
            candidate_queryset = candidate_queryset.filter(status__status_name=RECEIVED_STATUS_NAME) | base_queryset.filter(report_id=selected_report_id)

        seen_ids: set[int] = set()
        for item in candidate_queryset.order_by("created_at", "report_id"):
            item_id = int(item.report_id)
            if item_id in seen_ids:
                continue
            if int(resolve_reported_user(report=item).id) != int(reported_user.id):
                continue
            seen_ids.add(item_id)
            related_reports.append(item)

    if include_selected_always and all(int(item.report_id) != selected_report_id for item in related_reports):
        related_reports.append(report)

    dedup_map: dict[int, Report] = {}
    for item in related_reports:
        dedup_map[int(item.report_id)] = item
    return list(sorted(dedup_map.values(), key=lambda current: (current.created_at, current.report_id)))


@transaction.atomic
def record_report_disposition(
    *,
    report_id: int,
    actor_user: Any,
    action_type_id: int | None,
    dismiss_report: bool,
    notes: str,
) -> int:
    report = get_object_or_404(
        Report.objects.select_related(
            "status",
            "listing",
            "listing__status",
            "listing__seller_user",
            "conversation",
            "conversation__user_a",
            "conversation__user_b",
        ),
        report_id=report_id,
    )

    if str(report.status.status_name) != RECEIVED_STATUS_NAME:
        raise PermissionDenied("Only open reports can receive a new disposition.")

    if dismiss_report:
        return _dismiss_related_reports(report=report)

    if action_type_id is None:
        raise PermissionDenied("Choose a moderation action before saving the disposition.")

    action_type = get_object_or_404(ModerationActionType, action_type_id=action_type_id)
    related_reports = find_related_reports_for_report(report=report, include_selected_always=True, received_only=True)
    if not related_reports:
        raise PermissionDenied("No open reports were available for this target.")

    if str(action_type.action_type_name) == FREEZE_LISTING_ACTION_NAME:
        moderation_action = _freeze_listing_for_reports(
            report=report,
            actor_user=actor_user,
            action_type=action_type,
            notes=notes,
        )
    elif str(action_type.action_type_name) == BAN_USER_ACTION_NAME:
        moderation_action = _ban_user_for_reports(
            report=report,
            actor_user=actor_user,
            action_type=action_type,
            notes=notes,
        )
    else:
        raise PermissionDenied("The selected moderation action is not supported for this report.")

    resolved_status = _get_or_create_report_status(ACTION_TAKEN_STATUS_NAME)
    Report.objects.filter(report_id__in=[int(item.report_id) for item in related_reports]).update(
        status=resolved_status,
        action=moderation_action,
    )
    return len(related_reports)


def _dismiss_related_reports(*, report: Report) -> int:
    related_reports = find_related_reports_for_report(report=report, include_selected_always=True, received_only=True)
    dismissed_status = _get_or_create_report_status(DISMISSED_STATUS_NAME)
    Report.objects.filter(report_id__in=[int(item.report_id) for item in related_reports]).update(
        status=dismissed_status,
        action=None,
    )
    return len(related_reports)


def _freeze_listing_for_reports(
    *,
    report: Report,
    actor_user: Any,
    action_type: ModerationActionType,
    notes: str,
) -> ModerationAction:
    if report.listing is None:
        raise PermissionDenied("Only listing reports can record a FreezeListing disposition.")

    listing = report.listing
    current_status_name = str(listing.status.status_name).strip().lower()
    if current_status_name == FROZEN_LISTING_STATUS_NAME.lower():
        raise PermissionDenied("This listing is already frozen.")

    frozen_status = get_object_or_404(ListingStatus, status_name=FROZEN_LISTING_STATUS_NAME)
    listing.status = frozen_status
    listing.save(update_fields=["status"])

    return ModerationAction.objects.create(
        actor_user=actor_user,
        action_type=action_type,
        listing=listing,
        notes=notes or None,
    )


def _ban_user_for_reports(
    *,
    report: Report,
    actor_user: Any,
    action_type: ModerationActionType,
    notes: str,
) -> ModerationAction:
    target_user = resolve_reported_user(report=report)
    target_role_name = _get_current_role_name(target_user)

    if int(target_user.id) == int(actor_user.id):
        raise PermissionDenied("You cannot ban your own account through moderation.")
    if (target_role_name or "").lower() == ADMINISTRATOR_ROLE_NAME.lower():
        raise PermissionDenied("Administrator accounts cannot be banned.")
    if not bool(target_user.is_active):
        raise PermissionDenied("This account is already banned.")

    target_user.is_active = False
    target_user.save(update_fields=["is_active"])

    return ModerationAction.objects.create(
        actor_user=actor_user,
        action_type=action_type,
        target_user=target_user,
        notes=notes or None,
    )


def _get_current_role_name(user: Any) -> str | None:
    try:
        role_assignment = user.userroleassignment_set.select_related("role").first()
    except Exception:
        role_assignment = None
    if role_assignment is None:
        return None
    return str(role_assignment.role.role_name)


def _get_or_create_report_status(status_name: str) -> ReportStatus:
    report_status, _ = ReportStatus.objects.get_or_create(status_name=status_name)
    return report_status


def _build_person_display_name(user: Any) -> str:
    first_name = str(getattr(user, "first_name", "")).strip()
    last_name = str(getattr(user, "last_name", "")).strip()
    full_name = f"{first_name} {last_name}".strip()
    return full_name or str(getattr(user, "username", "Unknown user"))


def _status_variant_for(status_name: str) -> str:
    if status_name == RECEIVED_STATUS_NAME:
        return "warning"
    if status_name == ACTION_TAKEN_STATUS_NAME:
        return "success"
    if status_name == DISMISSED_STATUS_NAME:
        return "secondary"
    return "secondary"


def _truncate_text(value: str, limit: int) -> str:
    if len(value) <= limit:
        return value
    return f"{value[: max(0, limit - 3)].rstrip()}..."
