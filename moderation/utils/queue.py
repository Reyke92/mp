from __future__ import annotations

from dataclasses import dataclass, field
from django.core.paginator import Page, Paginator
from django.db.models import QuerySet
from django.urls import reverse
from reports.models import Report
from urllib.parse import urlencode
from moderation.forms import (
    QUEUE_SORT_MOST_RECENT_VALUE,
    QUEUE_SORT_OLDEST_OPEN_VALUE,
    QUEUE_STATUS_RECEIVED_VALUE,
    QUEUE_STATUS_RESOLVED_VALUE,
    QUEUE_TYPE_CONVERSATION_VALUE,
    QUEUE_TYPE_LISTING_VALUE,
)

PAGE_SIZE: int = 20

@dataclass(frozen=True)
class ModerationQueueRow:
    report_id: int
    report_type_label: str
    reason_text: str
    status_label: str
    status_variant: str
    detail_url: str

@dataclass(frozen=True)
class ModerationQueuePageContent:
    page_obj: Page
    table_rows: list[ModerationQueueRow]
    total_report_count: int
    preserved_query_string_without_page: str
    page_range: list[int] = field(default_factory=list)

def build_moderation_queue_page_content(*, search_email: str, report_status: str, report_type: str, sort_by: str, page_number: int):
    normalized_email = search_email.strip()

    queryset: QuerySet[Report] = build_queue_queryset(
        search_email=normalized_email,
        report_status=report_status,
        report_type=report_type,
    )
    queryset = apply_queue_sort(queryset=queryset, sort_by=sort_by)

    paginator = Paginator(queryset, PAGE_SIZE)
    page_obj = paginator.get_page(page_number)

    preserved_query_string_without_page = build_preserved_query_string(
        search_email=normalized_email,
        report_status=report_status,
        report_type=report_type,
        sort_by=sort_by,
    )
    table_rows = [
        build_row(report) for report in page_obj.object_list
    ]
    page_range = list(paginator.get_elided_page_range(page_obj.number, on_each_side=1, on_ends=1))  #type: ignore[attr-defined]

    return ModerationQueuePageContent(
        page_obj=page_obj,
        table_rows=table_rows,
        total_report_count=paginator.count,
        preserved_query_string_without_page=preserved_query_string_without_page,
        page_range=page_range,
    )
    
def build_queue_queryset(*, search_email: str, report_status: str, report_type: str):
    queryset = Report.objects.select_related("reporter_user", "status")

    if search_email:
        queryset = queryset.filter(reporter_user__username__icontains=search_email)
    
    if report_status == QUEUE_STATUS_RECEIVED_VALUE:
        queryset = queryset.filter(status__status_name="Received")
    elif report_status == QUEUE_STATUS_RESOLVED_VALUE:
        queryset = queryset.filter(status__status_name__in=["ActionTaken", "Dismissed"])

    if report_type == QUEUE_TYPE_LISTING_VALUE:
        queryset = queryset.filter(listing__isnull=False)
    elif report_type == QUEUE_TYPE_CONVERSATION_VALUE:
        queryset = queryset.filter(conversation__isnull=False)

    return queryset 

def apply_queue_sort(*, queryset: QuerySet[Report], sort_by: str):
    if (sort_by == QUEUE_SORT_MOST_RECENT_VALUE):
        return queryset.order_by("-created_at", "-report_id")
    
    return queryset.order_by("created_at", "report_id")

def build_preserved_query_string(*, search_email: str, report_status: str, report_type: str, sort_by: str):
    items = []
    if search_email.strip():
        items.append(("search_email", search_email))
    if report_status.strip():
        items.append(("report_status", report_status))
    if report_type.strip():
        items.append(("report_type", report_type))
    if sort_by.strip():
        items.append(("sort_by", sort_by))
    return urlencode(items)

def build_row(report: Report):
    is_listing_report = report.listing_id is not None   #type: ignore[attr-defined]
    report_type_label = "Listing" if is_listing_report else "Conversation"

    status_name = str(report.status.status_name)
    status_variant = "warning" if status_name == "Recieved" else "secondary"
    reason = str(report.details).strip()
    detail_url = reverse("report_details", kwargs={"report_id": report.report_id})

    return ModerationQueueRow(
        report_id=int(report.report_id),
        report_type_label=report_type_label,
        reason_text=reason or "(no reason provided)",
        status_label=status_name,
        status_variant=status_variant,
        detail_url=detail_url
    )
