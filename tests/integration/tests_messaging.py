from __future__ import annotations

from messaging.models import Conversation, Message
from tests.common import MarketplaceTestCase
from django.urls import reverse
from django.utils import timezone

# TC-MSG-001
class StartConversationIntegrationTests(MarketplaceTestCase):
    def setUp(self):
        self.world = self.create_basic_listing_world()
        self.buyer = self.create_user(email="buyer@example.com", with_profile=True, city=self.world.city)
        self.seller = self.create_user(email="seller@example.com", with_profile=True, city=self.world.city)
        self.listing = self.create_listing(
            seller_user=self.seller,
            world=self.world,
            title="Test listing",
            description="A test listing for conversation integration tests.",
        )

    def test_start_conversation_view_creates_new_conversation_and_redirects(self):
        self.client.force_login(self.buyer)

        response = self.client.post(reverse("messaging:start"), {"listing_id": int(self.listing.listing_id)})

        # Check that a conversation was created
        self.assertEqual(Conversation.objects.count(), 1)
        
        # Check that the response is a redirect to the conversation view
        self.assertEqual(response.status_code, 302)
        conversation = Conversation.objects.get()
        expected_url = reverse("messaging:conversation", kwargs={"conversation_id": conversation.conversation_id})
        self.assertRedirects(response, expected_url)

    def test_start_conversation_view_with_existing_conversation(self):
        self.client.force_login(self.buyer)

        # Create an existing conversation and ensure it is not duplicated
        first_response = self.client.post(reverse("messaging:start"), {"listing_id": int(self.listing.listing_id)})
        self.assertEqual(first_response.status_code, 302)
        self.assertEqual(Conversation.objects.count(), 1)
        second_response = self.client.post(reverse("messaging:start"), {"listing_id": int(self.listing.listing_id)})
        self.assertEqual(second_response.status_code, 302)
        self.assertEqual(Conversation.objects.count(), 1)

        # Check that both responses redirect to the same conversation view
        self.assertEqual(first_response.url, second_response.url)   #type: ignore

    def test_start_conversation_view_requires_authentication(self):
        response = self.client.post(reverse("messaging:start"), {"listing_id": int(self.listing.listing_id)})

        self.assertEqual(response.status_code, 302)
        self.assertEqual(Conversation.objects.count(), 0)

# TC-MSG-002
class SendMessageIntegrationTests(MarketplaceTestCase):
    def setUp(self):
        self.world = self.create_basic_listing_world()
        self.buyer = self.create_user(email="buyer@example.com", with_profile=True, city=self.world.city)
        self.seller = self.create_user(email="seller@example.com", with_profile=True, city=self.world.city)
        
        user_a, user_b = Conversation.standard_pair(self.buyer, self.seller)
        self.conversation = Conversation.objects.create(user_a=user_a, user_b=user_b)

    def test_send_message_view_persists_all_required_metadata(self):
        self.client.force_login(self.buyer)
        message_txt = "Hi, is this still available?"

        before_send = timezone.now()
        response = self.client.post(
            reverse("messaging:send_message", kwargs={"conversation_id": self.conversation.conversation_id}),
            data={"message_text": message_txt}
        )
        after_send = timezone.now()

        self.assertEqual(response.status_code, 302)
        self.assertEqual(Message.objects.count(), 1)

        message = Message.objects.get()
        self.assertEqual(message.conversation, self.conversation)
        self.assertEqual(message.sender_user, self.buyer)
        self.assertEqual(message.message_text, message_txt)
        self.assertGreaterEqual(message.sent_at, before_send)
        self.assertLessEqual(message.sent_at, after_send)

    def test_send_message_view_redirects_to_conversation_view(self):
        self.client.force_login(self.buyer)

        response = self.client.post(
            reverse("messaging:send_message", kwargs={"conversation_id": self.conversation.conversation_id}),
            data={"message_text": "Hello"}
        )

        expected_url = reverse("messaging:conversation", kwargs={"conversation_id": self.conversation.conversation_id})
        self.assertRedirects(response, expected_url)

# TC-MSG-003
class ConversationVisibilityIntegrationTests(MarketplaceTestCase):
    def setUp(self):
        self.world = self.create_basic_listing_world()
        self.participant_a = self.create_user(email="alice@example.com", with_profile=True, city=self.world.city)
        self.participant_b = self.create_user(email="bob@example.com", with_profile=True, city=self.world.city)
        self.non_participant = self.create_user(email="charlie@example.com", with_profile=True, city=self.world.city)

        user_a, user_b = Conversation.standard_pair(self.participant_a, self.participant_b)
        self.conversation = Conversation.objects.create(user_a=user_a, user_b=user_b)

        Message.objects.create(
            conversation=self.conversation,
            sender_user=self.participant_a,
            message_text="Hello Bob, this is Alice."
        )
        Message.objects.create(
            conversation=self.conversation,
            sender_user=self.participant_b,
            message_text="Hi Alice, nice to hear from you!"
        )

    def test_participant_a_can_view_conversation(self):
        self.client.force_login(self.participant_a)
        response = self.client.get(reverse("messaging:conversation", kwargs={"conversation_id": self.conversation.conversation_id}))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["conversation"], self.conversation)
        self.assertEqual(len(response.context["thread_messages"]), 2)
        
    def test_participant_b_can_view_conversation(self):
        self.client.force_login(self.participant_b)
        response = self.client.get(reverse("messaging:conversation", kwargs={"conversation_id": self.conversation.conversation_id}))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["conversation"], self.conversation)
        self.assertEqual(len(response.context["thread_messages"]), 2)

    def test_non_participant_cannot_view_conversation(self):
        self.client.force_login(self.non_participant)
        response = self.client.get(reverse("messaging:conversation", kwargs={"conversation_id": self.conversation.conversation_id}))
        self.assertEqual(response.status_code, 403)

# TC-MSG-004
class StartCoversationDoesNotDuplicateIntegrationTests(MarketplaceTestCase):
    def setUp(self):
        self.world = self.create_basic_listing_world()
        self.user_a = self.create_user(email="usera@example.com", with_profile=True, city=self.world.city)
        self.user_b = self.create_user(email="userb@example.com", with_profile=True, city=self.world.city)
        self.listing = self.create_listing(
            seller_user=self.user_a,
            world=self.world,
            title="Test listing",
            description="A test listing for conversation duplication tests.",
        )

        user_1, user_2 = Conversation.standard_pair(self.user_b, self.user_a)
        self.existing_conversation = Conversation.objects.create(user_a=user_1, user_b=user_2)

    def test_start_conversation_does_not_create_duplicate(self):
        self.client.force_login(self.user_b)

        response = self.client.post(reverse("messaging:start"), {"listing_id": int(self.listing.listing_id)})

        self.assertEqual(response.status_code, 302)
        self.assertEqual(Conversation.objects.count(), 1)  # No new conversation should be created

        # The existing conversation should be returned and the user should be redirected to it
        conversation = Conversation.objects.get()
        self.assertEqual(conversation.conversation_id, self.existing_conversation.conversation_id)  
        expected_url = reverse("messaging:conversation", kwargs={"conversation_id": conversation.conversation_id})
        self.assertRedirects(response, expected_url)

# TC-MSG-005
class StartConversationSelfMessagingIntegrationTests(MarketplaceTestCase):
    def setUp(self):
        self.world = self.create_basic_listing_world()
        self.user = self.create_user(email="user@example.com", with_profile=True, city=self.world.city)
        self.listing = self.create_listing(
            seller_user=self.user,
            world=self.world,
            title="Test listing",
            description="A test listing for self-messaging tests.",
        )

    def test_start_conversation_with_self_is_forbidden(self):
        self.client.force_login(self.user)

        response = self.client.post(reverse("messaging:start"), {"listing_id": int(self.listing.listing_id)})

        self.assertEqual(response.status_code, 403)
        self.assertEqual(Conversation.objects.count(), 0)

# TC-MSG-006
class SendMessageEmptyContentIntegrationTests(MarketplaceTestCase):
    def setUp(self):
        self.world = self.create_basic_listing_world()
        self.buyer = self.create_user(email="buyer@example.com", with_profile=True, city=self.world.city)
        self.seller = self.create_user(email="seller@example.com", with_profile=True, city=self.world.city)

        user_a, user_b = Conversation.standard_pair(self.buyer, self.seller)
        self.conversation = Conversation.objects.create(user_a=user_a, user_b=user_b)

    def test_empty_or_whitespace_only_message_is_not_sent(self):
        self.client.force_login(self.buyer)
        send_url = reverse("messaging:send_message", kwargs={"conversation_id": self.conversation.conversation_id})
        thread_url = reverse("messaging:conversation", kwargs={"conversation_id": self.conversation.conversation_id})

        invalid_contents = [
            ("empty string", {"message_text": ""}),
            ("whitespace only", {"message_text": "   "}),
            ("field missing", {}),
        ]

        for label, post_data in invalid_contents:
            with self.subTest(label=label):
                response = self.client.post(send_url, data=post_data)
                self.assertRedirects(response, thread_url)
                self.assertEqual(Message.objects.count(), 0)

# TC-MSG-007
class StartConversationNonViewableListingIntegrationTests(MarketplaceTestCase):
    def setUp(self):
        self.world = self.create_basic_listing_world()
        self.buyer = self.create_user(email="buyer@example.com", with_profile=True, city=self.world.city)
        self.seller = self.create_user(email="seller@example.com", with_profile=True, city=self.world.city)

    def test_buyer_cannot_start_conversation_for_frozen_listing(self):
        frozen_listing = self.create_listing(
            seller_user=self.seller,
            world=self.world,
            title="Frozen listing",
            description="This listing is frozen and should not allow conversations.",
            status=self.world.frozen_status,
        )

        self.client.force_login(self.buyer)
        response = self.client.post(reverse("messaging:start"), {"listing_id": int(frozen_listing.listing_id)})

        self.assertEqual(response.status_code, 403)
        self.assertEqual(Conversation.objects.count(), 0)

    def test_buyer_cannot_start_conversation_for_deleted_listing(self):
        deleted_listing = self.create_listing(
            seller_user=self.seller,
            world=self.world,
            title="Deleted listing",
            description="This listing is deleted and should not allow conversations.",
            status=self.world.deleted_status,
        )

        self.client.force_login(self.buyer)
        response = self.client.post(reverse("messaging:start"), {"listing_id": int(deleted_listing.listing_id)})

        self.assertEqual(response.status_code, 403)
        self.assertEqual(Conversation.objects.count(), 0)

# TC-MSG-008
class InboxViewIntegrationTests(MarketplaceTestCase):
    def setUp(self):
        self.world = self.create_basic_listing_world()
        self.test_user = self.create_user(email="testuser@example.com", with_profile=True, city=self.world.city)
        self.other_one = self.create_user(email="otherone@example.com", with_profile=True, city=self.world.city)
        self.other_two = self.create_user(email="othertwo@example.com", with_profile=True, city=self.world.city)

        self.conversation_as_user_a = Conversation.objects.create(user_a=self.test_user, user_b=self.other_one)
        self.conversation_as_user_b = Conversation.objects.create(user_a=self.other_two, user_b=self.test_user)

        Message.objects.create(conversation=self.conversation_as_user_a, sender_user=self.test_user, message_text="Reply from other_one to test_user.")
        Message.objects.create(conversation=self.conversation_as_user_b, sender_user=self.other_two, message_text="Message from other_two to test_user.")

    def test_inbox_view_shows_all_conversations(self):
        self.client.force_login(self.test_user)
        response = self.client.get(reverse("messaging:inbox"))

        self.assertEqual(response.status_code, 200)
        conversations_in_context = set(response.context["rows"])
        self.assertIn(self.conversation_as_user_a, conversations_in_context)
        self.assertIn(self.conversation_as_user_b, conversations_in_context)

# TC-MSG-009
class SidebarActiveStateIntegrationTests(MarketplaceTestCase):
    def setUp(self):
        self.world = self.create_basic_listing_world()
        self.test_user = self.create_user(email="testuser@example.com", with_profile=True, city=self.world.city)
        self.other_user = self.create_user(email="other@example.com", with_profile=True, city=self.world.city)

        user_a, user_b = Conversation.standard_pair(self.test_user, self.other_user)
        self.conversation = Conversation.objects.create(user_a=user_a, user_b=user_b)

    def test_messages_sidebar_entry_renders_active_state(self):
        self.client.force_login(self.test_user)
        response = self.client.get(reverse("messaging:inbox"))

        self.assertEqual(response.status_code, 200)

        sidebar_sections = response.context["sidebar_navigation_sections"]
        all_items = [item for section in sidebar_sections for item in section["items"]]
        messages_item = next(item for item in all_items if item["key"] == "messages")
        self.assertTrue(messages_item["is_active"])

    def test_messages_sidebar_entry_is_active_in_conversation_view(self):
        self.client.force_login(self.test_user)
        response = self.client.get(reverse("messaging:conversation", kwargs={"conversation_id": self.conversation.conversation_id}))

        self.assertEqual(response.status_code, 200)

        sidebar_sections = response.context["sidebar_navigation_sections"]
        all_items = [item for section in sidebar_sections for item in section["items"]]
        messages_item = next(item for item in all_items if item["key"] == "messages")
        self.assertTrue(messages_item["is_active"])
