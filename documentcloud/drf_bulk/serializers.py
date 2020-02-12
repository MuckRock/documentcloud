# Django
from django.conf import settings
from rest_framework import serializers


class BulkListSerializer(serializers.ListSerializer):
    def update(self, instance, validated_data):
        id_attr = getattr(self.child.Meta, "update_lookup_field", "id")

        # Maps for id->instance and id->data item.
        obj_mapping = {getattr(obj, id_attr): obj for obj in instance}
        data_mapping = {item[id_attr]: item for item in validated_data}

        # Perform creations and updates.
        ret = []
        for obj_id, data in data_mapping.items():
            obj = obj_mapping.get(obj_id)
            if obj:
                ret.append(self.child.update(obj, data))

        return ret

    def validate(self, attrs):
        if len(attrs) > settings.REST_BULK_LIMIT:
            raise serializers.ValidationError(
                f"Bulk API operations are limited to {settings.REST_BULK_LIMIT} "
                "at a time"
            )
        return attrs
