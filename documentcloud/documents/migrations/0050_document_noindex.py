# Generated by Django 3.2.9 on 2022-10-13 21:16

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("documents", "0049_document_delayed_index"),
    ]

    operations = [
        migrations.AddField(
            model_name="document",
            name="noindex",
            field=models.BooleanField(
                default=False,
                help_text="Ask search engines and DocumentCloud search to not index this document",
                verbose_name="noindex",
            ),
        ),
    ]
