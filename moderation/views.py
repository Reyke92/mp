from __future__ import annotations

from accounts.utils.auth import is_user_moderator, is_user_administrator
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import HttpRequest
from django.shortcuts import render
from django.views.decorators.http import require_http_methods
from moderation.forms import ModerationQueueFilterForm, ReportDispositionForm
from moderation.utils.report_detail import build_report_detail_page_content
from moderation.utils.queue import build_moderation_queue_page_content
from typing import Any

def enforce_staff_access(request: HttpRequest):
    if not (is_user_moderator(request.user) or is_user_administrator(request.user)):
        raise PermissionDenied("You do not have permission to access this page.")
    
@login_required
@require_http_methods(["GET"])
def mod_queue_view(request: HttpRequest):
    enforce_staff_access(request)

    filter_form = ModerationQueueFilterForm(request.GET or None)
    if filter_form.is_bound and filter_form.is_valid():
        cleaned = filter_form.cleaned_data
    else:
        cleaned = {}
        
    page_number = int(request.GET.get("page", 1))
    page_content = build_moderation_queue_page_content(
        search_email=cleaned.get("search_email", ""),
        report_status=cleaned.get("report_status", ""),
        report_type=cleaned.get("report_type", ""),
        sort_by=cleaned.get("sort_by", ""),
        page_number=page_number
    )
    
    context: dict[str, Any] = {
        "filter_form": filter_form,
        "page_obj": page_content.page_obj,
        "table_rows": page_content.table_rows,
        "total_report_count": page_content.total_report_count,
        "preserved_query_string_without_page": page_content.preserved_query_string_without_page,
        "page_range": page_content.page_range
    }
    return render(request, 'moderation/queue.html', context)

@login_required
@require_http_methods(["GET"])
def report_details_view(request: HttpRequest, report_id: int):
    enforce_staff_access(request)

    page_content = build_report_detail_page_content(report_id)
    disposition_form = ReportDispositionForm()

    content = {
        "page_context": page_content,
        "disposition_form": disposition_form
    }
    return render(request, "moderation/report_details.html", content)