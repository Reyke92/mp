from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from math import cos, radians
from typing import Any

from django.core.paginator import Paginator
from django.db.models import (
    Case,
    Exists,
    ExpressionWrapper,
    F,
    FloatField,
    IntegerField,
    OuterRef,
    Q,
    QuerySet,
    Value,
    When,
)
from django.db.models.functions import ACos, Cast, Cos, Greatest, Least, Radians, Sin
from django.http import HttpRequest, QueryDict

from accounts.models import UserProfile
from catalog.models import Category
from core.models import City
from listings.models import Listing, ListingAttributeValue
from tracking.json_snapshots import ListingMetadataSnapshotData, get_snapshot

from .forms import DynamicAttributeFieldGroup, ListingSearchForm


RESULTS_PER_PAGE: int = 12
EARTH_RADIUS_MILES: float = 3959.0
MILES_PER_LATITUDE_DEGREE: float = 69.0
MILES_PER_LONGITUDE_DEGREE_AT_EQUATOR: float = 69.172
MINIMUM_LONGITUDE_SCALE: float = 0.000001
NON_PUBLIC_STATUS_NAMES: tuple[str, ...] = ("Frozen", "Deleted")
DISTANCE_UNAVAILABLE_MESSAGE: str = (
    "Distance filtering and closest-to-me sorting require a signed-in user profile with a city."
)


@dataclass(slots=True)
class DynamicAttributeSection:
    label: str
    value_type_name: str
    fields: list[Any]


@dataclass(slots=True)
class SearchResultCard:
    listing_id: int
    title: str
    city_name: str
    state_code: str
    price_amount: float
    condition_name: str
    category_name: str
    image_url: str | None


@dataclass(slots=True)
class UserDistanceContext:
    latitude: float
    longitude: float


def build_listing_browser_context(
    request: HttpRequest,
    *,
    default_sort: str,
    filter_submit_url_name: str,
    category_refresh_url_name: str,
    clear_filters_url_name: str,
    results_page_url_name: str,
) -> dict[str, Any]:
    effective_query_data: QueryDict | None = _build_effective_query_data(
        query_dict=request.GET,
        default_sort=default_sort,
    )

    filter_form: ListingSearchForm = ListingSearchForm(
        data=effective_query_data,
        initial={"sort": default_sort},
        default_sort=default_sort,
    )

    listings_queryset: QuerySet[Listing] = Listing.objects.exclude(
        Q(status__status_name__iexact=NON_PUBLIC_STATUS_NAMES[0])
        | Q(status__status_name__iexact=NON_PUBLIC_STATUS_NAMES[1])
    )

    distance_is_available: bool = False
    distance_message: str | None = None

    if filter_form.is_valid():
        search_text: str = str(filter_form.cleaned_data.get("q") or "").strip()
        sort_value: str = str(filter_form.cleaned_data.get("sort") or default_sort)
        distance_miles: int | None = filter_form.cleaned_data.get("distance_miles")
        needs_distance_features: bool = distance_miles is not None or sort_value == "closest"

        listings_queryset = _apply_keyword_filter(
            queryset=listings_queryset,
            query_text=search_text,
        )

        selected_category_id: int | None = filter_form.cleaned_data.get("category")
        if selected_category_id is not None:
            listings_queryset = _apply_category_filter(
                queryset=listings_queryset,
                category_id=selected_category_id,
            )

        selected_condition_id: int | None = filter_form.cleaned_data.get("condition")
        if selected_condition_id is not None:
            listings_queryset = listings_queryset.filter(condition_id=selected_condition_id)

        minimum_price: Decimal | None = filter_form.cleaned_data.get("min_price")
        if minimum_price is not None:
            listings_queryset = listings_queryset.filter(price_amount__gte=minimum_price)

        maximum_price: Decimal | None = filter_form.cleaned_data.get("max_price")
        if maximum_price is not None:
            listings_queryset = listings_queryset.filter(price_amount__lte=maximum_price)

        user_distance_context: UserDistanceContext | None = None
        if needs_distance_features:
            user_distance_context = _get_user_distance_context(request)
            distance_is_available = user_distance_context is not None

        if distance_miles is not None and user_distance_context is not None:
            listings_queryset = _apply_distance_radius_prefilter(
                queryset=listings_queryset,
                user_distance_context=user_distance_context,
                radius_miles=distance_miles,
            )
        elif distance_miles is not None:
            distance_message = DISTANCE_UNAVAILABLE_MESSAGE

        listings_queryset = _apply_dynamic_attribute_filters(
            queryset=listings_queryset,
            filter_form=filter_form,
        )

        if needs_distance_features and user_distance_context is not None:
            listings_queryset = _annotate_distance_miles(
                queryset=listings_queryset,
                user_distance_context=user_distance_context,
            )
            if distance_miles is not None:
                listings_queryset = listings_queryset.filter(distance_miles__lte=distance_miles)
        elif needs_distance_features:
            distance_message = DISTANCE_UNAVAILABLE_MESSAGE

        listings_queryset = _apply_sorting(
            queryset=listings_queryset,
            sort_value=sort_value,
            search_text=search_text,
            distance_is_available=distance_is_available,
        )
    else:
        listings_queryset = _apply_sorting(
            queryset=listings_queryset,
            sort_value=default_sort,
            search_text="",
            distance_is_available=False,
        )

    listings_queryset = listings_queryset.distinct()

    paginator: Paginator = Paginator(listings_queryset, RESULTS_PER_PAGE)
    page_number: str = str(request.GET.get("page") or "1")
    page_obj = paginator.get_page(page_number)

    return {
        "filter_form": filter_form,
        "dynamic_attribute_sections": _build_dynamic_attribute_sections(filter_form),
        "page_obj": page_obj,
        "page_query_string": _build_query_string_without_page(effective_query_data),
        "distance_is_available": distance_is_available,
        "distance_message": distance_message,
        "active_result_count": paginator.count,
        "result_cards": _build_result_cards(page_obj.object_list),
        "search_term": str(filter_form["q"].value() or "").strip(),
        "filter_submit_url_name": filter_submit_url_name,
        "category_refresh_url_name": category_refresh_url_name,
        "clear_filters_url_name": clear_filters_url_name,
        "results_page_url_name": results_page_url_name,
    }



def _build_effective_query_data(query_dict: QueryDict, default_sort: str) -> QueryDict | None:
    if query_dict:
        effective_query_dict: QueryDict = query_dict.copy()
        if str(effective_query_dict.get("sort") or "").strip() == "":
            effective_query_dict["sort"] = default_sort
        return effective_query_dict
    return None



def _build_result_cards(listings: Any) -> list[SearchResultCard]:
    result_cards: list[SearchResultCard] = []

    for listing in listings:
        snapshot: ListingMetadataSnapshotData = get_snapshot(int(listing.listing_id))
        result_cards.append(
            SearchResultCard(
                listing_id=int(listing.listing_id),
                title=snapshot.Title,
                city_name=snapshot.CityName,
                state_code=snapshot.StateCode,
                price_amount=float(snapshot.PriceAmount),
                condition_name=snapshot.Condition,
                category_name=snapshot.CategoryName,
                image_url=snapshot.Image,
            )
        )

    return result_cards



def _apply_keyword_filter(queryset: QuerySet[Listing], query_text: str) -> QuerySet[Listing]:
    if query_text == "":
        return queryset.annotate(relevance_bucket=Value(5, output_field=IntegerField()))

    queryset = queryset.filter(
        Q(title__icontains=query_text)
        | Q(city__city_name__icontains=query_text)
        | Q(city__state__state_code__icontains=query_text)
    )

    return queryset.annotate(
        relevance_bucket=Case(
            When(title__iexact=query_text, then=Value(0)),
            When(title__istartswith=query_text, then=Value(1)),
            When(title__icontains=query_text, then=Value(2)),
            When(city__city_name__istartswith=query_text, then=Value(3)),
            When(city__city_name__icontains=query_text, then=Value(4)),
            default=Value(5),
            output_field=IntegerField(),
        )
    )



def _apply_category_filter(queryset: QuerySet[Listing], category_id: int) -> QuerySet[Listing]:
    category_ids: list[int] = _get_category_and_descendant_ids(category_id)
    return queryset.filter(category_id__in=category_ids)



def _get_category_and_descendant_ids(category_id: int) -> list[int]:
    category_rows: list[dict[str, Any]] = list(
        Category.objects.values("category_id", "parent_category_id")
    )

    children_by_parent_id: dict[int, list[int]] = {}
    for row in category_rows:
        parent_category_id: int | None = row["parent_category_id"]
        if parent_category_id is None:
            continue

        children_by_parent_id.setdefault(int(parent_category_id), []).append(int(row["category_id"]))

    discovered_ids: set[int] = set()
    pending_ids: list[int] = [category_id]

    while pending_ids:
        current_category_id: int = pending_ids.pop()
        if current_category_id in discovered_ids:
            continue

        discovered_ids.add(current_category_id)
        pending_ids.extend(children_by_parent_id.get(current_category_id, []))

    return sorted(discovered_ids)



def _get_user_distance_context(request: HttpRequest) -> UserDistanceContext | None:
    if not request.user.is_authenticated:
        return None

    try:
        user_profile: UserProfile = UserProfile.objects.select_related("city").only(
            "city__latitude",
            "city__longitude",
        ).get(user=request.user)
    except UserProfile.DoesNotExist:
        return None

    return UserDistanceContext(
        latitude=float(user_profile.city.latitude),
        longitude=float(user_profile.city.longitude),
    )



def _apply_distance_radius_prefilter(
    queryset: QuerySet[Listing],
    user_distance_context: UserDistanceContext,
    radius_miles: int,
) -> QuerySet[Listing]:
    candidate_city_ids: QuerySet[City] = _get_candidate_city_ids_within_radius(
        origin_latitude=user_distance_context.latitude,
        origin_longitude=user_distance_context.longitude,
        radius_miles=radius_miles,
    )

    return queryset.filter(city_id__in=candidate_city_ids)



def _get_candidate_city_ids_within_radius(
    *,
    origin_latitude: float,
    origin_longitude: float,
    radius_miles: int,
) -> QuerySet[City]:
    latitude_delta: float = radius_miles / MILES_PER_LATITUDE_DEGREE

    longitude_scale: float = abs(cos(radians(origin_latitude)))
    if longitude_scale < MINIMUM_LONGITUDE_SCALE:
        longitude_delta: float = 180.0
    else:
        longitude_delta = radius_miles / (
            MILES_PER_LONGITUDE_DEGREE_AT_EQUATOR * longitude_scale
        )

    minimum_latitude: Decimal = Decimal(str(max(-90.0, origin_latitude - latitude_delta)))
    maximum_latitude: Decimal = Decimal(str(min(90.0, origin_latitude + latitude_delta)))

    minimum_longitude_value: float = origin_longitude - longitude_delta
    maximum_longitude_value: float = origin_longitude + longitude_delta

    candidate_cities: QuerySet[City] = City.objects.filter(
        latitude__gte=minimum_latitude,
        latitude__lte=maximum_latitude,
    )

    if minimum_longitude_value < -180.0 or maximum_longitude_value > 180.0:
        normalized_minimum_longitude: Decimal = Decimal(
            str(((minimum_longitude_value + 180.0) % 360.0) - 180.0)
        )
        normalized_maximum_longitude: Decimal = Decimal(
            str(((maximum_longitude_value + 180.0) % 360.0) - 180.0)
        )
        candidate_cities = candidate_cities.filter(
            Q(longitude__gte=normalized_minimum_longitude)
            | Q(longitude__lte=normalized_maximum_longitude)
        )
    else:
        minimum_longitude: Decimal = Decimal(str(max(-180.0, minimum_longitude_value)))
        maximum_longitude: Decimal = Decimal(str(min(180.0, maximum_longitude_value)))
        candidate_cities = candidate_cities.filter(
            longitude__gte=minimum_longitude,
            longitude__lte=maximum_longitude,
        )

    return candidate_cities.values("city_id")



def _annotate_distance_miles(
    queryset: QuerySet[Listing],
    user_distance_context: UserDistanceContext,
) -> QuerySet[Listing]:
    listing_latitude = Cast(F("city__latitude"), FloatField())
    listing_longitude = Cast(F("city__longitude"), FloatField())

    cosine_term = (
        Cos(Radians(Value(user_distance_context.latitude)))
        * Cos(Radians(listing_latitude))
        * Cos(Radians(listing_longitude) - Radians(Value(user_distance_context.longitude)))
        + Sin(Radians(Value(user_distance_context.latitude))) * Sin(Radians(listing_latitude))
    )

    bounded_cosine_term = Greatest(Value(-1.0), Least(Value(1.0), cosine_term))

    distance_expression = ExpressionWrapper(
        Value(EARTH_RADIUS_MILES) * ACos(bounded_cosine_term),
        output_field=FloatField(),
    )

    return queryset.annotate(distance_miles=distance_expression)



def _apply_dynamic_attribute_filters(
    queryset: QuerySet[Listing],
    filter_form: ListingSearchForm,
) -> QuerySet[Listing]:
    if not filter_form.is_valid():
        return queryset

    for group in filter_form.dynamic_attribute_field_groups:
        attribute_subquery: QuerySet[ListingAttributeValue] = ListingAttributeValue.objects.filter(
            listing_id=OuterRef("pk"),
            attribute_id=group.attribute_id,
        )

        value_type_name: str = group.value_type_name.lower()

        if value_type_name in {"int", "integer"}:
            minimum_value: int | None = filter_form.cleaned_data.get(group.field_names[0])
            maximum_value: int | None = filter_form.cleaned_data.get(group.field_names[1])

            if minimum_value is None and maximum_value is None:
                continue
            if minimum_value is not None:
                attribute_subquery = attribute_subquery.filter(value_int__gte=minimum_value)
            if maximum_value is not None:
                attribute_subquery = attribute_subquery.filter(value_int__lte=maximum_value)

            queryset = queryset.filter(Exists(attribute_subquery))
            continue

        if value_type_name == "decimal":
            minimum_decimal: Decimal | None = filter_form.cleaned_data.get(group.field_names[0])
            maximum_decimal: Decimal | None = filter_form.cleaned_data.get(group.field_names[1])

            if minimum_decimal is None and maximum_decimal is None:
                continue
            if minimum_decimal is not None:
                attribute_subquery = attribute_subquery.filter(value_decimal__gte=minimum_decimal)
            if maximum_decimal is not None:
                attribute_subquery = attribute_subquery.filter(value_decimal__lte=maximum_decimal)

            queryset = queryset.filter(Exists(attribute_subquery))
            continue

        if value_type_name == "datetime":
            lower_bound = filter_form.cleaned_data.get(group.field_names[0])
            upper_bound = filter_form.cleaned_data.get(group.field_names[1])

            if lower_bound is None and upper_bound is None:
                continue
            if lower_bound is not None:
                attribute_subquery = attribute_subquery.filter(value_datetime__gte=lower_bound)
            if upper_bound is not None:
                attribute_subquery = attribute_subquery.filter(value_datetime__lte=upper_bound)

            queryset = queryset.filter(Exists(attribute_subquery))
            continue

        if value_type_name in {"bool", "boolean"}:
            bool_value: bool | None = filter_form.cleaned_data.get(group.field_names[0])
            if bool_value is None:
                continue

            queryset = queryset.filter(Exists(attribute_subquery.filter(value_bool=bool_value)))
            continue

        selected_allowed_value_id: int | None = filter_form.cleaned_data.get(group.field_names[0])
        if selected_allowed_value_id is None:
            continue

        queryset = queryset.filter(Exists(attribute_subquery.filter(value_text_id=selected_allowed_value_id)))

    return queryset



def _apply_sorting(
    queryset: QuerySet[Listing],
    sort_value: str,
    search_text: str,
    distance_is_available: bool,
) -> QuerySet[Listing]:
    if sort_value == "newest":
        return queryset.order_by("-created_at", "-listing_id")

    if sort_value == "closest":
        if distance_is_available:
            return queryset.order_by("distance_miles", "-created_at", "-listing_id")
        return queryset.order_by("-created_at", "-listing_id")

    if sort_value == "price_low":
        return queryset.order_by("price_amount", "-created_at", "-listing_id")

    if sort_value == "price_high":
        return queryset.order_by("-price_amount", "-created_at", "-listing_id")

    if search_text != "":
        return queryset.order_by("relevance_bucket", "-created_at", "-listing_id")

    return queryset.order_by("-created_at", "-listing_id")



def _build_dynamic_attribute_sections(
    filter_form: ListingSearchForm,
) -> list[DynamicAttributeSection]:
    sections: list[DynamicAttributeSection] = []

    for group in filter_form.dynamic_attribute_field_groups:
        sections.append(
            DynamicAttributeSection(
                label=group.label,
                value_type_name=group.value_type_name,
                fields=[filter_form[field_name] for field_name in group.field_names],
            )
        )

    return sections



def _build_query_string_without_page(query_dict: QueryDict | None) -> str:
    mutable_query_dict: QueryDict = (query_dict or QueryDict("")).copy()
    if "page" in mutable_query_dict:
        mutable_query_dict.pop("page")
    return mutable_query_dict.urlencode()
