# Django
from django.conf import settings
from django.core.management.base import BaseCommand

# DocumentCloud
from documentcloud.documents.models import Document
from documentcloud.documents.tasks import solr_reindex_all


class Command(BaseCommand):
    """Begin a full re-index of all documents in Solr"""

    def add_arguments(self, parser):
        parser.add_argument(
            "collection_name",
            type=str,
            help="The name of the new collection to index to (you must manually "
            "create this index in solr first)",
        )

    def handle(self, *args, **kwargs):
        total = Document.objects.exclude(status=Status.deleted).count()
        time = (
            (total / settings.SOLR_DIRTY_LIMIT) * settings.SOLR_DIRTY_COUNTDOWN
        ) // 60
        self.stdout.write(
            "Starting a full solr reindex:\n"
            f"\tInto collection: {kwargs['collection_name']}\n"
            f"\t{total} documents total\n"
            f"\t{settings.SOLR_DIRTY_LIMIT} documents at a time (SOLR_DIRTY_LIMIT)\n"
            f"\t{settings.SOLR_DIRTY_COUNTDOWN} seconds apart (SOLR_DIRTY_COUNTDOWN)\n"
            f"This should take about {time} minutes ({time / 60:.1f} hours)\n"
        )
        if input("Continue? [y/N] ") == "y":
            self.stdout.write("Starting")
            solr_reindex_all.delay(kwargs["collection_name"])
        else:
            self.stdout.write("Cancelled")
