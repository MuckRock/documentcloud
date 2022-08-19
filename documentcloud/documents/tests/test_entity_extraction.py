# Django
from django.conf import settings
from django.db import connection, reset_queries
from django.test.utils import override_settings
from rest_framework import status

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
    def test_get_or_create_entities(self):
        """get or create entities"""
        def mock_bulk_create(entity_objs):
          print("entity_objs", entity_objs)
          assert entity_objs
        #entity = Entity(**entity_dict)
        #assert entity
        _get_or_create_entities([entity_dict], bulk_create=mock_bulk_create)
        #assert len(response_json["results"]) == size
        # document list should never be cached
        #assert "no-cache" in response["Cache-Control"]
        #assert "public" not in response["Cache-Control"]
        #assert "max-age" not in response["Cache-Control"]
