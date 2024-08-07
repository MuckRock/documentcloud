# Generated by Django 2.2.5 on 2020-05-05 12:46

from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
    ]

    operations = [
        migrations.CreateModel(
            name='Statistics',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('date', models.DateField(help_text='The date these statistics were taken', unique=True)),
                ('total_documents', models.IntegerField(help_text='The total number of documents')),
                ('total_documents_public', models.IntegerField(help_text='The total number of public documents')),
                ('total_documents_organization', models.IntegerField(help_text='The total number of organizational documents')),
                ('total_documents_private', models.IntegerField(help_text='The total number of private documents')),
                ('total_documents_invisible', models.IntegerField(help_text='The total number of invisible documents')),
                ('total_pages', models.IntegerField(help_text='The total number of pages')),
                ('total_pages_public', models.IntegerField(help_text='The total number of public pages')),
                ('total_pages_organization', models.IntegerField(help_text='The total number of organizational pages')),
                ('total_pages_private', models.IntegerField(help_text='The total number of private pages')),
                ('total_pages_invisible', models.IntegerField(help_text='The total number of invisible pages')),
                ('total_notes', models.IntegerField(help_text='The total number of notes')),
                ('total_notes_public', models.IntegerField(help_text='The total number of public notes')),
                ('total_notes_organization', models.IntegerField(help_text='The total number of organizational notes')),
                ('total_notes_private', models.IntegerField(help_text='The total number of private notes')),
                ('total_notes_invisible', models.IntegerField(help_text='The total number of invisible notes')),
                ('total_projects', models.IntegerField(help_text='The total number of projects')),
            ],
            options={
                'verbose_name_plural': 'statistics',
                'ordering': ['-date'],
            },
        ),
    ]
