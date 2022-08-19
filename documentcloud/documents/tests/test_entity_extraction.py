# Django
from django.conf import settings
from django.db import connection, reset_queries
from django.test.utils import override_settings
from rest_framework import status

import pdb
import json

# Third Party
import pytest

# DocumentCloud
from documentcloud.core.tests import run_commit_hooks
from documentcloud.documents.models import Entity
from documentcloud.documents.entity_extraction import _get_or_create_entities

# pylint: disable=too-many-lines, too-many-public-methods

entity_dict = {
	"name": "Knight",
  "kind": 1,
	"type_": 1,
	"metadata": {
      "wikipedia_url": "https://en.wikipedia.org/wiki/Knight"
	},
	"salience": 0.14932491,
	"mentions": [{
			"text": {
				"content": "Knight",
				"begin_offset": 4397
			}
		},
		{
			"text": {
				"content": "Professor",
				"begin_offset": 4387
			}
		},
		{
			"text": {
				"content": "Knight",
				"begin_offset": 13852
			}
		},
		{
			"text": {
				"content": "Professor",
				"begin_offset": 13842
			}
		},
		{
			"text": {
				"content": "Knight",
				"begin_offset": 16824
			}
		},
		{
			"text": {
				"content": "Professor",
				"begin_offset": 16814
			}
		},
		{
			"text": {
				"content": "Knight",
				"begin_offset": 17444
			}
		},
		{
			"text": {
				"content": "Professor",
				"begin_offset": 17434
			},
			"type_": 2
		},
		{
			"text": {
				"content": "Knight",
				"begin_offset": 17873
			},
			"type_": 1
		},
		{
			"text": {
				"content": "Professor",
				"begin_offset": 17863
			},
			"type_": 2
		},
		{
			"text": {
				"content": "Knight",
				"begin_offset": 26361
			},
			"type_": 1
		},
		{
			"text": {
				"content": "Professor",
				"begin_offset": 26351
			},
			"type_": 2
		},
		{
			"text": {
				"content": "Knight",
				"begin_offset": 26498
			},
			"type_": 1
		},
		{
			"text": {
				"content": "Professor",
				"begin_offset": 26488
			},
			"type_": 2
		},
		{
			"text": {
				"content": "Knight",
				"begin_offset": 27352
			},
			"type_": 1
		},
		{
			"text": {
				"content": "Knight",
				"begin_offset": 27899
			},
			"type_": 1
		},
		{
			"text": {
				"content": "Knight",
				"begin_offset": 30121
			},
			"type_": 1
		},
		{
			"text": {
				"content": "Professor",
				"begin_offset": 30111
			},
			"type_": 2
		},
		{
			"text": {
				"content": "Knight",
				"begin_offset": 30432
			},
			"type_": 1
		},
		{
			"text": {
				"content": "Professor",
				"begin_offset": 30422
			},
			"type_": 2
		},
		{
			"text": {
				"content": "Knight",
				"begin_offset": 31321
			},
			"type_": 1
		},
		{
			"text": {
				"content": "Professor",
				"begin_offset": 31311
			},
			"type_": 2
		},
		{
			"text": {
				"content": "Knight",
				"begin_offset": 31915
			},
			"type_": 1
		},
		{
			"text": {
				"content": "Professor",
				"begin_offset": 31905
			},
			"type_": 2
		},
		{
			"text": {
				"content": "Knight",
				"begin_offset": 32254
			},
			"type_": 1
		},
		{
			"text": {
				"content": "Professor",
				"begin_offset": 32244
			},
			"type_": 2
		},
		{
			"text": {
				"content": "Knight",
				"begin_offset": 32528
			},
			"type_": 1
		},
		{
			"text": {
				"content": "Professor",
				"begin_offset": 32518
			},
			"type_": 2
		},
		{
			"text": {
				"content": "Knight",
				"begin_offset": 43223
			},
			"type_": 1
		},
		{
			"text": {
				"content": "Professor",
				"begin_offset": 43213
			},
			"type_": 2
		}
	]
}

@pytest.mark.django_db()
class TestEntityExtraction:
    def mock_bulk_create(self, entity_objs):
        self.entity_objs_passed_to_bulk_create = entity_objs
        print("entity_objs", entity_objs)

    def test_get_or_create_entities(self):
        """get or create entities"""
        self.entity_objs_passed_to_bulk_create = None
        #entity = Entity(**entity_dict)
        #assert entity
        #pdb.set_trace()

        # Mock
        _get_or_create_entities([entity_dict], bulk_create=self.mock_bulk_create)
        assert self.entity_objs_passed_to_bulk_create, "Entity objects were not passed to bulk_create."
        assert len(self.entity_objs_passed_to_bulk_create) == 1, "The number of entity objects passed to bulk_create are incorrect."
        entity_obj = self.entity_objs_passed_to_bulk_create[0]
        #pdb.set_trace()

        assert entity_obj.description == ""
        assert not entity_obj.id, "Primary key"
        assert entity_obj.kind == 1
        assert entity_obj.metadata == {}
        assert entity_obj.mid == ""
        assert entity_obj.name == "Knight"
        assert entity_obj.wikipedia_url == "https://en.wikipedia.org/wiki/Knight"
        #assert 1 == 2, "hey"
