from __future__ import annotations

from unittest import skip

from django.test import SimpleTestCase


@skip("Manual Playwright timing verification per the Software Testing Document.")
class ModerationPerformanceTests(SimpleTestCase):
    # The testing plan calls for manual browser timing for moderation workflows.

    def test_moderation_queue_page_timing(self) -> None:
        # TC-PERF-006: load the moderation queue within the documented target.
        self.fail("Manual performance test placeholder.")

    def test_report_review_page_timing(self) -> None:
        # TC-PERF-007: open a single report for review within the documented target.
        self.fail("Manual performance test placeholder.")
