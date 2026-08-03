# Django
from django.db import models


class UserStats(models.Model):
    user = models.OneToOneField(
        "users.User",
        on_delete=models.CASCADE,
        related_name="stats",
        primary_key=True,
    )
    last_upload_at = models.DateTimeField(null=True, blank=True, db_index=True)

    class Meta:
        app_label = "users"

    def __str__(self):
        return f"Stats for user {self.user_id}"
