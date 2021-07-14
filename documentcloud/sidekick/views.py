# Django
from rest_framework import mixins, viewsets

# DocumentCloud
from documentcloud.sidekick.models import Sidekick
from documentcloud.sidekick.serializers import SidekickSerializer


class SidekickViewset(viewsets.ModelViewSet):
    serializer_class = SidekickSerializer
    queryset = Sidekick.objects.none()

    @lru_cache()
    def get_queryset(self):
        """Only fetch documents viewable to this user"""
        document = get_object_or_404(
            Document.objects.get_viewable(self.request.user),
            pk=self.kwargs["document_pk"],
        )
        return document.sections.all()

    def perform_create(self, serializer):
        """Specify the document"""
        serializer.save(document_id=self.kwargs["document_pk"])
