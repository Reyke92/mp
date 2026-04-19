from __future__ import annotations

from django.test import Client
from django.urls import reverse

from tests.common import MarketplaceTestCase


class AdminOpsSecurityTests(MarketplaceTestCase):
    def setUp(self) -> None:
        self.world = self.create_basic_listing_world()
        self.seed_admin_action_types()
        self.admin = self.create_user(email="admin@example.com", with_profile=True, city=self.world.city)
        self.other_admin = self.create_user(email="other-admin@example.com", with_profile=True, city=self.world.city)
        self.user = self.create_user(email="user@example.com", with_profile=True, city=self.world.city)
        self.assign_role(user=self.admin, role_name="Administrator")
        self.assign_role(user=self.other_admin, role_name="Administrator")
        self.listing = self.create_listing(seller_user=self.user, world=self.world)

    def test_standard_user_cannot_access_admin_pages(self) -> None:
        self.client.force_login(self.user)

        for route_name in ("user_management", "listing_management", "moderation_log", "administration_log"):
            response = self.client.get(reverse(route_name))
            self.assertEqual(response.status_code, 403)

    def test_administrator_cannot_ban_self(self) -> None:
        self.client.force_login(self.admin)
        response = self.client.post(
            reverse("user_management"),
            data={"action": "ban_user", "target_user_id": int(self.admin.id)},
            follow=True,
        )

        self.admin.refresh_from_db()
        self.assertTrue(self.admin.is_active)
        self.assertContains(response, "cannot")

    def test_administrator_cannot_ban_another_administrator(self) -> None:
        self.client.force_login(self.admin)
        response = self.client.post(
            reverse("user_management"),
            data={"action": "ban_user", "target_user_id": int(self.other_admin.id)},
            follow=True,
        )

        self.other_admin.refresh_from_db()
        self.assertTrue(self.other_admin.is_active)
        self.assertContains(response, "Administrator")

    def test_csrf_protects_admin_post_actions(self) -> None:
        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.force_login(self.admin)
        response = csrf_client.post(
            reverse("listing_management"),
            data={"action": "freeze_listing", "target_listing_id": int(self.listing.listing_id)},
        )
        self.assertEqual(response.status_code, 403)
