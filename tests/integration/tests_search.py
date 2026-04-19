from __future__ import annotations

from django.urls import reverse

from tests.common import MarketplaceTestCase


class SearchIntegrationTests(MarketplaceTestCase):
    def setUp(self) -> None:
        self.world = self.create_basic_listing_world()
        self.owner = self.create_user(email="owner@example.com", with_profile=True, city=self.world.city)
        self.active_listing = self.create_listing(
            seller_user=self.owner,
            world=self.world,
            title="Lenovo Laptop",
            description="A reliable Lenovo laptop in good condition with charger.",
        )
        self.frozen_listing = self.create_listing(
            seller_user=self.owner,
            world=self.world,
            status=self.world.frozen_status,
            title="Frozen Laptop",
            description="This listing is not public.",
        )
        self.create_snapshot(listing=self.active_listing)
        self.create_snapshot(listing=self.frozen_listing)

    def test_search_view_returns_matching_public_results(self) -> None:
        response = self.client.get(reverse("search"), data={"q": "Lenovo"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["active_result_count"], 1)
        self.assertEqual(response.context["result_cards"][0].title, "Lenovo Laptop")

    def test_search_view_preserves_filters_for_empty_results(self) -> None:
        response = self.client.get(
            reverse("search"),
            data={
                "q": "NoSuchListing",
                "category": str(self.world.child_category.category_id),
                "sort": "newest",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["active_result_count"], 0)
        self.assertEqual(response.context["filter_form"].data["category"], str(self.world.child_category.category_id))

    def test_search_view_excludes_non_public_listings(self) -> None:
        response = self.client.get(reverse("search"), data={"q": "Laptop"})

        titles = [card.title for card in response.context["result_cards"]]
        self.assertIn("Lenovo Laptop", titles)
        self.assertNotIn("Frozen Laptop", titles)
