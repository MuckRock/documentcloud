# Standard Library
# Django
from django.db import models
from django.utils.translation import gettext_lazy as _

# Standard Library
from uuid import uuid4

# DocumentCloud
from documentcloud.core.fields import AutoCreatedField, AutoLastModifiedField


class SavedSearch(models.Model):
    uuid = models.UUIDField(
        unique=True,
        editable=False,
        default=uuid4,
        db_index=True,
        help_text=_("Unique identifier for the saved search"),
    )
    user = models.ForeignKey(
        verbose_name=_("user"),
        to="users.User",
        on_delete=models.CASCADE,
        related_name="saved_searches",
        help_text=_("The user who owns this saved search"),
    )
    name = models.CharField(
        _("name"),
        max_length=255,
        help_text=_("A name for the saved search"),
    )
    query = models.TextField(
        _("query"),
        help_text=_("The search query string"),
    )
    created_at = AutoCreatedField(
        _("created at"),
        help_text=_("Timestamp of when the saved search was created"),
    )
    updated_at = AutoLastModifiedField(
        _("updated at"),
        help_text=_("Timestamp of when the saved search was last updated"),
    )

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.name
