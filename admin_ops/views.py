from __future__ import annotations

from typing import Any

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.http import require_http_methods

from admin_ops.forms import ListingManagementFilterForm, UserManagementFilterForm
from admin_ops.utils.roles import is_user_administrator
from admin_ops.utils.listing_management import (
    ListingManagementActionError,
    ListingManagementPermissionError,
    UnsupportedListingManagementActionError,
    build_listing_management_page_context,
    build_selected_listing_card_context,
    perform_listing_management_action,
)
from admin_ops.utils.user_management import (
    UnsupportedUserManagementActionError,
    UserManagementActionError,
    UserManagementPermissionError,
    build_selected_user_card_context,
    build_user_management_page_context,
    perform_user_management_action,
)


@login_required
@require_http_methods(["GET", "POST"])
def user_management_view(request: HttpRequest) -> HttpResponse:
    _enforce_administrator_access(request)

    if request.method == "POST":
        response: HttpResponse = _handle_user_management_post(request)
        return response

    filter_form: UserManagementFilterForm = UserManagementFilterForm(request.GET or None)
    if not filter_form.is_valid():
        filter_form = UserManagementFilterForm()

    cleaned_data: dict[str, Any] = filter_form.cleaned_data if filter_form.is_valid() else {}
    selected_user_id: int | None = _parse_optional_int(request.GET.get("selected"))
    page_number: int = _parse_page_number(request.GET.get("page"))

    page_context = build_user_management_page_context(
        search_email=str(cleaned_data.get("search_email", "") or ""),
        account_status=str(cleaned_data.get("account_status", "") or ""),
        user_role=str(cleaned_data.get("user_role", "") or ""),
        sort_by=str(cleaned_data.get("sort_by", "newest") or "newest"),
        page_number=page_number,
        selected_user_id=selected_user_id,
        base_url=reverse("user_management"),
        acting_user_id=int(request.user.id),
    )

    context: dict[str, Any] = {
        "filter_form": filter_form,
        "page_obj": page_context.page_obj,
        "table_rows": page_context.table_rows,
        "selected_user": page_context.selected_user,
        "selected_user_id": page_context.selected_user_id,
        "total_user_count": page_context.total_user_count,
        "filter_summary_parts": page_context.filter_summary_parts,
        "preserved_query_string_without_page": page_context.preserved_query_string_without_page,
        "preserved_query_string_without_selected": page_context.preserved_query_string_without_selected,
        "preserved_query_items": page_context.preserved_query_items,
        "page_range": page_context.page_range,
    }
    return render(request, "admin_ops/user_management.html", context)



@login_required
@require_http_methods(["GET"])
def user_management_selected_card_view(request: HttpRequest, user_id: int) -> HttpResponse:
    _enforce_administrator_access(request)

    filter_form: UserManagementFilterForm = UserManagementFilterForm(request.GET or None)
    if not filter_form.is_valid():
        filter_form = UserManagementFilterForm()

    cleaned_data: dict[str, Any] = filter_form.cleaned_data if filter_form.is_valid() else {}
    page_number: int = _parse_page_number(request.GET.get("page"))

    card_context = build_selected_user_card_context(
        user_id=int(user_id),
        search_email=str(cleaned_data.get("search_email", "") or ""),
        account_status=str(cleaned_data.get("account_status", "") or ""),
        user_role=str(cleaned_data.get("user_role", "") or ""),
        sort_by=str(cleaned_data.get("sort_by", "newest") or "newest"),
        page_number=page_number,
        acting_user_id=int(request.user.id),
    )
    if card_context.selected_user is None:
        raise Http404

    context: dict[str, Any] = {
        "selected_user": card_context.selected_user,
        "preserved_query_items": card_context.preserved_query_items,
        "page_number": card_context.page_number,
    }
    return render(request, "admin_ops/partials/selected_user_card.html", context)



@login_required
@require_http_methods(["GET"])
def user_conversations_view(request: HttpRequest, user_id: int) -> HttpResponse:
    _enforce_administrator_access(request)

    context: dict[str, Any] = {
        "oversight_user_id": int(user_id),
    }
    return render(request, "admin_ops/user_conversations.html", context)



@login_required
@require_http_methods(["GET"])
def listing_management_selected_card_view(request: HttpRequest, listing_id: int) -> HttpResponse:
    _enforce_administrator_access(request)

    filter_form: ListingManagementFilterForm = ListingManagementFilterForm(request.GET or None)
    if not filter_form.is_valid():
        filter_form = ListingManagementFilterForm()

    cleaned_data: dict[str, Any] = filter_form.cleaned_data if filter_form.is_valid() else {}
    selected_category_id: int | None = _parse_optional_int(cleaned_data.get("category_id"))
    page_number: int = _parse_page_number(request.GET.get("page"))

    card_context = build_selected_listing_card_context(
        listing_id=int(listing_id),
        search_query=str(cleaned_data.get("search_query", "") or ""),
        listing_status=str(cleaned_data.get("listing_status", "") or ""),
        category_id=selected_category_id,
        sort_by=str(cleaned_data.get("sort_by", "newest") or "newest"),
        page_number=page_number,
    )
    if card_context.selected_listing is None:
        raise Http404

    context: dict[str, Any] = {
        "selected_listing": card_context.selected_listing,
        "preserved_query_items": card_context.preserved_query_items,
        "page_number": card_context.page_number,
    }
    return render(request, "admin_ops/partials/selected_listing_card.html", context)



@login_required
@require_http_methods(["GET", "POST"])
def listing_management_view(request: HttpRequest) -> HttpResponse:
    _enforce_administrator_access(request)

    if request.method == "POST":
        response: HttpResponse = _handle_listing_management_post(request)
        return response

    filter_form: ListingManagementFilterForm = ListingManagementFilterForm(request.GET or None)
    if not filter_form.is_valid():
        filter_form = ListingManagementFilterForm()

    cleaned_data: dict[str, Any] = filter_form.cleaned_data if filter_form.is_valid() else {}
    selected_listing_id: int | None = _parse_optional_int(request.GET.get("selected"))
    selected_category_id: int | None = _parse_optional_int(cleaned_data.get("category_id"))
    page_number: int = _parse_page_number(request.GET.get("page"))

    page_context = build_listing_management_page_context(
        search_query=str(cleaned_data.get("search_query", "") or ""),
        listing_status=str(cleaned_data.get("listing_status", "") or ""),
        category_id=selected_category_id,
        sort_by=str(cleaned_data.get("sort_by", "newest") or "newest"),
        page_number=page_number,
        selected_listing_id=selected_listing_id,
        base_url=reverse("listing_management"),
    )

    context: dict[str, Any] = {
        "filter_form": filter_form,
        "page_obj": page_context.page_obj,
        "table_rows": page_context.table_rows,
        "selected_listing": page_context.selected_listing,
        "selected_listing_id": page_context.selected_listing_id,
        "total_listing_count": page_context.total_listing_count,
        "filter_summary_parts": page_context.filter_summary_parts,
        "preserved_query_string_without_page": page_context.preserved_query_string_without_page,
        "preserved_query_string_without_selected": page_context.preserved_query_string_without_selected,
        "preserved_query_items": page_context.preserved_query_items,
        "page_range": page_context.page_range,
        "current_page_number": page_context.page_obj.number,
    }
    return render(request, "admin_ops/listing_management.html", context)



def _handle_listing_management_post(request: HttpRequest) -> HttpResponse:
    action_name: str = str(request.POST.get("action", "")).strip()
    target_listing_id: int | None = _parse_optional_int(request.POST.get("target_listing_id"))

    if target_listing_id is None:
        messages.error(request, "Choose a valid listing before running an administrative action.")
        return redirect(_build_listing_management_return_url(request))

    requesting_user_id: int = int(request.user.id)

    try:
        success_message: str = perform_listing_management_action(
            requesting_user_id=requesting_user_id,
            target_listing_id=target_listing_id,
            action_name=action_name,
        )
    except ListingManagementPermissionError as exc:
        messages.error(request, str(exc))
    except ListingManagementActionError as exc:
        messages.error(request, str(exc))
    except UnsupportedListingManagementActionError:
        messages.error(request, "That administrative action is not supported yet.")
    except PermissionDenied:
        raise
    except Exception:
        messages.error(request, "The administrative action could not be completed. Please review the selected listing and try again.")
    else:
        messages.success(request, success_message)

    return redirect(_build_listing_management_return_url(request, selected_listing_id=target_listing_id))


def _handle_user_management_post(request: HttpRequest) -> HttpResponse:
    action_name: str = str(request.POST.get("action", "")).strip()
    target_user_id: int | None = _parse_optional_int(request.POST.get("target_user_id"))

    if target_user_id is None:
        messages.error(request, "Choose a valid user before running an administrative action.")
        return redirect(_build_return_url(request))

    requesting_user_id: int = int(request.user.id)

    try:
        success_message: str = perform_user_management_action(
            requesting_user_id=requesting_user_id,
            target_user_id=target_user_id,
            action_name=action_name,
        )
    except UserManagementPermissionError as exc:
        messages.error(request, str(exc))
    except UserManagementActionError as exc:
        messages.error(request, str(exc))
    except UnsupportedUserManagementActionError:
        messages.error(request, "That administrative action is not supported yet.")
    except PermissionDenied:
        raise
    except Exception:
        messages.error(request, "The administrative action could not be completed. Please review the selected user and try again.")
    else:
        messages.success(request, success_message)

    return redirect(_build_return_url(request, selected_user_id=target_user_id))



def _enforce_administrator_access(request: HttpRequest) -> None:
    if not is_user_administrator(request.user):
        raise PermissionDenied



def _build_listing_management_return_url(request: HttpRequest, selected_listing_id: int | None = None) -> str:
    query_items: list[tuple[str, str]] = []
    for key in ("search_query", "listing_status", "category_id", "sort_by", "page"):
        value: str = str(request.POST.get(key, "")).strip()
        if value != "":
            query_items.append((key, value))

    resolved_selected_listing_id: int | None = selected_listing_id
    if resolved_selected_listing_id is None:
        resolved_selected_listing_id = _parse_optional_int(request.POST.get("selected"))

    if resolved_selected_listing_id is not None:
        query_items.append(("selected", str(resolved_selected_listing_id)))

    base_url: str = reverse("listing_management")
    if not query_items:
        return base_url

    from urllib.parse import urlencode

    return f"{base_url}?{urlencode(query_items, doseq=True)}"


def _build_return_url(request: HttpRequest, selected_user_id: int | None = None) -> str:
    query_items: list[tuple[str, str]] = []
    for key in ("search_email", "account_status", "user_role", "sort_by", "page"):
        value: str = str(request.POST.get(key, "")).strip()
        if value != "":
            query_items.append((key, value))

    resolved_selected_user_id: int | None = selected_user_id
    if resolved_selected_user_id is None:
        resolved_selected_user_id = _parse_optional_int(request.POST.get("selected"))

    if resolved_selected_user_id is not None:
        query_items.append(("selected", str(resolved_selected_user_id)))

    base_url: str = reverse("user_management")
    if not query_items:
        return base_url

    from urllib.parse import urlencode

    return f"{base_url}?{urlencode(query_items, doseq=True)}"



def _parse_optional_int(raw_value: Any) -> int | None:
    if raw_value in {None, ""}:
        return None

    try:
        return int(raw_value)
    except (TypeError, ValueError):
        return None



def _parse_page_number(raw_value: Any) -> int:
    parsed_value: int | None = _parse_optional_int(raw_value)
    if parsed_value is None or parsed_value < 1:
        return 1
    return parsed_value
