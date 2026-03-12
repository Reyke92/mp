from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time
from pathlib import Path
from typing import Any, Iterable, Sequence
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied
from django.core.files.storage import default_storage
from django.db import transaction
from django.db.models import QuerySet
from django.http import Http404, QueryDict
from django.utils import timezone

from accounts.models import UserProfile
from admin_ops.models import UserRoleAssignment
from catalog.models import AllowedAttributeValue
from core.models import City
from listings.models import Listing, ListingAttributeValue, ListingImage, ListingStatus
from tracking.json_snapshots import get_snapshot, refresh_snapshot
from tracking.services import record_view

from .forms import CreateListingForm, ListingAttributeFieldGroup


UserModel = get_user_model()

ACTIVE_STATUS_NAME: str = "Active"
FROZEN_STATUS_NAME: str = "Frozen"
DELETED_STATUS_NAME: str = "Deleted"
ADMIN_ROLE_NAME: str = "Administrator"
MODERATOR_ROLE_NAME: str = "Moderator"
PRIVILEGED_ROLE_NAMES: tuple[str, ...] = (ADMIN_ROLE_NAME, MODERATOR_ROLE_NAME)
NON_PUBLIC_STATUS_NAMES: tuple[str, ...] = (FROZEN_STATUS_NAME, DELETED_STATUS_NAME)


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
    can_edit: bool


@dataclass(slots=True)
class ListingDetailAttributeRow:
    label: str
    value: str


@dataclass(slots=True)
class ListingEditorExistingImageRow:
    image_id: int
    image_url: str
    display_order: int

    def to_client_dict(self) -> dict[str, Any]:
        file_name: str = Path(self.image_url).name or f"image-{self.image_id}"
        return {
            "id": self.image_id,
            "url": f"/{self.image_url}",
            "name": file_name,
            "display_order": self.display_order,
        }


@dataclass(slots=True)
class ListingDetailImageRow:
    image_id: int
    image_url: str
    display_order: int
    alt_text: str

    def to_client_dict(self) -> dict[str, Any]:
        return {
            "id": self.image_id,
            "url": self.image_url,
            "alt": self.alt_text,
            "displayOrder": self.display_order,
        }


@dataclass(slots=True)
class ListingDetailContextData:
    listing: Listing
    attributes: list[ListingDetailAttributeRow]
    snapshot: Any
    can_edit: bool
    is_owner: bool
    is_privileged_viewer: bool
    seller_display_name: str
    seller_avatar_url: str | None
    seller_bio: str | None
    seller_member_since: datetime | None
    gallery_images: list[ListingDetailImageRow]
    visibility_message: str | None
    show_view_count: bool


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
    active_status: ListingStatus = get_listing_status_by_name(ACTIVE_STATUS_NAME)

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

    _replace_listing_attribute_values(
        listing=listing,
        attribute_groups=form.attribute_field_groups,
        cleaned_data=form.cleaned_data,
    )
    _create_listing_images(listing=listing, uploaded_images=form.cleaned_data.get("images") or [])

    refresh_snapshot(int(listing.listing_id))
    return listing


@transaction.atomic
def update_listing_from_form(
    *,
    listing: Listing,
    form: CreateListingForm,
    image_order_tokens: Sequence[str],
    removed_existing_image_ids: Sequence[int],
) -> Listing:
    if not is_listing_editable_by_owner(listing):
        raise PermissionDenied("This listing is not editable.")

    resolved_city: City = form.cleaned_data["resolved_city"]

    listing.category_id = form.cleaned_data["category"]
    listing.condition_id = form.cleaned_data["condition"]
    listing.city = resolved_city
    listing.title = form.cleaned_data["title"]
    listing.description = form.cleaned_data["description"]
    listing.price_amount = form.cleaned_data["price_amount"]
    listing.save(
        update_fields=[
            "category",
            "condition",
            "city",
            "title",
            "description",
            "price_amount",
        ]
    )

    _replace_listing_attribute_values(
        listing=listing,
        attribute_groups=form.attribute_field_groups,
        cleaned_data=form.cleaned_data,
    )
    _sync_listing_images(
        listing=listing,
        uploaded_images=form.cleaned_data.get("images") or [],
        image_order_tokens=image_order_tokens,
        removed_existing_image_ids=removed_existing_image_ids,
    )

    refresh_snapshot(int(listing.listing_id))
    return listing


@transaction.atomic
def mark_listing_deleted_by_owner(*, listing: Listing, owner_user: UserModel) -> Listing:
    if int(listing.seller_user_id) != int(owner_user.id):
        raise PermissionDenied("You cannot delete another user's listing.")
    if get_listing_status_name(listing) == FROZEN_STATUS_NAME.lower():
        raise PermissionDenied("Frozen listings cannot be deleted by the seller.")
    if get_listing_status_name(listing) == DELETED_STATUS_NAME.lower():
        return listing

    deleted_status: ListingStatus = get_listing_status_by_name(DELETED_STATUS_NAME)
    listing.status = deleted_status
    listing.save(update_fields=["status"])
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
        .exclude(status__status_name__iexact=DELETED_STATUS_NAME)
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
                can_edit=is_listing_editable_by_owner(listing),
            )
        )

    return rows


@transaction.atomic
def get_listing_detail_context_data(*, listing_id: int, viewer: Any) -> ListingDetailContextData:
    listing: Listing = get_listing_by_id_or_404(listing_id)

    if not can_view_listing(listing=listing, viewer=viewer):
        raise Http404("Listing not found.")

    listing.view_count = record_view(int(listing.listing_id), viewer)

    snapshot = get_snapshot(int(listing.listing_id))
    attribute_rows: list[ListingDetailAttributeRow] = [
        ListingDetailAttributeRow(label=attribute_key.replace("_", " ").title(), value=value)
        for attribute_key, value in snapshot.Attributes.items()
        if str(value).strip() != ""
    ]

    viewer_is_authenticated: bool = bool(getattr(viewer, "is_authenticated", False))
    viewer_id: int = int(getattr(viewer, "id", -1)) if viewer_is_authenticated else -1
    is_owner: bool = viewer_is_authenticated and viewer_id == int(listing.seller_user_id)
    is_privileged_viewer: bool = is_user_privileged(viewer)
    can_edit: bool = is_owner and is_listing_editable_by_owner(listing)

    seller_profile: UserProfile | None = _get_user_profile_or_none(listing.seller_user)
    gallery_images: list[ListingDetailImageRow] = [
        ListingDetailImageRow(
            image_id=int(image.image_id),
            image_url=f"/{image.image_url}",
            display_order=int(image.display_order),
            alt_text=f"{listing.title} image {index + 1}",
        )
        for index, image in enumerate(
            ListingImage.objects.filter(listing=listing).order_by("display_order", "image_id")
        )
    ]

    visibility_message: str | None = build_listing_visibility_message(
        listing=listing,
        is_owner=is_owner,
        is_privileged_viewer=is_privileged_viewer,
    )

    return ListingDetailContextData(
        listing=listing,
        attributes=attribute_rows,
        snapshot=snapshot,
        can_edit=can_edit,
        is_owner=is_owner,
        is_privileged_viewer=is_privileged_viewer,
        seller_display_name=_build_user_display_name(listing.seller_user),
        seller_avatar_url=_get_user_avatar_url(seller_profile),
        seller_bio=None if seller_profile is None or not seller_profile.bio else str(seller_profile.bio).strip(),
        seller_member_since=getattr(listing.seller_user, "date_joined", None),
        gallery_images=gallery_images,
        visibility_message=visibility_message,
        show_view_count=can_user_view_listing_view_count(listing=listing, viewer=viewer),
    )


def build_listing_form_initial(listing: Listing) -> dict[str, Any]:
    initial_data: dict[str, Any] = {
        "title": str(listing.title),
        "price_amount": listing.price_amount,
        "category": int(listing.category_id),
        "condition": int(listing.condition_id),
        "city_name": str(listing.city.city_name),
        "state": int(listing.city.state_id),
        "description": str(listing.description or ""),
    }

    attribute_values: Iterable[ListingAttributeValue] = (
        ListingAttributeValue.objects.select_related("attribute", "attribute__value_type", "value_text")
        .filter(listing=listing)
    )
    for attribute_value in attribute_values:
        field_name: str = f"attr_{int(attribute_value.attribute_id)}_value"
        value_type_name: str = str(attribute_value.attribute.value_type.value_type_name).strip().lower()

        if value_type_name in {"int", "integer"}:
            initial_data[field_name] = attribute_value.value_int
        elif value_type_name == "decimal":
            initial_data[field_name] = attribute_value.value_decimal
        elif value_type_name == "datetime":
            initial_data[field_name] = _datetime_to_local_date(attribute_value.value_datetime)
        elif value_type_name in {"bool", "boolean"}:
            initial_data[field_name] = attribute_value.value_bool
        else:
            initial_data[field_name] = None if attribute_value.value_text_id is None else int(attribute_value.value_text_id)

    return initial_data


def build_existing_listing_image_rows(listing: Listing) -> list[ListingEditorExistingImageRow]:
    return [
        ListingEditorExistingImageRow(
            image_id=int(image.image_id),
            image_url=str(image.image_url),
            display_order=int(image.display_order),
        )
        for image in ListingImage.objects.filter(listing=listing).order_by("display_order", "image_id")
    ]


def build_existing_listing_images_payload(
    *,
    listing: Listing,
    post_data: QueryDict | None = None,
) -> list[dict[str, Any]]:
    rows_by_id: dict[int, ListingEditorExistingImageRow] = {
        row.image_id: row for row in build_existing_listing_image_rows(listing)
    }
    if post_data is None:
        return [row.to_client_dict() for row in rows_by_id.values()]

    removed_ids: set[int] = {value for value in parse_image_id_list(post_data.getlist("removed_existing_image_ids"))}
    ordered_payload: list[dict[str, Any]] = []
    ordered_seen_ids: set[int] = set()

    for token in post_data.getlist("image_order"):
        kind, image_id = parse_existing_image_token(token)
        if kind != "existing" or image_id is None or image_id in removed_ids:
            continue
        row: ListingEditorExistingImageRow | None = rows_by_id.get(image_id)
        if row is None:
            continue
        ordered_payload.append(row.to_client_dict())
        ordered_seen_ids.add(image_id)

    for image_id, row in rows_by_id.items():
        if image_id in removed_ids or image_id in ordered_seen_ids:
            continue
        ordered_payload.append(row.to_client_dict())

    return ordered_payload


def get_listing_by_id_or_404(listing_id: int) -> Listing:
    listing: Listing | None = (
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
    return listing


def get_owner_listing_for_edit_or_403(*, listing_id: int, owner_user: UserModel) -> Listing:
    listing: Listing = get_listing_by_id_or_404(listing_id)
    if int(listing.seller_user_id) != int(owner_user.id):
        raise PermissionDenied("You cannot edit another user's listing.")
    if not is_listing_editable_by_owner(listing):
        raise PermissionDenied("This listing cannot be edited.")
    return listing


def can_view_listing(*, listing: Listing, viewer: Any) -> bool:
    status_name: str = get_listing_status_name(listing)
    if status_name not in {status.lower() for status in NON_PUBLIC_STATUS_NAMES}:
        return True

    if not getattr(viewer, "is_authenticated", False):
        return False

    if is_user_privileged(viewer):
        return True

    if status_name == FROZEN_STATUS_NAME.lower() and int(getattr(viewer, "id", -1)) == int(listing.seller_user_id):
        return True

    return False


def can_user_view_listing_view_count(*, listing: Listing, viewer: Any) -> bool:
    if not getattr(viewer, "is_authenticated", False):
        return False
    if int(getattr(viewer, "id", -1)) == int(listing.seller_user_id):
        return True
    return is_user_administrator(viewer)


def build_listing_visibility_message(
    *,
    listing: Listing,
    is_owner: bool,
    is_privileged_viewer: bool,
) -> str | None:
    status_name: str = str(listing.status.status_name).strip()
    normalized_status_name: str = status_name.lower()
    if normalized_status_name not in {status.lower() for status in NON_PUBLIC_STATUS_NAMES}:
        return None

    if is_privileged_viewer:
        return (
            f"This listing is currently marked as {status_name.lower()} and is visible to you because you have staff access."
        )
    if is_owner and normalized_status_name == FROZEN_STATUS_NAME.lower():
        return "This listing is frozen. You can review it here, but only staff can restore it to an editable public state."
    return None


def is_user_administrator(user: Any) -> bool:
    return _user_has_any_privileged_role(user, role_names=(ADMIN_ROLE_NAME,))


def is_user_privileged(user: Any) -> bool:
    return _user_has_any_privileged_role(user, role_names=PRIVILEGED_ROLE_NAMES)


def get_active_listing_status() -> ListingStatus:
    return get_listing_status_by_name(ACTIVE_STATUS_NAME)


def get_listing_status_by_name(status_name: str) -> ListingStatus:
    status: ListingStatus | None = ListingStatus.objects.filter(status_name__iexact=status_name).first()
    if status is None:
        raise ListingStatus.DoesNotExist(f"Listing status '{status_name}' does not exist.")
    return status


def is_listing_editable_by_owner(listing: Listing) -> bool:
    return get_listing_status_name(listing) == ACTIVE_STATUS_NAME.lower()


def get_listing_status_name(listing: Listing) -> str:
    return str(listing.status.status_name).strip().lower()


def parse_image_id_list(raw_values: Sequence[Any]) -> list[int]:
    parsed_ids: list[int] = []
    for raw_value in raw_values:
        if raw_value in {None, ""}:
            continue
        try:
            parsed_ids.append(int(raw_value))
        except (TypeError, ValueError):
            continue
    return parsed_ids


def parse_existing_image_token(token: str) -> tuple[str, int | None]:
    parts: list[str] = str(token).split(":", 1)
    if len(parts) != 2:
        return "", None
    kind: str = parts[0].strip().lower()
    try:
        identifier: int = int(parts[1])
    except (TypeError, ValueError):
        return kind, None
    return kind, identifier


def _user_has_any_privileged_role(user: Any, *, role_names: Sequence[str]) -> bool:
    if not getattr(user, "is_authenticated", False):
        return False
    return UserRoleAssignment.objects.filter(
        user_id=int(user.id),
        role__role_name__in=tuple(role_names),
    ).exists()


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


def _replace_listing_attribute_values(
    *,
    listing: Listing,
    attribute_groups: list[ListingAttributeFieldGroup],
    cleaned_data: dict[str, Any],
) -> None:
    ListingAttributeValue.objects.filter(listing=listing).delete()
    _create_listing_attribute_values(
        listing=listing,
        attribute_groups=attribute_groups,
        cleaned_data=cleaned_data,
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
            datetime_value: Any = raw_value
            if isinstance(datetime_value, date) and not isinstance(datetime_value, datetime):
                datetime_value = timezone.make_aware(
                    datetime.combine(datetime_value, time.min),
                    timezone.get_current_timezone(),
                )
            ListingAttributeValue.objects.create(
                listing=listing,
                attribute_id=group.attribute_id,
                value_datetime=datetime_value,
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


def _sync_listing_images(
    *,
    listing: Listing,
    uploaded_images: Sequence[Any],
    image_order_tokens: Sequence[str],
    removed_existing_image_ids: Sequence[int],
) -> None:
    existing_images_by_id: dict[int, ListingImage] = {
        int(image.image_id): image
        for image in ListingImage.objects.filter(listing=listing).order_by("display_order", "image_id")
    }
    removed_id_set: set[int] = set(removed_existing_image_ids)

    for removed_image_id in removed_id_set:
        image: ListingImage | None = existing_images_by_id.get(removed_image_id)
        if image is None:
            continue
        _delete_listing_image(image)
        existing_images_by_id.pop(removed_image_id, None)

    if image_order_tokens:
        tokens_to_apply: list[str] = list(image_order_tokens)
    else:
        tokens_to_apply = [f"existing:{image_id}" for image_id in existing_images_by_id.keys()]
        tokens_to_apply.extend(f"new:{index}" for index in range(len(uploaded_images)))

    remaining_existing_images: dict[int, ListingImage] = dict(existing_images_by_id)
    temp_display_order_start: int = len(tokens_to_apply) + len(remaining_existing_images) + 1000
    temp_offset: int = 0
    for image in remaining_existing_images.values():
        image.display_order = temp_display_order_start + temp_offset
        image.save(update_fields=["display_order"])
        temp_offset += 1

    new_files: list[Any] = list(uploaded_images)

    for final_display_order, token in enumerate(tokens_to_apply):
        kind, identifier = parse_existing_image_token(token)
        if identifier is None:
            continue

        if kind == "existing":
            image = remaining_existing_images.get(identifier)
            if image is None:
                continue
            image.display_order = final_display_order
            image.save(update_fields=["display_order"])
            continue

        if kind != "new":
            continue
        if identifier < 0 or identifier >= len(new_files):
            continue

        uploaded_image = new_files[identifier]
        suffix: str = Path(str(getattr(uploaded_image, "name", ""))).suffix.lower() or ".png"
        stored_path: str = default_storage.save(
            f"listing_images/{uuid4().hex}{suffix}",
            uploaded_image,
        )
        ListingImage.objects.create(
            listing=listing,
            image_url=stored_path,
            display_order=final_display_order,
        )

    used_existing_ids: set[int] = {
        image_id
        for token in tokens_to_apply
        for kind, image_id in [parse_existing_image_token(token)]
        if kind == "existing" and image_id is not None
    }
    for image_id, image in remaining_existing_images.items():
        if image_id in used_existing_ids:
            continue
        _delete_listing_image(image)


def _delete_listing_image(image: ListingImage) -> None:
    image_path: str = str(image.image_url)
    image.delete()
    if image_path != "":
        default_storage.delete(image_path)


def _datetime_to_local_date(value: datetime | None) -> date | None:
    if value is None:
        return None
    localized_value: datetime = timezone.localtime(value) if timezone.is_aware(value) else value
    return localized_value.date()


def _get_user_profile_or_none(user: UserModel) -> UserProfile | None:
    try:
        return UserProfile.objects.select_related("city", "city__state").get(user=user)
    except UserProfile.DoesNotExist:
        return None


def _build_user_display_name(user: UserModel) -> str:
    full_name: str = user.get_full_name().strip()
    if full_name != "":
        return full_name
    username: str = str(getattr(user, "username", "")).strip()
    if username == "":
        return "Marketplace seller"
    if "@" in username:
        return username.split("@", 1)[0]
    return username


def _get_user_avatar_url(profile: UserProfile | None) -> str | None:
    if profile is None:
        return None
    avatar_name: str = str(getattr(profile.avatar, "name", "")).strip()
    if avatar_name == "":
        return None
    return f"/{avatar_name}"
