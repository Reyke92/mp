from __future__ import annotations

from unittest import skip

from django.test import SimpleTestCase


@skip("Manual system verification per the Software Testing Document.")
class ListingSystemTests(SimpleTestCase):
    # These scenarios map to create/edit/delete and browse flows.

    def test_create_listing_full_browser_flow(self) -> None:
        self.fail("Manual system test placeholder.")

    def test_edit_listing_full_browser_flow(self) -> None:
        self.fail("Manual system test placeholder.")

    def test_search_and_listing_detail_full_browser_flow(self) -> None:
        self.fail("Manual system test placeholder.")
