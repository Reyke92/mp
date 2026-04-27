from __future__ import annotations

from typing import Any

from django.db import transaction

from reports.models import Report


def create_report(*, reporter: Any, status: Any, listing: Any = None, conversation: Any = None, details: str | None = None) -> Report:
    """Create a report using the lowest available non-negative report ID."""
    with transaction.atomic():
        next_report_id = _get_next_available_report_id()
        report = Report(
            report_id=next_report_id,
            reporter_user=reporter,
            status=status,
            listing=listing,
            conversation=conversation,
            details=details,
        )
        report.save(force_insert=True)
        return report


def _get_next_available_report_id() -> int:
    """Return the lowest available non-negative report ID.

    The project database design permits storing ID 0 as a real entity value, so
    report creation must not assume MySQL's default 1-based AUTO_INCREMENT
    behavior.
    """
    existing_ids = list(
        Report.objects.select_for_update()
        .order_by("report_id")
        .values_list("report_id", flat=True)
    )

    expected_id = 0
    for current_id in existing_ids:
        normalized_id = int(current_id)
        if normalized_id < expected_id:
            continue
        if normalized_id != expected_id:
            break
        expected_id += 1

    return expected_id
