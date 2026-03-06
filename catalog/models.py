"""
Auto-generated Django models for the `catalog` app.

Source of truth: MySQL schema in db_schema.sql.
These models are mapped 1:1 to existing database tables and are managed by Django migrations (managed = True).
"""
from django.db import models


class Category(models.Model):
    category_id = models.BigAutoField(primary_key=True, db_column='category_id')
    parent_category = models.ForeignKey('catalog.Category', models.RESTRICT, null=True, blank=True, db_column='parent_category_id')
    name = models.CharField(max_length=255, db_column='name')
    slug = models.CharField(max_length=255, unique=True, db_column='slug')

    class Meta:
        managed = True
        db_table = 'categories'
        indexes = [
            models.Index(fields=['parent_category'], name='ix_categories_parent'),
        ]


class Attribute(models.Model):
    attribute_id = models.BigAutoField(primary_key=True, db_column='attribute_id')
    category = models.ForeignKey('catalog.Category', models.RESTRICT, db_column='category_id')
    attribute_key = models.CharField(max_length=100, unique=True, db_column='attribute_key')
    value_type = models.ForeignKey('catalog.AttributeValueType', models.RESTRICT, db_column='value_type_id')

    class Meta:
        managed = True
        db_table = 'attributes'
        indexes = [
            models.Index(fields=['value_type'], name='fk_attributes_value_type'),
            models.Index(fields=['category'], name='fk_attributes_category'),
        ]


class AttributeValueType(models.Model):
    value_type_id = models.BigAutoField(primary_key=True, db_column='value_type_id')
    value_type_name = models.CharField(max_length=30, unique=True, db_column='value_type_name')

    class Meta:
        managed = True
        db_table = 'attribute_value_type'


class AllowedAttributeValue(models.Model):
    allowed_value_id = models.BigAutoField(primary_key=True, db_column='allowed_value_id')
    attribute = models.ForeignKey('catalog.Attribute', models.CASCADE, db_column='attribute_id')
    allowed_value_label = models.CharField(max_length=80, db_column='allowed_value_label')

    class Meta:
        managed = True
        db_table = 'allowed_attribute_values'
        constraints = [
            models.UniqueConstraint(fields=['attribute', 'allowed_value_label'], name='uq_allowed_attribute_values_attribute_value_pair'),
        ]


class ItemCondition(models.Model):
    condition_id = models.BigAutoField(primary_key=True, db_column='condition_id')
    condition_name = models.CharField(max_length=50, unique=True, db_column='condition_name')

    class Meta:
        managed = True
        db_table = 'item_conditions'
