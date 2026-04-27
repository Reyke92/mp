from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from django.urls import NoReverseMatch, reverse


@dataclass(frozen=True, slots=True)
class ReportHubDefinition:
    key: str
    title: str
    description: str
    category_label: str
    accent_class: str
    route_name: str | None = None
    fallback_url: str | None = None


@dataclass(frozen=True, slots=True)
class ReportHubCard:
    key: str
    title: str
    description: str
    category_label: str
    accent_class: str
    url: str


_REPORT_HUB_DEFINITIONS: Final[tuple[ReportHubDefinition, ...]] = (
    ReportHubDefinition(
        key="admin_dashboard",
        title="Admin Dashboard",
        description="Open the website activity summary with current totals and weekly trends for the marketplace.",
        category_label="Activity Summary",
        accent_class="admin-report-link-card-primary",
        route_name="admin_dashboard",
    ),
    ReportHubDefinition(
        key="user_management",
        title="User Management Summary",
        description="Review user accounts, account status, role assignments, and enforcement controls from the user-management view.",
        category_label="Account Oversight",
        accent_class="admin-report-link-card-aqua",
        route_name="user_management",
    ),
    ReportHubDefinition(
        key="listing_management",
        title="Listing Management Summary",
        description="Inspect listings, listing status, seller ownership details, and enforcement controls from the listing-management view.",
        category_label="Marketplace Oversight",
        accent_class="admin-report-link-card-olive",
        route_name="listing_management",
    ),
    ReportHubDefinition(
        key="moderation_queue",
        title="Moderation Queue",
        description="Open the moderation queue to review flagged marketplace content awaiting staff attention and disposition.",
        category_label="Workflow Queue",
        accent_class="admin-report-link-card-red",
        fallback_url="/moderation/queue/",
    ),
    ReportHubDefinition(
        key="moderation_log",
        title="Moderation Report Enforcement Log",
        description="Review the history of recorded moderation actions taken in response to reported content.",
        category_label="Audit Log",
        accent_class="admin-report-link-card-primary",
        route_name="moderation_log",
    ),
    ReportHubDefinition(
        key="administration_log",
        title="Administration Enforcement Log",
        description="Review administrator-recorded enforcement and privileged account-management actions across the site.",
        category_label="Audit Log",
        accent_class="admin-report-link-card-aqua",
        route_name="administration_log",
    ),
)


def build_reports_hub_cards() -> list[ReportHubCard]:
    cards: list[ReportHubCard] = []

    for definition in _REPORT_HUB_DEFINITIONS:
        cards.append(
            ReportHubCard(
                key=definition.key,
                title=definition.title,
                description=definition.description,
                category_label=definition.category_label,
                accent_class=definition.accent_class,
                url=_resolve_report_url(definition),
            )
        )

    return cards



def _resolve_report_url(definition: ReportHubDefinition) -> str:
    if definition.route_name is not None:
        try:
            return reverse(definition.route_name)
        except NoReverseMatch:
            pass

    if definition.fallback_url:
        return definition.fallback_url

    return "#"
