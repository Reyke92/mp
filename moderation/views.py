from __future__ import annotations

from typing import Any

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.views.decorators.http import require_http_methods

from accounts.utils.auth import is_user_administrator, is_user_moderator
from moderation.forms import ModerationQueueFilterForm, ReportDispositionForm
from moderation.utils.queue import build_moderation_queue_page_content
from moderation.utils.report_detail import build_report_detail_page_content, record_report_disposition



def enforce_staff_access(request: HttpRequest) -> None:
    if not (is_user_moderator(request.user) or is_user_administrator(request.user)):
        raise PermissionDenied("You do not have permission to access this page.")


@login_required
@require_http_methods(["GET"])
def mod_queue_view(request: HttpRequest) -> HttpResponse:
    enforce_staff_access(request)

    filter_form = ModerationQueueFilterForm(request.GET or None)
    cleaned_data: dict[str, Any] = filter_form.cleaned_data if filter_form.is_valid() else {}
    page_number = _parse_page_number(request.GET.get("page"))

    page_content = build_moderation_queue_page_content(
        search_email=str(cleaned_data.get("search_email", "") or ""),
        report_status=str(cleaned_data.get("report_status", "") or ""),
        report_type=str(cleaned_data.get("report_type", "") or ""),
        sort_by=str(cleaned_data.get("sort_by", "") or ""),
        page_number=page_number,
    )

    context: dict[str, Any] = {
        "filter_form": filter_form,
        "page_obj": page_content.page_obj,
        "queue_summary_cards": page_content.queue_summary_cards,
        "needs_attention_rows": page_content.needs_attention_rows,
        "table_rows": page_content.table_rows,
        "total_report_count": page_content.total_report_count,
        "preserved_query_string_without_page": page_content.preserved_query_string_without_page,
        "page_range": page_content.page_range,
    }
    return render(request, "moderation/queue.html", context)


@login_required
@require_http_methods(["GET", "POST"])
def report_details_view(request: HttpRequest, report_id: int) -> HttpResponse:
    enforce_staff_access(request)

    readonly_mode = str(request.GET.get("readonly", "")).strip() in {"1", "true", "yes"}
    page_content = build_report_detail_page_content(report_id=report_id, readonly_mode=readonly_mode)

    if request.method == "POST":
        if readonly_mode:
            raise PermissionDenied("Read-only report detail pages cannot record dispositions.")

        submit_action = str(request.POST.get("action", "")).strip().lower()
        if submit_action == "dismiss":
            try:
                affected_count = record_report_disposition(
                    report_id=report_id,
                    actor_user=request.user,
                    action_type_id=None,
                    dismiss_report=True,
                    notes=str(request.POST.get("notes", "")).strip(),
                )
            except PermissionDenied as exc:
                messages.error(request, str(exc))
            else:
                messages.success(
                    request,
                    f"Dismissed {affected_count} open related report{'s' if affected_count != 1 else ''} for this target.",
                )
                return redirect("report_details", report_id=report_id)
        else:
            disposition_form = ReportDispositionForm(
                request.POST,
                allowed_action_names=page_content.allowed_action_names,
            )
            if disposition_form.is_valid():
                try:
                    affected_count = record_report_disposition(
                        report_id=report_id,
                        actor_user=request.user,
                        action_type_id=int(disposition_form.cleaned_data["action_type"]),
                        dismiss_report=False,
                        notes=str(disposition_form.cleaned_data.get("notes", "")).strip(),
                    )
                except PermissionDenied as exc:
                    messages.error(request, str(exc))
                else:
                    action_label = dict(disposition_form.fields["action_type"].choices).get(
                        str(disposition_form.cleaned_data["action_type"]),
                        "moderation action",
                    )
                    messages.success(
                        request,
                        f"Recorded {action_label} and updated {affected_count} open related report{'s' if affected_count != 1 else ''} for this target.",
                    )
                    return redirect("report_details", report_id=report_id)
            else:
                context = {
                    "page_context": page_content,
                    "disposition_form": disposition_form,
                }
                return render(request, "moderation/report_details.html", context)

    disposition_form = ReportDispositionForm(allowed_action_names=page_content.allowed_action_names)
    context = {
        "page_context": page_content,
        "disposition_form": disposition_form,
    }
    return render(request, "moderation/report_details.html", context)



def _parse_page_number(raw_page_number: Any) -> int:
    try:
        page_number = int(raw_page_number)
    except (TypeError, ValueError):
        return 1
    return page_number if page_number > 0 else 1
