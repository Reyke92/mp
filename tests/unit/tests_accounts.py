from __future__ import annotations

from django.test import RequestFactory

from accounts.forms import LoginForm, ProfileForm, RegisterForm
from accounts.utils.auth import authenticate_with_email, is_user_administrator, is_user_moderator
from tests.common import MarketplaceTestCase


class AccountFormAndAuthUnitTests(MarketplaceTestCase):
    def setUp(self) -> None:
        self.factory = RequestFactory()
        self.world = self.create_basic_listing_world()

    def test_register_form_rejects_duplicate_email(self) -> None:
        self.create_user(email="duplicate@example.com")

        form = RegisterForm(
            data={
                "email": "duplicate@example.com",
                "first_name": "Alice",
                "last_name": "Smith",
                "password1": "Password123!",
                "password2": "Password123!",
                "city_name": self.world.city.city_name,
                "state_name": self.world.state.state_name,
            }
        )

        self.assertFalse(form.is_valid())
        self.assertIn("email", form.errors)

    def test_register_form_rejects_non_alpha_names(self) -> None:
        form = RegisterForm(
            data={
                "email": "new@example.com",
                "first_name": "Alice1",
                "last_name": "Smith",
                "password1": "Password123!",
                "password2": "Password123!",
                "city_name": self.world.city.city_name,
                "state_name": self.world.state.state_name,
            }
        )

        self.assertFalse(form.is_valid())
        self.assertIn("first_name", form.errors)

    def test_register_form_rejects_password_mismatch(self) -> None:
        form = RegisterForm(
            data={
                "email": "new@example.com",
                "first_name": "Alice",
                "last_name": "Smith",
                "password1": "Password123!",
                "password2": "Different123!",
                "city_name": self.world.city.city_name,
                "state_name": self.world.state.state_name,
            }
        )

        self.assertFalse(form.is_valid())
        self.assertIn("password2", form.errors)

    def test_login_form_accepts_expected_fields(self) -> None:
        form = LoginForm(data={"email": "user@example.com", "password": "secret"})
        self.assertTrue(form.is_valid())

    def test_profile_form_accepts_basic_text_fields(self) -> None:
        form = ProfileForm(
            data={
                "first_name": "Alice",
                "last_name": "Smith",
                "bio": "Short bio.",
                "city_name": self.world.city.city_name,
                "state_name": self.world.state.state_name,
            }
        )
        self.assertTrue(form.is_valid())

    def test_authenticate_with_email_returns_matching_user(self) -> None:
        request = self.factory.post("/login/")
        self.create_user(email="login@example.com")

        user = authenticate_with_email(request, "login@example.com", self.password)

        self.assertIsNotNone(user)
        self.assertEqual(user.username, "login@example.com")

    def test_role_helpers_reflect_current_assignments(self) -> None:
        moderator = self.create_user(email="moderator@example.com")
        administrator = self.create_user(email="administrator@example.com")
        self.assign_role(user=moderator, role_name="Moderator")
        self.assign_role(user=administrator, role_name="Administrator")

        self.assertTrue(is_user_moderator(moderator))
        self.assertFalse(is_user_administrator(moderator))
        self.assertTrue(is_user_administrator(administrator))
        self.assertFalse(is_user_moderator(administrator))
