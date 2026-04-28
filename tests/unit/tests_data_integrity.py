from __future__ import annotations

from django.db import IntegrityError, transaction

from catalog.models import Attribute, AttributeValueType
from listings.models import ListingAttributeValue, ListingImage
from messaging.models import Conversation
from tests.common import MarketplaceTestCase


class DataIntegrityUnitTests(MarketplaceTestCase):
    def setUp(self) -> None:
        self.world = self.create_basic_listing_world()
        self.owner = self.create_user(email="owner@example.com", with_profile=True, city=self.world.city)
        self.other_user = self.create_user(email="other@example.com", with_profile=True, city=self.world.city)
        self.listing = self.create_listing(seller_user=self.owner, world=self.world)

    def test_duplicate_listing_image_display_order_is_rejected(self) -> None:
        # TC-DATA-004 / TC-DATA-010: one listing cannot store duplicate image display positions.
        ListingImage.objects.create(listing=self.listing, image_url="first.jpg", display_order=0)

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                ListingImage.objects.create(listing=self.listing, image_url="duplicate.jpg", display_order=0)

    def test_duplicate_listing_attribute_value_is_rejected(self) -> None:
        # TC-DATA-005 / TC-DATA-010: one listing cannot store duplicate rows for the same attribute.
        value_type, _ = AttributeValueType.objects.get_or_create(value_type_name="integer")
        attribute = Attribute.objects.create(
            category=self.world.child_category,
            attribute_key="screen_size_inches",
            value_type=value_type,
        )
        ListingAttributeValue.objects.create(listing=self.listing, attribute=attribute, value_int=14)

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                ListingAttributeValue.objects.create(listing=self.listing, attribute=attribute, value_int=15)

    def test_standard_pair_prevents_reversed_duplicate_conversations(self) -> None:
        # TC-DATA-011: application-layer pair normalization prevents reversed duplicate conversations.
        user_a, user_b = Conversation.standard_pair(self.owner, self.other_user)
        first, created_first = Conversation.objects.get_or_create(user_a=user_a, user_b=user_b)

        reversed_a, reversed_b = Conversation.standard_pair(self.other_user, self.owner)
        second, created_second = Conversation.objects.get_or_create(user_a=reversed_a, user_b=reversed_b)

        self.assertTrue(created_first)
        self.assertFalse(created_second)
        self.assertEqual(first.conversation_id, second.conversation_id)
        self.assertEqual(Conversation.objects.count(), 1)
