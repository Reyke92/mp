from __future__ import annotations

from datetime import timedelta

from django.urls import reverse
from django.utils import timezone

from messaging.models import Conversation
from moderation.models import ModerationAction, ModerationActionType
from reports.models import Report, ReportStatus
from tests.common import MarketplaceTestCase


class ModerationIntegrationTests(MarketplaceTestCase):
    def setUp(self) -> None:
        self.world = self.create_basic_listing_world()

        self.received_status, _ = ReportStatus.objects.get_or_create(status_name="Received")
        self.action_taken_status, _ = ReportStatus.objects.get_or_create(status_name="ActionTaken")
        self.dismissed_status, _ = ReportStatus.objects.get_or_create(status_name="Dismissed")

        self.freeze_action_type, _ = ModerationActionType.objects.get_or_create(action_type_name="FreezeListing")
        self.ban_action_type, _ = ModerationActionType.objects.get_or_create(action_type_name="BanUser")

        self.moderator = self.create_user(email="moderator@example.com", with_profile=True, city=self.world.city)
        self.admin = self.create_user(email="admin@example.com", with_profile=True, city=self.world.city)
        self.reporter = self.create_user(email="reporter@example.com", with_profile=True, city=self.world.city)
        self.second_reporter = self.create_user(email="second-reporter@example.com", with_profile=True, city=self.world.city)
        self.seller = self.create_user(email="seller@example.com", with_profile=True, city=self.world.city)
        self.reported_user = self.create_user(email="reported@example.com", with_profile=True, city=self.world.city)

        self.assign_role(user=self.moderator, role_name="Moderator")
        self.assign_role(user=self.admin, role_name="Administrator")

        self.listing = self.create_listing(
            seller_user=self.seller,
            world=self.world,
            title="Gaming laptop",
        )

        self.listing_report = Report.objects.create(
            reporter_user=self.reporter,
            listing=self.listing,
            status=self.received_status,
            details="Listing appears unsafe.",
            created_at=timezone.now() - timedelta(days=3),
        )
        self.related_listing_report = Report.objects.create(
            reporter_user=self.second_reporter,
            listing=self.listing,
            status=self.received_status,
            details="Another report against the same listing.",
            created_at=timezone.now() - timedelta(days=1),
        )
        self.resolved_listing_report = Report.objects.create(
            reporter_user=self.second_reporter,
            listing=self.listing,
            status=self.dismissed_status,
            details="Already resolved report.",
        )

        user_a, user_b = Conversation.standard_pair(self.reporter, self.reported_user)
        self.conversation = Conversation.objects.create(user_a=user_a, user_b=user_b)
        self.conversation_report = Report.objects.create(
            reporter_user=self.reporter,
            conversation=self.conversation,
            status=self.received_status,
            details="Conversation report.",
            created_at=timezone.now() - timedelta(hours=6),
        )

    def test_moderator_can_view_queue_and_report_detail_pages(self) -> None:
        # TC-MOD-001: authorized staff can open the moderation queue and a report detail page.
        self.client.force_login(self.moderator)

        queue_response = self.client.get(reverse("moderation_queue"))
        detail_response = self.client.get(reverse("report_details", kwargs={"report_id": int(self.listing_report.report_id)}))

        self.assertEqual(queue_response.status_code, 200)
        self.assertContains(queue_response, "Moderation Queue")
        self.assertContains(queue_response, "Needs Attention Now")
        self.assertContains(queue_response, self.listing.title)

        self.assertEqual(detail_response.status_code, 200)
        self.assertContains(detail_response, "Report Review")
        self.assertContains(detail_response, self.reporter.username)
        self.assertContains(detail_response, self.listing.title)

    def test_queue_summary_cards_show_open_counts_grouped_by_type(self) -> None:
        # TC-OPS-003: moderator queue summary groups open items by content type.
        self.client.force_login(self.moderator)

        response = self.client.get(reverse("moderation_queue"))

        self.assertEqual(response.status_code, 200)

        summary_cards = {card.label: card.value for card in response.context["queue_summary_cards"]}
        self.assertEqual(summary_cards["Open Listing Reports"], "2")
        self.assertEqual(summary_cards["Open Conversation Reports"], "1")
        self.assertEqual(summary_cards["Escalated Targets"], "1")

    def test_freeze_listing_disposition_updates_open_related_reports_and_links_action(self) -> None:
        # TC-MOD-002 / TC-DATA-007: saving a listing disposition records the moderation action,
        # updates report status, and links open related reports to that action.
        self.client.force_login(self.moderator)

        response = self.client.post(
            reverse("report_details", kwargs={"report_id": int(self.listing_report.report_id)}),
            data={
                "action": "save",
                "action_type": str(self.freeze_action_type.action_type_id),
                "notes": "Frozen after review.",
            },
        )

        self.assertEqual(response.status_code, 302)

        self.listing.refresh_from_db()
        self.listing_report.refresh_from_db()
        self.related_listing_report.refresh_from_db()
        self.resolved_listing_report.refresh_from_db()

        moderation_action = ModerationAction.objects.get(action_id=int(self.listing_report.action_id))

        self.assertEqual(self.listing.status.status_name, "Frozen")
        self.assertEqual(self.listing_report.status.status_name, "ActionTaken")
        self.assertEqual(self.related_listing_report.status.status_name, "ActionTaken")
        self.assertEqual(self.listing_report.action_id, self.related_listing_report.action_id)
        self.assertEqual(self.resolved_listing_report.status.status_name, "Dismissed")
        self.assertIsNone(self.resolved_listing_report.action_id)
        self.assertEqual(moderation_action.actor_user, self.moderator)
        self.assertEqual(moderation_action.listing, self.listing)
        self.assertEqual(moderation_action.action_type.action_type_name, "FreezeListing")
        self.assertEqual(moderation_action.notes, "Frozen after review.")

    def test_ban_user_disposition_bans_reported_user_and_updates_related_reports(self) -> None:
        # TC-MOD-002: conversation dispositions ban the reported user and create an action row.
        self.client.force_login(self.moderator)

        response = self.client.post(
            reverse("report_details", kwargs={"report_id": int(self.conversation_report.report_id)}),
            data={
                "action": "save",
                "action_type": str(self.ban_action_type.action_type_id),
                "notes": "Banned after review.",
            },
        )

        self.assertEqual(response.status_code, 302)

        self.reported_user.refresh_from_db()
        self.conversation_report.refresh_from_db()
        moderation_action = ModerationAction.objects.get(action_id=int(self.conversation_report.action_id))

        self.assertFalse(self.reported_user.is_active)
        self.assertEqual(self.conversation_report.status.status_name, "ActionTaken")
        self.assertEqual(moderation_action.action_type.action_type_name, "BanUser")
        self.assertEqual(moderation_action.target_user, self.reported_user)
        self.assertEqual(moderation_action.actor_user, self.moderator)

    def test_dismiss_report_updates_open_related_reports_without_creating_action(self) -> None:
        # TC-DATA-007: dismissing a report updates open related reports but leaves action_id NULL.
        self.client.force_login(self.moderator)

        response = self.client.post(
            reverse("report_details", kwargs={"report_id": int(self.listing_report.report_id)}),
            data={
                "action": "dismiss",
                "notes": "Insufficient evidence.",
            },
        )

        self.assertEqual(response.status_code, 302)

        self.listing_report.refresh_from_db()
        self.related_listing_report.refresh_from_db()

        self.assertEqual(self.listing_report.status.status_name, "Dismissed")
        self.assertEqual(self.related_listing_report.status.status_name, "Dismissed")
        self.assertIsNone(self.listing_report.action_id)
        self.assertIsNone(self.related_listing_report.action_id)

    def test_queue_most_recent_sort_orders_newest_first(self) -> None:
        self.client.force_login(self.moderator)

        response = self.client.get(reverse("moderation_queue"), data={"sort_by": "most_recent"})

        self.assertEqual(response.status_code, 200)
        table_rows = response.context["table_rows"]
        self.assertGreaterEqual(len(table_rows), 2)
        self.assertEqual(table_rows[0].report_id, int(self.conversation_report.report_id))

