from __future__ import annotations

from unittest import skip

from django.test import SimpleTestCase


@skip("Manual UI verification per the Software Testing Document.")
class CoreUiTests(SimpleTestCase):
    # These cover layout consistency and navigation clarity.

    def test_home_and_search_layouts(self) -> None:
        self.fail("Manual UI test placeholder.")

    def test_sidebar_navigation_and_active_states(self) -> None:
        self.fail("Manual UI test placeholder.")
