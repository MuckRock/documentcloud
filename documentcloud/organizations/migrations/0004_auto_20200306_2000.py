# Generated by Django 2.2.5 on 2020-03-06 20:00

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('organizations', '0003_auto_20200214_1640'),
    ]

    operations = [
        migrations.AddField(
            model_name='organization',
            name='document_language',
            field=models.CharField(blank=True, choices=[('ara', 'Arabic'), ('zho', 'Chinese (Simplified)'), ('tra', 'Chinese (Traditional)'), ('hrv', 'Croatian'), ('dan', 'Danish'), ('nld', 'Dutch'), ('eng', 'English'), ('fra', 'French'), ('deu', 'German'), ('heb', 'Hebrew'), ('hun', 'Hungarian'), ('ind', 'Indonesian'), ('ita', 'Italian'), ('jpn', 'Japanese'), ('kor', 'Korean'), ('nor', 'Norwegian'), ('por', 'Portuguese'), ('ron', 'Romanian'), ('rus', 'Russian'), ('spa', 'Spanish'), ('swe', 'Swedish'), ('ukr', 'Ukrainian')], default='eng', help_text="The default document language for user's in this organization", max_length=3, verbose_name='document language'),
        ),
        migrations.AddField(
            model_name='organization',
            name='language',
            field=models.CharField(blank=True, choices=[('ara', 'Arabic'), ('zho', 'Chinese (Simplified)'), ('tra', 'Chinese (Traditional)'), ('hrv', 'Croatian'), ('dan', 'Danish'), ('nld', 'Dutch'), ('eng', 'English'), ('fra', 'French'), ('deu', 'German'), ('heb', 'Hebrew'), ('hun', 'Hungarian'), ('ind', 'Indonesian'), ('ita', 'Italian'), ('jpn', 'Japanese'), ('kor', 'Korean'), ('nor', 'Norwegian'), ('por', 'Portuguese'), ('ron', 'Romanian'), ('rus', 'Russian'), ('spa', 'Spanish'), ('swe', 'Swedish'), ('ukr', 'Ukrainian')], default='eng', help_text="The default interface language for user's in this organization", max_length=3, verbose_name='language'),
        ),
        migrations.AddField(
            model_name='organization',
            name='verified_journalist',
            field=models.BooleanField(default=False, help_text='This organization is a verified jorunalistic organization', verbose_name='verified journalist'),
        ),
    ]