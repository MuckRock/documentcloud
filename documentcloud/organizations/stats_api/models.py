# Django
from django.db import models


class OrganizationStats(models.Model):
    organization = models.OneToOneField(
        "organizations.Organization",
        on_delete=models.CASCADE,
        related_name="stats",
        primary_key=True,
    )
    last_upload_at = models.DateTimeField(null=True, blank=True, db_index=True)
    last_ai_credit_at = models.DateTimeField(null=True, blank=True, db_index=True)

    class Meta:
        app_label = "organizations"

    def __str__(self):
        return f"Stats for organization {self.organization_id}"
