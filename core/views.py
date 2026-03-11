from __future__ import annotations

from typing import Any

from django.http import HttpRequest, HttpResponse
from django.shortcuts import render

from search.utils import build_listing_browser_context


def homepage_view(request: HttpRequest) -> HttpResponse:
    context: dict[str, Any] = build_listing_browser_context(
        request=request,
        default_sort="newest",
        filter_submit_url_name="search",
        category_refresh_url_name="home",
        clear_filters_url_name="home",
        results_page_url_name="home",
    )

    context["page_heading"] = "Newest Marketplace Listings"
    context["page_description"] = (
        "Browse, sell, message, and report content. "
        "Selling tools are available to all users."
    )
    context["empty_state_title"] = "No listings yet"
    context["empty_state_description"] = (
        "New public listings will appear here as soon as sellers publish them."
    )
    context["pagination_aria_label"] = "Homepage listings pagination"

    return render(request, "core/home.html", context)
