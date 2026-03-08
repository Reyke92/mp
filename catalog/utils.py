from collections import defaultdict
from typing import Any
from django.core.cache import cache
from .models import Category

def get_category(
    cache_key: str = "catalog:categories_2d",
    timeout_seconds: int = 900,
) -> list[dict[str, Any]]:
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    rows = list(Category.objects.values("category_id", "name", "slug", "parent_category_id"))

    parents: list[dict[str, Any]] = []
    children_by_parent: dict[int, list[dict[str, Any]]] = defaultdict(list)

    for r in rows:
        pid = r["parent_category_id"]

        # top-level categories now have NULL parent
        if pid is None:
            parents.append(r)
        else:
            children_by_parent[int(pid)].append(r)

    grouped: list[dict[str, Any]] = []
    for p in sorted(parents, key=lambda x: str(x["name"]).strip().lower()):
        pid = int(p["category_id"])
        kids = sorted(children_by_parent.get(pid, []), key=lambda x: str(x["name"]).strip().lower())

        grouped.append({
            "parent": {
                "id": pid,
                "name": str(p["name"]).strip(),
                "slug": str(p["slug"]).strip(),
            },
            "children": [
                {
                    "id": int(c["category_id"]),
                    "name": str(c["name"]).strip(),
                    "slug": str(c["slug"]).strip(),
                }
                for c in kids
            ],
        })

    cache.set(cache_key, grouped, timeout_seconds)
    return grouped