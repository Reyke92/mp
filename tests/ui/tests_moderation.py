from __future__ import annotations

from unittest import skip

from django.test import SimpleTestCase


@skip("Manual UI verification per the Software Testing Document.")
class ModerationUiTests(SimpleTestCase):
    # These focus on queue readability, report-review clarity, and action prominence.

    def test_moderation_queue_ui(self) -> None:
        # TC-UI-006 / TC-UI-008 representative moderation surface.
        self.fail("Manual UI test placeholder.")

    def test_report_review_ui(self) -> None:
        # TC-UI-006 representative disposition screen.
        self.fail("Manual UI test placeholder.")
