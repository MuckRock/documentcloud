# Django
from django.contrib.flatpages.models import FlatPage
from rest_framework import mixins, viewsets

# DocumentCloud
from documentcloud.flatpages.serializers import FlatPageSerializer


class FlatPageViewSet(
    mixins.RetrieveModelMixin, mixins.ListModelMixin, viewsets.GenericViewSet
):
    serializer_class = FlatPageSerializer
    queryset = FlatPage.objects.all()
    lookup_field = "url"
    lookup_value_regex = ".+"

    def get_object(self):
        self.kwargs["url"] = "/" + self.kwargs["url"] + "/"
        return super().get_object()
