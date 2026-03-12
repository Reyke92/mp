from __future__ import annotations

from typing import Any

from django.db.models import F

from admin_ops.models import UserRoleAssignment
from listings.models import Listing


ADMIN_ROLE_NAME: str = "Administrator"


def record_view(listing_id: int, user_or_session: Any) -> int:
    """
    Record one eligible listing-detail view and return the current view count.

    This is the public tracking-app entry point for listing view recording. The
    caller may pass a Django user, an ``AnonymousUser``, an ``HttpRequest``, or
    another session-like object. Views are recorded for guests and authenticated
    users except the listing owner and Administrators.
    """
    listing: Listing = Listing.objects.only("listing_id", "seller_user_id", "view_count").get(
        listing_id=listing_id
    )
    viewer: Any = _resolve_viewer(user_or_session)

    if not _is_eligible_listing_view(listing=listing, viewer=viewer):
        return int(listing.view_count)

    Listing.objects.filter(listing_id=listing_id).update(view_count=F("view_count") + 1)
    listing.refresh_from_db(fields=["view_count"])
    return int(listing.view_count)


def _resolve_viewer(user_or_session: Any) -> Any:
    if hasattr(user_or_session, "user"):
        return getattr(user_or_session, "user")
    return user_or_session


def _is_eligible_listing_view(*, listing: Listing, viewer: Any) -> bool:
    if getattr(viewer, "is_authenticated", False):
        viewer_id: Any = getattr(viewer, "id", None)
        if viewer_id is not None and int(viewer_id) == int(listing.seller_user_id):
            return False
        if _is_user_administrator(viewer):
            return False

    return True


def _is_user_administrator(user: Any) -> bool:
    if not getattr(user, "is_authenticated", False):
        return False

    return UserRoleAssignment.objects.filter(
        user_id=getattr(user, "id", None),
        role__role_name__iexact=ADMIN_ROLE_NAME,
    ).exists()
