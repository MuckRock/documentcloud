# Generated by Django 3.2.9 on 2022-04-07 13:30

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('addons', '0008_rename_github_token_addon__github_token'),
    ]

    operations = [
        migrations.AlterField(
            model_name='addon',
            name='parameters',
            field=models.JSONField(default={}, help_text='The parameters for this add-on', verbose_name='parameters'),
        ),
    ]