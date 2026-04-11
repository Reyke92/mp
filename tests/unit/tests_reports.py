from __future__ import annotations

from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.http import HttpResponseRedirect
from django.test import TestCase
from django.urls import reverse

from catalog.models import Category, ItemCondition
from core.models import City, State, Timezone
from listings.models import Listing, ListingStatus
from messaging.models import Conversation
from reports.forms import ReportForm
from reports.models import Report, ReportStatus


User = get_user_model()


class ReportWorkflowTestCase(TestCase):
    def setUp(self) -> None:
        self.reporter = User.objects.create_user(
            username="reporter@example.com",
            password="password123",
        )
        self.seller = User.objects.create_user(
            username="seller@example.com",
            password="password123",
        )
        self.other_user = User.objects.create_user(
            username="other@example.com",
            password="password123",
        )

        self.state = State.objects.create(state_code="KY", state_name="Kentucky")
        self.timezone = Timezone.objects.create(timezone_name="UTC-5")
        self.city = City.objects.create(
            state=self.state,
            city_name="Bowling Green",
            timezone=self.timezone,
            latitude="36.968521",
            longitude="-86.480804",
        )
        self.category = Category.objects.create(name="Electronics", slug="electronics")
        self.condition = ItemCondition.objects.create(condition_name="Used")
        self.active_status = ListingStatus.objects.create(status_name="Active")
        self.received_status = ReportStatus.objects.create(status_name="Received")

        self.listing = Listing.objects.create(
            seller_user=self.seller,
            category=self.category,
            condition=self.condition,
            city=self.city,
            title="Desk fan",
            description="A small desk fan in good condition.",
            price_amount="15.00",
            status=self.active_status,
            view_count=0,
        )
        self.conversation = Conversation.objects.create(
            user_a=self.reporter,
            user_b=self.other_user,
        )


class ReportAuthenticationTests(ReportWorkflowTestCase): # tests TC-AUTH-005 for listing and conversation reporting only, no other protected actions
    def test_unauthenticated_user_is_redirected_from_reporting_action_for_listing(self) -> None:
        response = self.client.get(reverse("report"), {"listing_id": self.listing.listing_id})
        redirect_target = response.headers["Location"]

        self.assertEqual(response.status_code, 302)
        self.assertIn("/login/", redirect_target)
        self.assertIn(reverse("report"), redirect_target)

    def test_unauthenticated_user_is_redirected_from_reporting_action_for_conversation(self) -> None:
        response = self.client.get(reverse("report"), {"conversation_id": self.conversation.conversation_id})
        redirect_target = response.headers["Location"]

        self.assertEqual(response.status_code, 302)
        self.assertIn("/login/", redirect_target)
        self.assertIn(reverse("report"), redirect_target)


class ReportSubmissionIntegrationTests(ReportWorkflowTestCase): #tests TC-REP-001 
    def test_authenticated_user_can_submit_report_for_listing(self) -> None:
        self.client.force_login(self.reporter)

        response = self.client.post(
            reverse("report"),
            {
                "listing_id": self.listing.listing_id,
                "reason": "This listing contains misleading information.",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(Report.objects.count(), 1)

        report = Report.objects.get()
        self.assertEqual(report.reporter_user, self.reporter)
        self.assertEqual(report.listing, self.listing)
        self.assertIsNone(report.conversation)
        self.assertEqual(report.details, "This listing contains misleading information.")
        self.assertEqual(report.status, self.received_status)

    @patch("reports.views.redirect", return_value=HttpResponseRedirect("/conversations/test/"))
    def test_authenticated_user_can_submit_report_for_conversation(self, _mock_redirect: object) -> None:
        self.client.force_login(self.reporter)

        response = self.client.post(
            reverse("report"),
            {
                "conversation_id": self.conversation.conversation_id,
                "reason": "This conversation includes abusive content.",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(Report.objects.count(), 1)

        report = Report.objects.get()
        self.assertEqual(report.reporter_user, self.reporter)
        self.assertIsNone(report.listing)
        self.assertEqual(report.conversation, self.conversation)
        self.assertEqual(report.details, "This conversation includes abusive content.")
        self.assertEqual(report.status, self.received_status)


class ReportTargetValidationTests(ReportWorkflowTestCase): #tests TC-REP-002 
    def test_report_form_rejects_submission_with_both_targets(self) -> None:
        form = ReportForm(
            data={"reason": "Both targets should be rejected."},
            listing=self.listing,
            conversation=self.conversation,
        )

        self.assertFalse(form.is_valid())
        self.assertIn("A report may only target one item at a time.", form.non_field_errors())

    def test_report_form_rejects_submission_with_neither_target(self) -> None:
        form = ReportForm(data={"reason": "Missing target should be rejected."})

        self.assertFalse(form.is_valid())
        self.assertIn("A report must target either a listing or a conversation.", form.non_field_errors())

    def test_report_view_rejects_submission_with_both_targets(self) -> None:
        self.client.force_login(self.reporter)

        response = self.client.post(
            reverse("report"),
            {
                "listing_id": self.listing.listing_id,
                "conversation_id": self.conversation.conversation_id,
                "reason": "Trying to report both targets at once.",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(Report.objects.count(), 0)
        self.assertIn(
            "A report may only target one item at a time.",
            response.context["form"].non_field_errors(),
        )

    def test_report_view_rejects_submission_with_neither_target(self) -> None:
        self.client.force_login(self.reporter)

        response = self.client.post(
            reverse("report"),
            {
                "reason": "Trying to submit a report without a target.",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(Report.objects.count(), 0)
        self.assertIn(
            "A report must target either a listing or a conversation.",
            response.context["form"].non_field_errors(),
        )
