# Django
from celery.task import task

# DocumentCloud
from documentcloud.documents.processing.sidekick.main import preprocess


@task
def sidekick_preprocess(data):
    preprocess(data)
