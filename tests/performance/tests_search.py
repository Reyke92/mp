from __future__ import annotations

from unittest import skip

from django.test import SimpleTestCase


@skip("Manual Playwright timing verification per the Software Testing Document.")
class SearchPerformanceTests(SimpleTestCase):
    # Use Playwright with Chromium for timing representative search flows.

    def test_search_results_first_page_timing(self) -> None:
        self.fail("Manual performance test placeholder.")

    def test_listing_detail_timing(self) -> None:
        self.fail("Manual performance test placeholder.")
