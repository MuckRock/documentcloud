# Django
from django.conf import settings
from django.db.models.query import prefetch_related_objects
from django.db.utils import IntegrityError
from rest_framework import serializers
from rest_framework.exceptions import ValidationError
from rest_framework.utils import model_meta


class BulkListSerializer(serializers.ListSerializer):
    def create(self, validated_data):
        """Create instances in bulk efficiently"""

        ModelClass = self.child.Meta.model

        info = model_meta.get_field_info(ModelClass)
        m2m_fields = [f for f, i in info.relations.items() if i.to_many]

        instances = []
        m2m_values = []
        for attrs in validated_data:
            m2m_values.append({})
            for field in m2m_fields:
                # m2m fields must be set after the instance is created
                m2m_values[-1][field] = attrs.pop(field, None)
            instances.append(ModelClass(**attrs))

        # create the instances in bulk for efficiency
        try:
            ModelClass.objects.bulk_create(instances)
        except IntegrityError as exc:
            raise ValidationError(exc)

        # set any m2m values
        for instance, m2m_values_ in zip(instances, m2m_values):
            for field_name, value in m2m_values_.items():
                if value:
                    field = getattr(instance, field_name)
                    field.set(value)

        # prefetch any m2m values which are serializer fields to avoid n+1 queries
        prefetch_fields = set(m2m_fields) & set(self.child.Meta.fields)
        prefetch_related_objects(instances, *prefetch_fields)

        return instances

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
