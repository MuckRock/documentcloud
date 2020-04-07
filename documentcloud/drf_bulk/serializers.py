# Django
from django.conf import settings
from rest_framework import serializers
from rest_framework.fields import empty

# Standard Library
import inspect


class BulkListSerializer(serializers.ListSerializer):
    def update(self, instance, validated_data):
        id_attr = getattr(self.child.Meta, "update_lookup_field", "id")

        data_mapping = {item.get(id_attr): item for item in validated_data}

        # instance is a queryset for bulk updates - filter it down
        # to the relevant instances
        queryset = instance.filter(**{f"{id_attr}__in": data_mapping.keys()})

        if len(data_mapping) != len(queryset):
            raise serializers.ValidationError("Could not find all objects to update.")

        updated_objects = []
        for obj in queryset:
            obj_id = getattr(obj, id_attr)
            data = data_mapping.get(obj_id)
            updated_objects.append(self.child.update(obj, data))

        return updated_objects

    def validate(self, attrs):
        if settings.REST_BULK_LIMIT and len(attrs) > settings.REST_BULK_LIMIT:
            raise serializers.ValidationError(
                f"Bulk API operations are limited to {settings.REST_BULK_LIMIT} "
                "at a time"
            )
        return attrs
