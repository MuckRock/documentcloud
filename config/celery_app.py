# Django
from celery import Celery
from django.conf import settings

# Standard Library
import os
import ssl

# set the default Django settings module for the 'celery' program.
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.local")

if settings.CELERY_BROKER_URL:
    app = Celery(
        "documentcloud",
        broker_use_ssl={"ssl_cert_reqs": ssl.CERT_NONE},
        redis_backend_use_ssl={"ssl_cert_reqs": ssl.CERT_NONE},
    )
else:
    app = Celery("documentcloud")

# Using a string here means the worker doesn't have to serialize
# the configuration object to child processes.
# - namespace='CELERY' means all celery-related configuration keys
#   should have a `CELERY_` prefix.
app.config_from_object("django.conf:settings", namespace="CELERY")

# Load task modules from all registered Django app configs.
app.autodiscover_tasks()

if "scout_apm.django" in settings.INSTALLED_APPS:
    import scout_apm.celery

    scout_apm.celery.install(app)
