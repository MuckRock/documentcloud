# Django
from django.core.management.base import BaseCommand

# DocumentCloud
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
        solr_reindex_all(kwargs["collection_name"])
