from __future__ import annotations

from django.urls import reverse

from tests.common import MarketplaceTestCase


class CoreHomepageIntegrationTests(MarketplaceTestCase):
    def setUp(self) -> None:
        self.world = self.create_basic_listing_world()
        self.seller = self.create_user(email="seller@example.com", with_profile=True, city=self.world.city)
        self.active_listing = self.create_listing(
            seller_user=self.seller,
            world=self.world,
            title="Laptop",
            description="A working laptop with charger and battery included.",
        )
        self.create_snapshot(listing=self.active_listing)

    def test_homepage_view_renders_public_results(self) -> None:
        response = self.client.get(reverse("home"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Newest Marketplace Listings")
        self.assertEqual(response.context["active_result_count"], 1)

    def test_homepage_view_handles_empty_results_state(self) -> None:
        response = self.client.get(reverse("home"), data={"q": "nothing-matchable"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["active_result_count"], 0)
        self.assertEqual(response.context["empty_state_title"], "No listings yet")
