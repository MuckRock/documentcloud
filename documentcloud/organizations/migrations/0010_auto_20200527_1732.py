# Generated by Django 2.2.5 on 2020-05-27 17:32

# Django
from django.db import migrations


def set_entitlements(apps, schema_editor):
    Organization = apps.get_model("organizations", "Organization")
    Plan = apps.get_model("squarelet_auth_organizations", "Plan")
    Entitlement = apps.get_model("squarelet_auth_organizations", "Entitlement")

    for plan in Plan.objects.all():
        try:
            entitlement = Entitlement.objects.get(slug=plan.slug)
        except Entitlement.DoesNotExist:
            continue
        Organization.objects.filter(plan=plan).update(entitlement=entitlement)


def delete_entitlements(apps, schema_editor):
    Organization = apps.get_model("organizations", "Organization")
    Organization.objects.update(entitlement=None)


class Migration(migrations.Migration):

    dependencies = [("organizations", "0009_organization_entitlement")]

    operations = [migrations.RunPython(set_entitlements, delete_entitlements)]