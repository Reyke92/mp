from __future__ import annotations

from typing import Any

from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import redirect, render

from accounts.models import UserProfile

from .forms import CreateListingForm
from .utils import (
    build_create_listing_attribute_sections,
    build_my_listings_rows,
    create_listing_from_form,
    get_cities_for_state,
    get_listing_detail_context_data,
)


@login_required
def create_listing_view(request: HttpRequest) -> HttpResponse:
    initial_data: dict[str, Any] = _build_initial_create_listing_data(request)

    if request.method == "POST":
        form: CreateListingForm = CreateListingForm(request.POST, request.FILES, initial=initial_data)
        if form.is_valid():
            listing = create_listing_from_form(form=form, seller_user=request.user)
            return redirect("listing_detail", listing_id=listing.listing_id)
    else:
        selected_category_id: int | None = _parse_optional_positive_int(request.GET.get("category"))
        if selected_category_id is not None:
            initial_data["category"] = selected_category_id
        form = CreateListingForm(initial=initial_data, selected_category_id=selected_category_id)

    selected_state_id: int | None = _extract_selected_state_id(form=form)
    city_suggestions: list[str] = [] if selected_state_id is None else get_cities_for_state(selected_state_id)

    context: dict[str, Any] = {
        "form": form,
        "attribute_sections": build_create_listing_attribute_sections(form),
        "city_suggestions": city_suggestions,
        "active_sidebar_item": "create_listing",
    }
    return render(request, "listings/create_listing.html", context)


@login_required
def create_listing_attribute_fields_partial_view(request: HttpRequest) -> HttpResponse:
    selected_category_id: int | None = _parse_optional_positive_int(request.GET.get("category"))
    form: CreateListingForm = CreateListingForm(
        initial={"category": selected_category_id} if selected_category_id is not None else {},
        selected_category_id=selected_category_id,
    )

    return render(
        request,
        "listings/partials/create_listing_attribute_fields.html",
        {
            "attribute_sections": build_create_listing_attribute_sections(form),
            "has_selected_category": selected_category_id is not None,
        },
    )


@login_required
def state_cities_view(request: HttpRequest) -> JsonResponse:
    state_id: int | None = _parse_optional_positive_int(request.GET.get("state_id"))
    if state_id is None:
        return JsonResponse({"cities": []})
    return JsonResponse({"cities": get_cities_for_state(state_id)})


@login_required
def my_listings_view(request: HttpRequest) -> HttpResponse:
    context: dict[str, Any] = {
        "rows": build_my_listings_rows(request.user),
        "active_sidebar_item": "my_listings",
    }
    return render(request, "listings/my_listings.html", context)


def listing_detail_view(request: HttpRequest, listing_id: int) -> HttpResponse:
    detail_context = get_listing_detail_context_data(listing_id=listing_id, viewer=request.user)
    context: dict[str, Any] = {
        "detail": detail_context,
        "active_sidebar_item": None,
    }
    return render(request, "listings/listing_detail.html", context)


def _build_initial_create_listing_data(request: HttpRequest) -> dict[str, Any]:
    initial_data: dict[str, Any] = {}
    if not request.user.is_authenticated:
        return initial_data

    try:
        profile: UserProfile = UserProfile.objects.select_related("city", "city__state").get(user=request.user)
    except UserProfile.DoesNotExist:
        return initial_data

    initial_data["city_name"] = str(profile.city.city_name)
    initial_data["state"] = int(profile.city.state_id)
    return initial_data


def _parse_optional_positive_int(raw_value: Any) -> int | None:
    if raw_value in {None, ""}:
        return None
    try:
        parsed_value: int = int(raw_value)
    except (TypeError, ValueError):
        return None
    return parsed_value if parsed_value > 0 else None


def _extract_selected_state_id(*, form: CreateListingForm) -> int | None:
    raw_value: Any
    if form.is_bound:
        raw_value = form.data.get("state")
    else:
        raw_value = form.initial.get("state")
    return _parse_optional_positive_int(raw_value)
