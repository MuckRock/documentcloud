# Generated by Django 3.2.9 on 2022-04-19 18:29

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('addons', '0015_auto_20220419_1824'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='addon',
            name='_github_token',
        ),
    ]
