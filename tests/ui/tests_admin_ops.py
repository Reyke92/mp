from __future__ import annotations

from unittest import skip

from django.test import SimpleTestCase


@skip("Manual UI verification per the Software Testing Document.")
class AdminOpsUiTests(SimpleTestCase):
    # These cover table readability, selected-card flows, and action clarity.

    def test_user_and_listing_management_ui(self) -> None:
        self.fail("Manual UI test placeholder.")

    def test_moderation_and_administration_log_ui(self) -> None:
        self.fail("Manual UI test placeholder.")
