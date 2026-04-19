from __future__ import annotations

from django.test import Client
from django.urls import reverse

from tests.common import MarketplaceTestCase


class ListingSecurityTests(MarketplaceTestCase):
    def setUp(self) -> None:
        self.world = self.create_basic_listing_world()
        self.owner = self.create_user(email="owner@example.com", with_profile=True, city=self.world.city)
        self.other_user = self.create_user(email="other@example.com", with_profile=True, city=self.world.city)
        self.admin = self.create_user(email="admin@example.com", with_profile=True, city=self.world.city)
        self.assign_role(user=self.admin, role_name="Administrator")
        self.listing = self.create_listing(seller_user=self.owner, world=self.world)
        self.create_snapshot(listing=self.listing)

    def test_guest_cannot_access_create_listing_page(self) -> None:
        response = self.client.get(reverse("create_listing"))
        self.assertEqual(response.status_code, 302)

    def test_non_owner_cannot_edit_listing(self) -> None:
        self.client.force_login(self.other_user)
        response = self.client.get(reverse("edit_listing", args=[self.listing.listing_id]))
        self.assertEqual(response.status_code, 403)

    def test_guest_cannot_view_frozen_listing(self) -> None:
        self.listing.status = self.world.frozen_status
        self.listing.save(update_fields=["status"])

        response = self.client.get(reverse("listing_detail", args=[self.listing.listing_id]))
        self.assertEqual(response.status_code, 404)

    def test_standard_user_cannot_view_deleted_listing(self) -> None:
        self.listing.status = self.world.deleted_status
        self.listing.save(update_fields=["status"])
        self.client.force_login(self.other_user)

        response = self.client.get(reverse("listing_detail", args=[self.listing.listing_id]))
        self.assertEqual(response.status_code, 404)

    def test_csrf_protects_delete_listing_post(self) -> None:
        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.force_login(self.owner)

        response = csrf_client.post(reverse("delete_listing", args=[self.listing.listing_id]))
        self.assertEqual(response.status_code, 403)
