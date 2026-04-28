from __future__ import annotations

from django.urls import reverse

from tests.common import MarketplaceTestCase
from tracking.models import ListingMetadataSnapshot


class ListingMetadataSnapshotIntegrationTests(MarketplaceTestCase):
    def setUp(self) -> None:
        self.world = self.create_basic_listing_world()
        self.owner = self.create_user(email="owner@example.com", with_profile=True, city=self.world.city)

    def _listing_form_data(self, *, title: str, price_amount: str = "75.00") -> dict[str, str]:
        return {
            "title": title,
            "price_amount": price_amount,
            "category": str(self.world.child_category.category_id),
            "condition": str(self.world.condition.condition_id),
            "city_name": self.world.city.city_name,
            "state": str(self.world.state.state_id),
            "description": "This listing has enough detail to pass the description validation.",
        }

    def test_create_listing_view_creates_snapshot_row(self) -> None:
        # TC-SNAP-001: creating a listing creates one matching snapshot row.
        self.client.force_login(self.owner)

        response = self.client.post(reverse("create_listing"), data=self._listing_form_data(title="Snapshot chair"))

        self.assertEqual(response.status_code, 302)
        snapshot = ListingMetadataSnapshot.objects.get(listing__title="Snapshot chair")
        self.assertEqual(snapshot.compiled_json["Title"], "Snapshot chair")
        self.assertEqual(snapshot.compiled_json["CityName"], self.world.city.city_name)

    def test_edit_listing_view_refreshes_core_snapshot_fields(self) -> None:
        # TC-SNAP-002: editing listing core fields refreshes snapshot content.
        listing = self.create_listing(seller_user=self.owner, world=self.world, title="Old title")
        self.create_snapshot(listing=listing)
        self.client.force_login(self.owner)

        response = self.client.post(
            reverse("edit_listing", args=[listing.listing_id]),
            data=self._listing_form_data(title="New snapshot title", price_amount="125.00"),
        )

        self.assertEqual(response.status_code, 302)
        snapshot = ListingMetadataSnapshot.objects.get(listing=listing)
        self.assertEqual(snapshot.compiled_json["Title"], "New snapshot title")
        self.assertEqual(snapshot.compiled_json["PriceAmount"], 125.0)

    def test_snapshot_backed_detail_and_search_show_current_values(self) -> None:
        # TC-SNAP-010: snapshot-backed detail/search surfaces display current derived values.
        listing = self.create_listing(seller_user=self.owner, world=self.world, title="Snapshot visible laptop")
        self.create_snapshot(listing=listing)
        self.client.force_login(self.owner)
        self.client.post(
            reverse("edit_listing", args=[listing.listing_id]),
            data=self._listing_form_data(title="Updated visible laptop", price_amount="225.00"),
        )

        detail_response = self.client.get(reverse("listing_detail", args=[listing.listing_id]))
        search_response = self.client.get(reverse("search"), data={"q": "Updated visible"})

        self.assertContains(detail_response, "Updated visible laptop")
        self.assertEqual(search_response.context["result_cards"][0].title, "Updated visible laptop")
        self.assertEqual(search_response.context["result_cards"][0].price_amount, 225.0)
