from __future__ import annotations

from dataclasses import dataclass
from django.shortcuts import get_object_or_404
from django.urls import reverse
from reports.models import Report

@dataclass(frozen=True)
class ReportDetailPageContent:
    report: Report
    report_type_label: str
    reporter_email: str
    reported_user_email: str
    status_label: str
    status_variant: str
    view_target_url: str | None
    view_target_disabled_reason: str | None
    view_reporter_url: str
    view_user_url: str
    back_to_queue_url: str

def build_report_detail_page_content(report_id: int):
    report = get_object_or_404(Report.objects.select_related(
        "reporter_user",
        "status",
        "listing",
        "listing__seller_user",
        "conversation",
        "conversation__user_a",
        "conversation__user_b"
    ), report_id=report_id)

    is_listing_report = report.listing_id is not None   #type: ignore
    report_type_label = "Listing" if is_listing_report else "Conversation"
    reported_user = resolve_reported_user(report=report, is_listing_report=is_listing_report)
    reported_user_email = str(reported_user.username)
    status_name = str(report.status.status_name)
    status_variant = status_variant_for(status_name)
    
    view_target_url, view_target_disabled_reason = resolve_view_target(report=report, is_listing_report=is_listing_report)
    view_reporter_url = reverse("view_profile", kwargs={"id": int(report.reporter_user_id)})    #type: ignore
    view_user_url = reverse("view_profile", kwargs={"id": int(reported_user.id)})

    return ReportDetailPageContent(
        report=report,
        report_type_label=report_type_label,
        reporter_email=str(report.reporter_user.username),
        reported_user_email=reported_user_email,
        status_label=status_name,
        status_variant=status_variant,
        view_target_url=view_target_url,
        view_target_disabled_reason=view_target_disabled_reason,
        view_reporter_url=view_reporter_url,
        view_user_url=view_user_url,
        back_to_queue_url=reverse("moderation_queue")
    )


def resolve_reported_user(*, report: Report, is_listing_report: bool):
    if is_listing_report:
        return report.listing.seller_user   #type: ignore
    
    conversation = report.conversation
    if conversation.user_a_id == report.reporter_user_id:   #type: ignore
        return conversation.user_b  #type: ignore
    return conversation.user_a  #type: ignore

def status_variant_for(status_name: str):
    if status_name == "Received":
        return "warning"
    if status_name == "ActionTaken":
        return "success"
    if status_name == "Dismissed":
        return "secondary"
    return "secondary"

def resolve_view_target(*, report: Report, is_listing_report: bool):
    if is_listing_report:
        url = reverse("listing_detail", kwargs={"listing_id": int(report.listing_id)})  #type: ignore
        return url, None
    
    # TODO: Conversation Moderator View
    return None, "Conversation Moderator View Not Implemented Yet"