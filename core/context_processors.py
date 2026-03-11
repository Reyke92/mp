from __future__ import annotations

from collections import defaultdict
from copy import deepcopy
from typing import Any

from django.core.cache import cache
from django.http import HttpRequest

from accounts.models import UserProfile
from catalog.models import Category


CATEGORY_SIDEBAR_CACHE_KEY: str = "core:categories_sidebar_tree:v1"
CATEGORY_SIDEBAR_CACHE_TIMEOUT_SECONDS: int = 900


def user_profile_context(request: HttpRequest) -> dict[str, Any]:
    """
    Adds:
      - user: request.user
      - profile: UserProfile (when authenticated)
      - categories_sidebar_tree: nested category tree for the global categories sidebar
      - active_category_id: currently selected category from the request query string
    """
    context: dict[str, Any] = {
        "user": request.user,
    }

    if request.user.is_authenticated:
        # Cache on the request object to avoid multiple DB hits in one request.
        profile = getattr(request, "_cached_user_profile", None)
        if profile is None:
            profile = UserProfile.objects.get(user=request.user)
            setattr(request, "_cached_user_profile", profile)

        context["profile"] = profile

    active_category_id: int | None = _parse_active_category_id(request)
    category_tree_payload: dict[str, Any] = _get_category_sidebar_payload()

    context["active_category_id"] = active_category_id
    context["categories_sidebar_tree"] = _annotate_category_tree(
        tree=deepcopy(category_tree_payload["tree"]),
        active_category_id=active_category_id,
        parent_by_id=category_tree_payload["parent_by_id"],
    )

    return context


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
