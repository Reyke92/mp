from __future__ import annotations

from typing import Any

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import redirect, render

from accounts.models import UserProfile

from .forms import CreateListingForm
from .utils import (
    build_create_listing_attribute_sections,
    build_existing_listing_images_payload,
    build_listing_form_initial,
    build_my_listings_rows,
    create_listing_from_form,
    get_cities_for_state,
    get_listing_detail_context_data,
    get_owner_listing_for_edit_or_403,
    mark_listing_deleted_by_owner,
    parse_image_id_list,
    update_listing_from_form,
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
        selected_category_id: int | None = _parse_optional_db_id(request.GET.get("category"))
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
        "editor_mode": "create",
        "page_title": "Create Listing",
        "page_description": "Share the essentials, add photos, and include item details in one place.",
        "page_hint": "Your photos stay on this device until you press Save Listing.",
        "primary_button_label": "Save Listing",
        "secondary_button_label": "Cancel",
        "secondary_button_url": "home",
        "existing_images_payload": [],
    }
    return render(request, "listings/create_listing.html", context)


@login_required
def edit_listing_view(request: HttpRequest, listing_id: int) -> HttpResponse:
    listing = get_owner_listing_for_edit_or_403(listing_id=listing_id, owner_user=request.user)
    initial_data: dict[str, Any] = build_listing_form_initial(listing)

    if request.method == "POST":
        form: CreateListingForm = CreateListingForm(request.POST, request.FILES, initial=initial_data)
        if form.is_valid():
            image_order_tokens: list[str] = request.POST.getlist("image_order")
            removed_existing_image_ids: list[int] = parse_image_id_list(
                request.POST.getlist("removed_existing_image_ids")
            )
            listing = update_listing_from_form(
                listing=listing,
                form=form,
                image_order_tokens=image_order_tokens,
                removed_existing_image_ids=removed_existing_image_ids,
            )
            return redirect("listing_detail", listing_id=listing.listing_id)
        existing_images_payload = build_existing_listing_images_payload(listing=listing, post_data=request.POST)
    else:
        form = CreateListingForm(initial=initial_data, selected_category_id=int(listing.category_id))
        existing_images_payload = build_existing_listing_images_payload(listing=listing)

    selected_state_id: int | None = _extract_selected_state_id(form=form)
    city_suggestions: list[str] = [] if selected_state_id is None else get_cities_for_state(selected_state_id)

    context: dict[str, Any] = {
        "listing": listing,
        "form": form,
        "attribute_sections": build_create_listing_attribute_sections(form),
        "city_suggestions": city_suggestions,
        "active_sidebar_item": "my_listings",
        "editor_mode": "edit",
        "page_title": "Edit Listing",
        "page_description": "Review and update the details shoppers see for this listing.",
        "page_hint": "New photos stay on this device until you press Save Changes.",
        "primary_button_label": "Save Changes",
        "secondary_button_label": "Discard",
        "secondary_button_url": "listing_detail",
        "secondary_button_listing_id": int(listing.listing_id),
        "existing_images_payload": existing_images_payload,
    }
    return render(request, "listings/edit_listing.html", context)


@login_required
def delete_listing_view(request: HttpRequest, listing_id: int) -> HttpResponse:
    if request.method != "POST":
        raise PermissionDenied("Deleting a listing requires POST.")

    listing = get_owner_listing_for_edit_or_403(listing_id=listing_id, owner_user=request.user)
    mark_listing_deleted_by_owner(listing=listing, owner_user=request.user)
    return redirect("my_listings")


@login_required
def create_listing_attribute_fields_partial_view(request: HttpRequest) -> HttpResponse:
    selected_category_id: int | None = _parse_optional_db_id(request.GET.get("category"))
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
    state_id: int | None = _parse_optional_db_id(request.GET.get("state_id"))
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
        "gallery_images_payload": [image.to_client_dict() for image in detail_context.gallery_images],
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


def _parse_optional_db_id(raw_value: Any) -> int | None:
    if raw_value in {None, ""}:
        return None
    try:
        return int(raw_value)
    except (TypeError, ValueError):
        return None


def _extract_selected_state_id(*, form: CreateListingForm) -> int | None:
    raw_value: Any
    if form.is_bound:
        raw_value = form.data.get("state")
    else:
        raw_value = form.initial.get("state")
    return _parse_optional_db_id(raw_value)
