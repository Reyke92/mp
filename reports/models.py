"""
Auto-generated Django models for the `reports` app.

Source of truth: MySQL schema in db_schema.sql.
These models are mapped 1:1 to existing database tables and are managed by Django migrations (managed = True).
"""
from django.conf import settings
from django.utils import timezone
from django.db import models, transaction
from common.fields import UnsignedBigAutoField


class Report(models.Model):
    report_id = UnsignedBigAutoField(primary_key=True, db_column='report_id')
    reporter_user = models.ForeignKey(settings.AUTH_USER_MODEL, models.RESTRICT, db_column='reporter_user_id')
    conversation = models.ForeignKey('messaging.Conversation', models.RESTRICT, null=True, blank=True, db_column='conversation_id')
    listing = models.ForeignKey('listings.Listing', models.RESTRICT, null=True, blank=True, db_column='listing_id')
    action = models.ForeignKey('moderation.ModerationAction', models.RESTRICT, null=True, blank=True, db_column='action_id')
    status = models.ForeignKey('reports.ReportStatus', models.RESTRICT, db_column='status_id')
    details = models.TextField(null=True, blank=True, db_column='details')
    created_at = models.DateTimeField(default=timezone.now, db_column='created_at')

    class Meta:
        managed = True
        db_table = 'reports'
        indexes = [
            models.Index(fields=['reporter_user'], name='ix_reports_reporter'),
            models.Index(fields=['conversation'], name='ix_reports_conversation'),
            models.Index(fields=['listing'], name='ix_reports_listing'),
            models.Index(fields=['action'], name='fk_reports_action'),
            models.Index(fields=['status'], name='fk_reports_status'),
        ]

    def save(self, *args, **kwargs):
        if self._state.adding and self.report_id is None:
            with transaction.atomic():
                self.report_id = self._allocate_next_report_id()
                return super().save(*args, **kwargs)

        return super().save(*args, **kwargs)

    @classmethod
    def _allocate_next_report_id(cls) -> int:
        next_report_id: int = 0
        existing_ids = cls.objects.select_for_update().order_by('report_id').values_list('report_id', flat=True)

        for existing_id in existing_ids:
            current_id = int(existing_id)

            if current_id < next_report_id:
                continue

            if current_id != next_report_id:
                break

            next_report_id += 1

        return next_report_id


class ReportStatus(models.Model):
    status_id = UnsignedBigAutoField(primary_key=True, db_column='status_id')
    status_name = models.CharField(max_length=30, unique=True, db_column='status_name')

    class Meta:
        managed = True
        db_table = 'report_status'
