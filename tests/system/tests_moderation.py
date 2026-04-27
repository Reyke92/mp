from __future__ import annotations

from unittest import skip

from django.test import SimpleTestCase


@skip("Manual system verification per the Software Testing Document.")
class ModerationSystemTests(SimpleTestCase):
    # System-level moderation flows are verified through browser walkthroughs.

    def test_queue_to_report_review_flow(self) -> None:
        # TC-MOD-001 manual system path.
        self.fail("Manual system test placeholder.")

    def test_recording_disposition_end_to_end(self) -> None:
        # TC-MOD-002 manual system path.
        self.fail("Manual system test placeholder.")
