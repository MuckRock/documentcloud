# Generated by Django 4.2.2 on 2024-03-04 21:09

# Django
from django.db import migrations


def default_pinned_projects(apps, schema_editor):
    User = apps.get_model("users", "User")
    Collaboration = apps.get_model("projects", "Collaboration")
    pins = []

    print(f"Total Collaborations: {Collaboration.objects.count()}")

    for i, collab in enumerate(Collaboration.objects.iterator()):
        if i % 1000 == 0:
            print(f"Collaboration #{i}")
        pins.append(
            User.pinned_projects.through(
                user_id=collab.user_id, project_id=collab.project_id
            )
        )

    User.pinned_projects.through.objects.bulk_create(pins, batch_size=1000)


def remove_pinned_projects(apps, schema_editor):
    User = apps.get_model("users", "User")
    User.pinned_projects.through.objects.all().delete()


class Migration(migrations.Migration):

    dependencies = [
        ("users", "0011_user_pinned_projects"),
        ("projects", "0012_auto_20210407_1801"),
    ]

    operations = [migrations.RunPython(default_pinned_projects, remove_pinned_projects)]
