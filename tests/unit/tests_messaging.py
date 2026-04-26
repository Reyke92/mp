from __future__ import annotations

from messaging.models import Conversation
from tests.common import MarketplaceTestCase

# TC-MSG-001
class ConversationStandardPairTests(MarketplaceTestCase):
    def setUp(self):
        self.world = self.create_basic_listing_world()
        self.user_with_lower_id = self.create_user(email="lower@example.com")
        self.user_with_higher_id = self.create_user(email="higher@example.com")

    def test_standard_pair_orders_users_by_id(self):
        user_a, user_b = Conversation.standard_pair(self.user_with_lower_id, self.user_with_higher_id)

        self.assertEqual(user_a, self.user_with_lower_id)
        self.assertEqual(user_b, self.user_with_higher_id)

    def test_standard_pair_swaps_when_arguments_are_reversed(self):
        user_a, user_b = Conversation.standard_pair(self.user_with_higher_id, self.user_with_lower_id)

        self.assertEqual(user_a, self.user_with_lower_id)
        self.assertEqual(user_b, self.user_with_higher_id)

    def test_standard_pair_returns_same_ordering(self):
        forward_pair = Conversation.standard_pair(self.user_with_lower_id, self.user_with_higher_id)
        reverse_pair = Conversation.standard_pair(self.user_with_higher_id, self.user_with_lower_id)

        self.assertEqual(forward_pair, reverse_pair)