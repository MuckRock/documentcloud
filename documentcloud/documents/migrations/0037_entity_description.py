# Generated by Django 2.2.5 on 2020-12-23 19:50

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('documents', '0036_auto_20201223_1830'),
    ]

    operations = [
        migrations.AddField(
            model_name='entity',
            name='description',
            field=models.TextField(blank=True, help_text='Detailed description from Google Knowledge Graph', verbose_name='description'),
        ),
    ]
