from __future__ import annotations

from collections import defaultdict
from copy import deepcopy
from typing import Any

from django.core.cache import cache
from django.http import HttpRequest
from django.urls import NoReverseMatch, reverse

from accounts.models import UserProfile
from accounts.utils.auth import is_user_administrator, is_user_moderator
from catalog.models import Category


CATEGORY_SIDEBAR_CACHE_KEY: str = "core:categories_sidebar_tree:v1"
CATEGORY_SIDEBAR_CACHE_TIMEOUT_SECONDS: int = 900

_SIDEBAR_MAIN_ITEMS: tuple[dict[str, Any], ...] = (
    {
        "key": "home",
        "label": "Home",
        "route_names": ("home",),
        "active_route_names": ("home",),
    },
    {
        "key": "my_listings",
        "label": "My Listings",
        "route_names": ("my_listings",),
        "active_route_names": ("my_listings", "edit_listing"),
    },
    {
        "key": "create_listing",
        "label": "Create Listing",
        "route_names": ("create_listing",),
        "active_route_names": ("create_listing",),
    },
    {
        "key": "messages",
        "label": "Messages",
        "route_names": ("inbox", "messages"),
        "active_route_names": ("inbox", "messages", "message_thread"),
    },
    {
        "key": "profile",
        "label": "Profile",
        "route_names": ("profile",),
        "active_route_names": ("profile", "view_profile"),
    },
)

_SIDEBAR_MODERATION_ITEMS: tuple[dict[str, Any], ...] = (
    {
        "key": "moderation_queue",
        "label": "Moderation Queue",
        "route_names": ("moderation_queue", "mod_queue"),
        "active_route_names": ("moderation_queue", "mod_queue", "report_details"),
    },
)

_SIDEBAR_ADMIN_ITEMS: tuple[dict[str, Any], ...] = (
    {
        "key": "admin_dashboard",
        "label": "Admin Dashboard",
        "route_names": ("admin_dashboard",),
        "active_route_names": ("admin_dashboard",),
    },
    {
        "key": "user_management",
        "label": "User Management",
        "route_names": ("user_management",),
        "active_route_names": ("user_management",),
    },
    {
        "key": "listing_management",
        "label": "Listing Management",
        "route_names": ("listing_management",),
        "active_route_names": ("listing_management",),
    },
    {
        "key": "web_reports_hub",
        "label": "Web Reports Hub",
        "route_names": ("admin_reports_hub", "reports_hub"),
        "active_route_names": ("admin_reports_hub", "reports_hub"),
    },
    {
        "key": "moderation_log",
        "label": "Moderation Log",
        "route_names": ("moderation_log",),
        "active_route_names": ("moderation_log",),
    },
    {
        "key": "administration_log",
        "label": "Administration Log",
        "route_names": ("administration_log",),
        "active_route_names": ("administration_log",),
    },
)

_ALL_SIDEBAR_ITEMS: tuple[dict[str, Any], ...] = (
    _SIDEBAR_MAIN_ITEMS
    + _SIDEBAR_MODERATION_ITEMS
    + _SIDEBAR_ADMIN_ITEMS
)

_ACTIVE_SIDEBAR_KEY_BY_ROUTE_NAME: dict[str, str] = {
    route_name: str(item_definition["key"])
    for item_definition in _ALL_SIDEBAR_ITEMS
    for route_name in item_definition["active_route_names"]
}


def user_profile_context(request: HttpRequest) -> dict[str, Any]:
    """
    Adds:
      - user: request.user
      - profile: UserProfile (when authenticated and present)
      - is_admin: whether the authenticated user is an Administrator
      - is_mod: whether the authenticated user is a Moderator
      - active_sidebar_item: the current sidebar key for page highlighting
      - sidebar_navigation_sections: dynamic sidebar navigation structure
      - categories_sidebar_tree: nested category tree for the global categories sidebar
      - active_category_id: currently selected category from the request query string
    """
    context: dict[str, Any] = {
        "user": request.user,
        "is_admin": False,
        "is_mod": False,
        "active_sidebar_item": None,
        "sidebar_navigation_sections": [],
    }

    if request.user.is_authenticated:
        profile_loaded: bool = getattr(request, "_cached_user_profile_loaded", False)
        profile: UserProfile | None = getattr(request, "_cached_user_profile", None)

        if not profile_loaded:
            profile = (
                UserProfile.objects.select_related("city", "city__state")
                .filter(user=request.user)
                .first()
            )
            setattr(request, "_cached_user_profile", profile)
            setattr(request, "_cached_user_profile_loaded", True)

        if profile is not None:
            context["profile"] = profile

        is_admin: bool = is_user_administrator(request.user)
        is_mod: bool = is_user_moderator(request.user)
        active_sidebar_item: str | None = _get_active_sidebar_item(request)

        context["is_admin"] = is_admin
        context["is_mod"] = is_mod
        context["active_sidebar_item"] = active_sidebar_item
        context["sidebar_navigation_sections"] = _build_sidebar_navigation_sections(
            active_sidebar_item=active_sidebar_item,
            is_admin=is_admin,
            is_mod=is_mod,
        )

    active_category_id: int | None = _parse_active_category_id(request)
    category_tree_payload: dict[str, Any] = _get_category_sidebar_payload()

    context["active_category_id"] = active_category_id
    context["categories_sidebar_tree"] = _annotate_category_tree(
        tree=deepcopy(category_tree_payload["tree"]),
        active_category_id=active_category_id,
        parent_by_id=category_tree_payload["parent_by_id"],
    )

    return context


def _get_active_sidebar_item(request: HttpRequest) -> str | None:
    """
    Resolve the current page to a sidebar item key using the matched route name.

    This uses Django's resolver match, so query-string parameters are ignored.
    """
    resolver_match: Any = getattr(request, "resolver_match", None)
    if resolver_match is None:
        return None

    route_name: str | None = getattr(resolver_match, "url_name", None)
    if not route_name:
        return None

    return _ACTIVE_SIDEBAR_KEY_BY_ROUTE_NAME.get(str(route_name))


def _build_sidebar_navigation_sections(
    *,
    active_sidebar_item: str | None,
    is_admin: bool,
    is_mod: bool,
) -> list[dict[str, Any]]:
    sections: list[dict[str, Any]] = [
        {
            "title": None,
            "items": _build_sidebar_items(
                item_definitions=_SIDEBAR_MAIN_ITEMS,
                active_sidebar_item=active_sidebar_item,
            ),
        }
    ]

    if is_mod or is_admin:
        sections.append(
            {
                "title": "Moderation",
                "items": _build_sidebar_items(
                    item_definitions=_SIDEBAR_MODERATION_ITEMS,
                    active_sidebar_item=active_sidebar_item,
                ),
            }
        )

    if is_admin:
        sections.append(
            {
                "title": "Administration",
                "items": _build_sidebar_items(
                    item_definitions=_SIDEBAR_ADMIN_ITEMS,
                    active_sidebar_item=active_sidebar_item,
                ),
            }
        )

    return sections


def _build_sidebar_items(
    *,
    item_definitions: tuple[dict[str, Any], ...],
    active_sidebar_item: str | None,
) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []

    for item_definition in item_definitions:
        item_url, route_available = _resolve_sidebar_url(
            route_names=tuple(item_definition["route_names"])
        )

        items.append(
            {
                "key": str(item_definition["key"]),
                "label": str(item_definition["label"]),
                "url": item_url,
                "is_active": active_sidebar_item == str(item_definition["key"]),
                "is_disabled": not route_available,
            }
        )

    return items


def _resolve_sidebar_url(*, route_names: tuple[str, ...]) -> tuple[str, bool]:
    """
    Resolve the first available named route for a sidebar item.

    If the route does not exist yet, return a safe placeholder URL and mark the
    item as disabled so future routes can be added without changing the template.
    """
    for route_name in route_names:
        try:
            return reverse(route_name), True
        except NoReverseMatch:
            continue

    return "#", False


def _parse_active_category_id(request: HttpRequest) -> int | None:
    raw_value: str | None = request.GET.get("category")
    if raw_value in {None, ""}:
        return None

    try:
        parsed_value: int = int(raw_value)
    except (TypeError, ValueError):
        return None

    return parsed_value if parsed_value > 0 else None


def _get_category_sidebar_payload() -> dict[str, Any]:
    cached_payload: dict[str, Any] | None = cache.get(CATEGORY_SIDEBAR_CACHE_KEY)
    if cached_payload is not None:
        return cached_payload

    rows: list[dict[str, Any]] = list(
        Category.objects.values(
            "category_id",
            "parent_category_id",
            "name",
            "slug",
        )
    )

    children_by_parent: dict[int | None, list[dict[str, Any]]] = defaultdict(list)
    parent_by_id: dict[int, int | None] = {}

    for row in rows:
        category_id: int = int(row["category_id"])
        parent_category_id: int | None = row["parent_category_id"]

        parent_by_id[category_id] = int(parent_category_id) if parent_category_id is not None else None
        children_by_parent[parent_category_id].append(
            {
                "id": category_id,
                "name": str(row["name"]).strip(),
                "slug": str(row["slug"]).strip(),
            }
        )

    def build_branch(parent_id: int | None) -> list[dict[str, Any]]:
        branch: list[dict[str, Any]] = []

        sorted_children: list[dict[str, Any]] = sorted(
            children_by_parent.get(parent_id, []),
            key=lambda item: item["name"].lower(),
        )

        for child in sorted_children:
            branch.append(
                {
                    "id": child["id"],
                    "name": child["name"],
                    "slug": child["slug"],
                    "url": f"/search/?q=&category={child['id']}",
                    "children": build_branch(child["id"]),
                }
            )

        return branch

    payload: dict[str, Any] = {
        "tree": build_branch(None),
        "parent_by_id": parent_by_id,
    }

    cache.set(CATEGORY_SIDEBAR_CACHE_KEY, payload, CATEGORY_SIDEBAR_CACHE_TIMEOUT_SECONDS)
    return payload


def _annotate_category_tree(
    tree: list[dict[str, Any]],
    active_category_id: int | None,
    parent_by_id: dict[int, int | None],
) -> list[dict[str, Any]]:
    active_path_ids: set[int] = set()

    current_category_id: int | None = active_category_id
    while current_category_id is not None:
        active_path_ids.add(current_category_id)
        current_category_id = parent_by_id.get(current_category_id)

    def annotate_node(node: dict[str, Any]) -> dict[str, Any]:
        node_id: int = int(node["id"])
        children: list[dict[str, Any]] = [annotate_node(child) for child in node["children"]]

        node["children"] = children
        node["has_children"] = len(children) > 0
        node["is_active"] = node_id == active_category_id
        node["is_open"] = node_id in active_path_ids
        node["child_count"] = len(children)
        node["collapse_id"] = f"category-children-{node_id}"

        return node

    return [annotate_node(node) for node in tree]