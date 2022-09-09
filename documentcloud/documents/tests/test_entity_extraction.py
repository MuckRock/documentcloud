# Third Party
import pytest

# DocumentCloud
from documentcloud.documents.entity_extraction import _get_or_create_entities

# pylint: disable=too-many-lines, too-many-public-methods

entity_dict = {
    "name": "Knight",
    "kind": 1,
    "type_": 1,
    "metadata": {"wikipedia_url": "https://en.wikipedia.org/wiki/Knight"},
    "salience": 0.14932491,
    "mentions": [
        {"text": {"content": "Knight", "begin_offset": 4397}},
        {"text": {"content": "Professor", "begin_offset": 4387}},
    ],
}


@pytest.mark.django_db()
class TestEntityExtraction:
    def test_get_or_create_entities(self, mocker):
        """get or create entities"""
        mock_bulk_create = mocker.patch(
            "documentcloud.documents.entity_extraction.Entity.objects.bulk_create"
        )

        _get_or_create_entities([entity_dict])

        assert mock_bulk_create.call_args.args[
            0
        ], "Entity objects were not passed to bulk_create."
        assert (
            len(mock_bulk_create.call_args.args[0]) == 1
        ), "The number of entity objects passed to bulk_create are incorrect."
        entity_obj = mock_bulk_create.call_args.args[0][0]

        assert entity_obj.description == ""
        assert not entity_obj.id, "Primary key"
        assert entity_obj.kind == 1
        assert entity_obj.metadata == {}
        assert entity_obj.mid == ""
        assert entity_obj.name == "Knight"
        assert entity_obj.wikipedia_url == "https://en.wikipedia.org/wiki/Knight"
