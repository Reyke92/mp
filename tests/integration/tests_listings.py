from __future__ import annotations

from django.urls import reverse

from listings.models import Listing, ListingImage, ListingStatus
from tests.common import MarketplaceTestCase


class ListingViewIntegrationTests(MarketplaceTestCase):
    def setUp(self) -> None:
        self.world = self.create_basic_listing_world()
        self.owner = self.create_user(email="owner@example.com", with_profile=True, city=self.world.city)
        self.other_user = self.create_user(email="other@example.com", with_profile=True, city=self.world.city)
        self.administrator = self.create_user(email="admin@example.com", with_profile=True, city=self.world.city)
        self.assign_role(user=self.administrator, role_name="Administrator")
        self.listing = self.create_listing(
            seller_user=self.owner,
            world=self.world,
            title="Laptop",
            description="A working laptop with charger and battery included.",
        )
        self.create_listing_image(listing=self.listing, display_order=0, file_name="laptop.jpg")
        self.create_snapshot(listing=self.listing)

    def test_create_listing_view_creates_listing(self) -> None:
        self.client.force_login(self.owner)
        response = self.client.post(
            reverse("create_listing"),
            data={
                "title": "Desk chair",
                "price_amount": "50.00",
                "category": str(self.world.child_category.category_id),
                "condition": str(self.world.condition.condition_id),
                "city_name": self.world.city.city_name,
                "state": str(self.world.state.state_id),
                "description": "A comfortable desk chair with adjustable height and good padding.",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertTrue(Listing.objects.filter(title="Desk chair").exists())

    def test_edit_listing_view_rejects_non_owner(self) -> None:
        self.client.force_login(self.other_user)

        response = self.client.get(reverse("edit_listing", args=[self.listing.listing_id]))

        self.assertEqual(response.status_code, 403)

    def test_delete_listing_marks_status_deleted(self) -> None:
        self.client.force_login(self.owner)

        response = self.client.post(reverse("delete_listing", args=[self.listing.listing_id]))

        self.listing.refresh_from_db()
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.listing.status.status_name, "Deleted")

    def test_state_cities_view_returns_selected_state_cities(self) -> None:
        self.client.force_login(self.owner)

        response = self.client.get(reverse("state_cities"), data={"state_id": int(self.world.state.state_id)})

        self.assertEqual(response.status_code, 200)
        self.assertIn(self.world.city.city_name, response.json()["cities"])

    def test_listing_detail_view_hides_view_count_for_non_owner(self) -> None:
        self.client.force_login(self.other_user)

        response = self.client.get(reverse("listing_detail", args=[self.listing.listing_id]))

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.context["detail"].show_view_count)

    def test_listing_detail_view_shows_view_count_for_owner(self) -> None:
        self.client.force_login(self.owner)

        response = self.client.get(reverse("listing_detail", args=[self.listing.listing_id]))

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["detail"].show_view_count)

    def test_listing_detail_view_allows_administrator_to_view_deleted_listing(self) -> None:
        self.listing.status = self.world.deleted_status
        self.listing.save(update_fields=["status"])
        self.client.force_login(self.administrator)

        response = self.client.get(reverse("listing_detail", args=[self.listing.listing_id]))

        self.assertEqual(response.status_code, 200)
