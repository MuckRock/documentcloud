from django.db import migrations, models


class Migration(migrations.Migration):

    replaces = [
        ("users", "0008_user_active_addons"),
        ("users", "0009_user_mailkey"),
        ("users", "0010_user_bio_alter_user_email_alter_user_username"),
    ]

    dependencies = [
        ("addons", "0005_auto_20220330_1908"),
        ("users", "0001_squashed_0007_auto_20211102_1707"),
    ]

    operations = [
        migrations.AddField(
            model_name="user",
            name="active_addons",
            field=models.ManyToManyField(
                help_text="Add-Ons shown for this user",
                related_name="users",
                to="addons.addon",
                verbose_name="active add-ons",
            ),
        ),
        migrations.AddField(
            model_name="user",
            name="mailkey",
            field=models.UUIDField(
                help_text="Mail key for uploading documents via email",
                null=True,
                verbose_name="mailkey",
            ),
        ),
        migrations.AddField(
            model_name="user",
            name="bio",
            field=models.TextField(
                blank=True,
                help_text="Public bio for the user, in Markdown",
                verbose_name="bio",
            ),
        ),
    ]
