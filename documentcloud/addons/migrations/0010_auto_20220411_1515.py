# Generated by Django 3.2.9 on 2022-04-11 15:15

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('addons', '0009_alter_addon_parameters'),
    ]

    operations = [
        migrations.AlterField(
            model_name='addon',
            name='user',
            field=models.ForeignKey(db_column='user', help_text='The user who created this add-on', on_delete=django.db.models.deletion.PROTECT, related_name='addons', to=settings.AUTH_USER_MODEL, verbose_name='user'),
        ),
        migrations.AlterField(
            model_name='githubaccount',
            name='user',
            field=models.ForeignKey(help_text='The user associated with this GitHub account', null=True, on_delete=django.db.models.deletion.PROTECT, related_name='github_accounts', to=settings.AUTH_USER_MODEL, verbose_name='user'),
        ),
        migrations.CreateModel(
            name='GitHubInstallation',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('iid', models.IntegerField(help_text='The ID for the GitHub installation', verbose_name='iid')),
                ('account', models.ForeignKey(help_text='The account which installed the app', on_delete=django.db.models.deletion.PROTECT, related_name='installations', to='addons.githubaccount', verbose_name='account')),
            ],
        ),
    ]
