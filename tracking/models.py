"""
Auto-generated Django models for the `tracking` app.

Source of truth: MySQL schema in db_schema.sql.
These models are mapped 1:1 to existing database tables and are **not** managed by Django migrations.
"""
from django.db import models

class ListingMetadataSnapshot(models.Model):
    id = models.BigAutoField(primary_key=True, db_column='id')
    listing = models.OneToOneField('listings.Listing', models.CASCADE, db_column='listing_id')
    compiled_json = models.JSONField(db_column='compiled_json')
    compiled_at = models.DateTimeField(auto_now_add=True, db_column='compiled_at')

    class Meta:
        managed = False
        db_table = 'listing_metadata_snapshots'
