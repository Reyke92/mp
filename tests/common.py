from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase

from accounts.models import UserProfile
from admin_ops.models import AdministrationActionType, Role, UserRoleAssignment
from catalog.models import AllowedAttributeValue, Attribute, AttributeValueType, Category, ItemCondition
from core.models import City, State, Timezone
from listings.models import Listing, ListingImage, ListingStatus
from moderation.models import ModerationAction, ModerationActionType
from reports.models import Report, ReportStatus
from tracking.models import ListingMetadataSnapshot


User = get_user_model()


@dataclass(slots=True)
class BasicListingWorld:
    state: State
    timezone: Timezone
    city: City
    parent_category: Category
    child_category: Category
    condition: ItemCondition
    active_status: ListingStatus
    frozen_status: ListingStatus
    deleted_status: ListingStatus


class MarketplaceTestCase(TestCase):
    password: str = "password123"

    def create_basic_listing_world(self) -> BasicListingWorld:
        state: State = State.objects.create(state_code="KY", state_name="Kentucky")
        timezone: Timezone = Timezone.objects.create(timezone_name="UTC-5")
        city: City = City.objects.create(
            state=state,
            city_name="Bowling Green",
            timezone=timezone,
            latitude="36.968521",
            longitude="-86.480804",
        )
        parent_category: Category = Category.objects.create(name="Electronics", slug="electronics")
        child_category: Category = Category.objects.create(
            parent_category=parent_category,
            name="Laptops",
            slug="laptops",
        )
        condition: ItemCondition = ItemCondition.objects.create(condition_name="Used")
        active_status: ListingStatus = ListingStatus.objects.create(status_name="Active")
        frozen_status: ListingStatus = ListingStatus.objects.create(status_name="Frozen")
        deleted_status: ListingStatus = ListingStatus.objects.create(status_name="Deleted")
        return BasicListingWorld(
            state=state,
            timezone=timezone,
            city=city,
            parent_category=parent_category,
            child_category=child_category,
            condition=condition,
            active_status=active_status,
            frozen_status=frozen_status,
            deleted_status=deleted_status,
        )

    def create_user(
        self,
        *,
        email: str,
        first_name: str = "Test",
        last_name: str = "User",
        is_active: bool = True,
        with_profile: bool = False,
        city: City | None = None,
    ) -> Any:
        user: Any = User.objects.create_user(
            username=email,
            email=email,
            password=self.password,
            first_name=first_name,
            last_name=last_name,
            is_active=is_active,
        )
        if with_profile:
            resolved_city: City = city if city is not None else self.create_basic_listing_world().city
            UserProfile.objects.create(user=user, city=resolved_city, bio="")
        return user

    def assign_role(self, *, user: Any, role_name: str) -> UserRoleAssignment:
        role: Role = Role.objects.create(role_name=role_name)
        return UserRoleAssignment.objects.create(user=user, role=role)

    def seed_admin_action_types(self) -> dict[str, AdministrationActionType]:
        names: tuple[str, ...] = (
            "AddRole",
            "RemoveRole",
            "BanUser",
            "UnbanUser",
            "FreezeListing",
            "UnfreezeListing",
        )
        return {
            name: AdministrationActionType.objects.create(action_type_name=name)
            for name in names
        }

    def seed_moderation_action_types(self) -> dict[str, ModerationActionType]:
        names: tuple[str, ...] = ("BanUser", "FreezeListing")
        return {
            name: ModerationActionType.objects.create(action_type_name=name)
            for name in names
        }

    def seed_report_statuses(self) -> dict[str, ReportStatus]:
        names: tuple[str, ...] = ("Received", "Resolved")
        return {
            name: ReportStatus.objects.create(status_name=name)
            for name in names
        }

    def create_listing(
        self,
        *,
        seller_user: Any,
        world: BasicListingWorld,
        status: ListingStatus | None = None,
        title: str = "Desk fan",
        description: str = "A small desk fan in good condition.",
        price_amount: str = "15.00",
        view_count: int = 0,
    ) -> Listing:
        return Listing.objects.create(
            seller_user=seller_user,
            category=world.child_category,
            condition=world.condition,
            city=world.city,
            title=title,
            description=description,
            price_amount=price_amount,
            status=status or world.active_status,
            view_count=view_count,
        )

    def create_listing_image(self, *, listing: Listing, display_order: int = 0, file_name: str = "listing.jpg") -> ListingImage:
        return ListingImage.objects.create(
            listing=listing,
            image_url=file_name,
            display_order=display_order,
        )

    def create_attribute_schema(self, *, category: Category) -> tuple[Attribute, AttributeValueType]:
        value_type: AttributeValueType = AttributeValueType.objects.create(value_type_name="text")
        attribute: Attribute = Attribute.objects.create(
            category=category,
            attribute_key="brand",
            value_type=value_type,
        )
        AllowedAttributeValue.objects.create(attribute=attribute, allowed_value_label="Lenovo")
        return attribute, value_type

    def create_snapshot(self, *, listing: Listing) -> ListingMetadataSnapshot:
        return ListingMetadataSnapshot.objects.create(
            listing=listing,
            compiled_json={
                "Title": listing.title,
                "CityName": listing.city.city_name,
                "Condition": listing.condition.condition_name,
                "CreatedAt": "2026-01-01T00:00:00",
                "StateCode": listing.city.state.state_code,
                "UpdatedAt": None,
                "Attributes": {},
                "Image": None,
                "PriceAmount": float(listing.price_amount),
                "CategoryName": listing.category.name,
            },
        )

    def create_moderation_report_for_listing(
        self,
        *,
        actor_user: Any,
        reporter_user: Any,
        listing: Listing,
        note: str = "Reviewed.",
    ) -> tuple[ModerationAction, Report]:
        action_type: ModerationActionType = ModerationActionType.objects.create(action_type_name="FreezeListing")
        report_status: ReportStatus = ReportStatus.objects.create(status_name="Received")
        action: ModerationAction = ModerationAction.objects.create(
            actor_user=actor_user,
            action_type=action_type,
            listing=listing,
            notes=note,
        )
        report: Report = Report.objects.create(
            reporter_user=reporter_user,
            listing=listing,
            action=action,
            status=report_status,
            details="Policy concern.",
        )
        return action, report
