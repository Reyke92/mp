"""
Auto-generated Django models for the `messaging` app.

Source of truth: MySQL schema in db_schema.sql.
These models are mapped 1:1 to existing database tables and are **not** managed by Django migrations.
"""
from django.db import models

from django.conf import settings

class Conversation(models.Model):
    conversation_id = models.BigAutoField(primary_key=True, db_column='conversation_id')
    # Two FKs to the same user model require distinct reverse accessors.
    user_a = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        models.RESTRICT,
        db_column='user_a_id',
        related_name='conversations_as_user_a',
    )
    user_b = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        models.RESTRICT,
        db_column='user_b_id',
        related_name='conversations_as_user_b',
    )
    created_at = models.DateTimeField(auto_now_add=True, db_column='created_at')

    class Meta:
        managed = False
        db_table = 'conversations'
        constraints = [
            models.UniqueConstraint(fields=['user_a', 'user_b'], name='uq_conversations_pair'),
        ]
        indexes = [
            models.Index(fields=['user_a'], name='ix_conversations_user_a'),
            models.Index(fields=['user_b'], name='ix_conversations_user_b'),
            models.Index(fields=['user_a', 'created_at'], name='idx_conv_user_a_created'),
            models.Index(fields=['user_b', 'created_at'], name='idx_conv_user_b_created'),
        ]



class Message(models.Model):
    message_id = models.BigAutoField(primary_key=True, db_column='message_id')
    conversation = models.ForeignKey('messaging.Conversation', models.CASCADE, db_column='conversation_id')
    sender_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        models.RESTRICT,
        db_column='sender_user_id',
        related_name='messages_sent',
    )
    message_text = models.TextField(db_column='message_text')
    sent_at = models.DateTimeField(auto_now_add=True, db_column='sent_at')

    class Meta:
        managed = False
        db_table = 'messages'
        indexes = [
            models.Index(fields=['conversation', 'sent_at'], name='ix_messages_conversation_sent'),
            models.Index(fields=['sender_user'], name='ix_messages_sender'),
        ]
