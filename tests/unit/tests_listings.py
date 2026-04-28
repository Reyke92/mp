from __future__ import annotations

from django.core.exceptions import PermissionDenied
from django.test import RequestFactory
from django.urls import reverse

from catalog.models import Attribute, AttributeValueType
from listings.forms import CreateListingForm
from listings.models import ListingAttributeValue
from listings.utils import (
    build_my_listings_rows,
    can_view_listing,
    create_listing_from_form,
    mark_listing_deleted_by_owner,
)
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
        # TC-SRCH-003 / TC-SEC-007: owners can view frozen listings but not deleted listings.
        frozen_listing = self.create_listing(seller_user=self.owner, world=self.world, status=self.world.frozen_status)
        deleted_listing = self.create_listing(seller_user=self.owner, world=self.world, status=self.world.deleted_status)

        self.assertTrue(can_view_listing(listing=frozen_listing, viewer=self.owner))
        self.assertFalse(can_view_listing(listing=deleted_listing, viewer=self.owner))

    def test_moderator_can_view_deleted_listing(self) -> None:
        # TC-SRCH-003 / TC-RBAC-001: moderators retain privileged access to deleted listings.
        deleted_listing = self.create_listing(seller_user=self.owner, world=self.world, status=self.world.deleted_status)
        self.assertTrue(can_view_listing(listing=deleted_listing, viewer=self.moderator))

    def test_administrator_can_view_frozen_and_deleted_listing(self) -> None:
        # TC-SRCH-003 / TC-RBAC-001: administrators retain privileged access to non-public listings.
        frozen_listing = self.create_listing(seller_user=self.owner, world=self.world, status=self.world.frozen_status)
        deleted_listing = self.create_listing(seller_user=self.owner, world=self.world, status=self.world.deleted_status)

        self.assertTrue(can_view_listing(listing=frozen_listing, viewer=self.administrator))
        self.assertTrue(can_view_listing(listing=deleted_listing, viewer=self.administrator))

    def test_my_listings_excludes_deleted_rows(self) -> None:
        # TC-LIST-005: seller listing management excludes soft-deleted rows.
        self.create_listing(seller_user=self.owner, world=self.world, status=self.world.active_status)
        self.create_listing(seller_user=self.owner, world=self.world, status=self.world.deleted_status)

        rows = build_my_listings_rows(self.owner)

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].status_name, "Active")

    def test_mark_listing_deleted_by_owner_rejects_non_owner(self) -> None:
        # TC-LIST-003 / TC-LIST-005: non-owners cannot delete another seller's listing.
        listing = self.create_listing(seller_user=self.owner, world=self.world, status=self.world.active_status)

        with self.assertRaises(PermissionDenied):
            mark_listing_deleted_by_owner(listing=listing, owner_user=self.other_user)

    def test_mark_listing_deleted_by_owner_rejects_frozen_listing(self) -> None:
        # TC-LIST-006: frozen listings cannot be deleted by the seller.
        listing = self.create_listing(seller_user=self.owner, world=self.world, status=self.world.frozen_status)

        with self.assertRaises(PermissionDenied):
            mark_listing_deleted_by_owner(listing=listing, owner_user=self.owner)

    def test_create_listing_form_rejects_parent_category_selection(self) -> None:
        # TC-ATTR-001 / TC-SEC-009: listing forms require a precise child category.
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
        # TC-SEC-009: server-side validation rejects invalid city/state combinations.
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

    def test_create_listing_form_loads_selected_category_attributes(self) -> None:
        # TC-ATTR-001: selecting a category loads only that category's dynamic attributes.
        attribute, _value_type = self.create_attribute_schema(category=self.world.child_category)

        form = CreateListingForm(selected_category_id=int(self.world.child_category.category_id))

        field_name = f"attr_{int(attribute.attribute_id)}_value"
        self.assertIn(field_name, form.fields)
        self.assertEqual(len(form.attribute_field_groups), 1)
        self.assertEqual(form.attribute_field_groups[0].attribute_key, "brand")

    def test_create_listing_from_form_persists_integer_attribute_to_integer_field_only(self) -> None:
        # TC-ATTR-002 / TC-DATA-005: valid typed attributes persist in the correct value column.
        value_type, _ = AttributeValueType.objects.get_or_create(value_type_name="integer")
        attribute = Attribute.objects.create(
            category=self.world.child_category,
            attribute_key="ram_gb",
            value_type=value_type,
        )
        field_name = f"attr_{int(attribute.attribute_id)}_value"
        form = CreateListingForm(
            data={
                "title": "Developer laptop",
                "price_amount": "700.00",
                "category": str(self.world.child_category.category_id),
                "condition": str(self.world.condition.condition_id),
                "city_name": self.world.city.city_name,
                "state": str(self.world.state.state_id),
                "description": "A fast laptop with enough detail for listing validation.",
                field_name: "16",
            }
        )

        self.assertTrue(form.is_valid(), form.errors)
        listing = create_listing_from_form(form=form, seller_user=self.owner)
        attribute_value = ListingAttributeValue.objects.get(listing=listing, attribute=attribute)

        self.assertEqual(attribute_value.value_int, 16)
        self.assertIsNone(attribute_value.value_decimal)
        self.assertIsNone(attribute_value.value_datetime)
        self.assertIsNone(attribute_value.value_text_id)
        self.assertIsNone(attribute_value.value_bool)

    def test_create_listing_form_rejects_negative_dynamic_integer_attribute(self) -> None:
        # TC-ATTR-003 / TC-DATA-006: invalid typed attribute input is rejected before persistence.
        value_type, _ = AttributeValueType.objects.get_or_create(value_type_name="integer")
        attribute = Attribute.objects.create(
            category=self.world.child_category,
            attribute_key="battery_cycles",
            value_type=value_type,
        )

        form = CreateListingForm(
            data={
                "title": "Battery test laptop",
                "price_amount": "250.00",
                "category": str(self.world.child_category.category_id),
                "condition": str(self.world.condition.condition_id),
                "city_name": self.world.city.city_name,
                "state": str(self.world.state.state_id),
                "description": "A laptop listing with enough description text for validation.",
                f"attr_{int(attribute.attribute_id)}_value": "-1",
            }
        )

        self.assertFalse(form.is_valid())
        self.assertIn(f"attr_{int(attribute.attribute_id)}_value", form.errors)
