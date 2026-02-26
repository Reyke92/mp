from django.conf import settings
from django.db import models

from core.storage import avatar_upload_to

class UserProfile(models.Model):
    id = models.BigAutoField(primary_key=True, db_column='id')
    user = models.OneToOneField(settings.AUTH_USER_MODEL, models.CASCADE, db_column='user_id')
    bio = models.TextField(null=True, max_length=80, blank=True, db_column='bio')
    # NOTE: maps to the EXISTING column `avatar_url`
    avatar = models.ImageField(
        upload_to=avatar_upload_to,     # random name generator
        db_column="avatar_url",
        max_length=512,
        blank=True,
        default="",                     # helps if DB column is NOT NULL
    )
    city = models.ForeignKey('core.City', models.RESTRICT, db_column='city_id')

    class Meta:
        managed = False
        db_table = 'user_profiles'
        indexes = [
            models.Index(fields=['city'], name='fk_user_profiles_city'),
        ]

    @property
    def avatar_public_url(self) -> str:
        """
        Convenience: gives a browser-usable URL.
        (Returns "" if no avatar is set.)
        """
        try:
            return self.avatar.url
        except Exception:
            return ""
