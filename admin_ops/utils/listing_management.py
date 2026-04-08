from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Iterable
from urllib.parse import urlencode

from django.core.paginator import Page, Paginator
from django.db import transaction
from django.db.models import Case, IntegerField, Q, QuerySet, Value, When
from django.db.models.functions import Coalesce, Lower
from django.urls import reverse

from admin_ops.forms import (
    LISTING_SORT_NEWEST_VALUE,
    LISTING_SORT_OLDEST_VALUE,
    LISTING_SORT_SELLER_ASC_VALUE,
    LISTING_SORT_SELLER_DESC_VALUE,
    LISTING_SORT_STATUS_ASC_VALUE,
    LISTING_SORT_STATUS_DESC_VALUE,
    LISTING_SORT_TITLE_ASC_VALUE,
    LISTING_SORT_TITLE_DESC_VALUE,
    LISTING_SORT_VIEWS_ASC_VALUE,
    LISTING_SORT_VIEWS_DESC_VALUE,
    LISTING_STATUS_ACTIVE_VALUE,
    LISTING_STATUS_DELETED_VALUE,
    LISTING_STATUS_FROZEN_VALUE,
)
from admin_ops.models import AdministrationAction, AdministrationActionType
from admin_ops.utils.roles import is_user_administrator
from catalog.models import Category
from listings.models import Listing, ListingImage, ListingStatus
from tracking.json_snapshots import refresh_snapshot


PAGE_SIZE: int = 20
ACTIVE_STATUS_NAME: str = "Active"
FROZEN_STATUS_NAME: str = "Frozen"
DELETED_STATUS_NAME: str = "Deleted"
FREEZE_LISTING_ACTION_TYPE_NAME: str = "FreezeListing"
UNFREEZE_LISTING_ACTION_TYPE_NAME: str = "UnfreezeListing"
USER_EMAIL_SOURCE_FIELD_NAME: str = "username"


@dataclass(frozen=True)
class ManagedListingRow:
    listing_id: int
    title: str
    seller_first_name: str
    seller_last_name: str
    seller_email_address: str
    listing_detail_url: str
    seller_profile_url: str
    status_label: str
    status_variant: str
    created_at: Any
    select_url: str
    selected_card_url: str
    is_selected: bool


@dataclass(frozen=True)
class SelectedManagedListing:
    listing_id: int
    title: str
    seller_first_name: str
    seller_last_name: str
    seller_email_address: str
    listing_detail_url: str
    seller_profile_url: str
    status_label: str
    status_variant: str
    category_label: str
    price_amount: Decimal
    view_count: int
    primary_image_url: str | None
    can_freeze: bool
    can_unfreeze: bool


@dataclass(frozen=True)
class ListingManagementPageContext:
    page_obj: Page[Any]
    table_rows: list[ManagedListingRow]
    selected_listing: SelectedManagedListing | None
    total_listing_count: int
    filter_summary_parts: list[str]
    preserved_query_string_without_page: str
    preserved_query_string_without_selected: str
    preserved_query_items: list[tuple[str, str]]
    selected_listing_id: int | None
    page_range: list[int | str]


@dataclass(frozen=True)
class SelectedListingCardContext:
    selected_listing: SelectedManagedListing | None
    preserved_query_items: list[tuple[str, str]]
    page_number: int


class ListingManagementActionError(Exception):
    """Raised when a listing-management action cannot be completed."""


class ListingManagementPermissionError(Exception):
    """Raised when a listing-management action is not permitted."""


class UnsupportedListingManagementActionError(Exception):
    """Raised when an unknown listing-management action is submitted."""



def build_listing_management_page_context(
    *,
    search_query: str,
    listing_status: str,
    category_id: int | None,
    sort_by: str,
    page_number: int,
    selected_listing_id: int | None,
    base_url: str,
) -> ListingManagementPageContext:
    normalized_query: str = search_query.strip()
    queryset: QuerySet[Listing] = _build_listing_management_queryset(
        search_query=normalized_query,
        listing_status=listing_status,
        category_id=category_id,
    )
    queryset = _apply_sort(queryset=queryset, sort_by=sort_by)

    paginator: Paginator = Paginator(queryset, PAGE_SIZE)
    page_obj: Page[Any] = paginator.get_page(page_number)

    preserved_query_items_without_page: list[tuple[str, str]] = _build_preserved_query_items(
        search_query=normalized_query,
        listing_status=listing_status,
        category_id=category_id,
        sort_by=sort_by,
        selected_listing_id=selected_listing_id,
        exclude_keys={"page"},
    )
    preserved_query_items_without_selected: list[tuple[str, str]] = _build_preserved_query_items(
        search_query=normalized_query,
        listing_status=listing_status,
        category_id=category_id,
        sort_by=sort_by,
        selected_listing_id=selected_listing_id,
        exclude_keys={"selected"},
    )

    selected_listing: SelectedManagedListing | None = _resolve_selected_listing(
        queryset=queryset,
        page_obj=page_obj,
        selected_listing_id=selected_listing_id,
    )
    resolved_selected_listing_id: int | None = selected_listing.listing_id if selected_listing is not None else None

    table_rows: list[ManagedListingRow] = []
    for listing in page_obj.object_list:
        current_listing_id: int = int(listing.listing_id)
        table_rows.append(
            ManagedListingRow(
                listing_id=current_listing_id,
                title=str(listing.title),
                seller_first_name=_get_display_first_name(listing.seller_user),
                seller_last_name=_get_display_last_name(listing.seller_user),
                seller_email_address=str(getattr(listing.seller_user, USER_EMAIL_SOURCE_FIELD_NAME, "")),
                listing_detail_url=reverse("listing_detail", kwargs={"listing_id": current_listing_id}),
                seller_profile_url=reverse("view_profile", kwargs={"id": int(listing.seller_user_id)}),
                status_label=_normalize_status_label(getattr(listing.status, "status_name", "")),
                status_variant=_normalize_status_variant(getattr(listing.status, "status_name", "")),
                created_at=listing.created_at,
                select_url=_build_selection_url(
                    base_url=base_url,
                    search_query=normalized_query,
                    listing_status=listing_status,
                    category_id=category_id,
                    sort_by=sort_by,
                    selected_listing_id=current_listing_id,
                    page_number=page_obj.number,
                ),
                selected_card_url=_build_selected_card_url(
                    listing_id=current_listing_id,
                    search_query=normalized_query,
                    listing_status=listing_status,
                    category_id=category_id,
                    sort_by=sort_by,
                    page_number=page_obj.number,
                ),
                is_selected=current_listing_id == resolved_selected_listing_id,
            )
        )

    if selected_listing is not None:
        selected_image: ListingImage | None = _get_first_images_by_listing_id([selected_listing.listing_id]).get(selected_listing.listing_id)
        selected_listing = _hydrate_selected_listing(selected_listing=selected_listing, image=selected_image)

    filter_summary_parts: list[str] = _build_filter_summary_parts(
        search_query=normalized_query,
        listing_status=listing_status,
        category_id=category_id,
        total_listing_count=paginator.count,
    )

    page_range: list[int | str] = list(paginator.get_elided_page_range(number=page_obj.number, on_each_side=1, on_ends=1))

    return ListingManagementPageContext(
        page_obj=page_obj,
        table_rows=table_rows,
        selected_listing=selected_listing,
        total_listing_count=paginator.count,
        filter_summary_parts=filter_summary_parts,
        preserved_query_string_without_page=urlencode(preserved_query_items_without_page, doseq=True),
        preserved_query_string_without_selected=urlencode(preserved_query_items_without_selected, doseq=True),
        preserved_query_items=preserved_query_items_without_selected,
        selected_listing_id=resolved_selected_listing_id,
        page_range=page_range,
    )





def build_selected_listing_card_context(
    *,
    listing_id: int,
    search_query: str,
    listing_status: str,
    category_id: int | None,
    sort_by: str,
    page_number: int,
) -> SelectedListingCardContext:
    normalized_query: str = search_query.strip()
    queryset: QuerySet[Listing] = _build_listing_management_queryset(
        search_query=normalized_query,
        listing_status=listing_status,
        category_id=category_id,
    )
    queryset = _apply_sort(queryset=queryset, sort_by=sort_by)

    selected_listing: SelectedManagedListing | None = _resolve_selected_listing_object(
        queryset=queryset,
        selected_listing_id=listing_id,
    )
    if selected_listing is not None:
        selected_image: ListingImage | None = _get_first_images_by_listing_id([selected_listing.listing_id]).get(selected_listing.listing_id)
        selected_listing = _hydrate_selected_listing(selected_listing=selected_listing, image=selected_image)

    preserved_query_items: list[tuple[str, str]] = _build_preserved_query_items(
        search_query=normalized_query,
        listing_status=listing_status,
        category_id=category_id,
        sort_by=sort_by,
        selected_listing_id=listing_id,
        exclude_keys={"selected"},
    )

    return SelectedListingCardContext(
        selected_listing=selected_listing,
        preserved_query_items=preserved_query_items,
        page_number=page_number,
    )


def perform_listing_management_action(
    *,
    requesting_user_id: int,
    target_listing_id: int,
    action_name: str,
) -> str:
    if action_name == "freeze_listing":
        set_listing_frozen_state(
            requesting_user_id=requesting_user_id,
            listing_id=target_listing_id,
            should_freeze=True,
        )
        return "Listing was frozen successfully."

    if action_name == "unfreeze_listing":
        set_listing_frozen_state(
            requesting_user_id=requesting_user_id,
            listing_id=target_listing_id,
            should_freeze=False,
        )
        return "Listing was unfrozen successfully."

    raise UnsupportedListingManagementActionError("Unsupported listing-management action.")



def is_listing_frozen(listing: Listing | int) -> bool:
    listing_id: int = int(listing.listing_id) if isinstance(listing, Listing) else int(listing)
    return Listing.objects.filter(
        listing_id=listing_id,
        status__status_name__iexact=FROZEN_STATUS_NAME,
    ).exists()



def set_listing_frozen_state(
    *,
    requesting_user_id: int,
    listing_id: int,
    should_freeze: bool,
) -> Listing:
    with transaction.atomic():
        if not is_user_administrator(requesting_user_id):
            raise ListingManagementPermissionError("Only Administrators may freeze or unfreeze listings.")

        Listing.objects.select_for_update().only("listing_id").get(listing_id=listing_id)
        listing: Listing = (
            Listing.objects.select_for_update()
            .select_related("status")
            .get(listing_id=listing_id)
        )
        current_status_name: str = _normalize_status_label(getattr(listing.status, "status_name", ""))

        if should_freeze:
            if current_status_name.lower() == FROZEN_STATUS_NAME.lower():
                raise ListingManagementActionError("That listing is already frozen.")
            next_status_name: str = FROZEN_STATUS_NAME
            action_type_name: str = FREEZE_LISTING_ACTION_TYPE_NAME
        else:
            if current_status_name.lower() != FROZEN_STATUS_NAME.lower():
                raise ListingManagementActionError("Only frozen listings can be unfrozen.")
            next_status_name = ACTIVE_STATUS_NAME
            action_type_name = UNFREEZE_LISTING_ACTION_TYPE_NAME

        next_status: ListingStatus = ListingStatus.objects.get(status_name__iexact=next_status_name)
        listing.status = next_status
        listing.save(update_fields=["status"])

        _log_listing_state_change(
            requesting_user_id=requesting_user_id,
            listing_id=int(listing.listing_id),
            target_status_name=next_status_name,
            action_type_name=action_type_name,
        )

    # Refresh the listing snapshot so public/search-facing caches stay in sync.
    refresh_snapshot(int(listing.listing_id))
    return listing





def _build_listing_management_queryset(
    *,
    search_query: str,
    listing_status: str,
    category_id: int | None,
) -> QuerySet[Listing]:
    seller_email_field: str = f"seller_user__{USER_EMAIL_SOURCE_FIELD_NAME}"

    queryset: QuerySet[Listing] = (
        Listing.objects.select_related("seller_user", "status", "category", "category__parent_category")
        .annotate(seller_first_name_sort=Lower(Coalesce("seller_user__first_name", Value(""))))
        .annotate(seller_last_name_sort=Lower(Coalesce("seller_user__last_name", Value(""))))
        .annotate(seller_email_sort=Lower(Coalesce(seller_email_field, Value(""))))
        .annotate(title_sort=Lower(Coalesce("title", Value(""))))
        .annotate(status_name_sort=Lower(Coalesce("status__status_name", Value(""))))
        .annotate(
            status_sort=Case(
                When(status__status_name__iexact=ACTIVE_STATUS_NAME, then=Value(0)),
                When(status__status_name__iexact=FROZEN_STATUS_NAME, then=Value(1)),
                When(status__status_name__iexact=DELETED_STATUS_NAME, then=Value(2)),
                default=Value(9),
                output_field=IntegerField(),
            )
        )
    )

    if search_query != "":
        queryset = queryset.filter(
            Q(**{f"{seller_email_field}__icontains": search_query})
            | Q(title__icontains=search_query)
            | Q(description__icontains=search_query)
        )

    if listing_status == LISTING_STATUS_ACTIVE_VALUE:
        queryset = queryset.filter(status__status_name__iexact=ACTIVE_STATUS_NAME)
    elif listing_status == LISTING_STATUS_FROZEN_VALUE:
        queryset = queryset.filter(status__status_name__iexact=FROZEN_STATUS_NAME)
    elif listing_status == LISTING_STATUS_DELETED_VALUE:
        queryset = queryset.filter(status__status_name__iexact=DELETED_STATUS_NAME)

    if category_id is not None:
        queryset = queryset.filter(category_id=category_id, category__parent_category__isnull=False)

    return queryset


def _log_listing_state_change(
    *,
    requesting_user_id: int,
    listing_id: int,
    target_status_name: str,
    action_type_name: str,
) -> AdministrationAction:
    action_type: AdministrationActionType = AdministrationActionType.objects.get(
        action_type_name__iexact=action_type_name,
    )
    return AdministrationAction.objects.create(
        actor_user_id=requesting_user_id,
        action_type=action_type,
        listing_id=listing_id,
        notes=f"Listing status changed to {target_status_name}.",
    )



def _apply_sort(*, queryset: QuerySet[Listing], sort_by: str) -> QuerySet[Listing]:
    if sort_by == LISTING_SORT_OLDEST_VALUE:
        return queryset.order_by("created_at", "listing_id")
    if sort_by == LISTING_SORT_TITLE_ASC_VALUE:
        return queryset.order_by("title_sort", "listing_id")
    if sort_by == LISTING_SORT_TITLE_DESC_VALUE:
        return queryset.order_by("-title_sort", "-listing_id")
    if sort_by == LISTING_SORT_SELLER_ASC_VALUE:
        return queryset.order_by("seller_email_sort", "title_sort", "listing_id")
    if sort_by == LISTING_SORT_SELLER_DESC_VALUE:
        return queryset.order_by("-seller_email_sort", "title_sort", "-listing_id")
    if sort_by == LISTING_SORT_STATUS_ASC_VALUE:
        return queryset.order_by("status_sort", "-created_at", "-listing_id")
    if sort_by == LISTING_SORT_STATUS_DESC_VALUE:
        return queryset.order_by("-status_sort", "-created_at", "-listing_id")
    if sort_by == LISTING_SORT_VIEWS_ASC_VALUE:
        return queryset.order_by("view_count", "-created_at", "-listing_id")
    if sort_by == LISTING_SORT_VIEWS_DESC_VALUE:
        return queryset.order_by("-view_count", "-created_at", "-listing_id")

    return queryset.order_by("-created_at", "-listing_id")



def _resolve_selected_listing(
    *,
    queryset: QuerySet[Listing],
    page_obj: Page[Any],
    selected_listing_id: int | None,
) -> SelectedManagedListing | None:
    selected_listing: SelectedManagedListing | None = None

    if selected_listing_id is not None:
        selected_listing = _resolve_selected_listing_object(
            queryset=queryset,
            selected_listing_id=selected_listing_id,
        )

    if selected_listing is not None:
        return selected_listing

    selected_listing_object: Listing | None = page_obj.object_list[0] if page_obj.object_list else None
    if selected_listing_object is None:
        return None

    return _build_selected_listing_from_listing(selected_listing_object)



def _resolve_selected_listing_object(
    *,
    queryset: QuerySet[Listing],
    selected_listing_id: int,
) -> SelectedManagedListing | None:
    selected_listing_object: Listing | None = queryset.filter(listing_id=selected_listing_id).first()
    if selected_listing_object is None:
        return None

    return _build_selected_listing_from_listing(selected_listing_object)



def _build_selected_listing_from_listing(listing: Listing) -> SelectedManagedListing:
    status_label: str = _normalize_status_label(getattr(listing.status, "status_name", ""))
    listing_id: int = int(listing.listing_id)
    category_label: str = _build_category_label(listing.category)

    return SelectedManagedListing(
        listing_id=listing_id,
        title=str(listing.title),
        seller_first_name=_get_display_first_name(listing.seller_user),
        seller_last_name=_get_display_last_name(listing.seller_user),
        seller_email_address=str(getattr(listing.seller_user, USER_EMAIL_SOURCE_FIELD_NAME, "")),
        listing_detail_url=reverse("listing_detail", kwargs={"listing_id": listing_id}),
        seller_profile_url=reverse("view_profile", kwargs={"id": int(listing.seller_user_id)}),
        status_label=status_label,
        status_variant=_normalize_status_variant(status_label),
        category_label=category_label,
        price_amount=listing.price_amount,
        view_count=int(listing.view_count),
        primary_image_url=None,
        can_freeze=status_label.lower() != FROZEN_STATUS_NAME.lower(),
        can_unfreeze=status_label.lower() == FROZEN_STATUS_NAME.lower(),
    )



def _hydrate_selected_listing(
    *,
    selected_listing: SelectedManagedListing,
    image: ListingImage | None,
) -> SelectedManagedListing:
    primary_image_url: str | None = None
    if image is not None:
        primary_image_url = f"/{str(image.image_url).lstrip('/')}"

    return SelectedManagedListing(
        listing_id=selected_listing.listing_id,
        title=selected_listing.title,
        seller_first_name=selected_listing.seller_first_name,
        seller_last_name=selected_listing.seller_last_name,
        seller_email_address=selected_listing.seller_email_address,
        listing_detail_url=selected_listing.listing_detail_url,
        seller_profile_url=selected_listing.seller_profile_url,
        status_label=selected_listing.status_label,
        status_variant=selected_listing.status_variant,
        category_label=selected_listing.category_label,
        price_amount=selected_listing.price_amount,
        view_count=selected_listing.view_count,
        primary_image_url=primary_image_url,
        can_freeze=selected_listing.can_freeze,
        can_unfreeze=selected_listing.can_unfreeze,
    )



def _get_first_images_by_listing_id(listing_ids: Iterable[int]) -> dict[int, ListingImage]:
    normalized_listing_ids: list[int] = [int(listing_id) for listing_id in listing_ids]
    if not normalized_listing_ids:
        return {}

    first_images_by_listing_id: dict[int, ListingImage] = {}
    images: QuerySet[ListingImage] = ListingImage.objects.filter(listing_id__in=normalized_listing_ids).order_by(
        "listing_id",
        "display_order",
        "image_id",
    )
    for image in images:
        first_images_by_listing_id.setdefault(int(image.listing_id), image)
    return first_images_by_listing_id



def _build_selected_card_url(
    *,
    listing_id: int,
    search_query: str,
    listing_status: str,
    category_id: int | None,
    sort_by: str,
    page_number: int,
) -> str:
    query_items: list[tuple[str, str]] = _build_preserved_query_items(
        search_query=search_query,
        listing_status=listing_status,
        category_id=category_id,
        sort_by=sort_by,
        selected_listing_id=listing_id,
        exclude_keys={"selected"},
    )
    query_items.append(("page", str(page_number)))
    base_url: str = reverse("listing_management_selected_card", kwargs={"listing_id": listing_id})
    if not query_items:
        return base_url
    return f"{base_url}?{urlencode(query_items, doseq=True)}"



def _build_selection_url(
    *,
    base_url: str,
    search_query: str,
    listing_status: str,
    category_id: int | None,
    sort_by: str,
    selected_listing_id: int,
    page_number: int,
) -> str:
    query_items: list[tuple[str, str]] = _build_preserved_query_items(
        search_query=search_query,
        listing_status=listing_status,
        category_id=category_id,
        sort_by=sort_by,
        selected_listing_id=selected_listing_id,
        exclude_keys=set(),
    )
    query_items.append(("page", str(page_number)))
    return f"{base_url}?{urlencode(query_items, doseq=True)}"



def _build_preserved_query_items(
    *,
    search_query: str,
    listing_status: str,
    category_id: int | None,
    sort_by: str,
    selected_listing_id: int | None,
    exclude_keys: set[str],
) -> list[tuple[str, str]]:
    query_items: list[tuple[str, str]] = []
    if "search_query" not in exclude_keys and search_query != "":
        query_items.append(("search_query", search_query))
    if "listing_status" not in exclude_keys and listing_status != "":
        query_items.append(("listing_status", listing_status))
    if "category_id" not in exclude_keys and category_id is not None:
        query_items.append(("category_id", str(category_id)))
    if "sort_by" not in exclude_keys and sort_by != "":
        query_items.append(("sort_by", sort_by))
    if "selected" not in exclude_keys and selected_listing_id is not None:
        query_items.append(("selected", str(selected_listing_id)))
    return query_items



def _build_filter_summary_parts(
    *,
    search_query: str,
    listing_status: str,
    category_id: int | None,
    total_listing_count: int,
) -> list[str]:
    summary_parts: list[str] = [f"{total_listing_count} listing{'s' if total_listing_count != 1 else ''}"]

    if search_query != "":
        summary_parts.append(f"search: “{search_query}”")
    if listing_status == LISTING_STATUS_ACTIVE_VALUE:
        summary_parts.append("status: Active")
    elif listing_status == LISTING_STATUS_FROZEN_VALUE:
        summary_parts.append("status: Frozen")
    elif listing_status == LISTING_STATUS_DELETED_VALUE:
        summary_parts.append("status: Deleted")

    if category_id is not None:
        category: Category | None = Category.objects.select_related("parent_category").filter(category_id=category_id).first()
        if category is not None:
            summary_parts.append(f"category: {_build_category_label(category)}")

    return summary_parts



def _build_category_label(category: Category) -> str:
    category_name: str = str(category.name).strip()
    if category.parent_category_id is None or category.parent_category is None:
        return category_name
    parent_name: str = str(category.parent_category.name).strip()
    return f"{parent_name} / {category_name}"



def _normalize_status_label(raw_status_name: Any) -> str:
    status_name: str = str(raw_status_name or "").strip()
    return status_name if status_name != "" else "Unknown"



def _normalize_status_variant(raw_status_name: Any) -> str:
    status_name: str = _normalize_status_label(raw_status_name).lower()
    if status_name == ACTIVE_STATUS_NAME.lower():
        return "active"
    if status_name == FROZEN_STATUS_NAME.lower():
        return "frozen"
    if status_name == DELETED_STATUS_NAME.lower():
        return "deleted"
    return "deleted"



def _get_display_first_name(user: Any) -> str:
    first_name: str = str(getattr(user, "first_name", "") or "").strip()
    if first_name != "":
        return first_name
    return "—"



def _get_display_last_name(user: Any) -> str:
    last_name: str = str(getattr(user, "last_name", "") or "").strip()
    if last_name != "":
        return last_name
    return "—"
