# Generated by Django 2.2.5 on 2020-08-07 16:59

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('documents', '0026_auto_20200805_2051'),
    ]

    operations = [
        migrations.AlterField(
            model_name='section',
            name='document',
            field=models.ForeignKey(db_constraint=False, help_text='The document this section belongs to', on_delete=django.db.models.deletion.CASCADE, related_name='sections', to='documents.Document', verbose_name='document'),
        ),
    ]
