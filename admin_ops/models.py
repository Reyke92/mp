"""
Auto-generated Django models for the `admin_ops` app.

Source of truth: MySQL schema in db_schema.sql.
These models are mapped 1:1 to existing database tables and are **not** managed by Django migrations.
"""
from django.db import models

from django.conf import settings

class Role(models.Model):
    role_id = models.BigAutoField(primary_key=True, db_column='role_id')
    role_name = models.CharField(max_length=50, unique=True, db_column='role_name')

    class Meta:
        managed = False
        db_table = 'roles'



class UserRoleAssignment(models.Model):
    id = models.BigAutoField(primary_key=True, db_column='id')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, models.CASCADE, db_column='user_id')
    role = models.ForeignKey('admin_ops.Role', models.CASCADE, db_column='role_id')
    assigned_at = models.DateTimeField(auto_now_add=True, db_column='assigned_at')

    class Meta:
        managed = False
        db_table = 'user_role_assignments'
        constraints = [
            models.UniqueConstraint(fields=['user', 'role'], name='user_id'),
        ]
        indexes = [
            models.Index(fields=['role'], name='ix_ura_role'),
        ]
