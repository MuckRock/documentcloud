# Generated by Django 2.2.5 on 2020-02-14 16:40

# Django
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [("users", "0002_auto_20200128_1418")]

    operations = [
        migrations.RunSQL("ALTER SEQUENCE users_user_id_seq RESTART WITH 100000")
    ]
