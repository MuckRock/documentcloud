# Django
from django.conf import settings
from django.db import transaction
from django.db.models import Q
from django.db.models.expressions import Exists, OuterRef, Value
from django.http.response import HttpResponse, HttpResponseForbidden
from django.views.decorators.csrf import csrf_exempt
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

# Standard Library
import json
import logging
from functools import lru_cache
import pdb

# DocumentCloud
from documentcloud.documents.models import (
    Entity,
)
from documentcloud.documents.serializers import (
    EntitySerializer,
)
from documentcloud.documents.entity_extraction import _get_or_create_entities

logger = logging.getLogger(__name__)


class FreestandingEntityViewSet(viewsets.ModelViewSet):
    serializer_class = EntitySerializer
    queryset = Entity.objects.none()

    @lru_cache()
    def get_queryset(self):
        #pdb.set_trace()
        # TODO: Should everyone be able to view all entities?
        return Entity.objects.all()

    def perform_create(self, serializer):
        #pdb.set_trace()
        """Initiate asyncrhonous creation of entities"""
        print("data", self.request.data)
        entity_map = _get_or_create_entities([ self.request.data ])
        # pylint: disable=unused-argument
        return Response(entity_map)
