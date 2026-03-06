"""
Auto-generated Django models for the `reports` app.

Source of truth: MySQL schema in db_schema.sql.
These models are mapped 1:1 to existing database tables and are managed by Django migrations (managed = True).
"""
from django.conf import settings
from django.utils import timezone
from django.db import models


class Report(models.Model):
    report_id = models.BigAutoField(primary_key=True, db_column='report_id')
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


class ReportStatus(models.Model):
    status_id = models.BigAutoField(primary_key=True, db_column='status_id')
    status_name = models.CharField(max_length=30, unique=True, db_column='status_name')

    class Meta:
        managed = True
        db_table = 'report_status'
