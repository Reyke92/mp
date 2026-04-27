from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any
from urllib.parse import urlencode

from django.core.paginator import Page, Paginator
from django.db.models import Case, IntegerField, Q, QuerySet, Value, When
from django.urls import reverse
from django.utils import timezone

from moderation.forms import (
    QUEUE_SORT_MOST_RECENT_VALUE,
    QUEUE_STATUS_RECEIVED_VALUE,
    QUEUE_STATUS_RESOLVED_VALUE,
    QUEUE_TYPE_CONVERSATION_VALUE,
    QUEUE_TYPE_LISTING_VALUE,
)
from reports.models import Report


PAGE_SIZE: int = 20
RECENT_REPORT_WINDOW_DAYS: int = 30
NEEDS_ATTENTION_PANEL_LIMIT: int = 8

RECEIVED_STATUS_NAME: str = "Received"
ACTION_TAKEN_STATUS_NAME: str = "ActionTaken"
DISMISSED_STATUS_NAME: str = "Dismissed"


@dataclass(frozen=True)
class ModerationQueueSummaryCard:
    label: str
    value: str
    subtext: str


@dataclass(frozen=True)
class ModerationNeedsAttentionRow:
    target_key: str
    target_type_label: str
    target_display_name: str
    target_email_address: str | None
    open_report_count: int
    recent_report_count: int
    oldest_open_created_at: Any | None
    most_recent_created_at: Any
    review_url: str


@dataclass(frozen=True)
class ModerationQueueRow:
    report_id: int
    report_type_label: str
    target_display_name: str
    target_email_address: str | None
    reporter_email_address: str
    recent_target_report_count: int
    status_label: str
    status_variant: str
    created_at: Any
    age_label: str
    detail_url: str


@dataclass(frozen=True)
class ModerationQueuePageContent:
    page_obj: Page[Any]
    queue_summary_cards: list[ModerationQueueSummaryCard]
    needs_attention_rows: list[ModerationNeedsAttentionRow]
    table_rows: list[ModerationQueueRow]
    total_report_count: int
    preserved_query_string_without_page: str
    page_range: list[int | str] = field(default_factory=list)


@dataclass(frozen=True)
class _TargetGroupStats:
    target_key: str
    target_type_label: str
    target_display_name: str
    target_email_address: str | None
    review_report_id: int
    open_report_count: int
    recent_report_count: int
    oldest_open_created_at: Any | None
    most_recent_created_at: Any


def build_moderation_queue_page_content(
    *,
    search_email: str,
    report_status: str,
    report_type: str,
    sort_by: str,
    page_number: int,
) -> ModerationQueuePageContent:
    normalized_email: str = search_email.strip()

    base_queryset: QuerySet[Report] = _build_base_report_queryset()
    recent_queryset: QuerySet[Report] = _build_recent_grouping_queryset(
        search_email=normalized_email,
        report_type=report_type,
    )
    target_group_stats: dict[str, _TargetGroupStats] = _build_target_group_stats(recent_queryset)

    queue_queryset: QuerySet[Report] = _build_queue_queryset(
        base_queryset=base_queryset,
        search_email=normalized_email,
        report_status=report_status,
        report_type=report_type,
    )
    queue_queryset = _apply_queue_sort(queryset=queue_queryset, sort_by=sort_by)

    paginator = Paginator(queue_queryset, PAGE_SIZE)
    page_obj = paginator.get_page(page_number)

    summary_cards = _build_summary_cards(
        all_open_queryset=base_queryset.filter(status__status_name=RECEIVED_STATUS_NAME),
        target_group_stats=target_group_stats,
    )
    needs_attention_rows = _build_needs_attention_rows(target_group_stats)

    table_rows = [_build_row(report=report, target_group_stats=target_group_stats) for report in page_obj.object_list]
    page_range = list(
        paginator.get_elided_page_range(page_obj.number, on_each_side=1, on_ends=1)  # type: ignore[attr-defined]
    )

    return ModerationQueuePageContent(
        page_obj=page_obj,
        queue_summary_cards=summary_cards,
        needs_attention_rows=needs_attention_rows,
        table_rows=table_rows,
        total_report_count=paginator.count,
        preserved_query_string_without_page=_build_preserved_query_string(
            search_email=normalized_email,
            report_status=report_status,
            report_type=report_type,
            sort_by=sort_by,
        ),
        page_range=page_range,
    )


def _build_base_report_queryset() -> QuerySet[Report]:
    return Report.objects.select_related(
        "reporter_user",
        "status",
        "listing",
        "listing__seller_user",
        "conversation",
        "conversation__user_a",
        "conversation__user_b",
    )


def _build_recent_grouping_queryset(*, search_email: str, report_type: str) -> QuerySet[Report]:
    queryset = _build_base_report_queryset().filter(
        created_at__gte=timezone.now() - timedelta(days=RECENT_REPORT_WINDOW_DAYS),
    )
    queryset = _apply_email_filter(queryset=queryset, search_email=search_email)
    queryset = _apply_type_filter(queryset=queryset, report_type=report_type)
    return queryset.order_by("created_at", "report_id")


def _build_queue_queryset(
    *,
    base_queryset: QuerySet[Report],
    search_email: str,
    report_status: str,
    report_type: str,
) -> QuerySet[Report]:
    queryset = base_queryset
    queryset = _apply_email_filter(queryset=queryset, search_email=search_email)
    queryset = _apply_status_filter(queryset=queryset, report_status=report_status)
    queryset = _apply_type_filter(queryset=queryset, report_type=report_type)
    return queryset


def _apply_email_filter(*, queryset: QuerySet[Report], search_email: str) -> QuerySet[Report]:
    if not search_email:
        return queryset

    return queryset.filter(
        Q(reporter_user__username__icontains=search_email)
        | Q(listing__seller_user__username__icontains=search_email)
        | Q(conversation__user_a__username__icontains=search_email)
        | Q(conversation__user_b__username__icontains=search_email)
    )


def _apply_status_filter(*, queryset: QuerySet[Report], report_status: str) -> QuerySet[Report]:
    if report_status == QUEUE_STATUS_RECEIVED_VALUE:
        return queryset.filter(status__status_name=RECEIVED_STATUS_NAME)

    if report_status == QUEUE_STATUS_RESOLVED_VALUE:
        return queryset.filter(
            status__status_name__in=[ACTION_TAKEN_STATUS_NAME, DISMISSED_STATUS_NAME]
        )

    return queryset


def _apply_type_filter(*, queryset: QuerySet[Report], report_type: str) -> QuerySet[Report]:
    if report_type == QUEUE_TYPE_LISTING_VALUE:
        return queryset.filter(listing__isnull=False)
    if report_type == QUEUE_TYPE_CONVERSATION_VALUE:
        return queryset.filter(conversation__isnull=False)
    return queryset


def _apply_queue_sort(*, queryset: QuerySet[Report], sort_by: str) -> QuerySet[Report]:
    if sort_by == QUEUE_SORT_MOST_RECENT_VALUE:
        return queryset.order_by("-created_at", "-report_id")

    return queryset.annotate(
        open_sort_rank=Case(
            When(status__status_name=RECEIVED_STATUS_NAME, then=Value(0)),
            default=Value(1),
            output_field=IntegerField(),
        )
    ).order_by(
        "open_sort_rank",
        "created_at",
        "report_id",
    )


def _build_target_group_stats(recent_queryset: QuerySet[Report]) -> dict[str, _TargetGroupStats]:
    grouped: dict[str, dict[str, Any]] = {}

    for report in recent_queryset:
        target_key, target_type_label, target_display_name, target_email_address = _resolve_target_group_key(report)
        if target_key is None:
            continue

        bucket = grouped.setdefault(
            target_key,
            {
                "target_key": target_key,
                "target_type_label": target_type_label,
                "target_display_name": target_display_name,
                "target_email_address": target_email_address,
                "review_report_id": int(report.report_id),
                "open_report_count": 0,
                "recent_report_count": 0,
                "oldest_open_created_at": None,
                "most_recent_created_at": report.created_at,
            },
        )

        bucket["recent_report_count"] += 1
        if str(report.status.status_name) == RECEIVED_STATUS_NAME:
            bucket["open_report_count"] += 1
            current_oldest = bucket["oldest_open_created_at"]
            if current_oldest is None or report.created_at < current_oldest:
                bucket["oldest_open_created_at"] = report.created_at
                bucket["review_report_id"] = int(report.report_id)

        if report.created_at > bucket["most_recent_created_at"]:
            bucket["most_recent_created_at"] = report.created_at

    stats: dict[str, _TargetGroupStats] = {}
    for key, value in grouped.items():
        stats[key] = _TargetGroupStats(
            target_key=value["target_key"],
            target_type_label=value["target_type_label"],
            target_display_name=value["target_display_name"],
            target_email_address=value["target_email_address"],
            review_report_id=value["review_report_id"],
            open_report_count=value["open_report_count"],
            recent_report_count=value["recent_report_count"],
            oldest_open_created_at=value["oldest_open_created_at"],
            most_recent_created_at=value["most_recent_created_at"],
        )
    return stats


def _resolve_target_group_key(report: Report) -> tuple[str | None, str, str, str | None]:
    if report.listing_id is not None and report.listing is not None:
        listing = report.listing
        return (
            f"listing:{int(listing.listing_id)}",
            "Listing",
            _truncate_text(str(listing.title), 72),
            str(getattr(listing.seller_user, "username", "")) or None,
        )

    if report.conversation_id is None or report.conversation is None:
        return None, "Conversation", "Conversation", None

    reported_user = _resolve_reported_user_for_conversation_report(report)
    return (
        f"user:{int(reported_user.id)}",
        "Reported User",
        _build_person_display_name(reported_user),
        str(getattr(reported_user, "username", "")) or None,
    )


def _resolve_reported_user_for_conversation_report(report: Report) -> Any:
    conversation = report.conversation
    if int(conversation.user_a_id) == int(report.reporter_user_id):
        return conversation.user_b
    return conversation.user_a


def _build_summary_cards(
    *,
    all_open_queryset: QuerySet[Report],
    target_group_stats: dict[str, _TargetGroupStats],
) -> list[ModerationQueueSummaryCard]:
    open_listing_reports: int = all_open_queryset.filter(listing__isnull=False).count()
    open_conversation_reports: int = all_open_queryset.filter(conversation__isnull=False).count()
    oldest_open_report = all_open_queryset.order_by("created_at", "report_id").first()
    escalated_target_count: int = sum(
        1
        for stat in target_group_stats.values()
        if stat.open_report_count > 0 and stat.recent_report_count >= 2
    )

    oldest_open_value: str = "—"
    oldest_open_subtext: str = "No open reports currently in queue."
    if oldest_open_report is not None:
        oldest_open_value = _humanize_age(oldest_open_report.created_at)
        oldest_open_subtext = f"Oldest open report filed {_format_short_datetime(oldest_open_report.created_at)}."

    return [
        ModerationQueueSummaryCard(
            label="Open Listing Reports",
            value=str(open_listing_reports),
            subtext="Listing reports still waiting on a disposition.",
        ),
        ModerationQueueSummaryCard(
            label="Open Conversation Reports",
            value=str(open_conversation_reports),
            subtext="Conversation reports still waiting on a disposition.",
        ),
        ModerationQueueSummaryCard(
            label="Oldest Open Age",
            value=oldest_open_value,
            subtext=oldest_open_subtext,
        ),
        ModerationQueueSummaryCard(
            label="Escalated Targets",
            value=str(escalated_target_count),
            subtext="Targets with multiple reports in the last 30 days and at least one open report.",
        ),
    ]


def _build_needs_attention_rows(target_group_stats: dict[str, _TargetGroupStats]) -> list[ModerationNeedsAttentionRow]:
    relevant_stats = [stat for stat in target_group_stats.values() if stat.open_report_count > 0]
    relevant_stats.sort(
        key=lambda stat: (
            -stat.recent_report_count,
            stat.oldest_open_created_at or stat.most_recent_created_at,
            stat.target_display_name.lower(),
        )
    )

    rows: list[ModerationNeedsAttentionRow] = []
    for stat in relevant_stats[:NEEDS_ATTENTION_PANEL_LIMIT]:
        rows.append(
            ModerationNeedsAttentionRow(
                target_key=stat.target_key,
                target_type_label=stat.target_type_label,
                target_display_name=stat.target_display_name,
                target_email_address=stat.target_email_address,
                open_report_count=stat.open_report_count,
                recent_report_count=stat.recent_report_count,
                oldest_open_created_at=stat.oldest_open_created_at,
                most_recent_created_at=stat.most_recent_created_at,
                review_url=reverse("report_details", kwargs={"report_id": stat.review_report_id}),
            )
        )
    return rows


def _build_row(*, report: Report, target_group_stats: dict[str, _TargetGroupStats]) -> ModerationQueueRow:
    target_key, target_type_label, target_display_name, target_email_address = _resolve_target_group_key(report)
    group_stats = None if target_key is None else target_group_stats.get(target_key)

    status_name = str(report.status.status_name)
    return ModerationQueueRow(
        report_id=int(report.report_id),
        report_type_label="Listing" if report.listing_id is not None else "Conversation",
        target_display_name=target_display_name,
        target_email_address=target_email_address,
        reporter_email_address=str(report.reporter_user.username),
        recent_target_report_count=0 if group_stats is None else group_stats.recent_report_count,
        status_label=status_name,
        status_variant=_status_variant_for(status_name),
        created_at=report.created_at,
        age_label=_humanize_age(report.created_at),
        detail_url=reverse("report_details", kwargs={"report_id": int(report.report_id)}),
    )


def _status_variant_for(status_name: str) -> str:
    if status_name == RECEIVED_STATUS_NAME:
        return "warning"
    if status_name == ACTION_TAKEN_STATUS_NAME:
        return "success"
    if status_name == DISMISSED_STATUS_NAME:
        return "secondary"
    return "secondary"


def _build_preserved_query_string(
    *,
    search_email: str,
    report_status: str,
    report_type: str,
    sort_by: str,
) -> str:
    items: list[tuple[str, str]] = []
    if search_email:
        items.append(("search_email", search_email))
    if report_status:
        items.append(("report_status", report_status))
    if report_type:
        items.append(("report_type", report_type))
    if sort_by:
        items.append(("sort_by", sort_by))
    return urlencode(items)


def _build_person_display_name(user: Any) -> str:
    first_name = str(getattr(user, "first_name", "")).strip()
    last_name = str(getattr(user, "last_name", "")).strip()
    full_name = f"{first_name} {last_name}".strip()
    return full_name or str(getattr(user, "username", "Unknown user"))


def _truncate_text(value: str, limit: int) -> str:
    text = value.strip()
    if len(text) <= limit:
        return text
    return f"{text[: max(0, limit - 3)].rstrip()}..."


def _humanize_age(created_at: Any) -> str:
    delta = timezone.now() - created_at
    if delta.days >= 1:
        day_label = "day" if delta.days == 1 else "days"
        return f"{delta.days} {day_label}"

    total_hours = max(1, int(delta.total_seconds() // 3600))
    if total_hours >= 1:
        hour_label = "hour" if total_hours == 1 else "hours"
        return f"{total_hours} {hour_label}"

    total_minutes = max(1, int(delta.total_seconds() // 60))
    minute_label = "minute" if total_minutes == 1 else "minutes"
    return f"{total_minutes} {minute_label}"


def _format_short_datetime(value: Any) -> str:
    return timezone.localtime(value).strftime("%b %d, %Y")