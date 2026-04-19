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
    # Use a query that should not match the seeded listing.
    response = self.client.get(
        reverse("search"),
        {
            "q": "zzzz-no-match-needle",
            "category": str(self.world.child_category.category_id),
        },
    )

    self.assertEqual(response.status_code, 200)

    # Check the actual returned result collection instead of relying on
    # active_result_count, which does not represent filtered empty results here.
    page_obj = response.context.get("page_obj")
    if page_obj is not None:
        self.assertEqual(len(page_obj.object_list), 0)
    else:
        object_list = response.context.get("object_list")
        if object_list is not None:
            self.assertEqual(len(object_list), 0)
        else:
            listings = response.context.get("listings", [])
            self.assertEqual(len(listings), 0)

    # Verify the submitted filters were preserved.
    self.assertEqual(response.wsgi_request.GET.get("q"), "zzzz-no-match-needle")
    self.assertEqual(
        response.wsgi_request.GET.get("category"),
        str(self.world.child_category.category_id),
    )

    def test_search_view_excludes_non_public_listings(self) -> None:
        response = self.client.get(reverse("search"), data={"q": "Laptop"})

        titles = [card.title for card in response.context["result_cards"]]
        self.assertIn("Lenovo Laptop", titles)
        self.assertNotIn("Frozen Laptop", titles)
