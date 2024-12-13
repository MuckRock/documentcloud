# Django
from celery import shared_task

# DocumentCloud
from documentcloud.documents.processing.sidekick.main import preprocess


@shared_task
def sidekick_preprocess(data):
    preprocess(data)
