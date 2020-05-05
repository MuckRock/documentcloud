# Django
from django.conf import settings
from rest_framework import serializers, status
from rest_framework.response import Response

# pylint: disable=unused-argument


class BulkCreateModelMixin:
    def create(self, request, *args, **kwargs):
        """Handle single and bulk creations"""
        if isinstance(request.data, list):
            serializer = self.get_serializer(data=request.data, many=True)
            serializer.is_valid(raise_exception=True)
            self.bulk_perform_create(serializer)
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        else:
            return super().create(request, *args, **kwargs)

    def bulk_perform_create(self, serializer):
        return self.perform_create(serializer)


class BulkUpdateModelMixin:
    def filter_update_queryset(self, queryset):
        """This should filter for object you have permission to update"""
        return queryset

    def bulk_update(self, request, *args, **kwargs):
        partial = kwargs.pop("partial", False)

        serializer = self.get_serializer(
            self.filter_update_queryset(self.filter_queryset(self.get_queryset())),
            data=request.data,
            many=True,
            partial=partial,
        )
        serializer.is_valid(raise_exception=True)
        self.bulk_perform_update(serializer, partial)
        return Response(serializer.data, status=status.HTTP_200_OK)

    def bulk_partial_update(self, request, *args, **kwargs):
        kwargs["partial"] = True
        return self.bulk_update(request, *args, **kwargs)

    def bulk_perform_update(self, serializer, partial):
        return self.perform_update(serializer)


class BulkDestroyModelMixin:
    def filter_delete_queryset(self, queryset):
        """This should filter for object you have permission to delete"""
        return queryset

    def check_bulk_destroy_permissions(self, queryset):
        if settings.REST_BULK_LIMIT and queryset.count() > settings.REST_BULK_LIMIT:
            raise serializers.ValidationError(
                f"Bulk API operations are limited to {settings.REST_BULK_LIMIT} "
                "at a time"
            )

    def bulk_destroy(self, request, *args, **kwargs):
        queryset = self.filter_delete_queryset(
            self.filter_queryset(self.get_queryset())
        )
        self.check_bulk_destroy_permissions(queryset)

        self.bulk_perform_destroy(queryset)

        return Response(status=status.HTTP_204_NO_CONTENT)

    def bulk_perform_destroy(self, objects):
        for obj in objects:
            self.perform_destroy(obj)


class BulkModelMixin(BulkCreateModelMixin, BulkUpdateModelMixin, BulkDestroyModelMixin):
    def filter_delete_queryset(self, queryset):
        return self.filter_update_queryset(queryset)
