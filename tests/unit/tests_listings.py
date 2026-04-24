from __future__ import annotations

from django.core.exceptions import PermissionDenied
from django.test import RequestFactory
from django.urls import reverse

from admin_ops.models import Role, UserRoleAssignment
from listings.forms import CreateListingForm
from listings.models import ListingStatus
from listings.utils import build_my_listings_rows, can_view_listing, mark_listing_deleted_by_owner
from tests.common import MarketplaceTestCase


class ListingAccessAndLifecycleTests(MarketplaceTestCase):
    def setUp(self) -> None:
        self.factory = RequestFactory()
        self.world = self.create_basic_listing_world()
        self.owner = self.create_user(email="owner@example.com")
        self.other_user = self.create_user(email="other@example.com")
        self.moderator = self.create_user(email="moderator@example.com")
        self.administrator = self.create_user(email="administrator@example.com")
        self.assign_role(user=self.moderator, role_name="Moderator")
        self.assign_role(user=self.administrator, role_name="Administrator")

    def test_owner_can_view_frozen_listing_but_not_deleted_listing(self) -> None:
        frozen_listing = self.create_listing(seller_user=self.owner, world=self.world, status=self.world.frozen_status)
        deleted_listing = self.create_listing(seller_user=self.owner, world=self.world, status=self.world.deleted_status)

        self.assertTrue(can_view_listing(listing=frozen_listing, viewer=self.owner))
        self.assertFalse(can_view_listing(listing=deleted_listing, viewer=self.owner))

    def test_moderator_can_view_deleted_listing(self) -> None:
        deleted_listing = self.create_listing(seller_user=self.owner, world=self.world, status=self.world.deleted_status)
        self.assertTrue(can_view_listing(listing=deleted_listing, viewer=self.moderator))

    def test_administrator_can_view_frozen_and_deleted_listing(self) -> None:
        frozen_listing = self.create_listing(seller_user=self.owner, world=self.world, status=self.world.frozen_status)
        deleted_listing = self.create_listing(seller_user=self.owner, world=self.world, status=self.world.deleted_status)

        self.assertTrue(can_view_listing(listing=frozen_listing, viewer=self.administrator))
        self.assertTrue(can_view_listing(listing=deleted_listing, viewer=self.administrator))

    def test_my_listings_excludes_deleted_rows(self) -> None:
        self.create_listing(seller_user=self.owner, world=self.world, status=self.world.active_status)
        self.create_listing(seller_user=self.owner, world=self.world, status=self.world.deleted_status)

        rows = build_my_listings_rows(self.owner)

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].status_name, "Active")

    def test_mark_listing_deleted_by_owner_rejects_non_owner(self) -> None:
        listing = self.create_listing(seller_user=self.owner, world=self.world, status=self.world.active_status)

        with self.assertRaises(PermissionDenied):
            mark_listing_deleted_by_owner(listing=listing, owner_user=self.other_user)

    def test_mark_listing_deleted_by_owner_rejects_frozen_listing(self) -> None:
        listing = self.create_listing(seller_user=self.owner, world=self.world, status=self.world.frozen_status)

        with self.assertRaises(PermissionDenied):
            mark_listing_deleted_by_owner(listing=listing, owner_user=self.owner)

    def test_create_listing_form_rejects_parent_category_selection(self) -> None:
        form = CreateListingForm(
            data={
                "title": "Gaming laptop",
                "price_amount": "500.00",
                "category": str(self.world.parent_category.category_id),
                "condition": str(self.world.condition.condition_id),
                "city_name": self.world.city.city_name,
                "state": str(self.world.state.state_id),
                "description": "This laptop works well and includes the charger.",
            }
        )

        self.assertFalse(form.is_valid())
        self.assertIn("category", form.errors)

    def test_create_listing_form_rejects_unknown_city_in_selected_state(self) -> None:
        form = CreateListingForm(
            data={
                "title": "Gaming laptop",
                "price_amount": "500.00",
                "category": str(self.world.child_category.category_id),
                "condition": str(self.world.condition.condition_id),
                "city_name": "Unknown City",
                "state": str(self.world.state.state_id),
                "description": "This laptop works well and includes the charger.",
            }
        )

        self.assertFalse(form.is_valid())
        self.assertIn("city_name", form.errors)
