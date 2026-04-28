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
        # TC-LIST-001 / TC-DATA-001: authenticated sellers can create listings with required core fields.
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

    def test_edit_listing_view_updates_owner_listing(self) -> None:
        # TC-LIST-002 / TC-DATA-002: owners can edit active listings without creating duplicates.
        self.client.force_login(self.owner)

        response = self.client.post(
            reverse("edit_listing", args=[self.listing.listing_id]),
            data={
                "title": "Updated laptop",
                "price_amount": "475.00",
                "category": str(self.world.child_category.category_id),
                "condition": str(self.world.condition.condition_id),
                "city_name": self.world.city.city_name,
                "state": str(self.world.state.state_id),
                "description": "An updated laptop description with enough useful detail.",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.listing.refresh_from_db()
        self.assertEqual(self.listing.title, "Updated laptop")
        self.assertEqual(str(self.listing.price_amount), "475.00")
        self.assertEqual(Listing.objects.filter(listing_id=self.listing.listing_id).count(), 1)

    def test_edit_listing_view_rejects_non_owner(self) -> None:
        # TC-LIST-003: non-owners cannot edit another seller's listing.
        self.client.force_login(self.other_user)

        response = self.client.get(reverse("edit_listing", args=[self.listing.listing_id]))

        self.assertEqual(response.status_code, 403)

    def test_delete_listing_marks_status_deleted(self) -> None:
        # TC-LIST-005 / TC-DATA-003: owner deletion is persisted as a non-public status transition.
        self.client.force_login(self.owner)

        response = self.client.post(reverse("delete_listing", args=[self.listing.listing_id]))

        self.listing.refresh_from_db()
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.listing.status.status_name, "Deleted")

    def test_deleted_listing_is_excluded_from_search_results(self) -> None:
        # TC-LIST-005 / TC-SRCH-003: deleted listings no longer appear in public search.
        self.client.force_login(self.owner)
        self.client.post(reverse("delete_listing", args=[self.listing.listing_id]))

        response = self.client.get(reverse("search"), data={"q": "Laptop"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["active_result_count"], 0)

    def test_seller_cannot_delete_frozen_listing(self) -> None:
        # TC-LIST-006: seller deletion is rejected for frozen listings.
        self.listing.status = self.world.frozen_status
        self.listing.save(update_fields=["status"])
        self.client.force_login(self.owner)

        response = self.client.post(reverse("delete_listing", args=[self.listing.listing_id]))

        self.listing.refresh_from_db()
        self.assertEqual(response.status_code, 403)
        self.assertEqual(self.listing.status.status_name, "Frozen")

    def test_state_cities_view_returns_selected_state_cities(self) -> None:
        # TC-SEC-009: city lookup safely returns only cities for the selected state.
        self.client.force_login(self.owner)

        response = self.client.get(reverse("state_cities"), data={"state_id": int(self.world.state.state_id)})

        self.assertEqual(response.status_code, 200)
        self.assertIn(self.world.city.city_name, response.json()["cities"])

    def test_listing_detail_view_hides_view_count_for_non_owner(self) -> None:
        # TC-OPS-001 / TC-SEC-007: standard non-owners cannot see listing view counts.
        self.client.force_login(self.other_user)

        response = self.client.get(reverse("listing_detail", args=[self.listing.listing_id]))

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.context["detail"].show_view_count)

    def test_listing_detail_view_shows_view_count_for_owner(self) -> None:
        # TC-OPS-001: sellers can see view counts for their own listings.
        self.client.force_login(self.owner)

        response = self.client.get(reverse("listing_detail", args=[self.listing.listing_id]))

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["detail"].show_view_count)

    def test_listing_detail_view_allows_administrator_to_view_deleted_listing(self) -> None:
        # TC-SRCH-003 / TC-SEC-007: administrators can inspect deleted listing details.
        self.listing.status = self.world.deleted_status
        self.listing.save(update_fields=["status"])
        self.client.force_login(self.administrator)

        response = self.client.get(reverse("listing_detail", args=[self.listing.listing_id]))

        self.assertEqual(response.status_code, 200)

    def test_listing_detail_orders_gallery_images_by_display_order(self) -> None:
        # TC-IMG-001 / TC-DATA-004: listing images are displayed in persisted display order.
        ListingImage.objects.filter(listing=self.listing).delete()
        later_image = self.create_listing_image(listing=self.listing, display_order=2, file_name="later.jpg")
        first_image = self.create_listing_image(listing=self.listing, display_order=0, file_name="first.jpg")
        middle_image = self.create_listing_image(listing=self.listing, display_order=1, file_name="middle.jpg")

        response = self.client.get(reverse("listing_detail", args=[self.listing.listing_id]))

        ordered_image_ids = [image.image_id for image in response.context["detail"].gallery_images]
        self.assertEqual(ordered_image_ids, [first_image.image_id, middle_image.image_id, later_image.image_id])

    def test_non_owner_cannot_modify_listing_images(self) -> None:
        # TC-IMG-002: unauthorized users cannot modify another user's listing images.
        original_image_ids = set(ListingImage.objects.filter(listing=self.listing).values_list("image_id", flat=True))
        self.client.force_login(self.other_user)

        response = self.client.post(
            reverse("edit_listing", args=[self.listing.listing_id]),
            data={
                "title": "Malicious edit attempt",
                "price_amount": "1.00",
                "category": str(self.world.child_category.category_id),
                "condition": str(self.world.condition.condition_id),
                "city_name": self.world.city.city_name,
                "state": str(self.world.state.state_id),
                "description": "This unauthorized edit should not alter image records.",
                "removed_existing_image_ids": [str(next(iter(original_image_ids)))],
            },
        )

        remaining_image_ids = set(ListingImage.objects.filter(listing=self.listing).values_list("image_id", flat=True))
        self.assertEqual(response.status_code, 403)
        self.assertEqual(remaining_image_ids, original_image_ids)
