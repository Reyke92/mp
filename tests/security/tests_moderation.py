from __future__ import annotations

from django.test import Client
from django.urls import reverse

from messaging.models import Conversation
from moderation.models import ModerationAction, ModerationActionType
from reports.models import Report, ReportStatus
from tests.common import MarketplaceTestCase


class ModerationSecurityTests(MarketplaceTestCase):
    def setUp(self) -> None:
        self.world = self.create_basic_listing_world()

        self.received_status, _ = ReportStatus.objects.get_or_create(status_name="Received")
        self.freeze_action_type, _ = ModerationActionType.objects.get_or_create(action_type_name="FreezeListing")
        self.ban_action_type, _ = ModerationActionType.objects.get_or_create(action_type_name="BanUser")

        self.moderator = self.create_user(email="moderator@example.com", with_profile=True, city=self.world.city)
        self.admin = self.create_user(email="admin@example.com", with_profile=True, city=self.world.city)
        self.standard_user = self.create_user(email="user@example.com", with_profile=True, city=self.world.city)
        self.reporter = self.create_user(email="reporter@example.com", with_profile=True, city=self.world.city)
        self.seller = self.create_user(email="seller@example.com", with_profile=True, city=self.world.city)
        self.other_admin = self.create_user(email="other-admin@example.com", with_profile=True, city=self.world.city)

        self.assign_role(user=self.moderator, role_name="Moderator")
        self.assign_role(user=self.admin, role_name="Administrator")
        self.assign_role(user=self.other_admin, role_name="Administrator")

        self.listing = self.create_listing(seller_user=self.seller, world=self.world, title="Secure listing")
        self.listing_report = Report.objects.create(
            reporter_user=self.reporter,
            listing=self.listing,
            status=self.received_status,
            details="Needs moderation.",
        )

        user_a, user_b = Conversation.standard_pair(self.reporter, self.other_admin)
        self.conversation = Conversation.objects.create(user_a=user_a, user_b=user_b)
        self.conversation_report = Report.objects.create(
            reporter_user=self.reporter,
            conversation=self.conversation,
            status=self.received_status,
            details="Conversation issue.",
        )

    def test_guest_cannot_access_moderation_pages(self) -> None:
        queue_response = self.client.get(reverse("moderation_queue"))
        detail_response = self.client.get(reverse("report_details", kwargs={"report_id": int(self.listing_report.report_id)}))

        self.assertEqual(queue_response.status_code, 302)
        self.assertEqual(detail_response.status_code, 302)

    def test_standard_user_cannot_access_queue_detail_or_record_disposition(self) -> None:
        # TC-SEC-004: moderation tools are staff-only.
        self.client.force_login(self.standard_user)

        queue_response = self.client.get(reverse("moderation_queue"))
        detail_response = self.client.get(reverse("report_details", kwargs={"report_id": int(self.listing_report.report_id)}))
        post_response = self.client.post(
            reverse("report_details", kwargs={"report_id": int(self.listing_report.report_id)}),
            data={
                "action": "save",
                "action_type": str(self.freeze_action_type.action_type_id),
                "notes": "Unauthorized attempt.",
            },
        )

        self.assertEqual(queue_response.status_code, 403)
        self.assertEqual(detail_response.status_code, 403)
        self.assertEqual(post_response.status_code, 403)

    def test_csrf_protects_moderation_disposition_post(self) -> None:
        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.force_login(self.moderator)

        response = csrf_client.post(
            reverse("report_details", kwargs={"report_id": int(self.listing_report.report_id)}),
            data={
                "action": "save",
                "action_type": str(self.freeze_action_type.action_type_id),
                "notes": "Missing CSRF token.",
            },
        )

        self.assertEqual(response.status_code, 403)

    def test_moderation_disposition_creates_auditable_action_record(self) -> None:
        # TC-SEC-012: enforcement actions are logged with actor, target, type, and notes.
        self.client.force_login(self.moderator)

        response = self.client.post(
            reverse("report_details", kwargs={"report_id": int(self.listing_report.report_id)}),
            data={
                "action": "save",
                "action_type": str(self.freeze_action_type.action_type_id),
                "notes": "Audit this action.",
            },
        )

        self.assertEqual(response.status_code, 302)

        moderation_action = ModerationAction.objects.get(action_id=int(Report.objects.get(report_id=int(self.listing_report.report_id)).action_id))
        self.assertEqual(moderation_action.actor_user, self.moderator)
        self.assertEqual(moderation_action.listing, self.listing)
        self.assertEqual(moderation_action.action_type.action_type_name, "FreezeListing")
        self.assertEqual(moderation_action.notes, "Audit this action.")
        self.assertIsNotNone(moderation_action.created_at)

    def test_moderator_cannot_ban_administrator_through_moderation_flow(self) -> None:
        self.client.force_login(self.moderator)

        response = self.client.post(
            reverse("report_details", kwargs={"report_id": int(self.conversation_report.report_id)}),
            data={
                "action": "save",
                "action_type": str(self.ban_action_type.action_type_id),
                "notes": "Attempt to ban admin.",
            },
            follow=True,
        )

        self.other_admin.refresh_from_db()
        self.conversation_report.refresh_from_db()

        self.assertTrue(self.other_admin.is_active)
        self.assertEqual(self.conversation_report.status.status_name, "Received")
        self.assertContains(response, "Administrator accounts cannot be banned")
