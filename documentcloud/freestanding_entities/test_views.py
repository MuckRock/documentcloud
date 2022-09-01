# Django
from django.conf import settings
from django.db import connection, reset_queries
from django.test.utils import override_settings
from rest_framework import status

import pdb

# Third Party
import pytest

# DocumentCloud
from documentcloud.documents.tests.factories import (
    DocumentErrorFactory,
    DocumentFactory,
    EntityDateFactory,
    EntityOccurrenceFactory,
    LegacyEntityFactory,
    NoteFactory,
    SectionFactory,
)

# pylint: disable=too-many-lines, too-many-public-methods

class TestFreestandingEntityAPI:
    def test_create_freestanding_entity(self, client, document, user, mocker):
        #"""Create freestanding entities"""
        entity_body = {
            "name": "Dog",
            "kind": "unknown",
            "metadata": {"wikipedia_url": "https://en.wikipedia.org/wiki/Dog" }
        }
        pdb.set_trace()
        _get_or_create_entities = mocker.patch(
            "documentcloud.documents.entity_extraction._get_or_create_entities",
            return_value={ "mock_mid": entity_body }
        )

        client.force_authenticate(user=user)
        response = client.post(
            "/api/freestanding_entities/",
            entity_body,
            format="json",
        )

        assert response.status_code == status.HTTP_201_CREATED
        assert response.content == b'{"name":"Dog","kind":"unknown","metadata":{"wikipedia_url":"https://en.wikipedia.org/wiki/Dog"}}'
        _get_or_create_entities.assert_called_once_with([ entity_body ])
        # TODO: Assert that the entity was returned. Do another case with an existing entity.
