# Django
from django.db.models.signals import post_delete
from django.dispatch import receiver

# DocumentCloud
from documentcloud.common import path
from documentcloud.common.environment import storage
from documentcloud.sidekick.models import Sidekick


@receiver(
    post_delete,
    sender=Sidekick,
    dispatch_uid="documentcloud.core.signals.delete_vectors",
)
def delete_vectors(instance, **kwargs):
    """Delete vector files when deleting a sidekick instance"""
    # pylint: disable=unused-argument
    storage.delete(path.sidekick_document_vectors_path(instance.project_id))
