from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from math import ceil
from typing import Any, Iterable

from django.contrib.auth import get_user_model
from django.db.models import Sum
from django.db.models.functions import Coalesce
from django.utils import timezone

from listings.models import Listing
from messaging.models import Conversation, Message
from reports.models import Report


ACTIVE_LISTING_STATUS_NAME: str = "Active"
OPEN_REPORT_STATUS_NAME: str = "Received"
_DEFAULT_TREND_RANGE_WEEKS: int = 12
_TOOLTIP_THRESHOLD: int = 10_000


@dataclass(frozen=True)
class DashboardMetric:
    label: str
    value: int
    compact_value: str
    tooltip_value: str | None
    helper_text: str


@dataclass(frozen=True)
class TrendPoint:
    label: str
    short_label: str
    value: int
    compact_value: str
    tooltip_value: str | None
    height_percent: float
    show_axis_label: bool


@dataclass(frozen=True)
class TrendMetricCard:
    key: str
    title: str
    total_value: int
    total_compact_value: str
    total_tooltip_value: str | None
    average_per_week: str
    points: list[TrendPoint]
    empty_state_message: str


@dataclass(frozen=True)
class AdminDashboardPageContext:
    summary_metrics: list[DashboardMetric]
    trend_cards: list[TrendMetricCard]
    selected_start_date: date
    selected_end_date: date
    total_weeks_in_range: int
    trend_range_label: str


class InvalidDashboardDateRangeError(Exception):
    """Raised when the administrator dashboard date range is invalid."""



def get_default_dashboard_start_date() -> date:
    today: date = timezone.localdate()
    start_of_current_week: date = today - timedelta(days=today.weekday())
    return start_of_current_week - timedelta(weeks=_DEFAULT_TREND_RANGE_WEEKS - 1)



def get_default_dashboard_end_date() -> date:
    return timezone.localdate()



def build_admin_dashboard_page_context(*, start_date: date, end_date: date) -> AdminDashboardPageContext:
    if end_date < start_date:
        raise InvalidDashboardDateRangeError("The end date must be on or after the start date.")

    summary_metrics: list[DashboardMetric] = _build_summary_metrics()
    week_starts: list[date] = _build_week_starts(start_date=start_date, end_date=end_date)

    trend_cards: list[TrendMetricCard] = [
        _build_trend_metric_card(
            key="new_listings",
            title="New Listings per Week",
            values_by_week_start=_build_weekly_counts_for_datetimes(
                datetimes=Listing.objects.filter(
                    created_at__date__gte=start_date,
                    created_at__date__lte=end_date,
                ).values_list("created_at", flat=True),
                week_starts=week_starts,
            ),
            week_starts=week_starts,
            empty_state_message="No listings were created during the selected date range.",
        ),
        _build_trend_metric_card(
            key="new_messages",
            title="New Messages per Week",
            values_by_week_start=_build_weekly_counts_for_datetimes(
                datetimes=Message.objects.filter(
                    sent_at__date__gte=start_date,
                    sent_at__date__lte=end_date,
                ).values_list("sent_at", flat=True),
                week_starts=week_starts,
            ),
            week_starts=week_starts,
            empty_state_message="No messages were created during the selected date range.",
        ),
        _build_trend_metric_card(
            key="new_users",
            title="New Registered Users per Week",
            values_by_week_start=_build_weekly_counts_for_datetimes(
                datetimes=get_user_model().objects.filter(
                    date_joined__date__gte=start_date,
                    date_joined__date__lte=end_date,
                ).values_list("date_joined", flat=True),
                week_starts=week_starts,
            ),
            week_starts=week_starts,
            empty_state_message="No accounts were created during the selected date range.",
        ),
        _build_trend_metric_card(
            key="new_reports",
            title="New Reports per Week",
            values_by_week_start=_build_weekly_counts_for_datetimes(
                datetimes=Report.objects.filter(
                    created_at__date__gte=start_date,
                    created_at__date__lte=end_date,
                ).values_list("created_at", flat=True),
                week_starts=week_starts,
            ),
            week_starts=week_starts,
            empty_state_message="No reports were created during the selected date range.",
        ),
    ]

    return AdminDashboardPageContext(
        summary_metrics=summary_metrics,
        trend_cards=trend_cards,
        selected_start_date=start_date,
        selected_end_date=end_date,
        total_weeks_in_range=len(week_starts),
        trend_range_label=_build_trend_range_label(start_date=start_date, end_date=end_date, week_count=len(week_starts)),
    )



def _build_summary_metrics() -> list[DashboardMetric]:
    total_registered_users: int = int(get_user_model().objects.count())
    total_active_listings: int = int(Listing.objects.filter(status__status_name=ACTIVE_LISTING_STATUS_NAME).count())
    total_conversations: int = int(Conversation.objects.count())
    total_messages: int = int(Message.objects.count())
    total_open_reports: int = int(Report.objects.filter(status__status_name=OPEN_REPORT_STATUS_NAME).count())
    total_sitewide_listing_views: int = int(
        Listing.objects.aggregate(total_views=Coalesce(Sum("view_count"), 0))["total_views"] or 0
    )

    return [
        _build_dashboard_metric(
            label="Total Registered Users",
            value=total_registered_users,
            helper_text="All accounts currently stored in the marketplace database.",
        ),
        _build_dashboard_metric(
            label="Total Active Listings",
            value=total_active_listings,
            helper_text="Listings whose status is currently set to Active.",
        ),
        _build_dashboard_metric(
            label="Total Conversations",
            value=total_conversations,
            helper_text="Buyer-seller conversation threads recorded across the site.",
        ),
        _build_dashboard_metric(
            label="Total Messages",
            value=total_messages,
            helper_text="All stored buyer-seller messages recorded by the platform.",
        ),
        _build_dashboard_metric(
            label="Total Open Reports",
            value=total_open_reports,
            helper_text="Reports whose current status is still Received.",
        ),
        _build_dashboard_metric(
            label="Total Site-Wide Listing Views",
            value=total_sitewide_listing_views,
            helper_text="The sum of listing view counts across every stored listing.",
        ),
    ]



def _build_dashboard_metric(*, label: str, value: int, helper_text: str) -> DashboardMetric:
    compact_value: str = _format_compact_number(value)
    tooltip_value: str | None = _format_full_number(value) if value >= _TOOLTIP_THRESHOLD else None
    return DashboardMetric(
        label=label,
        value=value,
        compact_value=compact_value,
        tooltip_value=tooltip_value,
        helper_text=helper_text,
    )



def _build_trend_metric_card(
    *,
    key: str,
    title: str,
    values_by_week_start: dict[date, int],
    week_starts: list[date],
    empty_state_message: str,
) -> TrendMetricCard:
    ordered_values: list[int] = [int(values_by_week_start.get(week_start, 0)) for week_start in week_starts]
    peak_value: int = max(ordered_values) if ordered_values else 0
    label_step: int = max(1, ceil(len(week_starts) / 6)) if week_starts else 1

    points: list[TrendPoint] = []
    for index, week_start in enumerate(week_starts):
        value: int = ordered_values[index]
        height_percent: float = 0.0
        if peak_value > 0:
            height_percent = max(12.0, (value / peak_value) * 100.0) if value > 0 else 0.0

        show_axis_label: bool = index == 0 or index == len(week_starts) - 1 or index % label_step == 0
        tooltip_value: str | None = _format_full_number(value) if value >= _TOOLTIP_THRESHOLD else None

        points.append(
            TrendPoint(
                label=_build_week_label(week_start=week_start),
                short_label=week_start.strftime("%b %d"),
                value=value,
                compact_value=_format_compact_number(value),
                tooltip_value=tooltip_value,
                height_percent=height_percent,
                show_axis_label=show_axis_label,
            )
        )

    total_value: int = sum(ordered_values)
    average_per_week: str = f"{_format_compact_number(round(total_value / max(len(week_starts), 1)))} avg / week"

    return TrendMetricCard(
        key=key,
        title=title,
        total_value=total_value,
        total_compact_value=_format_compact_number(total_value),
        total_tooltip_value=_format_full_number(total_value) if total_value >= _TOOLTIP_THRESHOLD else None,
        average_per_week=average_per_week,
        points=points,
        empty_state_message=empty_state_message,
    )



def _build_weekly_counts_for_datetimes(*, datetimes: Iterable[datetime | date | None], week_starts: list[date]) -> dict[date, int]:
    counts_by_week_start: dict[date, int] = {week_start: 0 for week_start in week_starts}
    if not week_starts:
        return counts_by_week_start

    min_week_start: date = week_starts[0]
    max_week_start: date = week_starts[-1]

    for raw_value in datetimes:
        resolved_date: date | None = _coerce_to_local_date(raw_value)
        if resolved_date is None:
            continue

        current_week_start: date = resolved_date - timedelta(days=resolved_date.weekday())
        if current_week_start < min_week_start or current_week_start > max_week_start:
            continue

        counts_by_week_start[current_week_start] = counts_by_week_start.get(current_week_start, 0) + 1

    return counts_by_week_start



def _coerce_to_local_date(value: datetime | date | None) -> date | None:
    if value is None:
        return None

    if isinstance(value, datetime):
        if timezone.is_aware(value):
            value = timezone.localtime(value)
        return value.date()

    return value



def _build_week_starts(*, start_date: date, end_date: date) -> list[date]:
    first_week_start: date = start_date - timedelta(days=start_date.weekday())
    last_week_start: date = end_date - timedelta(days=end_date.weekday())

    week_starts: list[date] = []
    current_week_start: date = first_week_start
    while current_week_start <= last_week_start:
        week_starts.append(current_week_start)
        current_week_start += timedelta(weeks=1)

    return week_starts



def _build_week_label(*, week_start: date) -> str:
    week_end: date = week_start + timedelta(days=6)
    if week_start.year == week_end.year:
        return f"Week of {week_start.strftime('%b %d')} – {week_end.strftime('%b %d, %Y')}"
    return f"Week of {week_start.strftime('%b %d, %Y')} – {week_end.strftime('%b %d, %Y')}"



def _build_trend_range_label(*, start_date: date, end_date: date, week_count: int) -> str:
    return f"{start_date.strftime('%b %d, %Y')} through {end_date.strftime('%b %d, %Y')} · {week_count} week{'s' if week_count != 1 else ''}"



def _format_compact_number(value: int) -> str:
    absolute_value: int = abs(int(value))
    sign: str = "-" if value < 0 else ""

    thresholds: tuple[tuple[int, str], ...] = (
        (1_000_000_000, "B"),
        (1_000_000, "M"),
        (1_000, "K"),
    )
    for threshold, suffix in thresholds:
        if absolute_value >= threshold:
            scaled_value: float = absolute_value / threshold
            decimal_places: int = 1 if scaled_value < 100 else 0
            formatted_value: str = f"{scaled_value:.{decimal_places}f}".rstrip("0").rstrip(".")
            return f"{sign}{formatted_value}{suffix}"

    return f"{value:,}"



def _format_full_number(value: int) -> str:
    return f"{value:,}"
