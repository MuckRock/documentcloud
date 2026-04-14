from django.db import migrations, models

class Migration(migrations.Migration):

    dependencies = [
        ("users", "0001_initial_squashed_0010_user_bio_alter_user_email_alter_user_username"),
        ("users", "0007_auto_20211102_1707"),
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
    ]