from django.conf import settings
from django.db import models
from core.storage import avatar_upload_to


class UserProfile(models.Model):
    id = models.BigAutoField(primary_key=True, db_column='id')
    user = models.OneToOneField(settings.AUTH_USER_MODEL, models.CASCADE, db_column='user_id')
    bio = models.TextField(null=True, blank=True, db_column='bio')
    avatar = models.ImageField(
        upload_to=avatar_upload_to,     # random name generator
        db_column="avatar_url",
        max_length=512,
        blank=True,
        default="",                     # helps if DB column is NOT NULL
    )
    city = models.ForeignKey('core.City', models.RESTRICT, db_column='city_id')

    class Meta:
        managed = True
        db_table = 'user_profiles'
        indexes = [
            models.Index(fields=['city'], name='fk_user_profiles_city'),
        ]
