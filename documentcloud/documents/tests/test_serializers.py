# Third Party
import pytest

# DocumentCloud
from documentcloud.documents.serializers import (
    DocumentSerializer,
    ModificationSpecSerializer,
)
from documentcloud.documents.tests.factories import DocumentFactory


class TestDocumentSerializer:
    def test_good_data(self):
        """Test validating good value for `data`"""
        serializer = DocumentSerializer(data={"data": {"a": ["1"]}}, partial=True)
        assert serializer.is_valid()

    def test_good_data_auto_list(self):
        """Test automatically listing a single string in `data`"""
        serializer = DocumentSerializer(data={"data": {"a": "1"}}, partial=True)
        assert serializer.is_valid()
        assert serializer.validated_data["data"]["a"] == ["1"]

    @pytest.mark.parametrize("data", [["a"], {"a": {"b": 1}}, {"a": ["1", [2]]}])
    def test_bad_data(self, data):
        serializer = DocumentSerializer(data={"data": data}, partial=True)
        assert not serializer.is_valid()

    def test_description_max_length(self):
        """Test validating max length for description"""
        serializer = DocumentSerializer(data={"description": "a"}, partial=True)
        assert serializer.is_valid()
        serializer = DocumentSerializer(data={"description": "a" * 4001}, partial=True)
        assert not serializer.is_valid()


@pytest.mark.django_db()
class TestModificationSerializer:
    def get_modification_serializer(self, data, page_count):
        document = DocumentFactory(page_count=page_count)

        class AttributeDict(dict):
            __slots__ = ()
            __getattr__ = dict.__getitem__
            __setattr__ = dict.__setitem__

        return ModificationSpecSerializer(
            data={"data": data},
            context={"view": AttributeDict({"kwargs": {"document_pk": document.pk}})},
        )

    def test_good_data_empty(self):
        serializer = self.get_modification_serializer([], 1)
        assert serializer.is_valid()

    def test_good_data_simple(self):
        serializer = self.get_modification_serializer([{"page": "0-500"}], 1000)
        assert serializer.is_valid()

    def test_good_data_bad_page_count(self):
        serializer = self.get_modification_serializer(
            [{"page": "0-500"}], 500
        )  # need 501 pages, since 0-indexed
        assert not serializer.is_valid()

    def test_good_data_complex(self):
        serializer = self.get_modification_serializer(
            [
                {"page": "2,0"},
                {"page": "1-3", "modifications": [{"type": "rotate", "angle": "cc"}]},
                {
                    "page": "1",
                    "modifications": [
                        {"type": "rotate", "angle": "cc"},
                        {"type": "rotate", "angle": "hw"},
                        {"type": "rotate", "angle": "ccw"},
                    ],
                },
            ],
            4,
        )
        assert serializer.is_valid()

    def test_bad_data_page(self):
        serializer = self.get_modification_serializer([{"page": "a-3"}], 100)
        assert not serializer.is_valid()

    def test_other_doc_id(self):
        long_doc = DocumentFactory(page_count=100)
        serializer = self.get_modification_serializer(
            [{"page": "0-49", "id": long_doc.pk}], 10
        )
        assert serializer.is_valid()

    def test_other_doc_id_too_short(self):
        short_doc = DocumentFactory(page_count=20)
        serializer = self.get_modification_serializer(
            [{"page": "0-49", "id": short_doc.pk}], 10
        )
        assert not serializer.is_valid()
