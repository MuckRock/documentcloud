from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("users", "0001_initial_squashed_0010_user_bio_alter_user_email_alter_user_username"),
        ("users", "0007_auto_20211102_1707"),
    ]
    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
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
            ],
            database_operations=[
                migrations.RunSQL(
                    sql="""
                        CREATE TABLE IF NOT EXISTS users_user_active_addons (
                            id serial NOT NULL PRIMARY KEY,
                            user_id integer NOT NULL REFERENCES users_user(id) DEFERRABLE INITIALLY DEFERRED,
                            addon_id bigint NOT NULL REFERENCES addons_addon(id) DEFERRABLE INITIALLY DEFERRED
                        )
                    """,
                    reverse_sql="DROP TABLE IF EXISTS users_user_active_addons",
                ),
            ],
        )
    ]