# Django
from rest_framework import status
from rest_framework.response import Response


class BulkCreateModelMixin:
    def create(self, request):
        """Handle single and bulk creations"""
        if isinstance(request.data, list):
            serializer = self.get_serializer(data=request.data, many=True)
            serializer.is_valid(raise_exception=True)
            self.bulk_perform_create(serializer)
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        else:
            return super().create(request)

    def bulk_perform_create(self, serializer):
        return self.perform_create(serializer)


class BulkUpdateModelMixin:
    def bulk_update(self, request, *args, **kwargs):
        partial = kwargs.pop("partial", False)

        serializer = self.get_serializer(
            self.filter_queryset(self.get_queryset()),
            data=request.data,
            many=True,
            partial=partial,
        )
        serializer.is_valid(raise_exception=True)
        self.bulk_perform_update(serializer)
        return Response(serializer.data, status=status.HTTP_200_OK)

    def bulk_partial_update(self, request, *args, **kwargs):
        kwargs["partial"] = True
        return self.bulk_update(request, *args, **kwargs)

    def bulk_perform_update(self, serializer):
        return self.perform_update(serializer)


class BulkDestroyModelMixin:
    def allow_bulk_destroy(self, queryset):
        return True

    def bulk_destroy(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        if not self.allow_bulk_destroy(queryset):
            return Response(status=status.HTTP_400_BAD_REQUEST)

        self.bulk_perform_destroy(queryset)

        return Response(status=status.HTTP_204_NO_CONTENT)

    def bulk_perform_destroy(self, objects):
        for obj in objects:
            self.perform_destroy(obj)


class BulkModelMixin(BulkCreateModelMixin, BulkUpdateModelMixin, BulkDestroyModelMixin):
    pass
