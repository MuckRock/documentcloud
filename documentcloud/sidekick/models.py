# Django
from django.db import models
from django.utils.translation import gettext_lazy as _

# Third Party
import numpy as np

# DocumentCloud
from documentcloud.common import path
from documentcloud.common.environment import storage
from documentcloud.sidekick.choices import Status

VOCAB_SIZE = 30_000


def file_path(instance, file_name):
    return f"sidekick/{instance.pk}/{file_name}"


class Sidekick(models.Model):
    """Online learning for documents in a project"""

    project = models.OneToOneField(
        verbose_name=_("project"),
        to="projects.Project",
        on_delete=models.CASCADE,
        related_name="sidekick",
        help_text=_("The project this sidekick is for"),
    )
    status = models.IntegerField(
        _("status"),
        choices=Status.choices,
        default=Status.pending,
        help_text=_("The status of this sidekick"),
    )

    def get_document_vectors(self):
        """Fetch the pre-preocessed document vectors from storage"""
        with storage.open(
            path.sidekick_document_vectors_path(self.project_id), "rb"
        ) as vectors_file:
            doc_vector_obj = np.load(vectors_file)

        # Grab document vector matrix
        return (doc_vector_obj.get("vectors"), doc_vector_obj.get("ids"))
