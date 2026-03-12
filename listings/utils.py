from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time
from pathlib import Path
from typing import Any, Iterable
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.core.files.storage import default_storage
from django.db import transaction
from django.db.models import F, QuerySet
from django.http import Http404
from django.utils import timezone

from admin_ops.models import UserRoleAssignment
from catalog.models import AllowedAttributeValue
from core.models import City
from listings.models import Listing, ListingAttributeValue, ListingImage, ListingStatus
from tracking.json_snapshots import get_snapshot, refresh_snapshot

from .forms import CreateListingForm, ListingAttributeFieldGroup


UserModel = get_user_model()

NON_PUBLIC_STATUS_NAMES: tuple[str, ...] = ("Frozen", "Deleted")


@dataclass(slots=True)
class CreateListingAttributeSection:
    label: str
    value_type_name: str
    fields: list[Any]


@dataclass(slots=True)
class MyListingRow:
    listing_id: int
    title: str
    status_name: str
    created_at: datetime
    updated_at: datetime | None
    price_amount: Any
    view_count: int
    city_name: str
    state_code: str
    primary_image_url: str | None


@dataclass(slots=True)
class ListingDetailAttributeRow:
    label: str
    value: str


@dataclass(slots=True)
class ListingDetailContextData:
    listing: Listing
    images: list[ListingImage]
    attributes: list[ListingDetailAttributeRow]
    snapshot: Any
    can_edit: bool


ACTIVE_STATUS_NAME: str = "Active"
ADMIN_ROLE_NAME: str = "Administrator"


def build_create_listing_attribute_sections(form: CreateListingForm) -> list[CreateListingAttributeSection]:
    sections: list[CreateListingAttributeSection] = []
    for group in form.attribute_field_groups:
        sections.append(
            CreateListingAttributeSection(
                label=group.label,
                value_type_name=group.value_type_name,
                fields=[form[field_name] for field_name in group.field_names],
            )
        )
    return sections


@transaction.atomic
def create_listing_from_form(*, form: CreateListingForm, seller_user: UserModel) -> Listing:
    resolved_city: City = form.cleaned_data["resolved_city"]
    active_status: ListingStatus = get_active_listing_status()

    listing: Listing = Listing.objects.create(
        seller_user=seller_user,
        category_id=form.cleaned_data["category"],
        condition_id=form.cleaned_data["condition"],
        city=resolved_city,
        title=form.cleaned_data["title"],
        description=form.cleaned_data["description"],
        price_amount=form.cleaned_data["price_amount"],
        status=active_status,
        view_count=0,
    )

    _create_listing_attribute_values(listing=listing, attribute_groups=form.attribute_field_groups, cleaned_data=form.cleaned_data)
    _create_listing_images(listing=listing, uploaded_images=form.cleaned_data.get("images") or [])

    refresh_snapshot(int(listing.listing_id))
    return listing


def get_cities_for_state(state_id: int) -> list[str]:
    return list(
        City.objects.filter(state_id=state_id)
        .order_by("city_name")
        .values_list("city_name", flat=True)
    )


def build_my_listings_rows(user: UserModel) -> list[MyListingRow]:
    queryset: QuerySet[Listing] = (
        Listing.objects.select_related("status", "city", "city__state")
        .filter(seller_user=user)
        .order_by("-created_at", "-listing_id")
    )
    listings: list[Listing] = list(queryset)

    listing_ids: list[int] = [int(listing.listing_id) for listing in listings]
    first_images_by_listing_id: dict[int, ListingImage] = {}
    if listing_ids:
        for image in ListingImage.objects.filter(listing_id__in=listing_ids).order_by("listing_id", "display_order", "image_id"):
            first_images_by_listing_id.setdefault(int(image.listing_id), image)

    rows: list[MyListingRow] = []
    for listing in listings:
        primary_image: ListingImage | None = first_images_by_listing_id.get(int(listing.listing_id))
        rows.append(
            MyListingRow(
                listing_id=int(listing.listing_id),
                title=str(listing.title),
                status_name=str(listing.status.status_name),
                created_at=listing.created_at,
                updated_at=listing.updated_at,
                price_amount=listing.price_amount,
                view_count=int(listing.view_count),
                city_name=str(listing.city.city_name),
                state_code=str(listing.city.state.state_code),
                primary_image_url=None if primary_image is None else f"/{primary_image.image_url}",
            )
        )

    return rows


@transaction.atomic
def get_listing_detail_context_data(*, listing_id: int, viewer: Any) -> ListingDetailContextData:
    listing: Listing = (
        Listing.objects.select_related(
            "seller_user",
            "status",
            "category",
            "condition",
            "city",
            "city__state",
        )
        .filter(listing_id=listing_id)
        .first()
    )
    if listing is None:
        raise Http404("Listing not found.")

    if not can_view_listing(listing=listing, viewer=viewer):
        raise Http404("Listing not found.")

    if should_increment_view_count(listing=listing, viewer=viewer):
        Listing.objects.filter(listing_id=listing_id).update(view_count=F("view_count") + 1)
        listing.refresh_from_db(fields=["view_count"])

    snapshot = get_snapshot(int(listing.listing_id))
    images: list[ListingImage] = list(
        ListingImage.objects.filter(listing=listing).order_by("display_order", "image_id")
    )
    attribute_rows: list[ListingDetailAttributeRow] = [
        ListingDetailAttributeRow(label=attribute_key.replace("_", " ").title(), value=value)
        for attribute_key, value in snapshot.Attributes.items()
        if str(value).strip() != ""
    ]

    can_edit: bool = bool(
        getattr(viewer, "is_authenticated", False)
        and int(getattr(listing.seller_user, "id", 0)) == int(getattr(viewer, "id", 0))
        and str(listing.status.status_name).lower() == ACTIVE_STATUS_NAME.lower()
    )

    return ListingDetailContextData(
        listing=listing,
        images=images,
        attributes=attribute_rows,
        snapshot=snapshot,
        can_edit=can_edit,
    )


def can_view_listing(*, listing: Listing, viewer: Any) -> bool:
    status_name: str = str(listing.status.status_name).strip().lower()
    if status_name not in {status.lower() for status in NON_PUBLIC_STATUS_NAMES}:
        return True

    if not getattr(viewer, "is_authenticated", False):
        return False

    if int(getattr(viewer, "id", 0)) == int(listing.seller_user_id):
        return True

    return is_user_administrator(viewer)


def should_increment_view_count(*, listing: Listing, viewer: Any) -> bool:
    if not getattr(viewer, "is_authenticated", False):
        return True
    if int(getattr(viewer, "id", 0)) == int(listing.seller_user_id):
        return False
    if is_user_administrator(viewer):
        return False
    return True


def is_user_administrator(user: Any) -> bool:
    if not getattr(user, "is_authenticated", False):
        return False
    return UserRoleAssignment.objects.filter(
        user_id=int(user.id),
        role__role_name__iexact=ADMIN_ROLE_NAME,
    ).exists()


def get_active_listing_status() -> ListingStatus:
    status: ListingStatus | None = ListingStatus.objects.filter(status_name__iexact=ACTIVE_STATUS_NAME).first()
    if status is None:
        raise ListingStatus.DoesNotExist("Listing status 'Active' does not exist.")
    return status


def _create_listing_images(*, listing: Listing, uploaded_images: Iterable[Any]) -> None:
    for display_order, uploaded_image in enumerate(uploaded_images):
        suffix: str = Path(str(getattr(uploaded_image, "name", ""))).suffix.lower() or ".png"
        stored_path: str = default_storage.save(
            f"listing_images/{uuid4().hex}{suffix}",
            uploaded_image,
        )
        ListingImage.objects.create(
            listing=listing,
            image_url=stored_path,
            display_order=display_order,
        )


def _create_listing_attribute_values(
    *,
    listing: Listing,
    attribute_groups: list[ListingAttributeFieldGroup],
    cleaned_data: dict[str, Any],
) -> None:
    for group in attribute_groups:
        field_name: str = group.field_names[0]
        raw_value: Any = cleaned_data.get(field_name)
        if raw_value in {None, ""}:
            continue

        value_type_name: str = group.value_type_name.lower()

        if value_type_name in {"int", "integer"}:
            ListingAttributeValue.objects.create(
                listing=listing,
                attribute_id=group.attribute_id,
                value_int=int(raw_value),
            )
            continue

        if value_type_name == "decimal":
            ListingAttributeValue.objects.create(
                listing=listing,
                attribute_id=group.attribute_id,
                value_decimal=raw_value,
            )
            continue

        if value_type_name == "datetime":
            localized_datetime: datetime = timezone.make_aware(
                datetime.combine(raw_value, time.min),
                timezone.get_current_timezone(),
            )
            ListingAttributeValue.objects.create(
                listing=listing,
                attribute_id=group.attribute_id,
                value_datetime=localized_datetime,
            )
            continue

        if value_type_name in {"bool", "boolean"}:
            ListingAttributeValue.objects.create(
                listing=listing,
                attribute_id=group.attribute_id,
                value_bool=bool(raw_value),
            )
            continue

        allowed_value: AllowedAttributeValue | None = AllowedAttributeValue.objects.filter(
            allowed_value_id=int(raw_value),
            attribute_id=group.attribute_id,
        ).first()
        if allowed_value is None:
            continue

        ListingAttributeValue.objects.create(
            listing=listing,
            attribute_id=group.attribute_id,
            value_text=allowed_value,
        )
