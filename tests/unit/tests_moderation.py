from __future__ import annotations

from messaging.models import Conversation
from moderation.forms import ReportDispositionForm
from moderation.utils.report_detail import find_related_reports_for_report, resolve_reported_user
from reports.models import Report, ReportStatus
from tests.common import MarketplaceTestCase


class ModerationFormUnitTests(MarketplaceTestCase):
    # TC-MOD-002 support: the disposition form must require an action unless the
    # separate Dismiss button path is used.

    def setUp(self) -> None:
        self.seed_moderation_action_types()

    def test_disposition_form_rejects_missing_action(self) -> None:
        form = ReportDispositionForm(data={"action_type": "", "notes": "Needs review."})

        self.assertFalse(form.is_valid())
        self.assertIn("Choose a moderation action", form.non_field_errors()[0])

    def test_disposition_form_limits_choices_to_allowed_action_names(self) -> None:
        form = ReportDispositionForm(allowed_action_names=["FreezeListing"])

        choice_labels = [label for _, label in form.fields["action_type"].choices]
        self.assertIn("FreezeListing", choice_labels)
        self.assertNotIn("BanUser", choice_labels)


class ModerationReportUtilityUnitTests(MarketplaceTestCase):
    # These unit tests cover the helper rules that power the moderation-review UI.

    def setUp(self) -> None:
        self.world = self.create_basic_listing_world()
        self.seed_moderation_action_types()
        self.received_status, _ = ReportStatus.objects.get_or_create(status_name="Received")
        self.dismissed_status, _ = ReportStatus.objects.get_or_create(status_name="Dismissed")

        self.seller = self.create_user(email="seller@example.com", with_profile=True, city=self.world.city)
        self.reporter = self.create_user(email="reporter@example.com", with_profile=True, city=self.world.city)
        self.other_reporter = self.create_user(email="other-reporter@example.com", with_profile=True, city=self.world.city)
        self.target_user = self.create_user(email="target@example.com", with_profile=True, city=self.world.city)

        self.listing = self.create_listing(seller_user=self.seller, world=self.world, title="Laptop listing")

        user_a, user_b = Conversation.standard_pair(self.reporter, self.target_user)
        self.conversation = Conversation.objects.create(user_a=user_a, user_b=user_b)

    def test_resolve_reported_user_returns_listing_owner_for_listing_reports(self) -> None:
        report = Report.objects.create(
            reporter_user=self.reporter,
            listing=self.listing,
            status=self.received_status,
            details="Unsafe listing.",
        )

        reported_user = resolve_reported_user(report=report)

        self.assertEqual(reported_user, self.seller)

    def test_resolve_reported_user_returns_other_conversation_participant(self) -> None:
        report = Report.objects.create(
            reporter_user=self.reporter,
            conversation=self.conversation,
            status=self.received_status,
            details="Unsafe messages.",
        )

        reported_user = resolve_reported_user(report=report)

        self.assertEqual(reported_user, self.target_user)

    def test_find_related_reports_groups_recent_reports_by_shared_listing_target(self) -> None:
        selected_report = Report.objects.create(
            reporter_user=self.reporter,
            listing=self.listing,
            status=self.received_status,
            details="First report.",
        )
        recent_related = Report.objects.create(
            reporter_user=self.other_reporter,
            listing=self.listing,
            status=self.received_status,
            details="Second report.",
        )
        unrelated_listing = self.create_listing(
            seller_user=self.seller,
            world=self.world,
            title="Unrelated listing",
        )
        Report.objects.create(
            reporter_user=self.other_reporter,
            listing=unrelated_listing,
            status=self.dismissed_status,
            details="Unrelated.",
        )

        related_reports = find_related_reports_for_report(
            report=selected_report,
            include_selected_always=True,
        )

        related_ids = {int(report.report_id) for report in related_reports}
        self.assertIn(int(selected_report.report_id), related_ids)
        self.assertIn(int(recent_related.report_id), related_ids)
        self.assertEqual(len(related_ids), 2)

    def test_find_related_reports_groups_conversation_reports_by_reported_user(self) -> None:
        selected_report = Report.objects.create(
            reporter_user=self.reporter,
            conversation=self.conversation,
            status=self.received_status,
            details="Conversation issue.",
        )

        second_reporter = self.create_user(email="third@example.com", with_profile=True, city=self.world.city)
        other_a, other_b = Conversation.standard_pair(second_reporter, self.target_user)
        second_conversation = Conversation.objects.create(user_a=other_a, user_b=other_b)
        related_report = Report.objects.create(
            reporter_user=second_reporter,
            conversation=second_conversation,
            status=self.received_status,
            details="Same user reported again.",
        )

        unrelated_other_user = self.create_user(email="another-target@example.com", with_profile=True, city=self.world.city)
        unrelated_a, unrelated_b = Conversation.standard_pair(self.other_reporter, unrelated_other_user)
        unrelated_conversation = Conversation.objects.create(user_a=unrelated_a, user_b=unrelated_b)
        Report.objects.create(
            reporter_user=self.other_reporter,
            conversation=unrelated_conversation,
            status=self.received_status,
            details="Different reported user.",
        )

        related_reports = find_related_reports_for_report(
            report=selected_report,
            include_selected_always=True,
        )

        related_ids = {int(report.report_id) for report in related_reports}
        self.assertIn(int(selected_report.report_id), related_ids)
        self.assertIn(int(related_report.report_id), related_ids)
        self.assertEqual(len(related_ids), 2)
