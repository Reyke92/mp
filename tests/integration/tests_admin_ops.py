from __future__ import annotations

from django.urls import reverse

from admin_ops.models import AdministrationAction, AdministrationActionType
from moderation.models import ModerationAction, ModerationActionType
from reports.models import Report, ReportStatus
from tests.common import MarketplaceTestCase


class AdminOpsIntegrationTests(MarketplaceTestCase):
    def setUp(self) -> None:
        self.world = self.create_basic_listing_world()
        self.seed_admin_action_types()
        self.admin = self.create_user(email="admin@example.com", with_profile=True, city=self.world.city)
        self.moderator = self.create_user(email="moderator@example.com", with_profile=True, city=self.world.city)
        self.standard_user = self.create_user(email="user@example.com", with_profile=True, city=self.world.city)
        self.seller = self.create_user(email="seller@example.com", with_profile=True, city=self.world.city)
        self.reporter = self.create_user(email="reporter@example.com", with_profile=True, city=self.world.city)
        self.assign_role(user=self.admin, role_name="Administrator")
        self.assign_role(user=self.moderator, role_name="Moderator")
        self.listing = self.create_listing(seller_user=self.seller, world=self.world, view_count=22)
        self.create_listing_image(listing=self.listing, display_order=0, file_name="listing.jpg")

        moderation_action_type = ModerationActionType.objects.create(action_type_name="FreezeListing")
        report_status = ReportStatus.objects.create(status_name="Received")
        self.moderation_action = ModerationAction.objects.create(
            actor_user=self.moderator,
            action_type=moderation_action_type,
            listing=self.listing,
            notes="Reviewed.",
        )
        self.report = Report.objects.create(
            reporter_user=self.reporter,
            listing=self.listing,
            action=self.moderation_action,
            status=report_status,
            details="Policy issue.",
        )
        administration_action_type = AdministrationActionType.objects.get(action_type_name="BanUser")
        self.admin_action = AdministrationAction.objects.create(
            actor_user=self.admin,
            action_type=administration_action_type,
            target_user=self.standard_user,
            notes="Banned for testing.",
        )

    def test_user_management_view_renders_for_administrator(self) -> None:
        self.client.force_login(self.admin)
        response = self.client.get(reverse("user_management"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Selected User")

    def test_user_management_selected_card_endpoint_renders_partial(self) -> None:
        self.client.force_login(self.admin)
        response = self.client.get(reverse("user_management_selected_card", kwargs={"user_id": int(self.standard_user.id)}))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.standard_user.username)

    def test_user_management_post_assigns_moderator_role(self) -> None:
        self.client.force_login(self.admin)
        response = self.client.post(
            reverse("user_management"),
            data={"action": "assign_moderator", "target_user_id": int(self.standard_user.id)},
        )

        self.assertEqual(response.status_code, 302)
        self.assertTrue(self.standard_user.userroleassignment_set.filter(role__role_name="Moderator").exists())

    def test_listing_management_selected_card_endpoint_renders_partial(self) -> None:
        self.client.force_login(self.admin)
        response = self.client.get(
            reverse("listing_management_selected_card", kwargs={"listing_id": int(self.listing.listing_id)})
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.listing.title)

    def test_listing_management_post_freezes_listing(self) -> None:
        self.client.force_login(self.admin)
        response = self.client.post(
            reverse("listing_management"),
            data={"action": "freeze_listing", "target_listing_id": int(self.listing.listing_id)},
        )

        self.assertEqual(response.status_code, 302)
        self.listing.refresh_from_db()
        self.assertEqual(self.listing.status.status_name, "Frozen")

    def test_moderation_log_view_renders_and_uses_report_linkage(self) -> None:
        self.client.force_login(self.admin)
        response = self.client.get(reverse("moderation_log"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Moderation Log")
        self.assertContains(response, self.listing.title)

    def test_moderation_log_selected_card_endpoint_renders_partial(self) -> None:
        self.client.force_login(self.admin)
        response = self.client.get(
            reverse("moderation_log_selected_card", kwargs={"action_id": int(self.moderation_action.action_id)})
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.reporter.username)

    def test_administration_log_view_renders_for_administrator(self) -> None:
        self.client.force_login(self.admin)
        response = self.client.get(reverse("administration_log"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Administration Log")
        self.assertContains(response, self.standard_user.first_name)

    def test_administration_log_selected_card_endpoint_renders_partial(self) -> None:
        self.client.force_login(self.admin)
        response = self.client.get(
            reverse("administration_log_selected_card", kwargs={"action_id": int(self.admin_action.action_id)})
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.standard_user.username)

    def test_user_conversations_placeholder_view_renders_for_administrator(self) -> None:
        self.client.force_login(self.admin)
        response = self.client.get(reverse("user_conversations", kwargs={"user_id": int(self.standard_user.id)}))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, str(int(self.standard_user.id)))
