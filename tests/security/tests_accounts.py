from __future__ import annotations

from django.test import Client
from django.urls import reverse

from tests.common import MarketplaceTestCase


class AccountSecurityTests(MarketplaceTestCase):
    def setUp(self) -> None:
        self.world = self.create_basic_listing_world()
        self.user = self.create_user(email="user@example.com", with_profile=True, city=self.world.city)
        self.admin = self.create_user(email="admin@example.com", with_profile=True, city=self.world.city)
        self.assign_role(user=self.admin, role_name="Administrator")

    def test_guest_cannot_access_profile_edit_page(self) -> None:
        response = self.client.get(reverse("profile"))
        self.assertEqual(response.status_code, 302)

    def test_regular_user_receives_404_for_internal_view_profile_endpoint(self) -> None:
        self.client.force_login(self.user)
        response = self.client.get(reverse("view_profile", kwargs={"id": int(self.user.id)}))
        self.assertEqual(response.status_code, 404)

    def test_banned_user_cannot_authenticate(self) -> None:
        self.user.is_active = False
        self.user.save(update_fields=["is_active"])

        response = self.client.post(
            reverse("login"),
            data={"email": self.user.username, "password": self.password},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Invalid email or password.")

    def test_csrf_protects_logout_post(self) -> None:
        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.force_login(self.user)

        response = csrf_client.post(reverse("logout"))

        self.assertEqual(response.status_code, 403)
