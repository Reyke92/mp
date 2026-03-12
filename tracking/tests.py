from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import RequestFactory, TestCase

from admin_ops.models import Role, UserRoleAssignment
from catalog.models import Category, ItemCondition
from core.models import City, State, Timezone
from listings.models import Listing, ListingStatus
from tracking.services import record_view


User = get_user_model()


class ListingViewCountTrackingTests(TestCase):
    def setUp(self) -> None:
        self.factory = RequestFactory()
        self.owner = User.objects.create_user(username="owner@example.com", password="password123")
        self.other_user = User.objects.create_user(username="other@example.com", password="password123")
        self.administrator = User.objects.create_user(username="administrator@example.com", password="password123")

        self.administrator_role = Role.objects.create(role_name="Administrator")
        UserRoleAssignment.objects.create(user=self.administrator, role=self.administrator_role)

        self.state = State.objects.create(state_code="KY", state_name="Kentucky")
        self.timezone = Timezone.objects.create(timezone_name="UTC-5")
        self.city = City.objects.create(
            state=self.state,
            city_name="Bowling Green",
            timezone=self.timezone,
            latitude="36.968521",
            longitude="-86.480804",
            location=b"",
        )
        self.category = Category.objects.create(name="Electronics", slug="electronics")
        self.condition = ItemCondition.objects.create(condition_name="Used")
        self.active_status = ListingStatus.objects.create(status_name="Active")

        self.listing = Listing.objects.create(
            seller_user=self.owner,
            category=self.category,
            condition=self.condition,
            city=self.city,
            title="Desk fan",
            description="A small desk fan in good condition.",
            price_amount="15.00",
            status=self.active_status,
            updated_at=None,
            view_count=0,
        )

    def test_record_view_increments_for_guest_request(self) -> None:
        request = self.factory.get(f"/listings/{int(self.listing.listing_id)}/")

        updated_count = record_view(int(self.listing.listing_id), request)

        self.listing.refresh_from_db(fields=["view_count"])
        self.assertEqual(updated_count, 1)
        self.assertEqual(int(self.listing.view_count), 1)

    def test_record_view_increments_for_other_authenticated_user(self) -> None:
        updated_count = record_view(int(self.listing.listing_id), self.other_user)

        self.listing.refresh_from_db(fields=["view_count"])
        self.assertEqual(updated_count, 1)
        self.assertEqual(int(self.listing.view_count), 1)

    def test_record_view_does_not_increment_for_owner(self) -> None:
        updated_count = record_view(int(self.listing.listing_id), self.owner)

        self.listing.refresh_from_db(fields=["view_count"])
        self.assertEqual(updated_count, 0)
        self.assertEqual(int(self.listing.view_count), 0)

    def test_record_view_does_not_increment_for_administrator(self) -> None:
        updated_count = record_view(int(self.listing.listing_id), self.administrator)

        self.listing.refresh_from_db(fields=["view_count"])
        self.assertEqual(updated_count, 0)
        self.assertEqual(int(self.listing.view_count), 0)
