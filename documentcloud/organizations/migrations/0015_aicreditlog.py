# Generated by Django 4.2.2 on 2023-08-21 19:30

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone
import documentcloud.core.fields


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("organizations", "0014_auto_20221025_1350"),
    ]

    operations = [
        migrations.CreateModel(
            name="AICreditLog",
            fields=[
                (
                    "id",
                    models.AutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "amount",
                    models.PositiveIntegerField(
                        help_text="Amount of AI credits charged", verbose_name="amount"
                    ),
                ),
                (
                    "note",
                    models.CharField(
                        help_text="What were these credits used for?",
                        max_length=1000,
                        verbose_name="note",
                    ),
                ),
                (
                    "created_at",
                    documentcloud.core.fields.AutoCreatedField(
                        default=django.utils.timezone.now,
                        editable=False,
                        help_text="Timestamp of when the credits were used",
                        verbose_name="created at",
                    ),
                ),
                (
                    "organization",
                    models.ForeignKey(
                        help_text="The organization the AI credits were used from",
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="ai_credit_logs",
                        to=settings.SQUARELET_ORGANIZATION_MODEL,
                        verbose_name="organization",
                    ),
                ),
                (
                    "user",
                    models.ForeignKey(
                        help_text="The user who used the AI credits",
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="ai_credit_logs",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="user",
                    ),
                ),
            ],
        ),
    ]