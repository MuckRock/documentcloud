# Django
from django.core.management.base import BaseCommand

# DocumentCloud
from documentcloud.organizations.models import Organization
from documentcloud.organizations.stats_api.models import OrganizationStats
from documentcloud.users.models import User
from documentcloud.users.stats_api.models import UserStats

BATCH_SIZE = 500


class Command(BaseCommand):
    """Backfill stats rows for existing users and organizations.

    The post_save signals only create stats rows for users/orgs created after
    they were deployed, so every pre-existing record lacks a row. This command
    creates the missing rows.

    Individual organizations are skipped, matching the org stats endpoint (which
    only surfaces collective orgs) and the create_organization_stats signal.
    Info about AI credit balances on individual orgs are pulled on the user
    record instead.
    """

    help = "Create stats rows for existing users and collective organizations"

    def handle(self, *args, **options):
        # pylint: disable=unused-argument
        self._backfill(
            "user",
            User.objects.filter(stats__isnull=True).values_list("pk", flat=True),
            lambda pk: UserStats(user_id=pk),
            UserStats,
        )
        self._backfill(
            "organization",
            Organization.objects.filter(
                individual=False, stats__isnull=True
            ).values_list("pk", flat=True),
            lambda pk: OrganizationStats(organization_id=pk),
            OrganizationStats,
        )

    def _backfill(self, label, pk_iterable, build, model):
        batch = []
        total = 0
        for pk in pk_iterable.iterator(chunk_size=BATCH_SIZE):
            batch.append(build(pk))
            if len(batch) >= BATCH_SIZE:
                model.objects.bulk_create(batch, ignore_conflicts=True)
                total += len(batch)
                batch = []
                self.stdout.write(f"{label}: {total:,} created...")
        if batch:
            model.objects.bulk_create(batch, ignore_conflicts=True)
            total += len(batch)
        self.stdout.write(self.style.SUCCESS(f"{label}: done, {total:,} processed"))
