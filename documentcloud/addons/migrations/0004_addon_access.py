# Generated by Django 3.2.9 on 2022-03-30 15:03

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('addons', '0003_addon_error'),
    ]

    operations = [
        migrations.AddField(
            model_name='addon',
            name='access',
            field=models.IntegerField(choices=[(0, 'Public'), (1, 'Organization'), (2, 'Private'), (3, 'Invisible')], default=2, help_text='Designates who may access this document by default', verbose_name='access'),
        ),
    ]
