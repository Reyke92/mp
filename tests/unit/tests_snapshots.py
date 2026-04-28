from __future__ import annotations

from datetime import timedelta

from django.db import IntegrityError, transaction
from django.utils import timezone

from catalog.models import AllowedAttributeValue, Attribute, AttributeValueType
from listings.models import ListingAttributeValue
from tests.common import MarketplaceTestCase
from tracking.json_snapshots import get_snapshot, refresh_snapshot
from tracking.models import ListingMetadataSnapshot


class ListingMetadataSnapshotUnitTests(MarketplaceTestCase):
    def setUp(self) -> None:
        self.world = self.create_basic_listing_world()
        self.owner = self.create_user(email="seller@example.com", with_profile=True, city=self.world.city)
        self.listing = self.create_listing(
            seller_user=self.owner,
            world=self.world,
            title="Original laptop",
            description="A useful laptop with a charger and working battery.",
            price_amount="400.00",
        )

    def test_get_snapshot_lazily_creates_missing_snapshot(self) -> None:
        # TC-SNAP-006: reading a missing snapshot rebuilds it from normalized data.
        self.assertFalse(ListingMetadataSnapshot.objects.filter(listing=self.listing).exists())

        snapshot = get_snapshot(int(self.listing.listing_id))

        self.assertEqual(snapshot.Title, "Original laptop")
        self.assertTrue(ListingMetadataSnapshot.objects.filter(listing=self.listing).exists())

    def test_get_snapshot_refreshes_stale_snapshot_on_read(self) -> None:
        # TC-SNAP-007: stale snapshots refresh automatically before being returned.
        refresh_snapshot(int(self.listing.listing_id))
        snapshot_row = ListingMetadataSnapshot.objects.get(listing=self.listing)
        snapshot_row.compiled_json["Title"] = "Stale title"
        snapshot_row.compiled_at = timezone.now() - timedelta(days=2)
        snapshot_row.save(update_fields=["compiled_json", "compiled_at"])

        snapshot = get_snapshot(int(self.listing.listing_id))

        snapshot_row.refresh_from_db()
        self.assertEqual(snapshot.Title, "Original laptop")
        self.assertGreater(snapshot_row.compiled_at, timezone.now() - timedelta(hours=1))

    def test_refresh_snapshot_reflects_images_and_attributes(self) -> None:
        # TC-SNAP-003 / TC-SNAP-004 / TC-SNAP-008: snapshot data matches normalized attributes/images.
        value_type, _ = AttributeValueType.objects.get_or_create(value_type_name="text")
        attribute = Attribute.objects.create(
            category=self.world.child_category,
            attribute_key="snapshot_brand",
            value_type=value_type,
        )
        allowed_value = AllowedAttributeValue.objects.create(
            attribute=attribute,
            allowed_value_label="Lenovo",
        )
        ListingAttributeValue.objects.create(
            listing=self.listing,
            attribute=attribute,
            value_text=allowed_value,
        )
        self.create_listing_image(listing=self.listing, display_order=1, file_name="secondary.jpg")
        self.create_listing_image(listing=self.listing, display_order=0, file_name="primary.jpg")

        refresh_snapshot(int(self.listing.listing_id))
        snapshot = get_snapshot(int(self.listing.listing_id))

        self.assertEqual(snapshot.Attributes, {"snapshot_brand": "Lenovo"})
        self.assertEqual(snapshot.Image, "/primary.jpg")
        self.assertEqual(snapshot.PriceAmount, 400.0)
        self.assertEqual(snapshot.CategoryName, self.world.child_category.name)

    def test_snapshot_is_one_to_one_with_listing(self) -> None:
        # TC-SNAP-009: the database allows only one snapshot row per listing.
        ListingMetadataSnapshot.objects.create(
            listing=self.listing,
            compiled_json={"Title": "First"},
            compiled_at=timezone.now(),
        )

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                ListingMetadataSnapshot.objects.create(
                    listing=self.listing,
                    compiled_json={"Title": "Duplicate"},
                    compiled_at=timezone.now(),
                )
