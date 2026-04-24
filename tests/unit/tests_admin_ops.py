from __future__ import annotations

from admin_ops.models import AdministrationAction, UserRoleAssignment
from admin_ops.utils.listing_management import is_listing_frozen, perform_listing_management_action
from admin_ops.utils.roles import _user_has_role, is_user_administrator, is_user_moderator
from admin_ops.utils.user_management import perform_user_management_action
from tests.common import MarketplaceTestCase


class AdminOpsUnitTests(MarketplaceTestCase):
    def setUp(self) -> None:
        self.world = self.create_basic_listing_world()
        self.seed_admin_action_types()
        self.admin = self.create_user(email="admin@example.com")
        self.moderator = self.create_user(email="moderator@example.com")
        self.target = self.create_user(email="target@example.com")
        self.seller = self.create_user(email="seller@example.com")
        self.assign_role(user=self.admin, role_name="Administrator")
        self.assign_role(user=self.moderator, role_name="Moderator")
        self.listing = self.create_listing(seller_user=self.seller, world=self.world, status=self.world.active_status)

    def test_role_helpers_use_current_role_assignments(self) -> None:
        self.assertTrue(_user_has_role(self.admin, "Administrator"))
        self.assertTrue(is_user_administrator(self.admin))
        self.assertTrue(is_user_moderator(self.moderator))
        self.assertFalse(is_user_administrator(self.target))

    def test_perform_user_management_action_assigns_and_unassigns_moderator(self) -> None:
        assign_message = perform_user_management_action(
            requesting_user_id=int(self.admin.id),
            target_user_id=int(self.target.id),
            action_name="assign_moderator",
        )
        self.assertIn("Moderator", assign_message)
        self.assertTrue(UserRoleAssignment.objects.filter(user=self.target, role__role_name="Moderator").exists())

        unassign_message = perform_user_management_action(
            requesting_user_id=int(self.admin.id),
            target_user_id=int(self.target.id),
            action_name="unassign_moderator",
        )
        self.assertIn("removed", unassign_message.lower())
        self.assertFalse(UserRoleAssignment.objects.filter(user=self.target, role__role_name="Moderator").exists())

    def test_perform_user_management_action_bans_and_unbans_user_with_audit_rows(self) -> None:
        perform_user_management_action(
            requesting_user_id=int(self.admin.id),
            target_user_id=int(self.target.id),
            action_name="ban_user",
        )
        self.target.refresh_from_db()
        self.assertFalse(self.target.is_active)

        perform_user_management_action(
            requesting_user_id=int(self.admin.id),
            target_user_id=int(self.target.id),
            action_name="unban_user",
        )
        self.target.refresh_from_db()
        self.assertTrue(self.target.is_active)

        action_names = list(
            AdministrationAction.objects.filter(target_user=self.target)
            .order_by("created_at")
            .values_list("action_type__action_type_name", flat=True)
        )
        self.assertIn("BanUser", action_names)
        self.assertIn("UnbanUser", action_names)

    def test_perform_listing_management_action_freezes_and_unfreezes_listing(self) -> None:
        perform_listing_management_action(
            requesting_user_id=int(self.admin.id),
            target_listing_id=int(self.listing.listing_id),
            action_name="freeze_listing",
        )
        self.assertTrue(is_listing_frozen(self.listing))

        perform_listing_management_action(
            requesting_user_id=int(self.admin.id),
            target_listing_id=int(self.listing.listing_id),
            action_name="unfreeze_listing",
        )
        self.assertFalse(is_listing_frozen(self.listing))
