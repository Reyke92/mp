from __future__ import annotations

from pathlib import Path
from unittest import skip

from django.test import SimpleTestCase


@skip("Manual Playwright timing verification per the Software Testing Document. Run tests/performance/playwright_manual_performance.py instead.")
class AdminOpsPerformanceTests(SimpleTestCase):
    def test_manual_runner_exists_for_admin_reporting_timing(self) -> None:
        runner_path = Path(__file__).with_name("playwright_manual_performance.py")
        self.assertTrue(runner_path.exists())


