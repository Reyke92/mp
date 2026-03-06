"""
Auto-generated Django models for the `core` app.

Source of truth: MySQL schema in db_schema.sql.
These models are mapped 1:1 to existing database tables and are managed by Django migrations (managed = True).
"""
from django.db.models import Q
from django.db import models


class City(models.Model):
    city_id = models.BigAutoField(primary_key=True, db_column='city_id')
    state = models.ForeignKey('core.State', models.RESTRICT, db_column='state_id')
    city_name = models.CharField(max_length=50, db_column='city_name')
    timezone = models.ForeignKey('core.Timezone', models.RESTRICT, db_column='timezone_id')
    latitude = models.DecimalField(max_digits=9, decimal_places=6, db_column='latitude')
    longitude = models.DecimalField(max_digits=9, decimal_places=6, db_column='longitude')
    location = models.BinaryField(editable=False, db_column='location')

    class Meta:
        managed = True
        db_table = 'cities'
        constraints = [
            models.UniqueConstraint(fields=['state', 'city_name'], name='uq_cities_state_city'),
            models.CheckConstraint(condition=models.Q(latitude__gte=-90, latitude__lte=90), name='chk_cities_lat'),
            models.CheckConstraint(condition=models.Q(longitude__gte=-180, longitude__lte=180), name='chk_cities_lon'),
        ]
        indexes = [
            models.Index(fields=['state'], name='ix_cities_state'),
            models.Index(fields=['timezone'], name='fk_cities_timezone'),
            models.Index(fields=['location'], name='spx_cities_location'),
        ]


class State(models.Model):
    state_id = models.BigAutoField(primary_key=True, db_column='state_id')
    state_code = models.CharField(max_length=2, unique=True, db_column='state_code')
    state_name = models.CharField(max_length=20, unique=True, db_column='state_name')

    class Meta:
        managed = True
        db_table = 'states'


class Timezone(models.Model):
    timezone_id = models.BigAutoField(primary_key=True, db_column='timezone_id')
    timezone_name = models.CharField(max_length=6, unique=True, db_column='timezone_name')

    class Meta:
        managed = True
        db_table = 'timezones'
