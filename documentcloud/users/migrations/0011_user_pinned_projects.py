# Generated by Django 4.2.2 on 2024-02-14 19:41

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("projects", "0012_auto_20210407_1801"),
        ("users", "0010_user_bio_alter_user_email_alter_user_username"),
    ]

    operations = [
        migrations.AddField(
            model_name="user",
            name="pinned_projects",
            field=models.ManyToManyField(
                help_text="Projects pinned for this user",
                related_name="pinners",
                to="projects.project",
                verbose_name="pinned projects",
            ),
        ),
    ]
