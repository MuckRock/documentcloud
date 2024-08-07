# Generated by Django 3.2.9 on 2023-02-14 15:15

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('entities', '0008_alter_entity_metadata'),
    ]

    operations = [
        migrations.RenameField(
            model_name='entity',
            old_name='owner',
            new_name='user',
        ),
        migrations.AlterField(
            model_name='entity',
            name='access',
            field=models.IntegerField(choices=[(0, 'Public'), (2, 'Private')], default=0, help_text='Designates who may access this entity.', verbose_name='access'),
        ),
    ]
