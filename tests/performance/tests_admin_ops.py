from __future__ import annotations

from unittest import skip

from django.test import SimpleTestCase


@skip("Manual Playwright timing verification per the Software Testing Document.")
class AdminOpsPerformanceTests(SimpleTestCase):
    # Use Playwright with Chromium for timing admin pages.

    def test_user_management_page_timing(self) -> None:
        self.fail("Manual performance test placeholder.")

    def test_moderation_queue_or_log_page_timing(self) -> None:
        self.fail("Manual performance test placeholder.")
