from __future__ import annotations

from unittest import skip

from django.test import SimpleTestCase


@skip("Manual UI verification per the Software Testing Document.")
class ListingUiTests(SimpleTestCase):
    # These cover editor clarity, image management, and status visibility.

    def test_create_and_edit_listing_ui(self) -> None:
        self.fail("Manual UI test placeholder.")

    def test_listing_detail_gallery_and_status_ui(self) -> None:
        self.fail("Manual UI test placeholder.")
