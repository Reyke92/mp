from __future__ import annotations

from typing import Any

from django.http import HttpRequest, HttpResponse
from django.shortcuts import render

from .utils import build_listing_browser_context


def search_view(request: HttpRequest) -> HttpResponse:
    context: dict[str, Any] = build_listing_browser_context(
        request=request,
        default_sort="most_relevant",
        filter_submit_url_name="search",
        category_refresh_url_name="search",
        clear_filters_url_name="search",
        results_page_url_name="search",
    )

    context["page_heading"] = "Search Results"
    if context["search_term"]:
        context["page_description"] = f"Showing results for “{context['search_term']}”."
    else:
        context["page_description"] = "Browse public listings with filters and category-specific attributes."
    context["empty_state_title"] = "No results"
    context["empty_state_description"] = (
        "No public listings matched the current keyword and filters. "
        "Your current filter values were preserved so you can adjust them and try again."
    )
    context["pagination_aria_label"] = "Search results pagination"

    return render(request, "search/search_results.html", context)
