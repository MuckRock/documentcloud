# Generated by Django 3.2.9 on 2022-02-17 01:34

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('plugins', '0002_pluginrun'),
    ]

    operations = [
        migrations.AddField(
            model_name='pluginrun',
            name='progress',
            field=models.PositiveSmallIntegerField(default=0, help_text='The progress as a percent done of this run', verbose_name='progress'),
        ),
    ]