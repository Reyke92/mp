from __future__ import annotations

from pathlib import Path

from django.conf import settings
from django.test import override_settings
from django.urls import reverse

from accounts.models import UserProfile
from tests.common import MarketplaceTestCase


class AccountViewIntegrationTests(MarketplaceTestCase):
    def setUp(self) -> None:
        self.world = self.create_basic_listing_world()
        self.user = self.create_user(
            email="user@example.com",
            first_name="Alice",
            last_name="Smith",
            with_profile=True,
            city=self.world.city,
        )
        self.admin = self.create_user(
            email="admin@example.com",
            first_name="Admin",
            last_name="Person",
            with_profile=True,
            city=self.world.city,
        )
        self.moderator = self.create_user(
            email="moderator@example.com",
            first_name="Mod",
            last_name="Person",
            with_profile=True,
            city=self.world.city,
        )
        self.assign_role(user=self.admin, role_name="Administrator")
        self.assign_role(user=self.moderator, role_name="Moderator")

    @override_settings(MEDIA_ROOT="/tmp/marketplace-test-media")
    def test_register_view_creates_user_and_profile(self) -> None:
        media_root = Path(settings.MEDIA_ROOT)
        media_root.mkdir(parents=True, exist_ok=True)
        (media_root / "DefaultAvatar.png").write_bytes(b"avatar")

        response = self.client.post(
            reverse("register"),
            data={
                "email": "newuser@example.com",
                "first_name": "New",
                "last_name": "User",
                "password1": "Password123!",
                "password2": "Password123!",
                "city_name": self.world.city.city_name,
                "state_name": self.world.state.state_name,
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertTrue(UserProfile.objects.filter(user__username="newuser@example.com").exists())

    def test_login_view_rejects_invalid_credentials_with_generic_error(self) -> None:
        response = self.client.post(
            reverse("login"),
            data={"email": self.user.username, "password": "wrong-password"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Invalid email or password.")

    def test_login_and_logout_flow_updates_session_access(self) -> None:
        login_response = self.client.post(
            reverse("login"),
            data={"email": self.user.username, "password": self.password},
        )
        self.assertEqual(login_response.status_code, 302)

        profile_response = self.client.get(reverse("profile"))
        self.assertEqual(profile_response.status_code, 200)

        logout_response = self.client.post(reverse("logout"))
        self.assertEqual(logout_response.status_code, 302)

        redirected_response = self.client.get(reverse("profile"))
        self.assertEqual(redirected_response.status_code, 302)

    def test_edit_profile_view_updates_profile_and_user_names(self) -> None:
        self.client.force_login(self.user)

        response = self.client.post(
            reverse("profile"),
            data={
                "first_name": "Updated",
                "last_name": "Name",
                "bio": "Updated biography.",
                "city_name": self.world.city.city_name,
                "state_name": self.world.state.state_name,
            },
        )

        self.assertEqual(response.status_code, 302)
        self.user.refresh_from_db()
        profile = UserProfile.objects.get(user=self.user)
        self.assertEqual(self.user.first_name, "Updated")
        self.assertEqual(profile.bio, "Updated biography.")

    def test_view_profile_view_returns_404_for_regular_user(self) -> None:
        self.client.force_login(self.user)

        response = self.client.get(reverse("view_profile", kwargs={"id": int(self.user.id)}))

        self.assertEqual(response.status_code, 404)

    def test_view_profile_view_allows_administrator(self) -> None:
        self.client.force_login(self.admin)

        response = self.client.get(reverse("view_profile", kwargs={"id": int(self.user.id)}))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["viewed_user"].id, self.user.id)
