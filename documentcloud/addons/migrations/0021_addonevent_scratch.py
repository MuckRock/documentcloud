# Generated by Django 3.2.9 on 2022-05-09 14:36

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('addons', '0020_alter_addonevent_event'),
    ]

    operations = [
        migrations.AddField(
            model_name='addonevent',
            name='scratch',
            field=models.JSONField(default=dict, help_text='Field to store data for add-on between events', verbose_name='scratch'),
        ),
    ]
