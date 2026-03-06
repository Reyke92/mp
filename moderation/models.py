"""
Auto-generated Django models for the `moderation` app.

Source of truth: MySQL schema in db_schema.sql.
These models are mapped 1:1 to existing database tables and are managed by Django migrations (managed = True).
"""
from django.conf import settings
from django.utils import timezone
from django.db import models


class ModerationActionType(models.Model):
    action_type_id = models.BigAutoField(primary_key=True, db_column='action_type_id')
    action_type_name = models.CharField(max_length=30, unique=True, db_column='action_type_name')

    class Meta:
        managed = True
        db_table = 'moderation_action_type'


class ModerationAction(models.Model):
    action_id = models.BigAutoField(primary_key=True, db_column='action_id')
    actor_user = models.ForeignKey(settings.AUTH_USER_MODEL, models.RESTRICT, db_column='actor_user_id', related_name='moderation_actions_as_actor')
    action_type = models.ForeignKey('moderation.ModerationActionType', models.RESTRICT, db_column='action_type_id')
    listing = models.ForeignKey('listings.Listing', models.RESTRICT, null=True, blank=True, db_column='listing_id')
    target_user = models.ForeignKey(settings.AUTH_USER_MODEL, models.RESTRICT, null=True, blank=True, db_column='target_user_id')
    notes = models.TextField(null=True, blank=True, db_column='notes')
    created_at = models.DateTimeField(default=timezone.now, db_column='created_at')

    class Meta:
        managed = True
        db_table = 'moderation_actions'
        indexes = [
            models.Index(fields=['actor_user'], name='ix_mod_actions_actor'),
            models.Index(fields=['listing'], name='ix_mod_actions_listing'),
            models.Index(fields=['target_user'], name='ix_mod_actions_target_user'),
            models.Index(fields=['action_type'], name='fk_mod_actions_action_type'),
        ]
