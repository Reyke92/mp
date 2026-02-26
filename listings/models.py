"""
Auto-generated Django models for the `listings` app.

Source of truth: MySQL schema in db_schema.sql.
These models are mapped 1:1 to existing database tables and are **not** managed by Django migrations.
"""
from django.db import models

from django.conf import settings

class Listing(models.Model):
    listing_id = models.BigAutoField(primary_key=True, db_column='listing_id')
    seller_user = models.ForeignKey(settings.AUTH_USER_MODEL, models.RESTRICT, db_column='seller_user_id')
    category = models.ForeignKey('catalog.Category', models.RESTRICT, db_column='category_id')
    condition = models.ForeignKey('catalog.ItemCondition', models.RESTRICT, db_column='condition_id')
    city = models.ForeignKey('core.City', models.RESTRICT, db_column='city_id')
    title = models.CharField(max_length=255, db_column='title')
    description = models.TextField(null=True, blank=True, db_column='description')
    price_amount = models.DecimalField(max_digits=12, decimal_places=2, db_column='price_amount')
    status = models.ForeignKey('listings.ListingStatus', models.RESTRICT, db_column='status_id')
    created_at = models.DateTimeField(auto_now_add=True, db_column='created_at')
    updated_at = models.DateTimeField(null=True, blank=True, db_column='updated_at')
    view_count = models.PositiveBigIntegerField(default=0, db_column='view_count')

    class Meta:
        managed = False
        db_table = 'listings'
        indexes = [
            models.Index(fields=['seller_user'], name='ix_listings_seller'),
            models.Index(fields=['category'], name='ix_listings_category'),
            models.Index(fields=['condition'], name='ix_listings_condition'),
            models.Index(fields=['city'], name='ix_listings_city'),
            models.Index(fields=['status'], name='fk_listings_status'),
        ]



class ListingImage(models.Model):
    image_id = models.BigAutoField(primary_key=True, db_column='image_id')
    listing = models.ForeignKey('listings.Listing', models.CASCADE, db_column='listing_id')
    image_url = models.CharField(max_length=512, db_column='image_url')
    display_order = models.IntegerField(db_column='display_order')
    uploaded_at = models.DateTimeField(auto_now_add=True, db_column='uploaded_at')

    class Meta:
        managed = False
        db_table = 'listing_images'
        constraints = [
            models.UniqueConstraint(fields=['listing', 'display_order'], name='uq_listing_images_listing_order'),
        ]
        indexes = [
            models.Index(fields=['listing'], name='ix_listing_images_listing'),
        ]



class ListingAttributeValue(models.Model):
    id = models.BigAutoField(primary_key=True, db_column='id')
    listing = models.ForeignKey('listings.Listing', models.CASCADE, db_column='listing_id')
    attribute = models.ForeignKey('catalog.Attribute', models.RESTRICT, db_column='attribute_id')
    value_int = models.BigIntegerField(null=True, blank=True, db_column='value_int')
    value_decimal = models.DecimalField(max_digits=18, decimal_places=6, null=True, blank=True, db_column='value_decimal')
    value_datetime = models.DateTimeField(null=True, blank=True, db_column='value_datetime')
    value_text = models.ForeignKey('catalog.AllowedAttributeValue', models.RESTRICT, null=True, blank=True, db_column='value_text_id')
    value_bool = models.BooleanField(null=True, blank=True, db_column='value_bool')

    class Meta:
        managed = False
        db_table = 'listing_attribute_values'
        constraints = [
            models.UniqueConstraint(fields=['listing', 'attribute'], name='listing_id'),
        ]
        indexes = [
            models.Index(fields=['attribute'], name='ix_lav_attribute'),
            models.Index(fields=['value_text'], name='fk_lav_value_text'),
        ]



class ListingStatus(models.Model):
    status_id = models.BigAutoField(primary_key=True, db_column='status_id')
    status_name = models.CharField(max_length=30, unique=True, db_column='status_name')

    class Meta:
        managed = False
        db_table = 'listing_status'
