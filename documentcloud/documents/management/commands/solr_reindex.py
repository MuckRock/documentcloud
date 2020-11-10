# Django
from django.conf import settings
from django.core.cache import cache
from django.core.management.base import BaseCommand

# DocumentCloud
from documentcloud.documents.choices import Status
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
        parser.add_argument(
            "--cancel", action="store_true", help="Cancel current re-indexing"
        )

    def handle(self, *args, **kwargs):
        if kwargs["cancel"]:
            self.stdout.write("Cancelling re-indexing")
            cache.set("solr_reindex_cancel", True, 3600)
            return

        cache.delete("solr_reindex_cancel")
        total = Document.objects.exclude(status=Status.deleted).count()
        self.stdout.write(
            "Starting a full solr reindex:\n"
            f"\tInto collection: {kwargs['collection_name']}\n"
            f"\t{total} documents total\n"
            f"\t{settings.SOLR_INDEX_LIMIT} documents at a time "
            "(SOLR_INDEX_LIMIT)\n"
        )
        if input("Continue? [y/N] ") == "y":
            self.stdout.write("Starting")
            solr_reindex_all.delay(kwargs["collection_name"])
        else:
            self.stdout.write("Cancelled")
