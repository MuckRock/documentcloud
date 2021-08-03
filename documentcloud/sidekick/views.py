# Django
from django.db import transaction
from django.db.utils import IntegrityError
from django.http.response import Http404
from rest_framework import serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.generics import get_object_or_404
from rest_framework.response import Response

# DocumentCloud
from documentcloud.core.permissions import (
    DjangoObjectPermissionsOrAnonReadOnly,
    SidekickPermissions,
)
from documentcloud.projects.models import Project
from documentcloud.sidekick.choices import Status
from documentcloud.sidekick.models import Sidekick
from documentcloud.sidekick.serializers import SidekickSerializer
from documentcloud.sidekick.tasks import lego_learn, preprocess


class SidekickViewSet(viewsets.ModelViewSet):
    serializer_class = SidekickSerializer
    queryset = Sidekick.objects.none()
    permission_classes = (DjangoObjectPermissionsOrAnonReadOnly | SidekickPermissions,)

    def get_object(self):
        """There is always at most one sidekick associated with a project"""
        valid_token = (
            hasattr(self.request, "auth")
            and self.request.auth is not None
            and "processing" in self.request.auth["permissions"]
        )
        # Processing scope can access all documents
        if valid_token:
            projects = Project.objects.all()
        else:
            projects = Project.objects.get_editable(self.request.user)
        project = get_object_or_404(projects, pk=self.kwargs["project_pk"])

        try:
            return project.sidekick
        except Sidekick.DoesNotExist:
            raise Http404

    def perform_create(self, serializer):
        """Specify the project"""
        project = get_object_or_404(
            Project.objects.get_editable(self.request.user),
            pk=self.kwargs["project_pk"],
        )
        try:
            # try saving and processing the sidekick if one does not exist
            with transaction.atomic():
                sidekick = serializer.save(project=project)
                preprocess.delay(self.kwargs["project_pk"])
        except IntegrityError:
            # a sidekick already exists, select it for updating
            with transaction.atomic():
                sidekick = Sidekick.objects.select_for_update().get(
                    project_id=self.kwargs["project_pk"]
                )
                if sidekick.status == Status.pending:
                    # if it is already processing then error
                    raise serializers.ValidationError("Already processing")

                # set to processing and begin the processing
                sidekick.status = Status.pending
                sidekick.save()
                preprocess.delay(self.kwargs["project_pk"])

    @action(detail=False, method=["post"])
    def learn(self, request, project_pk=None):
        """Activate lego learning"""
        # pylint: disable=unused-argument
        if "tagname" not in request.data:
            raise serializers.ValidationError("Missing tagname")

        lego_learn.delay(request.data["tagname"])

        return Response("OK", status=status.HTTP_200_OK)
