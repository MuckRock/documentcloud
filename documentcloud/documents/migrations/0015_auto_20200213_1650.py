# Generated by Django 2.2.5 on 2020-02-13 16:50

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('documents', '0014_auto_20200210_1900'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='document',
            options={'ordering': ('created_at',), 'permissions': (('share_document', 'Can share edit access to the document through a project'), ('process_document', 'Document processor - can set `page_count`, `page_spec`, and `status` through the API'))},
        ),
    ]