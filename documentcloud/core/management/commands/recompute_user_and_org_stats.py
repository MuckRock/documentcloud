# Django
from django.conf import settings
from django.core.management.base import BaseCommand
from django.db.models import Count
from django.utils import timezone

# Standard Library
from datetime import timedelta

# DocumentCloud
from documentcloud.documents.models import Document
from documentcloud.organizations.stats_api.models import OrganizationStats
from documentcloud.users.stats_api.models import UserStats

BATCH = 1000


class Command(BaseCommand):
    """Recompute stored document counts on stats rows (run nightly)."""

    help = "Recompute total_documents and recent_upload_count on stats rows"

    def handle(self, *args, **options):
        cutoff = timezone.now() - timedelta(days=settings.UPLOAD_WINDOW_DAYS)
        self._recompute(UserStats, "user_id", cutoff)
        self._recompute(OrganizationStats, "organization_id", cutoff)

    def _recompute(self, model, key, cutoff):
        totals = dict(Document.objects.values_list(key).annotate(c=Count("pk")))
        recents = dict(
            Document.objects.filter(created_at__gte=cutoff)
            .values_list(key)
            .annotate(c=Count("pk"))
        )
        to_update = []
        updated = 0
        for row in model.objects.all().iterator(chunk_size=BATCH):
            k = getattr(row, key)
            row.total_documents = totals.get(k, 0)
            row.recent_upload_count = recents.get(k, 0)
            to_update.append(row)
            if len(to_update) >= BATCH:
                model.objects.bulk_update(
                    to_update, ["total_documents", "recent_upload_count"]
                )
                updated += len(to_update)
                to_update = []
        if to_update:
            model.objects.bulk_update(
                to_update, ["total_documents", "recent_upload_count"]
            )
            updated += len(to_update)
        self.stdout.write(self.style.SUCCESS(f"{model.__name__}: {updated:,} updated"))
