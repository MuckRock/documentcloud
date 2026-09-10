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
    last_ai_credit_at = models.DateTimeField(null=True, blank=True, db_index=True)
    total_documents = models.IntegerField(default=0)
    recent_upload_count = models.IntegerField(default=0)

    class Meta:
        app_label = "users"

    def __str__(self):
        return f"Stats for user {self.user_id}"
