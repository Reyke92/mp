from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from admin_ops.models import Role, UserRoleAssignment
from catalog.models import Category, ItemCondition
from core.models import City, State, Timezone
from listings.models import Listing, ListingStatus
from listings.utils import build_my_listings_rows, can_view_listing


User = get_user_model()


class ListingAccessAndLifecycleTests(TestCase):
    def setUp(self) -> None:
        self.owner = User.objects.create_user(username="owner@example.com", password="password123")
        self.other_user = User.objects.create_user(username="other@example.com", password="password123")
        self.moderator = User.objects.create_user(username="moderator@example.com", password="password123")
        self.administrator = User.objects.create_user(username="administrator@example.com", password="password123")

        self.moderator_role = Role.objects.create(role_name="Moderator")
        self.administrator_role = Role.objects.create(role_name="Administrator")
        UserRoleAssignment.objects.create(user=self.moderator, role=self.moderator_role)
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
        self.frozen_status = ListingStatus.objects.create(status_name="Frozen")
        self.deleted_status = ListingStatus.objects.create(status_name="Deleted")

    def _create_listing(self, *, status: ListingStatus) -> Listing:
        return Listing.objects.create(
            seller_user=self.owner,
            category=self.category,
            condition=self.condition,
            city=self.city,
            title="Desk fan",
            description="A small desk fan in good condition.",
            price_amount="15.00",
            status=status,
            view_count=0,
        )

    def test_owner_can_view_frozen_listing_but_not_deleted_listing(self) -> None:
        frozen_listing = self._create_listing(status=self.frozen_status)
        deleted_listing = self._create_listing(status=self.deleted_status)

        self.assertTrue(can_view_listing(listing=frozen_listing, viewer=self.owner))
        self.assertFalse(can_view_listing(listing=deleted_listing, viewer=self.owner))

    def test_moderator_can_view_deleted_listing(self) -> None:
        deleted_listing = self._create_listing(status=self.deleted_status)
        self.assertTrue(can_view_listing(listing=deleted_listing, viewer=self.moderator))

    def test_administrator_can_view_frozen_and_deleted_listing(self) -> None:
        frozen_listing = self._create_listing(status=self.frozen_status)
        deleted_listing = self._create_listing(status=self.deleted_status)

        self.assertTrue(can_view_listing(listing=frozen_listing, viewer=self.administrator))
        self.assertTrue(can_view_listing(listing=deleted_listing, viewer=self.administrator))

    def test_listing_detail_view_allows_privileged_viewers_for_deleted_listing(self) -> None:
        deleted_listing = self._create_listing(status=self.deleted_status)
        self.client.force_login(self.moderator)

        response = self.client.get(reverse("listing_detail", args=[deleted_listing.listing_id]))

        self.assertEqual(response.status_code, 200)

    def test_my_listings_excludes_deleted_rows(self) -> None:
        self._create_listing(status=self.active_status)
        self._create_listing(status=self.deleted_status)

        rows = build_my_listings_rows(self.owner)

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].status_name, "Active")

    def test_edit_listing_view_rejects_non_owner(self) -> None:
        listing = self._create_listing(status=self.active_status)
        self.client.force_login(self.other_user)

        response = self.client.get(reverse("edit_listing", args=[listing.listing_id]))

        self.assertEqual(response.status_code, 403)

    def test_delete_listing_marks_status_deleted(self) -> None:
        listing = self._create_listing(status=self.active_status)
        self.client.force_login(self.owner)

        response = self.client.post(reverse("delete_listing", args=[listing.listing_id]))

        listing.refresh_from_db()
        self.assertEqual(response.status_code, 302)
        self.assertEqual(listing.status.status_name, "Deleted")

    def test_delete_listing_rejects_frozen_listing(self) -> None:
        listing = self._create_listing(status=self.frozen_status)
        self.client.force_login(self.owner)

        response = self.client.post(reverse("delete_listing", args=[listing.listing_id]))

        self.assertEqual(response.status_code, 403)
