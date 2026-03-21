"""
Django models for the `admin_ops` app.

This version preserves the existing role-assignment tables and adds:
- administration_action_type
- administration_actions
"""
from django.conf import settings
from django.utils import timezone
from django.db import models
from common.fields import UnsignedBigAutoField


class Role(models.Model):
    role_id = UnsignedBigAutoField(primary_key=True, db_column='role_id')
    role_name = models.CharField(max_length=50, unique=True, db_column='role_name')

    class Meta:
        managed = True
        db_table = 'roles'


class UserRoleAssignment(models.Model):
    id = UnsignedBigAutoField(primary_key=True, db_column='id')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, models.CASCADE, db_column='user_id')
    role = models.ForeignKey('admin_ops.Role', models.CASCADE, db_column='role_id')
    assigned_at = models.DateTimeField(default=timezone.now, db_column='assigned_at')

    class Meta:
        managed = True
        db_table = 'user_role_assignments'
        constraints = [
            models.UniqueConstraint(fields=['user', 'role'], name='user_id'),
        ]
        indexes = [
            models.Index(fields=['role'], name='ix_ura_role'),
        ]


class AdministrationActionType(models.Model):
    action_type_id = UnsignedBigAutoField(primary_key=True, db_column='action_type_id')
    action_type_name = models.CharField(max_length=30, unique=True, db_column='action_type_name')

    class Meta:
        managed = True
        db_table = 'administration_action_type'


class AdministrationAction(models.Model):
    action_id = UnsignedBigAutoField(primary_key=True, db_column='action_id')
    actor_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        models.RESTRICT,
        db_column='actor_user_id',
        related_name='administration_actions_as_actor',
    )
    action_type = models.ForeignKey(
        'admin_ops.AdministrationActionType',
        models.RESTRICT,
        db_column='action_type_id',
    )
    listing = models.ForeignKey(
        'listings.Listing',
        models.SET_NULL,
        null=True,
        blank=True,
        db_column='listing_id',
    )

    target_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        models.SET_NULL,
        null=True,
        blank=True,
        db_column='target_user_id',
        related_name='administration_actions_as_target',
    )
    notes = models.TextField(null=True, blank=True, db_column='notes')
    created_at = models.DateTimeField(default=timezone.now, db_column='created_at')

    class Meta:
        managed = True
        db_table = 'administration_actions'
        indexes = [
            models.Index(fields=['actor_user'], name='ix_admin_actions_actor'),
            models.Index(fields=['listing'], name='ix_admin_actions_listing'),
            models.Index(fields=['target_user'], name='ix_admin_actions_target_user'),
            models.Index(fields=['action_type'], name='fk_admin_actions_action_type'),
        ]
