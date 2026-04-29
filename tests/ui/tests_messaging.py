from __future__ import annotations

from pathlib import Path
from unittest import skip

from django.test import SimpleTestCase


@skip("UI tests are executed through Playwright. Run tests/ui/playwright_manual_ui.py.")
class PlaywrightUiRunnerPointerTests(SimpleTestCase):
    def test_playwright_ui_runner_exists(self) -> None:
        runner_path = Path(__file__).with_name("playwright_manual_ui.py")
        self.assertTrue(runner_path.exists())
