# Generated by Django 2.2.5 on 2020-01-28 14:18

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('organizations', '0001_initial'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='organization',
            options={'ordering': ('slug',)},
        ),
    ]
