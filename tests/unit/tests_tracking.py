from __future__ import annotations

from django.test import RequestFactory

from tracking.services import record_view
from tests.common import MarketplaceTestCase


class ListingViewCountTrackingTests(MarketplaceTestCase):
    def setUp(self) -> None:
        self.factory = RequestFactory()
        self.world = self.create_basic_listing_world()
        self.owner = self.create_user(email="owner@example.com")
        self.other_user = self.create_user(email="other@example.com")
        self.administrator = self.create_user(email="administrator@example.com")
        self.assign_role(user=self.administrator, role_name="Administrator")
        self.listing = self.create_listing(seller_user=self.owner, world=self.world, view_count=0)

    def test_record_view_increments_for_guest_request(self) -> None:
        request = self.factory.get(f"/listings/{int(self.listing.listing_id)}/")

        updated_count = record_view(int(self.listing.listing_id), request)

        self.listing.refresh_from_db(fields=["view_count"])
        self.assertEqual(updated_count, 1)
        self.assertEqual(int(self.listing.view_count), 1)

    def test_record_view_increments_for_other_authenticated_user(self) -> None:
        updated_count = record_view(int(self.listing.listing_id), self.other_user)

        self.listing.refresh_from_db(fields=["view_count"])
        self.assertEqual(updated_count, 1)
        self.assertEqual(int(self.listing.view_count), 1)

    def test_record_view_does_not_increment_for_owner(self) -> None:
        updated_count = record_view(int(self.listing.listing_id), self.owner)

        self.listing.refresh_from_db(fields=["view_count"])
        self.assertEqual(updated_count, 0)
        self.assertEqual(int(self.listing.view_count), 0)

    def test_record_view_does_not_increment_for_administrator(self) -> None:
        updated_count = record_view(int(self.listing.listing_id), self.administrator)

        self.listing.refresh_from_db(fields=["view_count"])
        self.assertEqual(updated_count, 0)
        self.assertEqual(int(self.listing.view_count), 0)
