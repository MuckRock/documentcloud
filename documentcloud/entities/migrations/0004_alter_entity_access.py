# Generated by Django 3.2.9 on 2023-02-01 19:44

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('entities', '0003_auto_20230201_1814'),
    ]

    operations = [
        migrations.AlterField(
            model_name='entity',
            name='access',
            field=models.IntegerField(choices=[(0, 'Public'), (2, 'Private')], help_text='Designates who may access this entity.', verbose_name='access'),
        ),
    ]