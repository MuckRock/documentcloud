# Generated by Django 2.2.5 on 2020-05-26 13:32

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('organizations', '0004_auto_20200306_2000'),
    ]

    operations = [
        migrations.RenameField(
            model_name='organization',
            old_name='plan',
            new_name='plan_old',
        ),
        migrations.AlterField(
            model_name='membership',
            name='organization',
            field=models.ForeignKey(help_text='An organization being linked to a user', on_delete=django.db.models.deletion.CASCADE, related_name='memberships_old', to=settings.SQUARELET_ORGANIZATION_MODEL, verbose_name='organization'),
        ),
        migrations.AlterField(
            model_name='membership',
            name='user',
            field=models.ForeignKey(help_text='A user being linked to an organization', on_delete=django.db.models.deletion.CASCADE, related_name='memberships_old', to=settings.AUTH_USER_MODEL, verbose_name='user'),
        ),
    ]