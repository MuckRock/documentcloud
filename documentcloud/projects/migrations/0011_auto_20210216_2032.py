# Generated by Django 2.2.5 on 2021-02-16 20:32

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('projects', '0010_auto_20200429_0121'),
    ]

    operations = [
        migrations.AlterField(
            model_name='collaboration',
            name='creator',
            field=models.ForeignKey(blank=True, help_text='The user who created this collaboration', null=True, on_delete=django.db.models.deletion.PROTECT, related_name='+', to=settings.AUTH_USER_MODEL, verbose_name='creator'),
        ),
    ]