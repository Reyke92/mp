from __future__ import annotations

from unittest import skip

from django.test import SimpleTestCase


@skip("Manual system verification per the Software Testing Document.")
class AccountSystemTests(SimpleTestCase):
    # These scenarios are intended for browser walkthroughs.

    def test_register_login_logout_end_to_end(self) -> None:
        self.fail("Manual system test placeholder.")

    def test_profile_edit_end_to_end(self) -> None:
        self.fail("Manual system test placeholder.")
