from __future__ import annotations

from listings.models import Listing
from search.utils import _apply_category_filter
from tests.common import MarketplaceTestCase


class SearchUtilityUnitTests(MarketplaceTestCase):
    def setUp(self) -> None:
        self.world = self.create_basic_listing_world()
        self.owner = self.create_user(email="owner@example.com")
        self.parent_listing = Listing.objects.create(
            seller_user=self.owner,
            category=self.world.parent_category,
            condition=self.world.condition,
            city=self.world.city,
            title="Parent item",
            description="Parent category item description.",
            price_amount="10.00",
            status=self.world.active_status,
            view_count=0,
        )
        self.child_listing = self.create_listing(
            seller_user=self.owner,
            world=self.world,
            title="Child item",
            description="Child category item description.",
        )

    def test_apply_category_filter_includes_descendant_categories(self) -> None:
        queryset = _apply_category_filter(Listing.objects.all(), int(self.world.parent_category.category_id))

        returned_ids = set(queryset.values_list("listing_id", flat=True))
        self.assertIn(int(self.parent_listing.listing_id), returned_ids)
        self.assertIn(int(self.child_listing.listing_id), returned_ids)
